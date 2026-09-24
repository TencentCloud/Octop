"""Kimi Claw 通道包。

与上游其他通道（yuanbao / dingtalk / feishu …）同构：配置是 dataclass、
通道实现 ``BaseChannel`` 契约、协议细节在 ``protocol.py``。

自实现协议来自 kimi-claw-py（经真流量验证），移植说明见 ``channel.py`` 顶部。
"""

from __future__ import annotations

from harness_gateway.channels.kimi.channel import Cursor, KimiChannel, SubscribeLock
from harness_gateway.channels.kimi.config import KimiConfig

__all__ = ["Cursor", "KimiChannel", "KimiConfig", "SubscribeLock"]
