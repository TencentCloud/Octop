"""Echo tool plugin for tests."""

from __future__ import annotations

import json

from octop_harness.plugins import PluginContext, get_tool_config


async def echo_message(message: str) -> str:
    cfg = get_tool_config("echo_message") or {}
    prefix = str(cfg.get("prefix") or "")
    return json.dumps({"echo": f"{prefix}{message}"})


def setup(ctx: PluginContext) -> None:
    ctx.tool(
        "echo_message",
        echo_message,
        description="Echo a message back as JSON",
        config_fields=[
            {"name": "prefix", "type": "text", "required": False},
        ],
    )
