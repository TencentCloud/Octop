"""Instance-wide media-generation settings for harness agents."""

from __future__ import annotations

import base64
import dataclasses
import importlib
import json
import re
import struct
import zlib
from contextlib import suppress
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import urlsplit, urlunsplit

import httpx

from octop.infra.connectors.crypto import decrypt_credentials, encrypt_credentials
from octop.infra.db.repos.secrets import SecretRepo
from octop.infra.db.repos.settings import SettingsRepo
from octop.infra.errors import ErrorCode, OctopError

if TYPE_CHECKING:
    from octop_harness import MediaGenerationConfig

MediaProviderName = Literal["volcengine", "dashscope", "minimax", "tencent-tokenhub"]
MediaTestKind = Literal["image", "video", "3d"]

DEFAULT_PROVIDER_ID = "volcengine-default"
DEFAULT_ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_IMAGE_MODEL = "doubao-seedream-5-0-lite-260128"
DEFAULT_VIDEO_MODEL = "doubao-seedance-2-0-mini-260615"

_PROVIDER_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_MAX_PROVIDERS = 8
_KEY_CONFIG = "media_generation_config_v2"
_SECRET_CREDENTIALS_V2 = "media_generation_credentials_v2"

# Legacy single-provider keys. They remain read-only so existing installations
# become a named Volcengine provider without a database migration.
_KEY_ENABLED = "media_generation_enabled"
_KEY_IMAGE_ENABLED = "media_generation_image_enabled"
_KEY_VIDEO_ENABLED = "media_generation_video_enabled"
_KEY_IMAGE_MODEL = "media_generation_image_model"
_KEY_VIDEO_MODEL = "media_generation_video_model"
_SECRET_CREDENTIALS = "media_generation_credentials"


@dataclass(frozen=True)
class MediaProviderPreset:
    """Built-in provider defaults shown by the admin UI."""

    provider: MediaProviderName
    display_name: str
    base_url: str
    image_models: tuple[str, ...]
    video_models: tuple[str, ...]
    three_d_models: tuple[str, ...] = ()

    @property
    def default_image_model(self) -> str:
        return self.image_models[0]

    @property
    def default_video_model(self) -> str:
        return self.video_models[0]

    @property
    def supports_three_d(self) -> bool:
        return bool(self.three_d_models)

    @property
    def default_three_d_model(self) -> str:
        return self.three_d_models[0] if self.three_d_models else ""


MEDIA_PROVIDER_PRESETS: dict[MediaProviderName, MediaProviderPreset] = {
    "volcengine": MediaProviderPreset(
        provider="volcengine",
        display_name="Volcengine Ark",
        base_url=DEFAULT_ARK_BASE_URL,
        image_models=(
            DEFAULT_IMAGE_MODEL,
            "doubao-seedream-5-0-pro-260628",
            "doubao-seedream-5-0-260128",
        ),
        video_models=(
            DEFAULT_VIDEO_MODEL,
            "doubao-seedance-2-5-260628",
            "doubao-seedance-2-0-fast-260128",
            "doubao-seedance-2-0-260128",
        ),
    ),
    "dashscope": MediaProviderPreset(
        provider="dashscope",
        display_name="Alibaba Cloud Model Studio",
        base_url="https://dashscope.aliyuncs.com/api/v1",
        image_models=(
            "wan2.7-image-pro",
            "wan2.7-image",
            "qwen-image-3.0-pro",
            "qwen-image-3.0",
            "wan2.6-image",
            "wan2.6-t2i",
        ),
        video_models=(
            "wan3.0-video-prime",
            "wan3.0-video",
            "wan2.7-t2v",
            "wan2.7-i2v",
            "wan2.7-r2v",
        ),
    ),
    "minimax": MediaProviderPreset(
        provider="minimax",
        display_name="MiniMax",
        base_url="https://api.minimax.cn",
        image_models=("image-01", "image-01-live"),
        video_models=("MiniMax-H3", "MiniMax-H3-Max"),
    ),
    "tencent-tokenhub": MediaProviderPreset(
        provider="tencent-tokenhub",
        display_name="Tencent Cloud TokenHub",
        base_url="https://tokenhub.tencentmaas.com/v1",
        image_models=(
            "hy-image-v3.5-preview",
            "wand-vega-image-1.5-pro",
            "wand-vega-image-pro",
            "wand-vega-image-flash",
            "wand-vega-image-lite",
            "seedream-image-v5.5",
            "seedream-image-v5.0-pro",
            "seedream-image-v5.0-flash",
            "kling-image-v4",
            "kling-image-v4-long",
            "kling-image-v3-omni",
            "kling-image-v3",
            "kling-image-o1",
            "vidu-image-q2",
            "hidream-image-o1-1.5",
            "hidream-image-o1-1.5-edit",
            "minimax-image-h3",
            "minimax-image-h3-highspeed",
        ),
        video_models=(
            "hy-video-v1.5",
            "wand-vega-video-1.5-lite",
            "wand-vega-video-1.0-lite",
            "kling-video-v4",
            "kling-video-v4-flash",
            "kling-video-v3",
            "kling-video-v3-omni",
            "kling-video-v3-turbo",
            "kling-video-o1",
            "kling-video-v2.6",
            "kling-video-v2.5-turbo",
            "vidu-video-q4-preview",
            "vidu-video-q3-pro",
            "vidu-video-q3-turbo",
            "vidu-video-q3",
            "vidu-video-q2-pro",
            "vidu-video-q2-turbo",
            "vidu-video-q2",
            "pixverse-video-v6.0-max",
            "pixverse-video-v6.0",
            "pixverse-video-c1",
            "pixverse-video-v5.6",
            "minimax-video-h3",
            "minimax-video-h3-max",
            "minimax-video-h3-highspeed",
            "minimax-video-h3-lite",
            "minimax-video-v2.3",
            "minimax-video-v2.3-fast",
            "yt-video-2.0",
        ),
        three_d_models=(
            "hy-3d-3.6",
            "hy-3d-3.1",
            "hy-3d-3.0",
            "hy-3d-express",
            "tripo-3d-3.1",
            "tripo-3d-p2",
            "tripo-3d-p1",
            "hi3d-3.0",
            "hi3d-2.1",
            "rodin-gen-3d-2.5",
        ),
    ),
}


