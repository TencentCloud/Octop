"""Instance-wide media-generation settings for harness agents."""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal
from urllib.parse import urlsplit, urlunsplit

import httpx

from octop.infra.connectors.crypto import decrypt_credentials, encrypt_credentials
from octop.infra.db.repos.secrets import SecretRepo
from octop.infra.db.repos.settings import SettingsRepo
from octop.infra.errors import ErrorCode, OctopError

if TYPE_CHECKING:
    from harness_agent import MediaGenerationConfig

DEFAULT_ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_SILICONFLOW_BASE_URL = "https://api.siliconflow.cn/v1"
DEFAULT_OPENAI_COMPAT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_IMAGE_MODEL = "doubao-seedream-5-0-lite-260128"
DEFAULT_VIDEO_MODEL = "doubao-seedance-2-0-mini-260615"
DEFAULT_IMAGE_MODEL_SILICONFLOW = "Qwen/Qwen-Image"
DEFAULT_VIDEO_MODEL_SILICONFLOW = "Wan-AI/Wan2.2-T2V-A14B"
DEFAULT_IMAGE_MODEL_OPENAI_COMPAT = "dall-e-3"

SUPPORTED_MEDIA_PROVIDERS = ("volcengine", "siliconflow", "openai-compatible")


def default_media_base_url(provider: str) -> str:
    if provider == "siliconflow":
        return DEFAULT_SILICONFLOW_BASE_URL
    if provider == "openai-compatible":
        return DEFAULT_OPENAI_COMPAT_BASE_URL
    return DEFAULT_ARK_BASE_URL


MediaTestKind = Literal["image", "video"]

_KEY_ENABLED = "media_generation_enabled"
_KEY_IMAGE_ENABLED = "media_generation_image_enabled"
_KEY_VIDEO_ENABLED = "media_generation_video_enabled"
_KEY_IMAGE_MODEL = "media_generation_image_model"
_KEY_VIDEO_MODEL = "media_generation_video_model"
_KEY_PROVIDER = "media_generation_provider"
_KEY_BASE_URL = "media_generation_base_url"
_SECRET_CREDENTIALS = "media_generation_credentials"


def _stored_bool(settings: SettingsRepo, key: str, *, default: bool) -> bool:
    raw = settings.get(key)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes"}


@dataclass(frozen=True)
class MediaGenerationSettings:
    """Admin-visible settings; the API key value is never exposed."""

    enabled: bool
    image_enabled: bool
    video_enabled: bool
    image_model: str
    video_model: str
    api_key_set: bool
    provider: str = "volcengine"
    base_url: str = DEFAULT_ARK_BASE_URL

    @property
    def configured(self) -> bool:
        return bool(
            self.enabled and self.api_key_set and (self.image_enabled or self.video_enabled)
        )


