"""Tool-result media for Dashboard WebSocket streaming.

Uses ``agent.workspace`` via :mod:`.backend_files` —
**not** :class:`~octop.infra.gateway.media.ingress.AgentBackedMediaBackend` (IM ingress).
"""

from __future__ import annotations

import base64
import contextlib
import json
import logging
import mimetypes
import re
import urllib.parse
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from harness_agent.backends.workspace import BackendWorkspace

from harness_gateway.models import (
    AudioContent,
    ContentPart,
    FileContent,
    ImageContent,
    MessageEvent,
    MessageEventType,
    VideoContent,
)

from octop.infra.gateway.media.backend_files import (
    dashboard_media_url,
    extract_workspace_rel,
    file_url_to_abs_path,
    media_preview_url,
    read_file_url_bytes,
    resolve_dashboard_media_url,
    workspace_download_url,
)
from octop.infra.gateway.media.inbound_store import display_name_from_stored

logger = logging.getLogger(__name__)

_MEDIA_BLOCK_TYPES = frozenset({"image", "video", "audio", "file"})
_PLAIN_IMAGE_PATH_RE = re.compile(
    r"(?:saved to|written to|file(?:\s+path)?[:\s]+)\s*([^\s(]+\.(?:png|jpe?g|gif|webp|bmp|svg))",
    re.IGNORECASE,
)
_OUTBOUND_IMAGE_PATH_RE = re.compile(
    r"([^\s\"'()]+/outbound/[^\s\"'()]+\.(?:png|jpe?g|gif|webp|bmp|svg))",
    re.IGNORECASE,
)


def iter_media_blocks(content: Any) -> list[dict[str, Any]]:
    candidates: list[Any]
    if isinstance(content, list):
        candidates = content
    elif isinstance(content, str):
        stripped = content.strip()
        if not stripped or stripped[0] not in "{[":
            return []
        try:
            parsed = json.loads(stripped)
        except (ValueError, TypeError):
            return []
        if isinstance(parsed, dict):
            candidates = [parsed]
        elif isinstance(parsed, list):
            candidates = parsed
        else:
            return []
    elif isinstance(content, dict):
        candidates = [content]
    else:
        return []

    return [
        block
        for block in candidates
        if isinstance(block, dict) and block.get("type") in _MEDIA_BLOCK_TYPES
    ]


def extract_message_content(message: Any) -> Any:
    if isinstance(message, dict):
        return message.get("content")
    return getattr(message, "content", None)


def _block_file_refs(block: dict[str, Any]) -> tuple[str, str, str]:
    source = block.get("source") if isinstance(block.get("source"), dict) else {}
    raw_url = source.get("url") if isinstance(source, dict) else ""
    raw_url = raw_url if isinstance(raw_url, str) else ""
    mime = ""
    if isinstance(source, dict):
        mime = str(source.get("media_type") or "")
    if not mime:
        mime = str(block.get("media_type") or block.get("mime_type") or "")
    filename = str(block.get("filename") or "")
    return raw_url, mime, filename


def _workspace_rel_from_preview(preview: str) -> str | None:
    if "path=" not in preview:
        return None
    try:
        query = preview.split("?", 1)[1]
    except IndexError:
        return None
    for part in query.split("&"):
        if part.startswith("path="):
            return extract_workspace_rel(urllib.parse.unquote(part[5:]))
    return None


def _resolve_block_workspace_rel(block: dict[str, Any], preview: str = "") -> str | None:
    """Return inbound/outbound relative path when present (image/media convention)."""
    raw_path = block.get("path")
    if isinstance(raw_path, str) and raw_path.strip():
        rel = extract_workspace_rel(raw_path.strip())
        if rel:
            return rel
    if preview:
        return _workspace_rel_from_preview(preview)
    raw_url, _, _ = _block_file_refs(block)
    if raw_url:
        return extract_workspace_rel(raw_url)
    return None


def _slim_file_block(block: dict[str, Any], *, rel: str | None, mime: str) -> dict[str, Any]:
    """Dashboard file cards only need workspace path + display name — no preview URLs."""
    out: dict[str, Any] = {"type": "file"}
    if rel:
        out["path"] = rel
    filename = block.get("filename")
    if isinstance(filename, str) and filename.strip():
        out["filename"] = display_name_from_stored(filename.strip())
    elif rel:
        out["filename"] = display_name_from_stored(Path(rel).name)
    if mime:
        out["media_type"] = mime
    return out


def _block_with_preview_url(block: dict[str, Any], preview: str) -> dict[str, Any]:
    """Rewrite media blocks for the dashboard.

    - ``file``: keep only ``path`` / ``filename`` / ``media_type`` (UI builds download URLs).
    - image/video/audio: set ``preview_url`` + ``source.url`` to the authenticated API.
    """
    btype = str(block.get("type") or "file")
    _, mime, _ = _block_file_refs(block)
    rel = _resolve_block_workspace_rel(block, preview)

    if btype == "file":
        return _slim_file_block(block, rel=rel, mime=mime)

    out = dict(block)
    out["preview_url"] = preview
    source = out.get("source")
    if isinstance(source, dict):
        source_copy = dict(source)
        source_copy["url"] = preview
        out["source"] = source_copy

    if rel:
        out["path"] = rel
    else:
        out.pop("path", None)
    return out


def _map_content_blocks(
    content: Any,
    transform: Callable[[dict[str, Any]], Any],
) -> Any:
    if isinstance(content, list):
        blocks = [transform(b) for b in content]
        return blocks if blocks != content else content
    if isinstance(content, dict):
        enriched = transform(content)
        return enriched if enriched is not content else content
    if isinstance(content, str):
        stripped = content.strip()
        if not stripped or stripped[0] not in "{[":
            return content
        try:
            parsed = json.loads(stripped)
        except (ValueError, TypeError):
            return content
        if isinstance(parsed, dict):
            return json.dumps(transform(parsed), ensure_ascii=False)
        if isinstance(parsed, list):
            return json.dumps([transform(b) for b in parsed], ensure_ascii=False)
    return content


async def _amap_content_blocks(
    content: Any,
    transform: Callable[[dict[str, Any]], Awaitable[Any]],
) -> Any:
    if isinstance(content, list):
        blocks = [await transform(b) for b in content]
        return blocks if blocks != content else content
    if isinstance(content, dict):
        enriched = await transform(content)
        return enriched if enriched is not content else content
    if isinstance(content, str):
        stripped = content.strip()
        if not stripped or stripped[0] not in "{[":
            return content
        try:
            parsed = json.loads(stripped)
        except (ValueError, TypeError):
            return content
        if isinstance(parsed, dict):
            return json.dumps(await transform(parsed), ensure_ascii=False)
        if isinstance(parsed, list):
            return json.dumps([await transform(b) for b in parsed], ensure_ascii=False)
    return content


def enrich_media_block_preview(block: Any, *, agent_id: str) -> Any:
    """Rewrite media blocks for dashboard history (no workspace import)."""
    if not isinstance(block, dict) or block.get("type") not in _MEDIA_BLOCK_TYPES:
        return block
    btype = str(block.get("type") or "")
    if btype == "file":
        raw_url, mime, _ = _block_file_refs(block)
        path = _file_block_path(block, raw_url)
        if path:
            return _slim_file_block(block, rel=path, mime=mime)
        # Fall through to try deriving a path from file:// URL fields.
    elif block.get("preview_url"):
        return block
    raw_url, mime, _ = _block_file_refs(block)
    if not raw_url.startswith("file://"):
        if btype == "file":
            return block
        return block
    url = dashboard_media_url(agent_id, raw_url, mime)
    return _block_with_preview_url(block, url) if url else block


def enrich_tool_message_content(content: Any, *, agent_id: str) -> Any:
    return _map_content_blocks(
        content,
        lambda block: enrich_media_block_preview(block, agent_id=agent_id),
    )


def enrich_tool_result_for_dashboard(
    chunk: dict[str, Any],
    *,
    agent_id: str,
) -> dict[str, Any]:
    messages = chunk.get("messages")
    if not isinstance(messages, list):
        return chunk

    out_messages: list[Any] = []
    for message in messages:
        if isinstance(message, dict):
            content = message.get("content")
            enriched = enrich_tool_message_content(content, agent_id=agent_id)
            if enriched is not content:
                msg_copy = dict(message)
                msg_copy["content"] = enriched
                out_messages.append(msg_copy)
            else:
                out_messages.append(message)
        else:
            content = getattr(message, "content", None)
            enriched = enrich_tool_message_content(content, agent_id=agent_id)
            if enriched is not content:
                with contextlib.suppress(AttributeError):
                    message.content = enriched
            out_messages.append(message)

    out = dict(chunk)
    out["messages"] = out_messages
    return out


async def enrich_tool_result_with_backend(
    chunk: dict[str, Any],
    *,
    agent_id: str,
    workspace: BackendWorkspace,
) -> dict[str, Any]:
    """Import external ``file://`` media into workspace and set ``preview_url``."""
    messages = chunk.get("messages")
    if not isinstance(messages, list):
        return chunk

    out_messages: list[Any] = []
    for message in messages:
        content = extract_message_content(message)
        if isinstance(content, str):
            stripped = content.strip()
            if stripped and stripped[0] not in "{[":
                plain_enriched = await _enrich_plain_text_tool_media(
                    content,
                    agent_id=agent_id,
                    workspace=workspace,
                )
                if plain_enriched != content:
                    if isinstance(message, dict):
                        msg_copy = dict(message)
                        msg_copy["content"] = plain_enriched
                        out_messages.append(msg_copy)
                    else:
                        with contextlib.suppress(AttributeError):
                            message.content = plain_enriched
                        out_messages.append(message)
                    continue

        enriched = await _amap_content_blocks(
            content,
            lambda block: _enrich_block_with_backend(block, agent_id=agent_id, workspace=workspace),
        )
        if enriched is content:
            out_messages.append(message)
            continue
        if isinstance(message, dict):
            msg_copy = dict(message)
            msg_copy["content"] = enriched
            out_messages.append(msg_copy)
        else:
            with contextlib.suppress(AttributeError):
                message.content = enriched
            out_messages.append(message)

    out = dict(chunk)
    out["messages"] = out_messages
    return out


def _file_block_path(block: dict[str, Any], raw_url: str) -> str | None:
    """Resolve the path to store on a slimmed file block.

    Prefer an explicit absolute / ``file://`` path from the tool (BackendWorkspace
    can read it directly). Fall back to inbound/outbound relatives. Never invent
    a relative rewrite of a host-absolute path.
    """
    raw_path = block.get("path")
    if isinstance(raw_path, str) and raw_path.strip():
        candidate = raw_path.strip()
        if candidate.startswith("file://"):
            return file_url_to_abs_path(candidate)
        # Leading '/' (and Windows drive) = host absolute under download default.
        if candidate.startswith("/") or (len(candidate) >= 2 and candidate[1] == ":"):
            return candidate
        rel = extract_workspace_rel(candidate)
        if rel:
            return rel
        return candidate.lstrip("/") or None

    if raw_url.startswith("file://"):
        return file_url_to_abs_path(raw_url)
    if raw_url.startswith("/") or (len(raw_url) >= 2 and raw_url[1] == ":"):
        return raw_url
    return extract_workspace_rel(raw_url)


async def _enrich_block_with_backend(
    block: Any, *, agent_id: str, workspace: BackendWorkspace
) -> Any:
    if not isinstance(block, dict) or block.get("type") not in _MEDIA_BLOCK_TYPES:
        return block
    btype = str(block.get("type") or "")
    # File blocks may already be path-only (no preview_url).
    if block.get("preview_url") and btype != "file":
        return block

    raw_url, mime, filename = _block_file_refs(block)
    if btype == "file":
        # Keep the tool's absolute path as-is — BackendWorkspace reads it
        # directly. Do not copy into outbound/ or collapse to a relative path.
        path = _file_block_path(block, raw_url)
        if path:
            return _slim_file_block(block, rel=path, mime=mime)
        return enrich_media_block_preview(block, agent_id=agent_id)

    if isinstance(block.get("path"), str) and block["path"].startswith(("inbound/", "outbound/")):
        return block

    if not raw_url.startswith("file://"):
        return enrich_media_block_preview(block, agent_id=agent_id)

    url = await resolve_dashboard_media_url(
        workspace,
        agent_id,
        raw_url,
        filename=filename,
        mime=mime,
    )
    return _block_with_preview_url(block, url)


def enrich_tool_output_string_sync(output: str, *, agent_id: str) -> str:
    """Cheap URL rewrite for history loads — no workspace file import."""
    if not output.strip():
        return output
    stripped = output.strip()
    if stripped[0] not in "{[":
        return _enrich_plain_text_tool_media_sync(output, agent_id=agent_id)
    enriched = enrich_tool_message_content(output, agent_id=agent_id)
    return enriched if isinstance(enriched, str) else output


async def enrich_tool_output_string(
    output: str,
    *,
    agent_id: str,
    workspace: BackendWorkspace | None,
) -> str:
    """Rewrite ``file://`` media in a tool-result JSON string to workspace download URLs."""
    if not output.strip():
        return output

    stripped = output.strip()
    if stripped[0] not in "{[":
        return await _enrich_plain_text_tool_media(
            output,
            agent_id=agent_id,
            workspace=workspace,
        )

    if workspace is not None:
        enriched = await _amap_content_blocks(
            output,
            lambda block: _enrich_block_with_backend(block, agent_id=agent_id, workspace=workspace),
        )
    else:
        enriched = enrich_tool_message_content(output, agent_id=agent_id)
    return enriched if isinstance(enriched, str) else output