@dataclass(frozen=True)
class MediaProviderUpdate:
    """One provider instance accepted from the administration surface."""

    id: str
    provider: MediaProviderName
    display_name: str
    enabled: bool
    base_url: str
    image_enabled: bool
    video_enabled: bool
    image_model: str
    video_model: str
    three_d_enabled: bool = False
    three_d_model: str = ""
    api_key: str | None = field(default=None, repr=False, compare=False)
    clear_api_key: bool = False


@dataclass(frozen=True)
class MediaProviderSettings:
    """Admin-visible provider settings; credentials are never exposed."""

    id: str
    provider: MediaProviderName
    display_name: str
    enabled: bool
    base_url: str
    image_enabled: bool
    video_enabled: bool
    image_model: str
    video_model: str
    api_key_set: bool
    three_d_enabled: bool = False
    three_d_model: str = ""

    @property
    def configured(self) -> bool:
        return bool(
            self.enabled
            and self.api_key_set
            and (self.image_enabled or self.video_enabled or self.three_d_enabled)
        )


def _kind_enabled_attr(kind: MediaTestKind) -> str:
    if kind == "image":
        return "image_enabled"
    if kind == "video":
        return "video_enabled"
    return "three_d_enabled"


def _kind_route_field(kind: MediaTestKind) -> str:
    if kind == "image":
        return "default_image_provider"
    if kind == "video":
        return "default_video_provider"
    return "default_three_d_provider"


@dataclass(frozen=True)
class MediaGenerationSettings:
    """Complete admin-visible media configuration."""

    enabled: bool
    providers: tuple[MediaProviderSettings, ...]
    default_image_provider: str | None
    default_video_provider: str | None
    default_three_d_provider: str | None = None

    def provider_by_id(self, provider_id: str | None) -> MediaProviderSettings | None:
        if provider_id is None:
            return None
        return next((item for item in self.providers if item.id == provider_id), None)

    def has_configured_route(self, kind: MediaTestKind) -> bool:
        route = getattr(self, _kind_route_field(kind))
        provider = self.provider_by_id(route)
        return bool(
            provider and provider.configured and getattr(provider, _kind_enabled_attr(kind))
        )

    @property
    def configured(self) -> bool:
        return bool(
            self.enabled
            and (
                self.has_configured_route("image")
                or self.has_configured_route("video")
                or self.has_configured_route("3d")
            )
        )


def _stored_bool(settings: SettingsRepo, key: str, *, default: bool) -> bool:
    raw = settings.get(key)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes"}


def _bad_args(message: str) -> OctopError:
    return OctopError(ErrorCode.SLASH_BAD_ARGS, message)


