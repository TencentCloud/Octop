"""Filesystem boundary: path denies, user-owned memory and soft failures.

deepagents ``FilesystemMiddleware`` rejects ``permissions`` when the backend
implements ``SandboxBackendProtocol`` (``local_shell``). Harness still needs
deny rules for read/write filesystem tools there.

Separately, deepagents ``FilesystemBackend._resolve_path`` raises ``ValueError``
for paths outside ``root_dir``, but ``read`` / ``write`` / … only catch
``(OSError, RuntimeError)`` — so the exception escapes ToolNode and aborts the
turn. This middleware softens those into ``ToolMessage(status="error")``.
"""

from __future__ import annotations

import logging
import os
import posixpath
import re
from collections.abc import Awaitable, Callable, Iterable
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from deepagents.backends.utils import validate_path
from deepagents.middleware.filesystem import FilesystemPermission
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langchain_core.messages.tool import ToolCall
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command
from wcmatch import glob as wcglob

if TYPE_CHECKING:
    from octop_harness.backends.workspace import BackendWorkspace

logger = logging.getLogger(__name__)

# Aligned with deepagents.middleware.filesystem._DEFAULT_FS_TOOL_OPS /
# _check_fs_permission / _FS_WCMATCH_FLAGS (private there; mirrored here).
_FS_TOOL_OPS: dict[str, Literal["read", "write"]] = {
    "ls": "read",
    "read_file": "read",
    "glob": "read",
    "grep": "read",
    "write_file": "write",
    "edit_file": "write",
    "delete": "write",
}
_FS_WCMATCH_FLAGS = wcglob.BRACE | wcglob.GLOBSTAR
_MEMORY_WRITE_TOOLS = frozenset({"write_file", "edit_file", "append_file", "delete", "delete_file", "move_file"})
_MEMORY_READ_ONLY_MESSAGE = (
    "{filename} is user-maintained memory. Edit it manually in the memory dashboard. "
    "Use memory_save to remember information in octop-memory."
)

_OUTSIDE_ROOT_REMEDIATION = (
    "The path is outside this agent's storage root. "
    "Use a path under the storage root (workspace-relative), or ask the user to "
    "widen the storage root so it contains this path "
    "(on Windows, set an explicit drive path such as D:/octop-data)."
)

_WINDOWS_ABS_RE = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\)")


def is_windows_absolute_path(raw: str) -> bool:
    """True for leftover ``D:\\…`` / ``D:/…`` / UNC host paths."""
    return bool(_WINDOWS_ABS_RE.match(raw.strip()))


def rewrite_legacy_windows_fs_path(
    raw: str,
    *,
    root_dir: str | Path | None = None,
    workspace_dir: str | Path | None = None,
) -> str:
    """Map a leftover Windows absolute path onto the current storage jail.

    Conversation history and memory often keep ``D:\\octop-data\\…`` after the
    backend root moves (or after migrating off Windows). deepagents virtual
    mode treats that drive-letter string as a relative key; pathlib then jumps
    to the other drive and raises ``Path … outside root directory``, which
    used to abort the whole turn as a generic model-call failure.

    When the same suffix exists under *root_dir* or *workspace_dir*, return a
    jail-safe virtual path (``/data/…``). Otherwise return *raw* unchanged so
    the outside-root soft-fail can explain the storage-root mismatch.
    """
    text = raw.strip()
    if not text or not is_windows_absolute_path(text):
        return raw

    for base in (root_dir, workspace_dir):
        mapped = _virtual_path_if_under_base(text, base)
        if mapped is not None:
            return mapped

    posix = text.replace("\\", "/")
    stripped = posix.split(":", 1)[-1].lstrip("/") if ":" in posix[:3] else posix.lstrip("/")
    parts = [part for part in stripped.split("/") if part]
    bases = [Path(item) for item in (root_dir, workspace_dir) if item]
    for index in range(len(parts)):
        suffix = "/".join(parts[index:])
        for base in bases:
            try:
                candidate = (base.expanduser() / suffix).resolve()
            except OSError:
                continue
            if candidate.is_file() or candidate.is_dir():
                return f"/{suffix}"
    return raw


def _virtual_path_if_under_base(windows_path: str, base: str | Path | None) -> str | None:
    if base is None:
        return None
    try:
        resolved_base = Path(base).expanduser().resolve()
        resolved = Path(windows_path).expanduser().resolve()
        rel = resolved.relative_to(resolved_base).as_posix()
    except (OSError, ValueError):
        return None
    return "/" if not rel or rel == "." else f"/{rel}"


def _tool_base_name(name: str) -> str:
    trimmed = name.strip()
    slash = trimmed.rfind("/")
    return trimmed[slash + 1 :] if slash >= 0 else trimmed


