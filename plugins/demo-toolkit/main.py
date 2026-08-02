"""Demo Toolkit — sample tool plugin (kind=tool).

How to write an Octop plugin (copy this file as a template):
  1. This directory must contain plugin.yaml (id / version / name / kind / entry).
  2. The entry file (main.py here) must define setup(ctx: PluginContext).
  3. Register callable tools with ctx.tool(...) inside setup.
  4. Tool functions may be async; parameters become the agent call schema.
  5. Read per-agent tool settings with get_tool_config("tool_name").
     Fields come from config_fields and are edited in Dashboard → Tool management.
"""

from __future__ import annotations

from datetime import UTC, datetime

from harness_agent.plugins import PluginContext, get_tool_config


async def get_current_time(tz: str = "UTC") -> str:
    """Return the current time in the given timezone (e.g. Asia/Shanghai, UTC)."""
    try:
        from zoneinfo import ZoneInfo

        zone = ZoneInfo(tz)
    except Exception:
        zone = UTC
    return datetime.now(zone).strftime("%Y-%m-%d %H:%M:%S %Z")


async def text_stats(text: str) -> str:
    """Count characters and whitespace-separated words in text."""
    chars = len(text)
    words = len(text.split())
    return f"characters: {chars}\nwords: {words}"


async def echo_prefix(message: str) -> str:
    """Echo a message with an optional admin-configured prefix.

    Demonstrates config_fields + get_tool_config: the prefix is not an agent
    argument; it comes from each agent's tool configuration.
    """
    cfg = get_tool_config("echo_prefix") or {}
    prefix = str(cfg.get("prefix") or "")
    return f"{prefix}{message}"


def setup(ctx: PluginContext) -> None:
    ctx.tool(
        "get_current_time",
        get_current_time,
        description="Get the current time in a given timezone",
    )
    ctx.tool(
        "text_stats",
        text_stats,
        description="Count characters and words in text",
    )
    ctx.tool(
        "echo_prefix",
        echo_prefix,
        description="Echo a message with a configurable prefix",
        config_fields=[
            {"name": "prefix", "type": "text", "required": False},
        ],
    )
