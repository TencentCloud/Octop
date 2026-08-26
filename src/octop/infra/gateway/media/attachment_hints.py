"""Agent-facing inbound attachment routing — vision bytes vs tool path hints."""

from __future__ import annotations

import asyncio
import base64
import logging
import mimetypes
from collections.abc import Sequence
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any

from harness_gateway.models import (
    AudioContent,
    ContentPart,
    FileContent,
    ImageContent,
    VideoContent,
)

from octop.i18n.domains.attachment import (
    attachment_image_unavailable,
    attachment_path_hint,
)
from octop.infra.gateway.media.inbound_store import (
    display_name_from_stored,
    inbound_rel_path,
    resolve_inbound_attachment_path,
)
from octop.infra.utils.locale import Locale

if TYPE_CHECKING:
    from harness_agent.backends.workspace import BackendWorkspace
    from harness_gateway.media import MediaBackend

logger = logging.getLogger(__name__)

_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg")
_VISION_BLOCK_TYPES = frozenset({"image", "image_url", "input_image"})

# Vision materialize limits — oversized / excess images become path hints.
VISION_MAX_BYTES = 2 * 1024 * 1024
VISION_MAX_COUNT = 4
# Re-encode target: vision models commonly resize to ~1568 px on the longest
# edge. JPEG at that size keeps even a worst-case (noisy) image under
# VISION_MAX_BYTES.
VISION_MAX_SIDE = 1568
VISION_JPEG_QUALITY = 85


def is_image_media_type(media_type: str) -> bool:
    return media_type.split(";", 1)[0].strip().lower().startswith("image/")


def is_av_media_type(media_type: str) -> bool:
    return media_type.split(";", 1)[0].strip().lower().startswith(("video/", "audio/"))


def is_preview_media_type(media_type: str) -> bool:
    """True when the dashboard can inline-preview (image / audio / video)."""
    return is_image_media_type(media_type) or is_av_media_type(media_type)


def is_image_workspace_path(path: str) -> bool:
    return path.lower().endswith(_IMAGE_EXTENSIONS)


def is_image_inbound(*, media_type: str, path: str = "") -> bool:
    """True when bytes should be embedded for the vision model."""
    return is_image_media_type(media_type) or bool(path and is_image_workspace_path(path))


def _block_needs_vision(block: object) -> bool:
    return isinstance(block, dict) and str(block.get("type") or "") in _VISION_BLOCK_TYPES


def content_blocks_need_vision(content: Any) -> bool:
    """True when a harness user ``content`` list includes image blocks."""
    if not isinstance(content, list):
        return False
    return any(_block_needs_vision(block) for block in content)


def is_vision_attachment(
    *,
    kind: str = "",
    media_type: str = "",
    path: str = "",
) -> bool:
    """Attachment routing: vision block vs workspace path hint."""
    if kind == "image":
        return True
    return is_image_inbound(media_type=media_type, path=path)


def sniff_image_media_type(data: bytes) -> str | None:
    """Detect common image formats when the client sends ``application/octet-stream``."""
    if len(data) >= 8 and data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if len(data) >= 3 and data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if len(data) >= 6 and data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


@dataclass(frozen=True)
class InboundAttachmentMeta:
    path: str
    filename: str
    media_type: str


def format_attachment_path_hint(
    *,
    filename: str,
    path: str,
    media_type: str,
    size: int | None = None,
    locale: str | Locale = "en",
) -> str:
    """Workspace path hint for agent tools — never inline file bytes."""
    return attachment_path_hint(
        filename=filename,
        path=path,
        media_type=media_type,
        size=size,
        locale=locale,
    )


def path_hint_content_block(
    meta: InboundAttachmentMeta,
    *,
    workspace: BackendWorkspace | None = None,
    locale: str | Locale = "en",
) -> dict[str, Any]:
    display_path = (
        resolve_inbound_attachment_path(workspace, meta.path)
        if workspace is not None
        else meta.path
    )
    return {
        "type": "text",
        "text": format_attachment_path_hint(
            filename=meta.filename,
            path=display_path,
            media_type=meta.media_type,
            locale=locale,
        ),
    }


