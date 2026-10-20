"""Custom middleware shipped with octop-harness."""

from __future__ import annotations

from octop_harness.middleware.client_tool_search import ClientToolSearchMiddleware
from octop_harness.middleware.conversation_mode import ConversationModeMiddleware
from octop_harness.middleware.filesystem_guard import FilesystemGuardMiddleware
from octop_harness.middleware.media_offload import MediaOffloadMiddleware
from octop_harness.middleware.memory import MemoryMiddleware
from octop_harness.middleware.model_settings import (
    CONFIGURABLE_MAX_INPUT_TOKENS,
    CONFIGURABLE_MODEL_SETTINGS,
    ModelSettingsMiddleware,
)
from octop_harness.middleware.native_tool_search import NativeToolSearchMiddleware
from octop_harness.middleware.peer import PeerAgentMiddleware
from octop_harness.middleware.pii import detect_pii
from octop_harness.middleware.tool_search import ToolSearchMiddleware

__all__ = [
    "CONFIGURABLE_MAX_INPUT_TOKENS",
    "CONFIGURABLE_MODEL_SETTINGS",
    "ClientToolSearchMiddleware",
    "ConversationModeMiddleware",
    "FilesystemGuardMiddleware",
    "MediaOffloadMiddleware",
    "MemoryMiddleware",
    "ModelSettingsMiddleware",
    "NativeToolSearchMiddleware",
    "PeerAgentMiddleware",
    "ToolSearchMiddleware",
    "detect_pii",
]
