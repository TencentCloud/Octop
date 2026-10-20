"""Shared Bearer-authenticated JSON transport for media providers."""

from __future__ import annotations

import contextlib
from collections.abc import Mapping
from typing import Any, cast
from urllib.parse import urlsplit

import httpx

from octop_harness.media.base import BaseMediaProvider
from octop_harness.media.errors import MediaGenerationError
from octop_harness.media.models import GeneratedMedia, RemoteArtifact


class BearerJsonMediaProvider(BaseMediaProvider):
    """Common HTTP behavior for the built-in domestic media providers."""

    async def _request_json(
        self,
        client: httpx.AsyncClient,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        provider_task_id: str | None = None,
    ) -> dict[str, Any]:
        request_headers = self._auth_headers()
        if headers:
            request_headers.update(headers)
        try:
            response = await client.request(
                method,
                f"{self._config.base_url.rstrip('/')}{path}",
                headers=request_headers,
                json=json,
            )
        except httpx.TimeoutException as exc:
            raise MediaGenerationError(
                "The media provider request timed out.",
                code="provider_timeout",
                retryable=True,
                safe_to_resubmit=False,
                remediation="retry_later",
                model_instruction=(
                    "Do not retry this tool call manually because the provider may have accepted it. "
                    "Tell the user the request timed out."
                ),
                provider_task_id=provider_task_id,
            ) from exc
        except httpx.RequestError as exc:
            raise MediaGenerationError(
                "The media provider could not be reached.",
                code="provider_unavailable",
                retryable=True,
                safe_to_resubmit=False,
                remediation="retry_later",
                model_instruction=(
                    "Do not retry this tool call manually. Tell the user the provider is temporarily unavailable."
                ),
                provider_task_id=provider_task_id,
            ) from exc
        if response.is_error:
            raise response_error(response, provider_task_id=provider_task_id)
        try:
            payload = response.json()
        except ValueError as exc:
            raise MediaGenerationError(
                "The media provider returned invalid JSON.",
                code="provider_response_invalid",
            ) from exc
        if not isinstance(payload, dict):
            raise MediaGenerationError("The media provider returned an unexpected response")
        return cast(dict[str, Any], payload)

    def _auth_headers(self) -> dict[str, str]:
        try:
            api_key = self._config.resolve_api_key()
        except ValueError as exc:
            raise MediaGenerationError(
                "Media generation credentials are not configured.",
                code="credential_missing",
                category="configuration",
                remediation="configure_credentials",
                model_instruction="Do not retry. Tell the user to configure media-generation credentials.",
            ) from exc
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    async def _load_artifact(
        self,
        client: httpx.AsyncClient,
        artifact: RemoteArtifact,
    ) -> GeneratedMedia:
        if artifact.data is not None:
            data = artifact.data
        else:
            assert artifact.url is not None
            data = await self._download(client, artifact.url)
        media_type, extension = detect_media(
            data,
            fallback_type=artifact.media_type or "application/octet-stream",
            fallback_extension=artifact.extension or "bin",
        )
        return GeneratedMedia(data=data, media_type=media_type, extension=extension)

    @staticmethod
    async def _download(client: httpx.AsyncClient, url: str) -> bytes:
        if urlsplit(url).scheme not in {"http", "https"}:
            raise MediaGenerationError("Media provider returned an unsupported download URL")
        try:
            response = await client.get(url, follow_redirects=True)
        except httpx.TimeoutException as exc:
            raise MediaGenerationError(
                "Generated media download timed out.",
                code="provider_timeout",
                retryable=True,
                safe_to_resubmit=False,
                remediation="retry_download",
                model_instruction="Do not regenerate the media. Tell the user the result download timed out.",
            ) from exc
        except httpx.RequestError as exc:
            raise MediaGenerationError(
                "Generated media could not be downloaded.",
                code="provider_unavailable",
                retryable=True,
                safe_to_resubmit=False,
                remediation="retry_download",
                model_instruction=(
                    "Do not regenerate the media. Tell the user the result download is temporarily unavailable."
                ),
            ) from exc
        if response.is_error:
            raise MediaGenerationError(
                f"Generated media download failed with HTTP {response.status_code}.",
                code="download_failed",
                retryable=response.status_code >= 500,
                safe_to_resubmit=False,
                remediation="retry_download",
                model_instruction="Do not regenerate the media. Retry downloading the existing result.",
                http_status=response.status_code,
            )
        if not response.content:
            raise MediaGenerationError(
                "Generated media download returned an empty file.",
                code="download_failed",
                safe_to_resubmit=False,
                remediation="retry_download",
                model_instruction="Do not regenerate the media. The provider returned an empty file.",
            )
        return response.content


def provider_payload_error(
    value: object,
    *,
    fallback: str,
    provider_task_id: str | None = None,
) -> MediaGenerationError:
    """Convert a provider-native error object into the stable error taxonomy."""
    message = provider_error_message(value, fallback=fallback)
    provider_code: str | None = None
    if isinstance(value, Mapping):
        raw_code = value.get("code") or value.get("type") or value.get("status_code")
        if raw_code is not None:
            provider_code = str(raw_code)
    return classified_provider_error(
        message,
        provider_code=provider_code,
        provider_task_id=provider_task_id,
    )


def provider_error_message(value: object, *, fallback: str) -> str:
    if isinstance(value, Mapping):
        code = value.get("code") or value.get("type") or value.get("status_code")
        message = value.get("message") or value.get("status_msg")
        parts = [str(item) for item in (code, message) if item not in (None, "")]
        if parts:
            return ": ".join(parts)
    if isinstance(value, str) and value:
        return value
    return fallback


