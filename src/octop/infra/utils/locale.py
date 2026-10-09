"""Shared locale normalization for API, slash commands, and dashboard."""

from __future__ import annotations

from typing import Literal

Locale = Literal["zh", "en"]

DEFAULT_LOCALE: Locale = "zh"
SUPPORTED_LOCALES: tuple[Locale, ...] = ("zh", "en")


def normalize_locale(raw: str | None) -> Locale:
    if not raw:
        return DEFAULT_LOCALE
    lower = raw.lower().replace("_", "-")
    if lower.startswith("zh"):
        return "zh"
    return "en"


UiLocale = Literal["zh", "en", "ja"]


def normalize_ui_locale(raw: str | None) -> UiLocale:
    """Dashboard UI locale. Like ``normalize_locale`` but keeps ``ja``.

    Server-generated text (errors, tool labels, prompts) only ships zh/en, so
    backend code keeps calling ``normalize_locale`` which maps ``ja`` to ``en``.
    """
    if raw and raw.lower().startswith("ja"):
        return "ja"
    return normalize_locale(raw)


def resolve_locale(
    *,
    user_locale: str | None = None,
    explicit: str | None = None,
    channel_type: str = "",
    metadata: dict[str, object] | None = None,
) -> Locale:
    """Pick locale: stored user preference wins, then explicit override, then channel hints."""
    if user_locale:
        return normalize_locale(user_locale)
    if explicit:
        return normalize_locale(explicit)
    if metadata:
        for key in ("locale", "language", "lang"):
            if metadata.get(key):
                return normalize_locale(str(metadata[key]))
    im_zh = {"feishu", "wecom", "weixin", "dingtalk", "qq", "xiaoyi", "yuanbao"}
    if channel_type in im_zh:
        return "zh"
    if channel_type == "telegram":
        return "en"
    return DEFAULT_LOCALE


def locale_from_user_row(row: object | None) -> Locale:
    if row is None:
        return DEFAULT_LOCALE
    raw = getattr(row, "locale", None)
    return normalize_locale(str(raw) if raw is not None else None)


def resolve_user_locale(
    *,
    user_repo: object | None = None,
    user_id: int = 0,
    channel_type: str = "",
    metadata: dict[str, object] | None = None,
) -> Locale:
    """Resolve locale from stored user preference, channel hints, and metadata."""
    user_loc: str | None = None
    if user_repo is not None and user_id > 0:
        row = getattr(user_repo, "get", lambda _id: None)(user_id)
        if row is not None:
            raw = getattr(row, "locale", None)
            if raw is not None:
                user_loc = str(raw)
    return resolve_locale(
        user_locale=user_loc,
        channel_type=channel_type,
        metadata=metadata,
    )


def resolve_request_locale(request: object) -> Locale:
    """Pick locale from HTTP ``Accept-Language`` (first tag), else default."""
    headers = getattr(request, "headers", None)
    if headers is not None:
        raw = headers.get("accept-language") or headers.get("Accept-Language")
        if raw:
            first = str(raw).split(",")[0].strip().split(";")[0]
            return normalize_locale(first)
    return DEFAULT_LOCALE
