"""Neutral provider HTTP header assembly (OpenCode + Magpie).

Runtime chat session values are not stored here. Harness injects
``ProviderConfig.session_header`` from the current ``thread_id``.
Probe / list-models paths may stamp a throwaway UUID so gateways that
require a session header still accept the request.
"""

from __future__ import annotations

from typing import Any

from octop.infra.agents.providers.magpie import (
    MAGPIE_SESSION_HEADER,
    ensure_magpie_headers,
    extra_dict,
    is_magpie_provider,
)
from octop.infra.agents.providers.opencode_session import (
    ensure_opencode_session_header,
)
from octop.infra.agents.providers.opencode_session import (
    session_header_for_provider as opencode_session_header_for_provider,
)


def session_header_for_provider(
    provider_name: Any,
    base_url: Any = None,
    extra: Any = None,
) -> str | None:
    """Return the dynamic session header name for Magpie or OpenCode, else None."""
    if is_magpie_provider(provider_name=provider_name, base_url=base_url, extra=extra):
        return MAGPIE_SESSION_HEADER
    return opencode_session_header_for_provider(provider_name, base_url)


def assemble_provider_headers(
    provider_name: Any,
    headers: dict[str, str] | None,
    *,
    base_url: Any = None,
    extra: Any = None,
    probe: bool = False,
) -> dict[str, str]:
    """Merge stored headers with Magpie UA / probe session or OpenCode session."""
    blob = extra_dict(extra)
    out = dict(headers) if headers else {}
    if is_magpie_provider(provider_name=provider_name, base_url=base_url, extra=blob):
        return ensure_magpie_headers(out, probe=probe)
    # Runtime configs leave the session value to harness. Probes and model
    # listing still need a throwaway id because they never enter a turn.
    if not probe:
        return out
    return ensure_opencode_session_header(provider_name, out, base_url=base_url)


__all__ = [
    "assemble_provider_headers",
    "session_header_for_provider",
]
