"""Validation for provider names.

A provider name is used as the first segment of a model ref
(``{provider_name}/{model_id}``), which is parsed with ``str.partition("/")``
(see :mod:`octop.infra.agents.providers.store`). A name containing ``/`` would
break that split — the ref then resolves to a nonexistent provider and every
model lookup fails (e.g. setting a preferred model returns 400).
"""

from __future__ import annotations

from octop.infra.errors import ErrorCode, OctopError


def validate_provider_name(name: str) -> str:
    """Return the stripped provider *name*, or raise when it is unusable.

    Names must be non-empty and must not contain ``/`` (the model-ref
    separator).
    """
    cleaned = (name or "").strip()
    if not cleaned:
        raise OctopError(ErrorCode.PROVIDER_NAME_INVALID, "provider name cannot be empty")
    if "/" in cleaned:
        raise OctopError(
            ErrorCode.PROVIDER_NAME_INVALID,
            "provider name cannot contain '/' (it prefixes model refs as '<name>/<model>')",
        )
    return cleaned
