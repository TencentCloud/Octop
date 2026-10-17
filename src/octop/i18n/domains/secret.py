"""``secret.*`` — secret-file card tool-result messages (metadata only)."""

from __future__ import annotations

from octop.i18n.loader import tr
from octop.infra.utils.locale import Locale

__all__ = [
    "secret_cancelled_message",
    "secret_filled_message",
]


def secret_filled_message(path: str, locale: str | Locale = "en") -> str:
    """Tool-result text after a successful write; carries the path, never the secret."""
    return tr("secret.filled_message", locale, path=path)


def secret_cancelled_message(locale: str | Locale = "en") -> str:
    """Tool-result text after the user dismissed the card without writing."""
    return tr("secret.cancelled_message", locale)
