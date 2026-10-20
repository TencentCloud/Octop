"""Tests for provider-neutral media tools and the Volcengine adapter."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest
from deepagents.backends import FilesystemBackend
from langchain_core.messages import ToolMessage

from octop_harness.agent import HarnessAgent
from octop_harness.backends.workspace import BackendWorkspace
from octop_harness.builtin.tools.media_generation import build_media_generation_tools
from octop_harness.config import (
    HarnessAgentConfig,
    MediaGenerationConfig,
    MediaProviderConfig,
    ModelConfig,
    ProviderConfig,
)
from octop_harness.media.base import BaseMediaProvider
from octop_harness.media.errors import MediaGenerationError
from octop_harness.media.manager import MediaManager
from octop_harness.media.models import (
    GeneratedMedia,
    ImageGenerationRequest,
    MediaCapabilities,
    MediaJob,
    MediaJobUpdate,
    MediaSubmission,
    ProviderTask,
    RemoteArtifact,
    VideoGenerationRequest,
)
from octop_harness.media.providers.dashscope import DashScopeMediaProvider
from octop_harness.media.providers.minimax import MiniMaxMediaProvider
from octop_harness.media.providers.volcengine import VolcengineMediaProvider
from octop_harness.media.registry import create_media_manager, create_media_provider

_PNG = b"\x89PNG\r\n\x1a\nimage-bytes"
_MP4 = b"\x00\x00\x00\x18ftypmp42video-bytes"


class _FakeProvider:
    provider_id = "fake"
    image_model = "fake-image"
    video_model = "fake-video"
    capabilities = MediaCapabilities()
    poll_interval_seconds = 0.001
    task_timeout_seconds = 1.0

    def __init__(self) -> None:
        self.image_request: ImageGenerationRequest | None = None
        self.video_request: VideoGenerationRequest | None = None

    async def submit_image(self, request: ImageGenerationRequest) -> MediaSubmission:
        self.image_request = request
        return MediaSubmission(artifacts=(RemoteArtifact(data=_PNG, media_type="image/png", extension="png"),))

    async def submit_video(self, request: VideoGenerationRequest) -> MediaSubmission:
        self.video_request = request
        return MediaSubmission(artifacts=(RemoteArtifact(data=_MP4, media_type="video/mp4", extension="mp4"),))

    async def poll(self, task: ProviderTask) -> MediaJobUpdate:
        del task
        return MediaJobUpdate(status="pending")

    async def cancel(self, task: ProviderTask) -> None:
        del task

    async def load_artifact(self, artifact: RemoteArtifact) -> GeneratedMedia:
        assert artifact.data is not None
        return GeneratedMedia(
            data=artifact.data,
            media_type=artifact.media_type or "application/octet-stream",
            extension=artifact.extension or "bin",
        )


class _FailingProvider(_FakeProvider):
    async def submit_image(self, request: ImageGenerationRequest) -> MediaSubmission:
        del request
        raise MediaGenerationError(
            "The configured image model is not enabled.",
            code="model_access_required",
            category="authorization",
            remediation="configure_model",
            model_instruction="Do not retry. Ask the user to enable the configured image model.",
        )


class _AsyncFakeProvider(_FakeProvider):
    def __init__(self) -> None:
        super().__init__()
        self.polls = 0

    async def submit_video(self, request: VideoGenerationRequest) -> MediaSubmission:
        self.video_request = request
        return MediaSubmission(task=ProviderTask(task_id="provider-task-1", kind="video", model=self.video_model))

    async def poll(self, task: ProviderTask) -> MediaJobUpdate:
        assert task.task_id == "provider-task-1"
        self.polls += 1
        if self.polls == 1:
            return MediaJobUpdate(status="running")
        return MediaJobUpdate(
            status="succeeded",
            artifacts=(RemoteArtifact(data=_MP4, media_type="video/mp4", extension="mp4"),),
        )


class _NeverCompletesProvider(_AsyncFakeProvider):
    task_timeout_seconds = 0.000000001

    def __init__(self) -> None:
        super().__init__()
        self.cancelled = False

    async def poll(self, task: ProviderTask) -> MediaJobUpdate:
        del task
        return MediaJobUpdate(status="running")

    async def cancel(self, task: ProviderTask) -> None:
        del task
        self.cancelled = True


class _RecordingJobStore:
    def __init__(self) -> None:
        self.jobs: dict[str, MediaJob] = {}

    async def save(self, job: MediaJob) -> None:
        self.jobs[job.id] = job

    async def get(self, job_id: str) -> MediaJob | None:
        return self.jobs.get(job_id)


def _media_config(**overrides: Any) -> MediaGenerationConfig:
    return MediaGenerationConfig(api_key="ark-test-key", **overrides)


def _workspace(tmp_path: Path) -> BackendWorkspace:
    backend = FilesystemBackend(root_dir=str(tmp_path), virtual_mode=True)
    return BackendWorkspace(backend, tmp_path)


@pytest.mark.asyncio
async def test_generate_image_tool_normalizes_reference_and_stores_workbuddy_result(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    workspace.upload_bytes("references/source.png", _PNG)
    provider = _FakeProvider()
    image_tool, _ = build_media_generation_tools(workspace, _media_config(), provider=provider)

    result = await image_tool.ainvoke(
        {
            "prompt": "  turn this into a paper sculpture  ",
            "reference_images": ["references/source.png"],
            "count": 1,
        }
    )

    assert provider.image_request is not None
    assert provider.image_request.prompt == "turn this into a paper sculpture"
    assert provider.image_request.reference_images[0].startswith("data:image/png;base64,")
    assert result["type"] == "image_gen_tool_result"
    assert result["status"] == "completed"
    assert result["is_error"] is False
    assert result["execution"] == {
        "provider": "fake",
        "model": "fake-image",
        "fallback_used": False,
    }
    assert result["provider"] == "fake"
    image = result["images"][0]
    assert image["path"].startswith("generated/images/image-")
    assert Path(image["localPath"]).read_bytes() == _PNG


@pytest.mark.asyncio
async def test_generate_video_tool_maps_frames_and_stores_result(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    provider = _FakeProvider()
    _, video_tool = build_media_generation_tools(workspace, _media_config(), provider=provider)

    result = await video_tool.ainvoke(
        {
            "prompt": "camera pushes in",
            "first_frame": "https://example.com/first.png",
            "last_frame": "https://example.com/last.png",
            "reference_images": ["data:image/png;base64,eA=="],
            "duration": 10,
            "aspect_ratio": "9:16",
            "resolution": "1080p",
            "generate_audio": False,
        }
    )

    assert provider.video_request == VideoGenerationRequest(
        prompt="camera pushes in",
        first_frame="https://example.com/first.png",
        last_frame="https://example.com/last.png",
        reference_images=("data:image/png;base64,eA==",),
        duration=10,
        aspect_ratio="9:16",
        resolution="1080p",
        generate_audio=False,
    )
    assert result["type"] == "video_gen_tool_result"
    video = result["videos"][0]
    assert video["path"].startswith("generated/videos/video-")
    assert Path(video["localPath"]).read_bytes() == _MP4


@pytest.mark.asyncio
async def test_generate_tool_validates_billable_request_before_provider_call(tmp_path: Path) -> None:
    provider = _FakeProvider()
    image_tool, video_tool = build_media_generation_tools(_workspace(tmp_path), _media_config(), provider=provider)

    image_result = await image_tool.ainvoke(
        {
            "name": "generate_image",
            "args": {"prompt": "x", "count": 5},
            "id": "invalid-image-call",
            "type": "tool_call",
        }
    )
    video_result = await video_tool.ainvoke(
        {
            "name": "generate_video",
            "args": {"prompt": "x", "duration": 16},
            "id": "invalid-video-call",
            "type": "tool_call",
        }
    )

    assert isinstance(image_result, ToolMessage)
    assert isinstance(video_result, ToolMessage)
    assert image_result.status == "error"
    assert video_result.status == "error"
    assert json.loads(image_result.text)["error"]["code"] == "invalid_request"
    assert json.loads(video_result.text)["remediation"]["action"] == "adjust_request"

    assert provider.image_request is None
    assert provider.video_request is None


def test_media_tool_schema_explains_routing_and_arguments(tmp_path: Path) -> None:
    image_tool, video_tool = build_media_generation_tools(
        _workspace(tmp_path),
        _media_config(),
        provider=_FakeProvider(),
    )

    assert "Do not use for image analysis" in image_tool.description
    assert "do not retry manually" in image_tool.description
    assert "billable and may take minutes" in video_tool.description
    assert "never invent a path" in image_tool.args["reference_images"]["description"]
    assert image_tool.args["count"]["minimum"] == 1
    assert image_tool.args["count"]["maximum"] == 4
    assert "synchronized audio" in video_tool.args["generate_audio"]["description"]


@pytest.mark.asyncio
async def test_media_operational_failure_becomes_model_visible_tool_error(tmp_path: Path) -> None:
    image_tool, _ = build_media_generation_tools(
        _workspace(tmp_path),
        _media_config(),
        provider=_FailingProvider(),
    )

    result = await image_tool.ainvoke(
        {
            "name": "generate_image",
            "args": {"prompt": "a footballer"},
            "id": "image-call-1",
            "type": "tool_call",
        }
    )

    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    payload = json.loads(result.text)
    assert payload["status"] == "failed"
    assert payload["is_error"] is True
    assert payload["error"]["code"] == "model_access_required"
    assert payload["error"]["retryable"] is False
    assert payload["remediation"]["action"] == "configure_model"
    assert "Do not retry" in payload["remediation"]["model_instruction"]


@pytest.mark.asyncio
async def test_volcengine_image_request_uses_seedream_api_and_decodes_base64() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["auth"] = request.headers.get("Authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(_PNG).decode()}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = VolcengineMediaProvider(_media_config(), client=client)
        result = await provider.generate_image(
            ImageGenerationRequest(
                prompt="a red panda",
                reference_images=("https://example.com/ref.png",),
                size="2048x2048",
                count=2,
                seed=7,
            )
        )

    assert seen["path"] == "/api/v3/images/generations"
    assert seen["auth"] == "Bearer ark-test-key"
    assert seen["body"] == {
        "model": "doubao-seedream-5-0-lite-260128",
        "prompt": "a red panda",
        "response_format": "b64_json",
        "watermark": False,
        "sequential_image_generation": "auto",
        "image": ["https://example.com/ref.png"],
        "size": "2048x2048",
        "seed": 7,
        "sequential_image_generation_options": {"max_images": 2},
    }
    assert result == [GeneratedMedia(data=_PNG, media_type="image/png", extension="png")]


@pytest.mark.asyncio
async def test_seedream_5_upgrades_undersized_image_request_to_2k() -> None:
    seen_body: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_body.update(json.loads(request.content))
        return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(_PNG).decode()}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = VolcengineMediaProvider(_media_config(), client=client)
        await provider.generate_image(ImageGenerationRequest(prompt="a ball", size="1024x1024"))

    assert seen_body["size"] == "2K"


@pytest.mark.asyncio
async def test_volcengine_video_request_polls_and_downloads_without_leaking_auth() -> None:
    polls = 0
    seen_body: dict[str, Any] = {}
    download_auth: str | None = "not-called"

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal polls, download_auth
        if request.url.host == "media.example":
            download_auth = request.headers.get("Authorization")
            return httpx.Response(200, content=_MP4)
        if request.method == "POST":
            seen_body.update(json.loads(request.content))
            return httpx.Response(200, json={"id": "cgt-1"})
        polls += 1
        if polls == 1:
            return httpx.Response(200, json={"id": "cgt-1", "status": "running"})
        return httpx.Response(
            200,
            json={"id": "cgt-1", "status": "succeeded", "content": {"video_url": "https://media.example/v.mp4"}},
        )

    config = _media_config(
        video_model="doubao-seedance-2-0-260128",
        video_poll_interval_seconds=0.001,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = VolcengineMediaProvider(config, client=client)
        result = await provider.generate_video(
            VideoGenerationRequest(
                prompt="a moving camera",
                first_frame="https://example.com/first.png",
                reference_images=("data:image/png;base64,eA==",),
                duration=8,
                aspect_ratio="16:9",
                resolution="1080p",
                generate_audio=True,
            )
        )

    assert seen_body["model"] == "doubao-seedance-2-0-260128"
    assert seen_body["content"] == [
        {"type": "text", "text": "a moving camera"},
        {
            "type": "image_url",
            "image_url": {"url": "https://example.com/first.png"},
            "role": "first_frame",
        },
        {
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64,eA=="},
            "role": "reference_image",
        },
    ]
    assert seen_body["duration"] == 8
    assert seen_body["generate_audio"] is True
    assert polls == 2
    assert download_auth is None
    assert result == [GeneratedMedia(data=_MP4, media_type="video/mp4", extension="mp4")]


@pytest.mark.asyncio
async def test_volcengine_video_failure_surfaces_provider_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"id": "cgt-bad"})
        return httpx.Response(
            200,
            json={"status": "failed", "error": {"code": "Unsafe", "message": "blocked"}},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = VolcengineMediaProvider(_media_config(), client=client)
        with pytest.raises(MediaGenerationError, match=r"Unsafe: blocked") as exc_info:
            await provider.generate_video(VideoGenerationRequest(prompt="x"))

    assert exc_info.value.code == "content_rejected"
    assert exc_info.value.category == "safety"
    assert exc_info.value.safe_to_resubmit is False


@pytest.mark.asyncio
async def test_volcengine_http_auth_error_is_actionable() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={"error": {"code": "InvalidAuthentication", "message": "bad key"}},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = VolcengineMediaProvider(_media_config(), client=client)
        with pytest.raises(MediaGenerationError) as exc_info:
            await provider.generate_image(ImageGenerationRequest(prompt="x"))

    error = exc_info.value
    assert error.code == "credential_invalid"
    assert error.category == "authentication"
    assert error.remediation == "configure_credentials"
    assert error.retryable is False


@pytest.mark.asyncio
async def test_volcengine_video_timeout_cancels_remote_task() -> None:
    methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        if request.method == "POST":
            return httpx.Response(200, json={"id": "cgt-timeout"})
        if request.method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(200, json={"id": "cgt-timeout", "status": "running"})

    config = _media_config(video_timeout_seconds=0.000000001)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = VolcengineMediaProvider(config, client=client)
        with pytest.raises(MediaGenerationError, match="timed out"):
            await provider.generate_video(VideoGenerationRequest(prompt="x"))

    assert methods == ["POST", "GET", "DELETE"]


@pytest.mark.parametrize(
    ("provider_name", "provider_type", "api_key_env", "image_model", "video_model"),
    [
        (
            "volcengine",
            VolcengineMediaProvider,
            "ARK_API_KEY",
            "doubao-seedream-5-0-lite-260128",
            "doubao-seedance-2-0-mini-260615",
        ),
        (
            "dashscope",
            DashScopeMediaProvider,
            "DASHSCOPE_API_KEY",
            "wan2.7-image-pro",
            "wan3.0-video-prime",
        ),
        ("minimax", MiniMaxMediaProvider, "MINIMAX_API_KEY", "image-01", "MiniMax-H3"),
    ],
)
def test_media_provider_registry_applies_provider_defaults(
    provider_name: str,
    provider_type: type[BaseMediaProvider],
    api_key_env: str,
    image_model: str,
    video_model: str,
) -> None:
    config = MediaGenerationConfig(provider=provider_name, api_key="test")  # type: ignore[arg-type]

    provider = create_media_provider(config)

    assert isinstance(provider, provider_type)
    assert config.api_key_env == api_key_env
    assert config.image_model == image_model
    assert config.video_model == video_model


def test_media_manager_builds_named_multi_provider_routes_without_serializing_secrets(tmp_path: Path) -> None:
    config = MediaGenerationConfig(
        providers=[
            MediaProviderConfig(
                id="ark-images",
                provider="volcengine",
                api_key="ark-secret",
                video_enabled=False,
            ),
            MediaProviderConfig(
                id="minimax-videos",
                provider="minimax",
                api_key="minimax-secret",
                image_enabled=False,
            ),
        ],
        default_image_provider="ark-images",
        default_video_provider="minimax-videos",
    )

    manager = create_media_manager(config, _workspace(tmp_path))

    assert manager.route_info("image").provider_id == "ark-images"
    assert manager.route_info("image").provider_type == "volcengine"
    assert manager.route_info("video").provider_id == "minimax-videos"
    assert manager.route_info("video").provider_type == "minimax"
    serialized = config.to_dict()
    assert "ark-secret" not in json.dumps(serialized)
    assert MediaGenerationConfig.from_dict(serialized).to_dict() == serialized


@pytest.mark.asyncio
async def test_media_manager_owns_async_job_lifecycle_and_workspace_persistence(tmp_path: Path) -> None:
    provider = _AsyncFakeProvider()
    jobs = _RecordingJobStore()
    manager = MediaManager(_workspace(tmp_path), output_dir="generated", job_store=jobs)
    manager.add_provider("custom-video", provider, image_enabled=False)

    started = await manager.submit_video(VideoGenerationRequest(prompt="camera pushes in"))
    assert isinstance(started, MediaJob)
    assert started.status == "pending"

    result = await manager.wait(started.id)

    assert provider.polls == 2
    assert result.provider_id == "custom-video"
    assert result.provider_type == "fake"
    assert result.provider_task_id == "provider-task-1"
    assert len(jobs.jobs) == 1
    stored_job = next(iter(jobs.jobs.values()))
    assert stored_job.status == "succeeded"
    assert stored_job.result == result
    assert Path(result.artifacts[0].local_path).read_bytes() == _MP4


@pytest.mark.asyncio
async def test_media_manager_times_out_and_records_failed_job(tmp_path: Path) -> None:
    provider = _NeverCompletesProvider()
    jobs = _RecordingJobStore()
    manager = MediaManager(_workspace(tmp_path), output_dir="generated", job_store=jobs)
    manager.add_provider("custom-video", provider, image_enabled=False)
    started = await manager.submit_video(VideoGenerationRequest(prompt="never completes"))
    assert isinstance(started, MediaJob)

    with pytest.raises(MediaGenerationError, match="timed out") as exc_info:
        await manager.wait(started.id)

    assert exc_info.value.provider_task_id == "provider-task-1"
    assert provider.cancelled is True
    assert jobs.jobs[started.id].status == "failed"


@pytest.mark.asyncio
async def test_dashscope_wan_image_sync_request_and_download() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "dashscope-result.example":
            seen["download_auth"] = request.headers.get("Authorization")
            return httpx.Response(200, content=_PNG)
        seen["path"] = request.url.path
        seen["auth"] = request.headers.get("Authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "output": {
                    "choices": [
                        {
                            "message": {
                                "content": [{"type": "image", "image": "https://dashscope-result.example/image.png"}]
                            }
                        }
                    ]
                }
            },
        )

    config = _media_config(provider="dashscope", image_model="wan2.6-t2i")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = DashScopeMediaProvider(config, client=client)
        result = await provider.generate_image(
            ImageGenerationRequest(prompt="水墨山水", size="1280x1280", count=2, seed=9)
        )

    assert seen["path"] == "/api/v1/services/aigc/multimodal-generation/generation"
    assert seen["auth"] == "Bearer ark-test-key"
    assert seen["download_auth"] is None
    assert seen["body"] == {
        "model": "wan2.6-t2i",
        "input": {"messages": [{"role": "user", "content": [{"text": "水墨山水"}]}]},
        "parameters": {"n": 2, "watermark": False, "size": "1280*1280", "seed": 9},
    }
    assert result == [GeneratedMedia(data=_PNG, media_type="image/png", extension="png")]


@pytest.mark.asyncio
async def test_dashscope_modern_image_model_accepts_reference_images() -> None:
    seen_body: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "dashscope-result.example":
            return httpx.Response(200, content=_PNG)
        seen_body.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "output": {
                    "choices": [
                        {
                            "message": {
                                "content": [{"type": "image", "image": "https://dashscope-result.example/image.png"}]
                            }
                        }
                    ]
                }
            },
        )

    config = _media_config(provider="dashscope", image_model="wan2.7-image-pro")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = DashScopeMediaProvider(config, client=client)
        result = await provider.generate_image(
            ImageGenerationRequest(
                prompt="把图一改成夜景",
                reference_images=("https://example.com/reference.png",),
                size="2K",
                count=2,
                seed=12,
                watermark=True,
            )
        )

    assert seen_body == {
        "model": "wan2.7-image-pro",
        "input": {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"image": "https://example.com/reference.png"},
                        {"text": "把图一改成夜景"},
                    ],
                }
            ]
        },
        "parameters": {"n": 2, "watermark": True, "size": "2K", "seed": 12},
    }
    assert result == [GeneratedMedia(data=_PNG, media_type="image/png", extension="png")]


@pytest.mark.asyncio
async def test_dashscope_wan_video_async_request_polls_and_downloads() -> None:
    seen_body: dict[str, Any] = {}
    seen_async_header: str | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_async_header
        if request.url.host == "dashscope-result.example":
            return httpx.Response(200, content=_MP4)
        if request.method == "POST":
            seen_async_header = request.headers.get("X-DashScope-Async")
            seen_body.update(json.loads(request.content))
            return httpx.Response(200, json={"output": {"task_id": "wan-task", "task_status": "PENDING"}})
        return httpx.Response(
            200,
            json={
                "output": {
                    "task_id": "wan-task",
                    "task_status": "SUCCEEDED",
                    "video_url": "https://dashscope-result.example/video.mp4",
                }
            },
        )

    config = _media_config(
        provider="dashscope",
        video_model="wan2.7-t2v",
        video_poll_interval_seconds=0.001,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = DashScopeMediaProvider(config, client=client)
        result = await provider.generate_video(
            VideoGenerationRequest(
                prompt="一只猫在月光下奔跑",
                duration=10,
                aspect_ratio="9:16",
                resolution="720p",
                watermark=True,
            )
        )

    assert seen_async_header == "enable"
    assert seen_body == {
        "model": "wan2.7-t2v",
        "input": {"prompt": "一只猫在月光下奔跑"},
        "parameters": {
            "resolution": "720P",
            "ratio": "9:16",
            "duration": 10,
            "watermark": True,
        },
    }
    assert result == [GeneratedMedia(data=_MP4, media_type="video/mp4", extension="mp4")]


@pytest.mark.asyncio
async def test_dashscope_wan3_video_maps_provider_neutral_media() -> None:
    seen_body: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_body.update(json.loads(request.content))
        return httpx.Response(200, json={"output": {"task_id": "wan3-task", "task_status": "PENDING"}})

    config = _media_config(provider="dashscope", video_model="wan3.0-video-prime")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = DashScopeMediaProvider(config, client=client)
        submission = await provider.submit_video(
            VideoGenerationRequest(
                prompt="让角色转身看向镜头",
                first_frame="https://example.com/first.png",
                reference_images=("data:image/png;base64,eA==",),
                duration=12,
                aspect_ratio="9:16",
                resolution="1080p",
                generate_audio=True,
                seed=8,
                watermark=True,
            )
        )

    assert submission.task == ProviderTask(task_id="wan3-task", kind="video", model="wan3.0-video-prime")
    assert seen_body == {
        "model": "wan3.0-video-prime",
        "input": {
            "prompt": "让角色转身看向镜头",
            "media": [
                {"type": "first_frame", "url": "https://example.com/first.png"},
                {"type": "reference_image", "url": "data:image/png;base64,eA=="},
            ],
        },
        "parameters": {
            "resolution": "1080P",
            "ratio": "adaptive",
            "duration": 12,
            "watermark": True,
            "seed": 8,
            "audio": True,
        },
    }


@pytest.mark.asyncio
async def test_minimax_image_request_decodes_base64() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "data": {"image_base64": [base64.b64encode(_PNG).decode()]},
                "base_resp": {"status_code": 0, "status_msg": "success"},
            },
        )

    config = _media_config(provider="minimax")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = MiniMaxMediaProvider(config, client=client)
        result = await provider.generate_image(
            ImageGenerationRequest(prompt="未来城市", size="16:9", count=2, seed=42, watermark=True)
        )

    assert seen["path"] == "/v1/image_generation"
    assert seen["body"] == {
        "model": "image-01",
        "prompt": "未来城市",
        "response_format": "base64",
        "n": 2,
        "prompt_optimizer": False,
        "aigc_watermark": True,
        "aspect_ratio": "16:9",
        "seed": 42,
    }
    assert result == [GeneratedMedia(data=_PNG, media_type="image/png", extension="png")]


@pytest.mark.asyncio
async def test_minimax_image_request_maps_subject_references() -> None:
    seen_body: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_body.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "data": {"image_base64": [base64.b64encode(_PNG).decode()]},
                "base_resp": {"status_code": 0, "status_msg": "success"},
            },
        )

    config = _media_config(provider="minimax")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = MiniMaxMediaProvider(config, client=client)
        await provider.generate_image(
            ImageGenerationRequest(
                prompt="保留人物主体并改成油画风格",
                reference_images=("https://example.com/person.jpg",),
            )
        )

    assert seen_body["subject_reference"] == [{"type": "character", "image_file": "https://example.com/person.jpg"}]


@pytest.mark.asyncio
async def test_minimax_h3_max_rejects_unsupported_2k_resolution() -> None:
    config = _media_config(provider="minimax", video_model="MiniMax-H3-Max")
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(500))) as client:
        provider = MiniMaxMediaProvider(config, client=client)
        with pytest.raises(MediaGenerationError, match="supports only 480p or 768p"):
            await provider.submit_video(VideoGenerationRequest(prompt="x", duration=5, resolution="1080p"))


@pytest.mark.asyncio
async def test_minimax_h3_submit_and_poll_multimodal_video() -> None:
    seen_body: dict[str, Any] = {}
    queried = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal queried
        if request.url.host == "minimax-result.example":
            return httpx.Response(200, content=_MP4)
        if request.method == "POST":
            seen_body.update(json.loads(request.content))
            return httpx.Response(200, json={"task_id": "h3-task"})
        queried = True
        return httpx.Response(
            200,
            json={
                "task": {
                    "id": "h3-task",
                    "status": "succeeded",
                    "content": {"url": "https://minimax-result.example/video.mp4"},
                }
            },
        )

    config = _media_config(provider="minimax", video_poll_interval_seconds=0.001)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = MiniMaxMediaProvider(config, client=client)
        submission = await provider.submit_video(
            VideoGenerationRequest(
                prompt="镜头缓慢推进",
                first_frame="https://example.com/first.png",
                last_frame="data:image/png;base64,eA==",
                duration=8,
                aspect_ratio="16:9",
                resolution="1080p",
                watermark=True,
            )
        )
        assert submission.task == ProviderTask(task_id="h3-task", kind="video", model="MiniMax-H3")
        assert queried is False
        assert submission.task is not None
        update = await provider.poll(submission.task)
        assert update.status == "succeeded"
        assert update.artifacts[0].url == "https://minimax-result.example/video.mp4"
        assert queried is True
        queried = False

        result = await provider.generate_video(
            VideoGenerationRequest(
                prompt="镜头缓慢推进",
                first_frame="https://example.com/first.png",
                last_frame="data:image/png;base64,eA==",
                duration=8,
                aspect_ratio="16:9",
                resolution="1080p",
                watermark=True,
            )
        )

    assert queried is True
    assert seen_body == {
        "model": "MiniMax-H3",
        "content": [
            {"type": "text", "text": "镜头缓慢推进"},
            {
                "type": "image_url",
                "image_url": {"url": "https://example.com/first.png"},
                "role": "first_frame",
            },
            {
                "type": "image_url",
                "image_url": {"url": "data:image/png;base64,eA=="},
                "role": "last_frame",
            },
        ],
        "resolution": "2K",
        "duration": 8,
        "ratio": "adaptive",
        "aigc_watermark": True,
    }
    assert result == [GeneratedMedia(data=_MP4, media_type="video/mp4", extension="mp4")]


def test_agent_registers_media_tools_and_defers_them_by_default(tmp_path: Path) -> None:
    config = HarnessAgentConfig(
        workspace_dir=tmp_path,
        backend={"type": "filesystem", "root_dir": str(tmp_path), "virtual_mode": False},
        providers=[
            ProviderConfig(
                id="p",
                base_url="https://example.com/v1",
                api_key="test",
                models=[ModelConfig(id="text")],
            )
        ],
        default_model="p/text",
        media_generation=_media_config(),
        web_search_tools=False,
        memory_enabled=False,
        checkpointer=False,
    )
    captured: dict[str, Any] = {}

    def fake_create(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return MagicMock()

    with (
        patch("langchain_openai.ChatOpenAI", return_value=MagicMock()),
        patch("deepagents.create_deep_agent", side_effect=fake_create),
    ):
        HarnessAgent(config)

    tool_names = {tool.name for tool in captured["tools"]}
    assert {"generate_image", "generate_video"} <= tool_names
    search = next(item for item in captured["middleware"] if type(item).__name__ == "ToolSearchMiddleware")
    assert search._deferred_tools >= {"generate_image", "generate_video"}


def test_agent_hides_media_tools_without_credentials_and_informs_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ARK_API_KEY", raising=False)
    config = HarnessAgentConfig(
        workspace_dir=tmp_path,
        backend={"type": "filesystem", "root_dir": str(tmp_path), "virtual_mode": False},
        providers=[
            ProviderConfig(
                id="p",
                base_url="https://example.com/v1",
                api_key="test",
                models=[ModelConfig(id="text")],
            )
        ],
        default_model="p/text",
        media_generation=MediaGenerationConfig(),
        web_search_tools=False,
        memory_enabled=False,
        checkpointer=False,
    )
    captured: dict[str, Any] = {}

    def fake_create(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return MagicMock()

    with (
        patch("langchain_openai.ChatOpenAI", return_value=MagicMock()),
        patch("deepagents.create_deep_agent", side_effect=fake_create),
    ):
        HarnessAgent(config)

    tool_names = {tool.name for tool in captured["tools"]}
    assert "generate_image" not in tool_names
    assert "generate_video" not in tool_names
    assert "credentials are missing" in captured["system_prompt"]
    assert "do not retry or claim success" in captured["system_prompt"]


@pytest.mark.parametrize(
    ("config", "expected"),
    [
        (_media_config(video_enabled=False), {"generate_image"}),
        (_media_config(image_enabled=False), {"generate_video"}),
    ],
)
def test_agent_registers_only_enabled_media_tools(
    tmp_path: Path,
    config: MediaGenerationConfig,
    expected: set[str],
) -> None:
    harness_config = HarnessAgentConfig(
        workspace_dir=tmp_path,
        backend={"type": "filesystem", "root_dir": str(tmp_path), "virtual_mode": False},
        providers=[
            ProviderConfig(
                id="p",
                base_url="https://example.com/v1",
                api_key="test",
                models=[ModelConfig(id="text")],
            )
        ],
        default_model="p/text",
        media_generation=config,
        web_search_tools=False,
        memory_enabled=False,
        checkpointer=False,
    )
    captured: dict[str, Any] = {}

    def fake_create(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return MagicMock()

    with (
        patch("langchain_openai.ChatOpenAI", return_value=MagicMock()),
        patch("deepagents.create_deep_agent", side_effect=fake_create),
    ):
        HarnessAgent(harness_config)

    media_names = {tool.name for tool in captured["tools"]} & {"generate_image", "generate_video"}
    assert media_names == expected
    search = next(item for item in captured["middleware"] if type(item).__name__ == "ToolSearchMiddleware")
    assert search._deferred_tools & {"generate_image", "generate_video"} == expected
