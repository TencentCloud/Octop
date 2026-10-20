"""Workspace boundary for media inputs and generated artifacts."""

from __future__ import annotations

import asyncio
import base64
import mimetypes
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import PurePosixPath
from urllib.parse import urlsplit
from uuid import uuid4

from octop_harness.backends.workspace import BackendWorkspace
from octop_harness.media.models import (
    GeneratedMedia,
    ImageGenerationRequest,
    StoredMedia,
    VideoGenerationRequest,
)


class WorkspaceMediaArtifactStore:
    """Normalize workspace references and persist generated media safely."""

    def __init__(self, workspace: BackendWorkspace, *, output_dir: str) -> None:
        output = PurePosixPath(output_dir)
        if output.is_absolute() or ".." in output.parts or not output_dir.strip("/."):
            raise ValueError("media output_dir must stay inside the workspace")
        self._workspace = workspace
        self._output_dir = output_dir.strip("/")

    async def normalize_image_request(self, request: ImageGenerationRequest) -> ImageGenerationRequest:
        prompt = request.prompt.strip()
        if not prompt:
            raise ValueError("prompt must not be empty")
        if not 1 <= request.count <= 4:
            raise ValueError("count must be between 1 and 4")
        references = await self._normalize_references(request.reference_images)
        return replace(request, prompt=prompt, reference_images=references)

    async def normalize_video_request(self, request: VideoGenerationRequest) -> VideoGenerationRequest:
        prompt = request.prompt.strip()
        if not prompt:
            raise ValueError("prompt must not be empty")
        if not 4 <= request.duration <= 15:
            raise ValueError("duration must be between 4 and 15 seconds")
        first_frame = await self._normalize_optional_reference(request.first_frame)
        last_frame = await self._normalize_optional_reference(request.last_frame)
        references = await self._normalize_references(request.reference_images)
        return replace(
            request,
            prompt=prompt,
            first_frame=first_frame,
            last_frame=last_frame,
            reference_images=references,
        )

    async def store(self, generated: list[GeneratedMedia], *, kind: str, prefix: str) -> tuple[StoredMedia, ...]:
        if not generated:
            raise RuntimeError("media provider returned no artifacts")
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        stored: list[StoredMedia] = []
        for artifact in generated:
            extension = artifact.extension.strip(".") or "bin"
            filename = f"{prefix}-{timestamp}-{uuid4().hex[:12]}.{extension}"
            path = str(PurePosixPath(self._output_dir) / kind / filename)
            await self._workspace.aupload_bytes(path, artifact.data)
            local = await asyncio.to_thread(self._workspace.materialize_local, path)
            stored.append(
                StoredMedia(
                    path=path,
                    local_path=str(local) if local is not None else path,
                    media_type=artifact.media_type,
                    size_bytes=len(artifact.data),
                )
            )
        return tuple(stored)

    async def _normalize_optional_reference(self, reference: str | None) -> str | None:
        if reference is None:
            return None
        normalized = await self._normalize_references((reference,))
        return normalized[0]

    async def _normalize_references(self, references: tuple[str, ...]) -> tuple[str, ...]:
        normalized: list[str] = []
        for reference in references:
            raw = reference.strip()
            if not raw:
                raise ValueError("reference image paths and URLs must not be empty")
            if urlsplit(raw).scheme in {"http", "https", "data"}:
                normalized.append(raw)
                continue
            data = await self._workspace.adownload_bytes(raw)
            if data is None:
                raise FileNotFoundError(f"reference image not found: {raw}")
            media_type, _ = mimetypes.guess_type(raw)
            if media_type is None or not media_type.startswith("image/"):
                media_type = "image/png"
            encoded = base64.b64encode(data).decode("ascii")
            normalized.append(f"data:{media_type};base64,{encoded}")
        return tuple(normalized)


__all__ = ["WorkspaceMediaArtifactStore"]
