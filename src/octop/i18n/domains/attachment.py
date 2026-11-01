"""``attachment.*`` — inbound path hints and empty-turn placeholders."""

from __future__ import annotations

from octop.i18n.loader import tr
from octop.infra.utils.locale import Locale

__all__ = [
    "attachment_empty_image",
    "attachment_empty_message",
    "attachment_extracted_body",
    "attachment_image_unavailable",
    "attachment_path_hint",
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


def attachment_extracted_body(
    *,
    filename: str,
    body: str,
    locale: str | Locale = "en",
) -> str:
    """Inline document text extracted for the model (kept separate from path hints)."""
    header = tr("attachment.extracted_header", locale, filename=filename)
    return f"{header}\n{body.strip()}"


def attachment_empty_message(locale: str | Locale = "en") -> str:
    return tr("attachment.empty_message", locale)


def attachment_empty_image(locale: str | Locale = "en") -> str:
    return tr("attachment.empty_image", locale)


def attachment_image_unavailable(locale: str | Locale = "en") -> str:
    return tr("attachment.image_unavailable", locale)
