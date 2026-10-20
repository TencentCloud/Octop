"""Configuration models for the Tencent Yuanbao channel."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import ClassVar

from octop_gateway.channel import ChannelConfig
from octop_gateway.channels.yuanbao.constants import (
    DEFAULT_API_DOMAIN,
    DEFAULT_WS_URL,
    HERMES_INSTANCE_ID,
)
from octop_gateway.channels.yuanbao.utils import _normalize_http_origin, _normalize_ws_url


@dataclass
class _YuanbaoToken:
    token: str
    bot_id: str
    source: str
    expires_at: float
    duration: int


@dataclass
class YuanbaoConfig(ChannelConfig):
    """Configuration for Tencent Yuanbao channel.

    The current Yuanbao bot binding flow returns ``app_key`` / ``app_secret``.
    The gateway uses them to call ``/api/v5/robotLogic/sign-token`` and then
    binds the returned token over the configured WebSocket URL.
    """

    app_key: str = ""
    app_secret: str = ""
    api_domain: str = ""
    ws_url: str = ""
    route_env: str = ""

    # Legacy/compat fields. They are retained so old stored configs can still
    # be loaded, but live Yuanbao connections use app_key/app_secret.
    api_base: str = ""
    token: str = ""
    bot_id: str = ""
    identifier: str = ""
    source: str = ""
    extra: dict[str, object] = field(default_factory=dict)

    app_version: str = "1.0.0"
    app_operation_system: str = ""
    operation_system: str = ""
    bot_version: str = "1.0.0"
    instance_id: str = str(HERMES_INSTANCE_ID)
    request_timeout: float = 30.0
    heartbeat_interval: float = 30.0
    connect_timeout: float = 15.0
    probe_mode: str = "full"

    required_credentials: ClassVar[tuple[str, ...]] = ("app_key", "app_secret")
    field_aliases: ClassVar[dict[str, str]] = {
        "appId": "app_key",
        "appKey": "app_key",
        "client_id": "app_key",
        "appSecret": "app_secret",
        "client_secret": "app_secret",
        "api_base": "api_domain",
        "apiBase": "api_domain",
        "apiDomain": "api_domain",
        "websocket_url": "ws_url",
        "webSocketURL": "ws_url",
        "wsUrl": "ws_url",
        "routeEnv": "route_env",
        "probeMode": "probe_mode",
        "botId": "bot_id",
        "identifier": "bot_id",
        "operationSystem": "app_operation_system",
        "appOperationSystem": "app_operation_system",
    }

    def __post_init__(self) -> None:
        self.api_domain = _normalize_http_origin(self.api_domain or self.api_base or DEFAULT_API_DOMAIN)
        self.api_base = self.api_domain
        self.ws_url = _normalize_ws_url(self.ws_url or DEFAULT_WS_URL)
        selected_operation_system = self.app_operation_system or self.operation_system or sys.platform
        self.app_operation_system = selected_operation_system
        self.operation_system = selected_operation_system
        self.instance_id = str(self.instance_id or HERMES_INSTANCE_ID)
        if not self.bot_id and self.identifier:
            self.bot_id = self.identifier
        if not self.identifier and self.bot_id:
            self.identifier = self.bot_id

    def missing_credentials(self) -> list[str]:
        missing: list[str] = []
        if not self.app_key:
            missing.append("app_key")
        if not self.app_secret:
            missing.append("app_secret")
        return missing
