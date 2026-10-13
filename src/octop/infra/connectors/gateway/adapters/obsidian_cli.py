"""Obsidian official CLI gateway — note tools scoped to one vault."""

from __future__ import annotations

from typing import Any

from octop.infra.connectors.gateway.cli_install import (
    OBSIDIAN_CLI_MISSING,
    OBSIDIAN_NOT_RUNNING,
    locate_obsidian_binary,
)
from octop.infra.connectors.gateway.cli_runner import run_cli

_MAX_OUTPUT = 32_000
_TIMEOUT_S = 30.0
_SEARCH_TIMEOUT_S = 60.0

_DENIED_EXACT = frozenset(
    {
        "eval",
        "devtools",
        "reload",
        "restart",
        "delete",
        "command",
        "history:restore",
        "workspace:delete",
    }
)
_DENIED_PREFIXES = ("dev:", "plugin:", "theme:", "snippet:", "sync:", "publish:")
_HELP_COMMANDS = frozenset(
    {
        "search",
        "search:context",
        "read",
        "files",
        "create",
        "append",
        "prepend",
        "daily:path",
        "daily:read",
        "daily:append",
        "daily:prepend",
        "tasks",
        "task",
        "property:read",
        "property:set",
        "property:remove",
        "backlinks",
        "links",
        "unresolved",
        "orphans",
        "tags",
        "help",
    }
)

_NO_SHELL = "禁止建议或执行任何终端命令。"

TOOLS: list[dict[str, Any]] = [
    {
        "name": "search",
        "description": (
            "Search the configured Obsidian vault. "
            "mode=context returns matching lines. Use \\n for newlines in other tools. "
            "NEVER suggest or run shell commands."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "mode": {"type": "string", "enum": ["search", "context"]},
                "path": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                "case": {"type": "boolean"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "read",
        "description": "Read one note by wikilink file name or vault-relative path.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file": {"type": "string"},
                "path": {"type": "string"},
            },
        },
    },
    {
        "name": "files",
        "description": "List files in the vault, optionally under a folder or by extension.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "folder": {"type": "string"},
                "ext": {"type": "string"},
            },
        },
    },
    {
        "name": "create",
        "description": "Create a note. Multiline content must use \\n, not raw newlines.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "content": {"type": "string"},
                "template": {"type": "string"},
                "overwrite": {"type": "boolean"},
            },
        },
    },
    {
        "name": "append",
        "description": "Append or prepend content to a note. position is append or prepend.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "string"},
                "position": {"type": "string", "enum": ["append", "prepend"]},
                "file": {"type": "string"},
                "path": {"type": "string"},
            },
            "required": ["content"],
        },
    },
    {
        "name": "daily",
        "description": "Read or update today's daily note. action: path, read, append, prepend.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["path", "read", "append", "prepend"],
                },
                "content": {"type": "string"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "tasks",
        "description": (
            "List tasks, or mark one task done, todo, or toggle. Updates require line or ref."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["list", "done", "todo", "toggle"]},
                "file": {"type": "string"},
                "path": {"type": "string"},
                "line": {"type": "integer", "minimum": 1},
                "ref": {"type": "string"},
                "daily": {"type": "boolean"},
                "todo": {"type": "boolean"},
                "done": {"type": "boolean"},
                "verbose": {"type": "boolean"},
            },
        },
    },
    {
        "name": "properties",
        "description": "Read, set, or remove a note property. action: read, set, remove.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["read", "set", "remove"]},
                "name": {"type": "string"},
                "value": {"type": "string"},
                "type": {"type": "string"},
                "file": {"type": "string"},
                "path": {"type": "string"},
            },
            "required": ["action", "name"],
        },
    },
    {
        "name": "links",
        "description": "List backlinks, outgoing links, unresolved links, or orphans.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "kind": {
                    "type": "string",
                    "enum": ["backlinks", "links", "unresolved", "orphans"],
                },
                "file": {"type": "string"},
                "path": {"type": "string"},
            },
        },
    },
    {
        "name": "tags",
        "description": "List tags in the vault or on one note.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file": {"type": "string"},
                "sort": {"type": "string"},
                "counts": {"type": "boolean"},
            },
        },
    },
    {
        "name": "help",
        "description": "Show Obsidian CLI help for an allowlisted note command.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
            },
            "required": ["command"],
        },
    },
]


def list_tools() -> list[dict[str, Any]]:
    return TOOLS


