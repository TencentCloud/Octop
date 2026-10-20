"""Volcengine Ark adapter for Seedream image and Seedance video generation."""

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

_SEEDREAM_5_MIN_PIXELS = 3_686_400
_EXPLICIT_IMAGE_SIZE = re.compile(r"^(\d+)[xX](\d+)$")


class VolcengineMediaProvider(BearerJsonMediaProvider):
    """Call the public Volcengine Ark Seedream and Seedance HTTP APIs."""

    provider_id = "volcengine"
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
            "response_format": "b64_json",
            "watermark": request.watermark,
            "sequential_image_generation": "auto" if request.count > 1 else "disabled",
        }
        if request.reference_images:
            body["image"] = list(request.reference_images)
        size = _seedream_image_size(self.image_model, request.size)
        if size:
            body["size"] = size
        if request.seed is not None:
            body["seed"] = request.seed
        if request.count > 1:
            body["sequential_image_generation_options"] = {"max_images": request.count}

        payload = await self._request_json(client, "POST", "/images/generations", json=body)
        error = payload.get("error")
        if isinstance(error, Mapping) and error:
            raise provider_payload_error(error, fallback="image generation failed")
        rows = payload.get("data")
        if not isinstance(rows, list) or not rows:
            raise MediaGenerationError("Volcengine image generation returned no images")

        artifacts: list[RemoteArtifact] = []
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            encoded = row.get("b64_json")
            if isinstance(encoded, str) and encoded:
                try:
                    data = base64.b64decode(encoded, validate=True)
                except ValueError as exc:
                    raise MediaGenerationError("Volcengine returned invalid base64 image data") from exc
                artifacts.append(RemoteArtifact(data=data, media_type="image/png", extension="png"))
                continue
            url = row.get("url")
            if isinstance(url, str) and url:
                artifacts.append(RemoteArtifact(url=url, media_type="image/png", extension="png"))
        if not artifacts:
            raise MediaGenerationError("Volcengine image generation returned no usable images")
        return MediaSubmission(artifacts=tuple(artifacts))

    async def _submit_video(
        self,
        client: httpx.AsyncClient,
        request: VideoGenerationRequest,
    ) -> MediaSubmission:
        content: list[dict[str, Any]] = [{"type": "text", "text": request.prompt}]
        if request.first_frame:
            content.append(_image_content(request.first_frame, role="first_frame"))
        if request.last_frame:
            content.append(_image_content(request.last_frame, role="last_frame"))
        content.extend(_image_content(image, role="reference_image") for image in request.reference_images)

        body: dict[str, Any] = {
            "model": self.video_model,
            "content": content,
            "duration": request.duration,
            "ratio": request.aspect_ratio,
            "resolution": request.resolution,
            "generate_audio": request.generate_audio,
            "watermark": request.watermark,
            "output_format": "mp4",
        }
        if request.seed is not None:
            body["seed"] = request.seed
        created = await self._request_json(client, "POST", "/contents/generations/tasks", json=body)
        task_id = created.get("id")
        if not isinstance(task_id, str) or not task_id:
            raise MediaGenerationError("Volcengine video generation did not return a task id")
        return MediaSubmission(task=ProviderTask(task_id=task_id, kind="video", model=self.video_model))

    async def _poll_task(
        self,
        client: httpx.AsyncClient,
        task: ProviderTask,
    ) -> MediaJobUpdate:
        payload = await self._request_json(
            client,
            "GET",
            f"/contents/generations/tasks/{task.task_id}",
            provider_task_id=task.task_id,
        )
        status = payload.get("status")
        if status == "succeeded":
            content = payload.get("content")
            if not isinstance(content, Mapping):
                raise MediaGenerationError("Volcengine video task completed without content")
            raw_url = content.get("video_url") or content.get("file_url")
            if not isinstance(raw_url, str) or not raw_url:
                raise MediaGenerationError("Volcengine video task completed without a download URL")
            artifact = RemoteArtifact(url=raw_url, media_type="video/mp4", extension="mp4")
            return MediaJobUpdate(status="succeeded", artifacts=(artifact,))
        if status in {"failed", "cancelled"}:
            error = provider_payload_error(
                payload.get("error"),
                fallback=f"task {task.task_id} {status}",
                provider_task_id=task.task_id,
            )
            if status == "cancelled":
                error.code = "generation_cancelled"
            raise error
        return MediaJobUpdate(status="running" if status == "running" else "pending")

    async def _cancel_task(self, client: httpx.AsyncClient, task: ProviderTask) -> None:
        try:
            await client.delete(
                f"{self._config.base_url.rstrip('/')}/contents/generations/tasks/{task.task_id}",
                headers={"Authorization": f"Bearer {self._config.resolve_api_key()}"},
            )
        except (httpx.HTTPError, ValueError):
            return


def _seedream_image_size(model: str, requested: str | None) -> str | None:
    """Return an Ark-compatible size, upgrading undersized Seedream 5 requests."""
    if not model.startswith("doubao-seedream-5-0"):
        return requested
    size = (requested or "2K").strip()
    match = _EXPLICIT_IMAGE_SIZE.fullmatch(size)
    if match and int(match.group(1)) * int(match.group(2)) < _SEEDREAM_5_MIN_PIXELS:
        return "2K"
    return size


def _image_content(url: str, *, role: str) -> dict[str, Any]:
    return {"type": "image_url", "image_url": {"url": url}, "role": role}


__all__ = ["VolcengineMediaProvider"]
