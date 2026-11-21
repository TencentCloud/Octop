"""Keep a stamped file target on the target directory.

The member filesystem guard runs outside Octop middleware and would rewrite a
relative path onto the member workspace before the tool runs. While this turn
names a target directory, that rewrite is skipped. Relative paths stay
relative, and ``BackendWorkspace`` resolves them against the target.

A managed runner cannot drop its own write and shell tools. While a target is
stamped, a permission request for those tools is denied. A call that still
runs is marked as the runner's own workspace, not the selected directory.
"""

from __future__ import annotations

import logging
import shlex
from typing import Any

from langgraph.config import get_config
from langgraph.prebuilt.tool_node import ToolCallRequest

from octop.i18n import tr
from octop.infra.agents.teams.file_target import (
    BRIDGE_TARGET_KEY,
    DIR_KEY,
    HOST_KEY,
    workspace_relative,
)

logger = logging.getLogger(__name__)

_PATH_TOOLS = frozenset({"ls", "read_file", "write_file", "edit_file", "glob", "grep", "delete"})
_WRITE_KINDS = frozenset({"edit", "delete", "move", "execute"})
_WRITE_NAMES = frozenset(
    {
        "write",
        "edit",
        "bash",
        "shell",
        "execute",
        "delete",
        "notebookedit",
        "multiedit",
        "write_file",
        "edit_file",
        "strreplace",
        "apply_patch",
    }
)
_SERVER = "octop-team-workspace"


def install_file_target_guards() -> None:
    """Install both shims. Repeated calls leave the wrappers in place."""
    _install_relative_guard()
    _install_runner_block()


def _stamped_directory() -> str:
    try:
        raw = get_config().get("configurable") or {}
    except RuntimeError:
        return ""
    if not isinstance(raw, dict):
        return ""
    host = raw.get(HOST_KEY)
    bridge = raw.get(BRIDGE_TARGET_KEY)
    active = (isinstance(host, str) and bool(host.strip())) or (
        isinstance(bridge, str) and bool(bridge.strip())
    )
    directory = raw.get(DIR_KEY)
    if not active or not isinstance(directory, str) or not directory.strip():
        return ""
    return directory.strip()


def _locale() -> str:
    try:
        raw = get_config().get("configurable") or {}
    except RuntimeError:
        return "en"
    if isinstance(raw, dict):
        locale = raw.get("locale")
        if isinstance(locale, str) and locale.strip():
            return locale.strip()
    return "en"


def _base(name: str) -> str:
    trimmed = name.strip()
    slash = trimmed.rfind("/")
    return trimmed[slash + 1 :] if slash >= 0 else trimmed


def _store(request: Any, name: str, args: dict[str, Any]) -> Any:
    new_call: dict[str, Any] = {
        "name": name,
        "args": args,
        "id": request.tool_call.get("id"),
    }
    if request.tool_call.get("type") == "tool_call":
        new_call["type"] = "tool_call"
    override = getattr(request, "override", None)
    if callable(override):
        updated = override(tool_call=new_call)
        if isinstance(updated, ToolCallRequest):
            return updated
    request.tool_call = new_call
    return request


def _against_target(request: Any, target: str, original: Any, owner: Any) -> Any:
    """Pop harness-only path hints without joining them onto the member root."""
    name = str(request.tool_call.get("name") or "")
    base = _base(name)
    raw = request.tool_call.get("args") or {}
    if not isinstance(raw, dict):
        return request
    args = dict(raw)
    if base == "execute":
        cwd = args.pop("cwd", None)
        if cwd is None:
            return request
        if not isinstance(cwd, str) or not cwd.strip():
            return original(owner, request)
        command = args.get("command")
        if not isinstance(command, str):
            return original(owner, request)
        relative = workspace_relative(cwd, target)
        root = target.replace("\\", "/").rstrip("/")
        mapped = root if relative in {"", "."} else f"{root}/{relative}"
        args["command"] = f"cd -- {shlex.quote(mapped)} && {command}"
        return _store(request, name, args)
    if base not in _PATH_TOOLS:
        return request
    base_dir = args.pop("base_dir", None)
    if base_dir is None:
        return request
    if not isinstance(base_dir, str) or not base_dir.strip():
        return original(owner, request)
    key = next(
        (
            item
            for item in ("file_path", "path")
            if isinstance(args.get(item), str) and str(args[item]).strip()
        ),
        None,
    )
    if key is not None and not str(args[key]).strip().startswith(("/", "~")):
        root = workspace_relative(base_dir, target)
        fragment = str(args[key]).strip().lstrip("./")
        args[key] = fragment if root in {"", "."} else f"{root}/{fragment}"
    return _store(request, name, args)


