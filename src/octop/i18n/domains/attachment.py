"""``attachment.*`` — inbound path hints and empty-turn placeholders."""

from __future__ import annotations

from octop.i18n.loader import tr
from octop.infra.utils.locale import Locale

__all__ = [
    "attachment_empty_image",
    "attachment_empty_message",
    "attachment_image_unavailable",
    "attachment_path_hint",
    "attachment_voice_transcript",
]


def attachment_path_hint(
    *,
    filename: str,
    path: str,
    media_type: str,
    size: int | None = None,
    locale: str | Locale = "en",
) -> str:
    """Short workspace path hint for agent tools — never inline file bytes."""
    lines = [
        tr("attachment.header", locale, filename=filename),
        tr("attachment.path", locale, path=path),
        tr("attachment.mime", locale, media_type=media_type),
    ]
    if size is not None and size > 0:
        lines.append(tr("attachment.size", locale, size=size))
    return "\n".join(lines)


def attachment_empty_message(locale: str | Locale = "en") -> str:
    return tr("attachment.empty_message", locale)


def attachment_empty_image(locale: str | Locale = "en") -> str:
    return tr("attachment.empty_image", locale)


def attachment_image_unavailable(locale: str | Locale = "en") -> str:
    return tr("attachment.image_unavailable", locale)


def attachment_voice_transcript(
    text: str,
    *,
    truncated: bool = False,
    minutes: int = 5,
    locale: str | Locale = "en",
) -> str:
    """Speech-to-text transcript of an inbound voice note / audio attachment."""
    if truncated:
        return tr("attachment.voice_transcript_truncated", locale, text=text, minutes=minutes)
    return tr("attachment.voice_transcript", locale, text=text)
