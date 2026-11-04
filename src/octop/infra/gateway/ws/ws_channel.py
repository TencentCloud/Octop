"""Virtual IM channel that delivers Dashboard chat over WebSocket."""

from __future__ import annotations

import base64
import logging
from typing import Any

from octop_gateway.channel import BaseChannel, MessageProcessor
from octop_gateway.constraints import ChannelConstraints
from octop_gateway.models import (
    AudioContent,
    ChannelSubject,
    ContentPart,
    FileContent,
    ImageContent,
    InboundMessage,
    TextContent,
    VideoContent,
)
from octop_gateway.utils import close_event_stream

from octop.i18n.domains.stream import format_stream_error
from octop.infra.gateway.media.attachment_hints import (
    inbound_attachments_from_parts,
    is_vision_attachment,
)
from octop.infra.gateway.process.message_keys import INBOUND_ATTACHMENTS_KEY
from octop.infra.gateway.steer import DiscardBundle, DrainBundle, SteerCoordinator
from octop.infra.gateway.threads import ThreadRegistry
from octop.infra.gateway.ws.ws_hub import WebSocketHub
from octop.infra.utils.locale import resolve_locale

logger = logging.getLogger(__name__)

WS_CHANNEL_ID = "octop-dashboard"


class WebSocketChannel(BaseChannel):
    """Routes chat turns through GlobalProcessor.iter_turn_chunks → WebSocket hub."""

    channel_type = ThreadRegistry.CHANNEL_DASHBOARD

    def __init__(
        self,
        processor: MessageProcessor,
        *,
        hub: WebSocketHub,
        steer: SteerCoordinator | None = None,
        channel_id: str = WS_CHANNEL_ID,
    ) -> None:
        super().__init__(processor, channel_id=channel_id, debounce_seconds=0.0)
        self._hub = hub
        self._steer = steer or SteerCoordinator()

    def _default_constraints(self) -> ChannelConstraints:
        return ChannelConstraints(
            show_thinking=True,
            show_tool_hints=True,
            send_rate_limit=None,
        )

    async def start(self) -> None:
        return

    async def stop(self) -> None:
        return

    def parse_inbound(self, raw_payload: Any) -> InboundMessage:
        if isinstance(raw_payload, InboundMessage):
            return raw_payload
        raise TypeError(f"websocket channel expects InboundMessage, got {type(raw_payload)!r}")

    def get_debounce_key(self, message: InboundMessage) -> str:
        """Lock and batch per thread so concurrent WS turns cannot interleave.

        Dashboard ``session_key`` is per user+agent; using it as the worker lock
        would serialize unrelated threads and let ``_drain_same_session`` merge
        turns from different conversations.
        """
        meta = message.metadata or {}
        thread_id = meta.get("thread_id")
        if isinstance(thread_id, str) and thread_id.strip():
            return f"thread:{thread_id.strip()}"
        session_key = meta.get("session_key")
        if isinstance(session_key, str) and session_key.strip():
            return session_key.strip()
        if message.channel_session_id:
            return message.channel_session_id
        subject_id = ""
        if message.channel_subject and message.channel_subject.subject_id:
            subject_id = message.channel_subject.subject_id
        return f"{message.tenant_id or ''}:{subject_id}"

    def should_batch_inbound(self, message: InboundMessage) -> bool:  # noqa: ARG002
        # Never concatenate two dashboard user_turns (would look like 串流).
        return False

    async def handle_inbound(self, raw_payload: Any) -> None:
        """Stream harness chunks to all thread subscribers (no delta batching).

        After each harness stream completes, drain pending steers and continue
        the same logical turn (issue #1300 soft interrupt at Octop boundaries).
        """
        message = self.parse_inbound(raw_payload)

        if self._media_backend:
            await self._persist_media(message)

        msg_meta = message.metadata or {}
        conn_id = str(msg_meta.get("ws_connection_id") or "")
        if not conn_id:
            logger.warning("websocket inbound missing ws_connection_id")
            return

        thread_id = str(msg_meta.get("thread_id") or "").strip()
        if not thread_id:
            logger.warning("websocket inbound missing thread_id")
            await self._hub.push(conn_id, {"type": "error", "message": "missing thread_id"})
            await self._hub.push(conn_id, {"type": "done"})
            return

        self._track_subject(message)
        # Per-turn routing copy: do not write thread_id onto the shared
        # ChannelSubject (keyed by user), or concurrent threads 串流 via _send_*.
        subject_id = message.channel_subject.subject_id if message.channel_subject else ""
        tracked = self._known_subjects.get(subject_id) or ChannelSubject(
            subject_id=subject_id,
            first_seen=message.timestamp,
            last_seen=message.timestamp,
        )
        message.channel_subject = ChannelSubject(
            subject_id=tracked.subject_id,
            first_seen=tracked.first_seen,
            last_seen=tracked.last_seen,
            display_name=tracked.display_name,
            chat_type=tracked.chat_type,
            metadata={
                **(tracked.metadata or {}),
                "ws_connection_id": conn_id,
                "thread_id": thread_id,
            },
        )

        # Bind the originating connection so early chunks are delivered; extra
        # browsers / reconnects add subscribers via hub.subscribe without kicking
        # existing connections.
        self._hub.subscribe(thread_id, conn_id)

        processor = self._processor
        if not hasattr(processor, "iter_turn_chunks"):
            await self._hub.push_to_thread(
                thread_id,
                {"type": "error", "message": "processor does not support turn chunk streaming"},
            )
            await self._hub.push_to_thread(thread_id, {"type": "done"})
            return

        turn_id, started_seq, replaced = self._steer.begin_turn(thread_id)
        if replaced is not None:
            await _push_discarded(self._hub, thread_id, replaced)
        self._steer.remember_context(
            thread_id, message.metadata if isinstance(message.metadata, dict) else None
        )
        self._hub.mark_turn_active(thread_id)
        failed = False
        stream = None
        try:
            await self._hub.push_to_thread(
                thread_id,
                {
                    "type": "turn.started",
                    "turn_id": turn_id,
                    "seq": started_seq,
                    "phase": "streaming_text",
                    "thread_id": thread_id,
                },
            )
            current = message
            while True:
                saw_tool_result = False
                preempted = False
                stream = processor.iter_turn_chunks(current)
                async for chunk in stream:
                    chunk_type = str(chunk.get("type") or "") if isinstance(chunk, dict) else ""
                    if preempted and chunk_type not in ("done", "error"):
                        # Cancel already landed at the tool boundary. Later
                        # tokens are not in the checkpoint — do not show them.
                        continue
                    if (
                        not preempted
                        and chunk_type in ("token", "tool_call_chunk")
                        and saw_tool_result
                        and self._steer.has_pending(thread_id)
                    ):
                        # First model output after a completed tools superstep.
                        # Drop this chunk: the checkpoint still ends at the
                        # tool results, and the client must not render text
                        # the continuation will not see.
                        preempted = True
                        self._steer.set_phase(thread_id, "between_model_steps")
                        cancel = getattr(processor, "cancel_agent_stream", None)
                        if callable(cancel):
                            logger.info(
                                "steer preemption cancelling stream agent=%s thread=%s",
                                message.tenant_id,
                                thread_id,
                            )
                            cancel(str(message.tenant_id or ""), thread_id)
                        continue
                    # Never let delivery failures abort the harness turn — otherwise a
                    # flaky client disconnect can stop generation mid-node and leave
                    # an incomplete checkpoint.
                    try:
                        await self._hub.push_to_thread(thread_id, chunk)
                    except Exception:
                        logger.exception(
                            "websocket push failed thread=%s (turn continues)",
                            thread_id,
                        )
                    if chunk_type == "error":
                        failed = True
                        break
                    if chunk_type == "hitl_required":
                        # Graph is interrupted; the WS turn ends but resume flows
                        # through the HITL SSE route — never continue into it.
                        self._steer.set_phase(thread_id, "hitl_paused")
                        continue
                    if chunk_type == "tool_result":
                        saw_tool_result = True
                        self._steer.set_phase(thread_id, "awaiting_tools")
                if failed or self._steer.is_hitl_paused(thread_id):
                    break
                await close_event_stream(stream)
                stream = None
                outcome = self._steer.drain_for_continuation(thread_id)
                if outcome is None:
                    break
                if isinstance(outcome, DiscardBundle):
                    try:
                        await self._hub.push_to_thread(
                            thread_id,
                            {
                                "type": "steer.discarded",
                                "seq": outcome.seq,
                                "client_pending_ids": outcome.client_pending_ids,
                                "pending_ids": outcome.pending_ids,
                                "turn_id": outcome.turn_id,
                                "reason": outcome.reason,
                                "thread_id": thread_id,
                            },
                        )
                    except Exception:
                        logger.exception("websocket failed to deliver steer.discarded (in-loop)")
                    break
                if not isinstance(outcome, DrainBundle):  # pragma: no cover - defensive
                    raise TypeError(f"unexpected steer drain outcome: {outcome!r}")
                seq_drained = self._steer.drained_event_seq(thread_id)
                # Dashboard user bubble then drained (adjacent allocating seq).
                await self._hub.push_to_thread(
                    thread_id,
                    _steer_user_frame(thread_id, outcome),
                )
                await self._hub.push_to_thread(
                    thread_id,
                    {
                        "type": "steer.drained",
                        "seq": seq_drained,
                        "client_pending_ids": outcome.client_pending_ids,
                        "pending_ids": outcome.pending_ids,
                        "turn_id": outcome.turn_id,
                        "message_id": outcome.message_id,
                        "thread_id": thread_id,
                    },
                )
                resumed_seq = self._steer.allocate_seq(thread_id)
                await self._hub.push_to_thread(
                    thread_id,
                    {
                        "type": "turn.resumed",
                        "turn_id": outcome.turn_id,
                        "seq": resumed_seq,
                        "phase": "between_model_steps",
                        "thread_id": thread_id,
                    },
                )
                current = _continuation_inbound(
                    message,
                    text=outcome.text,
                    blocks=outcome.content_blocks,
                )
        except Exception as exc:
            failed = True
            logger.exception("websocket turn failed")
            err_meta = message.metadata if isinstance(message.metadata, dict) else None
            locale = resolve_locale(
                channel_type=str(getattr(message, "channel_type", "") or ""),
                metadata=err_meta,
            )
            try:
                await self._hub.push_to_thread(
                    thread_id,
                    {"type": "error", "message": format_stream_error(exc, locale)},
                )
                await self._hub.push_to_thread(thread_id, {"type": "done"})
            except Exception:
                logger.exception("websocket failed to deliver error frame thread=%s", thread_id)
        finally:
            discarded = self._steer.end_turn(thread_id, failed=failed)
            self._hub.mark_turn_idle(thread_id)
            if stream is not None:
                await close_event_stream(stream)
            if discarded is not None:
                try:
                    await self._hub.push_to_thread(
                        thread_id,
                        {
                            "type": "steer.discarded",
                            "seq": discarded.seq,
                            "client_pending_ids": discarded.client_pending_ids,
                            "pending_ids": discarded.pending_ids,
                            "turn_id": discarded.turn_id,
                            "reason": discarded.reason,
                            "thread_id": thread_id,
                        },
                    )
                except Exception:
                    logger.exception("websocket failed to deliver steer.discarded")
            try:
                # hitl_paused means the steer queue is parked server-side and
                # survives the approval pause (drains after SSE resume) — the
                # dashboard keeps its chips instead of clearing them.
                hitl_parked = self._steer.is_hitl_paused(thread_id)
                await self._hub.push_to_thread(
                    thread_id,
                    {
                        "type": "turn.ended",
                        "turn_id": turn_id,
                        "thread_id": thread_id,
                        "failed": failed or None,
                        **({"hitl_paused": True} if hitl_parked else {}),
                    },
                )
            except Exception:
                logger.exception("websocket failed to deliver turn.ended thread=%s", thread_id)

    async def _send_text(self, subject: ChannelSubject, text: str) -> None:
        if not text:
            return
        thread_id = str(subject.metadata.get("thread_id") or "").strip()
        if thread_id:
            await self._hub.push_to_thread(thread_id, {"type": "token", "content": text})
            await self._hub.push_to_thread(thread_id, {"type": "done"})
            return
        conn_id = str(subject.metadata.get("ws_connection_id") or "")
        if conn_id:
            await self._hub.push(conn_id, {"type": "token", "content": text})
            await self._hub.push(conn_id, {"type": "done"})

    async def _send_content(self, subject: ChannelSubject, parts: list[ContentPart]) -> None:
        text = "\n".join(p.text for p in parts if isinstance(p, TextContent) and p.text)
        if text:
            await self._send_text(subject, text)

    async def _send_media(self, subject: ChannelSubject, media: ContentPart) -> None:
        thread_id = str(subject.metadata.get("thread_id") or "").strip()
        conn_id = str(subject.metadata.get("ws_connection_id") or "")
        if not thread_id and not conn_id:
            return
        try:
            raw_bytes, mime = await self.load_media_bytes(media)
        except (ValueError, RuntimeError, OSError) as exc:
            logger.warning("websocket channel: failed to load media bytes: %s", exc)
            return

        frame: dict[str, Any] = {
            "type": "attachment",
            "kind": _media_kind(media),
            "mime_type": mime,
            "data": base64.b64encode(raw_bytes).decode("ascii"),
        }
        filename = getattr(media, "filename", None)
        if isinstance(filename, str) and filename.strip():
            frame["filename"] = filename.strip()
        alt = getattr(media, "alt_text", None)
        if isinstance(alt, str) and alt.strip():
            frame["alt_text"] = alt.strip()
        if thread_id:
            await self._hub.push_to_thread(thread_id, frame)
        else:
            await self._hub.push(conn_id, frame)


