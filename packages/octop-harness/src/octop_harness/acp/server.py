"""Expose a :class:`~octop_harness.HarnessAgent` as an ACP agent over stdio."""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import uuid4

from octop_harness.backends.utils import ASYNC_DEFENSIVE_OP_ERRORS

logger = logging.getLogger(__name__)

ACP_AGENT_META_KEY = "octop.agent"
ACP_ERROR_META_KEY = "octop.error"


class _StreamTracker:
    """Convert cumulative harness text into ACP incremental deltas."""

    def __init__(self) -> None:
        self._prev_text = ""
        self._prev_thinking = ""
        self._seen_tool_ids: set[str] = set()
        self._tool_inputs: dict[str, Any] = {}

    def delta_text(self, cumulative: str) -> str:
        delta = cumulative[len(self._prev_text) :] if cumulative.startswith(self._prev_text) else cumulative
        self._prev_text = cumulative
        return delta

    def delta_thinking(self, cumulative: str) -> str:
        delta = cumulative[len(self._prev_thinking) :] if cumulative.startswith(self._prev_thinking) else cumulative
        self._prev_thinking = cumulative
        return delta

    def is_new_tool_call(self, tool_id: str) -> bool:
        if tool_id in self._seen_tool_ids:
            return False
        self._seen_tool_ids.add(tool_id)
        return True

    def tool_input_changed(self, tool_id: str, raw_input: Any) -> bool:
        if not raw_input:
            return False
        if self._tool_inputs.get(tool_id) == raw_input:
            return False
        self._tool_inputs[tool_id] = raw_input
        return True


def _extract_prompt_text(prompt: Any) -> str:
    parts: list[str] = []
    for block in prompt or []:
        text = block.get("text", "") if isinstance(block, dict) else getattr(block, "text", "")
        if text:
            parts.append(str(text))
    return "\n".join(parts)


def _tool_output_text(messages: list[Any]) -> str:
    parts: list[str] = []
    for msg in messages:
        content = msg.content if hasattr(msg, "content") else msg.get("content") if isinstance(msg, dict) else ""
        if isinstance(content, str) and content.strip():
            parts.append(content.strip())
        elif content is not None:
            parts.append(str(content))
    return "\n".join(parts)


def _chunk_to_updates(
    chunk: dict[str, Any],
    tracker: _StreamTracker,
    *,
    tool_name_buf: dict[str, str],
    tool_id_buf: dict[str, str],
) -> list[Any]:
    from acp import (
        start_tool_call,
        text_block,
        tool_content,
        update_agent_message,
        update_agent_thought,
        update_tool_call,
    )

    ctype = str(chunk.get("type") or "")
    updates: list[Any] = []

    if ctype == "token":
        text = str(chunk.get("content") or "")
        delta = tracker.delta_text(text)
        if delta:
            updates.append(update_agent_message(text_block(delta)))
    elif ctype == "reasoning":
        text = str(chunk.get("content") or "")
        delta = tracker.delta_thinking(text)
        if delta:
            updates.append(update_agent_thought(text_block(delta)))
    elif ctype == "tool_call_chunk":
        idx_key = f"_idx_{chunk.get('index', 0)}"
        name_frag = str(chunk.get("name") or "")
        tool_id = str(chunk.get("id") or "") or tool_id_buf.get(idx_key, "")
        if name_frag:
            tool_name_buf[idx_key] = tool_name_buf.get(idx_key, "") + name_frag
        if tool_id:
            tool_id_buf[idx_key] = tool_id
        args_frag = chunk.get("args")
        resolved_id = tool_id_buf.get(idx_key) or idx_key
        resolved_name = tool_name_buf.get(idx_key, "tool")
        if name_frag and tracker.is_new_tool_call(resolved_id):
            updates.append(
                start_tool_call(
                    resolved_id,
                    resolved_name,
                    status="in_progress",
                    raw_input=args_frag or None,
                ),
            )
            tracker.tool_input_changed(resolved_id, args_frag)
        elif args_frag and tracker.tool_input_changed(resolved_id, args_frag):
            updates.append(update_tool_call(resolved_id, raw_input=args_frag))
    elif ctype == "tool_result":
        messages = chunk.get("messages") or []
        output = _tool_output_text(messages)
        tool_id = next(iter(tool_id_buf.values()), uuid4().hex[:8])
        updates.append(
            update_tool_call(
                tool_id,
                status="completed",
                content=[tool_content(text_block(output or "(no output)"))],
            ),
        )
    return updates


