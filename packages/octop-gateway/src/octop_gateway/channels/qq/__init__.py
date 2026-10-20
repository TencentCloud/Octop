"""QQ Bot channel package.

Public symbols remain importable from ``octop_gateway.channels.qq`` for
backward compatibility with the previous single-file implementation.
"""

from octop_gateway.channels.qq.channel import QQChannel, QQConfig
from octop_gateway.channels.qq.login_qr import (
    QQBotQRCodeResponse,
    QQBotQRCredentials,
    QQBotQRLogin,
    QQBotQRPollResult,
    QQBotQRWaitResult,
)

__all__ = [
    "QQBotQRCodeResponse",
    "QQBotQRCredentials",
    "QQBotQRLogin",
    "QQBotQRPollResult",
    "QQBotQRWaitResult",
    "QQChannel",
    "QQConfig",
]
