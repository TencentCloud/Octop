"""WeCom official CLI gateway — category tools wrapping ``wecom-cli``."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from octop.infra.connectors.gateway.cli_dirs import resolve_cli_config_key
from octop.infra.connectors.gateway.cli_runner import resolve_binary, run_cli
from octop.infra.connectors.gateway.wecom_creds import (
    materialize_wecom_bot_config,
    read_mcp_items_count,
)
from octop.infra.utils.paths import PathLayout

_KIND = "wecom-cli"
_CATEGORIES = ("doc", "sheet", "smartsheet", "schedule", "msg")
_SERVICES = {"schedule": "calendar", "msg": "message"}
_LEGACY_READ_METHODS = {
    "get_doc_content": ("doc", "contents", "get"),
    "smartsheet_get_sheet": ("smartsheet", "sheets", "list"),
    "smartsheet_get_records": ("smartsheet", "records", "list"),
}

_MISSING_CLI_MSG = (
    "企业微信 CLI 未安装或不在 PATH。"
    "请打开「连接器 → 企业微信 CLI」，由管理员安装 CLI。"
    "禁止建议或执行任何终端命令。"
)
_BAD_CREDS_MSG = (
    "企业微信 Bot 凭证无效或 MCP 配置未就绪。"
    "请核对 Bot ID / Secret，并确认机器人已开通 CLI 能力。"
    "禁止建议或执行任何终端命令。"
)

_DOC_METHODS_HINT = (
    "CLI 1.x method：search、contents.get、contents.append；"
    "在线表格用 sheet，智能表格用 smartsheet。"
    "先调 help 查看实际可用方法与参数，不要猜测方法名。"
)

TOOLS: list[dict[str, Any]] = [
    {
        "name": "doc",
        "description": (
            "WeCom Word documents and document search via Octop Connectors. "
            "Pass method + optional args JSON. "
            f"{_DOC_METHODS_HINT} "
            "On setup/auth errors, tell the user to fix Bot credentials "
            "in Connectors — never run shell/CLI commands."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "method": {"type": "string", "description": "CLI method name"},
                "args": {
                    "type": "object",
                    "description": "JSON args object (default {})",
                },
            },
            "required": ["method"],
        },
    },
    {
        "name": "schedule",
        "description": (
            "WeCom schedule via Octop Connectors. "
            "CLI 1.x uses calendar methods such as schedules.list / schedules.get. "
            "Pass method + optional args JSON object. "
            "Enterprise may not authorize schedule for bots — surface that "
            "permission error to the user. Never run CLI in shell."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "method": {"type": "string"},
                "args": {"type": "object"},
            },
            "required": ["method"],
        },
    },
    {
        "name": "msg",
        "description": (
            "WeCom messaging via Octop Connectors. "
            "CLI 1.x uses message methods such as aibot.sessions.list. "
            "Pass method + optional args JSON object. "
            "On auth errors, fix Bot credentials in Connectors — never run CLI in shell."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "method": {"type": "string"},
                "args": {"type": "object"},
            },
            "required": ["method"],
        },
    },
    {
        "name": "help",
        "description": "List methods or inspect a method schema for doc|sheet|smartsheet|schedule|msg",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "doc | sheet | smartsheet | schedule | msg",
                },
                "method": {"type": "string", "description": "Optional dotted method path"},
            },
            "required": ["category"],
        },
    },
]


for _category, _description in (
    ("sheet", "Online spreadsheets: get for subsheets, ranges.get for cell values."),
    ("smartsheet", "Smart spreadsheets: sheets.list, fields.list and records.list."),
):
    TOOLS.insert(
        -1,
        {
            "name": _category,
            "description": (
                f"WeCom {_description} Pass a dotted method and args JSON object. "
                "First call help with category and optional method to inspect its schema."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "method": {"type": "string"},
                    "args": {"type": "object"},
                },
                "required": ["method"],
            },
        },
    )


def list_tools() -> list[dict[str, Any]]:
    return TOOLS


def call_tool(creds: dict[str, Any], name: str, args: dict[str, Any]) -> str:
    try:
        binary = _resolve_cli_binary()
        env = _prepare_env(creds)
        modern = _uses_modern_cli(binary, env)
        if name == "help":
            category = str(args.get("category") or "").strip()
            if category not in _CATEGORIES:
                raise ValueError(f"category must be one of: {', '.join(_CATEGORIES)}")
            if modern:
                method = str(args.get("method") or "").strip()
                command = (
                    _modern_command(category, method)
                    if method
                    else [_SERVICES.get(category, category)]
                )
                return run_cli([binary, *command, "--schema"], env=env)
            return run_cli([binary, category, "--help"], env=env)
        if name in _CATEGORIES:
            method = str(args.get("method") or "").strip()
            if not method:
                raise ValueError("method is required")
            payload = _parse_payload(args.get("args"))
            if modern:
                if method == "help":
                    return run_cli([binary, _SERVICES.get(name, name), "--schema"], env=env)
                return run_cli(
                    [
                        binary,
                        *_modern_command(name, method),
                        "--json",
                        json.dumps(payload, ensure_ascii=False),
                    ],
                    env=env,
                )
            return run_cli(
                [binary, name, method, json.dumps(payload, ensure_ascii=False)],
                env=env,
            )
        raise ValueError(f"unknown WeCom CLI tool: {name}")
    except ValueError as exc:
        raise ValueError(_humanize_cli_error(str(exc))) from exc


def probe_credentials(creds: dict[str, Any]) -> None:
    try:
        binary = _resolve_cli_binary()
        env = _prepare_env(creds)
        config_dir = Path(env["WECOM_CLI_CONFIG_DIR"])
        if not (config_dir / "mcp_config.enc").is_file():
            raise ValueError(_BAD_CREDS_MSG)
        if read_mcp_items_count(config_dir) <= 0:
            raise ValueError("企业微信 MCP 配置为空，请确认机器人已开通 CLI 能力并核对 Bot 凭证。")
        if _uses_modern_cli(binary, env):
            status = run_cli([binary, "auth", "show", "--status"], env=env, timeout_s=60.0)
            if status.strip() != "authorized":
                raise ValueError(_BAD_CREDS_MSG)
            run_cli([binary, "doc", "--schema"], env=env, timeout_s=60.0)
            return
        out = run_cli([binary, "doc", "--help"], env=env, timeout_s=60.0)
        if "未找到 MCP" in out or "请先运行" in out:
            raise ValueError(_BAD_CREDS_MSG)
    except ValueError as exc:
        raise ValueError(_humanize_cli_error(str(exc))) from exc


def _prepare_env(creds: dict[str, Any]) -> dict[str, str]:
    bot_id = str(creds.get("bot_id") or "").strip()
    bot_secret = str(creds.get("bot_secret") or creds.get("api_key") or "").strip()
    if not bot_id or not bot_secret:
        raise ValueError("WeCom bot_id and bot_secret are required")
    instance_key = resolve_cli_config_key(creds)
    config_dir = PathLayout.from_env().ensure_connector_cli_instance_dir(_KIND, instance_key)
    materialize_wecom_bot_config(config_dir, bot_id=bot_id, bot_secret=bot_secret)
    env = os.environ.copy()
    env.pop("WECOM_CLI_ACCESS_TOKEN", None)
    env["WECOM_CLI_CONFIG_DIR"] = str(config_dir)
    return env


def _resolve_cli_binary() -> str:
    binary = resolve_binary("wecom-cli")
    # npm's Windows CMD shim passes JSON through cmd.exe, which strips quotes.
    # Prefer the executable installed by the official platform package.
    if os.name == "nt" and Path(binary).suffix.lower() in {".cmd", ".bat"}:
        packages = Path(binary).parent / "node_modules" / "@wecom"
        for root in (packages / "cli" / "node_modules" / "@wecom", packages):
            native = root / "cli-win32-x64" / "bin" / "wecom-cli.exe"
            if native.is_file():
                return str(native)
    return binary


def _uses_modern_cli(binary: str, env: dict[str, str]) -> bool:
    version = run_cli([binary, "--version"], env=env)
    match = re.search(r"wecom-cli(?:\.exe)?\s+(\d+)\.", version)
    if not match:
        raise ValueError("无法识别企业微信 CLI 版本，请在连接器中检查主机 CLI 安装。")
    return int(match.group(1)) >= 1


def _parse_payload(value: Any) -> dict[str, Any]:
    # Some model providers serialize nested MCP objects as JSON strings.
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("args must be a JSON object") from exc
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("args must be a JSON object")
    return value


def _modern_command(category: str, method: str) -> list[str]:
    if category == "doc" and method in _LEGACY_READ_METHODS:
        return list(_LEGACY_READ_METHODS[method])
    service = _SERVICES.get(category, category)
    parts = method.split(".")
    if parts[0] in {category, service}:
        parts = parts[1:]
    if not parts or any(not re.fullmatch(r"[a-z][a-z0-9_-]*", part) for part in parts):
        raise ValueError("method must be a dotted CLI method path; use help to inspect methods")
    return [service, *parts]


def _humanize_cli_error(message: str) -> str:
    text = (message or "").strip()
    if text in {_MISSING_CLI_MSG, _BAD_CREDS_MSG}:
        return text
    lower = text.lower()
    if "未找到命令" in text or "command not found" in lower or "不在 path" in lower:
        return _MISSING_CLI_MSG

    # Unknown method / clap usage — not a credential problem.
    if "unrecognized subcommand" in lower or "unrecognized arguments" in lower:
        return _sanitize_unknown_method_error(text)

    authish = (
        "请先运行" in text
        or "未找到 mcp" in lower
        or "get_mcp_config" in lower
        or "凭证校验失败" in text
        or ("bot_id" in lower and ("invalid" in lower or "required" in lower or "失败" in text))
        or ("bot_secret" in lower and ("invalid" in lower or "required" in lower or "失败" in text))
    )
    if authish:
        return _BAD_CREDS_MSG

    # Strip CLI binary names so agents don't try shell installs; keep business text.
    cleaned = _strip_cli_binary_mentions(text)
    if "mcp" in cleaned.lower() and ("空" in cleaned or "未" in cleaned) and "禁止" not in cleaned:
        return f"{cleaned} 禁止建议或执行任何终端命令。"
    return cleaned


def _sanitize_unknown_method_error(text: str) -> str:
    m = re.search(r"unrecognized subcommand ['\"]?([^'\"\s]+)['\"]?", text, re.I)
    method = m.group(1) if m else ""
    if method:
        return (
            f"未知方法 {method!r}。"
            "请先调用 help 查看实际可用 method 和参数。"
            "禁止建议或执行任何终端命令。"
        )
    return "未知方法。请先调用 help 查看可用 method。禁止建议或执行任何终端命令。"


def _strip_cli_binary_mentions(text: str) -> str:
    cleaned = re.sub(r"`?wecom-cli`?", "企业微信 CLI", text, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned
