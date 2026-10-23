"""Sandbox container ledger, drift detection, and safe recreate (admin).

Docker SDK calls are concentrated here (lazy ``import docker``) so tests can
inject a fake client. Containers are discovered live via the harness
``harness.agent.sandbox`` labels — no local registry. See
``docs/sandbox-image-management.md`` for the design.
"""

from __future__ import annotations

import json
import logging
import tarfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from octop.infra.errors import ErrorCode, OctopError

logger = logging.getLogger(__name__)

LABEL_SANDBOX = "harness.agent.sandbox"
LABEL_SCOPE = "harness.agent.sandbox_scope"
LABEL_AGENT_ID = "harness.agent.id"

_BACKUP_KEEP = 3


@dataclass(frozen=True)
class SandboxEntry:
    """One sandbox container row for the ledger."""

    container_name: str
    container_id: str
    scope: str
    agent_id: str | None
    status: str
    created_at: str
    image: str
    network_offline: bool | None
    expected_image: str | None = None
    expected_allow_network: bool | None = None
    drift: bool | None = None
    network_drift: bool | None = None
    affected_agents: list[dict[str, Any]] = field(default_factory=list)


def _load_docker_client() -> Any:
    """Return a docker client or raise ``SANDBOX_DOCKER_UNAVAILABLE``."""
    try:
        import docker  # noqa: PLC0415 — optional harness extra
    except ImportError as exc:
        raise OctopError(
            ErrorCode.SANDBOX_DOCKER_UNAVAILABLE,
            "docker Python package not installed (pip install 'octop-harness[docker]')",
        ) from exc
    try:
        client = cast(Any, docker).from_env()
        client.ping()
    except Exception as exc:
        raise OctopError(
            ErrorCode.SANDBOX_DOCKER_UNAVAILABLE,
            f"docker daemon unreachable: {exc}",
        ) from exc
    return client


def _container_labels(container: Any) -> dict[str, str]:
    config = (getattr(container, "attrs", {}) or {}).get("Config") or {}
    raw = config.get("Labels") or {}
    return raw if isinstance(raw, dict) else {}


def _network_offline(container: Any) -> bool | None:
    """True when the container has no networks besides ``none``."""
    networks = (getattr(container, "attrs", {}) or {}).get("NetworkSettings", {}) or {}
    nets = networks.get("Networks") or {}
    if not isinstance(nets, dict):
        return None
    return not [name for name in nets if name != "none"]


def _parse_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        low = value.strip().lower()
        if low in ("true", "1", "yes", "on"):
            return True
        if low in ("false", "0", "no", "off"):
            return False
    return None


def _expected_from_spec(spec: Any) -> tuple[str | None, bool | None]:
    """Extract ``(image, allow_network)`` from a resolved harness spec."""
    if not isinstance(spec, dict):
        return None, None
    image = spec.get("image")
    expected_image = str(image) if image else None
    if "allow_network" in spec:
        return expected_image, _parse_bool(spec.get("allow_network"))
    # harness DockerSandbox default: allow_network=False
    return expected_image, False if expected_image is not None else None


def _drift_direction(offline: bool | None, expected_allow: bool | None) -> str | None:
    """Human-readable network drift direction, e.g. ``offline→online``."""
    if offline is None or expected_allow is None:
        return None
    return "offline→online" if expected_allow else "online→offline"


def _affected_agent_payload(registry: Any, agent_id: str | None) -> list[dict[str, Any]]:
    if not agent_id or registry is None:
        return []
    row = None
    getter = getattr(registry, "get_row", None)
    if callable(getter):
        try:
            row = getter(agent_id)
        except Exception:  # noqa: BLE001 — ledger must survive a bad row
            row = None
    if row is None:
        return [{"agent_id": agent_id, "name": None}]
    name = getattr(row, "name", None)
    return [{"agent_id": agent_id, "name": str(name) if name else None}]


def _all_agent_rows(registry: Any) -> list[Any]:
    """All enabled agent rows (registry.list_rows when available)."""
    getter = getattr(registry, "list_rows", None)
    if not callable(getter):
        return []
    try:
        return getter() or []
    except Exception:  # noqa: BLE001 — ledger must survive a bad row
        return []


