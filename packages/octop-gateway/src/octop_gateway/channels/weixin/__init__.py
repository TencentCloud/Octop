"""WeChat (iLink Bot) channel package.

Public API — all symbols previously importable from
``octop_gateway.channels.weixin`` remain available here for
backward compatibility.
"""

from octop_gateway.channels.weixin.channel import (
    WeixinAccountConfig,
    WeixinChannel,
    WeixinConfig,
)
from octop_gateway.channels.weixin.login_qr import (
    QRCodeResponse,
    WeixinQRLogin,
    WeixinQrWaitResult,
)

__all__ = [
    "QRCodeResponse",
    "WeixinAccountConfig",
    "WeixinChannel",
    "WeixinConfig",
    "WeixinQRLogin",
    "WeixinQrWaitResult",
]