async def verify_ark_api_key(
    api_key: str,
    *,
    base_url: str = DEFAULT_ARK_BASE_URL,
    client: httpx.AsyncClient | None = None,
) -> dict[str, object]:
    """Verify an Ark inference API key against its non-generation ping endpoint."""
    parsed = urlsplit(base_url)
    ping_url = urlunsplit((parsed.scheme, parsed.netloc, "/ping", "", ""))

    async def _request(http: httpx.AsyncClient) -> httpx.Response:
        return await http.get(
            ping_url,
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
        return {"ok": False, "error": "Ark API key authentication failed"}
    if response.is_error:
        return {"ok": False, "error": f"Ark ping returned HTTP {response.status_code}"}
    return {"ok": True}


async def verify_openai_compatible_api_key(
    api_key: str,
    *,
    base_url: str,
    client: httpx.AsyncClient | None = None,
) -> dict[str, object]:
    """Verify a key against the OpenAI-compatible /models endpoint."""
    try:
        if client is not None:
            response = await client.get(
                f"{base_url.rstrip('/')}/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
        else:
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as http:
                response = await http.get(
                    f"{base_url.rstrip('/')}/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
    except httpx.HTTPError as exc:
        return {"ok": False, "error": str(exc)}
    if response.status_code in {401, 403}:
        return {"ok": False, "error": "provider API key authentication failed"}
    if response.is_error:
        return {"ok": False, "error": f"/models returned HTTP {response.status_code}"}
    return {"ok": True}


async def verify_provider_api_key(
    api_key: str,
    *,
    provider: str,
    base_url: str,
    client: httpx.AsyncClient | None = None,
) -> dict[str, object]:
    """Verify credentials against the selected media provider."""
    if provider == "volcengine":
        return await verify_ark_api_key(api_key, base_url=base_url, client=client)
    return await verify_openai_compatible_api_key(api_key, base_url=base_url, client=client)


async def _verify_openai_compatible_image(
    api_key: str,
    *,
    model: str,
    base_url: str,
    client: httpx.AsyncClient | None = None,
) -> dict[str, object]:
    """Probe OpenAI-dialect image generations; explicit, potentially billable."""

    async def _request(http: httpx.AsyncClient) -> httpx.Response:
        return await http.post(
            f"{base_url.rstrip('/')}/images/generations",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "prompt": "A plain blue circle centered on a white background.",
                "size": "1024x1024",
                "n": 1,
                "response_format": "url",
            },
        )

    try:
        if client is not None:
            response = await _request(client)
        else:
            async with httpx.AsyncClient(timeout=120, follow_redirects=True) as http:
                response = await _request(http)
    except httpx.HTTPError as exc:
        return {"ok": False, "error": str(exc)}
    return _classify_verify_response(response, kind="image", is_siliconflow=False)


async def _verify_siliconflow_image(
    api_key: str,
    *,
    model: str,
    base_url: str,
    client: httpx.AsyncClient | None = None,
) -> dict[str, object]:
    """Probe SiliconFlow-dialect image generations; explicit, potentially billable."""

    async def _request(http: httpx.AsyncClient) -> httpx.Response:
        return await http.post(
            f"{base_url.rstrip('/')}/images/generations",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "prompt": "A plain blue circle centered on a white background.",
                "image_size": "1024x1024",
                "batch_size": 1,
            },
        )

    try:
        if client is not None:
            response = await _request(client)
        else:
            async with httpx.AsyncClient(timeout=120, follow_redirects=True) as http:
                response = await _request(http)
    except httpx.HTTPError as exc:
        return {"ok": False, "error": str(exc)}
    return _classify_verify_response(response, kind="image", is_siliconflow=True)


async def _verify_siliconflow_video(
    api_key: str,
    *,
    model: str,
    base_url: str,
    client: httpx.AsyncClient | None = None,
) -> dict[str, object]:
    """Submit a SiliconFlow video task to verify model access (runs and bills)."""

    async def _request(http: httpx.AsyncClient) -> httpx.Response:
        return await http.post(
            f"{base_url.rstrip('/')}/video/submit",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "prompt": "A static blue circle on a white background.",
                "image_size": "1280x720",
            },
        )

    try:
        if client is not None:
            response = await _request(client)
        else:
            async with httpx.AsyncClient(timeout=60, follow_redirects=True) as http:
                response = await _request(http)
    except httpx.HTTPError as exc:
        return {"ok": False, "error": str(exc)}
    if response.is_error:
        return _classify_verify_response(response, kind="video", is_siliconflow=True)
    try:
        payload = response.json()
    except ValueError:
        return {"ok": False, "error": "SiliconFlow returned invalid JSON"}
    if not isinstance(payload, dict) or not isinstance(payload.get("requestId"), str):
        return {"ok": False, "error": "SiliconFlow video test returned no requestId"}
    return {"ok": True}


def _classify_verify_response(
    response: httpx.Response,
    *,
    kind: str,
    is_siliconflow: bool,
) -> dict[str, object]:
    """Shared error extraction for provider probe responses."""
    provider_name = "SiliconFlow" if is_siliconflow else "OpenAI-compatible"
    if response.is_error:
        try:
            payload = response.json()
        except ValueError:
            payload = None
        detail = ""
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                code = error.get("code")
                message = error.get("message")
                detail = ": ".join(str(value) for value in (code, message) if value)
            elif error:
                detail = str(error)
            if not detail and payload.get("message"):
                detail = str(payload["message"])
        if response.status_code in {401, 403}:
            return {"ok": False, "error": f"provider API key authentication failed ({response.status_code})"}
        if response.status_code == 429 or "rate limit" in detail.lower():
            return {"ok": False, "error": f"{provider_name} rate limited: {detail or response.status_code}"}
        return {"ok": False, "error": detail or f"{provider_name} returned HTTP {response.status_code}"}
    try:
        payload = response.json()
    except ValueError:
        return {"ok": False, "error": f"{provider_name} returned invalid JSON"}
    if not isinstance(payload, dict):
        return {"ok": False, "error": f"{provider_name} returned an unexpected response"}
    rows = payload.get("images" if is_siliconflow else "data")
    if kind == "image" and not isinstance(rows, list):
        return {"ok": False, "error": f"{provider_name} image test returned no output"}
    return {"ok": True}


async def verify_provider_media_model(
    api_key: str,
    *,
    kind: MediaTestKind,
    model: str,
    provider: str,
    base_url: str,
    client: httpx.AsyncClient | None = None,
) -> dict[str, object]:
    """Run an explicit, potentially billable probe against one media model."""
    if provider == "volcengine":
        return await verify_ark_media_model(api_key, kind=kind, model=model, base_url=base_url, client=client)
    if provider == "siliconflow":
        if kind == "image":
            return await _verify_siliconflow_image(api_key, model=model, base_url=base_url, client=client)
        return await _verify_siliconflow_video(api_key, model=model, base_url=base_url, client=client)
    if kind == "image":
        return await _verify_openai_compatible_image(api_key, model=model, base_url=base_url, client=client)
    return {"ok": False, "error": "the openai-compatible provider does not support video generation"}