def call_tool(creds: dict[str, Any], name: str, args: dict[str, Any]) -> str:
    binary = locate_obsidian_binary(str(creds.get("binary_path") or ""))
    vault_arg = _vault_arg(creds)
    try:
        argv, timeout_s = _build_call(binary, vault_arg, name, args)
        output = _cap(run_cli(argv, timeout_s=timeout_s))
        if name == "help":
            return f"参数说明（请使用连接器工具，{_NO_SHELL}）\n{output}"
        return output
    except ValueError as exc:
        raise ValueError(_humanize_cli_error(str(exc), vault=_vault_name(creds))) from exc


def probe_credentials(creds: dict[str, Any]) -> None:
    binary = locate_obsidian_binary(str(creds.get("binary_path") or ""))
    vault = _vault_name(creds)
    try:
        run_cli([binary, f"vault={vault}", "vault"], timeout_s=_TIMEOUT_S)
    except ValueError as exc:
        raise ValueError(_humanize_cli_error(str(exc), vault=vault)) from exc


def _build_call(
    binary: str,
    vault_arg: str,
    name: str,
    args: dict[str, Any],
) -> tuple[list[str], float]:
    if name == "search":
        query = _required(args, "query")
        mode = str(args.get("mode") or "search").strip()
        command = "search:context" if mode == "context" else "search"
        if mode not in ("search", "context"):
            raise ValueError("mode must be search or context")
        argv = [binary, vault_arg, command, f"query={query}", "format=json"]
        _add_param(argv, args, "path")
        limit = args.get("limit")
        if limit is not None:
            number = int(limit)
            if number < 1 or number > 50:
                raise ValueError("limit must be between 1 and 50")
            argv.append(f"limit={number}")
        if args.get("case") is True:
            argv.append("case")
        return argv, _SEARCH_TIMEOUT_S
    if name == "read":
        return _with_file([binary, vault_arg, "read"], args, required=True), _TIMEOUT_S
    if name == "files":
        argv = [binary, vault_arg, "files"]
        _add_param(argv, args, "folder")
        _add_param(argv, args, "ext")
        return argv, _TIMEOUT_S
    if name == "create":
        argv = [binary, vault_arg, "create"]
        _add_param(argv, args, "name")
        _add_param(argv, args, "content")
        _add_param(argv, args, "template")
        if args.get("overwrite") is True:
            argv.append("overwrite")
        return argv, _TIMEOUT_S
    if name == "append":
        content = _required(args, "content")
        position = str(args.get("position") or "append").strip()
        if position not in ("append", "prepend"):
            raise ValueError("position must be append or prepend")
        argv = _with_file([binary, vault_arg, position, f"content={content}"], args)
        return argv, _TIMEOUT_S
    if name == "daily":
        action = str(args.get("action") or "").strip()
        if action not in ("path", "read", "append", "prepend"):
            raise ValueError("action must be path, read, append, or prepend")
        command = "daily:path" if action == "path" else f"daily:{action}"
        _assert_command_allowed(command)
        argv = [binary, vault_arg, command]
        if action in ("append", "prepend"):
            argv.append(f"content={_required(args, 'content')}")
        return argv, _TIMEOUT_S
    if name == "tasks":
        return _tasks_argv(binary, vault_arg, args), _TIMEOUT_S
    if name == "properties":
        return _properties_argv(binary, vault_arg, args), _TIMEOUT_S
    if name == "links":
        kind = str(args.get("kind") or "backlinks").strip()
        if kind not in ("backlinks", "links", "unresolved", "orphans"):
            raise ValueError("kind must be backlinks, links, unresolved, or orphans")
        return _with_file([binary, vault_arg, kind], args), _TIMEOUT_S
    if name == "tags":
        argv = [binary, vault_arg, "tags", "format=json"]
        _add_param(argv, args, "file")
        _add_param(argv, args, "sort")
        if args.get("counts") is True:
            argv.append("counts")
        return argv, _TIMEOUT_S
    if name == "help":
        command = _assert_command_allowed(str(args.get("command") or ""))
        return [binary, vault_arg, "help", command], _TIMEOUT_S
    raise ValueError(f"unknown Obsidian CLI tool: {name}")


def _tasks_argv(binary: str, vault_arg: str, args: dict[str, Any]) -> list[str]:
    action = str(args.get("action") or "list").strip()
    if action == "list":
        argv = [binary, vault_arg, "tasks", "format=json"]
        _add_param(argv, args, "file")
        _add_param(argv, args, "path")
        if args.get("daily") is True:
            argv.append("daily")
        if args.get("todo") is True:
            argv.append("todo")
        if args.get("done") is True:
            argv.append("done")
        if args.get("verbose") is True:
            argv.append("verbose")
        return argv
    if action not in ("done", "todo", "toggle"):
        raise ValueError("action must be list, done, todo, or toggle")
    if args.get("line") is None and not str(args.get("ref") or "").strip():
        raise ValueError("line or ref is required to update a task")
    argv = [binary, vault_arg, "task"]
    _add_param(argv, args, "file")
    _add_param(argv, args, "path")
    _add_param(argv, args, "ref")
    if args.get("line") is not None:
        argv.append(f"line={int(args['line'])}")
    if args.get("daily") is True:
        argv.append("daily")
    argv.append(action)
    return argv