def _append_path_hint(
    hints: list[str],
    *,
    local_path: str,
    filename: str,
    media_type: str,
    size: int | None,
    workspace: BackendWorkspace | None,
    locale: str | Locale,
) -> None:
    rel = inbound_rel_path(local_path)
    display_path = resolve_inbound_attachment_path(workspace, rel) if workspace is not None else rel
    hints.append(
        format_attachment_path_hint(
            filename=filename,
            path=display_path,
            media_type=media_type,
            size=size,
            locale=locale,
        )
    )


def hints_from_content_parts(
    parts: Sequence[ContentPart],
    *,
    workspace: BackendWorkspace | None = None,
    locale: str | Locale = "en",
    skip_vision_images: bool = True,
) -> list[str]:
    """Path hints for non-vision attachments (files, audio, video, oversized images)."""
    hints: list[str] = []
    for part in parts:
        if isinstance(part, FileContent):
            if not part.local_path:
                continue
            rel = inbound_rel_path(part.local_path)
            media_type = part.mime_type or "application/octet-stream"
            if skip_vision_images and is_vision_attachment(media_type=media_type, path=rel):
                continue
            _append_path_hint(
                hints,
                local_path=part.local_path,
                filename=part.filename or "attachment",
                media_type=media_type,
                size=part.size,
                workspace=workspace,
                locale=locale,
            )
        elif isinstance(part, AudioContent):
            if not part.local_path:
                continue
            _append_path_hint(
                hints,
                local_path=part.local_path,
                filename="audio",
                media_type=part.mime_type or "audio/mpeg",
                size=part.size,
                workspace=workspace,
                locale=locale,
            )
        elif isinstance(part, VideoContent):
            if not part.local_path:
                continue
            _append_path_hint(
                hints,
                local_path=part.local_path,
                filename="video",
                media_type=part.mime_type or "video/mp4",
                size=part.size,
                workspace=workspace,
                locale=locale,
            )
        elif isinstance(part, ImageContent) and not skip_vision_images:
            if not part.local_path:
                continue
            rel = inbound_rel_path(part.local_path)
            _append_path_hint(
                hints,
                local_path=part.local_path,
                filename=Path(rel).name or "image",
                media_type=part.mime_type or "image/png",
                size=part.size,
                workspace=workspace,
                locale=locale,
            )
    return hints


WORKSPACE_IMAGE_SCHEME = "workspace://"


def make_image_url_block(b64_data: str, mime_type: str) -> dict[str, Any]:
    return {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64_data}"}}


def make_workspace_image_ref(*, workspace_path: str, mime_type: str) -> dict[str, Any]:
    """Checkpoint-safe vision block: path only; bytes materialize at model-call time."""
    rel = inbound_rel_path(workspace_path)
    return {
        "type": "image_url",
        "workspace_path": rel,
        "mime_type": mime_type or "image/png",
        "image_url": {"url": f"{WORKSPACE_IMAGE_SCHEME}{rel}"},
    }


def is_workspace_image_ref(block: object) -> bool:
    """True when *block* is a path-only vision ref (not yet a data URI)."""
    if not isinstance(block, dict) or str(block.get("type") or "") != "image_url":
        return False
    url_field = block.get("image_url")
    url = ""
    if isinstance(url_field, dict):
        url = str(url_field.get("url") or "")
    elif isinstance(url_field, str):
        url = url_field
    if url.startswith("data:"):
        return False
    if str(block.get("workspace_path") or "").strip():
        return True
    return url.startswith(WORKSPACE_IMAGE_SCHEME)


def workspace_path_from_image_ref(block: dict[str, Any]) -> str:
    path = str(block.get("workspace_path") or "").strip()
    if path:
        return inbound_rel_path(path)
    url_field = block.get("image_url")
    url = ""
    if isinstance(url_field, dict):
        url = str(url_field.get("url") or "")
    elif isinstance(url_field, str):
        url = url_field
    if url.startswith(WORKSPACE_IMAGE_SCHEME):
        return inbound_rel_path(url[len(WORKSPACE_IMAGE_SCHEME) :])
    return ""