def _plain_text_image_path(text: str) -> str | None:
    match = _PLAIN_IMAGE_PATH_RE.search(text)
    if match:
        return match.group(1)
    match = _OUTBOUND_IMAGE_PATH_RE.search(text)
    if match:
        return match.group(1)
    return None


def _enrich_plain_text_tool_media_sync(output: str, *, agent_id: str) -> str:
    """History-safe plain-text image rewrite (preview URL only, no import)."""
    stripped = output.strip()
    if not stripped:
        return output
    raw_path = _plain_text_image_path(stripped)
    if not raw_path:
        return output
    file_url = raw_path if raw_path.startswith("file://") else f"file://{raw_path}"
    mime = mimetypes.guess_type(raw_path)[0] or "image/png"
    preview = dashboard_media_url(agent_id, file_url, mime) or media_preview_url(
        agent_id, file_url, mime
    )
    image_block: dict[str, Any] = {
        "type": "image",
        "source": {"type": "url", "url": file_url, "media_type": mime},
        "preview_url": preview,
        "filename": Path(raw_path).name,
    }
    return json.dumps(
        [{"type": "text", "text": stripped}, image_block],
        ensure_ascii=False,
    )


async def _enrich_plain_text_tool_media(
    output: str,
    *,
    agent_id: str,
    workspace: BackendWorkspace | None,
) -> str:
    """When tool output is plain text with a screenshot path, append an image block."""
    stripped = output.strip()
    if not stripped:
        return output
    raw_path = _plain_text_image_path(stripped)
    if not raw_path:
        return output

    file_url = raw_path if raw_path.startswith("file://") else f"file://{raw_path}"
    mime = mimetypes.guess_type(raw_path)[0] or "image/png"
    if workspace is not None:
        preview = await resolve_dashboard_media_url(
            workspace,
            agent_id,
            file_url,
            filename=Path(raw_path).name,
            mime=mime,
        )
    else:
        preview = dashboard_media_url(agent_id, file_url, mime) or media_preview_url(
            agent_id, file_url, mime
        )

    image_block: dict[str, Any] = {
        "type": "image",
        "source": {"type": "url", "url": file_url, "media_type": mime},
        "preview_url": preview,
        "filename": Path(raw_path).name,
    }
    return json.dumps(
        [{"type": "text", "text": stripped}, image_block],
        ensure_ascii=False,
    )


def _attachment_kind(block_type: str) -> str:
    if block_type == "image":
        return "image"
    if block_type in {"video", "audio"}:
        return block_type
    return "file"


async def attachment_frames_from_tool_result(
    chunk: dict[str, Any],
    *,
    agent_id: str,
    workspace: BackendWorkspace,
) -> AsyncIterator[dict[str, Any]]:
    """Yield dashboard WS attachment frames with workspace download URLs."""
    messages = chunk.get("messages")
    if not isinstance(messages, list):
        return

    for message in messages:
        for block in iter_media_blocks(extract_message_content(message)):
            preview_url = block.get("preview_url")
            if not isinstance(preview_url, str) or not preview_url:
                raw_url, mime, filename = _block_file_refs(block)
                if raw_url:
                    preview_url = await resolve_dashboard_media_url(
                        workspace,
                        agent_id,
                        raw_url,
                        filename=filename,
                        mime=mime,
                    )

            btype = str(block.get("type") or "file")
            # File cards: derive download URL from path (absolute or relative).
            if btype == "file" and (not isinstance(preview_url, str) or not preview_url):
                raw_url, _, _ = _block_file_refs(block)
                file_path = _file_block_path(block, raw_url)
                if file_path:
                    preview_url = workspace_download_url(agent_id, file_path)

            if not preview_url:
                attachment = await _attachment_frame_from_bytes(block, workspace=workspace)
                if attachment:
                    yield attachment
                continue

            frame: dict[str, Any] = {
                "type": "attachment",
                "kind": _attachment_kind(btype),
                "url": preview_url,
                "preview_url": preview_url,
            }
            fn = block.get("filename")
            if isinstance(fn, str) and fn.strip():
                frame["filename"] = display_name_from_stored(fn.strip())
            if btype == "file":
                raw_url, _, _ = _block_file_refs(block)
                file_path = _file_block_path(block, raw_url) or _resolve_block_workspace_rel(
                    block, preview_url if isinstance(preview_url, str) else ""
                )
                if file_path:
                    frame["path"] = file_path
            block_mime = (
                block.get("mime_type")
                or block.get("media_type")
                or (
                    (block.get("source") or {}).get("media_type")
                    if isinstance(block.get("source"), dict)
                    else None
                )
            )
            if isinstance(block_mime, str) and block_mime:
                frame["mime_type"] = block_mime
            yield frame


