"""``channel.*`` — IM channel status lines (tool hints, probe errors)."""

from __future__ import annotations

from octop.i18n.loader import lookup, tr
from octop.infra.utils.locale import Locale

__all__ = [
    "channel_probe_field_label",
    "channel_probe_incomplete",
    "channel_runtime_reason",
    "channel_tool_hint_end",
    "channel_tool_hint_start",
    "telegram_quote_prompt",
    "telegram_reject_notice",
]


def channel_tool_hint_start(tool_name: str, locale: str | Locale = "en") -> str:
    return tr("channel.tool_hint_start", locale, tool_name=tool_name)


def channel_tool_hint_end(tool_name: str, locale: str | Locale = "en") -> str:
    return tr("channel.tool_hint_end", locale, tool_name=tool_name)


def channel_probe_field_label(field: str, locale: str | Locale = "en") -> str:
    """Human label for a credential field; falls back to the raw field name."""
    label = lookup(f"channel.probe.field.{field}", locale)
    return label if isinstance(label, str) else field


def channel_probe_incomplete(missing: list[str], locale: str | Locale = "en") -> str:
    """Localized 'missing credentials' message from structured field names."""
    sep = "、" if str(locale).startswith("zh") else ", "
    fields = sep.join(channel_probe_field_label(name, locale) for name in missing)
    return tr("channel.probe.incomplete", locale, fields=fields)


def channel_runtime_reason(reason: str, locale: str | Locale = "en") -> str:
    """Localized label for a runtime-status reason code (``disabled``/``error``/…)."""
    label = lookup(f"channel.runtime.{reason}", locale)
    return label if isinstance(label, str) else reason


def telegram_reject_notice(reason: str, locale: str | Locale = "en") -> str:
    """Short notice for a rejected Telegram button; unknown reasons use the default."""
    text = lookup(f"channel.telegram.reject.{reason}", locale)
    return text if isinstance(text, str) else tr("channel.telegram.reject.default", locale)


def telegram_quote_prompt(quote: str, locale: str | Locale = "en") -> str:
    """Prompt prefix that carries the quoted (replied-to) message body."""
    header = tr("channel.telegram.quote.header", locale)
    current = tr("channel.telegram.quote.current", locale)
    return f"{header}\n{quote}\n\n{current}\n"
