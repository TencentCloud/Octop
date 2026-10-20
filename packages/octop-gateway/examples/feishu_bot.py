"""飞书 (Feishu/Lark) AI Bot 示例.

Usage:
    python examples/feishu_bot.py
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from backends.octop_harness import create_processor

from octop_gateway import ChannelManager, FileSystemMediaBackend
from octop_gateway.channels.feishu import FeishuConfig


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    media_backend = FileSystemMediaBackend("/tmp/octop-gateway/media")

    processor = create_processor(
        system_prompt="你是飞书AI助手，回答简洁有用。",  # noqa: RUF001
        streaming=False,
        media_backend=media_backend,
    )

    manager = ChannelManager(processor=processor, workers_per_channel=4, media_backend=media_backend)
    await manager.start()

    channel_id = await manager.add_feishu_channel(
        FeishuConfig(
            app_id=os.environ["FEISHU_APP_ID"],
            app_secret=os.environ["FEISHU_APP_SECRET"],
        )
    )
    print(f"   channel_id: {channel_id}")
    print("🟢 飞书 Bot 在线! Ctrl+C 退出")

    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        await manager.stop()
        print("⏹️  已停止")


if __name__ == "__main__":
    asyncio.run(main())
