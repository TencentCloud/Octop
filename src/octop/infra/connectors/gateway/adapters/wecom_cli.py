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
_CATEGORIES = ("doc", "schedule", "msg")

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
    "常用 method：create_doc、get_doc_content、edit_doc_content、"
    "smartsheet_get_sheet、smartsheet_get_records；"
    "没有 list。不确定时先调 help(category=doc)。"
)

TOOLS: list[dict[str, Any]] = [
    {
        "name": "doc",
        "description": (
            "WeCom docs / smartsheet via Octop Connectors. "
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
            "Pass method + optional args. "
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
            "Pass method + optional args. "
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
        "description": "List WeCom CLI methods for a category (doc|schedule|msg)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "doc | schedule | msg",
                },
            },
            "required": ["category"],
        },
    },
]


def list_tools() -> list[dict[str, Any]]:
    return TOOLS


def call_tool(creds: dict[str, Any], name: str, args: dict[str, Any]) -> str:
    try:
        binary = resolve_binary("wecom-cli")
        env = _prepare_env(creds)
        if name == "help":
            category = str(args.get("category") or "").strip()
            if category not in _CATEGORIES:
                raise ValueError("category must be one of: doc, schedule, msg")
            return run_cli([binary, category, "--help"], env=env)
        if name in _CATEGORIES:
            method = str(args.get("method") or "").strip()
            if not method:
                raise ValueError("method is required")
            payload = args.get("args") if isinstance(args.get("args"), dict) else {}
            return run_cli(
                [binary, name, method, json.dumps(payload, ensure_ascii=False)],
                env=env,
            )
        raise ValueError(f"unknown WeCom CLI tool: {name}")
    except ValueError as exc:
        raise ValueError(_humanize_cli_error(str(exc))) from exc


def probe_credentials(creds: dict[str, Any]) -> None:
    try:
        binary = resolve_binary("wecom-cli")
        env = _prepare_env(creds)
        config_dir = Path(env["WECOM_CLI_CONFIG_DIR"])
        if not (config_dir / "mcp_config.enc").is_file():
            raise ValueError(_BAD_CREDS_MSG)
        if read_mcp_items_count(config_dir) <= 0:
            raise ValueError("企业微信 MCP 配置为空，请确认机器人已开通 CLI 能力并核对 Bot 凭证。")
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
    env["WECOM_CLI_CONFIG_DIR"] = str(config_dir)
    return env


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
            "请先调用 help 查看可用 method；勿猜测 list 等不存在的命令。"
            "禁止建议或执行任何终端命令。"
        )
    return "未知方法。请先调用 help 查看可用 method。禁止建议或执行任何终端命令。"


def _strip_cli_binary_mentions(text: str) -> str:
    cleaned = re.sub(r"`?wecom-cli`?", "企业微信 CLI", text, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned
