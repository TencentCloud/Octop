"""Provider-neutral request and result models for media generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

MediaKind = Literal["image", "video"]
MediaJobStatus = Literal["pending", "running", "succeeded"]
MediaManagerJobStatus = Literal["pending", "running", "succeeded", "failed", "cancelled"]


@dataclass(frozen=True)
class ImageGenerationRequest:
    """Normalized image-generation request passed to a media provider."""

    prompt: str
    reference_images: tuple[str, ...] = ()
    size: str | None = None
    count: int = 1
    seed: int | None = None
    watermark: bool = False


@dataclass(frozen=True)
class VideoGenerationRequest:
    """Normalized video-generation request passed to a media provider."""

    prompt: str
    first_frame: str | None = None
    last_frame: str | None = None
    reference_images: tuple[str, ...] = ()
    duration: int = 5
    aspect_ratio: str = "16:9"
    resolution: str = "720p"
    generate_audio: bool = False
    seed: int | None = None
    watermark: bool = False


@dataclass(frozen=True)
class GeneratedMedia:
    """One generated binary artifact returned by a media provider."""

    data: bytes
    media_type: str
    extension: str


@dataclass(frozen=True)
class RemoteArtifact:
    """Provider result that has not yet been persisted in the workspace."""

    url: str | None = None
    data: bytes | None = None
    media_type: str | None = None
    extension: str | None = None

    def __post_init__(self) -> None:
        if (self.url is None) == (self.data is None):
            raise ValueError("RemoteArtifact requires exactly one of url or data")


@dataclass(frozen=True)
class ProviderTask:
    """Opaque handle for one provider-side asynchronous generation task."""

    task_id: str
    kind: MediaKind
    model: str
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class MediaSubmission:
    """Result of submitting a request: immediate artifacts or an async task."""

    artifacts: tuple[RemoteArtifact, ...] = ()
    task: ProviderTask | None = None

    def __post_init__(self) -> None:
        if bool(self.artifacts) == (self.task is not None):
            raise ValueError("MediaSubmission requires artifacts or task, but not both")


@dataclass(frozen=True)
class MediaJobUpdate:
    """Normalized non-failure state returned while polling a provider task."""

    status: MediaJobStatus
    artifacts: tuple[RemoteArtifact, ...] = ()

    def __post_init__(self) -> None:
        if self.status == "succeeded" and not self.artifacts:
            raise ValueError("succeeded media jobs require at least one artifact")
        if self.status != "succeeded" and self.artifacts:
            raise ValueError("unfinished media jobs cannot contain artifacts")


@dataclass(frozen=True)
class MediaCapabilities:
    """High-level feature flags exposed by a provider adapter."""

    image_generation: bool = True
    video_generation: bool = True
    image_references: bool = False
    video_first_frame: bool = False
    video_last_frame: bool = False
    video_references: bool = False
    video_audio: bool = False


@dataclass(frozen=True)
class StoredMedia:
    """One generated artifact persisted through ``BackendWorkspace``."""

    path: str
    local_path: str
    media_type: str
    size_bytes: int


@dataclass(frozen=True)
class MediaGenerationResult:
    """Completed manager execution with workspace-backed artifacts."""

    kind: MediaKind
    prompt: str
    provider_id: str
    provider_type: str
    model: str
    artifacts: tuple[StoredMedia, ...]
    provider_task_id: str | None = None


@dataclass(frozen=True)
class MediaJob:
    """A globally unique manager job wrapping a provider-local task."""

    id: str
    provider_id: str
    provider_type: str
    task: ProviderTask
    prompt: str
    status: MediaManagerJobStatus = "pending"
    artifacts: tuple[RemoteArtifact, ...] = ()
    result: MediaGenerationResult | None = None
    error: str | None = None
    error_code: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
