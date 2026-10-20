import json

from octop_harness.plugins import PluginContext, get_tool_config


async def echo_message(message: str) -> str:
    cfg = get_tool_config("echo_message") or {}
    return json.dumps({"echo": f"{cfg.get('prefix', '')}{message}"})


def setup(ctx: PluginContext) -> None:
    ctx.tool("echo_message", echo_message, description="echo")
