"""Project harness stream chunks into harness-gateway MessageEvent objects."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from harness_gateway.media import MediaBackend
from harness_gateway.models import MessageEvent

from octop.i18n import channel_tool_hint_end, channel_tool_hint_start, tool_display_name
from octop.infra.gateway.hitl.format import format_hitl_card
from octop.infra.gateway.media.tool_media import media_events_from_tool_result
from octop.infra.gateway.process.agent_resolve import harness_workspace_for_agent
from octop.infra.gateway.process.usage_record import UsageTracker
from octop.infra.utils.locale import DEFAULT_LOCALE, Locale, normalize_locale

if TYPE_CHECKING:
    from octop.infra.agents.manager import AgentManager
    from octop.infra.gateway.hitl.coordinator import HitlChannelCoordinator, HitlStreamContext
    from octop.infra.gateway.questions.coordinator import UserQuestionCoordinator


@dataclass
class StreamProjectionState:
    hitl_paused: bool = False
    hitl_pending_id: str | None = None


@dataclass
class _ToolProjectionState:
    current_node: str | None = None
    tool_name_buf: dict[str, str] = field(default_factory=dict)
    tool_started: set[str] = field(default_factory=set)
    active_tool_idx: str | None = None
    # True once we've seen at least one tool_call_chunk in this stream.
    # Media events are only emitted when a tool was actually called this turn;
    # historical tool results (replayed via PatchToolCallsMiddleware / Overwrite)
    # must not trigger re-sends.
    saw_tool_call: bool = False
    # Track tool_call_ids whose media we've already emitted to prevent
    # re-emission when PatchToolCallsMiddleware emits Overwrite(full_history).
    emitted_media_ids: set[str] = field(default_factory=set)


def _dedup_tool_result_messages(
    chunk: dict[str, Any],
    emitted_ids: set[str],
) -> dict[str, Any] | None:
    """Filter ``tool_result`` messages to those not yet emitted this stream.

    When ``PatchToolCallsMiddleware`` returns ``Overwrite(full_history)`` the
    ``tool_result`` chunk contains every ToolMessage ever (including ones from
    previous turns).  We keep only messages whose ``tool_call_id`` hasn't been
    seen yet in this stream, then record the new ones.

    Returns the (possibly trimmed) chunk, or ``None`` when all messages are
    duplicates.
    """
    messages = chunk.get("messages")
    if not isinstance(messages, list):
        return chunk

    new_messages = []
    for msg in messages:
        msg_id = getattr(msg, "tool_call_id", None) or (
            msg.get("tool_call_id") if isinstance(msg, dict) else None
        )
        if msg_id and msg_id in emitted_ids:
            continue
        new_messages.append(msg)
        if msg_id:
            emitted_ids.add(msg_id)

    if not new_messages:
        return None
    if len(new_messages) == len(messages):
        return chunk
    return {**chunk, "messages": new_messages}


def enrich_tool_stream_chunk(chunk: dict[str, Any], locale: str | Locale) -> dict[str, Any]:
    """Add ``display_name`` to harness tool stream chunks for dashboard clients."""
    if chunk.get("type") not in ("tool_call_chunk", "tool_result"):
        return chunk
    name = chunk.get("name")
    if not isinstance(name, str) or not name:
        return chunk
    out = dict(chunk)
    out["display_name"] = tool_display_name(name, locale)
    return out


async def _project_chunks(
    chunks: AsyncIterator[dict[str, Any]],
    *,
    agent_manager: AgentManager,
    agent_id: str,
    locale: str | Locale,
    usage_tracker: UsageTracker | None,
    projection_state: StreamProjectionState | None,
    hitl_coordinator: HitlChannelCoordinator | None,
    hitl_ctx: HitlStreamContext | None,
    question_coordinator: UserQuestionCoordinator | None,
) -> AsyncIterator[MessageEvent]:
    loc = normalize_locale(str(locale))
    tool_state = _ToolProjectionState()
    harness_workspace = harness_workspace_for_agent(agent_manager, agent_id)

    def _tool_label(raw: str) -> str:
        return tool_display_name(raw, loc)

    def _tool_start(raw: str) -> MessageEvent:
        label = _tool_label(raw)
        return MessageEvent.tool_start(
            label,
            tool_hint_text=channel_tool_hint_start(label, loc),
        )

    def _tool_end(raw: str) -> MessageEvent:
        label = _tool_label(raw)
        return MessageEvent.tool_end(
            label,
            tool_hint_text=channel_tool_hint_end(label, loc),
        )

    async for chunk in chunks:
        if usage_tracker is not None:
            usage_tracker.observe(chunk)
        ctype: str = chunk.get("type", "")
        node: str | None = chunk.get("node")

        if ctype == "token":
            if tool_state.current_node is not None and node != tool_state.current_node:
                yield MessageEvent.flush()
            tool_state.current_node = node
            content = chunk.get("content") or ""
            if content:
                yield MessageEvent.delta(content)

        elif ctype == "reasoning":
            content = chunk.get("content") or ""
            if content:
                yield MessageEvent.thinking_delta(content)

        elif ctype == "tool_call_chunk":
            tool_state.saw_tool_call = True
            idx_key = f"_idx_{chunk.get('index', 0)}"
            tool_state.active_tool_idx = idx_key

            name_frag: str = chunk.get("name") or ""
            args_frag: str = chunk.get("args") or ""

            if name_frag:
                tool_state.tool_name_buf[idx_key] = (
                    tool_state.tool_name_buf.get(idx_key, "") + name_frag
                )

            if (
                args_frag
                and idx_key not in tool_state.tool_started
                and tool_state.tool_name_buf.get(idx_key)
            ):
                tool_state.tool_started.add(idx_key)
                yield _tool_start(tool_state.tool_name_buf[idx_key])

        elif ctype == "tool_result":
            final_name = (
                tool_state.tool_name_buf.get(tool_state.active_tool_idx or "", "") or "tool"
            )
            if tool_state.active_tool_idx is not None:
                idx = tool_state.active_tool_idx
                if idx not in tool_state.tool_started:
                    tool_state.tool_started.add(idx)
                    yield _tool_start(final_name)
                yield _tool_end(final_name)
                tool_state.tool_name_buf.pop(idx, None)
                tool_state.tool_started.discard(idx)
                tool_state.active_tool_idx = None
            if harness_workspace is not None and tool_state.saw_tool_call:
                chunk_for_media = _dedup_tool_result_messages(chunk, tool_state.emitted_media_ids)
                if chunk_for_media is not None:
                    async for media_event in media_events_from_tool_result(
                        chunk_for_media,
                        workspace=harness_workspace,
                    ):
                        yield media_event
            tool_state.current_node = node

        elif ctype == "hitl_required":
            request = chunk.get("request")
            if not isinstance(request, dict):
                request = {}
            from octop.infra.gateway.questions.coordinator import is_user_question_request

            if (
                is_user_question_request(request)
                and question_coordinator is not None
                and hitl_ctx is not None
            ):
                question_record = question_coordinator.register_from_request(
                    request,
                    thread_id=hitl_ctx.thread_id,
                    agent_id=hitl_ctx.agent_id,
                    user_id=hitl_ctx.user_id,
                    session_key=hitl_ctx.session_key,
                    channel_type=hitl_ctx.channel_type,
                )
                if projection_state is not None:
                    projection_state.hitl_paused = True
                yield MessageEvent.text(
                    question_coordinator.channel_card(question_record, str(loc))
                )
            elif hitl_coordinator is not None and hitl_ctx is not None:
                hitl_record = hitl_coordinator.register_from_request(request, ctx=hitl_ctx)
                card = format_hitl_card(
                    hitl_record.action_requests,
                    pending_id=hitl_record.pending_id,
                    locale=loc,
                )
                if projection_state is not None:
                    projection_state.hitl_paused = True
                    projection_state.hitl_pending_id = hitl_record.pending_id
                yield MessageEvent.text(card)
            return

        elif ctype == "state_update":
            if tool_state.current_node is not None and node != tool_state.current_node:
                yield MessageEvent.flush()
            tool_state.current_node = node


async def project_stream(
    agent_manager: AgentManager,
    agent_id: str,
    request: dict[str, Any],
    *,
    media_backend: MediaBackend | None = None,
    usage_tracker: UsageTracker | None = None,
    locale: str | Locale = DEFAULT_LOCALE,
    projection_state: StreamProjectionState | None = None,
    hitl_coordinator: HitlChannelCoordinator | None = None,
    hitl_ctx: HitlStreamContext | None = None,
    question_coordinator: UserQuestionCoordinator | None = None,
) -> AsyncIterator[MessageEvent]:
    del media_backend  # IM tool media uses agent.backend directly
    async for ev in _project_chunks(
        agent_manager.stream(agent_id, request),
        agent_manager=agent_manager,
        agent_id=agent_id,
        locale=locale,
        usage_tracker=usage_tracker,
        projection_state=projection_state,
        hitl_coordinator=hitl_coordinator,
        hitl_ctx=hitl_ctx,
        question_coordinator=question_coordinator,
    ):
        yield ev


async def project_resume_stream(
    agent_manager: AgentManager,
    agent_id: str,
    thread_id: str,
    decisions: list[dict[str, Any]],
    *,
    usage_tracker: UsageTracker | None = None,
    locale: str | Locale = DEFAULT_LOCALE,
    projection_state: StreamProjectionState | None = None,
    hitl_coordinator: HitlChannelCoordinator | None = None,
    hitl_ctx: HitlStreamContext | None = None,
    question_coordinator: UserQuestionCoordinator | None = None,
) -> AsyncIterator[MessageEvent]:
    async for ev in _project_chunks(
        agent_manager.resume_hitl(agent_id, thread_id, decisions),
        agent_manager=agent_manager,
        agent_id=agent_id,
        locale=locale,
        usage_tracker=usage_tracker,
        projection_state=projection_state,
        hitl_coordinator=hitl_coordinator,
        hitl_ctx=hitl_ctx,
        question_coordinator=question_coordinator,
    ):
        yield ev
