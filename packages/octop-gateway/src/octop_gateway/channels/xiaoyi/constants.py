"""XiaoYi channel constants."""

from __future__ import annotations

DEFAULT_WS_URL = "wss://hag.cloud.huawei.com/openclaw/v1/ws/link"
DEFAULT_WS_URL_BACKUP = "wss://116.63.174.231/openclaw/v1/ws/link"

HEARTBEAT_INTERVAL = 30
RECONNECT_DELAYS = [1, 2, 5, 10, 30, 60]
MAX_RECONNECT_ATTEMPTS = 50
CONNECTION_TIMEOUT = 30
TEXT_CHUNK_LIMIT = 4000
