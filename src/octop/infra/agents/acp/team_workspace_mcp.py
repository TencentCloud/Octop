"""One loopback MCP for a managed member's team turn.

This server is the selected workspace: the same read, write, execute, and
send operations, with the directory in every tool description.
``send_file_to_user`` reads that workspace. The runner's own write and shell
tools are denied while a target is stamped; a call that still runs is marked
as the runner workspace.
"""

from __future__ import annotations

import asyncio
import json
import secrets
from dataclasses import dataclass
from typing import Any

from octop.infra.agents.teams.file_target import SERVER_NAME, acall_backend

_PROTOCOL = "2024-11-05"
_SCOPES: dict[str, TeamWorkspaceScope] = {}
_TOKENS: dict[tuple[str, str, bool, bool], str] = {}
_READ_LINES = 2000
_EXECUTE_CAP = 20_000


@dataclass(frozen=True)
class TeamWorkspaceScope:
    host_agent_id: str
    directory: str
    execute: bool
    bridge_target_id: str = ""
    deliver: bool = True


def team_workspace_scope(token: str) -> TeamWorkspaceScope | None:
    return _SCOPES.get(token)


def retain_team_workspace_scope(scope: TeamWorkspaceScope) -> str:
    """Reuse one token per host so the ACP session is not reloaded each turn."""
    key = (scope.host_agent_id, scope.bridge_target_id, scope.execute, scope.deliver)
    token = _TOKENS.get(key)
    if token is None:
        token = secrets.token_urlsafe(32)
        _TOKENS[key] = token
    _SCOPES[token] = scope
    return token