class HarnessACPAgent:
    """ACP Agent implementation backed by a live :class:`~octop_harness.HarnessAgent`."""

    def __init__(self, harness: Any, *, agent_id: str = "") -> None:
        self._harness = harness
        self._agent_id = agent_id
        self._conn: Any = None
        self._sessions: dict[str, dict[str, Any]] = {}
        self._cancel_events: dict[str, asyncio.Event] = {}

    def on_connect(self, conn: Any) -> None:
        self._conn = conn

    async def initialize(
        self,
        protocol_version: int,
        client_capabilities: Any | None = None,
        client_info: Any | None = None,
        **kwargs: Any,
    ) -> Any:
        from acp.schema import AgentCapabilities, Implementation, InitializeResponse

        logger.info("ACP initialize: version=%s client=%s", protocol_version, client_info)
        return InitializeResponse(
            protocol_version=protocol_version,
            agent_capabilities=AgentCapabilities(load_session=True),
            agent_info=Implementation(
                name="octop",
                title="Octop Agent",
                version="0.0.0",
            ),
        )

    async def new_session(self, cwd: str, **kwargs: Any) -> Any:
        from acp.schema import NewSessionResponse

        session_id = uuid4().hex
        self._sessions[session_id] = {"cwd": cwd}
        logger.info("ACP new_session: id=%s cwd=%s", session_id, cwd)
        meta = {ACP_AGENT_META_KEY: self._agent_id} if self._agent_id else None
        return NewSessionResponse(session_id=session_id, field_meta=meta)

    async def load_session(self, cwd: str, session_id: str, **kwargs: Any) -> Any:
        from acp.schema import LoadSessionResponse

        self._sessions[session_id] = {"cwd": cwd}
        logger.info("ACP load_session: id=%s cwd=%s", session_id, cwd)
        meta = {ACP_AGENT_META_KEY: self._agent_id} if self._agent_id else None
        return LoadSessionResponse(field_meta=meta)

    async def prompt(self, prompt: Any, session_id: str, **kwargs: Any) -> Any:
        from acp.schema import PromptResponse

        text = _extract_prompt_text(prompt)
        if not text:
            return PromptResponse(stop_reason="end_turn")

        cancel_event = asyncio.Event()
        self._cancel_events[session_id] = cancel_event
        tracker = _StreamTracker()
        tool_name_buf: dict[str, str] = {}
        tool_id_buf: dict[str, str] = {}

        request = {
            "messages": [{"role": "user", "content": text}],
            "thread_id": session_id,
            "source": "acp",
            **({"agent_id": self._agent_id} if self._agent_id else {}),
        }

        try:
            async for chunk in self._harness.stream(request):
                if cancel_event.is_set():
                    logger.info("ACP prompt cancelled: session=%s", session_id)
                    break
                for update in _chunk_to_updates(
                    chunk,
                    tracker,
                    tool_name_buf=tool_name_buf,
                    tool_id_buf=tool_id_buf,
                ):
                    await self._conn.session_update(session_id=session_id, update=update)
        except ASYNC_DEFENSIVE_OP_ERRORS as exc:
            logger.exception("ACP prompt error: session=%s", session_id)
            await self._report_prompt_error(session_id, exc)
        finally:
            self._cancel_events.pop(session_id, None)

        return PromptResponse(stop_reason="end_turn")

    async def close_session(self, session_id: str, **kwargs: Any) -> Any:
        from acp.schema import CloseSessionResponse

        logger.info("ACP close_session: session=%s", session_id)
        self._sessions.pop(session_id, None)
        self._cancel_events.pop(session_id, None)
        return CloseSessionResponse()

    async def cancel(self, session_id: str, **kwargs: Any) -> None:
        logger.info("ACP cancel: session=%s", session_id)
        event = self._cancel_events.get(session_id)
        if event is not None:
            event.set()

    async def _report_prompt_error(self, session_id: str, exc: BaseException) -> None:
        from acp import text_block
        from acp.schema import AgentMessageChunk

        try:
            await self._conn.session_update(
                session_id=session_id,
                update=AgentMessageChunk(
                    session_update="agent_message_chunk",
                    content=text_block(f"Error: {exc}"),
                    field_meta={ACP_ERROR_META_KEY: True},
                ),
            )
        except ASYNC_DEFENSIVE_OP_ERRORS:
            logger.exception("ACP: failed to report prompt error (session=%s)", session_id)


def _acp_agent_cls(harness: Any, *, agent_id: str = "") -> type:
    """Concrete ACP agent class with implementation-first MRO.

    ``acp.Agent`` is a :class:`~typing.Protocol`. Putting it *before*
    :class:`HarnessACPAgent` makes Protocol stub methods (returning
    ``None``) win lookup, so ``initialize`` / ``session/new`` serialize
    as JSON ``null`` and IDE clients (Zed, Multica, …) fail to handshake.
    Implementation must come first: ``(HarnessACPAgent, Agent)``.
    """
    from acp import Agent

    class _Agent(HarnessACPAgent, Agent):  # type: ignore[misc]
        def __init__(self) -> None:
            HarnessACPAgent.__init__(self, harness, agent_id=agent_id)

    return _Agent


async def run_harness_acp_server(harness: Any, *, agent_id: str = "") -> None:
    """Run *harness* as an ACP agent on stdio until the client disconnects."""
    from acp import run_agent

    await run_agent(_acp_agent_cls(harness, agent_id=agent_id)(), use_unstable_protocol=True)


def build_harness_acp_agent(harness: Any, *, agent_id: str = "") -> Any:
    """Build an ACP :class:`acp.Agent` wrapper around *harness* (for tests)."""
    return _acp_agent_cls(harness, agent_id=agent_id)()
