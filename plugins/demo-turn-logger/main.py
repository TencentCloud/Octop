"""Demo Turn Logger — sample hook plugin (kind=hook).

Hook plugins register a LangChain AgentMiddleware via ctx.middleware(...).
Octop attaches middleware from globally enabled plugins to the agent chain
(lower priority runs earlier).

This demo only emits observability logs and does not mutate messages or the
system prompt — use it as a hook template.
"""

from __future__ import annotations

import logging
from typing import Any

from harness_agent.plugins import AgentMiddleware, PluginContext

logger = logging.getLogger("octop.plugins.demo_turn_logger")


def _message_count(state: Any) -> int:
    if state is None:
        return 0
    if isinstance(state, dict):
        messages = state.get("messages") or []
    else:
        messages = getattr(state, "messages", None) or []
    try:
        return len(messages)
    except TypeError:
        return 0


class TurnLoggerMiddleware(AgentMiddleware[Any, Any]):
    """Log before/after each model call without mutating agent state."""

    def before_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        logger.info(
            "demo-turn-logger before_model messages=%s",
            _message_count(state),
        )
        return None

    async def abefore_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        return self.before_model(state, runtime)

    def after_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        logger.info(
            "demo-turn-logger after_model messages=%s",
            _message_count(state),
        )
        return None

    async def aafter_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        return self.after_model(state, runtime)


def setup(ctx: PluginContext) -> None:
    # Lower priority runs earlier; 100 is a common default.
    ctx.middleware(TurnLoggerMiddleware(), priority=100)