def _push_discarded_frame(thread_id: str, bundle: DiscardBundle) -> dict[str, Any]:
    return {
        "type": "steer.discarded",
        "seq": bundle.seq,
        "client_pending_ids": bundle.client_pending_ids,
        "pending_ids": bundle.pending_ids,
        "turn_id": bundle.turn_id,
        "reason": bundle.reason,
        "thread_id": thread_id,
    }


async def _push_discarded(hub: WebSocketHub, thread_id: str, bundle: DiscardBundle) -> None:
    try:
        await hub.push_to_thread(thread_id, _push_discarded_frame(thread_id, bundle))
    except Exception:
        logger.exception("websocket failed to deliver steer.discarded thread=%s", thread_id)


def _steer_user_frame(thread_id: str, bundle: DrainBundle) -> dict[str, Any]:
    content = _content_from_steer(bundle.text, bundle.content_blocks)
    frame: dict[str, Any] = {
        "type": "user",
        "content": bundle.text,
        "message_id": bundle.message_id,
        "meta": {"steer": True},
        "thread_id": thread_id,
    }
    attachments = inbound_attachments_from_parts(content)
    if attachments:
        frame["attachments"] = attachments
    return frame


def _content_from_steer(text: str, blocks: tuple[dict[str, Any], ...]) -> list[ContentPart]:
    parts: list[ContentPart] = []
    if text.strip():
        parts.append(TextContent(text=text))
    for block in blocks:
        path = str(block.get("workspace_path") or "").strip()
        if not path:
            continue
        filename = str(block.get("filename") or "").strip() or "attachment"
        media_type = str(block.get("media_type") or "").strip() or "application/octet-stream"
        kind = str(block.get("type") or "")
        if is_vision_attachment(kind=kind, media_type=media_type, path=path):
            parts.append(
                ImageContent(
                    local_path=path,
                    mime_type=media_type if media_type.startswith("image/") else "image/png",
                    alt_text=filename,
                )
            )
        else:
            parts.append(
                FileContent(
                    local_path=path,
                    filename=filename,
                    mime_type=media_type,
                )
            )
    return parts


