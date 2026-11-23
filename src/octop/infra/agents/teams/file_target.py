"""Point one team-member turn at the host workspace.

File tools keep their names. While the turn is active, reads and writes use
the host or bridge directory. Directories the member passes to deepagents
stay on the member backend and are read-only. The member's own file tools
are left in place only when the user explicitly asks for them.
"""

from __future__ import annotations

import inspect
import logging
import threading
from contextvars import ContextVar
from typing import Any

from octop.i18n import tr

logger = logging.getLogger(__name__)

HOST_KEY = "octop_team_file_host"
DIR_KEY = "octop_team_file_dir"
EXECUTE_KEY = "octop_team_file_execute"
# Directories the member already passes to deepagents (skills, subagents, and
# any later roots resolved the same way). Read-only for this turn.
MOUNTS_KEY = "octop_team_member_mounts"
MEMBER_KEY = "octop_team_file_member"
# What this turn may do on the bound workspace. ``file`` is always on when a
# file target is stamped. ``execute`` follows the workspace shell. Later device
# tools (contacts, location) are extra bool keys on the same dict.
CAPABILITIES_KEY = "octop_turn_capabilities"
BRIDGE_TARGET_KEY = "octop_bridge_file_target"
SERVER_NAME = "octop-team-workspace"

_RESERVED_CAPABILITIES = frozenset({"file", "execute"})

_FILE_METHODS = (
    "read",
    "aread",
    "write",
    "awrite",
    "edit",
    "aedit",
    "ls",
    "als",
    "glob",
    "aglob",
    "grep",
    "agrep",
    "delete",
    "adelete",
)

# Negations that mention the member workspace still want the host workspace.
_KEEP_HOST = (
    "不要用你自己的",
    "不要使用你自己的",
    "不要用自己的",
    "不要使用自己的",
    "do not use your own",
    "don't use your own",
)

# The user, not the host's rewritten task, has to ask for the member workspace.
_OPT_OUT = (
    "用你自己的工作区",
    "使用你自己的工作区",
    "用自己的工作区",
    "使用自己的工作区",
    "用你自己的文件工具",
    "使用你自己的文件工具",
    "不要用主持人的工作区",
    "不要使用主持人的工作区",
    "use your own workspace",
    "use your own file tools",
    "do not use the host workspace",
    "don't use the host workspace",
)

_TARGET: ContextVar[Any | None] = ContextVar("octop_team_file_backend", default=None)
_ORIGINALS: dict[int, dict[str, Any]] = {}
_LOCK = threading.Lock()


def turn_capabilities(
    *,
    execute: bool,
    extra: dict[str, Any] | None = None,
) -> dict[str, bool]:
    """Capability table for one file-target turn.

    ``file`` stays on. ``execute`` is the shell flag. ``extra`` may add other
    bools, but it cannot flip ``file`` or ``execute`` — those two come from
    the workspace.
    """
    caps: dict[str, bool] = {"file": True, "execute": bool(execute)}
    if not isinstance(extra, dict):
        return caps
    for key, value in extra.items():
        if not isinstance(key, str) or key in _RESERVED_CAPABILITIES:
            continue
        name = key.strip()
        if not name:
            continue
        caps[name] = bool(value)
    return caps


def stamp_turn_capabilities(
    cfg: dict[str, Any],
    *,
    execute: bool,
    extra: dict[str, Any] | None = None,
) -> dict[str, bool]:
    """Write the capability table and keep the legacy execute string in step."""
    caps = turn_capabilities(execute=execute, extra=extra)
    cfg[CAPABILITIES_KEY] = caps
    cfg[EXECUTE_KEY] = "1" if caps["execute"] else "0"
    return caps


def capability_enabled(cfg: dict[str, Any] | None, name: str) -> bool:
    """Whether *name* is on for this turn.

    A stamped table wins. Turns that only carry the legacy execute string still
    answer ``execute`` from that string, and ``file`` from a bound workspace.
    """
    if not isinstance(cfg, dict):
        return False
    raw = cfg.get(CAPABILITIES_KEY)
    if isinstance(raw, dict) and name in raw:
        return bool(raw[name])
    if name == "execute":
        return str(cfg.get(EXECUTE_KEY) or "") == "1"
    if name == "file":
        return bool(cfg.get(HOST_KEY) or cfg.get(BRIDGE_TARGET_KEY) or cfg.get(DIR_KEY))
    return False


def file_target_opt_out(*texts: str) -> bool:
    """True when the user explicitly wants the member's own file tools."""
    for text in texts:
        folded = text.lower()
        if any(phrase in folded for phrase in _KEEP_HOST):
            continue
        if any(phrase in folded for phrase in _OPT_OUT):
            return True
    return False


