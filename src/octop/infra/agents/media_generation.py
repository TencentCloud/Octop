"""Instance-wide media-generation settings for harness agents."""

from __future__ import annotations

import json
import re
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
    from harness_agent import MediaGenerationConfig

MediaProviderName = Literal["volcengine", "dashscope", "minimax"]
MediaTestKind = Literal["image", "video"]

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

    @property
    def default_image_model(self) -> str:
        return self.image_models[0]

    @property
    def default_video_model(self) -> str:
        return self.video_models[0]


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

    @property
    def configured(self) -> bool:
        return bool(
            self.enabled and self.api_key_set and (self.image_enabled or self.video_enabled)
        )


@dataclass(frozen=True)
class MediaGenerationSettings:
    """Complete admin-visible media configuration."""

    enabled: bool
    providers: tuple[MediaProviderSettings, ...]
    default_image_provider: str | None
    default_video_provider: str | None

    def provider_by_id(self, provider_id: str | None) -> MediaProviderSettings | None:
        if provider_id is None:
            return None
        return next((item for item in self.providers if item.id == provider_id), None)

    def has_configured_route(self, kind: MediaTestKind) -> bool:
        route = self.default_image_provider if kind == "image" else self.default_video_provider
        provider = self.provider_by_id(route)
        return bool(provider and provider.configured and getattr(provider, f"{kind}_enabled"))

    @property
    def configured(self) -> bool:
        return bool(
            self.enabled
            and (self.has_configured_route("image") or self.has_configured_route("video"))
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
    if not item.display_name:
        raise _bad_args(f"display_name is required for provider {item.id}")
    parsed = urlsplit(item.base_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise _bad_args(f"provider {item.id} base_url must be an HTTPS URL")
    if item.enabled and not (item.image_enabled or item.video_enabled):
        raise _bad_args(f"provider {item.id} must enable image or video generation")
    if item.enabled and item.image_enabled and not item.image_model:
        raise _bad_args(f"image_model is required for provider {item.id}")
    if item.enabled and item.video_enabled and not item.video_model:
        raise _bad_args(f"video_model is required for provider {item.id}")


def _probe_url(provider: MediaProviderName, base_url: str) -> str:
    base = base_url.rstrip("/")
    if provider == "volcengine":
        parsed = urlsplit(base)
        return urlunsplit((parsed.scheme, parsed.netloc, "/ping", "", ""))
    if provider == "dashscope":
        return f"{base}/models?page_no=1&page_size=1"
    return f"{base}/models" if base.endswith("/v1") else f"{base}/v1/models"


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
    return {"ok": True}


async def verify_media_model(
    item: MediaProviderUpdate,
    api_key: str,
    *,
    kind: MediaTestKind,
) -> dict[str, object]:
    """Submit one provider-neutral model probe through the harness adapter."""
    from harness_agent import MediaProviderConfig  # noqa: PLC0415
    from harness_agent.media import (  # noqa: PLC0415
        ImageGenerationRequest,
        MediaGenerationError,
        VideoGenerationRequest,
        create_media_provider,
    )

    config = MediaProviderConfig(
        id=item.id,
        provider=item.provider,
        api_key=api_key,
        base_url=item.base_url,
        image_model=item.image_model,
        video_model=item.video_model,
        image_enabled=item.image_enabled,
        video_enabled=item.video_enabled,
    )
    provider = create_media_provider(config)
    try:
        if kind == "image":
            submission = await provider.submit_image(
                ImageGenerationRequest(
                    prompt="A plain blue circle centered on a white background.",
                    count=1,
                    watermark=False,
                )
            )
        else:
            submission = await provider.submit_video(
                VideoGenerationRequest(
                    prompt="A static blue circle on a white background.",
                    duration=5,
                    aspect_ratio="16:9",
                    resolution="480p",
                    generate_audio=False,
                    watermark=False,
                )
            )
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
                    )
                )
        return MediaGenerationSettings(
            enabled=bool(payload.get("enabled", False)),
            providers=tuple(providers),
            default_image_provider=_optional_string(payload.get("default_image_provider")),
            default_video_provider=_optional_string(payload.get("default_video_provider")),
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
        )
        return MediaGenerationSettings(
            enabled=_stored_bool(self._settings, _KEY_ENABLED, default=False),
            providers=(provider,),
            default_image_provider=DEFAULT_PROVIDER_ID if image_enabled else None,
            default_video_provider=DEFAULT_PROVIDER_ID if video_enabled else None,
        )

    def save(
        self,
        *,
        enabled: bool,
        providers: list[MediaProviderUpdate],
        default_image_provider: str | None,
        default_video_provider: str | None,
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
                    "image_model": item.image_model,
                    "video_model": item.video_model,
                }
                for item in normalized
            ],
            "default_image_provider": image_route,
            "default_video_provider": video_route,
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
        capable = [item for item in providers if item.enabled and getattr(item, f"{kind}_enabled")]
        if enabled and capable and route is None:
            raise _bad_args(f"default_{kind}_provider is required")
        if route is None:
            return
        target = by_id.get(route)
        if target is None:
            raise _bad_args(f"default {kind} provider {route!r} does not exist")
        if not target.enabled or not getattr(target, f"{kind}_enabled"):
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

    async def test_model(
        self,
        item: MediaProviderUpdate,
        *,
        kind: MediaTestKind,
    ) -> dict[str, object]:
        normalized = _normalized_update(item)
        _validate_provider(normalized)
        if not getattr(normalized, f"{kind}_enabled"):
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

        from harness_agent import (  # noqa: PLC0415
            MediaGenerationConfig,
            MediaProviderConfig,
        )

        credentials = self._credentials()
        providers = [
            MediaProviderConfig(
                id=item.id,
                provider=item.provider,
                api_key=credentials[item.id],
                base_url=item.base_url,
                image_model=item.image_model,
                video_model=item.video_model,
                enabled=item.enabled,
                image_enabled=item.image_enabled,
                video_enabled=item.video_enabled,
            )
            for item in view.providers
            if item.enabled and credentials.get(item.id)
        ]
        if not providers:
            return None
        provider_ids = {item.id for item in providers}
        return MediaGenerationConfig(
            providers=providers,
            default_image_provider=(
                view.default_image_provider if view.default_image_provider in provider_ids else None
            ),
            default_video_provider=(
                view.default_video_provider if view.default_video_provider in provider_ids else None
            ),
        )


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
    "verify_media_credentials",
    "verify_media_model",
]
