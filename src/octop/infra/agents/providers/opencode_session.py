"""Session header for OpenCode presets and ``opencode.ai`` hosts.

OpenCode gateways reject chat without ``x-opencode-session``. Runtime injection
is ``ProviderConfig.session_header`` (value = ``thread_id``). This module:

- recognizes bundled ``opencode-*`` presets (id or display name)
- recognizes any provider whose ``base_url`` host is ``opencode.ai`` or a
  subdomain (including custom vendors)
- stamps a throwaway UUID on probe / list-models / embedding (those never
  enter ``HarnessAgent``)
"""

from __future__ import annotations

import uuid
from functools import lru_cache
from typing import Any
from urllib.parse import urlsplit

OPENCODE_SESSION_HEADER = "x-opencode-session"
_OPENCODE_PRESET_PREFIX = "opencode-"
_OPENCODE_HOST = "opencode.ai"


@lru_cache(maxsize=1)
def _opencode_preset_display_names() -> frozenset[str]:
    from octop.infra.agents.providers.presets import load_provider_presets

    return frozenset(
        str(preset.get("name") or "")
        for preset in load_provider_presets()
        if str(preset.get("id") or "").startswith(_OPENCODE_PRESET_PREFIX)
    )


def is_opencode_preset(provider_name: Any) -> bool:
    """True when *provider_name* is a bundled OpenCode preset id or name."""
    name = str(provider_name or "").strip()
    if not name:
        return False
    if name.startswith(_OPENCODE_PRESET_PREFIX):
        return True
    return name in _opencode_preset_display_names()


def is_opencode_base_url(base_url: Any) -> bool:
    """True when *base_url* is hosted on ``opencode.ai`` or a subdomain."""
    if not base_url:
        return False
    try:
        host = (urlsplit(str(base_url)).hostname or "").lower()
    except ValueError:
        return False
    return host == _OPENCODE_HOST or host.endswith("." + _OPENCODE_HOST)


def needs_opencode_session_header(*, provider_name: Any = None, base_url: Any = None) -> bool:
    """True for bundled OpenCode presets or an ``opencode.ai`` base URL."""
    return is_opencode_preset(provider_name) or is_opencode_base_url(base_url)


def session_header_for_provider(provider_name: Any, base_url: Any = None) -> str | None:
    """Return the OpenCode session header name, or ``None`` when it is not needed."""
    if needs_opencode_session_header(provider_name=provider_name, base_url=base_url):
        return OPENCODE_SESSION_HEADER
    return None


def ensure_opencode_session_header(
    provider_name: Any,
    headers: dict[str, str] | None,
    *,
    base_url: Any = None,
) -> dict[str, str]:
    """Add a throwaway ``x-opencode-session`` when the provider or URL needs it.

    Existing values (any casing) always win.
    """
    out = dict(headers) if headers else {}
    if any(key.lower() == OPENCODE_SESSION_HEADER for key in out):
        return out
    if not needs_opencode_session_header(provider_name=provider_name, base_url=base_url):
        return out
    out[OPENCODE_SESSION_HEADER] = uuid.uuid4().hex
    return out


__all__ = [
    "OPENCODE_SESSION_HEADER",
    "ensure_opencode_session_header",
    "is_opencode_base_url",
    "is_opencode_preset",
    "needs_opencode_session_header",
    "session_header_for_provider",
]
