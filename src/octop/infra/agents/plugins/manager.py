"""Install, load, and expose plugins under ``~/.octop/plugins/``."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml
from octop_harness.plugins import (
    LoadedPlugin,
    PluginManifest,
    PluginRegistry,
    discover_plugin_dirs,
    load_plugin_dir,
    unload_plugin,
)

from octop.infra.agents.plugins.legacy_imports import ensure_legacy_harness_agent_alias
from octop.infra.errors import ErrorCode, OctopError, corrupt_config_error
from octop.infra.market import (
    PortalMarketError,
    get_market_plugin,
    is_market_archive_url,
    list_market_plugins,
    pick_localized,
)
from octop.infra.market.errors import local_network_error
from octop.infra.utils.json_file import (
    JsonFileCorruptError,
    read_json_object,
    write_json_atomic,
)

logger = logging.getLogger(__name__)

_MAX_PLUGIN_ARCHIVE_BYTES = 100 * 1024 * 1024
_MAX_PLUGIN_ZIP_ENTRIES = 2_000
_MAX_PLUGIN_UNCOMPRESSED_BYTES = 64 * 1024 * 1024
_MAX_PLUGIN_MEMBER_BYTES = 64 * 1024 * 1024
_MAX_PLUGIN_COMPRESSION_RATIO = 100.0
_DOWNLOAD_CHUNK = 64 * 1024

_GITHUB_BLOB_RE = re.compile(
    r"^https?://(?:www\.)?github\.com/"
    r"(?P<owner>[^/]+)/(?P<repo>[^/]+)/(?:blob|raw)/"
    r"(?P<ref>[^/]+)/(?P<path>.+)$",
    re.IGNORECASE,
)


_CHANNEL_FINGERPRINTS: dict[str, str] = {}


def _channel_fingerprint(directory: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(directory.rglob("*")):
        if not path.is_file() or any(
            part in {"__pycache__", ".git"} for part in path.relative_to(directory).parts
        ):
            continue
        digest.update(str(path.relative_to(directory)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def normalize_plugin_download_url(url: str) -> str:
    """Rewrite GitHub ``/blob/`` (and ``/raw/``) page URLs to raw content URLs.

    ``https://github.com/org/repo/blob/main/plugin.zip`` returns HTML, not the
    archive — that is the common cause of ``BadZipFile`` during install.
    """
    cleaned = url.strip()
    match = _GITHUB_BLOB_RE.match(cleaned)
    if match is None:
        return cleaned
    owner = match.group("owner")
    repo = match.group("repo")
    ref = match.group("ref")
    path = match.group("path").lstrip("/")
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}"


def _load_plugin_dir(plugin_dir: Path, *, install_deps: bool) -> LoadedPlugin:
    """Load one plugin, accepting the pre-rename ``harness_agent`` import."""
    ensure_legacy_harness_agent_alias()
    return load_plugin_dir(plugin_dir, install_deps=install_deps)


def _read_global_plugins(config_path: Path) -> dict[str, bool]:
    if not config_path.is_file():
        return {}
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    plugins = raw.get("plugins")
    if not isinstance(plugins, dict):
        return {}
    out: dict[str, bool] = {}
    for plugin_id, entry in plugins.items():
        if isinstance(entry, dict):
            out[str(plugin_id)] = bool(entry.get("enabled", True))
        else:
            out[str(plugin_id)] = True
    return out


def _write_global_plugin_enabled(config_path: Path, plugin_id: str, enabled: bool) -> None:
    """Merge ``plugins.<id>.enabled`` into ``config.json`` without dropping other keys.

    A corrupt config.json raises instead of being treated as empty: merging into
    ``{}`` and writing back destroys every other setting, including the
    ``database`` section (issue #730).
    """
    try:
        data = read_json_object(config_path)
    except JsonFileCorruptError as exc:
        raise corrupt_config_error(exc.path, exc.detail) from exc
    if data is None:
        data = {}
    plugins = data.get("plugins")
    if not isinstance(plugins, dict):
        plugins = {}
        data["plugins"] = plugins
    entry = plugins.get(plugin_id)
    if not isinstance(entry, dict):
        entry = {}
    entry["enabled"] = bool(enabled)
    plugins[plugin_id] = entry
    write_json_atomic(config_path, data)


def _assert_http_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise OctopError(
            ErrorCode.PLUGIN_INVALID_ARCHIVE,
            "plugin URL must be an http(s) address to a ZIP archive",
        )


def _assert_zip_magic(archive: Path) -> None:
    with archive.open("rb") as source:
        head = source.read(4)
    if len(head) < 2 or head[:2] != b"PK":
        raise OctopError(
            ErrorCode.PLUGIN_INVALID_ARCHIVE,
            "file is not a valid ZIP archive",
        )


def _archive_error(message: str) -> OctopError:
    return OctopError(ErrorCode.PLUGIN_INVALID_ARCHIVE, message)


def _validate_plugin_zip(zf: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    infos = zf.infolist()
    if len(infos) > _MAX_PLUGIN_ZIP_ENTRIES:
        raise _archive_error("plugin ZIP contains too many entries")

    total_uncompressed = 0
    for member in infos:
        if member.file_size < 0 or member.file_size > _MAX_PLUGIN_MEMBER_BYTES:
            raise _archive_error(f"plugin ZIP member is too large: {member.filename}")
        total_uncompressed += member.file_size
        if total_uncompressed > _MAX_PLUGIN_UNCOMPRESSED_BYTES:
            raise _archive_error("plugin ZIP expands beyond 64 MiB")
        compressed = member.compress_size or 0
        if (
            compressed > 0
            and member.file_size > 1024 * 1024
            and member.file_size / compressed > _MAX_PLUGIN_COMPRESSION_RATIO
        ):
            raise _archive_error(f"plugin ZIP compression ratio is too high: {member.filename}")
    return infos


def _download_plugin_archive(url: str, archive: Path) -> None:
    try:
        with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310
            content_length = response.headers.get("Content-Length")
            if content_length is not None:
                try:
                    if int(content_length) > _MAX_PLUGIN_ARCHIVE_BYTES:
                        raise _archive_error("plugin ZIP download exceeds the configured limit")
                except ValueError:
                    pass
            total = 0
            with archive.open("wb") as target:
                while True:
                    chunk = response.read(_DOWNLOAD_CHUNK)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > _MAX_PLUGIN_ARCHIVE_BYTES:
                        raise _archive_error("plugin ZIP download exceeds the configured limit")
                    target.write(chunk)
    except OctopError:
        raise
    except urllib.error.HTTPError as exc:
        raise OctopError(
            ErrorCode.PLUGIN_INSTALL_FAILED,
            f"download failed with HTTP {exc.code}",
            details={"reason": f"HTTP {exc.code}"},
        ) from exc
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", None) or str(exc)
        raise OctopError(
            ErrorCode.PLUGIN_INSTALL_FAILED,
            f"download failed: {reason}",
            details={"reason": str(reason)},
        ) from exc
    except OSError as exc:
        raise OctopError(
            ErrorCode.PLUGIN_INSTALL_FAILED, f"download failed: {exc}", details={"reason": str(exc)}
        ) from exc


def _read_plugin_yaml(plugin_dir: Path) -> dict[str, Any]:
    raw = yaml.safe_load((plugin_dir / "plugin.yaml").read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def parse_plugin_ui_meta(plugin_dir: Path) -> dict[str, str] | None:
    """Return ``{entry, manifest}`` relative paths when ``plugin.yaml`` declares ``ui``.

    Missing entry file → ``None`` (treat as backend-only). Harness ignores the
    ``ui`` key; Octop surfaces it for Dashboard dynamic loading.
    """
    try:
        data = _read_plugin_yaml(plugin_dir)
    except Exception:
        return None
    ui = data.get("ui")
    if not isinstance(ui, dict):
        return None
    entry = str(ui.get("entry") or "ui/dist/index.js").strip()
    manifest = str(ui.get("manifest") or "ui/dist/manifest.json").strip()
    if not entry or ".." in entry.replace("\\", "/").split("/"):
        return None
    if ".." in manifest.replace("\\", "/").split("/"):
        return None
    if not (plugin_dir / entry).is_file():
        logger.warning(
            "plugin %s declares ui.entry=%s but file is missing",
            plugin_dir.name,
            entry,
        )
        return None
    return {"entry": entry, "manifest": manifest}


_ICON_FILE_SUFFIXES = {".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif"}

# Stable catalog slugs for Dashboard grouping. Unknown values still pass through.
PLUGIN_GROUPS: frozenset[str] = frozenset(
    {
        "lifestyle",
        "news",
        "finance",
        "media",
        "fun",
        "games",
        "tools",
        "ops",
    },
)


def parse_plugin_group(plugin_dir: Path) -> str | None:
    """Optional ``group`` slug from ``plugin.yaml`` (e.g. ``lifestyle``, ``games``)."""
    try:
        data = _read_plugin_yaml(plugin_dir)
    except Exception:
        return None
    raw = data.get("group")
    if raw is None:
        return None
    group = str(raw).strip().lower().replace("_", "-")
    if not group or len(group) > 64:
        return None
    if not all(ch.isalnum() or ch == "-" for ch in group):
        return None
    return group


def parse_plugin_icon(
    plugin_dir: Path,
    *,
    asset_prefix: str | None = None,
) -> str | None:
    """Optional ``icon`` from ``plugin.yaml`` for Dashboard cards.

    Accepts emoji text, absolute ``http(s)://`` / ``/api/...`` URLs, or a
    plugin-relative image path (e.g. ``icon.svg``) resolved to
    ``/api/plugins/{id}/ui/...`` (or ``asset_prefix`` when listing the market).
    """
    try:
        data = _read_plugin_yaml(plugin_dir)
    except Exception:
        return None
    raw = data.get("icon")
    if raw is None:
        return None
    icon = str(raw).strip()
    if not icon or len(icon) > 2048:
        return None
    if icon.startswith(("http://", "https://", "/api/", "data:image/")) or icon.startswith("//"):
        return icon
    # Relative image file shipped with the plugin package.
    cleaned = icon.lstrip("/").replace("\\", "/")
    if (
        cleaned
        and ".." not in cleaned.split("/")
        and Path(cleaned).suffix.lower() in _ICON_FILE_SUFFIXES
    ):
        target = (plugin_dir / cleaned).resolve()
        try:
            target.relative_to(plugin_dir.resolve())
        except ValueError:
            return icon
        if target.is_file():
            plugin_id = str(data.get("id") or plugin_dir.name).strip() or plugin_dir.name
            prefix = (asset_prefix or f"/api/plugins/{plugin_id}/ui").rstrip("/")
            return f"{prefix}/{cleaned}"
    return icon


def parse_plugin_requires(plugin_dir: Path) -> list[str]:
    try:
        data = _read_plugin_yaml(plugin_dir)
    except Exception:
        return []
    raw = data.get("requires") or []
    if not isinstance(raw, list):
        return []
    return [str(r).strip() for r in raw if str(r).strip()]


def _read_installed_version(plugin_dir: Path) -> str | None:
    try:
        data = _read_plugin_yaml(plugin_dir)
    except Exception:
        return None
    ver = data.get("version")
    if ver is None:
        return None
    text = str(ver).strip()
    return text or None


def _version_tuple(version: str | None) -> tuple[int, ...]:
    ver = str(version or "0").strip() or "0"
    parts: list[int] = []
    for bit in ver.split("."):
        try:
            parts.append(int(bit))
        except ValueError:
            parts.append(0)
    return tuple(parts) or (0,)


_MARKET_ASSET_SUFFIXES = frozenset({".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif"})


class PluginManager:
    def __init__(self, *, plugins_dir: Path, config_path: Path) -> None:
        self._plugins_dir = plugins_dir
        self._config_path = config_path
        self._plugins_dir.mkdir(parents=True, exist_ok=True)
        # Last-known tool metadata so Admin / Experts can still list tools after
        # a global disable unloads the plugin from the process registry.
        self._tool_catalog: dict[str, list[dict[str, Any]]] = {}
        self._skill_catalog: dict[str, set[str]] = {}

    @property
    def plugins_dir(self) -> Path:
        return self._plugins_dir

    def global_enabled_map(self) -> dict[str, bool]:
        return _read_global_plugins(self._config_path)

    def seed_bundled(self) -> list[str]:
        """Upgrade already-installed bundled plugins when catalog versions are newer."""
        from octop.infra.agents.plugins.bundled import default_bundled_plugins_root
        from octop.infra.agents.plugins.seed import seed_bundled_plugins

        return seed_bundled_plugins(
            bundled_root=default_bundled_plugins_root(),
            plugins_dir=self._plugins_dir,
            config_path=self._config_path,
        )

    def market_root(self) -> Path:
        from octop.infra.agents.plugins.bundled import default_bundled_plugins_root

        return default_bundled_plugins_root()

    def market_plugin_dir(self, plugin_id: str) -> Path | None:
        """Return a catalog plugin directory when it exists under the market root."""
        cleaned = plugin_id.strip()
        if not cleaned or ".." in cleaned or "/" in cleaned or "\\" in cleaned:
            return None
        dest = self.market_root() / cleaned
        if dest.is_dir() and (dest / "plugin.yaml").is_file():
            return dest
        return None

    def list_market(self, language: str = "zh") -> list[dict[str, Any]]:
        """List marketplace plugins from the portal catalog."""
        try:
            remote = list_market_plugins()
        except PortalMarketError as exc:
            logger.warning("remote plugin market unavailable: %s", exc)
            network_error = local_network_error(exc)
            if network_error is not None:
                raise network_error from exc
            raise OctopError(
                ErrorCode.PLUGIN_MARKET_FAILED,
                "plugin market failed: upstream request failed",
                details={"reason": "upstream request failed"},
            ) from exc
        return [self._remote_plugin_row(item, language) for item in remote]

    def _remote_plugin_row(self, item: dict[str, Any], language: str) -> dict[str, Any]:
        plugin_id = str(item.get("id") or "").strip()
        version = str(item.get("version") or "")
        installed_dir = self.plugin_dir(plugin_id) if plugin_id else None
        installed_version = (
            None if installed_dir is None else _read_installed_version(installed_dir)
        )
        icon = item.get("icon")
        group = item.get("group")
        raw_requires = item.get("requires")
        requires = raw_requires if isinstance(raw_requires, list) else []
        return {
            "id": plugin_id,
            "version": version,
            "name": pick_localized(item.get("name"), language) or plugin_id,
            "kind": str(item.get("kind") or "tool"),
            "description": pick_localized(item.get("description"), language),
            "icon": icon.strip() if isinstance(icon, str) and icon.strip() else None,
            "group": group.strip() if isinstance(group, str) and group.strip() else None,
            "requires": [
                str(item_name).strip() for item_name in requires if str(item_name).strip()
            ],
            "installed": installed_dir is not None,
            "installed_version": installed_version,
            "update_available": (
                installed_dir is not None
                and _version_tuple(version) > _version_tuple(installed_version)
            ),
        }

    def install_from_market(
        self,
        plugin_id: str,
        *,
        version: str | None = None,
        force: bool = False,
    ) -> LoadedPlugin:
        """Install one marketplace release from its CDN archive.

        ``version`` selects the catalog release. ``latest`` means the release
        currently listed for that id. A different release already on disk is
        replaced. ``force`` replaces the same release.
        """
        requested = version.strip() if version else None
        if requested == "latest":
            requested = None
        try:
            remote = get_market_plugin(plugin_id)
        except PortalMarketError as exc:
            logger.warning("remote plugin market unavailable: %s", exc)
            network_error = local_network_error(exc)
            if network_error is not None:
                raise network_error from exc
            raise OctopError(
                ErrorCode.PLUGIN_MARKET_FAILED,
                "plugin market failed: upstream request failed",
                details={"reason": "upstream request failed"},
            ) from exc
        if remote is None:
            raise OctopError(
                ErrorCode.NOT_FOUND,
                f"marketplace plugin {plugin_id!r} not found",
            )
        catalog_version = str(remote.get("version") or "")
        if requested and catalog_version != requested:
            raise OctopError(
                ErrorCode.NOT_FOUND,
                f"marketplace plugin {plugin_id!r} version {requested!r} not found",
            )
        url = remote.get("download_url")
        if not isinstance(url, str) or not is_market_archive_url(url):
            raise OctopError(
                ErrorCode.PLUGIN_INSTALL_FAILED,
                f"marketplace plugin {plugin_id!r} has no archive",
            )
        loaded = self.install_url(
            url,
            force=self._replace_market_release(
                plugin_id,
                requested or catalog_version,
                force=force,
            ),
            expect_id=plugin_id,
            expect_version=catalog_version or None,
        )
        _write_global_plugin_enabled(self._config_path, loaded.manifest.id, True)
        return loaded

    def _replace_market_release(self, plugin_id: str, version: str, *, force: bool) -> bool:
        """Replace disk contents when installing a different catalog release."""
        if force:
            return True
        installed_dir = self.plugin_dir(plugin_id)
        if installed_dir is None or not version:
            return False
        return _read_installed_version(installed_dir) != version

    def resolve_market_ui_file(self, plugin_id: str, rel_path: str) -> Path:
        """Resolve a marketplace catalog asset (icons only)."""
        plugin_dir = self.market_plugin_dir(plugin_id)
        if plugin_dir is None:
            raise OctopError(
                ErrorCode.NOT_FOUND,
                f"marketplace plugin {plugin_id!r} not found",
            )
        cleaned = rel_path.strip().lstrip("/").replace("\\", "/")
        suffix = Path(cleaned).suffix.lower()
        if suffix not in _MARKET_ASSET_SUFFIXES:
            raise OctopError(ErrorCode.NOT_FOUND, "invalid marketplace asset path")
        return self._resolve_plugin_asset(plugin_dir, cleaned)

    def load_installed(self, *, install_deps: bool = True) -> list[LoadedPlugin]:
        enabled = self.global_enabled_map()
        previous = {plugin.manifest.id: plugin for plugin in PluginRegistry().all_loaded()}
        PluginRegistry().clear()
        loaded: list[LoadedPlugin] = []
        for plugin_dir in discover_plugin_dirs(self._plugins_dir):
            try:
                manifest = PluginManifest.load(plugin_dir / "plugin.yaml")
            except Exception as exc:
                logger.error("skip plugin dir %s: %s", plugin_dir, exc)
                continue
            if enabled.get(manifest.id, True) is False:
                continue
            try:
                fingerprint = (
                    _channel_fingerprint(plugin_dir) if str(manifest.kind) == "channel" else ""
                )
                old = previous.get(manifest.id)
                if (
                    str(manifest.kind) == "channel"
                    and old is not None
                    and _CHANNEL_FINGERPRINTS.get(manifest.id) == fingerprint
                ):
                    PluginRegistry().register(old)
                    loaded.append(old)
                else:
                    loaded.append(_load_plugin_dir(plugin_dir, install_deps=install_deps))
                if str(manifest.kind) == "channel":
                    _CHANNEL_FINGERPRINTS[manifest.id] = fingerprint
            except Exception as exc:
                logger.error(
                    "failed to load plugin from %s: %s",
                    plugin_dir,
                    exc,
                    exc_info=True,
                )
        for plugin_id, is_on in enabled.items():
            if not is_on:
                unload_plugin(plugin_id)
        return [p for p in loaded if enabled.get(p.manifest.id, True) is not False]

    def load_missing(self, *, install_deps: bool = False) -> list[LoadedPlugin]:
        """Load any on-disk plugins that are not yet in the process registry.

        Used after CLI ``octop plugin install`` while ``octop run`` is already
        up — unlike ``load_installed``, this does not clear already-loaded
        plugins.
        """
        enabled = self.global_enabled_map()
        newly: list[LoadedPlugin] = []
        for plugin_dir in discover_plugin_dirs(self._plugins_dir):
            try:
                manifest = PluginManifest.load(plugin_dir / "plugin.yaml")
            except Exception as exc:
                logger.error("skip plugin dir %s: %s", plugin_dir, exc)
                continue
            if enabled.get(manifest.id) is False:
                continue
            if PluginRegistry().get(manifest.id) is not None:
                continue
            try:
                newly.append(_load_plugin_dir(plugin_dir, install_deps=install_deps))
                logger.info(
                    "loaded missing plugin %s v%s",
                    manifest.id,
                    manifest.version,
                )
            except Exception as exc:
                logger.error(
                    "failed to load plugin from %s: %s",
                    plugin_dir,
                    exc,
                    exc_info=True,
                )
        return newly

    @staticmethod
    def _channel_registration_error(plugin_id: str) -> str | None:
        from octop.infra.gateway.plugin_channels import registration_errors

        return registration_errors().get(plugin_id)

    def list_installed(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        enabled_map = self.global_enabled_map()
        for plugin_dir in discover_plugin_dirs(self._plugins_dir):
            try:
                manifest = PluginManifest.load(plugin_dir / "plugin.yaml")
            except Exception as exc:
                out.append(
                    {
                        "id": plugin_dir.name,
                        "error": str(exc),
                        "path": str(plugin_dir),
                        "enabled": enabled_map.get(plugin_dir.name, True),
                    },
                )
                continue
            loaded = PluginRegistry().get(manifest.id)
            ui_meta = parse_plugin_ui_meta(plugin_dir)
            if loaded is not None:
                tools_meta = [
                    {
                        "name": t.name,
                        "description": t.description,
                        "config_fields": t.config_fields,
                    }
                    for t in loaded.tools
                ]
                self._tool_catalog[manifest.id] = tools_meta
                if loaded.skills_dir is not None:
                    self._skill_catalog[manifest.id] = {
                        path.name
                        for path in loaded.skills_dir.iterdir()
                        if path.is_dir() and (path / "SKILL.md").is_file()
                    }
            else:
                tools_meta = list(self._tool_catalog.get(manifest.id) or [])
            out.append(
                {
                    "id": manifest.id,
                    "version": manifest.version,
                    "name": manifest.name,
                    "kind": manifest.kind,
                    "description": manifest.description,
                    "icon": parse_plugin_icon(plugin_dir),
                    "group": parse_plugin_group(plugin_dir),
                    "requires": parse_plugin_requires(plugin_dir),
                    "path": str(plugin_dir),
                    "loaded": loaded is not None,
                    "registration_error": self._channel_registration_error(manifest.id),
                    "enabled": enabled_map.get(manifest.id, True),
                    "ui": ui_meta,
                    "tools": tools_meta,
                },
            )
        return out

    def set_enabled(self, plugin_id: str, enabled: bool) -> dict[str, Any]:
        """Toggle global plugin enablement in ``config.json`` and load/unload registry."""
        plugin_dir = self.plugin_dir(plugin_id)
        if plugin_dir is None:
            raise OctopError(ErrorCode.NOT_FOUND, f"plugin {plugin_id!r} not found")
        try:
            PluginManifest.load(plugin_dir / "plugin.yaml")
        except Exception as exc:
            raise OctopError(
                ErrorCode.PLUGIN_INVALID_ARCHIVE,
                f"invalid plugin manifest: {exc}",
            ) from exc

        _write_global_plugin_enabled(self._config_path, plugin_id, enabled)
        if enabled:
            if PluginRegistry().get(plugin_id) is None:
                try:
                    _load_plugin_dir(plugin_dir, install_deps=False)
                except Exception as exc:
                    raise OctopError(
                        ErrorCode.PLUGIN_INSTALL_FAILED,
                        f"failed to load plugin: {exc}",
                        details={"reason": str(exc)},
                    ) from exc
        else:
            loaded = PluginRegistry().get(plugin_id)
            if loaded is not None:
                self._tool_catalog[plugin_id] = [
                    {
                        "name": t.name,
                        "description": t.description,
                        "config_fields": t.config_fields,
                    }
                    for t in loaded.tools
                ]
                if loaded.skills_dir is not None:
                    self._skill_catalog[plugin_id] = {
                        path.name
                        for path in loaded.skills_dir.iterdir()
                        if path.is_dir() and (path / "SKILL.md").is_file()
                    }
            unload_plugin(plugin_id)

        for item in self.list_installed():
            if item.get("id") == plugin_id:
                return item
        return {"id": plugin_id, "enabled": enabled}

    def plugin_dir(self, plugin_id: str) -> Path | None:
        """Return the on-disk plugin directory when it exists."""
        dest = self._plugins_dir / plugin_id
        if dest.is_dir() and (dest / "plugin.yaml").is_file():
            return dest
        return None

    def resolve_ui_file(self, plugin_id: str, rel_path: str) -> Path:
        """Resolve a UI asset under the plugin tree with path-traversal checks.

        ``rel_path`` is typically relative to ``<plugin>/ui/`` (e.g. ``dist/index.js``)
        as served by ``GET /api/plugins/{id}/ui/{path}``. Full paths from the
        plugin root (``ui/dist/index.js``) are also accepted.
        """
        plugin_dir = self.plugin_dir(plugin_id)
        if plugin_dir is None:
            raise OctopError(
                ErrorCode.NOT_FOUND,
                f"plugin {plugin_id!r} not found",
            )
        return self._resolve_plugin_asset(plugin_dir, rel_path)

    @staticmethod
    def _resolve_plugin_asset(plugin_dir: Path, rel_path: str) -> Path:
        cleaned = rel_path.strip().lstrip("/").replace("\\", "/")
        if not cleaned or any(part == ".." for part in cleaned.split("/")):
            raise OctopError(ErrorCode.NOT_FOUND, "invalid plugin UI path")
        candidates = [
            plugin_dir / "ui" / cleaned,
            plugin_dir / cleaned,
        ]
        if not cleaned.startswith("ui/") and not cleaned.startswith("dist/"):
            candidates.append(plugin_dir / "ui" / "dist" / cleaned)
        for target in candidates:
            resolved = target.resolve()
            try:
                resolved.relative_to(plugin_dir.resolve())
            except ValueError as exc:
                raise OctopError(ErrorCode.NOT_FOUND, "invalid plugin UI path") from exc
            if resolved.is_file():
                return resolved
        raise OctopError(
            ErrorCode.NOT_FOUND,
            f"plugin UI file not found: {cleaned}",
        )

    def install_path(
        self,
        source: Path,
        *,
        force: bool = False,
        expect_id: str | None = None,
        expect_version: str | None = None,
    ) -> LoadedPlugin:
        source = source.resolve()
        if not source.is_dir():
            raise OctopError(
                ErrorCode.PLUGIN_INVALID_ARCHIVE,
                f"plugin directory not found: {source}",
            )
        try:
            manifest = PluginManifest.load(source / "plugin.yaml")
        except Exception as exc:
            raise OctopError(
                ErrorCode.PLUGIN_INVALID_ARCHIVE,
                f"invalid plugin manifest: {exc}",
            ) from exc
        if expect_id is not None and manifest.id != expect_id:
            raise OctopError(
                ErrorCode.PLUGIN_INVALID_ARCHIVE,
                f"plugin id {manifest.id!r} does not match {expect_id!r}",
            )
        if expect_version is not None and manifest.version != expect_version:
            raise OctopError(
                ErrorCode.PLUGIN_INVALID_ARCHIVE,
                f"plugin version {manifest.version!r} does not match {expect_version!r}",
            )
        dest = self._plugins_dir / manifest.id
        if dest.exists():
            if not force:
                raise OctopError(
                    ErrorCode.PLUGIN_ALREADY_EXISTS,
                    f"plugin already installed: {manifest.id}",
                    details={"id": manifest.id},
                )
            shutil.rmtree(dest)
        shutil.copytree(source, dest)
        unload_plugin(manifest.id)
        try:
            return _load_plugin_dir(dest, install_deps=True)
        except Exception as exc:
            raise OctopError(
                ErrorCode.PLUGIN_INSTALL_FAILED,
                f"failed to load plugin: {exc}",
                details={"reason": str(exc)},
            ) from exc

    def install_archive(
        self,
        archive: Path,
        *,
        force: bool = False,
        expect_id: str | None = None,
        expect_version: str | None = None,
    ) -> LoadedPlugin:
        """Install a plugin from a local ZIP archive.

        The archive must contain exactly one plugin directory (at the zip root
        or in a single top-level folder) with a ``plugin.yaml`` manifest.
        """
        _assert_zip_magic(archive)
        try:
            if archive.stat().st_size > _MAX_PLUGIN_ARCHIVE_BYTES:
                raise _archive_error("plugin ZIP exceeds 100 MiB")
        except OSError as exc:
            raise _archive_error(f"cannot inspect plugin ZIP: {exc}") from exc
        with tempfile.TemporaryDirectory() as tmp:
            extract_to = Path(tmp) / "extract"
            extract_to.mkdir()
            try:
                with zipfile.ZipFile(archive) as zf:
                    infos = _validate_plugin_zip(zf)
                    extract_root = extract_to.resolve()
                    for member in infos:
                        target = (extract_to / member.filename).resolve()
                        try:
                            target.relative_to(extract_root)
                        except ValueError as exc:
                            raise _archive_error("zip path traversal detected") from exc
                    total_written = 0
                    for member in infos:
                        target = (extract_to / member.filename).resolve()
                        if member.is_dir():
                            target.mkdir(parents=True, exist_ok=True)
                            continue
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with zf.open(member) as source, target.open("wb") as destination:
                            while True:
                                chunk = source.read(1024 * 1024)
                                if not chunk:
                                    break
                                total_written += len(chunk)
                                if total_written > _MAX_PLUGIN_UNCOMPRESSED_BYTES:
                                    raise _archive_error("plugin ZIP expands beyond 64 MiB")
                                destination.write(chunk)
            except OctopError:
                raise
            except zipfile.BadZipFile as exc:
                raise OctopError(
                    ErrorCode.PLUGIN_INVALID_ARCHIVE,
                    "file is not a valid ZIP archive",
                ) from exc

            # Support zip root being the plugin dir or containing one subdir
            candidates = [p for p in extract_to.iterdir() if (p / "plugin.yaml").is_file()]
            if not candidates and (extract_to / "plugin.yaml").is_file():
                candidates = [extract_to]
            if len(candidates) != 1:
                raise OctopError(
                    ErrorCode.PLUGIN_INVALID_ARCHIVE,
                    "zip must contain exactly one plugin directory with plugin.yaml",
                )
            return self.install_path(
                candidates[0],
                force=force,
                expect_id=expect_id,
                expect_version=expect_version,
            )

    def install_url(
        self,
        url: str,
        *,
        force: bool = False,
        expect_id: str | None = None,
        expect_version: str | None = None,
    ) -> LoadedPlugin:
        resolved = normalize_plugin_download_url(url)
        _assert_http_url(resolved)
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "plugin.zip"
            _download_plugin_archive(resolved, archive)
            try:
                return self.install_archive(
                    archive,
                    force=force,
                    expect_id=expect_id,
                    expect_version=expect_version,
                )
            except OctopError as exc:
                if exc.code is not ErrorCode.PLUGIN_INVALID_ARCHIVE:
                    raise
                raise OctopError(
                    ErrorCode.PLUGIN_INVALID_ARCHIVE,
                    f"{exc.message} (GitHub /blob/ pages return HTML — use a raw .zip URL)",
                    details=exc.details,
                ) from exc

    def uninstall(self, plugin_id: str) -> None:
        unload_plugin(plugin_id)
        self._tool_catalog.pop(plugin_id, None)
        self._skill_catalog.pop(plugin_id, None)
        dest = self._plugins_dir / plugin_id
        if dest.is_dir():
            shutil.rmtree(dest)

    def plugin_skill_names(self, plugin_id: str) -> set[str]:
        """Return skill directory names registered by one loaded plugin."""
        plugin = PluginRegistry().get(plugin_id)
        if plugin is None or plugin.skills_dir is None:
            return set(self._skill_catalog.get(plugin_id) or ())
        names = {
            path.name
            for path in plugin.skills_dir.iterdir()
            if path.is_dir() and (path / "SKILL.md").is_file()
        }
        self._skill_catalog[plugin_id] = names
        return set(names)

    def sync_skills_to_workspace(
        self,
        workspace: Any,
        *,
        agent_plugins: object = None,
    ) -> None:
        from octop_harness.backends.workspace import BackendWorkspace

        from octop.infra.agents.plugins.plugin_tool_defaults import agent_plugin_enabled

        if not isinstance(workspace, BackendWorkspace):
            return
        enabled = self.global_enabled_map()
        pairs: list[tuple[str, bytes]] = []
        for plugin in PluginRegistry().list_plugins():
            if enabled.get(plugin.manifest.id) is False:
                continue
            if not agent_plugin_enabled(agent_plugins, plugin.manifest.id):
                continue
            if plugin.skills_dir is None:
                continue
            for skill_dir in plugin.skills_dir.iterdir():
                if not skill_dir.is_dir():
                    continue
                if not (skill_dir / "SKILL.md").is_file():
                    continue
                dest = f"skills/{skill_dir.name}"
                if workspace.exists(f"{dest}/SKILL.md"):
                    continue
                for path in skill_dir.rglob("*"):
                    if not path.is_file():
                        continue
                    rel = path.relative_to(skill_dir).as_posix()
                    pairs.append((f"{dest}/{rel}", path.read_bytes()))
        if pairs:
            workspace.upload_many(pairs)
