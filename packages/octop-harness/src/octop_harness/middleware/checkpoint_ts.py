"""Stamp ``checkpoint_ts`` onto messages at write time.

Open-chat latency used to be dominated by ``graph.aget_state_history`` walks
just to recover first-seen times for history display. Instead, stamp
``additional_kwargs["checkpoint_ts"]`` (wall-clock epoch ms) onto new
messages in ``before_model`` / ``after_model``. Once persisted in the
checkpointer, ``HarnessAgent.aget_history`` returns those stamps directly.

Messages written before this middleware was enabled simply have no stamp —
there is no read-path backfill.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import BaseMessage, HumanMessage

from octop_harness.backends.utils import DEFENSIVE_OP_ERRORS
from octop_harness.messages import CHECKPOINT_TS_KEY

logger = logging.getLogger(__name__)


def _extract_messages(state: Any) -> list[BaseMessage]:
    if state is None:
        return []
    if isinstance(state, dict):
        return list(state.get("messages", []) or [])
    return list(getattr(state, "messages", []) or [])


def _index_of_last_human(messages: list[BaseMessage]) -> int:
    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], HumanMessage):
            return i
    return len(messages)


def stamp_missing_checkpoint_ts(
    messages: list[BaseMessage],
    *,
    start: int = 0,
    now_ms: int | None = None,
) -> list[BaseMessage]:
    """Return only the messages in ``messages[start:]`` that needed a stamp.

    Returning the changed subset keeps ``add_messages`` updates small — we do
    not rewrite the whole transcript on every model call.

    Already-stamped messages (including older unstamped history left behind
    ``start``) are never rewritten to ``now``.
    """
    ts_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    start = max(start, 0)
    stamped: list[BaseMessage] = []
    for i in range(start, len(messages)):
        msg = messages[i]
        kwargs = getattr(msg, "additional_kwargs", None) or {}
        if not isinstance(kwargs, dict):
            kwargs = {}
        if CHECKPOINT_TS_KEY in kwargs:
            continue
        new_kwargs = {**kwargs, CHECKPOINT_TS_KEY: ts_ms}
        stamped.append(msg.model_copy(update={"additional_kwargs": new_kwargs}))
    return stamped


class CheckpointTsMiddleware(AgentMiddleware[Any, Any]):
    """Persist wall-clock timestamps on newly appended messages.

    Both hooks start from the trailing :class:`HumanMessage` and only stamp
    messages that still lack ``checkpoint_ts``. That avoids a process-local
    length cursor while still refusing to backfill older unstamped history
    with ``now``.
    """

    def before_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        try:
            messages = _extract_messages(state)
            if not messages:
                return None
            # New user turn is typically the trailing HumanMessage (and anything
            # after it). Never backfill older unstamped history with "now".
            stamped = stamp_missing_checkpoint_ts(
                messages,
                start=_index_of_last_human(messages),
            )
            return {"messages": stamped} if stamped else None
        except DEFENSIVE_OP_ERRORS:  # pragma: no cover - defensive
            logger.warning("CheckpointTsMiddleware before_model failed", exc_info=True)
            return None

    async def abefore_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        return self.before_model(state, runtime)

    def after_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        try:
            messages = _extract_messages(state)
            if not messages:
                return None
            # Same trailing-human window as before_model: user is already stamped,
            # so only new AI / tool messages missing the key are rewritten.
            stamped = stamp_missing_checkpoint_ts(
                messages,
                start=_index_of_last_human(messages),
            )
            return {"messages": stamped} if stamped else None
        except DEFENSIVE_OP_ERRORS:  # pragma: no cover - defensive
            logger.warning("CheckpointTsMiddleware after_model failed", exc_info=True)
            return None

    async def aafter_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        return self.after_model(state, runtime)
