"""Built-in ``generate_image`` and ``generate_video`` tools."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from langchain_core.tools import ToolException, tool
from pydantic import BaseModel, Field, ValidationError
from pydantic.v1 import ValidationError as ValidationErrorV1

from octop_harness.backends.workspace import BackendWorkspace
from octop_harness.config import MediaGenerationConfig
from octop_harness.media.base import MediaGenerationProvider
from octop_harness.media.errors import MediaGenerationError
from octop_harness.media.manager import MediaManager
from octop_harness.media.models import (
    ImageGenerationRequest,
    MediaGenerationResult,
    StoredMedia,
    VideoGenerationRequest,
)
from octop_harness.media.registry import create_media_manager

_IMAGE_DESCRIPTION = """Generate or edit images from text and optional reference images.

Use for text-to-image, image-to-image, illustration, photo, poster, icon, or
visual transformation requests. Do not use for image analysis. This operation
may be billable. Provider/model and retry/fallback are selected by the runtime;
do not retry manually after an error. Outputs are saved in the agent workspace.
"""

_VIDEO_DESCRIPTION = """Generate a video from text and optional frame or reference images.

Use for text-to-video, image-to-video, animation, and cinematic scene requests.
Do not use for video analysis or trimming existing videos. This operation is
billable and may take minutes. The runtime selects the provider/model; do not
retry manually after an error. Outputs are saved in the agent workspace.
"""


class GenerateImageInput(BaseModel):
    """Provider-neutral arguments exposed by ``generate_image``."""

    prompt: str = Field(
        min_length=1,
        description=(
            "Describe the subject, composition, style, lighting, and any exact text to render. "
            "For editing, describe only the requested changes."
        ),
    )
    reference_images: list[str] | None = Field(
        default=None,
        description=(
            "Optional workspace paths, HTTP(S) URLs, or data URLs supplied by the user. "
            "Use for editing or visual consistency; never invent a path."
        ),
    )
    size: str | None = Field(
        default=None,
        description=(
            "Optional preferred output size. Leave unset unless the user requests one; "
            "the runtime chooses a provider-compatible default."
        ),
    )
    count: int = Field(
        default=1,
        ge=1,
        le=4,
        description="Number of images. Request more than one only when the user asks for variants.",
    )
    seed: int | None = Field(
        default=None,
        description="Optional reproducibility seed. Leave unset unless reproducibility is requested.",
    )
    watermark: bool = Field(
        default=False,
        description="Whether the provider should add a watermark.",
    )


class GenerateVideoInput(BaseModel):
    """Provider-neutral arguments exposed by ``generate_video``."""

    prompt: str = Field(
        min_length=1,
        description=("Describe the scene, subject motion, camera movement, timing, and audio intent."),
    )
    first_frame: str | None = Field(
        default=None,
        description="Optional user-supplied starting-frame workspace path, HTTP(S) URL, or data URL.",
    )
    last_frame: str | None = Field(
        default=None,
        description="Optional user-supplied ending-frame workspace path, HTTP(S) URL, or data URL.",
    )
    reference_images: list[str] | None = Field(
        default=None,
        description=("Optional user-supplied subject or style references. Never invent workspace paths."),
    )
    duration: int = Field(
        default=5,
        ge=4,
        le=15,
        description="Requested duration in seconds. Keep the default unless the user asks otherwise.",
    )
    aspect_ratio: str = Field(
        default="16:9",
        min_length=3,
        description="Output aspect ratio such as 16:9 or 9:16.",
    )
    resolution: str = Field(
        default="720p",
        min_length=2,
        description=("Preferred provider-supported resolution. Keep 720p unless the user requests higher quality."),
    )
    generate_audio: bool = Field(
        default=False,
        description=(
            "Generate synchronized audio only when the user requests sound and the selected model supports it."
        ),
    )
    seed: int | None = Field(
        default=None,
        description="Optional reproducibility seed. Leave unset unless reproducibility is requested.",
    )
    watermark: bool = Field(
        default=False,
        description="Whether the provider should add a watermark.",
    )


def _tool_error_formatter(
    *,
    result_type: str,
    tool_name: str,
    provider: str,
    model: str,
) -> Callable[[ToolException], str]:
    def format_error(error: ToolException) -> str:
        if not isinstance(error, MediaGenerationError):
            return str(error)
        payload = error.to_tool_result(
            result_type=result_type,
            tool_name=tool_name,
            provider=provider,
            model=model,
        )
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    return format_error


def _validation_error_formatter(
    *,
    result_type: str,
    tool_name: str,
    provider: str,
    model: str,
) -> Callable[[ValidationError | ValidationErrorV1], str]:
    def format_error(error: ValidationError | ValidationErrorV1) -> str:
        details = "; ".join(f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}" for item in error.errors())
        tool_error = MediaGenerationError(
            f"Invalid media generation arguments: {details}",
            code="invalid_request",
            category="validation",
            safe_to_resubmit=True,
            remediation="adjust_request",
            model_instruction="Correct the invalid arguments, then call the tool at most once more.",
        )
        return json.dumps(
            tool_error.to_tool_result(
                result_type=result_type,
                tool_name=tool_name,
                provider=provider,
                model=model,
            ),
            ensure_ascii=False,
            separators=(",", ":"),
        )

    return format_error


def _request_error(exc: ValueError | FileNotFoundError) -> MediaGenerationError:
    if isinstance(exc, FileNotFoundError):
        return MediaGenerationError(
            str(exc),
            code="reference_not_found",
            category="validation",
            remediation="choose_reference",
            model_instruction=("Do not invent another path. Ask the user to provide an existing reference image."),
        )
    return MediaGenerationError(
        str(exc),
        code="invalid_request",
        category="validation",
        safe_to_resubmit=True,
        remediation="adjust_request",
        model_instruction="Correct the invalid arguments, then call the tool at most once more.",
    )


def _media_result_payload(result: MediaGenerationResult) -> dict[str, object]:
    """Render a manager result into the stable tool-result envelope."""
    singular = result.kind
    plural = "images" if result.kind == "image" else "videos"
    execution: dict[str, object] = {
        "provider": result.provider_type,
        "model": result.model,
        "fallback_used": False,
    }
    if result.provider_id != result.provider_type:
        execution["provider_instance"] = result.provider_id
    if result.provider_task_id is not None:
        execution["provider_task_id"] = result.provider_task_id
    return {
        "schema_version": 1,
        "type": f"{singular}_gen_tool_result",
        "tool": f"generate_{singular}",
        "prompt": result.prompt,
        "status": "completed",
        "is_error": False,
        "message": f"Generated {len(result.artifacts)} {singular} artifact(s).",
        "provider": result.provider_type,
        "model": result.model,
        "error": None,
        "remediation": None,
        "execution": execution,
        plural: [_stored_payload(item) for item in result.artifacts],
    }


def _stored_payload(item: StoredMedia) -> dict[str, object]:
    return {
        "localPath": item.local_path,
        "path": item.path,
        "mediaType": item.media_type,
        "sizeBytes": item.size_bytes,
    }


def build_media_generation_tools(
    workspace: BackendWorkspace,
    config: MediaGenerationConfig,
    *,
    provider: MediaGenerationProvider | None = None,
    manager: MediaManager | None = None,
) -> list[Any]:
    """Build workspace-bound media tools routed through one manager."""
    if provider is not None and manager is not None:
        raise ValueError("provider and manager are mutually exclusive")
    if manager is not None:
        resolved_manager = manager
    elif provider is not None:
        resolved_manager = MediaManager(workspace, output_dir=config.output_dir)
        resolved_manager.add_provider(
            provider.provider_id,
            provider,
            image_enabled=config.image_enabled,
            video_enabled=config.video_enabled,
        )
    else:
        resolved_manager = create_media_manager(config, workspace)

    @tool(args_schema=GenerateImageInput, description=_IMAGE_DESCRIPTION)
    async def generate_image(
        prompt: str,
        *,
        reference_images: list[str] | None = None,
        size: str | None = None,
        count: int = 1,
        seed: int | None = None,
        watermark: bool = False,
    ) -> dict[str, object]:
        try:
            result = await resolved_manager.generate_image(
                ImageGenerationRequest(
                    prompt=prompt,
                    reference_images=tuple(reference_images or ()),
                    size=size,
                    count=count,
                    seed=seed,
                    watermark=watermark,
                )
            )
            return _media_result_payload(result)
        except MediaGenerationError:
            raise
        except (ValueError, FileNotFoundError) as exc:
            raise _request_error(exc) from exc

    @tool(args_schema=GenerateVideoInput, description=_VIDEO_DESCRIPTION)
    async def generate_video(
        prompt: str,
        *,
        first_frame: str | None = None,
        last_frame: str | None = None,
        reference_images: list[str] | None = None,
        duration: int = 5,
        aspect_ratio: str = "16:9",
        resolution: str = "720p",
        generate_audio: bool = False,
        seed: int | None = None,
        watermark: bool = False,
    ) -> dict[str, object]:
        try:
            result = await resolved_manager.generate_video(
                VideoGenerationRequest(
                    prompt=prompt,
                    first_frame=first_frame,
                    last_frame=last_frame,
                    reference_images=tuple(reference_images or ()),
                    duration=duration,
                    aspect_ratio=aspect_ratio,
                    resolution=resolution,
                    generate_audio=generate_audio,
                    seed=seed,
                    watermark=watermark,
                )
            )
            return _media_result_payload(result)
        except MediaGenerationError:
            raise
        except (ValueError, FileNotFoundError) as exc:
            raise _request_error(exc) from exc

    tools: list[Any] = []
    image_available = manager is not None or provider is not None or config.has_image_provider()
    video_available = manager is not None or provider is not None or config.has_video_provider()
    if image_available and resolved_manager.has_route("image"):
        image_route = resolved_manager.route_info("image")
        generate_image.handle_tool_error = _tool_error_formatter(
            result_type="image_gen_tool_result",
            tool_name="generate_image",
            provider=image_route.provider_type,
            model=image_route.model,
        )
        generate_image.handle_validation_error = _validation_error_formatter(
            result_type="image_gen_tool_result",
            tool_name="generate_image",
            provider=image_route.provider_type,
            model=image_route.model,
        )
        tools.append(generate_image)
    if video_available and resolved_manager.has_route("video"):
        video_route = resolved_manager.route_info("video")
        generate_video.handle_tool_error = _tool_error_formatter(
            result_type="video_gen_tool_result",
            tool_name="generate_video",
            provider=video_route.provider_type,
            model=video_route.model,
        )
        generate_video.handle_validation_error = _validation_error_formatter(
            result_type="video_gen_tool_result",
            tool_name="generate_video",
            provider=video_route.provider_type,
            model=video_route.model,
        )
        tools.append(generate_video)
    return tools