def _media_kind(media: ContentPart) -> str:
    if isinstance(media, ImageContent):
        return "image"
    if isinstance(media, VideoContent):
        return "video"
    if isinstance(media, AudioContent):
        return "audio"
    if isinstance(media, FileContent):
        return "file"
    return "file"


def _continuation_inbound(
    original: InboundMessage,
    *,
    text: str,
    blocks: tuple[dict[str, Any], ...] = (),
) -> InboundMessage:
    """Clone inbound for a steer continuation (same thread / connection)."""
    meta = dict(original.metadata or {})
    content = _content_from_steer(text, blocks)
    attachments = inbound_attachments_from_parts(content)
    if attachments:
        meta[INBOUND_ATTACHMENTS_KEY] = attachments
    else:
        meta.pop(INBOUND_ATTACHMENTS_KEY, None)
    return InboundMessage(
        channel_id=original.channel_id,
        channel_type=original.channel_type,
        tenant_id=original.tenant_id,
        channel_subject=original.channel_subject,
        channel_session_id=original.channel_session_id,
        content=content,
        metadata=meta,
        timestamp=original.timestamp,
    )


async def resume_parked_steers(
    server: Any,
    *,
    agent_id: str,
    thread_id: str,
    session_key: str,
    channel_type: str,
    user_id: int,
) -> None:
    """After an HITL approval resumes, drain steers parked across the pause.

    The queue survives the interrupt and drains at the first
    boundary after resume — here that boundary is the end of the SSE resume
    stream, and the drain re-enters through the normal WS channel turn so all
    steer frames (user bubble, steer.drained, turn.started…) flow as usual.
    """
    runtime = getattr(server, "app_runtime", None)
    gateway = getattr(runtime, "gateway", None)
    steer = getattr(gateway, "steer", None)
    hub = getattr(gateway, "ws_hub", None)
    channel_manager = getattr(gateway, "channel_manager", None)
    if steer is None or hub is None or channel_manager is None:
        return
    expired = steer.sweep_expired(thread_id)
    if expired is not None:
        await _push_discarded(hub, thread_id, expired)
        return
    staged = steer.stage_hitl_pending(thread_id)
    if staged is None:
        return
    bundle, seq = staged
    queues = getattr(channel_manager, "_queues", None)
    if not isinstance(queues, dict) or WS_CHANNEL_ID not in queues:
        steer.release_staged_hitl(thread_id)
        logger.error("steer resume has no dashboard queue thread=%s", thread_id)
        return
    meta = steer.continuation_metadata(thread_id)
    meta["thread_id"] = thread_id
    meta["session_key"] = session_key
    # Subscribers already on the thread receive the turn. This id only
    # satisfies the inbound guard; it is not a hub connection.
    meta["ws_connection_id"] = f"hitl-resume:{thread_id}"
    content = _content_from_steer(bundle.text, bundle.content_blocks)
    attachments = inbound_attachments_from_parts(content)
    if attachments:
        meta[INBOUND_ATTACHMENTS_KEY] = attachments
    logger.info(
        "steer resume drain after hitl agent=%s thread=%s items=%d",
        agent_id,
        thread_id,
        len(bundle.client_pending_ids),
    )
    try:
        channel_manager.enqueue(
            WS_CHANNEL_ID,
            InboundMessage(
                channel_id=WS_CHANNEL_ID,
                channel_type=channel_type or "dashboard",
                tenant_id=agent_id,
                channel_subject=ChannelSubject(subject_id=str(user_id)),
                channel_session_id=session_key,
                content=content,
                metadata=meta,
            ),
        )
    except Exception:
        steer.release_staged_hitl(thread_id)
        logger.exception("steer resume continuation enqueue failed thread=%s", thread_id)
        return
    steer.commit_staged_hitl(thread_id)
    try:
        await hub.push_to_thread(thread_id, _steer_user_frame(thread_id, bundle))
        await hub.push_to_thread(
            thread_id,
            {
                "type": "steer.drained",
                "seq": seq,
                "client_pending_ids": bundle.client_pending_ids,
                "pending_ids": bundle.pending_ids,
                "turn_id": bundle.turn_id,
                "message_id": bundle.message_id,
                "thread_id": thread_id,
            },
        )
    except Exception:
        logger.exception("steer resume drain frames failed thread=%s", thread_id)


__all__ = ["WS_CHANNEL_ID", "WebSocketChannel", "resume_parked_steers"]
