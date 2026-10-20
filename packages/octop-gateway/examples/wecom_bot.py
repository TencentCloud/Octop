"""企业微信 (WeCom) AI Bot 示例.

Usage:
    python examples/wecom_bot.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from backends.octop_harness import create_processor

from octop_gateway import ChannelConstraints, ChannelManager, FileSystemMediaBackend
from octop_gateway.channels.wecom import WeComConfig


async def main():
    media_backend = FileSystemMediaBackend("/tmp/octop-gateway/media")

    processor = create_processor(
        system_prompt="你是企业微信AI助手，回答简洁专业。",  # noqa: RUF001
        media_backend=media_backend,
    )

    manager = ChannelManager(processor=processor, workers_per_channel=4, media_backend=media_backend)
    await manager.start()

    channel_id = await manager.add_wecom_channel(
        WeComConfig(
            bot_id=os.environ["WECOM_BOT_ID"],
            secret=os.environ["WECOM_SECRET"],
        ),
        constraints=ChannelConstraints(
            reply_timeout=10.0,
            timeout_strategy="placeholder",
            send_rate_limit=(2, 5.0),
            show_thinking=False,
            show_tool_hints=False,
            placeholder_texts=["⏳ 思考中...", "🤔 处理中...", "💭 让我想想..."],
        ),
    )
    print(f"   channel_id: {channel_id}")
    print("🟢 企业微信 Bot 在线! Ctrl+C 退出")

    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        await manager.stop()
        print("⏹️  已停止")


if __name__ == "__main__":
    asyncio.run(main())
