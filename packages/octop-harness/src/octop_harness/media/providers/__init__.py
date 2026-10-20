"""Built-in media generation provider adapters."""

from octop_harness.media.providers.dashscope import DashScopeMediaProvider
from octop_harness.media.providers.minimax import MiniMaxMediaProvider
from octop_harness.media.providers.volcengine import VolcengineMediaProvider

__all__ = ["DashScopeMediaProvider", "MiniMaxMediaProvider", "VolcengineMediaProvider"]
