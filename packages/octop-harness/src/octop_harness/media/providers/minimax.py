"""MiniMax adapters for image-01 and H3 video generation."""

from __future__ import annotations

import base64
import re
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

_IMAGE_SIZE = re.compile(r"^(\d+)[xX](\d+)$")
_IMAGE_RATIOS = {"1:1", "16:9", "4:3", "3:2", "2:3", "3:4", "9:16", "21:9"}


class MiniMaxMediaProvider(BearerJsonMediaProvider):
    """Call MiniMax image generation and H3 video generation APIs."""

    provider_id = "minimax"
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
        body: dict[str, Any] = {
            "model": self.image_model,
            "prompt": request.prompt,
            "response_format": "base64",
            "n": request.count,
            "prompt_optimizer": False,
            "aigc_watermark": request.watermark,
        }
        if request.reference_images:
            body["subject_reference"] = [
                {"type": "character", "image_file": image} for image in request.reference_images
            ]
        if request.size:
            match = _IMAGE_SIZE.fullmatch(request.size.strip())
            if match:
                body["width"] = int(match.group(1))
                body["height"] = int(match.group(2))
            elif request.size in _IMAGE_RATIOS:
                body["aspect_ratio"] = request.size
            else:
                raise _unsupported("MiniMax image size must be a supported aspect ratio or WIDTHxHEIGHT.")
        if request.seed is not None:
            body["seed"] = request.seed

        payload = await self._request_json(client, "POST", "/v1/image_generation", json=body)
        base_resp = payload.get("base_resp")
        if isinstance(base_resp, Mapping) and base_resp.get("status_code") not in {None, 0, "0"}:
            raise provider_payload_error(base_resp, fallback="MiniMax image generation failed")
        data = payload.get("data")
        if not isinstance(data, Mapping):
            raise MediaGenerationError("MiniMax image generation returned no image data")
        artifacts = _minimax_image_artifacts(data)
        if not artifacts:
            raise MediaGenerationError("MiniMax image generation returned no usable images")
        return MediaSubmission(artifacts=artifacts)

    async def _submit_video(
        self,
        client: httpx.AsyncClient,
        request: VideoGenerationRequest,
    ) -> MediaSubmission:
        if request.seed is not None:
            raise _unsupported("MiniMax H3 does not expose a reproducibility seed in the V2 API.")
        if request.reference_images and (request.first_frame or request.last_frame):
            raise _unsupported("MiniMax H3 reference images cannot be combined with first or last frames.")
        if self.video_model == "MiniMax-H3-Max" and request.duration < 5:
            raise _unsupported("MiniMax-H3-Max requires a duration between 5 and 15 seconds.")

        content: list[dict[str, Any]] = [{"type": "text", "text": request.prompt}]
        if request.first_frame:
            content.append(_image_content(request.first_frame, "first_frame"))
        if request.last_frame:
            content.append(_image_content(request.last_frame, "last_frame"))
        content.extend(_image_content(image, "reference_image") for image in request.reference_images)
        ratio = "adaptive" if request.first_frame or request.last_frame else request.aspect_ratio
        body = {
            "model": self.video_model,
            "content": content,
            "resolution": _minimax_resolution(self.video_model, request.resolution),
            "duration": request.duration,
            "ratio": ratio,
            "aigc_watermark": request.watermark,
        }
        payload = await self._request_json(client, "POST", "/v2/video_generation", json=body)
        task_id = payload.get("task_id")
        if not isinstance(task_id, str) or not task_id:
            error = payload.get("error")
            if error:
                raise provider_payload_error(error, fallback="MiniMax video generation failed")
            raise MediaGenerationError("MiniMax video generation did not return a task id")
        return MediaSubmission(task=ProviderTask(task_id=task_id, kind="video", model=self.video_model))

    async def _poll_task(
        self,
        client: httpx.AsyncClient,
        task: ProviderTask,
    ) -> MediaJobUpdate:
        payload = await self._request_json(
            client,
            "GET",
            f"/v2/query/video_generation/{task.task_id}",
            provider_task_id=task.task_id,
        )
        raw_task = payload.get("task")
        if not isinstance(raw_task, Mapping):
            raise MediaGenerationError("MiniMax task response did not contain task data")
        status = raw_task.get("status")
        if status == "succeeded":
            content = raw_task.get("content")
            raw_url = content.get("url") if isinstance(content, Mapping) else None
            if not isinstance(raw_url, str) or not raw_url:
                raise MediaGenerationError("MiniMax video task completed without a download URL")
            artifact = RemoteArtifact(url=raw_url, media_type="video/mp4", extension="mp4")
            return MediaJobUpdate(status="succeeded", artifacts=(artifact,))
        if status in {"failed", "cancelled"}:
            error = provider_payload_error(
                raw_task.get("error"),
                fallback=f"MiniMax task {task.task_id} {status}",
                provider_task_id=task.task_id,
            )
            if status == "cancelled":
                error.code = "generation_cancelled"
            raise error
        return MediaJobUpdate(status="running" if status == "running" else "pending")


def _minimax_image_artifacts(data: Mapping[object, object]) -> tuple[RemoteArtifact, ...]:
    artifacts: list[RemoteArtifact] = []
    encoded_images = data.get("image_base64")
    if isinstance(encoded_images, list):
        for encoded in encoded_images:
            if not isinstance(encoded, str) or not encoded:
                continue
            try:
                raw = base64.b64decode(encoded, validate=True)
            except ValueError as exc:
                raise MediaGenerationError("MiniMax returned invalid base64 image data") from exc
            artifacts.append(RemoteArtifact(data=raw, media_type="image/png", extension="png"))
    image_urls = data.get("image_urls")
    if isinstance(image_urls, list):
        for raw_url in image_urls:
            if isinstance(raw_url, str) and raw_url:
                artifacts.append(RemoteArtifact(url=raw_url, media_type="image/png", extension="png"))
    return tuple(artifacts)


def _image_content(url: str, role: str) -> dict[str, Any]:
    return {"type": "image_url", "image_url": {"url": url}, "role": role}


def _minimax_resolution(model: str, value: str) -> str:
    normalized = value.strip().lower()
    if model == "MiniMax-H3-Max":
        if normalized == "480p":
            return "480P"
        if normalized in {"720p", "768p"}:
            return "768P"
        raise _unsupported("MiniMax-H3-Max supports only 480p or 768p output.")
    if normalized in {"720p", "768p"}:
        return "768P"
    if normalized in {"1080p", "2k"}:
        return "2K"
    raise _unsupported("MiniMax-H3 supports only 768p or 2K output.")


def _unsupported(message: str) -> MediaGenerationError:
    return MediaGenerationError(
        message,
        code="unsupported_input",
        category="validation",
        safe_to_resubmit=True,
        remediation="adjust_request",
        model_instruction="Adjust the unsupported arguments, then call the tool at most once more.",
    )


__all__ = ["MiniMaxMediaProvider"]
