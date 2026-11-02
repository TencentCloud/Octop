"""``voice.*`` — probe, realtime and Tencent provider error copy."""

from __future__ import annotations

from octop.i18n.loader import lookup, tr
from octop.infra.utils.locale import Locale, normalize_locale


def tencent_api_language(locale: str | Locale | None) -> str | None:
    """``X-TC-Language`` value for Tencent Cloud common errors, or ``None``."""
    if locale is None:
        return None
    return "zh-CN" if normalize_locale(str(locale)) == "zh" else "en-US"


def voice_not_configured(locale: str | Locale) -> str:
    return tr("voice.probe.not_configured", locale)


def voice_credentials_error(kind: str, locale: str | Locale) -> str:
    if kind == "tencent":
        return tr("voice.probe.tencent_credentials", locale)
    return tr("voice.probe.credentials_missing", locale)


def format_voice_probe_error(exc: BaseException, locale: str | Locale) -> str:
    """Map probe-time exceptions to localized copy; unknown text stays as-is."""
    import httpx

    if isinstance(exc, httpx.HTTPStatusError):
        return tr("voice.probe.http_status", locale, status=exc.response.status_code)
    if isinstance(exc, httpx.HTTPError):
        return tr("voice.probe.network_error", locale, name=type(exc).__name__)
    raw = str(exc).strip() or type(exc).__name__
    code, sep, _message = raw.partition(": ")
    if sep and lookup(f"voice.tencent.{code}", locale) is not None:
        return tr(f"voice.tencent.{code}", locale)
    return raw


#: Realtime ASR error codes worth their own copy; anything else falls back to
#: ``voice.realtime.error_unknown``.
_ASR_ERROR_KEYS = {
    4002: "error_4002",
    4003: "error_4003",
    4004: "error_4004",
    4005: "error_4005",
    4006: "error_4006",
    4007: "error_4007",
    4008: "error_4008",
    4009: "error_4009",
    5000: "error_5000",
    5001: "error_5000",
    5002: "error_5000",
}


def realtime_error_message(tencent_code: int | None, locale: str | Locale) -> str:
    """Localized copy for a realtime ASR failure code (``None`` = unknown)."""
    suffix = _ASR_ERROR_KEYS.get(int(tencent_code or 0), "error_unknown")
    return tr(f"voice.realtime.{suffix}", locale)
