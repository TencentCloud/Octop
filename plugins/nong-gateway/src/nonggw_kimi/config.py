"""Configuration for the Kimi Claw channel.

凭据是一把 bot token（来自 Kimi 开放平台的 Claw 应用）。游标/订阅锁/原始帧
都落在 ``state_dir`` 下面，这个目录必须是本通道**独占**的（多 bot 就配多个
通道实例，各自一个目录），因为订阅锁与游标都按目录隔离。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from harness_gateway.channel import ChannelConfig


@dataclass
class KimiConfig(ChannelConfig):
    """Kimi Claw 通道配置。

    凭据：``token``（bot token，必填）。
    ``state_dir``：游标 ``cursor.json``、订阅锁 ``subscribe.lock``、原始帧 ``raw/``
    的家。同一 bot 的所有消费者必须指向同一个 state_dir（锁才锁得住），不同 bot 必须分开。
    """

    token: str = ""
    kimiapi_host: str = ""
    state_dir: str = ""

    # 协议版本头（官方 Claw 客户端伪装值，来自 kcp 实测）
    claw_version: str = "0.27.1"
    openclaw_version: str = "2026.4.14"

    # 订阅锁被占时最多等多久（秒）；0 = 立刻放弃（另一个消费者在跑就明说退出）
    lock_wait_sec: float = 0.0
    # 原始帧留证上限（MB）；0 = 关闭。ping 帧与失败风暴都不会刷爆磁盘（轮转 + 只留一份）
    raw_dump_mb: int = 0
    # 取正文失败后的补取窗口大小
    fetch_page_size: int = 20

    required_credentials: ClassVar[tuple[str, ...]] = ("token",)
    field_aliases: ClassVar[dict[str, str]] = {
        "bot_token": "token",
        "botToken": "token",
        "botTokenFile": "token_file",
        "kimiapiHost": "kimiapi_host",
        "stateDir": "state_dir",
        "lockWaitSec": "lock_wait_sec",
        "rawDumpMb": "raw_dump_mb",
        "rawMaxMb": "raw_dump_mb",
        "fetchPageSize": "fetch_page_size",
    }

    def missing_credentials(self) -> list[str]:
        return [] if self.token else ["token"]
