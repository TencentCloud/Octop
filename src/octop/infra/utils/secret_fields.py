"""Blank-means-keep handling for credentials on config APIs.

Responses omit stored secrets. A probe or update that leaves the field blank
reuses the stored value and does not echo it.
"""

from __future__ import annotations

import json
from collections.abc import Collection, Mapping
from typing import Any

# Exact names used by providers, channels, storage, and bridge-adjacent config.
_SECRET_FIELD_NAMES = frozenset(
    {
        "api_key",
        "app_secret",
        "bot_token",
        "client_secret",
        "encrypt_key",
        "http_proxy_auth",
        "password",
        "secret",
        "secret_key",
        "security_token",
        "sk",
        "token",
    }
)
_SECRET_SUFFIXES = ("_api_key", "_password", "_secret", "_token")


def is_secret_field(name: str, *, extra_keys: Collection[str] = ()) -> bool:
    """True when ``name`` holds a credential rather than an identifier."""
    key = name.strip().lower()
    if not key:
        return False
    if key in _SECRET_FIELD_NAMES or key in {item.lower() for item in extra_keys}:
        return True
    return key.endswith(_SECRET_SUFFIXES)


def blank_secret(value: object) -> bool:
    """True when the client did not supply a new secret.

    Empty strings and the mask we previously returned (a short prefix plus
    stars) both count as "leave the stored value alone".
    """
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text:
        return True
    if set(text) <= {"*", "•"}:
        return True
    if "****" in text:
        head = text.split("*", 1)[0]
        tail = text[len(head) :]
        if head.isalnum() and len(head) <= 4 and set(tail) <= {"*"}:
            return True
    return False


def redact_mapping(
    data: Mapping[str, Any],
    *,
    extra_keys: Collection[str] = (),
) -> tuple[dict[str, Any], list[str]]:
    """Drop secret values. The second item lists keys that had a stored secret."""
    kept: dict[str, Any] = {}
    present: list[str] = []
    for key, value in data.items():
        name = str(key)
        if not is_secret_field(name, extra_keys=extra_keys):
            kept[name] = value
            continue
        if not blank_secret(value) and value not in ("", None):
            present.append(name)
    return kept, present


def merge_blank_secrets(
    submitted: Mapping[str, Any],
    stored: Mapping[str, Any],
    *,
    extra_keys: Collection[str] = (),
) -> dict[str, Any]:
    """Fill blank secret fields from ``stored``. Newly typed secrets win."""
    merged = dict(submitted)
    for key, stored_value in stored.items():
        name = str(key)
        if not is_secret_field(name, extra_keys=extra_keys):
            continue
        incoming = merged.get(name)
        if name not in merged or blank_secret(incoming):
            if not blank_secret(stored_value) and stored_value not in ("", None):
                merged[name] = stored_value
            else:
                merged.pop(name, None)
    for key in list(merged):
        if is_secret_field(str(key), extra_keys=extra_keys) and blank_secret(merged[key]):
            merged.pop(key, None)
    return merged


def redact_config_json(raw: str | None) -> tuple[str | None, list[str]]:
    """Return config JSON with secret keys removed, plus the removed names."""
    if raw is None or not raw.strip():
        return raw, []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return raw, []
    if not isinstance(parsed, dict):
        return raw, []
    redacted, present = redact_mapping(parsed)
    return json.dumps(redacted, ensure_ascii=False), present


def merge_config_json(submitted: str | None, stored: str | None) -> str | None:
    """Keep stored secrets when the submitted JSON leaves those keys blank."""
    if submitted is None:
        return None
    try:
        incoming = json.loads(submitted) if submitted.strip() else {}
    except json.JSONDecodeError:
        return submitted
    if not isinstance(incoming, dict):
        return submitted
    try:
        base = json.loads(stored) if stored and stored.strip() else {}
    except json.JSONDecodeError:
        base = {}
    if not isinstance(base, dict):
        base = {}
    return json.dumps(merge_blank_secrets(incoming, base), ensure_ascii=False)


def coalesce_secret(typed: str | None, stored: str | None) -> str | None:
    """Prefer a newly typed secret, otherwise the stored one.

    ``""`` means the client sent a blank value and nothing is stored (clear).
    ``None`` means the field was omitted and nothing is stored (keep).
    """
    if isinstance(typed, str) and typed.strip() and not blank_secret(typed):
        return typed.strip()
    saved = stored.strip() if isinstance(stored, str) else ""
    if saved and not blank_secret(saved):
        return saved
    if isinstance(typed, str):
        return ""
    return None
