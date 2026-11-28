"""Load nested locale JSON and resolve dot-path keys."""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from importlib import resources
from typing import Any

from octop.infra.utils.locale import Locale, normalize_locale

_FALLBACK_LOCALE: Locale = "en"

logger = logging.getLogger(__name__)


def _resolve_node(table: dict[str, Any], key: str) -> str | None:
    node: Any = table
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node if isinstance(node, str) else None


def _merge_missing(base: dict[str, Any], extra: Any, *, source: str, path: str = "") -> None:
    """Add keys from ``extra`` that ``base`` lacks; built-in strings always win."""
    if not isinstance(extra, dict):
        raise ValueError(f"{source}: i18n node {path or '<root>'!r} must be an object")
    for name, value in extra.items():
        key = f"{path}.{name}" if path else str(name)
        if isinstance(value, dict):
            node = base.setdefault(name, {})
            if not isinstance(node, dict):
                logger.warning("%s: i18n key %r is a built-in string; ignored", source, key)
                continue
            _merge_missing(node, value, source=source, path=key)
        elif isinstance(value, str):
            if name in base:
                logger.warning("%s: i18n key %r already exists; ignored", source, key)
                continue
            base[name] = value
        else:
            raise ValueError(f"{source}: i18n key {key!r} must be a string or an object")


@lru_cache(maxsize=1)
def _load_all() -> dict[Locale, dict[str, Any]]:
    out: dict[Locale, dict[str, Any]] = {}
    for loc in ("en", "zh"):
        raw = resources.files("octop.i18n").joinpath(f"{loc}.json").read_text(encoding="utf-8")
        out[loc] = json.loads(raw)
    from octop.infra.extensions import extension_hooks  # noqa: PLC0415

    for ext_name, bundles in extension_hooks("i18n_bundles"):
        for loc, table in bundles().items():
            if loc in out:
                _merge_missing(out[loc], table, source=f"extension {ext_name!r}")
    return out


def lookup(key: str, locale: str | Locale) -> str | None:
    loc = normalize_locale(str(locale))
    tables = _load_all()
    text = _resolve_node(tables[loc], key)
    if text is not None:
        return text
    if loc != _FALLBACK_LOCALE:
        return _resolve_node(tables[_FALLBACK_LOCALE], key)
    return None


def tr(key: str, locale: str | Locale = "en", **kwargs: object) -> str:
    """Resolve *key* (e.g. ``slash.help.title``) for *locale*, fallback to ``en``."""
    text = lookup(key, locale)
    if text is None:
        raise KeyError(key)
    return text.format(**kwargs) if kwargs else text


def flatten_keys(table: dict[str, Any], prefix: str = "") -> set[str]:
    keys: set[str] = set()
    for name, value in table.items():
        path = f"{prefix}.{name}" if prefix else name
        if isinstance(value, dict):
            keys.update(flatten_keys(value, path))
        elif isinstance(value, str):
            keys.add(path)
    return keys


def all_keys_for_locale(locale: Locale = "en") -> set[str]:
    return flatten_keys(_load_all()[locale])
