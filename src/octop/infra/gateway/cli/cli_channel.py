"""Virtual IM channel that delivers CLI chat turns in-process."""

from __future__ import annotations

import base64
import logging
from typing import Any

from harness_gateway.channel import BaseChannel, MessageProcessor
from harness_gateway.constraints import ChannelConstraints
from harness_gateway.models import (
    AudioContent,
    ChannelSubject,
    ContentPart,
    FileContent,
    ImageContent,
    InboundMessage,
    TextContent,
    VideoContent,
)

from octop.i18n.domains.stream import format_stream_error
from octop.infra.gateway.threads import ThreadRegistry
from octop.infra.gateway.ws.ws_hub import WebSocketHub
from octop.infra.utils.locale import resolve_locale

logger = logging.getLogger(__name__)

CLI_CHANNEL_ID = "octop-cli"
CLI_CONNECTION_META = "cli_connection_id"


class CliChannel(BaseChannel):
    """Routes chat turns through GlobalProcessor.iter_turn_chunks → CLI hub."""

    channel_type = ThreadRegistry.CHANNEL_CLI

    def __init__(
        self,
        processor: MessageProcessor,
        *,
        hub: WebSocketHub,
        channel_id: str = CLI_CHANNEL_ID,
    ) -> None:
        super().__init__(processor, channel_id=channel_id, debounce_seconds=0.0)
        self._hub = hub

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
        raise TypeError(f"cli channel expects InboundMessage, got {type(raw_payload)!r}")

    def get_debounce_key(self, message: InboundMessage) -> str:
        meta = message.metadata or {}
        session_key = meta.get("session_key")
        if isinstance(session_key, str) and session_key.strip():
            return session_key.strip()
        if message.channel_session_id:
            return message.channel_session_id
        subject_id = ""
        if message.channel_subject and message.channel_subject.subject_id:
            subject_id = message.channel_subject.subject_id
        return f"{message.tenant_id or ''}:{subject_id}"

    async def handle_inbound(self, raw_payload: Any) -> None:
        """Stream harness chunks to the originating CLI session (no delta batching)."""
        message = self.parse_inbound(raw_payload)

        if self._media_backend:
            await self._persist_media(message)

        self._track_subject(message)
        subject_id = message.channel_subject.subject_id if message.channel_subject else ""
        subject = self._known_subjects.get(subject_id) or ChannelSubject(
            subject_id=subject_id,
            first_seen=message.timestamp,
            last_seen=message.timestamp,
        )
        message.channel_subject = subject

        conn_id = str((message.metadata or {}).get(CLI_CONNECTION_META) or "")
        if not conn_id:
            logger.warning("cli inbound missing %s", CLI_CONNECTION_META)
            return

        meta = dict(subject.metadata or {})
        meta[CLI_CONNECTION_META] = conn_id
        subject.metadata = meta

        processor = self._processor
        if not hasattr(processor, "iter_turn_chunks"):
            await self._hub.push(
                conn_id,
                {"type": "error", "message": "processor does not support turn chunk streaming"},
            )
            await self._hub.push(conn_id, {"type": "done"})
            return

        try:
            async for chunk in processor.iter_turn_chunks(message):
                await self._hub.push(conn_id, chunk)
        except Exception as exc:
            logger.exception("cli turn failed")
            meta = message.metadata if isinstance(message.metadata, dict) else None
            locale = resolve_locale(
                channel_type=str(getattr(message, "channel_type", "") or ""),
                metadata=meta,
            )
            await self._hub.push(
                conn_id,
                {"type": "error", "message": format_stream_error(exc, locale)},
            )
            await self._hub.push(conn_id, {"type": "done"})

    async def _send_text(self, subject: ChannelSubject, text: str) -> None:
        conn_id = str(subject.metadata.get(CLI_CONNECTION_META) or "")
        if conn_id and text:
            await self._hub.push(conn_id, {"type": "token", "content": text})

    async def _send_content(self, subject: ChannelSubject, parts: list[ContentPart]) -> None:
        text = "\n".join(p.text for p in parts if isinstance(p, TextContent) and p.text)
        if text:
            await self._send_text(subject, text)

    async def _send_media(self, subject: ChannelSubject, media: ContentPart) -> None:
        conn_id = str(subject.metadata.get(CLI_CONNECTION_META) or "")
        if not conn_id:
            return
        try:
            raw_bytes, mime = await self.load_media_bytes(media)
        except (ValueError, RuntimeError, OSError) as exc:
            logger.warning("cli channel: failed to load media bytes: %s", exc)
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
        await self._hub.push(conn_id, frame)


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


__all__ = ["CLI_CHANNEL_ID", "CLI_CONNECTION_META", "CliChannel"]