def _install_relative_guard() -> None:
    try:
        from octop_harness.middleware.filesystem_guard import FilesystemGuardMiddleware
    except ImportError:
        logger.debug("filesystem guard is not installed", exc_info=True)
        return
    current = FilesystemGuardMiddleware._resolve_relative_paths
    if getattr(current, "_octop_target_relative", False):
        return

    def resolve(self: Any, request: Any) -> Any:
        target = _stamped_directory()
        if not target:
            return current(self, request)
        return _against_target(request, target, current, self)

    resolve._octop_target_relative = True  # type: ignore[attr-defined]
    FilesystemGuardMiddleware._resolve_relative_paths = resolve  # type: ignore[method-assign]


def _payload(tool_call: Any) -> dict[str, Any]:
    if isinstance(tool_call, dict):
        return tool_call
    dump = getattr(tool_call, "model_dump", None)
    if callable(dump):
        data = dump(by_alias=True, exclude_none=True)
        if isinstance(data, dict):
            return data
    return {}


def _label(payload: dict[str, Any]) -> str:
    for key in ("title", "name"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def writes_member_workspace(title: str, kind: str) -> bool:
    """True when this call is the runner's own write or shell, not the target MCP."""
    text = title.strip()
    if _SERVER in text.lower():
        return False
    if kind.strip().lower() in _WRITE_KINDS:
        return True
    head = text.lower().split("(", 1)[0].strip().rsplit("/", 1)[-1]
    head = head.split()[0].rstrip(":") if head else ""
    return head in _WRITE_NAMES


def _install_runner_block() -> None:
    try:
        from octop_harness.acp.client import ACPHostedClient
        from octop_harness.acp.permissions import ACPPermissionAdapter
    except ImportError:
        logger.debug("ACP client is not installed", exc_info=True)
        return
    blocked = ACPPermissionAdapter.is_hard_blocked
    if not getattr(blocked, "_octop_runner_files", False):

        def is_hard_blocked(self: Any, tool_call: Any) -> bool:
            if _stamped_directory():
                payload = _payload(tool_call)
                kind = str(payload.get("kind") or "")
                if writes_member_workspace(_label(payload), kind):
                    return True
            return bool(blocked(self, tool_call))

        is_hard_blocked._octop_runner_files = True  # type: ignore[attr-defined]
        ACPPermissionAdapter.is_hard_blocked = is_hard_blocked  # type: ignore[method-assign]

    event_from = ACPHostedClient._tool_event_from_state
    if getattr(event_from, "_octop_runner_files", False):
        return

    def tool_event(self: Any, update: Any) -> dict[str, Any] | None:
        event = event_from(self, update)
        if not isinstance(event, dict) or not _stamped_directory():
            return event
        if str(event.get("status") or "") != "completed":
            return event
        title = str(event.get("title") or event.get("name") or "")
        kind = str(event.get("kind") or "")
        if not writes_member_workspace(title, kind):
            return event
        warning = tr("teams.runner_workspace_write", _locale())
        output = str(event.get("output") or "")
        if warning in output:
            return event
        marked = dict(event)
        marked["output"] = f"{output}\n{warning}".strip()
        marked["status"] = "failed"
        return marked

    tool_event._octop_runner_files = True  # type: ignore[attr-defined]
    ACPHostedClient._tool_event_from_state = tool_event  # type: ignore[method-assign]