def _normalized_update(item: MediaProviderUpdate) -> MediaProviderUpdate:
    return MediaProviderUpdate(
        id=item.id.strip(),
        provider=item.provider,
        display_name=item.display_name.strip(),
        enabled=item.enabled,
        base_url=item.base_url.strip().rstrip("/"),
        image_enabled=item.image_enabled,
        video_enabled=item.video_enabled,
        image_model=item.image_model.strip(),
        video_model=item.video_model.strip(),
        three_d_enabled=item.three_d_enabled,
        three_d_model=item.three_d_model.strip(),
        api_key=(item.api_key or "").strip() or None,
        clear_api_key=item.clear_api_key,
    )


def _validate_provider(item: MediaProviderUpdate) -> None:
    if not _PROVIDER_ID.fullmatch(item.id):
        raise _bad_args(
            "provider id must use 1-64 lowercase letters, numbers, dots, underscores, or hyphens"
        )
    if item.provider not in MEDIA_PROVIDER_PRESETS:
        raise _bad_args(f"unsupported media provider: {item.provider}")
    preset = MEDIA_PROVIDER_PRESETS[item.provider]
    if not item.display_name:
        raise _bad_args(f"display_name is required for provider {item.id}")
    parsed = urlsplit(item.base_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise _bad_args(f"provider {item.id} base_url must be an HTTPS URL")
    if item.three_d_enabled and not preset.supports_three_d:
        raise _bad_args(f"provider {item.provider} does not support 3D generation")
    if item.enabled and not (item.image_enabled or item.video_enabled or item.three_d_enabled):
        raise _bad_args(f"provider {item.id} must enable image, video, or 3D generation")
    if item.enabled and item.image_enabled and not item.image_model:
        raise _bad_args(f"image_model is required for provider {item.id}")
    if item.enabled and item.video_enabled and not item.video_model:
        raise _bad_args(f"video_model is required for provider {item.id}")
    if item.enabled and item.three_d_enabled and not item.three_d_model:
        raise _bad_args(f"three_d_model is required for provider {item.id}")


def _probe_url(provider: MediaProviderName, base_url: str) -> str:
    base = base_url.rstrip("/")
    if provider == "volcengine":
        parsed = urlsplit(base)
        return urlunsplit((parsed.scheme, parsed.netloc, "/ping", "", ""))
    if provider == "dashscope":
        return f"{base}/models?page_no=1&page_size=1"
    return f"{base}/models" if base.endswith("/v1") else f"{base}/v1/models"


def _models_list_url(provider: MediaProviderName, base_url: str) -> str:
    base = base_url.rstrip("/")
    if provider == "dashscope":
        return f"{base}/models?page_no=1&page_size=200"
    if provider == "volcengine":
        return f"{base}/models"
    return f"{base}/models" if base.endswith("/v1") else f"{base}/v1/models"


_TOKENHUB_IMAGE_PREFIXES = (
    "hy-image-",
    "wand-vega-image",
    "vidu-image",
    "seedream-image",
    "kling-image",
    "hidream-image",
    "minimax-image",
)
_TOKENHUB_VIDEO_PREFIXES = (
    "hy-video",
    "wand-vega-video",
    "kling-video",
    "vidu-video",
    "pixverse-video",
    "minimax-video",
    "yt-video",
)
_TOKENHUB_VIDEO_EXCLUDES = ("motion-control", "humanactor", "-fx")
_TOKENHUB_3D_PREFIXES = ("hy-3d-", "tripo-3d-", "hi3d-", "rodin-gen-3d-")
_TOKENHUB_3D_EXCLUDES = (
    "-component",
    "-format",
    "-texture",
    "-uv",
    "-retopology",
    "-rigging",
    "-motion",
    "-polygen",
    "-animation",
)


def _classify_remote_models(
    provider: MediaProviderName,
    entries: list[dict[str, Any]],
) -> tuple[list[str], list[str], list[str]]:
    """Classify online remote model entries into image, video, and 3D model lists."""
    preset = MEDIA_PROVIDER_PRESETS[provider]
    image_found: list[str] = []
    video_found: list[str] = []
    three_d_found: list[str] = []

    for item in entries:
        model_id = str(item.get("id") or item.get("model") or "").strip()
        if not model_id:
            continue
        status = str(item.get("status") or "").strip().lower()
        if status and status not in {"online", "active", "available", "enabled"}:
            continue
        # Skip chat/multimodal LLMs that advertise token generation limits.
        if item.get("max_output_tokens") is not None:
            continue
        lower = model_id.lower()
        if provider == "tencent-tokenhub":
            if lower.startswith(_TOKENHUB_IMAGE_PREFIXES):
                image_found.append(model_id)
            elif lower.startswith(_TOKENHUB_VIDEO_PREFIXES) and not any(
                tok in lower for tok in _TOKENHUB_VIDEO_EXCLUDES
            ):
                video_found.append(model_id)
            elif lower.startswith(_TOKENHUB_3D_PREFIXES) and not any(
                tok in lower for tok in _TOKENHUB_3D_EXCLUDES
            ):
                three_d_found.append(model_id)
        elif provider == "volcengine":
            if ("seedream" in lower or "t2i" in lower or "image" in lower) and "video" not in lower:
                image_found.append(model_id)
            elif any(tok in lower for tok in ("seedance", "t2v", "i2v", "video")) and (
                "vision" not in lower and "-vl" not in lower
            ):
                video_found.append(model_id)
        elif provider == "dashscope":
            if any(tok in lower for tok in ("qwen-image", "z-image", "flux")) or (
                "wan" in lower and any(tok in lower for tok in ("t2i", "i2i", "image"))
            ):
                image_found.append(model_id)
            elif "wan" in lower and any(
                tok in lower for tok in ("t2v", "i2v", "kf2v", "r2v", "video")
            ):
                video_found.append(model_id)
        elif provider == "minimax":
            if lower.startswith("image-") or "image" in lower:
                image_found.append(model_id)
            elif any(tok in lower for tok in ("hailuo", "minimax-h3", "video")):
                video_found.append(model_id)

    def _merge(preset_models: tuple[str, ...], discovered: list[str]) -> list[str]:
        if not discovered:
            return list(preset_models)
        discovered_set = set(discovered)
        ordered = [m for m in preset_models if m in discovered_set]
        extras = sorted(m for m in discovered_set if m not in set(ordered))
        # Keep any preset models not returned by remote at the end so defaults remain selectable.
        missing_presets = [m for m in preset_models if m not in discovered_set]
        return [*ordered, *extras, *missing_presets]

    return (
        _merge(preset.image_models, image_found),
        _merge(preset.video_models, video_found),
        _merge(preset.three_d_models, three_d_found) if preset.supports_three_d else [],
    )


async def fetch_media_provider_models(
    provider: MediaProviderName,
    api_key: str,
    *,
    base_url: str,
    client: httpx.AsyncClient | None = None,
) -> dict[str, object]:
    """Fetch remote models from a provider's model-list endpoint and classify by modality."""

    async def _request(http: httpx.AsyncClient) -> httpx.Response:
        return await http.get(
            _models_list_url(provider, base_url),
            headers={"Authorization": f"Bearer {api_key}"},
        )

    try:
        if client is not None:
            response = await _request(client)
        else:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as http:
                response = await _request(http)
    except httpx.HTTPError as exc:
        return {"ok": False, "error": str(exc)}

    if response.status_code in {401, 403}:
        return {"ok": False, "error": "Media provider authentication failed"}
    if response.is_error:
        return {
            "ok": False,
            "error": f"Model list endpoint returned HTTP {response.status_code}",
        }
    try:
        payload = response.json()
    except ValueError:
        return {"ok": False, "error": "Model list endpoint returned invalid JSON"}

    raw_items: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        if isinstance(payload.get("data"), list):
            raw_items = [item for item in payload["data"] if isinstance(item, dict)]
        elif isinstance(payload.get("output"), dict) and isinstance(
            payload["output"].get("models"), list
        ):
            raw_items = [item for item in payload["output"]["models"] if isinstance(item, dict)]
        elif isinstance(payload.get("models"), list):
            raw_items = [item for item in payload["models"] if isinstance(item, dict)]

    image_models, video_models, three_d_models = _classify_remote_models(provider, raw_items)
    return {
        "ok": True,
        "image_models": image_models,
        "video_models": video_models,
        "three_d_models": three_d_models,
        "total_remote": len(raw_items),
    }


async def verify_media_credentials(
    provider: MediaProviderName,
    api_key: str,
    *,
    base_url: str,
    client: httpx.AsyncClient | None = None,
) -> dict[str, object]:
    """Run a non-generation authenticated probe for one built-in provider."""

    async def _request(http: httpx.AsyncClient) -> httpx.Response:
        return await http.get(
            _probe_url(provider, base_url),
            headers={"Authorization": f"Bearer {api_key}"},
        )

    try:
        if client is not None:
            response = await _request(client)
        else:
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as http:
                response = await _request(http)
    except httpx.HTTPError as exc:
        return {"ok": False, "error": str(exc)}

    if response.status_code in {401, 403}:
        return {"ok": False, "error": "Media provider authentication failed"}
    if response.is_error:
        return {
            "ok": False,
            "error": f"Media provider probe returned HTTP {response.status_code}",
        }
    with suppress(ValueError):
        payload = response.json()
        if isinstance(payload, dict):
            base_resp = payload.get("base_resp")
            if isinstance(base_resp, dict) and base_resp.get("status_code") not in {
                None,
                0,
                "0",
            }:
                return {
                    "ok": False,
                    "error": str(base_resp.get("status_msg") or base_resp),
                }
            if payload.get("code") and payload.get("message"):
                return {"ok": False, "error": str(payload["message"])}
            error = payload.get("error")
            if isinstance(error, dict) and (error.get("message") or error.get("code")):
                return {"ok": False, "error": str(error.get("message") or error)}
            if isinstance(error, str) and error.strip():
                return {"ok": False, "error": error.strip()}
    return {"ok": True}


_IMAGE_ONLY_VIDEO_MODELS = frozenset(
    {
        "vidu-video-q4-preview",
        "vidu-video-q3",
        "vidu-video-q2-pro",
        "vidu-video-q2-turbo",
        "minimax-video-v2.3-fast",
        "yt-video-2.0",
    }
)
_IMAGE_ONLY_3D_MODELS = frozenset({"hy-3d-3.6", "hi3d-3.0", "hi3d-2.1"})


def _minimal_test_png_data_url(size: int = 320) -> str:
    """Return a tiny solid-color PNG data URL meeting >=300px image/video/3D inputs."""

    def _chunk(chunk_type: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", crc)

    row = b"\x00" + bytes((66, 133, 244)) * size
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    raw = (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(row * size, level=9))
        + _chunk(b"IEND", b"")
    )
    return f"data:image/png;base64,{base64.b64encode(raw).decode('ascii')}"


def _construct_dataclass_compat(cls: type[Any], **kwargs: Any) -> Any:
    """Instantiate a harness dataclass while ignoring fields absent in older SDK versions."""
    field_names = {entry.name for entry in dataclasses.fields(cls)}
    filtered = {key: value for key, value in kwargs.items() if key in field_names}
    return cls(**filtered)


async def verify_media_model(
    item: MediaProviderUpdate,
    api_key: str,
    *,
    kind: MediaTestKind,
) -> dict[str, object]:
    """Submit one provider-neutral model probe through the harness adapter."""
    from octop_harness import MediaProviderConfig  # noqa: PLC0415
    from octop_harness.media import (  # noqa: PLC0415
        ImageGenerationRequest,
        MediaGenerationError,
        VideoGenerationRequest,
        create_media_provider,
    )

    media_mod = importlib.import_module("octop_harness.media")
    supported_providers = getattr(media_mod, "BUILTIN_MEDIA_PROVIDERS", ())
    if supported_providers and item.provider not in supported_providers:
        return {
            "ok": False,
            "error": (
                f"Installed octop-harness does not support provider {item.provider!r}; "
                "upgrade octop-harness."
            ),
        }

    config = _construct_dataclass_compat(
        MediaProviderConfig,
        id=item.id,
        provider=item.provider,
        api_key=api_key,
        base_url=item.base_url,
        image_model=item.image_model,
        video_model=item.video_model,
        three_d_model=item.three_d_model,
        image_enabled=item.image_enabled,
        video_enabled=item.video_enabled,
        three_d_enabled=item.three_d_enabled,
    )
    provider = create_media_provider(config)
    try:
        if kind == "image":
            image_model = item.image_model.strip().lower()
            reference_images = (
                (_minimal_test_png_data_url(320),) if image_model.endswith("-edit") else ()
            )
            submission = await provider.submit_image(
                ImageGenerationRequest(
                    prompt="A plain blue circle centered on a white background.",
                    reference_images=reference_images,
                    count=1,
                    watermark=False,
                )
            )
        elif kind == "video":
            video_model = item.video_model.strip().lower()
            first_frame = (
                _minimal_test_png_data_url(320) if video_model in _IMAGE_ONLY_VIDEO_MODELS else None
            )
            submission = await provider.submit_video(
                VideoGenerationRequest(
                    prompt="A static blue circle on a white background.",
                    first_frame=first_frame,
                    duration=5,
                    aspect_ratio="16:9",
                    resolution="480p",
                    generate_audio=False,
                    watermark=False,
                )
            )
        else:
            three_d_req_cls = getattr(media_mod, "ThreeDGenerationRequest", None)
            submit_3d = getattr(provider, "submit_3d", None)
            if three_d_req_cls is None or submit_3d is None:
                return {
                    "ok": False,
                    "error": (
                        "Installed octop-harness does not support 3D generation; "
                        "upgrade octop-harness."
                    ),
                }
            three_d_model = item.three_d_model.strip().lower()
            three_d_request = (
                three_d_req_cls(image=_minimal_test_png_data_url(320))
                if three_d_model in _IMAGE_ONLY_3D_MODELS
                else three_d_req_cls(prompt="A simple blue sphere.")
            )
            submission = await submit_3d(three_d_request)
        if submission.task is not None:
            await provider.cancel(submission.task)
    except (MediaGenerationError, ValueError) as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True}


