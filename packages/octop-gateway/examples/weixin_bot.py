"""微信 (WeChat iLink) AI Bot 示例.

Usage:
    python examples/weixin_bot.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from backends.octop_harness import create_processor

from octop_gateway import ChannelConstraints, ChannelManager, FileSystemMediaBackend
from octop_gateway.channels.weixin import WeixinAccountConfig, WeixinConfig


async def main():
    media_backend = FileSystemMediaBackend("/tmp/octop-gateway/media")

    processor = create_processor(
        system_prompt="你是微信AI助手，回答友好简洁。",  # noqa: RUF001
        streaming=False,
        media_backend=media_backend,
    )

    manager = ChannelManager(processor=processor, workers_per_channel=4, media_backend=media_backend)
    await manager.start()

    channel_id = await manager.add_weixin_channel(
        WeixinConfig(
            accounts=[
                WeixinAccountConfig(
                    account_id=os.environ["WEIXIN_ACCOUNT_ID"],
                    token=os.environ["WEIXIN_TOKEN"],
                    base_url=os.environ.get("WEIXIN_BASE_URL", "https://ilinkai.weixin.qq.com"),
                ),
            ]
        ),
        constraints=ChannelConstraints(
            reply_timeout=5.0,
            timeout_strategy="placeholder",
            send_rate_limit=(5, 60.0),
            typing_keepalive_interval=5.0,
            show_thinking=False,
            show_tool_hints=False,
            placeholder_texts=["⏳ 思考中...", "🤔 让我想想...", "💭 正在处理..."],
        ),
    )
    print(f"   channel_id: {channel_id}")
    print("🟢 微信 iLink Bot 在线! Ctrl+C 退出")

    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        await manager.stop()
        print("⏹️  已停止")


if __name__ == "__main__":
    asyncio.run(main())