def _ok(req_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    if req_id is None:
        return {}
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _err(req_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _arguments(params: Any) -> dict[str, Any]:
    if not isinstance(params, dict):
        return {}
    raw = params.get("arguments") or {}
    if not isinstance(raw, dict):
        return {}
    nested = raw.get("kwargs")
    if nested is not None and set(raw.keys()) == {"kwargs"} and isinstance(nested, dict):
        return nested
    return raw


def _text(req_id: Any, text: str, *, failed: bool = False) -> dict[str, Any]:
    return _ok(req_id, {"content": [{"type": "text", "text": text}], "isError": failed})


def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required}


def _tools(scope: TeamWorkspaceScope) -> list[dict[str, Any]]:
    directory = scope.directory
    where = (
        f"Default workspace directory: {directory}. "
        "Relative paths resolve from this directory. Prefer these tools."
    )
    path = {"type": "string", "description": f"File or directory path. {where}"}
    tools = [
        {
            "name": "ls",
            "description": f"List a directory in the workspace. {where}",
            "inputSchema": _schema({"path": path}, []),
        },
        {
            "name": "read_file",
            "description": f"Read a file in the workspace. {where}",
            "inputSchema": _schema(
                {
                    "file_path": path,
                    "offset": {"type": "integer", "description": "0-based line offset."},
                    "limit": {"type": "integer", "description": "Maximum lines."},
                },
                ["file_path"],
            ),
        },
        {
            "name": "write_file",
            "description": f"Create a file in the workspace. Fails if it already exists. {where}",
            "inputSchema": _schema(
                {"file_path": path, "content": {"type": "string"}},
                ["file_path", "content"],
            ),
        },
        {
            "name": "edit_file",
            "description": f"Replace text in a workspace file. {where}",
            "inputSchema": _schema(
                {
                    "file_path": path,
                    "old_string": {"type": "string"},
                    "new_string": {"type": "string"},
                    "replace_all": {"type": "boolean"},
                },
                ["file_path", "old_string", "new_string"],
            ),
        },
        {
            "name": "glob",
            "description": f"Find files in the workspace. {where}",
            "inputSchema": _schema(
                {"pattern": {"type": "string"}, "path": path},
                ["pattern"],
            ),
        },
        {
            "name": "grep",
            "description": f"Search file contents in the workspace. {where}",
            "inputSchema": _schema(
                {"pattern": {"type": "string"}, "path": path, "glob": {"type": "string"}},
                ["pattern"],
            ),
        },
        {
            "name": "delete",
            "description": f"Delete a file in the workspace. {where}",
            "inputSchema": _schema({"file_path": path}, ["file_path"]),
        },
    ]
    if scope.deliver:
        tools.append(
            {
                "name": "send_file_to_user",
                "description": (f"Send an existing file from this workspace to the user. {where}"),
                "inputSchema": _schema({"file_path": path}, ["file_path"]),
            }
        )
    if scope.execute:
        tools.append(
            {
                "name": "execute",
                "description": (
                    f"Run a shell command in the workspace. The working directory is {directory}."
                ),
                "inputSchema": _schema(
                    {
                        "command": {"type": "string"},
                        "timeout": {"type": "integer", "description": "Seconds."},
                    },
                    ["command"],
                ),
            }
        )
    return tools


def _paths(entries: Any) -> str:
    lines: list[str] = []
    for entry in entries or []:
        if isinstance(entry, dict):
            text = str(entry.get("path") or "")
        else:
            text = str(getattr(entry, "path", "") or "")
        if text:
            lines.append(text)
    return "\n".join(lines) if lines else "(empty)"


def _grep_lines(matches: Any) -> str:
    lines: list[str] = []
    for match in matches or []:
        if isinstance(match, dict):
            path = match.get("path") or ""
            line = match.get("line")
            text = match.get("text") or ""
        else:
            path = getattr(match, "path", "")
            line = getattr(match, "line", None)
            text = getattr(match, "text", "")
        if line is None:
            lines.append(f"{path}:{text}")
        else:
            lines.append(f"{path}:{line}:{text}")
    return "\n".join(lines) if lines else "(no matches)"


async def handle_team_workspace_mcp(
    body: dict[str, Any],
    *,
    scope: TeamWorkspaceScope,
    workspace: Any,
    backend: Any,
) -> dict[str, Any]:
    """Answer one JSON-RPC request. An empty dict means the caller should return 202."""
    method = str(body.get("method") or "")
    req_id = body.get("id")
    params = body.get("params") or {}
    if method == "initialize":
        return _ok(
            req_id,
            {
                "protocolVersion": _PROTOCOL,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": "0.1.0"},
            },
        )
    if method == "notifications/initialized":
        return {}
    if method == "tools/list":
        return _ok(req_id, {"tools": _tools(scope)})
    if method == "ping":
        return _ok(req_id, {})
    if method != "tools/call":
        return _err(req_id, -32601, f"Method not found: {method}")
    name = str(params.get("name") or "") if isinstance(params, dict) else ""
    args = _arguments(params)
    try:
        text = await run_workspace_tool(
            name, args, scope=scope, workspace=workspace, backend=backend
        )
    except Exception as exc:
        return _text(req_id, str(exc), failed=True)
    failed = text.startswith("Error:")
    return _text(req_id, text, failed=failed)


async def run_workspace_tool(
    name: str,
    args: dict[str, Any],
    *,
    scope: TeamWorkspaceScope,
    workspace: Any,
    backend: Any,
) -> str:
    """Run one workspace tool. Bridge file ops forward; send stays on this side."""
    if name in {"send_file", "send_file_to_user"}:
        return await _send(workspace, backend, args)
    if getattr(backend, "bridge_file_target", False):
        return str(await backend.call_text(name, args))
    return await _call(name, args, scope=scope, workspace=workspace, backend=backend)


async def _call(
    name: str,
    args: dict[str, Any],
    *,
    scope: TeamWorkspaceScope,
    workspace: Any,
    backend: Any,
) -> str:
    if name == "ls":
        result = await workspace.als(str(args.get("path") or "."))
        error = getattr(result, "error", None)
        if result is None or error:
            return f"Error: {error or 'ls failed'}"
        return _paths(getattr(result, "entries", None))
    if name == "read_file":
        return await _read(workspace, str(args.get("file_path") or args.get("path") or ""), args)
    if name == "write_file":
        path = str(args.get("file_path") or "").strip()
        if not path:
            return "Error: file_path is required"
        await workspace.awrite_text(path, str(args.get("content") or ""), force=False)
        return f"Wrote {path}"
    if name == "edit_file":
        return await _edit(workspace, args)
    if name == "glob":
        pattern = str(args.get("pattern") or "").strip()
        if not pattern:
            return "Error: pattern is required"
        result = await workspace.aglob(pattern, str(args.get("path") or "."))
        error = getattr(result, "error", None)
        if result is None or error:
            return f"Error: {error or 'glob failed'}"
        return _paths(getattr(result, "matches", None))
    if name == "grep":
        pattern = str(args.get("pattern") or "").strip()
        if not pattern:
            return "Error: pattern is required"
        result = await workspace.agrep(pattern, str(args.get("path") or "."))
        error = getattr(result, "error", None)
        if result is None or error:
            return f"Error: {error or 'grep failed'}"
        return _grep_lines(getattr(result, "matches", None))
    if name == "delete":
        path = str(args.get("file_path") or "").strip()
        if not path:
            return "Error: file_path is required"
        await workspace.adelete(path)
        return f"Deleted {path}"
    if name == "execute":
        if not scope.execute:
            return "Error: this workspace has no shell; do not call execute"
        command = str(args.get("command") or "").strip()
        if not command:
            return "Error: command is required"
        timeout = args.get("timeout")
        if isinstance(timeout, int) and not isinstance(timeout, bool) and timeout >= 0:
            response = await acall_backend(backend, "aexecute", command, timeout=timeout)
        else:
            response = await acall_backend(backend, "aexecute", command)
        output = str(getattr(response, "output", "") or "")
        if len(output) > _EXECUTE_CAP:
            output = output[-_EXECUTE_CAP:]
        code = getattr(response, "exit_code", None)
        if code is None:
            return output or "(no output)"
        return f"{output}\n[exit code {code}]".strip()
    return f"Error: unknown tool {name}"


class _MaterializedFile:
    """Workspace facade whose only file is the one just fetched over the bridge."""

    def __init__(self, path: Any) -> None:
        self._path = path

    def materialize_local(self, file_path: str) -> Any:
        del file_path
        return self._path


async def _send(workspace: Any, backend: Any, args: dict[str, Any]) -> str:
    """Deliver a file that already lives in the target workspace."""
    path = str(args.get("file_path") or args.get("path") or "").strip()
    if not path:
        return "Error: file_path is required"
    if getattr(backend, "bridge_file_target", False):
        try:
            local = await backend.materialize(path)
        except Exception as exc:
            return f"Error: {exc}"
        workspace = _MaterializedFile(local)
    try:
        from octop_harness.builtin.tools.send_file import build_send_file_to_user_tool

        tool = build_send_file_to_user_tool(workspace)
        result = await asyncio.to_thread(tool.invoke, {"file_path": path})
    except Exception as exc:
        return f"Error: {exc}"
    if not isinstance(result, dict):
        return f"Error: {result}"
    marked = {**result, "octop_delivery": "send_file_to_user"}
    return json.dumps(marked, ensure_ascii=False)


async def _read(workspace: Any, path: str, args: dict[str, Any]) -> str:
    if not path.strip():
        return "Error: file_path is required"
    text = await workspace.aread_text(path)
    if text is None:
        return f"Error: no such file: {path}"
    lines = str(text).splitlines()
    offset = args.get("offset")
    start = offset if isinstance(offset, int) and not isinstance(offset, bool) and offset > 0 else 0
    limit = args.get("limit")
    count = (
        limit
        if isinstance(limit, int) and not isinstance(limit, bool) and limit > 0
        else _READ_LINES
    )
    window = lines[start : start + count]
    return "\n".join(window)


async def _edit(workspace: Any, args: dict[str, Any]) -> str:
    path = str(args.get("file_path") or "").strip()
    old = args.get("old_string")
    new = args.get("new_string")
    if not path or not isinstance(old, str) or not isinstance(new, str):
        return "Error: file_path, old_string, and new_string are required"
    if old == new:
        return "Error: old_string and new_string must differ"
    text = await workspace.aread_text(path)
    if text is None:
        return f"Error: no such file: {path}"
    found = str(text).count(old)
    if found == 0:
        return "Error: old_string was not found"
    replace_all = args.get("replace_all") is True
    if not replace_all and found != 1:
        return f"Error: old_string matched {found} times; pass replace_all to change all"
    updated = str(text).replace(old, new) if replace_all else str(text).replace(old, new, 1)
    await workspace.awrite_text(path, updated, force=True)
    return f"Edited {path}"
