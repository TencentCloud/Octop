"""Example: XiaoYi (小艺) bot."""

from __future__ import annotations

import asyncio
import logging
import os

from dotenv import load_dotenv

from octop_gateway.channels.xiaoyi import XiaoyiConfig
from octop_gateway.manager import ChannelManager

load_dotenv()
logging.basicConfig(level=logging.INFO)


async def main() -> None:
    async def processor(msg):
        from octop_gateway.models import MessageEvent, TextContent

        user_text = msg.content[0].text if msg.content else ""  # type: ignore[union-attr]
        yield MessageEvent.message([TextContent(text=f"Echo: {user_text}")])
        yield MessageEvent.completed()

    manager = ChannelManager(processor=processor)
    await manager.start()
    await manager.add_xiaoyi_channel(
        XiaoyiConfig(
            ak=os.environ["XIAOYI_AK"],
            sk=os.environ["XIAOYI_SK"],
            agent_id=os.environ["XIAOYI_AGENT_ID"],
            show_thinking=os.getenv("XIAOYI_SHOW_THINKING", "false").lower() == "true",
            show_tool_hints=os.getenv("XIAOYI_SHOW_TOOL_HINTS", "true").lower() == "true",
        )
    )
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
