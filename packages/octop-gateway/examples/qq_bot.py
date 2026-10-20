"""QQ Bot 示例.

Usage:
    python examples/qq_bot.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from backends.octop_harness import create_processor

from octop_gateway import ChannelConstraints, ChannelManager, FileSystemMediaBackend
from octop_gateway.channels.qq import QQConfig


async def main():
    media_backend = FileSystemMediaBackend("/")

    processor = create_processor(
        system_prompt="你是QQ AI助手，回答轻松有趣。",  # noqa: RUF001
        streaming=False,
        media_backend=media_backend,
    )

    manager = ChannelManager(processor=processor, workers_per_channel=4, media_backend=media_backend)
    await manager.start()

    channel_id = await manager.add_qq_channel(
        QQConfig(
            app_id=os.environ["QQ_APP_ID"],
            token=os.environ["QQ_TOKEN"],
            secret=os.environ["QQ_SECRET"],
        ),
        constraints=ChannelConstraints(
            send_rate_limit=(20, 60.0),
            show_thinking=True,
            show_tool_hints=True,
        ),
    )
    print(f"   channel_id: {channel_id}")
    print("🟢 QQ Bot 在线! Ctrl+C 退出")

    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        await manager.stop()
        print("⏹️  已停止")


if __name__ == "__main__":
    asyncio.run(main())