def workspace_directory(agent: Any) -> str:
    """Directory string the host's own file tools already treat as default."""
    visible = getattr(agent, "_agent_visible_workspace_dir", None)
    if callable(visible):
        try:
            text = visible().as_posix()
        except Exception:
            logger.debug("team file target workspace dir failed", exc_info=True)
            text = ""
        if isinstance(text, str) and text.strip():
            return text.strip()
    config = getattr(agent, "config", None)
    raw = getattr(config, "workspace_dir", None)
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return ""


def host_can_execute(backend: Any) -> bool:
    if backend is None:
        return False
    from deepagents.middleware.filesystem import supports_execution

    try:
        return bool(supports_execution(backend))
    except Exception:
        logger.debug("team file target execute check failed", exc_info=True)
        return False


def file_target_briefing(
    locale: str,
    directory: str,
    *,
    execute: bool,
    managed: bool,
    local: bool = False,
    deliver: bool = False,
    mounts: list[str] | None = None,
) -> str:
    if local:
        key = "bridge.local_file_target_managed" if managed else "bridge.local_file_target"
    else:
        key = "teams.member_file_target_managed" if managed else "teams.member_file_target"
    body = tr(key, locale, directory=directory)
    if managed and deliver:
        body = f"{body}\n{tr('teams.member_file_target_send', locale)}"
    listed = [item for item in (mounts or []) if item]
    if listed:
        body = f"{body}\n{tr('teams.member_file_mounts', locale, paths=chr(10).join(listed))}"
    extra_key = (
        "teams.member_file_target_execute" if execute else "teams.member_file_target_no_execute"
    )
    return f"{body}\n{tr(extra_key, locale)}"


def deepagents_directories(agent: Any) -> list[str]:
    """Directories this agent passes to deepagents, as that runtime sees them.

    Skills come from ``BackendWorkspace.skill_paths``. Subagent roots use the
    same source-path conversion. An empty list means the turn keeps the root
    workspace only.
    """
    workspace = getattr(agent, "workspace", None)
    skill_paths = getattr(workspace, "skill_paths", None)
    if workspace is None or not callable(skill_paths):
        return []
    config = getattr(agent, "config", None)
    try:
        found = [str(path) for path in skill_paths(extra=getattr(config, "skills_dir", None))]
    except Exception:
        logger.debug("team file mounts skipped; skill paths failed", exc_info=True)
        return []
    source = getattr(workspace, "_deepagents_source_path", None)
    if callable(source):
        try:
            from octop_harness.subagents.loader import agent_scan_roots

            for root in agent_scan_roots(workspace, extra=getattr(config, "subagents_path", None)):
                found.append(str(source(root)))
        except Exception:
            logger.debug("team file mounts skipped subagent roots", exc_info=True)
    return _unique_mounts(found)


def stamp_member_mounts(cfg: dict[str, Any], agent: Any, member_agent_id: str) -> list[str]:
    """Record the member's deepagents directories. Empty when they cannot be read."""
    try:
        mounts = deepagents_directories(agent)
    except Exception:
        logger.debug("team file mounts skipped for %s", member_agent_id, exc_info=True)
        return []
    if not mounts:
        return []
    cfg[MOUNTS_KEY] = mounts
    if member_agent_id.strip():
        cfg[MEMBER_KEY] = member_agent_id.strip()
    return mounts


_MUTATING_FILE_TOOLS = frozenset({"write_file", "edit_file", "delete"})
_MOUNT_ARG_KEYS = {
    "glob": ("path", "pattern"),
    "grep": ("path",),
    "ls": ("path",),
    "execute": (),
}


def mount_for_path(path: str, mounts: list[str] | tuple[str, ...]) -> str | None:
    """Longest mounted directory that contains *path*, or ``None``."""
    text = _posix(path)
    if text.startswith("./"):
        text = text[2:]
    if not text or text in {".", "/"}:
        return None
    best: str | None = None
    for mount in mounts:
        base = _posix(str(mount)).rstrip("/")
        if path_under_root(text, base) is None:
            continue
        if best is None or len(base) > len(best):
            best = base
    return best


def mount_for_args(
    name: str,
    args: dict[str, Any],
    mounts: list[str] | tuple[str, ...],
) -> str | None:
    """Mounted directory touched by this tool call, before host-path rewriting."""
    if not mounts or name == "execute":
        return None
    best: str | None = None
    for key in _MOUNT_ARG_KEYS.get(name, ("file_path", "path")):
        value = args.get(key)
        if not isinstance(value, str) or not value.strip():
            continue
        hit = mount_for_path(value, mounts)
        if hit is not None and (best is None or len(hit) > len(best)):
            best = hit
    return best


