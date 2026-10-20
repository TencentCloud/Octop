"""Scheduled proactive push example."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from octop_gateway import ChannelConstraints, ChannelManager
from octop_gateway.channels.qq import QQConfig
from octop_gateway.models import InboundMessage, MessageEvent


async def echo_processor(msg: InboundMessage):
    yield MessageEvent.text(f"收到: {msg.text}")
    yield MessageEvent.completed()


async def main():
    manager = ChannelManager(processor=echo_processor, workers_per_channel=2)
    await manager.start()

    await manager.add_qq_channel(
        QQConfig(
            app_id=os.environ["QQ_APP_ID"],
            token=os.environ["QQ_TOKEN"],
            secret=os.environ["QQ_SECRET"],
        ),
        constraints=ChannelConstraints(show_thinking=False),
    )

    print("🟢 Push Scheduler Bot 在线")
    print("   每 5 分钟向所有已知用户推送一条问候")

    async def scheduled_push():
        while True:
            await asyncio.sleep(300)
            users = manager.list_all_users()
            for cid, user_list in users.items():
                if user_list:
                    print(f"📤 推送到 {cid}: {len(user_list)} 个用户")
                    try:
                        await manager.push_to_all(cid, "👋 定时问候！有什么需要帮助的吗？")  # noqa: RUF001
                    except Exception as e:  # pylint: disable=broad-except
                        # Keep scheduled fan-out running when one channel adapter fails.
                        print(f"   推送失败: {e}")

    _bg_tasks: set = set()
    _task = asyncio.create_task(scheduled_push())
    _bg_tasks.add(_task)
    _task.add_done_callback(_bg_tasks.discard)

    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        await manager.stop()
        print("⏹️ 已停止")


if __name__ == "__main__":
    asyncio.run(main())