async def _attachment_frame_from_bytes(
    block: dict[str, Any], *, workspace: BackendWorkspace
) -> dict[str, Any] | None:
    """Fallback: inline base64 when workspace import is impossible."""
    data = await read_media_block_bytes(block, workspace=workspace)
    if data is None:
        return None
    raw_bytes, block_mime = data
    btype = str(block.get("type") or "file")
    frame: dict[str, Any] = {
        "type": "attachment",
        "kind": _attachment_kind(btype),
        "mime_type": block_mime,
        "data": base64.b64encode(raw_bytes).decode("ascii"),
    }
    fn = block.get("filename")
    if isinstance(fn, str) and fn.strip():
        frame["filename"] = fn.strip()
    return frame


async def read_media_block_bytes(
    block: dict[str, Any],
    *,
    workspace: BackendWorkspace,
) -> tuple[bytes, str] | None:
    raw_source = block.get("source")
    source = raw_source if isinstance(raw_source, dict) else {}
    src_type = str(source.get("type") or "")
    raw_url, mime, filename = _block_file_refs(block)

    if src_type == "base64":
        payload = str(source.get("data") or "")
        if not payload:
            return None
        try:
            return base64.b64decode(payload), mime or "application/octet-stream"
        except (ValueError, TypeError):
            return None

    if not raw_url.startswith("file://"):
        return None

    data = await read_file_url_bytes(workspace, raw_url, filename=filename, mime=mime)
    if data is None:
        return None
    guessed = mime or mimetypes.guess_type(filename or raw_url)[0] or "application/octet-stream"
    return data, guessed


async def block_to_content_part(
    block: dict[str, Any],
    *,
    workspace: BackendWorkspace,
) -> ContentPart | None:
    btype = block.get("type")
    if btype not in _MEDIA_BLOCK_TYPES:
        return None

    source = block.get("source") or {}
    src_type = source.get("type") or ""
    raw_url, mime, filename = _block_file_refs(block)

    local_path: str | None = None
    url_field = ""
    data_field: str | None = None

    # v1 standard: top-level base64 + mime_type (LangChain / MediaOffload format)
    if "base64" in block and block["base64"]:
        data_field = block["base64"]
        mime = mime or block.get("mime_type", "") or ""
        filename = filename or block.get("filename", "") or ""
    elif src_type == "base64":
        payload = source.get("data", "") or ""
        if not payload:
            return None
        data_field = payload
    elif raw_url.startswith("file://"):
        file_bytes = await read_file_url_bytes(workspace, raw_url, filename=filename, mime=mime)
        if file_bytes is None:
            return None
        data_field = base64.b64encode(file_bytes).decode("ascii")
        if not mime:
            mime = mimetypes.guess_type(filename or raw_url)[0] or "application/octet-stream"
    elif raw_url:
        url_field = raw_url
    else:
        return None

    if btype == "image":
        return ImageContent(
            url=url_field,
            local_path=local_path,
            data=data_field,
            mime_type=mime or None,
        )
    if btype == "video":
        return VideoContent(
            url=url_field,
            local_path=local_path,
            data=data_field,
            mime_type=mime or None,
        )
    if btype == "audio":
        return AudioContent(
            url=url_field,
            local_path=local_path,
            data=data_field,
            mime_type=mime or None,
        )
    if btype == "file":
        return FileContent(
            url=url_field,
            local_path=local_path,
            data=data_field,
            filename=filename,
            mime_type=mime or None,
        )
    return None


async def media_events_from_tool_result(
    chunk: dict[str, Any],
    *,
    workspace: BackendWorkspace,
) -> AsyncIterator[MessageEvent]:
    messages = chunk.get("messages") or []
    if not isinstance(messages, list):
        return

    for message in messages:
        for block in iter_media_blocks(extract_message_content(message)):
            try:
                part = await block_to_content_part(block, workspace=workspace)
            except (FileNotFoundError, OSError, ValueError) as exc:
                logger.warning("tool_result media block: file missing: %s", exc)
                continue
            except Exception:
                logger.exception("tool_result media block: failed to resolve")
                continue
            if part is None:
                continue
            yield MessageEvent(type=MessageEventType.MESSAGE, content=[part])


__all__ = [
    "attachment_frames_from_tool_result",
    "block_to_content_part",
    "enrich_tool_output_string",
    "enrich_tool_result_for_dashboard",
    "enrich_tool_result_with_backend",
    "iter_media_blocks",
    "media_events_from_tool_result",
    "read_media_block_bytes",
]