def _agents_affected_by_prefix(
    registry: Any, prefix: str, backend_names: set[str]
) -> list[dict[str, Any]]:
    """Affected agents for a user-scope container: union of

    - agents referencing a docker backend row with this ``sandbox_prefix``
      (named or composite refs — via ``find_agents_using_storage_backend``);
    - agents with an inline docker backend carrying this prefix (the default
      backend is not a named ref, so the reference lookup alone misses them).
    """
    if registry is None:
        return []
    get_config = getattr(registry, "get_config", None)
    finder = getattr(registry, "find_agents_using_storage_backend", None)
    rows = _all_agent_rows(registry)

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        agent_id = str(getattr(row, "agent_id", "") or "")
        if not agent_id:
            continue
        hit = False
        if callable(finder):
            for backend_name in backend_names:
                try:
                    refs = finder(backend_name) or []
                except Exception:  # noqa: BLE001
                    refs = []
                if any(str(r.get("agent_id") or "") == agent_id for r in refs):
                    hit = True
                    break
        if not hit and callable(get_config):
            cfg = get_config(agent_id)
            spec = cfg.get("backend") if isinstance(cfg, dict) else None
            if (
                isinstance(spec, dict)
                and str(spec.get("type") or "") == "docker"
                and str(spec.get("sandbox_prefix") or "agentbuddy_sandbox") == prefix
            ):
                hit = True
        if hit and agent_id not in seen:
            seen.add(agent_id)
            name = getattr(row, "name", None)
            out.append({"agent_id": agent_id, "name": str(name) if name else None})
    return out


