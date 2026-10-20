"""Template-method base class for media generation providers."""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Protocol

import httpx

from octop_harness.config import MediaGenerationConfig, MediaProviderConfig
from octop_harness.media.errors import MediaGenerationError
from octop_harness.media.models import (
    GeneratedMedia,
    ImageGenerationRequest,
    MediaCapabilities,
    MediaJobUpdate,
    MediaSubmission,
    ProviderTask,
    RemoteArtifact,
    VideoGenerationRequest,
)


class MediaGenerationProvider(Protocol):
    """Minimal provider SPI consumed by :class:`MediaManager`.

    Custom providers may implement this protocol directly. Built-in providers
    inherit :class:`BaseMediaProvider` for HTTP client and compatibility helpers.
    """

    provider_id: str
    capabilities: MediaCapabilities

    @property
    def image_model(self) -> str:
        """Model id used for image generation."""
        ...

    @property
    def video_model(self) -> str:
        """Model id used for video generation."""
        ...

    @property
    def poll_interval_seconds(self) -> float:
        """Delay between job status polls."""
        ...

    @property
    def task_timeout_seconds(self) -> float:
        """Hard deadline for a single generation job."""
        ...

    async def submit_image(self, request: ImageGenerationRequest) -> MediaSubmission:
        """Start an image job and return its initial submission state."""
        ...

    async def submit_video(self, request: VideoGenerationRequest) -> MediaSubmission:
        """Start a video job and return its initial submission state."""
        ...

    async def poll(self, task: ProviderTask) -> MediaJobUpdate:
        """Fetch the latest state of a submitted job."""
        ...

    async def cancel(self, task: ProviderTask) -> None:
        """Request cancellation of a submitted job."""
        ...

    async def load_artifact(self, artifact: RemoteArtifact) -> GeneratedMedia:
        """Fetch a finished artifact into workspace media."""
        ...


class BaseMediaProvider(ABC):
    """Stable generation lifecycle shared by all vendor adapters.

    Subclasses only implement provider protocol primitives. The manager owns
    routing, job persistence and workspace artifacts; ``generate_*`` remains
    as a compatibility convenience for direct adapter callers.
    """

    provider_id = "base"
    capabilities = MediaCapabilities()

    def __init__(
        self,
        config: MediaGenerationConfig | MediaProviderConfig,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._config = config
        self._client = client

    @property
    def image_model(self) -> str:
        return self._config.image_model

    @property
    def video_model(self) -> str:
        return self._config.video_model

    @property
    def poll_interval_seconds(self) -> float:
        return self._config.video_poll_interval_seconds

    @property
    def task_timeout_seconds(self) -> float:
        return self._config.video_timeout_seconds

    async def generate_image(self, request: ImageGenerationRequest) -> list[GeneratedMedia]:
        """Submit an image request and return materialized artifacts."""
        async with self._client_scope() as client:
            submission = await self._submit_image(client, request)
            return await self._complete_submission(client, submission)

    async def generate_video(self, request: VideoGenerationRequest) -> list[GeneratedMedia]:
        """Submit a video request and return materialized artifacts."""
        async with self._client_scope() as client:
            submission = await self._submit_video(client, request)
            return await self._complete_submission(client, submission)

    async def submit_image(self, request: ImageGenerationRequest) -> MediaSubmission:
        """Submit without waiting, for applications that persist async jobs."""
        async with self._client_scope() as client:
            return await self._submit_image(client, request)

    async def submit_video(self, request: VideoGenerationRequest) -> MediaSubmission:
        """Submit without waiting, for applications that persist async jobs."""
        async with self._client_scope() as client:
            return await self._submit_video(client, request)

    async def poll(self, task: ProviderTask) -> MediaJobUpdate:
        """Fetch one normalized state update for an existing provider task."""
        async with self._client_scope() as client:
            return await self._poll_task(client, task)

    async def cancel(self, task: ProviderTask) -> None:
        """Best-effort cancellation of an existing provider task."""
        async with self._client_scope() as client:
            await self._cancel_task(client, task)

    async def load_artifact(self, artifact: RemoteArtifact) -> GeneratedMedia:
        """Materialize one completed artifact without leaking credentials."""
        async with self._client_scope() as client:
            return await self._load_artifact(client, artifact)

    @abstractmethod
    async def _submit_image(
        self,
        client: httpx.AsyncClient,
        request: ImageGenerationRequest,
    ) -> MediaSubmission:
        """Translate and submit one image request."""

    @abstractmethod
    async def _submit_video(
        self,
        client: httpx.AsyncClient,
        request: VideoGenerationRequest,
    ) -> MediaSubmission:
        """Translate and submit one video request."""

    @abstractmethod
    async def _poll_task(
        self,
        client: httpx.AsyncClient,
        task: ProviderTask,
    ) -> MediaJobUpdate:
        """Return a normalized update or raise a classified terminal error."""

    @abstractmethod
    async def _load_artifact(
        self,
        client: httpx.AsyncClient,
        artifact: RemoteArtifact,
    ) -> GeneratedMedia:
        """Download or decode one completed provider artifact."""

    async def _cancel_task(self, client: httpx.AsyncClient, task: ProviderTask) -> None:
        """Optional provider cancellation primitive."""
        del client, task

    @asynccontextmanager
    async def _client_scope(self) -> AsyncIterator[httpx.AsyncClient]:
        if self._client is not None:
            yield self._client
            return
        async with httpx.AsyncClient(timeout=self._config.request_timeout_seconds) as client:
            yield client

    async def _complete_submission(
        self,
        client: httpx.AsyncClient,
        submission: MediaSubmission,
    ) -> list[GeneratedMedia]:
        if submission.task is None:
            return await self._materialize(client, submission.artifacts)

        task = submission.task
        deadline = time.monotonic() + self._config.video_timeout_seconds
        try:
            while True:
                update = await self._poll_task(client, task)
                if update.status == "succeeded":
                    return await self._materialize(client, update.artifacts)
                if time.monotonic() >= deadline:
                    await self._cancel_task(client, task)
                    label = "Image" if task.kind == "image" else "Video"
                    raise MediaGenerationError(
                        f"{label} generation timed out after {self._config.video_timeout_seconds:g} seconds",
                        code="provider_timeout",
                        retryable=True,
                        safe_to_resubmit=False,
                        remediation="check_task_status",
                        model_instruction=(
                            "Do not submit another generation request. Tell the user the provider task timed out "
                            "and its final state could not be confirmed."
                        ),
                        provider_task_id=task.task_id,
                    )
                await asyncio.sleep(self._config.video_poll_interval_seconds)
        except asyncio.CancelledError:
            await asyncio.shield(self._cancel_task(client, task))
            raise

    async def _materialize(
        self,
        client: httpx.AsyncClient,
        artifacts: tuple[RemoteArtifact, ...],
    ) -> list[GeneratedMedia]:
        if not artifacts:
            raise MediaGenerationError("Media provider returned no artifacts")
        return [await self._load_artifact(client, artifact) for artifact in artifacts]


__all__ = ["BaseMediaProvider", "MediaGenerationProvider"]