def inbound_attachments_from_parts(parts: Sequence[ContentPart]) -> list[dict[str, str]]:
    """Snapshot attachment metadata from ContentParts for history UI."""
    attachments: list[dict[str, str]] = []
    for part in parts:
        if isinstance(part, ImageContent):
            path = inbound_rel_path(part.local_path) if part.local_path else ""
            media_type = part.mime_type or "image/png"
            filename = display_name_from_stored(Path(path).name) if path else "image"
            kind = "image"
        elif isinstance(part, FileContent):
            path = inbound_rel_path(part.local_path) if part.local_path else ""
            media_type = part.mime_type or "application/octet-stream"
            filename = part.filename or (
                display_name_from_stored(Path(path).name) if path else "attachment"
            )
            kind = "image" if is_vision_attachment(media_type=media_type, path=path) else "file"
        else:
            continue
        if not path:
            continue
        entry: dict[str, str] = {
            "filename": filename,
            "media_type": media_type,
            "kind": kind,
            "workspace_path": path,
        }
        attachments.append(entry)
    return attachments


def _image_unavailable_block(*, locale: str | Locale = "en") -> dict[str, Any]:
    return {"type": "text", "text": attachment_image_unavailable(locale)}


def _image_as_path_hint(
    part: ImageContent,
    *,
    workspace: BackendWorkspace | None,
    locale: str | Locale = "en",
) -> dict[str, Any]:
    path = inbound_rel_path(part.local_path) if part.local_path else ""
    if not path:
        return _image_unavailable_block(locale=locale)
    return path_hint_content_block(
        InboundAttachmentMeta(
            path=path,
            filename=Path(path).name or "image",
            media_type=part.mime_type or "image/png",
        ),
        workspace=workspace,
        locale=locale,
    )


def _encoded_image_fits(img: Any, fmt: str, *, ref: bytes, **save_kwargs: Any) -> bytes | None:
    """Encode ``img``; return the bytes only when smaller than ``ref`` and under the limit."""
    buf = BytesIO()
    img.save(buf, format=fmt, **save_kwargs)
    out = buf.getvalue()
    return out if out and len(out) < len(ref) and len(out) <= VISION_MAX_BYTES else None


def _reencode_image_to_fit(data: bytes) -> tuple[bytes, str] | None:
    """Downscale and re-encode ``data`` to fit :data:`VISION_MAX_BYTES`.

    Returns ``(bytes, mime_type)`` for the re-encoded image, or ``None`` when
    Pillow is unavailable, the bytes are not decodable, or re-encoding cannot
    shrink them under the limit (the caller keeps the path-hint fallback).
    """
    try:
        from PIL import Image, ImageOps  # noqa: PLC0415
    except ImportError:  # Pillow not installed — keep legacy path-hint behaviour.
        return None
    try:
        with Image.open(BytesIO(data)) as src:
            img = ImageOps.exif_transpose(src)
            img.thumbnail((VISION_MAX_SIDE, VISION_MAX_SIDE), Image.Resampling.LANCZOS)
            has_alpha = img.mode in ("RGBA", "LA") or (
                img.mode == "P" and "transparency" in img.info
            )
            if has_alpha:
                rgba = img.convert("RGBA")
                # Keep alpha when it fits (transparent PNG / WebP / GIF).
                png = _encoded_image_fits(rgba, "PNG", ref=data, optimize=True)
                if png is not None:
                    return png, "image/png"
                # PNG too large — flatten alpha onto white and fall through to JPEG.
                canvas = Image.new("RGB", rgba.size, (255, 255, 255))
                canvas.paste(rgba, mask=rgba.getchannel("A"))
                img = canvas
            elif img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            jpeg = _encoded_image_fits(
                img, "JPEG", ref=data, quality=VISION_JPEG_QUALITY, optimize=True
            )
            if jpeg is not None:
                return jpeg, "image/jpeg"
    except Exception:
        logger.warning("vision image re-encode failed for %d bytes", len(data), exc_info=True)
    return None