class MediaGenerationSettingsStore:
    """Persist provider routes and an encrypted credential map."""

    def __init__(self, *, settings_repo: SettingsRepo, secret_repo: SecretRepo) -> None:
        self._settings = settings_repo
        self._secrets = secret_repo

    def load(self) -> MediaGenerationSettings:
        raw = self._settings.get(_KEY_CONFIG)
        if raw:
            with suppress(json.JSONDecodeError, TypeError, ValueError):
                payload = json.loads(raw)
                if isinstance(payload, dict):
                    return self._load_v2(payload)
        return self._load_legacy()

    def _load_v2(self, payload: dict[str, Any]) -> MediaGenerationSettings:
        credentials = self._credentials()
        providers: list[MediaProviderSettings] = []
        raw_providers = payload.get("providers")
        if isinstance(raw_providers, list):
            for raw in raw_providers:
                if not isinstance(raw, dict):
                    continue
                provider = raw.get("provider")
                if provider not in MEDIA_PROVIDER_PRESETS:
                    continue
                preset = MEDIA_PROVIDER_PRESETS[provider]
                provider_id = str(raw.get("id") or "").strip()
                if not provider_id:
                    continue
                providers.append(
                    MediaProviderSettings(
                        id=provider_id,
                        provider=provider,
                        display_name=str(raw.get("display_name") or preset.display_name).strip(),
                        enabled=bool(raw.get("enabled", True)),
                        base_url=str(raw.get("base_url") or preset.base_url).strip().rstrip("/"),
                        image_enabled=bool(raw.get("image_enabled", True)),
                        video_enabled=bool(raw.get("video_enabled", True)),
                        image_model=str(
                            raw.get("image_model") or preset.default_image_model
                        ).strip(),
                        video_model=str(
                            raw.get("video_model") or preset.default_video_model
                        ).strip(),
                        api_key_set=bool(credentials.get(provider_id)),
                        three_d_enabled=(
                            bool(raw.get("three_d_enabled", False))
                            if preset.supports_three_d
                            else False
                        ),
                        three_d_model=(
                            str(raw.get("three_d_model") or preset.default_three_d_model).strip()
                            if preset.supports_three_d
                            else ""
                        ),
                    )
                )
        return MediaGenerationSettings(
            enabled=bool(payload.get("enabled", False)),
            providers=tuple(providers),
            default_image_provider=_optional_string(payload.get("default_image_provider")),
            default_video_provider=_optional_string(payload.get("default_video_provider")),
            default_three_d_provider=_optional_string(payload.get("default_three_d_provider")),
        )

    def _load_legacy(self) -> MediaGenerationSettings:
        credentials = self._credentials()
        image_enabled = _stored_bool(self._settings, _KEY_IMAGE_ENABLED, default=True)
        video_enabled = _stored_bool(self._settings, _KEY_VIDEO_ENABLED, default=True)
        provider = MediaProviderSettings(
            id=DEFAULT_PROVIDER_ID,
            provider="volcengine",
            display_name=MEDIA_PROVIDER_PRESETS["volcengine"].display_name,
            enabled=True,
            base_url=DEFAULT_ARK_BASE_URL,
            image_enabled=image_enabled,
            video_enabled=video_enabled,
            image_model=(self._settings.get(_KEY_IMAGE_MODEL) or DEFAULT_IMAGE_MODEL).strip(),
            video_model=(self._settings.get(_KEY_VIDEO_MODEL) or DEFAULT_VIDEO_MODEL).strip(),
            api_key_set=bool(credentials.get(DEFAULT_PROVIDER_ID)),
            three_d_enabled=False,
            three_d_model="",
        )
        return MediaGenerationSettings(
            enabled=_stored_bool(self._settings, _KEY_ENABLED, default=False),
            providers=(provider,),
            default_image_provider=DEFAULT_PROVIDER_ID if image_enabled else None,
            default_video_provider=DEFAULT_PROVIDER_ID if video_enabled else None,
            default_three_d_provider=None,
        )

    def save(
        self,
        *,
        enabled: bool,
        providers: list[MediaProviderUpdate],
        default_image_provider: str | None,
        default_video_provider: str | None,
        default_three_d_provider: str | None = None,
    ) -> MediaGenerationSettings:
        if len(providers) > _MAX_PROVIDERS:
            raise _bad_args(f"at most {_MAX_PROVIDERS} media providers are allowed")

        normalized = [_normalized_update(item) for item in providers]
        provider_ids = [item.id for item in normalized]
        if len(provider_ids) != len(set(provider_ids)):
            raise _bad_args("media provider ids must be unique")
        if enabled and not normalized:
            raise _bad_args("at least one media provider is required")
        for item in normalized:
            _validate_provider(item)
        if enabled and not any(item.enabled for item in normalized):
            raise _bad_args("at least one media provider must be enabled")

        old_credentials = self._credentials()
        credentials: dict[str, str] = {}
        for item in normalized:
            if item.clear_api_key:
                continue
            api_key = item.api_key or old_credentials.get(item.id)
            if api_key:
                credentials[item.id] = api_key

        image_route = _optional_string(default_image_provider)
        video_route = _optional_string(default_video_provider)
        three_d_route = _optional_string(default_three_d_provider)
        by_id = {item.id: item for item in normalized}
        self._validate_route(
            kind="image",
            route=image_route,
            enabled=enabled,
            providers=normalized,
            by_id=by_id,
            credentials=credentials,
        )
        self._validate_route(
            kind="video",
            route=video_route,
            enabled=enabled,
            providers=normalized,
            by_id=by_id,
            credentials=credentials,
        )
        self._validate_route(
            kind="3d",
            route=three_d_route,
            enabled=enabled,
            providers=normalized,
            by_id=by_id,
            credentials=credentials,
        )

        credential_blob = encrypt_credentials(self._secrets, {"api_keys": credentials})
        if self._secrets.get(_SECRET_CREDENTIALS_V2) is None:
            self._secrets.get_or_create(_SECRET_CREDENTIALS_V2, lambda: credential_blob)
        else:
            self._secrets.rotate(_SECRET_CREDENTIALS_V2, credential_blob)

        payload = {
            "version": 2,
            "enabled": enabled,
            "providers": [
                {
                    "id": item.id,
                    "provider": item.provider,
                    "display_name": item.display_name,
                    "enabled": item.enabled,
                    "base_url": item.base_url,
                    "image_enabled": item.image_enabled,
                    "video_enabled": item.video_enabled,
                    "three_d_enabled": item.three_d_enabled,
                    "image_model": item.image_model,
                    "video_model": item.video_model,
                    "three_d_model": item.three_d_model,
                }
                for item in normalized
            ],
            "default_image_provider": image_route,
            "default_video_provider": video_route,
            "default_three_d_provider": three_d_route,
        }
        self._settings.set(
            _KEY_CONFIG,
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        )
        return self.load()

    @staticmethod
    def _validate_route(
        *,
        kind: MediaTestKind,
        route: str | None,
        enabled: bool,
        providers: list[MediaProviderUpdate],
        by_id: dict[str, MediaProviderUpdate],
        credentials: dict[str, str],
    ) -> None:
        enabled_attr = _kind_enabled_attr(kind)
        capable = [item for item in providers if item.enabled and getattr(item, enabled_attr)]
        if enabled and capable and route is None:
            raise _bad_args(f"{_kind_route_field(kind)} is required")
        if route is None:
            return
        target = by_id.get(route)
        if target is None:
            raise _bad_args(f"default {kind} provider {route!r} does not exist")
        if not target.enabled or not getattr(target, enabled_attr):
            raise _bad_args(f"provider {route!r} does not enable {kind} generation")
        if enabled and not credentials.get(route):
            raise _bad_args(f"API key is required for provider {route!r}")

    def _credentials(self) -> dict[str, str]:
        blob = self._secrets.get(_SECRET_CREDENTIALS_V2)
        if blob is not None:
            raw = decrypt_credentials(self._secrets, blob).get("api_keys")
            if isinstance(raw, dict):
                return {str(key): str(value) for key, value in raw.items() if str(value).strip()}
            return {}

        legacy = self._secrets.get(_SECRET_CREDENTIALS)
        if legacy is None:
            return {}
        value = decrypt_credentials(self._secrets, legacy).get("api_key")
        return {DEFAULT_PROVIDER_ID: str(value)} if value else {}

    def api_key(self, provider_id: str) -> str | None:
        return self._credentials().get(provider_id)

    async def test_connection(
        self,
        item: MediaProviderUpdate,
    ) -> dict[str, object]:
        normalized = _normalized_update(item)
        _validate_provider(normalized)
        key = normalized.api_key or self.api_key(normalized.id)
        if not key:
            raise _bad_args(f"API key is required for provider {normalized.id!r}")
        return await verify_media_credentials(
            normalized.provider,
            key,
            base_url=normalized.base_url,
        )

    async def fetch_models(
        self,
        item: MediaProviderUpdate,
    ) -> dict[str, object]:
        normalized = _normalized_update(item)
        _validate_provider(normalized)
        key = normalized.api_key or self.api_key(normalized.id)
        if not key:
            raise _bad_args(f"API key is required for provider {normalized.id!r}")
        return await fetch_media_provider_models(
            normalized.provider,
            key,
            base_url=normalized.base_url,
        )

    async def test_model(
        self,
        item: MediaProviderUpdate,
        *,
        kind: MediaTestKind,
    ) -> dict[str, object]:
        normalized = _normalized_update(item)
        _validate_provider(normalized)
        if not getattr(normalized, _kind_enabled_attr(kind)):
            raise _bad_args(f"provider {normalized.id!r} does not enable {kind}")
        key = normalized.api_key or self.api_key(normalized.id)
        if not key:
            raise _bad_args(f"API key is required for provider {normalized.id!r}")
        return await verify_media_model(normalized, key, kind=kind)

    def harness_config(self) -> MediaGenerationConfig | None:
        """Build the runtime-only harness config, including decrypted keys."""
        view = self.load()
        if not view.configured:
            return None

        from octop_harness import (  # noqa: PLC0415
            MediaGenerationConfig,
            MediaProviderConfig,
        )

        media_mod = importlib.import_module("octop_harness.media")
        supported_providers = set(getattr(media_mod, "BUILTIN_MEDIA_PROVIDERS", ()))

        credentials = self._credentials()
        providers = [
            _construct_dataclass_compat(
                MediaProviderConfig,
                id=item.id,
                provider=item.provider,
                api_key=credentials[item.id],
                base_url=item.base_url,
                image_model=item.image_model,
                video_model=item.video_model,
                three_d_model=item.three_d_model,
                enabled=item.enabled,
                image_enabled=item.image_enabled,
                video_enabled=item.video_enabled,
                three_d_enabled=item.three_d_enabled,
            )
            for item in view.providers
            if item.enabled
            and credentials.get(item.id)
            and (not supported_providers or item.provider in supported_providers)
        ]
        if not providers:
            return None
        provider_ids = {item.id for item in providers}
        config: MediaGenerationConfig = _construct_dataclass_compat(
            MediaGenerationConfig,
            providers=providers,
            default_image_provider=(
                view.default_image_provider if view.default_image_provider in provider_ids else None
            ),
            default_video_provider=(
                view.default_video_provider if view.default_video_provider in provider_ids else None
            ),
            default_three_d_provider=(
                view.default_three_d_provider
                if view.default_three_d_provider in provider_ids
                else None
            ),
        )
        return config


def _optional_string(value: object) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


__all__ = [
    "DEFAULT_ARK_BASE_URL",
    "DEFAULT_IMAGE_MODEL",
    "DEFAULT_PROVIDER_ID",
    "DEFAULT_VIDEO_MODEL",
    "MEDIA_PROVIDER_PRESETS",
    "MediaGenerationSettings",
    "MediaGenerationSettingsStore",
    "MediaProviderName",
    "MediaProviderPreset",
    "MediaProviderSettings",
    "MediaProviderUpdate",
    "fetch_media_provider_models",
    "verify_media_credentials",
    "verify_media_model",
]
