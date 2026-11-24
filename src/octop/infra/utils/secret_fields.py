"""Blank-means-keep handling for credentials on config APIs.

Responses omit stored secrets. A probe or update that leaves the field blank
reuses the stored value and does not echo it.

Declared model fields are secrets only when marked with :class:`Secret`.
Dynamic dicts (channel config, storage ``config_json``, plugin extras) have
no field declaration, so they use :data:`_SECRET_FIELD_NAMES` and
:data:`_SECRET_SUFFIXES`.
"""

from __future__ import annotations

import json
from collections.abc import Collection, Mapping
from typing import Any

from pydantic import BaseModel
from pydantic.fields import FieldInfo

# Exact names used by dynamic config dicts (channels, storage JSON, extras).
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


class Secret:
    """Marks a Pydantic field as a credential.

    Put it in ``Annotated`` on the field. A declared field without this marker
    is not a secret, even when its name would match the dynamic-dict rules.
    """


def is_secret_field(name: str, *, extra_keys: Collection[str] = ()) -> bool:
    """True when a dynamic dict key holds a credential rather than an identifier."""
    key = name.strip().lower()
    if not key:
        return False
    if key in _SECRET_FIELD_NAMES or key in {item.lower() for item in extra_keys}:
        return True
    return key.endswith(_SECRET_SUFFIXES)


def _marked_secret(info: FieldInfo) -> bool:
    return any(isinstance(item, Secret) for item in info.metadata)


def model_secret_names(model: type[BaseModel]) -> frozenset[str]:
    """Names of fields marked with :class:`Secret`."""
    return frozenset(name for name, info in model.model_fields.items() if _marked_secret(info))


def persisted_secret(body: BaseModel, name: str) -> Any:
    """Value to write for a ``Secret`` field.

    ``None`` means the client left it blank or sent the mask, so the stored
    value stays. ``name`` must be marked; an unmarked field raises ``KeyError``.
    """
    info = type(body).model_fields.get(name)
    if info is None or not _marked_secret(info):
        raise KeyError(name)
    value = getattr(body, name)
    if blank_secret(value):
        return None
    return value


def _key_is_secret(
    name: str,
    *,
    extra_keys: Collection[str],
    model: type[BaseModel] | None,
) -> bool:
    if model is not None and name in model.model_fields:
        return _marked_secret(model.model_fields[name])
    return is_secret_field(name, extra_keys=extra_keys)


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
    model: type[BaseModel] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Drop secret values. The second item lists keys that had a stored secret.

    Keys declared on ``model`` are secret only when marked with :class:`Secret`.
    Other keys follow the dynamic-dict name rules.
    """
    kept: dict[str, Any] = {}
    present: list[str] = []
    for key, value in data.items():
        name = str(key)
        if not _key_is_secret(name, extra_keys=extra_keys, model=model):
            kept[name] = value
            continue
        if not blank_secret(value) and value not in ("", None):
            present.append(name)
    return kept, present


def _explicit_clear(value: object) -> bool:
    """True when the client sent the key with an empty value to delete it."""
    return value is None or (isinstance(value, str) and not value.strip())


def merge_blank_secrets(
    submitted: Mapping[str, Any],
    stored: Mapping[str, Any],
    *,
    extra_keys: Collection[str] = (),
    model: type[BaseModel] | None = None,
) -> dict[str, Any]:
    """Fill unmodified secret fields from ``stored``. Newly typed secrets win.

    A secret key the client omitted, or echoed back masked, keeps the stored
    value. Sending the key with ``""`` or ``None`` clears it, so an optional
    credential (e.g. a TOS ``security_token``) can be removed.

    Keys declared on ``model`` are secret only when marked with :class:`Secret`.
    Other keys follow the dynamic-dict name rules.
    """
    merged = dict(submitted)
    for key, stored_value in stored.items():
        name = str(key)
        if not _key_is_secret(name, extra_keys=extra_keys, model=model):
            continue
        if name not in merged:
            if not blank_secret(stored_value) and stored_value not in ("", None):
                merged[name] = stored_value
            continue
        incoming = merged[name]
        if _explicit_clear(incoming):
            merged.pop(name, None)
        elif blank_secret(incoming):
            if not blank_secret(stored_value) and stored_value not in ("", None):
                merged[name] = stored_value
            else:
                merged.pop(name, None)
    for key in list(merged):
        secret = _key_is_secret(str(key), extra_keys=extra_keys, model=model)
        if secret and blank_secret(merged[key]):
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
    """Keep stored secrets the submitted JSON omits; ``""``/``null`` clears one."""
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
