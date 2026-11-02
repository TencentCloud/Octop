"""Return local workspace images to the current multimodal model."""

from __future__ import annotations

import asyncio
import base64
import io
import os
from dataclasses import dataclass
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from octop_harness.llm.invoke_helpers import stringify_content
from octop_harness.plugins import PluginContext
from PIL import Image, UnidentifiedImageError

_MAX_IMAGE_BYTES = 20 * 1024 * 1024
_INTERNAL_LC_SOURCE = "image_inspector"
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


def _resolved(path: Path) -> Path:
    try:
        return path.expanduser().resolve()
    except OSError:
        return path.expanduser()


def _data_roots() -> list[Path]:
    candidates: list[Path] = []
    home = os.environ.get("OCTOP_HOME", "").strip()
    data_dir = os.environ.get("OCTOP_DATA_DIR", "").strip()
    if home:
        candidates.append(Path(home))
    if data_dir:
        candidates.append(Path(data_dir))
        if Path(data_dir).name != ".octop":
            candidates.append(Path(data_dir) / ".octop")
    candidates.append(Path.home() / ".octop")

    roots: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = _resolved(candidate)
        if resolved in seen:
            continue
        seen.add(resolved)
        roots.append(resolved)
    return roots


def _allowed_roots() -> list[Path]:
    roots: list[Path] = []
    for data_root in _data_roots():
        for name in ("agents", "workspaces"):
            roots.append((data_root / name).resolve())
    return roots


def _path_hint(raw: str) -> tuple[str, str, Path] | None:
    parts = [part for part in raw.replace("\\", "/").split("/") if part]
    for index, part in enumerate(parts):
        if part in {"agents", "workspaces"} and index + 2 < len(parts):
            return part, parts[index + 1], Path(*parts[index + 2 :])
    return None


def _path_is_allowed(path: Path) -> bool:
    for root in _allowed_roots():
        try:
            path.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def _candidate_paths(raw: str) -> list[Path]:
    candidate = Path(raw).expanduser()
    candidates = [candidate]
    normalized = raw.replace("\\", "/")
    hint = _path_hint(raw)

    for root in _data_roots():
        if normalized.startswith("/.octop/"):
            candidates.append(root / normalized.lstrip("/"))
        elif not candidate.is_absolute():
            candidates.append(root / candidate)

        if hint is None:
            continue
        namespace, agent_id, relative = hint
        for resolved_namespace in dict.fromkeys((namespace, "agents", "workspaces")):
            workspace = root / resolved_namespace / agent_id
            candidates.append(workspace / relative)
            candidates.append(workspace / ".harness-materialize" / relative)
    return candidates


def _unique_workspace_match(relative: Path) -> list[Path]:
    matches: list[Path] = []
    seen: set[Path] = set()
    for root in _allowed_roots():
        if not root.is_dir():
            continue
        try:
            workspaces = root.iterdir()
        except OSError:
            continue
        for workspace in workspaces:
            if not workspace.is_dir():
                continue
            for base in (workspace, workspace / ".harness-materialize"):
                candidate = base / relative
                try:
                    resolved = candidate.resolve(strict=True)
                except (FileNotFoundError, NotADirectoryError, OSError):
                    continue
                if resolved.is_file() and resolved not in seen:
                    seen.add(resolved)
                    matches.append(resolved)
    return matches


def _resolve_image_path(raw: str) -> Path | str:
    direct = Path(raw).expanduser()
    seen: set[Path] = set()
    for candidate in _candidate_paths(raw):
        try:
            resolved = candidate.resolve(strict=True)
        except (FileNotFoundError, NotADirectoryError):
            continue
        except OSError:
            # A sandbox-facing path may be inaccessible on the host. Try the
            # allowed data-root/materialized candidates before reporting failure.
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        if _path_is_allowed(resolved):
            return resolved

    if not direct.is_absolute() and _path_hint(raw) is None:
        matches = _unique_workspace_match(direct)
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            return _error(f"relative image path is ambiguous across agent workspaces: {raw}")

    if direct.is_absolute():
        direct_resolved: Path | None
        try:
            direct_resolved = direct.resolve(strict=True)
        except (FileNotFoundError, NotADirectoryError):
            direct_resolved = None
        except OSError as exc:
            return _error(f"cannot resolve image path: {exc}")
        if direct_resolved is not None:
            return _error("path is outside the Octop agents/workspaces directories")

    return _error(
        f"image file not found: {raw}. If it was created in a sandbox backend, "
        "materialize it first with send_file_to_user or pass the .harness-materialize path."
    )


def _load_image(path: str) -> _LoadedImage | str:
    raw = path.strip()
    if not raw:
        return _error("path is required")

    resolved = _resolve_image_path(raw)
    if isinstance(resolved, str):
        return resolved

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
            # The parent LangGraph stream must not expose this nested review call.
            result = await access.chat_model.ainvoke(
                messages,
                config={
                    "callbacks": [],
                    "metadata": {"lc_source": _INTERNAL_LC_SOURCE},
                },
            )
        except Exception as exc:  # noqa: BLE001 — returned to the agent as a tool error
            detail = str(exc).strip()[:240] or exc.__class__.__name__
            return _error(f"visual review model call failed: {detail}")

        text = stringify_content(getattr(result, "content", result))
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
