"""Alibaba Cloud Model Studio adapters for Wan image and video models."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from octop_harness.media.errors import MediaGenerationError
from octop_harness.media.http import BearerJsonMediaProvider, provider_payload_error
from octop_harness.media.models import (
    ImageGenerationRequest,
    MediaCapabilities,
    MediaJobUpdate,
    MediaSubmission,
    ProviderTask,
    RemoteArtifact,
    VideoGenerationRequest,
)

_ASYNC_HEADERS = {"X-DashScope-Async": "enable"}
_MULTIMODAL_IMAGE_PREFIXES = (
    "qwen-image-3.0",
    "wan2.6-image",
    "wan2.6-t2i",
    "wan2.7-image",
)
_REFERENCE_IMAGE_PREFIXES = ("qwen-image-3.0", "wan2.6-image", "wan2.7-image")


class DashScopeMediaProvider(BearerJsonMediaProvider):
    """Call Wan image and video APIs through DashScope HTTP endpoints."""

    provider_id = "dashscope"
    capabilities = MediaCapabilities(
        image_references=True,
        video_first_frame=True,
        video_last_frame=True,
        video_references=True,
        video_audio=True,
    )

    async def _submit_image(
        self,
        client: httpx.AsyncClient,
        request: ImageGenerationRequest,
    ) -> MediaSubmission:
        parameters: dict[str, Any] = {
            "n": request.count,
            "watermark": request.watermark,
        }
        if request.size:
            parameters["size"] = request.size.replace("X", "*").replace("x", "*")
        if request.seed is not None:
            parameters["seed"] = request.seed

        if self.image_model.startswith(_MULTIMODAL_IMAGE_PREFIXES):
            if request.reference_images and not self.image_model.startswith(_REFERENCE_IMAGE_PREFIXES):
                raise _unsupported(
                    f"The configured DashScope model {self.image_model} does not accept reference images."
                )
            content = [{"image": image} for image in request.reference_images]
            content.append({"text": request.prompt})
            body = {
                "model": self.image_model,
                "input": {
                    "messages": [
                        {
                            "role": "user",
                            "content": content,
                        }
                    ]
                },
                "parameters": parameters,
            }
            payload = await self._request_json(
                client,
                "POST",
                "/services/aigc/multimodal-generation/generation",
                json=body,
            )
            _raise_dashscope_payload_error(payload, fallback="DashScope image generation failed")
            artifacts = _choice_image_artifacts(payload.get("output"))
            if not artifacts:
                raise MediaGenerationError("DashScope image generation returned no usable images")
            return MediaSubmission(artifacts=artifacts)

        if request.reference_images:
            raise _unsupported(f"The configured DashScope model {self.image_model} does not accept reference images.")
        body = {
            "model": self.image_model,
            "input": {"prompt": request.prompt},
            "parameters": parameters,
        }
        payload = await self._request_json(
            client,
            "POST",
            "/services/aigc/text2image/image-synthesis",
            json=body,
            headers=_ASYNC_HEADERS,
        )
        task_id = _dashscope_task_id(payload, fallback="DashScope image generation did not return a task id")
        return MediaSubmission(task=ProviderTask(task_id=task_id, kind="image", model=self.image_model))

    async def _submit_video(
        self,
        client: httpx.AsyncClient,
        request: VideoGenerationRequest,
    ) -> MediaSubmission:
        parameters: dict[str, Any] = {
            "resolution": request.resolution.upper(),
            "ratio": request.aspect_ratio,
            "duration": request.duration,
            "watermark": request.watermark,
        }
        if request.seed is not None:
            parameters["seed"] = request.seed
        input_payload: dict[str, Any] = {"prompt": request.prompt}
        if self.video_model.startswith("wan3.0-video"):
            media = _wan_video_media(request)
            if media:
                input_payload["media"] = media
                parameters["ratio"] = "adaptive" if request.first_frame else request.aspect_ratio
            parameters["audio"] = request.generate_audio
        elif self.video_model.startswith("wan2.7-i2v"):
            if request.reference_images:
                raise _unsupported("Wan 2.7 image-to-video does not accept reference images.")
            if not request.first_frame:
                raise _unsupported("Wan 2.7 image-to-video requires a first frame.")
            media = [{"type": "first_frame", "url": request.first_frame}]
            if request.last_frame:
                media.append({"type": "last_frame", "url": request.last_frame})
            input_payload["media"] = media
            parameters.pop("ratio", None)
        elif self.video_model.startswith("wan2.7-r2v"):
            if request.last_frame:
                raise _unsupported("Wan 2.7 reference-to-video does not accept a last frame.")
            media = _wan_reference_video_media(request)
            if not media:
                raise _unsupported("Wan 2.7 reference-to-video requires a frame or reference image.")
            input_payload["media"] = media
        elif request.first_frame or request.last_frame or request.reference_images:
            raise _unsupported(
                f"The configured DashScope model {self.video_model} does not accept frame or reference images."
            )
        body = {
            "model": self.video_model,
            "input": input_payload,
            "parameters": parameters,
        }
        payload = await self._request_json(
            client,
            "POST",
            "/services/aigc/video-generation/video-synthesis",
            json=body,
            headers=_ASYNC_HEADERS,
        )
        task_id = _dashscope_task_id(payload, fallback="DashScope video generation did not return a task id")
        return MediaSubmission(task=ProviderTask(task_id=task_id, kind="video", model=self.video_model))

    async def _poll_task(
        self,
        client: httpx.AsyncClient,
        task: ProviderTask,
    ) -> MediaJobUpdate:
        payload = await self._request_json(
            client,
            "GET",
            f"/tasks/{task.task_id}",
            provider_task_id=task.task_id,
        )
        _raise_dashscope_payload_error(
            payload,
            fallback=f"DashScope task {task.task_id} failed",
            provider_task_id=task.task_id,
        )
        output = payload.get("output")
        if not isinstance(output, Mapping):
            raise MediaGenerationError("DashScope task response did not contain output")
        status = str(output.get("task_status", "")).upper()
        if status == "SUCCEEDED":
            artifacts: tuple[RemoteArtifact, ...]
            if task.kind == "video":
                raw_url = output.get("video_url")
                artifacts = (
                    (RemoteArtifact(url=raw_url, media_type="video/mp4", extension="mp4"),)
                    if isinstance(raw_url, str) and raw_url
                    else ()
                )
            else:
                artifacts = _result_image_artifacts(output) or _choice_image_artifacts(output)
            if not artifacts:
                raise MediaGenerationError("DashScope task completed without a download URL")
            return MediaJobUpdate(status="succeeded", artifacts=artifacts)
        if status in {"FAILED", "CANCELED", "UNKNOWN"}:
            raise provider_payload_error(
                output,
                fallback=f"DashScope task {task.task_id} {status.lower()}",
                provider_task_id=task.task_id,
            )
        return MediaJobUpdate(status="running" if status == "RUNNING" else "pending")


def _dashscope_task_id(payload: Mapping[str, Any], *, fallback: str) -> str:
    _raise_dashscope_payload_error(payload, fallback=fallback)
    output = payload.get("output")
    task_id = output.get("task_id") if isinstance(output, Mapping) else None
    if not isinstance(task_id, str) or not task_id:
        raise MediaGenerationError(fallback)
    return task_id


def _raise_dashscope_payload_error(
    payload: Mapping[str, Any],
    *,
    fallback: str,
    provider_task_id: str | None = None,
) -> None:
    if payload.get("code") or payload.get("message"):
        raise provider_payload_error(payload, fallback=fallback, provider_task_id=provider_task_id)


def _choice_image_artifacts(value: object) -> tuple[RemoteArtifact, ...]:
    if not isinstance(value, Mapping):
        return ()
    choices = value.get("choices")
    if not isinstance(choices, list):
        return ()
    artifacts: list[RemoteArtifact] = []
    for choice in choices:
        if not isinstance(choice, Mapping):
            continue
        message = choice.get("message")
        content = message.get("content") if isinstance(message, Mapping) else None
        if not isinstance(content, list):
            continue
        for item in content:
            raw_url = item.get("image") if isinstance(item, Mapping) else None
            if isinstance(raw_url, str) and raw_url:
                artifacts.append(RemoteArtifact(url=raw_url, media_type="image/png", extension="png"))
    return tuple(artifacts)


def _result_image_artifacts(value: object) -> tuple[RemoteArtifact, ...]:
    if not isinstance(value, Mapping):
        return ()
    results = value.get("results")
    if not isinstance(results, list):
        return ()
    artifacts: list[RemoteArtifact] = []
    for result in results:
        raw_url = result.get("url") if isinstance(result, Mapping) else None
        if isinstance(raw_url, str) and raw_url:
            artifacts.append(RemoteArtifact(url=raw_url, media_type="image/png", extension="png"))
    return tuple(artifacts)


def _wan_video_media(request: VideoGenerationRequest) -> list[dict[str, str]]:
    media: list[dict[str, str]] = []
    if request.first_frame:
        media.append({"type": "first_frame", "url": request.first_frame})
    if request.last_frame:
        media.append({"type": "last_frame", "url": request.last_frame})
    media.extend({"type": "reference_image", "url": image} for image in request.reference_images)
    return media


def _wan_reference_video_media(request: VideoGenerationRequest) -> list[dict[str, str]]:
    media: list[dict[str, str]] = []
    if request.first_frame:
        media.append({"type": "first_frame", "url": request.first_frame})
    media.extend({"type": "reference_image", "url": image} for image in request.reference_images)
    return media


def _unsupported(message: str) -> MediaGenerationError:
    return MediaGenerationError(
        message,
        code="unsupported_input",
        category="validation",
        safe_to_resubmit=True,
        remediation="adjust_request",
        model_instruction="Remove the unsupported media inputs, then call the tool at most once more.",
    )


__all__ = ["DashScopeMediaProvider"]
