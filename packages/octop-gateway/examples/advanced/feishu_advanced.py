"""Feishu Bot advanced example: image/file send, group messages, proactive push."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backends.octop_harness import create_processor

from octop_gateway import ChannelConstraints, ChannelManager
from octop_gateway.channels.feishu import FeishuConfig
from octop_gateway.models import InboundMessage, MessageEvent


async def advanced_processor(msg: InboundMessage):
    """Advanced processor with commands and multimodal support."""
    text = msg.text.strip()

    if text == "/help":
        yield MessageEvent.text("**飞书高级 Bot 命令:**\n- /help — 显示帮助\n- 发送图片 — AI 描述图片内容\n")
        yield MessageEvent.completed()
        return

    processor = create_processor(system_prompt="你是飞书AI助手，支持markdown格式回答。如果收到图片请描述。")  # noqa: RUF001
    async for event in processor(msg):
        yield event


async def main():
    manager = ChannelManager(processor=advanced_processor, workers_per_channel=4)
    await manager.start()

    channel_id = await manager.add_feishu_channel(
        FeishuConfig(
            app_id=os.environ["FEISHU_APP_ID"],
            app_secret=os.environ["FEISHU_APP_SECRET"],
        ),
        constraints=ChannelConstraints(
            show_thinking=False,
            show_tool_hints=False,
            media_storage_path="./media_storage",
        ),
    )
    print(f"   channel_id: {channel_id}")
    print("🟢 飞书 Advanced Bot 在线! Ctrl+C 退出")

    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        await manager.stop()
        print("⏹️ 已停止")


if __name__ == "__main__":
    asyncio.run(main())
