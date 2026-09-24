"""Offload oversized ``octop_ui`` tool payloads onto ``ToolMessage.artifact``.

Plugin tools return one JSON envelope string (``octop_ui`` hint + ``data`` +
``text``) that serves both the model and the dashboard. For chatty tools like
bilibili-anime the ``data`` payload can reach tens of KB, which then rides the
model context on every subsequent turn.

Model-request converters only serialize ``message.content`` — ``artifact`` is
kept on the message (history, WS frames) but never sent to the model. So for
large envelopes we move ``data`` to ``artifact`` here, leaving the model a slim
envelope with ``data_ref: "artifact"``. The dashboard resolves the reference
when rendering. Design: ``docs/octop-ui-payload-offload.md``.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

logger = logging.getLogger(__name__)

_OFFLOAD_MIN_CHARS = 4000
# Tool results embedding workspace media references must stay intact: media
# extraction (tool_media) and thread-artifact path scans read ``content``.
_FILE_URL_GUARD = "file://"


class OctopUiOffloadMiddleware(AgentMiddleware[Any, Any]):
    """Move oversized ``octop_ui`` ``data`` payloads to ``ToolMessage.artifact``."""

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        result = handler(request)
        self._try_offload(result)
        return result

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        result = await handler(request)
        self._try_offload(result)
        return result

    def _try_offload(self, result: ToolMessage | Command[Any]) -> None:
        try:
            self._offload(result)
        except Exception:
            # Offload must never break a tool call.
            logger.warning("octop_ui offload failed", exc_info=True)

    def _offload(self, result: ToolMessage | Command[Any]) -> None:
        if not isinstance(result, ToolMessage):
            return
        content = result.content
        if not isinstance(content, str) or len(content) < _OFFLOAD_MIN_CHARS:
            return
        if '"octop_ui"' not in content or _FILE_URL_GUARD in content:
            return
        try:
            envelope = json.loads(content)
        except (ValueError, TypeError):
            return
        if not isinstance(envelope, dict):
            return
        hint = envelope.get("octop_ui")
        if not isinstance(hint, dict) or not str(hint.get("renderer") or "").strip():
            return
        data = envelope.pop("data", None)
        if not data:
            return
        envelope["data_ref"] = "artifact"
        result.content = json.dumps(envelope, ensure_ascii=False)
        result.artifact = data


__all__ = ["OctopUiOffloadMiddleware"]