def _normalized_memory_path(path: str) -> str:
    return posixpath.normpath(path.strip().replace("\\", "/")).casefold()


def _path_from_tool_args(tool_name: str, params: dict[str, Any]) -> str | None:
    base = _tool_base_name(tool_name)
    if base in {"read_file", "write_file", "edit_file", "delete"}:
        for key in ("file_path", "path"):
            raw = params.get(key)
            if isinstance(raw, str) and raw.strip():
                return raw.strip()
        return None
    if base in {"ls", "glob", "grep"}:
        raw = params.get("path")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None


def _realpath_if_available(path: str) -> str | None:
    try:
        if os.path.lexists(path):
            return os.path.realpath(path)
    except OSError:
        return None
    return None


def _expand_path_candidates(path: str) -> tuple[str, ...]:
    """Path forms to match against deny/allow patterns.

    Includes the logical path and its realpath (macOS ``/etc`` → ``/private/etc``).
    """
    out: list[str] = [path]
    real = _realpath_if_available(path)
    if real and real not in out:
        out.append(real)
    return tuple(out)


def _expand_patterns(pattern: str) -> tuple[str, ...]:
    """Expand one policy pattern so directory roots are covered.

    ``/etc/**`` must also match ``/etc`` itself (``ls /etc``). When the prefix
    resolves through a symlink (macOS), also match the realpath forms.
    """
    patterns: list[str] = [pattern]
    if pattern.endswith("/**"):
        prefix = pattern[:-3]
        if prefix and prefix not in patterns:
            patterns.append(prefix)
        real_prefix = _realpath_if_available(prefix) if prefix else None
        if real_prefix:
            if real_prefix not in patterns:
                patterns.append(real_prefix)
            real_glob = f"{real_prefix}/**"
            if real_glob not in patterns:
                patterns.append(real_glob)
    return tuple(patterns)


def _path_matches_patterns(path: str, patterns: Iterable[str]) -> bool:
    for candidate in _expand_path_candidates(path):
        for pattern in patterns:
            for expanded in _expand_patterns(pattern):
                if wcglob.globmatch(candidate, expanded, flags=_FS_WCMATCH_FLAGS):
                    return True
    return False


def _check_fs_permission(
    rules: list[FilesystemPermission],
    operation: Literal["read", "write"],
    path: str,
) -> Literal["allow", "deny", "interrupt"]:
    """First-match path rule — directory roots and symlink aliases included."""
    for rule in rules:
        if operation not in rule.operations:
            continue
        if _path_matches_patterns(path, rule.paths):
            return rule.mode
    return "allow"


def filesystem_guard_block_reason(
    permissions: list[FilesystemPermission],
    *,
    tool_name: str,
    params: dict[str, Any],
) -> str | None:
    """Return a rejection message when *tool_name* is denied by *permissions*.

    Matched sensitive paths refuse access for read/write filesystem tools
    (``ls``, ``read_file``, ``glob``, ``grep``, ``write_file``, ``edit_file``).
    """
    if not permissions:
        return None
    base = _tool_base_name(tool_name)
    operation = _FS_TOOL_OPS.get(base)
    if operation is None:
        return None
    raw_path = _path_from_tool_args(tool_name, params)
    if raw_path is None:
        return None
    try:
        validated_path = validate_path(raw_path)
    except ValueError:
        return None
    if _check_fs_permission(permissions, operation, validated_path) == "deny":
        return f"Error: permission denied for {operation} on {validated_path}"
    return None


def is_path_outside_root_error(exc: BaseException) -> bool:
    """True when *exc* is the deepagents virtual-path jail ``ValueError``."""
    if not isinstance(exc, ValueError):
        return False
    lower = str(exc).lower()
    return "outside root directory" in lower or "path traversal not allowed" in lower


def path_outside_root_tool_message(
    *,
    tool_name: str,
    tool_call_id: str,
    exc: BaseException,
) -> ToolMessage:
    """Build a model-visible tool error for an outside-root failure."""
    return ToolMessage(
        content=f"Error: {exc}. {_OUTSIDE_ROOT_REMEDIATION}",
        name=tool_name or "tool",
        tool_call_id=tool_call_id,
        status="error",
    )


def _tool_call_meta(request: ToolCallRequest) -> tuple[str, str]:
    tool_call = request.tool_call
    return str(tool_call.get("name") or ""), str(tool_call.get("id") or "")


