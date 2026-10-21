"""Return local workspace images to the current multimodal model."""

from __future__ import annotations

import asyncio
import base64
import io
import os
from dataclasses import dataclass
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from octop_harness.plugins import PluginContext
from PIL import Image, UnidentifiedImageError

_MAX_IMAGE_BYTES = 20 * 1024 * 1024
_MEDIA_TYPES = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "WEBP": "image/webp",
}
_SYSTEM_PROMPT = """You are a precise visual quality reviewer.
Inspect the supplied image itself. Do not rely on OCR or guess unseen content.
Report visible defects involving clipping, overlap, alignment, spacing,
contrast, hierarchy, incorrect relative-date labels, or other visual mistakes.
State uncertain observations explicitly and do not invent details."""


@dataclass(frozen=True)
class _LoadedImage:
    path: Path
    media_type: str
    data: bytes
    width: int
    height: int


def _error(message: str) -> str:
    return f"Error: {message}"


def _workspace_root() -> Path:
    home = Path(os.environ.get("OCTOP_HOME") or (Path.home() / ".octop")).expanduser()
    return (home / "workspaces").resolve()


def _load_image(path: str) -> _LoadedImage | str:
    raw = path.strip()
    if not raw:
        return _error("path is required")

    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate

    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError:
        return _error(f"image file not found: {raw}")
    except OSError as exc:
        return _error(f"cannot resolve image path: {exc}")

    allowed_root = _workspace_root()
    try:
        resolved.relative_to(allowed_root)
    except ValueError:
        return _error(f"path is outside the Octop workspaces directory: {resolved}")

    if not resolved.is_file():
        return _error(f"not a regular image file: {resolved}")

    try:
        size_bytes = resolved.stat().st_size
    except OSError as exc:
        return _error(f"cannot stat image file: {exc}")
    if size_bytes > _MAX_IMAGE_BYTES:
        return _error(f"image is too large: {size_bytes} bytes; maximum is {_MAX_IMAGE_BYTES}")

    try:
        data = resolved.read_bytes()
        with Image.open(io.BytesIO(data)) as image:
            image_format = str(image.format or "").upper()
            width, height = image.size
            image.verify()
    except Image.DecompressionBombError:
        return _error("image dimensions exceed Pillow safety limits")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        return _error(f"unsupported image format: {exc}")

    media_type = _MEDIA_TYPES.get(image_format)
    if media_type is None:
        return _error(
            f"unsupported image format {image_format or 'unknown'}; use PNG, JPEG, or WebP"
        )

    return _LoadedImage(
        path=resolved,
        media_type=media_type,
        data=data,
        width=width,
        height=height,
    )


def setup(ctx: PluginContext) -> None:
    async def inspect_image(path: str, focus: str = "") -> str:
        """Inspect a workspace image with the Agent's multimodal model."""
        loaded = await asyncio.to_thread(_load_image, path)
        if isinstance(loaded, str):
            return loaded

        encoded = base64.b64encode(loaded.data).decode("ascii")
        focus_text = focus.strip() or (
            "Review the overall visual quality and identify concrete defects."
        )
        messages = [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(
                content=[
                    {
                        "type": "text",
                        "text": (
                            f"Visually inspect {loaded.path.name} "
                            f"({loaded.width}x{loaded.height}).\nFocus: {focus_text}"
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{loaded.media_type};base64,{encoded}",
                        },
                    },
                ],
            ),
        ]
        try:
            access = ctx.get_model_access("auto", messages=messages)
            result = await access.ainvoke(messages)
        except Exception as exc:  # noqa: BLE001 — returned to the agent as a tool error
            detail = str(exc).strip()[:240] or exc.__class__.__name__
            return _error(f"visual review model call failed: {detail}")

        text = str(result).strip()
        if not text:
            return _error("visual review model returned an empty result")
        return text

    ctx.tool(
        "inspect_image",
        inspect_image,
        description=(
            "Inspect a local PNG, JPEG, or WebP image from the Octop workspace "
            "with the current multimodal model and return a textual visual-quality review. "
            "Call manually after generate_image when the generated image will be delivered "
            "or judged for visual quality. Pass the exact localPath returned by "
            "generate_image. Do not use read_file for images. This tool does not fetch URLs."
        ),
    )