def mounted_mutation(name: str, args: dict[str, Any], mounts: list[str] | tuple[str, ...]) -> bool:
    """True when a write would land in a read-only deepagents directory."""
    return name in _MUTATING_FILE_TOOLS and mount_for_args(name, args, mounts) is not None


def _unique_mounts(paths: list[str]) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for raw in paths:
        text = _posix(raw).rstrip("/")
        if not text or text in {".", "/"} or text in seen:
            continue
        seen.add(text)
        found.append(text)
    return found


def _posix(path: str) -> str:
    return path.strip().replace("\\", "/")


def path_under_root(path: str, root: str) -> str | None:
    """Workspace-relative fragment when *path* is *root* or a file inside it.

    ``/`` is not a root. A virtual tool root would otherwise match every
    absolute path.
    """
    text = _posix(path)
    base = _posix(root).rstrip("/")
    if not text or not base or base in {".", "/"}:
        return None
    if text.rstrip("/") == base:
        return "."
    prefix = base + "/"
    if text.startswith(prefix):
        return text[len(prefix) :].lstrip("/") or "."
    return None


def workspace_relative(path: str, target_dir: str) -> str:
    """Path the target workspace should resolve.

    A relative path stays relative, so ``BackendWorkspace`` joins it onto the
    target directory. A path already inside that directory becomes the fragment
    under it. Any other absolute path is confined into the target by dropping
    the leading slash, so it is not left as a host path.
    """
    text = _posix(path)
    if not text or text in {".", "./"}:
        return "."
    if text.startswith("./"):
        text = text[2:] or "."
    relative = path_under_root(text, target_dir)
    if relative is not None:
        return relative
    if text.startswith("/"):
        return text.lstrip("/") or "."
    return text


def workspace_file_args(args: dict[str, Any], *, target_dir: str) -> dict[str, Any]:
    """Rewrite ``file_path`` / ``path`` against the target directory."""
    updated = dict(args)
    for key in ("file_path", "path"):
        value = updated.get(key)
        if isinstance(value, str) and value.strip():
            updated[key] = workspace_relative(value, target_dir)
    return updated


def install_file_redirect(backend: Any) -> None:
    """Redirect this backend's file methods while a host target is active.

    The compiled file tools close over this object. Swapping the methods keeps
    their validation and formatting, and only the backend changes.
    """
    if backend is None:
        return
    with _LOCK:
        if getattr(backend, "_octop_team_file_redirect", False):
            return
        saved: dict[str, Any] = {}
        for name in _FILE_METHODS:
            current = getattr(backend, name, None)
            if not callable(current):
                continue
            saved[name] = current
            try:
                setattr(backend, name, _wrap(backend, name, current))
            except (AttributeError, TypeError):
                saved.pop(name, None)
        if not saved:
            return
        try:
            backend._octop_team_file_redirect = True
        except (AttributeError, TypeError):
            return
        _ORIGINALS[id(backend)] = saved


def activate_file_target(backend: Any) -> Any:
    """Return a token. Reset it when the file tool returns."""
    return _TARGET.set(backend)


def reset_file_target(token: Any) -> None:
    _TARGET.reset(token)


def call_backend(backend: Any, name: str, /, *args: Any, **kwargs: Any) -> Any:
    """Call a backend method, skipping a redirect wrapper if one is installed."""
    saved = _ORIGINALS.get(id(backend))
    method = saved.get(name) if saved and name in saved else getattr(backend, name, None)
    if not callable(method):
        msg = f"{type(backend).__name__} has no {name}"
        raise AttributeError(msg)
    return method(*args, **kwargs)


async def acall_backend(backend: Any, name: str, /, *args: Any, **kwargs: Any) -> Any:
    result = call_backend(backend, name, *args, **kwargs)
    if inspect.isawaitable(result):
        return await result
    return result


def _wrap(backend: Any, name: str, original: Any) -> Any:
    if inspect.iscoroutinefunction(original):

        async def async_wrapped(*args: Any, **kwargs: Any) -> Any:
            target = _TARGET.get()
            chosen = original if target is None or target is backend else None
            if chosen is None:
                chosen = _method(target, name, original)
            result = chosen(*args, **kwargs)
            if inspect.isawaitable(result):
                return await result
            return result

        return async_wrapped

    def sync_wrapped(*args: Any, **kwargs: Any) -> Any:
        target = _TARGET.get()
        chosen = (
            original if target is None or target is backend else _method(target, name, original)
        )
        return chosen(*args, **kwargs)

    return sync_wrapped


def _method(backend: Any, name: str, fallback: Any) -> Any:
    saved = _ORIGINALS.get(id(backend))
    if saved and name in saved:
        return saved[name]
    method = getattr(backend, name, None)
    if callable(method):
        return method
    return fallback