class SandboxAdminService:
    """Ledger / drift / recreate over the local Docker daemon."""

    def __init__(
        self,
        *,
        services: Any,
        app_runtime: Any,
        client: Any | None = None,
        backup_root: Path | None = None,
    ) -> None:
        self._services = services
        self._runtime = app_runtime
        self._client = client
        self._backup_dir_override = backup_root

    # -- docker client -------------------------------------------------------

    def _ensure_client(self) -> Any:
        if self._client is None:
            self._client = _load_docker_client()
        return self._client

    # -- expected values -----------------------------------------------------

    def _resolved_spec_for_agent(self, agent_id: str) -> Any:
        """Final harness spec via the same path the agent runtime uses."""
        registry = self._runtime.agent_registry if self._runtime else None
        if registry is None:
            return None
        method = getattr(registry, "_backend_spec_for_row", None)
        row = getattr(registry, "get_row", lambda _aid: None)(agent_id)
        if row is None or not callable(method):
            return None
        try:
            return method(row)
        except Exception:  # noqa: BLE001 — unknown expected → no drift claim
            return None

    def _expected_for_agent_scope(self, agent_id: str | None) -> tuple[str | None, bool | None]:
        if not agent_id:
            return None, None
        return _expected_from_spec(self._resolved_spec_for_agent(agent_id))

    def _docker_backend_rows(self) -> list[Any]:
        repo = getattr(self._services, "storage_backend_repo", None)
        if repo is None:
            return []
        try:
            rows = repo.list_all()
        except Exception:  # noqa: BLE001
            return []
        return [r for r in rows if str(getattr(r, "kind", "") or "").lower() == "docker"]

    def _docker_backend_rows_for_prefix(self, prefix: str) -> list[Any]:
        """Docker backend rows whose ``sandbox_prefix`` matches *prefix*."""
        out: list[Any] = []
        for row in self._docker_backend_rows():
            cfg: dict[str, Any] = {}
            try:
                cfg = json.loads(row.config_json) if row.config_json else {}
            except Exception:  # noqa: BLE001
                cfg = {}
            if not isinstance(cfg, dict):
                cfg = {}
            if str(cfg.get("sandbox_prefix") or "agentbuddy_sandbox") == prefix:
                out.append(row)
        return out

    def _expected_for_user_scope(self, prefix: str) -> tuple[str | None, bool | None, list[str]]:
        """Expected values from any agent affected by this prefix (Q3 union lookup)."""
        registry = self._runtime.agent_registry if self._runtime else None
        matching = self._docker_backend_rows_for_prefix(prefix)
        backend_names = {str(row.name) for row in matching}
        affected = _agents_affected_by_prefix(registry, prefix, backend_names)

        images: set[str] = set()
        allow_values: set[bool] = set()
        for item in affected:
            image, allow = self._expected_for_agent_scope(str(item["agent_id"]))
            if image:
                images.add(image)
            if allow is not None:
                allow_values.add(allow)
        image = next(iter(images)) if len(images) == 1 else None
        allow = next(iter(allow_values)) if len(allow_values) == 1 else None
        return image, allow, sorted(backend_names)

    def _known_sandbox_prefixes(self) -> list[str]:
        """All ``sandbox_prefix`` values declared in docker backend rows + agent configs."""
        prefixes: set[str] = set()
        for row in self._docker_backend_rows():
            cfg: dict[str, Any] = {}
            try:
                cfg = json.loads(row.config_json) if row.config_json else {}
            except Exception:  # noqa: BLE001
                cfg = {}
            if isinstance(cfg, dict):
                prefixes.add(str(cfg.get("sandbox_prefix") or "agentbuddy_sandbox"))
        registry = self._runtime.agent_registry if self._runtime else None
        get_config = getattr(registry, "get_config", None)
        if callable(get_config):
            for row in _all_agent_rows(registry):
                agent_id = str(getattr(row, "agent_id", "") or "")
                if not agent_id:
                    continue
                try:
                    cfg = get_config(agent_id)
                except Exception:  # noqa: BLE001
                    continue
                spec = cfg.get("backend") if isinstance(cfg, dict) else None
                if isinstance(spec, dict) and str(spec.get("type") or "") == "docker":
                    prefixes.add(str(spec.get("sandbox_prefix") or "agentbuddy_sandbox"))
        return sorted(prefixes)

    def _user_scope_prefix(self, container_name: str) -> str:
        """Reverse ``{prefix}_{username}`` for a user-scope container name.

        Matches the longest known prefix that the name starts with; falls back
        to the text before the last underscore (usernames without underscores).
        """
        for prefix in sorted(self._known_sandbox_prefixes(), key=len, reverse=True):
            if container_name.startswith(f"{prefix}_"):
                return prefix
        return container_name.rsplit("_", 1)[0] if "_" in container_name else container_name

    # -- ledger --------------------------------------------------------------

    def list_sandboxes(self) -> list[SandboxEntry]:
        client = self._ensure_client()
        try:
            containers = client.containers.list(all=True, filters={"label": f"{LABEL_SANDBOX}=1"})
        except Exception as exc:
            raise OctopError(
                ErrorCode.SANDBOX_DOCKER_UNAVAILABLE,
                f"docker daemon unreachable: {exc}",
            ) from exc
        entries: list[SandboxEntry] = []
        for c in containers:
            attrs = getattr(c, "attrs", {}) or {}
            labels = _container_labels(c)
            scope = str(labels.get(LABEL_SCOPE) or "agent")
            agent_id = labels.get(LABEL_AGENT_ID) or None
            name = str(getattr(c, "name", "") or "")
            if scope == "agent":
                expected_image, expected_allow = self._expected_for_agent_scope(agent_id)
                affected = _affected_agent_payload(
                    self._runtime.agent_registry if self._runtime else None, agent_id
                )
            else:
                prefix_match = self._user_scope_prefix(name)
                expected_image, expected_allow, _backends = self._expected_for_user_scope(
                    prefix_match
                )
                backend_names = {
                    str(r.name) for r in self._docker_backend_rows_for_prefix(prefix_match)
                }
                affected = _agents_affected_by_prefix(
                    self._runtime.agent_registry if self._runtime else None,
                    prefix_match,
                    backend_names,
                )
            image = str((attrs.get("Config") or {}).get("Image") or "")
            offline = _network_offline(c)
            drift = (expected_image != image) if expected_image is not None and image else None
            network_drift = (
                (offline != (not expected_allow))
                if offline is not None and expected_allow is not None
                else None
            )
            entries.append(
                SandboxEntry(
                    container_name=name,
                    container_id=str(getattr(c, "id", "") or "")[:12],
                    scope=scope,
                    agent_id=agent_id,
                    status=str((attrs.get("State") or {}).get("Status") or ""),
                    created_at=str((attrs.get("Created") or "") or ""),
                    image=image,
                    network_offline=offline,
                    expected_image=expected_image,
                    expected_allow_network=expected_allow,
                    drift=drift,
                    network_drift=network_drift,
                    affected_agents=affected,
                )
            )
        entries.sort(key=lambda e: e.container_name)
        return entries

    def _get_sandbox_container(self, client: Any, name: str) -> Any:
        try:
            container = client.containers.get(name)
        except Exception as exc:
            raise OctopError(
                ErrorCode.SANDBOX_CONTAINER_NOT_FOUND,
                f"sandbox container {name!r} not found",
            ) from exc
        labels = _container_labels(container)
        if labels.get(LABEL_SANDBOX) != "1":
            raise OctopError(
                ErrorCode.SANDBOX_LABEL_MISMATCH,
                f"container {name!r} is not a harness sandbox",
            )
        return container

    # -- backup --------------------------------------------------------------

    def _backup_root(self) -> Path:
        if self._backup_dir_override is not None:
            return self._backup_dir_override
        from octop.infra.utils.paths import PathLayout

        return PathLayout.from_env().root / "sandbox-backups"

    def _workspace_root_of(self, container: Any, agent_id: str | None) -> str:
        """In-container workspace root, mirroring harness rules."""
        attrs = getattr(container, "attrs", {}) or {}
        workdir = str((attrs.get("Config") or {}).get("WorkingDir") or "").strip()
        if workdir and workdir != "/":
            return workdir
        if agent_id:
            return f"/workspace/{agent_id}"
        return "/workspace"

    def backup_workspace(self, client: Any, container: Any, *, agent_id: str | None) -> Path:
        """Export the container workspace via ``get_archive`` to the host."""
        name = str(getattr(container, "name", "") or "sandbox")
        root = self._backup_root()
        stamp = time.strftime("%Y%m%d-%H%M%S")
        target = root / Path(name).name / stamp
        try:
            target.mkdir(parents=True, exist_ok=True)
            ws_root = self._workspace_root_of(container, agent_id)
            stream, _stat = container.get_archive(ws_root)
            tar_path = target / "workspace.tar"
            with tar_path.open("wb") as fh:
                for chunk in stream:
                    fh.write(chunk)
            with tarfile.open(tar_path) as tf:
                tf.extractall(target / "workspace")  # noqa: S202 — trusted local archive
            tar_path.unlink(missing_ok=True)
            meta = {
                "container_name": name,
                "scope": str(_container_labels(container).get(LABEL_SCOPE) or ""),
                "agent_id": agent_id,
                "image": str(
                    (getattr(container, "attrs", {}) or {}).get("Config", {}).get("Image") or ""
                ),
                "workspace_root": ws_root,
                "created_at": stamp,
            }
            (target / "meta.json").write_text(
                json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OctopError:
            raise
        except Exception as exc:
            raise OctopError(
                ErrorCode.SANDBOX_BACKUP_FAILED,
                f"failed to back up workspace of {name!r}: {exc}",
            ) from exc
        self._prune_backups(root / Path(name).name)
        return target

    def _prune_backups(self, container_dir: Path) -> None:
        try:
            stamps = sorted(
                (p for p in container_dir.iterdir() if p.is_dir()),
                key=lambda p: p.name,
                reverse=True,
            )
        except OSError:
            return
        for stale in stamps[_BACKUP_KEEP:]:
            import shutil  # noqa: PLC0415

            shutil.rmtree(stale, ignore_errors=True)

    def list_backups(self, container_name: str) -> list[dict[str, Any]]:
        container_dir = self._backup_root() / Path(container_name).name
        if not container_dir.is_dir():
            return []
        out: list[dict[str, Any]] = []
        for stamp_dir in sorted(
            (p for p in container_dir.iterdir() if p.is_dir()),
            key=lambda p: p.name,
            reverse=True,
        ):
            meta: dict[str, Any] = {}
            meta_file = stamp_dir / "meta.json"
            if meta_file.is_file():
                try:
                    meta = json.loads(meta_file.read_text(encoding="utf-8"))
                except Exception:  # noqa: BLE001
                    meta = {}
            out.append({"stamp": stamp_dir.name, "path": str(stamp_dir), "meta": meta})
        return out

    # -- recreate ------------------------------------------------------------

    def _assert_not_in_use(self, agent_ids: list[str]) -> None:
        registry = self._runtime.agent_registry if self._runtime else None
        checker = getattr(registry, "is_agent_active", None)
        if not callable(checker):
            return
        for agent_id in agent_ids:
            if checker(agent_id):
                raise OctopError(
                    ErrorCode.SANDBOX_IN_USE,
                    f"agent {agent_id} has an active conversation",
                    details={"agent_id": agent_id},
                )

    def recreate(self, container_name: str, *, actor: str | None = None) -> dict[str, Any]:
        client = self._ensure_client()
        container = self._get_sandbox_container(client, container_name)
        labels = _container_labels(container)
        scope = str(labels.get(LABEL_SCOPE) or "agent")
        agent_id = labels.get(LABEL_AGENT_ID) or None

        if scope == "agent":
            agent_ids = [agent_id] if agent_id else []
        else:
            prefix = self._user_scope_prefix(container_name)
            backend_names = {str(r.name) for r in self._docker_backend_rows_for_prefix(prefix)}
            affected = _agents_affected_by_prefix(
                self._runtime.agent_registry if self._runtime else None,
                prefix,
                backend_names,
            )
            agent_ids = [str(item["agent_id"]) for item in affected]
        self._assert_not_in_use(sorted(set(agent_ids)))

        old_image = str(
            (getattr(container, "attrs", {}) or {}).get("Config", {}).get("Image") or ""
        )
        offline = _network_offline(container)

        if scope == "agent":
            expected_image, expected_allow = self._expected_for_agent_scope(agent_id)
        else:
            expected_image, expected_allow, _backends = self._expected_for_user_scope(prefix)

        backup_path = self.backup_workspace(client, container, agent_id=agent_id)

        # Verify the expected image exists (or pull) BEFORE removing anything.
        if expected_image:
            try:
                from octop_harness.backends.docker_sandbox import (  # noqa: PLC0415
                    ensure_docker_image,
                )

                ensure_docker_image(expected_image, client=client)
            except Exception as exc:
                raise OctopError(
                    ErrorCode.SANDBOX_IMAGE_MISSING,
                    f"expected sandbox image {expected_image!r} missing and pull failed; "
                    "old container kept",
                    details={"reason": str(exc)},
                ) from exc

        try:
            container.remove(force=True)
        except Exception as exc:
            raise OctopError(
                ErrorCode.SANDBOX_BACKUP_FAILED,
                f"failed to remove container {container_name!r}: {exc}",
            ) from exc
        logger.info(
            "sandbox recreated container=%s scope=%s old_image=%s expected_image=%s "
            "old_network_offline=%s expected_allow_network=%s backup=%s actor=%s",
            container_name,
            scope,
            old_image,
            expected_image,
            offline,
            expected_allow,
            backup_path,
            actor,
        )
        return {
            "recreated": True,
            "container_name": container_name,
            "backup_path": str(backup_path),
            "old_image": old_image,
            "expected_image": expected_image,
            "old_network_offline": offline,
            "expected_allow_network": expected_allow,
        }

    # -- image inventory -----------------------------------------------------

    def list_images(self) -> list[dict[str, Any]]:
        client = self._ensure_client()
        try:
            images = client.images.list()
        except Exception as exc:
            raise OctopError(
                ErrorCode.SANDBOX_DOCKER_UNAVAILABLE,
                f"docker daemon unreachable: {exc}",
            ) from exc
        expected: set[str] = set()
        for entry in self.list_sandboxes():
            if entry.image:
                expected.add(entry.image)
            if entry.expected_image:
                expected.add(entry.expected_image)
        out: list[dict[str, Any]] = []
        for img in images:
            attrs = (
                img.get("attrs", {}) if isinstance(img, dict) else getattr(img, "attrs", {}) or {}
            )
            image_id = img.get("id", "") if isinstance(img, dict) else getattr(img, "id", "") or ""
            for tag in attrs.get("RepoTags") or [None]:
                out.append(
                    {
                        "tag": tag,
                        "id": str(image_id)[:12],
                        "size": int(attrs.get("Size") or 0),
                        "created": attrs.get("Created"),
                        "referenced": tag in expected if tag else False,
                    }
                )
        out.sort(key=lambda i: (not i["referenced"], str(i["tag"])))
        return out