def classified_provider_error(  # noqa: PLR0911 - explicit categories keep remediation auditable
    message: str,
    *,
    provider_code: str | None = None,
    provider_task_id: str | None = None,
    http_status: int | None = None,
    retry_after_seconds: float | None = None,
) -> MediaGenerationError:
    """Classify common HTTP and vendor error shapes without leaking secrets."""
    haystack = f"{provider_code or ''} {message}".lower().replace("_", " ")
    if http_status == 401 or any(
        token in haystack
        for token in ("invalid api key", "invalidapikey", "unauthorized", "authorized error", "1004", "2049")
    ):
        return MediaGenerationError(
            "The media provider rejected the configured credentials.",
            code="credential_invalid",
            category="authentication",
            remediation="configure_credentials",
            model_instruction="Do not retry. Tell the user to check or replace the provider API key.",
            provider_code=provider_code,
            provider_task_id=provider_task_id,
            http_status=http_status,
            retry_after_seconds=retry_after_seconds,
        )
    if http_status == 422 or any(
        token in haystack
        for token in (
            "unsafe",
            "safety",
            "sensitive",
            "content policy",
            "moderation",
            "datainspectionfailed",
            "ipinfringement",
            "1026",
        )
    ):
        return MediaGenerationError(
            message,
            code="content_rejected",
            category="safety",
            remediation="adjust_prompt",
            model_instruction="Do not switch providers to bypass this rejection. Ask the user to revise the request.",
            provider_code=provider_code,
            provider_task_id=provider_task_id,
            http_status=http_status,
            retry_after_seconds=retry_after_seconds,
        )
    if http_status == 429 or any(token in haystack for token in ("rate limit", "too many requests", "1002")):
        return MediaGenerationError(
            "The media provider is rate limited.",
            code="rate_limited",
            category="rate_limit",
            retryable=True,
            safe_to_resubmit=provider_task_id is None,
            remediation="retry_later",
            model_instruction="Do not retry manually. Tell the user to retry later or use a configured fallback.",
            provider_code=provider_code,
            provider_task_id=provider_task_id,
            http_status=http_status,
            retry_after_seconds=retry_after_seconds,
        )
    if http_status == 402 or any(token in haystack for token in ("insufficient", "balance", "quota", "1008")):
        return MediaGenerationError(
            message,
            code="quota_exhausted",
            category="quota",
            remediation="check_billing",
            model_instruction="Do not retry. Tell the user to check provider quota or billing.",
            provider_code=provider_code,
            provider_task_id=provider_task_id,
            http_status=http_status,
            retry_after_seconds=retry_after_seconds,
        )
    if http_status in {403, 404} or any(
        token in haystack for token in ("model not found", "model access", "not activated", "permission")
    ):
        return MediaGenerationError(
            message,
            code="model_access_required" if http_status == 403 else "model_not_found",
            category="authorization",
            remediation="configure_model",
            model_instruction="Do not retry. Enable the configured model or select another available model.",
            provider_code=provider_code,
            provider_task_id=provider_task_id,
            http_status=http_status,
            retry_after_seconds=retry_after_seconds,
        )
    if http_status is not None and http_status >= 500:
        return MediaGenerationError(
            "The media provider is temporarily unavailable.",
            code="provider_unavailable",
            retryable=True,
            safe_to_resubmit=provider_task_id is None,
            remediation="retry_later",
            model_instruction="Do not retry manually. Tell the user the provider is temporarily unavailable.",
            provider_code=provider_code,
            provider_task_id=provider_task_id,
            http_status=http_status,
            retry_after_seconds=retry_after_seconds,
        )
    return MediaGenerationError(
        message,
        provider_code=provider_code,
        provider_task_id=provider_task_id,
        http_status=http_status,
        retry_after_seconds=retry_after_seconds,
    )


def response_error(
    response: httpx.Response,
    *,
    provider_task_id: str | None,
) -> MediaGenerationError:
    detail = response_error_message(response)
    provider_code: str | None = None
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, Mapping):
        error = payload.get("error")
        raw_code = error.get("code") or error.get("type") if isinstance(error, Mapping) else payload.get("code")
        if raw_code is not None:
            provider_code = str(raw_code)
    retry_after: float | None = None
    raw_retry_after = response.headers.get("retry-after")
    if raw_retry_after:
        with contextlib.suppress(ValueError):
            retry_after = float(raw_retry_after)
    return classified_provider_error(
        detail,
        provider_code=provider_code,
        provider_task_id=provider_task_id,
        http_status=response.status_code,
        retry_after_seconds=retry_after,
    )


def response_error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text[:500] or response.reason_phrase
    if isinstance(payload, Mapping):
        error = payload.get("error")
        if error:
            return provider_error_message(error, fallback=str(error))
        if payload.get("code") or payload.get("message"):
            return provider_error_message(payload, fallback=str(payload))
    return str(payload)[:500]


def detect_media(data: bytes, *, fallback_type: str, fallback_extension: str) -> tuple[str, str]:
    """Detect the small set of media formats supported by built-in tools."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", "jpg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif", "gif"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp", "webp"
    if len(data) >= 12 and data[4:8] == b"ftyp":
        return "video/mp4", "mp4"
    return fallback_type, fallback_extension


__all__ = [
    "BearerJsonMediaProvider",
    "classified_provider_error",
    "detect_media",
    "provider_payload_error",
]
