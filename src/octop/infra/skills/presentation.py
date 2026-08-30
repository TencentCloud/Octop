"""Skill presentation metadata shared by catalogs and HTTP adapters."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

from octop.infra.utils.locale import Locale

# Keep in sync with harness_agent.skills.catalog._summary_dict.
_EXTENSION_NAMESPACES = ("octop", "harness", "lightclaw", "orca", "openclaw")


def _text(value: object) -> str:
    return str(value or "").strip()


def _localized_text(value: object, locale: Locale) -> str:
    if not isinstance(value, Mapping):
        return _text(value)
    for key in (locale, "en", "zh"):
        text = _text(value.get(key))
        if text:
            return text
    return ""


def _valid_icon_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def apply_skill_presentation(
    summary: Mapping[str, Any],
    frontmatter: Mapping[str, Any] | None = None,
    *,
    locale: Locale | None = None,
) -> dict[str, Any]:
    """Overlay optional UI metadata without changing the stable skill slug.

    Without ``locale``, ``name`` / ``description`` stay the frontmatter identity
    used for disable matching and chat skill filters. ``label``, ``summary``,
    and legacy ``display_name`` are copied through so a later localize pass can
    fill UI copy. Compatible namespaces may still contribute emoji / icon_url.
    """
    out = dict(summary)
    metadata = (frontmatter or {}).get("metadata")
    extensions = metadata if isinstance(metadata, Mapping) else {}

    display_name = ""
    for namespace in _EXTENSION_NAMESPACES:
        extension = extensions.get(namespace)
        if not isinstance(extension, Mapping):
            continue
        if namespace == "octop":
            label = extension.get("label")
            short_summary = extension.get("summary")
            if isinstance(label, Mapping):
                out["label"] = dict(label)
            if isinstance(short_summary, Mapping):
                out["summary"] = dict(short_summary)
        if not display_name:
            display_name = _text(extension.get("display_name"))
        emoji = _text(extension.get("emoji"))
        if emoji and not _text(out.get("emoji")):
            out["emoji"] = emoji
        icon_url = _text(extension.get("icon_url"))
        if icon_url and "icon_url" not in out and _valid_icon_url(icon_url):
            out["icon_url"] = icon_url
    if display_name:
        out["display_name"] = display_name
    if locale is not None:
        return localize_skill_summary(out, locale)
    return out


def localize_skill_summary(summary: Mapping[str, Any], locale: Locale) -> dict[str, Any]:
    """Resolve raw localized fields already returned by an upstream catalog."""
    out = dict(summary)
    label = _localized_text(out.get("label"), locale)
    short_summary = _localized_text(out.get("summary"), locale)
    display_name = _text(out.get("display_name"))
    if label or display_name:
        out["name"] = label or display_name
    if short_summary:
        out["description"] = short_summary
    return out


__all__ = ["apply_skill_presentation", "localize_skill_summary"]
