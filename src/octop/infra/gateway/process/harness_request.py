"""Assemble harness-agent stream requests and multimodal user content."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from harness_gateway.media import MediaBackend
from harness_gateway.models import ContentPart, ImageContent, InboundMessage, TextContent

from octop.i18n.domains.attachment import attachment_empty_image, attachment_empty_message
from octop.infra.gateway.media.attachment_hints import (
    VISION_MAX_COUNT,
    content_blocks_need_vision,
    hints_from_content_parts,
    materialize_image_part,
)
from octop.infra.gateway.media.ingress import AgentBackedMediaBackend
from octop.infra.gateway.process.message_keys import images_from_message
from octop.infra.utils.locale import Locale, normalize_locale


def _workspace_from_media_backend(media_backend: MediaBackend | None) -> Any:
    if isinstance(media_backend, AgentBackedMediaBackend):
        return media_backend._workspace
    return None


def _group_turn_text(
    msg: InboundMessage,
    current_text: str,
    *,
    workspace: Any = None,
    locale: str | Locale = "en",
) -> str:
    """Render short-lived group context without creating durable fake turns."""
    context = msg.group_context
    if context is None:
        return current_text

    language = normalize_locale(str(locale))
    anonymous_labels: dict[str, str] = {}

    def sender_label(sender_id: str, sender_name: str) -> str:
        safe_id = " ".join(sender_id.split()) or "unknown"
        safe_name = " ".join(sender_name.split())
        if safe_name and safe_name != safe_id:
            return safe_name
        if safe_id not in anonymous_labels:
            index = len(anonymous_labels) + 1
            anonymous_labels[safe_id] = (
                f"群成员{index}" if language == "zh" else f"Group member {index}"
            )
        return anonymous_labels[safe_id]

    context_header = (
        "【群聊背景｜仅供参考】" if language == "zh" else "[Group context | reference only]"
    )
    current_header = (
        "【当前群消息｜请回复这条消息】"
        if language == "zh"
        else "[Current group message | reply to this]"
    )

    lines: list[str] = []
    if context.messages:
        lines.append(context_header)
        for item in context.messages:
            label = sender_label(item.sender_id, item.sender_name)
            segments = [item.text] if item.text else []
            segments.extend(
                hints_from_content_parts(
                    item.content,
                    workspace=workspace,
                    locale=locale,
                    skip_vision_images=False,
                )
            )
            for segment in segments:
                segment_lines = segment.splitlines() or [""]
                lines.append(f"[{label}] {segment_lines[0]}")
                lines.extend(f"  {line}" for line in segment_lines[1:])
        lines.append("")

    sender_id = str(msg.metadata.get("sender_id") or "unknown")
    sender_name = str(msg.metadata.get("sender_name") or "")
    lines.extend(
        [
            current_header,
            f"[{sender_label(sender_id, sender_name)}] {current_text}",
        ]
    )
    return "\n".join(lines)


async def build_content_from_message(
    msg: InboundMessage,
    *,
    media_backend: MediaBackend | None = None,
    locale: str | Locale = "en",
) -> str | list[dict[str, Any]]:
    """Convert ``InboundMessage.content`` into harness user content.

    Images within :data:`VISION_MAX_COUNT` / size limits become ``image_url``
    blocks; excess / oversized / non-image attachments become path-hint text.
    """
    workspace = _workspace_from_media_backend(media_backend)
    images = images_from_message(msg)

    vision_parts: list[ImageContent] = []
    excess_images: list[ImageContent] = []
    for i, part in enumerate(images):
        if i < VISION_MAX_COUNT:
            vision_parts.append(part)
        else:
            excess_images.append(part)

    file_hints = hints_from_content_parts(
        msg.content,
        workspace=workspace,
        locale=locale,
        skip_vision_images=True,
    )
    # Oversized / unreadable vision parts may also degrade to hints inside
    # materialize; excess images always become path hints.
    if excess_images:
        file_hints.extend(
            hints_from_content_parts(
                excess_images,
                workspace=workspace,
                locale=locale,
                skip_vision_images=False,
            )
        )

    image_blocks: list[dict[str, Any]] = []
    for part in vision_parts:
        block = await materialize_image_part(
            part,
            media_backend=media_backend,
            workspace=workspace,
            locale=locale,
        )
        if block is None:
            continue
        if block.get("type") == "text":
            # Degraded to path hint (oversized / unloadable).
            text = str(block.get("text") or "").strip()
            if text:
                file_hints.append(text)
            continue
        image_blocks.append(block)

    current_text = "\n\n".join(part for part in [msg.text or "", *file_hints] if part)
    combined_text = _group_turn_text(msg, current_text, workspace=workspace, locale=locale)

    if not image_blocks:
        return combined_text or attachment_empty_message(locale)

    blocks: list[dict[str, Any]] = [
        {"type": "text", "text": combined_text or attachment_empty_image(locale)}
    ]
    blocks.extend(image_blocks)
    return blocks


def content_from_parts(
    parts: Sequence[ContentPart],
    *,
    media_backend: MediaBackend | None = None,
    locale: str | Locale = "en",
) -> str | list[dict[str, Any]]:
    """Sync helper for tests — no vision size gate (inline/url only)."""
    texts: list[str] = []
    images: list[ImageContent] = []
    for part in parts:
        if isinstance(part, TextContent):
            if part.text:
                texts.append(part.text)
        elif isinstance(part, ImageContent):
            images.append(part)
    texts.extend(
        hints_from_content_parts(
            parts,
            workspace=_workspace_from_media_backend(media_backend),
            locale=locale,
        )
    )
    return _build_content_sync(
        text="\n\n".join(texts),
        images=images or None,
        media_backend=media_backend,
        locale=locale,
    )


def build_content(
    *,
    text: str = "",
    images: Sequence[ImageContent | dict[str, Any]] | None = None,
    media_backend: MediaBackend | None = None,
    locale: str | Locale = "en",
) -> str | list[dict[str, Any]]:
    """Sync build for unit tests / callers with already-resolved image bytes."""
    return _build_content_sync(
        text=text,
        images=images,
        media_backend=media_backend,
        locale=locale,
    )


def _build_content_sync(
    *,
    text: str,
    images: Sequence[ImageContent | dict[str, Any]] | None,
    media_backend: MediaBackend | None,
    locale: str | Locale,
) -> str | list[dict[str, Any]]:
    from octop.infra.gateway.media.attachment_hints import make_image_url_block  # noqa: PLC0415

    image_blocks: list[dict[str, Any]] = []
    for part in images or ():
        if isinstance(part, ImageContent):
            if part.data:
                mime = part.mime_type or "image/png"
                image_blocks.append(make_image_url_block(part.data, mime))
            elif part.url and part.url.startswith(("http://", "https://")):
                image_blocks.append({"type": "image_url", "image_url": {"url": part.url}})
            elif part.local_path and media_backend is not None:
                # Best-effort sync read for tests using FileSystemMediaBackend.
                from pathlib import Path  # noqa: PLC0415

                local = media_backend.get_local_path(part.local_path)
                if local is not None and Path(local).is_file():
                    import base64  # noqa: PLC0415
                    import mimetypes  # noqa: PLC0415

                    raw = Path(local).read_bytes()
                    mime = part.mime_type or mimetypes.guess_type(part.local_path)[0] or "image/png"
                    image_blocks.append(make_image_url_block(base64.b64encode(raw).decode(), mime))
        elif isinstance(part, dict):
            image_blocks.append(part)

    if not image_blocks:
        return text or attachment_empty_message(locale)

    blocks: list[dict[str, Any]] = [
        {"type": "text", "text": text or attachment_empty_image(locale)}
    ]
    blocks.extend(image_blocks)
    return blocks


def build_harness_request(
    *,
    thread_id: str,
    user_id: int,
    source: str,
    agent_id: str | None = None,
    session_key: str | None = None,
    text: str = "",
    images: Sequence[ImageContent | dict[str, Any]] | None = None,
    content: str | list[dict[str, Any]] | None = None,
    messages: list[Any] | None = None,
    model: str | None = None,
    message_kwargs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if messages is not None:
        req: dict[str, Any] = {
            "messages": messages,
            "thread_id": thread_id,
            "user": str(user_id),
            "source": source,
        }
        if agent_id is not None:
            req["agent_id"] = agent_id
        if session_key is not None:
            req["configurable"] = {"session_key": session_key}
        if model:
            req["model"] = model
        return req

    payload = content if content is not None else build_content(text=text, images=images)

    if isinstance(payload, list):
        from langchain_core.messages import HumanMessage  # noqa: PLC0415

        kwargs = dict(message_kwargs or {})
        msg_list: list[Any] = [HumanMessage(content=payload, additional_kwargs=kwargs)]  # type: ignore[arg-type]
    else:
        if message_kwargs:
            from langchain_core.messages import HumanMessage  # noqa: PLC0415

            msg_list = [HumanMessage(content=payload, additional_kwargs=dict(message_kwargs))]
        else:
            msg_list = [{"role": "user", "content": payload}]

    req = {
        "messages": msg_list,
        "thread_id": thread_id,
        "user": str(user_id),
        "source": source,
    }
    if agent_id is not None:
        req["agent_id"] = agent_id
    if session_key is not None:
        req["configurable"] = {"session_key": session_key}
    if model:
        req["model"] = model
    return req


# Re-export for callers that previously imported from here.
__all__ = [
    "build_content",
    "build_content_from_message",
    "build_harness_request",
    "content_blocks_need_vision",
    "content_from_parts",
]