async def materialize_image_part(
    part: ImageContent,
    *,
    media_backend: MediaBackend | None,
    workspace: BackendWorkspace | None = None,
    locale: str | Locale = "en",
) -> dict[str, Any] | None:
    """Build a checkpoint-safe vision block, or degrade to a path hint.

    Prefer workspace path refs for files already under ``inbound/`` — bytes are
    inlined only at LLM request time (see ``WorkspaceImageMaterializeMiddleware``).
    Inline ``part.data`` / remote URL downloads without a rematerializable path
    still produce ``data:`` URLs here (with size re-encode when needed).
    """
    mime = part.mime_type or "image/png"

    # Path-backed images: store a ref only (plan B). Do not inline base64 into
    # the checkpoint / history — rematerialize in wrap_model_call.
    if part.local_path:
        rel = inbound_rel_path(part.local_path)
        guessed = part.mime_type or mimetypes.guess_type(part.local_path)[0] or "image/png"
        # Without a media backend / workspace we cannot rematerialize later —
        # degrade to a tool path hint instead of a dangling workspace:// ref.
        if media_backend is None and workspace is None:
            return _image_as_path_hint(part, workspace=workspace, locale=locale)
        if media_backend is not None:
            data: bytes | None = None
            try:
                data = await media_backend.read(part.local_path)
            except (FileNotFoundError, OSError, RuntimeError):
                data = None
            if data is None:
                local = media_backend.get_local_path(part.local_path)
                if local is not None and Path(local).is_file():
                    data = Path(local).read_bytes()
            if data is None and workspace is not None:
                try:
                    data = await workspace.adownload_bytes(rel)
                except Exception:
                    data = None
            if data is None:
                return _image_as_path_hint(part, workspace=workspace, locale=locale)
        return make_workspace_image_ref(workspace_path=rel, mime_type=guessed)

    if part.data:
        try:
            raw = base64.b64decode(part.data, validate=False)
        except Exception:
            return _image_unavailable_block(locale=locale)
        if len(raw) > VISION_MAX_BYTES:
            logger.info(
                "vision inline image %d bytes > %d, re-encoding",
                len(raw),
                VISION_MAX_BYTES,
            )
            reencoded = await asyncio.to_thread(_reencode_image_to_fit, raw)
            if reencoded is not None:
                return make_image_url_block(base64.b64encode(reencoded[0]).decode(), reencoded[1])
            return _image_as_path_hint(part, workspace=workspace, locale=locale)
        return make_image_url_block(part.data, mime)

    if part.url:
        downloaded = await _download_image_url(part.url)
        if downloaded is not None:
            raw_bytes, content_type = downloaded
            if len(raw_bytes) > VISION_MAX_BYTES:
                logger.info(
                    "vision url image: %d bytes > %d, re-encoding",
                    len(raw_bytes),
                    VISION_MAX_BYTES,
                )
                reencoded = await asyncio.to_thread(_reencode_image_to_fit, raw_bytes)
                if reencoded is not None:
                    return make_image_url_block(
                        base64.b64encode(reencoded[0]).decode(), reencoded[1]
                    )
                return _image_as_path_hint(part, workspace=workspace, locale=locale)
            mime = content_type or part.mime_type or "image/png"
            return make_image_url_block(base64.b64encode(raw_bytes).decode(), mime)
        if part.url.startswith(("http://", "https://")):
            return {"type": "image_url", "image_url": {"url": part.url}}

    return None