class FilesystemGuardMiddleware(AgentMiddleware[Any, Any]):
    """Filesystem tool boundary: user-owned memory, denies and soft failures.

    When a workspace is bound, MEMORY.md / USER.md writes are blocked independently of
    optional permission rules and shell-command guard settings.
    Outside-root softening applies only to filesystem tools (``ls``,
    ``read_file``, …), not arbitrary tool ValueErrors.
    """

    def __init__(
        self,
        permissions: list[FilesystemPermission] | None = None,
        *,
        root_dir: str | Path | None = None,
        workspace_dir: str | Path | None = None,
        workspace: BackendWorkspace | None = None,
    ) -> None:
        self._permissions = list(permissions or ())
        self._root_dir = root_dir
        self._workspace_dir = workspace_dir
        self._workspace = workspace
        self._rewritten_logged: set[str] = set()

    def _rewrite_legacy_windows_request(self, request: ToolCallRequest) -> ToolCallRequest:
        tool_name, _ = _tool_call_meta(request)
        raw_args: Any = request.tool_call.get("args") or {}
        path = (
            _path_from_tool_args(tool_name, raw_args)
            if _tool_base_name(tool_name) in _FS_TOOL_OPS and isinstance(raw_args, dict)
            else None
        )
        rewritten = (
            rewrite_legacy_windows_fs_path(
                path,
                root_dir=self._root_dir,
                workspace_dir=self._workspace_dir,
            )
            if path
            else None
        )
        if not path or rewritten is None or rewritten == path:
            return request
        new_args: dict[str, Any] = dict(raw_args)
        key = next((name for name in ("file_path", "path") if new_args.get(name) == path), None)
        if key is None:
            return request
        new_args[key] = rewritten
        if path not in self._rewritten_logged:
            self._rewritten_logged.add(path)
            logger.debug("FilesystemGuard rewrote leftover Windows path %s -> %s", path, rewritten)
        new_call: ToolCall = {
            "name": str(request.tool_call.get("name") or ""),
            "args": new_args,
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

    def _memory_write_block_reason(self, tool_name: str, params: dict[str, Any]) -> str | None:
        workspace = self._workspace
        if workspace is None or _tool_base_name(tool_name) not in _MEMORY_WRITE_TOOLS:
            return None
        protected: dict[str, str] = {}
        for filename in ("MEMORY.md", "USER.md"):
            canonical = workspace.system_rel(filename)
            for path in (filename, f"/{filename}", canonical, f"/{canonical}", workspace.resolve_path(filename)):
                protected[_normalized_memory_path(path)] = filename
        for key in ("file_path", "path", "source", "destination"):
            raw = params.get(key)
            if not isinstance(raw, str):
                continue
            matched_filename = protected.get(_normalized_memory_path(raw))
            if matched_filename is None:
                try:
                    matched_filename = protected.get(_normalized_memory_path(workspace.resolve_path(raw)))
                except (OSError, ValueError, PermissionError):
                    continue
            if matched_filename is not None:
                return _MEMORY_READ_ONLY_MESSAGE.format(filename=matched_filename)
        return None

    def _blocked_message(self, request: ToolCallRequest) -> ToolMessage | None:
        tool_name, call_id = _tool_call_meta(request)
        raw_args: Any = request.tool_call.get("args") or {}
        params: dict[str, Any] = raw_args if isinstance(raw_args, dict) else {}
        reason = self._memory_write_block_reason(tool_name, params) or filesystem_guard_block_reason(
            self._permissions,
            tool_name=tool_name,
            params=params,
        )
        if reason is None:
            return None
        logger.info("FilesystemGuard blocked %s", tool_name)
        return ToolMessage(
            content=reason,
            name=tool_name or "tool",
            tool_call_id=call_id,
            status="error",
        )

    def _soften_outside_root(
        self,
        request: ToolCallRequest,
        exc: ValueError,
    ) -> ToolMessage | None:
        if not is_path_outside_root_error(exc):
            return None
        tool_name, call_id = _tool_call_meta(request)
        if _tool_base_name(tool_name) not in _FS_TOOL_OPS:
            return None
        logger.info("FilesystemGuard softened outside-root %s: %s", tool_name, exc)
        return path_outside_root_tool_message(
            tool_name=tool_name,
            tool_call_id=call_id,
            exc=exc,
        )

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        request = self._rewrite_legacy_windows_request(request)
        blocked = self._blocked_message(request)
        if blocked is not None:
            return blocked
        try:
            return await handler(request)
        except ValueError as exc:
            softened = self._soften_outside_root(request, exc)
            if softened is not None:
                return softened
            raise

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        request = self._rewrite_legacy_windows_request(request)
        blocked = self._blocked_message(request)
        if blocked is not None:
            return blocked
        try:
            return handler(request)
        except ValueError as exc:
            softened = self._soften_outside_root(request, exc)
            if softened is not None:
                return softened
            raise


__all__ = [
    "FilesystemGuardMiddleware",
    "filesystem_guard_block_reason",
    "is_path_outside_root_error",
    "is_windows_absolute_path",
    "path_outside_root_tool_message",
    "rewrite_legacy_windows_fs_path",
]
