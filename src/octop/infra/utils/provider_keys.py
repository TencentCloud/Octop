"""Explicit environment references for provider API keys."""

from __future__ import annotations

import os
import re

_ENV_REF = re.compile(r"env:([A-Za-z_][A-Za-z0-9_]*)\Z")


def api_key_reference(value: str | None) -> str | None:
    return value if value is not None and _ENV_REF.fullmatch(value) else None


def resolve_api_key(value: str | None) -> str | None:
    if api_key_reference(value):
        assert value is not None
        return os.environ.get(value[4:]) or None
    return value