def _properties_argv(binary: str, vault_arg: str, args: dict[str, Any]) -> list[str]:
    action = str(args.get("action") or "").strip()
    if action not in ("read", "set", "remove"):
        raise ValueError("action must be read, set, or remove")
    command = f"property:{action}"
    _assert_command_allowed(command)
    name = _required(args, "name")
    argv = [binary, vault_arg, command, f"name={name}"]
    if action == "set":
        argv.append(f"value={_required(args, 'value')}")
        _add_param(argv, args, "type")
    _add_param(argv, args, "file")
    _add_param(argv, args, "path")
    return argv


def _with_file(argv: list[str], args: dict[str, Any], *, required: bool = False) -> list[str]:
    file_name = str(args.get("file") or "").strip()
    path = str(args.get("path") or "").strip()
    if required and not file_name and not path:
        raise ValueError("file or path is required")
    if file_name:
        argv.append(f"file={_check_value('file', file_name)}")
    if path:
        argv.append(f"path={_check_value('path', path)}")
    return argv


def _add_param(argv: list[str], args: dict[str, Any], key: str) -> None:
    raw = args.get(key)
    if raw is None:
        return
    text = str(raw).strip()
    if not text:
        return
    argv.append(f"{key}={_check_value(key, text)}")


def _required(args: dict[str, Any], key: str) -> str:
    text = str(args.get(key) or "").strip()
    if not text:
        raise ValueError(f"{key} is required")
    return _check_value(key, text)


def _vault_name(creds: dict[str, Any]) -> str:
    vault = str(creds.get("vault") or "").strip()
    if not vault or any(char in vault for char in "\n\r\x00"):
        raise ValueError("vault is required")
    return vault


def _vault_arg(creds: dict[str, Any]) -> str:
    return f"vault={_vault_name(creds)}"


def _check_value(field: str, value: str) -> str:
    if any(char in value for char in "\n\r\x00"):
        raise ValueError(f"{field} 不能包含换行")
    if value.startswith("="):
        raise ValueError(f"{field} 不能以 = 开头")
    return value


def _assert_command_allowed(command: str) -> str:
    name = command.strip()
    if not name or any(char in name for char in " \t\n\r=/\\"):
        raise ValueError("command 无效")
    lower = name.lower()
    if lower in _DENIED_EXACT or any(lower.startswith(prefix) for prefix in _DENIED_PREFIXES):
        raise ValueError(f"不允许执行 Obsidian 命令 {name}。{_NO_SHELL}")
    if lower not in _HELP_COMMANDS:
        raise ValueError(f"不支持的 Obsidian 命令 {name}。{_NO_SHELL}")
    return name


def _cap(text: str) -> str:
    if len(text) <= _MAX_OUTPUT:
        return text
    return text[:_MAX_OUTPUT] + "\n…(truncated)"


def _humanize_cli_error(message: str, *, vault: str) -> str:
    text = (message or "").strip()
    if text.startswith("主机上未找到 Obsidian CLI") or text.startswith("Obsidian 未在运行"):
        return text
    if text.startswith("找不到库") or text.startswith("不允许执行") or text.startswith("不支持的"):
        return text
    lower = text.lower()
    if (
        "command not found" in lower
        or "未找到命令" in text
        or "未找到主机命令" in text
        or "no such file" in lower
        or "not recognized" in lower
        or "cannot find the file" in lower
    ):
        return OBSIDIAN_CLI_MISSING
    if any(
        phrase in lower
        for phrase in (
            "not running",
            "is not open",
            "could not connect",
            "connection refused",
            "econnrefused",
            "failed to connect",
            "cannot connect",
        )
    ):
        return OBSIDIAN_NOT_RUNNING
    if "vault" in lower and any(
        phrase in lower
        for phrase in ("not found", "unknown", "no such", "does not exist", "could not find")
    ):
        return f"找不到库「{vault}」。请填写 Obsidian 侧边栏显示的库名，不是文件夹路径。{_NO_SHELL}"
    if "找不到库" in text:
        return f"找不到库「{vault}」。请填写 Obsidian 侧边栏显示的库名，不是文件夹路径。{_NO_SHELL}"
    if any(token in lower for token in ("sudo ", "npm install", "ln -s", "ln -sf")):
        return OBSIDIAN_CLI_MISSING
    return text
