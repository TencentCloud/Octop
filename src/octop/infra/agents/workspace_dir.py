"""Agent ``workspace_dir`` (persisted in ``config_json``).

``workspace_dir`` and ``backend.root_dir`` are different dimensions:

* ``root_dir`` — local backend rootfs (agent-visible ``/``).
* ``workspace_dir`` — the agent's working directory. After create, the DB value
  is authoritative and is what harness receives **verbatim** (never
  ``root_dir``-joined).

Create-time defaults when unset:

* Host-rooted backend → on-disk ``{OCTOP_HOME}/agents/<id>/``, persist that
  host absolute path.
* Scoped ``root_dir`` → on-disk ``{root_dir}/.octop/workspaces/<id>/`` (so files
  land inside the jail), but persist ``/.octop/workspaces/<id>`` — the
  agent-facing workspace path. Harness gets that persisted string as-is.

User-assigned ``workspace_dir`` always wins (strip only).

:func:`resolve_workspace_host_path` is only for Octop host FS ops (delete,
memory sqlite path, etc.) when the persisted value is the agent-facing
``/.octop/workspaces/…`` form.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from octop.infra.utils.paths import PathLayout

DEFAULT_SYSTEM_FILES_PATH = ".octop"
SCOPED_WORKSPACE_DIRNAME = "workspaces"

_WINDOWS_HOST_PATH_RE = re.compile(r"^(?:[A-Za-z]:[/\\]|\\\\|//)")


def _running_on_windows() -> bool:
    return os.name == "nt"


def _is_host_root_sentinel(root: str | Path | None) -> bool:
    if root is None:
        return True
    return str(root).strip() in ("/", "\\", "")


def _is_windows_style_host_path(raw: str) -> bool:
    return bool(_WINDOWS_HOST_PATH_RE.match(raw.strip()))


def local_backend_root_dir(cfg: dict[str, Any] | None) -> str | None:
    """Return ``root_dir`` from a local ``filesystem`` / ``local_shell`` backend spec."""
    backend = (cfg or {}).get("backend")
    if not isinstance(backend, dict):
        return None
    kind = str(backend.get("type") or "").lower()
    if kind in {"local_shell", "filesystem"}:
        raw = backend.get("root_dir")
        return str(raw).strip() if raw is not None and str(raw).strip() else None
    if kind == "composite":
        default = backend.get("default")
        if isinstance(default, dict):
            nested = str(default.get("type") or "").lower()
            if nested in {"local_shell", "filesystem"}:
                raw = default.get("root_dir")
                return str(raw).strip() if raw is not None and str(raw).strip() else None
    return None


def uses_scoped_workspace_default(cfg: dict[str, Any] | None) -> bool:
    root_raw = local_backend_root_dir(cfg)
    return root_raw is not None and not _is_host_root_sentinel(root_raw)


def scoped_workspace_dir_str(agent_id: str) -> str:
    """Agent-facing / harness workspace path for scoped-root create defaults."""
    return f"/{DEFAULT_SYSTEM_FILES_PATH}/{SCOPED_WORKSPACE_DIRNAME}/{agent_id}"


def default_agent_workspace_dir(
    paths: PathLayout,
    agent_id: str,
    *,
    cfg: dict[str, Any] | None = None,
) -> Path:
    """Create-time on-disk workspace (mkdir -p). Not what harness receives."""
    root_raw = local_backend_root_dir(cfg)
    if root_raw is not None and not _is_host_root_sentinel(root_raw):
        try:
            root = Path(root_raw).expanduser().resolve()
        except OSError:
            return paths.ensure_agent_workspace(agent_id)
        out = root / DEFAULT_SYSTEM_FILES_PATH / SCOPED_WORKSPACE_DIRNAME / agent_id
        out.mkdir(parents=True, exist_ok=True)
        return out
    return paths.ensure_agent_workspace(agent_id)


def seed_workspace_dir_on_create(
    config: dict[str, Any],
    *,
    paths: PathLayout,
    agent_id: str,
) -> Path:
    """Ensure ``config["workspace_dir"]`` at create; return on-disk Path for seeding."""
    raw = config.get("workspace_dir")
    if isinstance(raw, str) and raw.strip():
        text = raw.strip()
        host = resolve_workspace_host_path(text, config)
        host.mkdir(parents=True, exist_ok=True)
        config["workspace_dir"] = text
        return host.resolve()

    host = default_agent_workspace_dir(paths, agent_id, cfg=config).resolve()
    if uses_scoped_workspace_default(config):
        config["workspace_dir"] = scoped_workspace_dir_str(agent_id)
    else:
        config["workspace_dir"] = str(host)
    return host


def _relative_under(child: Path, root: Path) -> Path:
    if not _running_on_windows():
        return child.resolve().relative_to(root.resolve())
    child_s = str(child.resolve())
    root_s = str(root.resolve())
    if child_s.casefold() == root_s.casefold():
        return Path(".")
    prefix = root_s if root_s.endswith(("\\", "/")) else root_s + os.sep
    if not child_s.casefold().startswith(prefix.casefold()):
        raise ValueError(f"{child_s!r} is not under {root_s!r}")
    return Path(child_s[len(prefix) :].replace("\\", "/"))


def _path_under(child: Path, root: Path) -> bool:
    try:
        _relative_under(child, root)
        return True
    except (ValueError, OSError):
        return False


def resolve_workspace_host_path(raw: str, cfg: dict[str, Any] | None = None) -> Path:
    """Map persisted ``workspace_dir`` to an on-disk path for Octop host FS ops.

    Harness receives the persisted string as-is (no join here). When the DB
    holds agent-facing ``/.octop/workspaces/…`` and the backend has a scoped
    ``root_dir``, the on-disk tree is ``{root_dir}/.octop/workspaces/…``.
    """
    text = raw.strip()
    if not text:
        raise ValueError("workspace_dir is empty")
    if _is_windows_style_host_path(text):
        return Path(text).expanduser().resolve()

    root_raw = local_backend_root_dir(cfg)
    if root_raw is None or _is_host_root_sentinel(root_raw):
        return Path(text).expanduser().resolve()

    root = Path(root_raw).expanduser().resolve()
    normalized = text.replace("\\", "/").strip()
    candidate = Path(text).expanduser()

    if normalized == "/" or normalized.startswith("/.octop/"):
        rel = normalized.lstrip("/")
        return (root / rel).resolve() if rel else root

    try:
        host_resolved = candidate.resolve()
    except OSError:
        host_resolved = candidate

    if _path_under(host_resolved, root):
        return host_resolved

    if candidate.is_absolute():
        return (
            host_resolved if host_resolved.exists() or not _running_on_windows() else host_resolved
        )

    return (root / text).resolve()


def harness_workspace_path(raw: str, cfg: dict[str, Any] | None = None) -> Path:
    """Path handed to harness as ``workspace_dir``.

    The persisted value goes through as-is whenever the platform can express it
    as an absolute path. Windows cannot: the agent-facing
    ``/.octop/workspaces/<id>`` form has no drive letter, and harness rejects a
    non-absolute workspace — fall back to the on-disk host mapping there.
    """
    text = raw.strip()
    if not text:
        raise ValueError("workspace_dir is empty")
    candidate = Path(text)
    if candidate.is_absolute():
        return candidate
    return resolve_workspace_host_path(text, cfg)


def _backend_virtual_mode(cfg: dict[str, Any] | None) -> bool:
    backend = (cfg or {}).get("backend")
    if not isinstance(backend, dict):
        return False
    kind = str(backend.get("type") or "").lower()
    target = backend
    if kind == "composite":
        default = backend.get("default")
        if not isinstance(default, dict):
            return False
        target = default
        kind = str(target.get("type") or "").lower()
    if kind not in {"local_shell", "filesystem"}:
        return False
    return bool(target.get("virtual_mode", True))


def agent_facing_workspace_root(
    workspace_dir: Path | str,
    *,
    root_dir: Path | str | None = None,
    virtual_mode: bool = False,
) -> str:
    """Agent-visible workspace directory (never ``root_dir``-joined).

    Scoped virtual backends map the on-disk workspace back to a rootfs path
    such as ``/.octop/workspaces/<id>``. Host-rooted layouts keep the workspace
    path string as-is.
    """
    text = str(workspace_dir).strip().replace("\\", "/")
    if not text:
        return ""
    if text == "/" or text.startswith("/.octop/"):
        return text if text != "/" else "/"
    if not virtual_mode or root_dir is None or _is_host_root_sentinel(root_dir):
        return text
    try:
        ws = Path(text).expanduser().resolve()
        root = Path(str(root_dir)).expanduser().resolve()
        rel = _relative_under(ws, root).as_posix()
    except (OSError, ValueError):
        return text
    if not rel or rel == ".":
        return "/"
    return f"/{rel}"


def agent_facing_workspace_dir_from_config(cfg: dict[str, Any] | None) -> str:
    """Persisted / agent-visible ``workspace_dir`` for path hints and artifacts."""
    raw = (cfg or {}).get("workspace_dir")
    if not isinstance(raw, str) or not raw.strip():
        return ""
    text = raw.strip().replace("\\", "/")
    if text == "/" or text.startswith("/.octop/"):
        return text
    return agent_facing_workspace_root(
        text,
        root_dir=local_backend_root_dir(cfg),
        virtual_mode=_backend_virtual_mode(cfg),
    )


def join_agent_facing(root: str, *parts: str) -> str:
    """Join workspace-relative segments under an agent-facing root."""
    base = (root or "").replace("\\", "/").rstrip("/") or ""
    segs: list[str] = []
    for part in parts:
        piece = str(part or "").replace("\\", "/").strip("/")
        if piece and piece != ".":
            segs.append(piece)
    if not segs:
        return base or "/"
    tail = "/".join(segs)
    if not base or base == "/":
        return f"/{tail}"
    return f"{base}/{tail}"


def workspace_dir_from_config(
    cfg: dict[str, Any] | None,
    *,
    paths: PathLayout,
    agent_id: str,
) -> Path:
    """On-disk workspace for Octop host ops (may map ``/.octop/…`` under root_dir)."""
    raw = (cfg or {}).get("workspace_dir")
    if isinstance(raw, str) and raw.strip():
        out = resolve_workspace_host_path(raw, cfg)
        out.mkdir(parents=True, exist_ok=True)
        return out
    return default_agent_workspace_dir(paths, agent_id, cfg=cfg)


def system_files_path_from_config(cfg: dict[str, Any] | None) -> str:
    raw = (cfg or {}).get("system_files_path")
    if not isinstance(raw, str):
        return ""
    text = raw.strip().replace("\\", "/").strip("/")
    if not text or text == ".":
        return ""
    if ".." in text.split("/"):
        return ""
    return text


def host_system_dir(workspace_dir: Path, cfg: dict[str, Any] | None) -> Path:
    prefix = system_files_path_from_config(cfg)
    return workspace_dir / prefix if prefix else workspace_dir


def agent_auth_dir(workspace_dir: Path, cfg: dict[str, Any] | None) -> Path:
    prefix = system_files_path_from_config(cfg)
    legacy = workspace_dir / ".octop-auth"
    if not prefix:
        return legacy
    canonical = workspace_dir / prefix / "auth"
    try:
        legacy_has_files = legacy.is_dir() and any(legacy.iterdir())
        canonical_empty = not canonical.exists() or not any(canonical.iterdir())
    except OSError:
        legacy_has_files = False
        canonical_empty = True
    if legacy_has_files and canonical_empty:
        return legacy
    return canonical


def skills_discovery_roots(workspace_dir: Path) -> list[Path]:
    return [workspace_dir / DEFAULT_SYSTEM_FILES_PATH / "skills", workspace_dir / "skills"]


def workspace_dir_from_config_json(
    config_json: str | None,
    *,
    paths: PathLayout,
    agent_id: str,
) -> Path:
    try:
        parsed = json.loads(config_json or "{}")
    except (json.JSONDecodeError, TypeError):
        parsed = {}
    cfg = parsed if isinstance(parsed, dict) else {}
    return workspace_dir_from_config(cfg, paths=paths, agent_id=agent_id)


__all__ = [
    "DEFAULT_SYSTEM_FILES_PATH",
    "SCOPED_WORKSPACE_DIRNAME",
    "agent_auth_dir",
    "agent_facing_workspace_dir_from_config",
    "agent_facing_workspace_root",
    "default_agent_workspace_dir",
    "harness_workspace_path",
    "host_system_dir",
    "join_agent_facing",
    "local_backend_root_dir",
    "resolve_workspace_host_path",
    "scoped_workspace_dir_str",
    "seed_workspace_dir_on_create",
    "skills_discovery_roots",
    "system_files_path_from_config",
    "uses_scoped_workspace_default",
    "workspace_dir_from_config",
    "workspace_dir_from_config_json",
]
