"""Install, load, and expose plugins under ``~/.octop/plugins/``."""

from __future__ import annotations

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

from harness_agent.plugins import (
    LoadedPlugin,
    PluginManifest,
    PluginRegistry,
    discover_plugin_dirs,
    load_all,
    load_plugin_dir,
    unload_plugin,
)

from octop.infra.errors import ErrorCode, OctopError

logger = logging.getLogger(__name__)

_GITHUB_BLOB_RE = re.compile(
    r"^https?://(?:www\.)?github\.com/"
    r"(?P<owner>[^/]+)/(?P<repo>[^/]+)/(?:blob|raw)/"
    r"(?P<ref>[^/]+)/(?P<path>.+)$",
    re.IGNORECASE,
)


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


def _assert_http_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise OctopError(
            ErrorCode.PLUGIN_INVALID_ARCHIVE,
            "plugin URL must be an http(s) address to a ZIP archive",
        )


def _assert_zip_magic(archive: Path) -> None:
    head = archive.read_bytes()[:4]
    if len(head) < 2 or head[:2] != b"PK":
        raise OctopError(
            ErrorCode.PLUGIN_INVALID_ARCHIVE,
            "downloaded file is not a ZIP archive "
            "(GitHub /blob/ pages return HTML — use a raw .zip URL)",
        )


class PluginManager:
    def __init__(self, *, plugins_dir: Path, config_path: Path) -> None:
        self._plugins_dir = plugins_dir
        self._config_path = config_path
        self._plugins_dir.mkdir(parents=True, exist_ok=True)

    @property
    def plugins_dir(self) -> Path:
        return self._plugins_dir

    def global_enabled_map(self) -> dict[str, bool]:
        return _read_global_plugins(self._config_path)

    def load_installed(self, *, install_deps: bool = True) -> list[LoadedPlugin]:
        enabled = self.global_enabled_map()
        loaded = load_all(self._plugins_dir, install_deps=install_deps)
        # Drop globally disabled plugins from registry
        for plugin_id, is_on in enabled.items():
            if not is_on:
                unload_plugin(plugin_id)
        return [p for p in loaded if enabled.get(p.manifest.id, True)]

    def list_installed(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for plugin_dir in discover_plugin_dirs(self._plugins_dir):
            try:
                manifest = PluginManifest.load(plugin_dir / "plugin.yaml")
            except Exception as exc:
                out.append(
                    {
                        "id": plugin_dir.name,
                        "error": str(exc),
                        "path": str(plugin_dir),
                    },
                )
                continue
            loaded = PluginRegistry().get(manifest.id)
            out.append(
                {
                    "id": manifest.id,
                    "version": manifest.version,
                    "name": manifest.name,
                    "kind": manifest.kind,
                    "description": manifest.description,
                    "path": str(plugin_dir),
                    "loaded": loaded is not None,
                    "tools": [
                        {
                            "name": t.name,
                            "description": t.description,
                            "config_fields": t.config_fields,
                        }
                        for t in (loaded.tools if loaded else [])
                    ],
                },
            )
        return out

    def install_path(self, source: Path, *, force: bool = False) -> LoadedPlugin:
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
            return load_plugin_dir(dest, install_deps=True)
        except Exception as exc:
            raise OctopError(
                ErrorCode.PLUGIN_INSTALL_FAILED,
                f"failed to load plugin: {exc}",
                details={"reason": str(exc)},
            ) from exc

    def install_url(self, url: str, *, force: bool = False) -> LoadedPlugin:
        resolved = normalize_plugin_download_url(url)
        _assert_http_url(resolved)
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            archive = tmp_path / "plugin.zip"
            try:
                urllib.request.urlretrieve(resolved, archive)  # noqa: S310
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
                    ErrorCode.PLUGIN_INSTALL_FAILED,
                    f"download failed: {exc}",
                    details={"reason": str(exc)},
                ) from exc

            _assert_zip_magic(archive)
            extract_to = tmp_path / "extract"
            extract_to.mkdir()
            try:
                with zipfile.ZipFile(archive) as zf:
                    for member in zf.namelist():
                        target = (extract_to / member).resolve()
                        if not str(target).startswith(str(extract_to.resolve())):
                            raise OctopError(
                                ErrorCode.PLUGIN_INVALID_ARCHIVE,
                                "zip path traversal detected",
                            )
                    zf.extractall(extract_to)
            except OctopError:
                raise
            except zipfile.BadZipFile as exc:
                raise OctopError(
                    ErrorCode.PLUGIN_INVALID_ARCHIVE,
                    "downloaded file is not a valid ZIP archive",
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
            return self.install_path(candidates[0], force=force)

    def uninstall(self, plugin_id: str) -> None:
        unload_plugin(plugin_id)
        dest = self._plugins_dir / plugin_id
        if dest.is_dir():
            shutil.rmtree(dest)

    def sync_skills_to_workspace(self, workspace: Any) -> None:
        from harness_agent.backends.workspace import BackendWorkspace

        if not isinstance(workspace, BackendWorkspace):
            return
        enabled = self.global_enabled_map()
        pairs: list[tuple[str, bytes]] = []
        for plugin in PluginRegistry().list_plugins():
            if enabled.get(plugin.manifest.id) is False:
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
