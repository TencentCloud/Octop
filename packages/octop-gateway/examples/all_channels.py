"""全通道 AI Bot 示例 — 所有通道同时运行.

Usage:
    python examples/all_channels.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from backends.octop_harness import create_processor

from octop_gateway import ChannelConstraints, ChannelManager, FileSystemMediaBackend
from octop_gateway.channels.feishu import FeishuConfig
from octop_gateway.channels.qq import QQConfig
from octop_gateway.channels.wecom import WeComConfig
from octop_gateway.channels.weixin import WeixinAccountConfig, WeixinConfig


async def main():
    media_backend = FileSystemMediaBackend("/tmp/octop-gateway/media")

    processor = create_processor(
        system_prompt="你是一个友好的AI助手，支持连续对话，回答简洁有用。",  # noqa: RUF001
        media_backend=media_backend,
    )

    manager = ChannelManager(processor=processor, workers_per_channel=4, media_backend=media_backend)
    await manager.start()

    wecom_id = await manager.add_wecom_channel(
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
        ),
    )

    qq_id = await manager.add_qq_channel(
        QQConfig(
            app_id=os.environ["QQ_APP_ID"],
            token=os.environ["QQ_TOKEN"],
            secret=os.environ["QQ_SECRET"],
        ),
        constraints=ChannelConstraints(show_thinking=False, show_tool_hints=False),
    )

    feishu_id = await manager.add_feishu_channel(
        FeishuConfig(
            app_id=os.environ["FEISHU_APP_ID"],
            app_secret=os.environ["FEISHU_APP_SECRET"],
        )
    )

    weixin_id = await manager.add_weixin_channel(
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
            show_thinking=False,
        ),
    )

    print("=" * 60)
    print("🟢 全通道 AI Bot 在线!")
    print(f"   wecom:  {wecom_id}")
    print(f"   qq:     {qq_id}")
    print(f"   feishu: {feishu_id}")
    print(f"   weixin: {weixin_id}")
    print("   Ctrl+C 退出")
    print("=" * 60)

    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        await manager.stop()
        print("\n⏹️  全部停止")


if __name__ == "__main__":
    asyncio.run(main())
