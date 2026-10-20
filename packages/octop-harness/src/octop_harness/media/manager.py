"""Unified routing and lifecycle orchestration for media generation."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from octop_harness.backends.workspace import BackendWorkspace
from octop_harness.media.artifacts import WorkspaceMediaArtifactStore
from octop_harness.media.base import MediaGenerationProvider
from octop_harness.media.errors import MediaGenerationError
from octop_harness.media.models import (
    ImageGenerationRequest,
    MediaGenerationResult,
    MediaJob,
    MediaKind,
    MediaSubmission,
    RemoteArtifact,
    VideoGenerationRequest,
)


class MediaJobStore(Protocol):
    """Persistence boundary for manager-owned job state."""

    async def save(self, job: MediaJob) -> None:
        """Persist (or replace) a job record."""
        ...

    async def get(self, job_id: str) -> MediaJob | None:
        """Return the stored job, or ``None`` when the id is unknown."""
        ...


class InMemoryMediaJobStore:
    """Process-local default; hosts may inject a durable implementation."""

    def __init__(self) -> None:
        self._jobs: dict[str, MediaJob] = {}
        self._lock = asyncio.Lock()

    async def save(self, job: MediaJob) -> None:
        async with self._lock:
            self._jobs[job.id] = job

    async def get(self, job_id: str) -> MediaJob | None:
        async with self._lock:
            return self._jobs.get(job_id)


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class MediaRouteInfo:
    """Resolved provider and model metadata for one media kind."""

    provider_id: str
    provider_type: str
    model: str


@dataclass(frozen=True)
class _ProviderEntry:
    id: str
    provider: MediaGenerationProvider
    image_enabled: bool
    video_enabled: bool


class MediaManager:
    """Own provider registration, routing, jobs, and workspace persistence."""

    def __init__(
        self,
        workspace: BackendWorkspace,
        *,
        output_dir: str,
        job_store: MediaJobStore | None = None,
    ) -> None:
        self._artifacts = WorkspaceMediaArtifactStore(workspace, output_dir=output_dir)
        self._job_store = job_store if job_store is not None else InMemoryMediaJobStore()
        self._providers: dict[str, _ProviderEntry] = {}
        self._routes: dict[MediaKind, str] = {}
        self._job_locks: dict[str, asyncio.Lock] = {}
        self._completion_locks: dict[str, asyncio.Lock] = {}

    def add_provider(
        self,
        provider_id: str,
        provider: MediaGenerationProvider,
        *,
        image_enabled: bool = True,
        video_enabled: bool = True,
    ) -> None:
        """Register one provider instance under a unique routing id."""
        provider_id = provider_id.strip()
        if not provider_id:
            raise ValueError("media provider id must not be empty")
        if provider_id in self._providers:
            raise ValueError(f"media provider id {provider_id!r} is already registered")
        if image_enabled and not provider.capabilities.image_generation:
            raise ValueError(f"media provider {provider_id!r} does not support image generation")
        if video_enabled and not provider.capabilities.video_generation:
            raise ValueError(f"media provider {provider_id!r} does not support video generation")
        entry = _ProviderEntry(
            id=provider_id,
            provider=provider,
            image_enabled=image_enabled,
            video_enabled=video_enabled,
        )
        self._providers[provider_id] = entry
        if image_enabled:
            self._routes.setdefault("image", provider_id)
        if video_enabled:
            self._routes.setdefault("video", provider_id)

    def set_default_route(self, kind: MediaKind, provider_id: str) -> None:
        """Select the provider instance used when a request has no override."""
        entry = self._providers.get(provider_id)
        if entry is None:
            raise ValueError(f"unknown media provider id: {provider_id!r}")
        if not self._is_enabled(entry, kind):
            raise ValueError(f"media provider {provider_id!r} does not enable {kind} generation")
        self._routes[kind] = provider_id

    def has_route(self, kind: MediaKind) -> bool:
        """Return whether the manager has a usable default route."""
        return kind in self._routes

    def route_info(self, kind: MediaKind, provider_id: str | None = None) -> MediaRouteInfo:
        """Resolve routing metadata without submitting a request."""
        entry = self._resolve_entry(kind, provider_id)
        model = entry.provider.image_model if kind == "image" else entry.provider.video_model
        return MediaRouteInfo(
            provider_id=entry.id,
            provider_type=entry.provider.provider_id,
            model=model,
        )

    async def generate_image(
        self,
        request: ImageGenerationRequest,
        *,
        provider_id: str | None = None,
    ) -> MediaGenerationResult:
        """Route, complete, and persist one image generation request."""
        started = await self.submit_image(request, provider_id=provider_id)
        if isinstance(started, MediaGenerationResult):
            return started
        return await self.wait(started.id)

    async def submit_image(
        self,
        request: ImageGenerationRequest,
        *,
        provider_id: str | None = None,
    ) -> MediaGenerationResult | MediaJob:
        """Submit an image request, returning an immediate result or async job."""
        normalized = await self._artifacts.normalize_image_request(request)
        entry = self._resolve_entry("image", provider_id)
        submission = await entry.provider.submit_image(normalized)
        return await self._record_submission(entry, "image", normalized.prompt, submission)

    async def generate_video(
        self,
        request: VideoGenerationRequest,
        *,
        provider_id: str | None = None,
    ) -> MediaGenerationResult:
        """Route, complete, and persist one video generation request."""
        started = await self.submit_video(request, provider_id=provider_id)
        if isinstance(started, MediaGenerationResult):
            return started
        return await self.wait(started.id)

    async def submit_video(
        self,
        request: VideoGenerationRequest,
        *,
        provider_id: str | None = None,
    ) -> MediaGenerationResult | MediaJob:
        """Submit a video request, returning an immediate result or async job."""
        normalized = await self._artifacts.normalize_video_request(request)
        entry = self._resolve_entry("video", provider_id)
        submission = await entry.provider.submit_video(normalized)
        return await self._record_submission(entry, "video", normalized.prompt, submission)

    async def get_job(self, job_id: str) -> MediaJob | None:
        """Return manager-owned state for an async provider task."""
        return await self._job_store.get(job_id)

    async def wait(self, job_id: str) -> MediaGenerationResult:
        """Wait for an existing manager job and persist its artifacts."""
        lock = self._completion_locks.setdefault(job_id, asyncio.Lock())
        async with lock:
            return await self._wait_unlocked(job_id)

    async def _wait_unlocked(self, job_id: str) -> MediaGenerationResult:
        job = await self._require_job(job_id)
        if job.result is not None:
            return job.result
        if job.status in {"failed", "cancelled"}:
            raise MediaGenerationError(
                job.error or f"Media generation job {job.status}.",
                code=job.error_code
                or ("generation_cancelled" if job.status == "cancelled" else "provider_task_failed"),
                safe_to_resubmit=False,
                remediation="check_task_status",
                provider_task_id=job.task.task_id,
            )
        entry = self._providers.get(job.provider_id)
        if entry is None:
            raise MediaGenerationError(
                f"Media provider {job.provider_id!r} is no longer registered.",
                code="provider_not_registered",
                category="configuration",
                remediation="configure_provider",
                provider_task_id=job.task.task_id,
            )
        artifacts = job.artifacts if job.status == "succeeded" else await self._await_job(entry, job)
        result = await self._materialize(
            entry,
            kind=job.task.kind,
            prompt=job.prompt,
            artifacts=artifacts,
            provider_task_id=job.task.task_id,
        )
        latest = await self._require_job(job_id)
        await self._job_store.save(replace(latest, result=result, updated_at=_utc_now()))
        return result

    async def poll(self, job_id: str) -> MediaJob:
        """Poll one job once and persist its normalized state."""
        lock = self._job_locks.setdefault(job_id, asyncio.Lock())
        async with lock:
            job = await self._require_job(job_id)
            if job.status in {"succeeded", "failed", "cancelled"}:
                return job
            entry = self._providers.get(job.provider_id)
            if entry is None:
                raise MediaGenerationError(
                    f"Media provider {job.provider_id!r} is no longer registered.",
                    code="provider_not_registered",
                    category="configuration",
                    remediation="configure_provider",
                    provider_task_id=job.task.task_id,
                )
            try:
                update = await entry.provider.poll(job.task)
            except MediaGenerationError as exc:
                failed = replace(
                    job,
                    status="failed",
                    error=str(exc),
                    error_code=exc.code,
                    updated_at=_utc_now(),
                )
                await self._job_store.save(failed)
                raise
            refreshed = replace(
                job,
                status=update.status,
                artifacts=update.artifacts,
                updated_at=_utc_now(),
            )
            await self._job_store.save(refreshed)
            return refreshed

    async def cancel(self, job_id: str) -> MediaJob:
        """Best-effort cancel one manager job and record the local state."""
        lock = self._job_locks.setdefault(job_id, asyncio.Lock())
        async with lock:
            job = await self._require_job(job_id)
            if job.status in {"succeeded", "failed", "cancelled"}:
                return job
            entry = self._providers.get(job.provider_id)
            if entry is not None:
                await entry.provider.cancel(job.task)
            cancelled = replace(
                job,
                status="cancelled",
                error="Media generation job was cancelled.",
                error_code="generation_cancelled",
                updated_at=_utc_now(),
            )
            await self._job_store.save(cancelled)
            return cancelled

    def _resolve_entry(self, kind: MediaKind, provider_id: str | None) -> _ProviderEntry:
        resolved_id = provider_id or self._routes.get(kind)
        if resolved_id is None:
            raise MediaGenerationError(
                f"No default {kind} generation provider is configured.",
                code="media_route_missing",
                category="configuration",
                remediation="configure_provider",
            )
        entry = self._providers.get(resolved_id)
        if entry is None:
            raise MediaGenerationError(
                f"Unknown media provider route: {resolved_id!r}.",
                code="provider_not_registered",
                category="configuration",
                remediation="configure_provider",
            )
        if not self._is_enabled(entry, kind):
            raise MediaGenerationError(
                f"Media provider {resolved_id!r} does not enable {kind} generation.",
                code="media_capability_disabled",
                category="configuration",
                remediation="configure_provider",
            )
        return entry

    @staticmethod
    def _is_enabled(entry: _ProviderEntry, kind: MediaKind) -> bool:
        return entry.image_enabled if kind == "image" else entry.video_enabled

    async def _record_submission(
        self,
        entry: _ProviderEntry,
        kind: MediaKind,
        prompt: str,
        submission: MediaSubmission,
    ) -> MediaGenerationResult | MediaJob:
        if submission.task is not None:
            if submission.task.kind != kind:
                raise MediaGenerationError("Media provider returned a task for the wrong media kind")
            created_at = _utc_now()
            job = MediaJob(
                id=uuid4().hex,
                provider_id=entry.id,
                provider_type=entry.provider.provider_id,
                task=submission.task,
                prompt=prompt,
                created_at=created_at,
                updated_at=created_at,
            )
            await self._job_store.save(job)
            return job
        return await self._materialize(
            entry,
            kind=kind,
            prompt=prompt,
            artifacts=submission.artifacts,
            provider_task_id=None,
        )

    async def _await_job(self, entry: _ProviderEntry, job: MediaJob) -> tuple[RemoteArtifact, ...]:
        deadline = time.monotonic() + entry.provider.task_timeout_seconds
        try:
            while True:
                current = await self.poll(job.id)
                if current.status == "succeeded":
                    return current.artifacts
                if current.status in {"failed", "cancelled"}:
                    raise MediaGenerationError(
                        current.error or f"Media generation job {current.status}.",
                        code=current.error_code
                        or ("generation_cancelled" if current.status == "cancelled" else "provider_task_failed"),
                        safe_to_resubmit=False,
                        remediation="check_task_status",
                        provider_task_id=current.task.task_id,
                    )
                if time.monotonic() >= deadline:
                    await entry.provider.cancel(job.task)
                    failed = replace(
                        current,
                        status="failed",
                        error="provider task timed out",
                        error_code="provider_timeout",
                        updated_at=_utc_now(),
                    )
                    await self._job_store.save(failed)
                    label = "Image" if job.task.kind == "image" else "Video"
                    raise MediaGenerationError(
                        f"{label} generation timed out after {entry.provider.task_timeout_seconds:g} seconds",
                        code="provider_timeout",
                        retryable=True,
                        safe_to_resubmit=False,
                        remediation="check_task_status",
                        model_instruction=(
                            "Do not submit another generation request. Tell the user the provider task timed out "
                            "and its final state could not be confirmed."
                        ),
                        provider_task_id=job.task.task_id,
                    )
                await asyncio.sleep(entry.provider.poll_interval_seconds)
        except asyncio.CancelledError:
            await asyncio.shield(self.cancel(job.id))
            raise

    async def _materialize(
        self,
        entry: _ProviderEntry,
        *,
        kind: MediaKind,
        prompt: str,
        artifacts: tuple[RemoteArtifact, ...],
        provider_task_id: str | None,
    ) -> MediaGenerationResult:
        if not artifacts:
            raise MediaGenerationError("Media provider returned no artifacts")
        generated = [await entry.provider.load_artifact(artifact) for artifact in artifacts]
        stored = await self._artifacts.store(
            generated,
            kind="images" if kind == "image" else "videos",
            prefix=kind,
        )
        model = entry.provider.image_model if kind == "image" else entry.provider.video_model
        return MediaGenerationResult(
            kind=kind,
            prompt=prompt,
            provider_id=entry.id,
            provider_type=entry.provider.provider_id,
            model=model,
            artifacts=stored,
            provider_task_id=provider_task_id,
        )

    async def _require_job(self, job_id: str) -> MediaJob:
        job = await self._job_store.get(job_id)
        if job is None:
            raise MediaGenerationError(
                f"Unknown media job: {job_id!r}.",
                code="media_job_not_found",
                category="validation",
                remediation="check_task_status",
            )
        return job


__all__ = ["InMemoryMediaJobStore", "MediaJobStore", "MediaManager", "MediaRouteInfo"]
