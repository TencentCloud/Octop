"""QQ Bot advanced example: image send, group messages, proactive push."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backends.octop_harness import create_processor

from octop_gateway import ChannelConstraints, ChannelManager
from octop_gateway.channels.qq import QQConfig
from octop_gateway.models import ImageContent, InboundMessage, MessageEvent


async def advanced_processor(msg: InboundMessage):
    """Advanced processor with image handling and commands."""
    text = msg.text.strip().lower()

    if text == "/image":
        yield MessageEvent.message(content=[ImageContent(url="https://picsum.photos/400/300")])
        yield MessageEvent.completed()
        return

    processor = create_processor(system_prompt="你是QQ高级助手。支持图片理解。回答简洁。")
    async for event in processor(msg):
        yield event


async def main():
    manager = ChannelManager(processor=advanced_processor, workers_per_channel=4)
    await manager.start()

    channel_id = await manager.add_qq_channel(
        QQConfig(
            app_id=os.environ["QQ_APP_ID"],
            token=os.environ["QQ_TOKEN"],
            secret=os.environ["QQ_SECRET"],
        ),
        constraints=ChannelConstraints(
            send_rate_limit=(20, 60.0),
            show_thinking=False,
            show_tool_hints=False,
            media_storage_path="./media_storage",
        ),
    )
    print(f"   channel_id: {channel_id}")
    print("🟢 QQ Advanced Bot 在线! /image 发送示例图片 Ctrl+C 退出")

    async def show_users():
        while True:
            await asyncio.sleep(60)
            users = manager.list_subjects(channel_id)
            if users:
                print(f"📋 已知用户 ({len(users)}): {[u.user_id[:8] for u in users]}")

    _bg_tasks: set = set()
    _task = asyncio.create_task(show_users())
    _bg_tasks.add(_task)
    _task.add_done_callback(_bg_tasks.discard)

    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        users = manager.list_subjects(channel_id)
        print(f"\n⏹️ 停止中... (通知 {len(users)} 个用户)")
        await manager.stop()


if __name__ == "__main__":
    asyncio.run(main())