async def expand_workspace_image_ref(
    block: dict[str, Any],
    *,
    workspace: BackendWorkspace,
    locale: str | Locale = "en",
) -> dict[str, Any]:
    """Turn a path-only vision ref into an inlined ``data:`` block for the model.

    Used by :class:`WorkspaceImageMaterializeMiddleware` on the ephemeral
    model request only — never write the result back into checkpoint state.
    """
    if not is_workspace_image_ref(block):
        return block
    path = workspace_path_from_image_ref(block)
    if not path:
        return _image_unavailable_block(locale=locale)
    try:
        data = await workspace.adownload_bytes(path)
    except Exception:
        logger.warning("vision rematerialize failed for %s", path, exc_info=True)
        data = None
    # Re-encode (Pillow) must not block the event loop.
    return await asyncio.to_thread(
        _finalize_rematerialized_image,
        data,
        path=path,
        mime_type=str(block.get("mime_type") or ""),
        workspace=workspace,
        locale=locale,
    )


def expand_workspace_image_ref_sync(
    block: dict[str, Any],
    *,
    workspace: BackendWorkspace,
    locale: str | Locale = "en",
) -> dict[str, Any]:
    """Sync counterpart of :func:`expand_workspace_image_ref`."""
    if not is_workspace_image_ref(block):
        return block
    path = workspace_path_from_image_ref(block)
    if not path:
        return _image_unavailable_block(locale=locale)
    try:
        data = workspace.download_bytes(path)
    except Exception:
        logger.warning("vision rematerialize failed for %s", path, exc_info=True)
        data = None
    return _finalize_rematerialized_image(
        data,
        path=path,
        mime_type=str(block.get("mime_type") or ""),
        workspace=workspace,
        locale=locale,
    )


def _finalize_rematerialized_image(
    data: bytes | None,
    *,
    path: str,
    mime_type: str,
    workspace: BackendWorkspace,
    locale: str | Locale,
) -> dict[str, Any]:
    if not data:
        return path_hint_content_block(
            InboundAttachmentMeta(
                path=path,
                filename=Path(path).name or "image",
                media_type=mime_type or "image/png",
            ),
            workspace=workspace,
            locale=locale,
        )
    mime = mime_type or mimetypes.guess_type(path)[0] or "image/png"
    if len(data) > VISION_MAX_BYTES:
        logger.info(
            "vision rematerialize %s: %d bytes > %d, re-encoding",
            path,
            len(data),
            VISION_MAX_BYTES,
        )
        reencoded = _reencode_image_to_fit(data)
        if reencoded is not None:
            out = make_image_url_block(base64.b64encode(reencoded[0]).decode(), reencoded[1])
            out["workspace_path"] = path
            return out
        return path_hint_content_block(
            InboundAttachmentMeta(
                path=path,
                filename=Path(path).name or "image",
                media_type=mime,
            ),
            workspace=workspace,
            locale=locale,
        )
    out = make_image_url_block(base64.b64encode(data).decode(), mime)
    out["workspace_path"] = path
    return out


async def _download_image_url(url: str) -> tuple[bytes, str] | None:
    if not url.startswith(("http://", "https://")):
        return None
    import aiohttp  # noqa: PLC0415

    try:
        async with (
            aiohttp.ClientSession() as session,
            session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp,
        ):
            if resp.status != 200:
                return None
            content_type = resp.content_type or "image/png"
            data = await resp.read()
            if not data:
                return None
            return data, content_type
    except Exception:
        return None


__all__ = [
    "VISION_MAX_BYTES",
    "VISION_MAX_COUNT",
    "VISION_MAX_SIDE",
    "WORKSPACE_IMAGE_SCHEME",
    "InboundAttachmentMeta",
    "content_blocks_need_vision",
    "expand_workspace_image_ref",
    "expand_workspace_image_ref_sync",
    "format_attachment_path_hint",
    "hints_from_content_parts",
    "inbound_attachments_from_parts",
    "is_av_media_type",
    "is_image_inbound",
    "is_image_media_type",
    "is_preview_media_type",
    "is_vision_attachment",
    "is_workspace_image_ref",
    "make_image_url_block",
    "make_workspace_image_ref",
    "materialize_image_part",
    "path_hint_content_block",
    "sniff_image_media_type",
    "workspace_path_from_image_ref",
]