async def verify_ark_media_model(
    api_key: str,
    *,
    kind: MediaTestKind,
    model: str,
    base_url: str = DEFAULT_ARK_BASE_URL,
    client: httpx.AsyncClient | None = None,
) -> dict[str, object]:
    """Run an explicit, potentially billable probe against one media model."""

    async def _request(http: httpx.AsyncClient) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        if kind == "image":
            return await http.post(
                f"{base_url.rstrip('/')}/images/generations",
                headers=headers,
                json={
                    "model": model,
                    "prompt": "A plain blue circle centered on a white background.",
                    "size": "2K",
                    "response_format": "url",
                    "watermark": False,
                    "sequential_image_generation": "disabled",
                },
            )

        created = await http.post(
            f"{base_url.rstrip('/')}/contents/generations/tasks",
            headers=headers,
            json={
                "model": model,
                "content": [
                    {
                        "type": "text",
                        "text": "A static blue circle on a white background.",
                    }
                ],
                "duration": 4,
                "ratio": "16:9",
                "resolution": "480p",
                "generate_audio": False,
                "watermark": False,
                "output_format": "mp4",
            },
        )
        if created.is_error:
            return created
        try:
            payload = created.json()
        except ValueError:
            return created
        task_id = payload.get("id") if isinstance(payload, dict) else None
        if isinstance(task_id, str) and task_id:
            with suppress(httpx.HTTPError):
                await http.delete(
                    f"{base_url.rstrip('/')}/contents/generations/tasks/{task_id}",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
        return created

    try:
        if client is not None:
            response = await _request(client)
        else:
            async with httpx.AsyncClient(timeout=120, follow_redirects=True) as http:
                response = await _request(http)
    except httpx.HTTPError as exc:
        return {"ok": False, "error": str(exc)}

    if response.is_error:
        try:
            payload = response.json()
        except ValueError:
            payload = response.text or response.reason_phrase
        if isinstance(payload, dict) and payload.get("error"):
            error = payload["error"]
            if isinstance(error, dict):
                code = error.get("code")
                message = error.get("message")
                detail = ": ".join(str(value) for value in (code, message) if value)
                return {"ok": False, "error": detail or str(error)}
        return {"ok": False, "error": str(payload)[:500]}
    try:
        payload = response.json()
    except ValueError:
        return {"ok": False, "error": "Ark returned invalid JSON"}
    if not isinstance(payload, dict):
        return {"ok": False, "error": "Ark returned an unexpected response"}
    error = payload.get("error")
    if isinstance(error, dict) and error:
        code = error.get("code")
        message = error.get("message")
        detail = ": ".join(str(value) for value in (code, message) if value)
        return {"ok": False, "error": detail or str(error)}
    if kind == "image" and not isinstance(payload.get("data"), list):
        return {"ok": False, "error": "Ark image test returned no output"}
    if kind == "video" and not isinstance(payload.get("id"), str):
        return {"ok": False, "error": "Ark video test returned no task ID"}
    return {"ok": True}


class MediaGenerationSettingsStore:
    """Persist public settings and an encrypted Ark credential."""

    def __init__(self, *, settings_repo: SettingsRepo, secret_repo: SecretRepo) -> None:
        self._settings = settings_repo
        self._secrets = secret_repo

    def load(self) -> MediaGenerationSettings:
        provider = (self._settings.get(_KEY_PROVIDER) or "volcengine").strip()
        if provider not in SUPPORTED_MEDIA_PROVIDERS:
            provider = "volcengine"
        base_url = (self._settings.get(_KEY_BASE_URL) or default_media_base_url(provider)).strip()
        return MediaGenerationSettings(
            enabled=_stored_bool(self._settings, _KEY_ENABLED, default=False),
            image_enabled=_stored_bool(self._settings, _KEY_IMAGE_ENABLED, default=True),
            video_enabled=_stored_bool(self._settings, _KEY_VIDEO_ENABLED, default=True),
            image_model=(self._settings.get(_KEY_IMAGE_MODEL) or DEFAULT_IMAGE_MODEL).strip(),
            video_model=(self._settings.get(_KEY_VIDEO_MODEL) or DEFAULT_VIDEO_MODEL).strip(),
            api_key_set=self._secrets.get(_SECRET_CREDENTIALS) is not None,
            provider=provider,
            base_url=base_url,
        )

    def save(
        self,
        *,
        enabled: bool,
        image_enabled: bool,
        video_enabled: bool,
        image_model: str,
        video_model: str,
        api_key: str | None = None,
        provider: str | None = None,
        base_url: str | None = None,
    ) -> MediaGenerationSettings:
        image_model = image_model.strip()
        video_model = video_model.strip()
        provider = (provider or self.load().provider).strip()
        if provider not in SUPPORTED_MEDIA_PROVIDERS:
            raise OctopError(
                ErrorCode.SLASH_BAD_ARGS,
                f"unsupported media generation provider {provider!r}; "
                f"choose from {', '.join(SUPPORTED_MEDIA_PROVIDERS)}",
            )
        base_url = (base_url or default_media_base_url(provider)).strip()
        if not base_url.startswith(("https://", "http://")):
            raise OctopError(ErrorCode.SLASH_BAD_ARGS, "media generation base URL must be an HTTP(S) URL")
        has_stored_key = self._secrets.get(_SECRET_CREDENTIALS) is not None
        if enabled and not (image_enabled or video_enabled):
            raise OctopError(
                ErrorCode.SLASH_BAD_ARGS,
                "image or video generation must be enabled",
            )
        if enabled and image_enabled and not image_model:
            raise OctopError(ErrorCode.SLASH_BAD_ARGS, "image_model is required")
        if enabled and video_enabled and not video_model:
            raise OctopError(ErrorCode.SLASH_BAD_ARGS, "video_model is required")
        if enabled and not (api_key or has_stored_key):
            raise OctopError(ErrorCode.SLASH_BAD_ARGS, "the provider API key is required")

        self._settings.set(_KEY_PROVIDER, provider)
        self._settings.set(_KEY_BASE_URL, base_url)
        self._settings.set(_KEY_ENABLED, "true" if enabled else "false")
        self._settings.set(_KEY_IMAGE_ENABLED, "true" if image_enabled else "false")
        self._settings.set(_KEY_VIDEO_ENABLED, "true" if video_enabled else "false")
        self._settings.set(_KEY_IMAGE_MODEL, image_model)
        self._settings.set(_KEY_VIDEO_MODEL, video_model)
        if api_key:
            blob = encrypt_credentials(self._secrets, {"api_key": api_key})
            if has_stored_key:
                self._secrets.rotate(_SECRET_CREDENTIALS, blob)
            else:
                self._secrets.get_or_create(_SECRET_CREDENTIALS, lambda: blob)
        return self.load()

    def api_key(self) -> str | None:
        blob = self._secrets.get(_SECRET_CREDENTIALS)
        if blob is None:
            return None
        value = decrypt_credentials(self._secrets, blob).get("api_key")
        return str(value) if value else None

    async def test_connection(
        self,
        *,
        api_key: str | None = None,
        provider: str | None = None,
        base_url: str | None = None,
    ) -> dict[str, object]:
        view = self.load()
        provider = (provider or view.provider or "volcengine").strip()
        base_url = (base_url or view.base_url or default_media_base_url(provider)).strip()
        key = (api_key or self.api_key() or "").strip()
        if not key:
            raise OctopError(ErrorCode.SLASH_BAD_ARGS, "provider API key is required")
        return await verify_provider_api_key(key, provider=provider, base_url=base_url)

    async def test_model(
        self,
        *,
        kind: MediaTestKind,
        model: str,
        api_key: str | None = None,
        provider: str | None = None,
        base_url: str | None = None,
    ) -> dict[str, object]:
        """Test that the selected media model accepts a real request."""
        view = self.load()
        provider = (provider or view.provider or "volcengine").strip()
        base_url = (base_url or view.base_url or default_media_base_url(provider)).strip()
        key = (api_key or self.api_key() or "").strip()
        model = model.strip()
        if not key:
            raise OctopError(ErrorCode.SLASH_BAD_ARGS, "provider API key is required")
        if not model:
            raise OctopError(ErrorCode.SLASH_BAD_ARGS, "media model is required")
        return await verify_provider_media_model(
            key,
            kind=kind,
            model=model,
            provider=provider,
            base_url=base_url,
        )

    def harness_config(self) -> MediaGenerationConfig | None:
        """Build the runtime-only harness config, including the decrypted key."""
        view = self.load()
        key = self.api_key()
        if not view.configured or key is None:
            return None

        from harness_agent import MediaGenerationConfig  # noqa: PLC0415

        return MediaGenerationConfig(
            provider=view.provider,
            api_key=key,
            base_url=view.base_url,
            image_model=view.image_model,
            video_model=view.video_model,
            image_enabled=view.image_enabled,
            video_enabled=view.video_enabled,
        )


__all__ = [
    "DEFAULT_ARK_BASE_URL",
    "DEFAULT_IMAGE_MODEL",
    "DEFAULT_VIDEO_MODEL",
    "MediaGenerationSettings",
    "MediaGenerationSettingsStore",
    "verify_ark_api_key",
    "verify_ark_media_model",
]
