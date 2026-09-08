"""OpenCode Go gateway session header injection.

The OpenCode Go gateway (``https://opencode.ai/zen/go``) rejects chat requests
that lack a stable ``x-opencode-session`` header with ``HTTP 400
MissingSessionID``. The header routes each conversation to a consistent
backend and enables prompt caching; the value must stay stable within a
conversation (see https://opencode.ai/docs/go).

Octop cannot assign one session per thread here: harness-agent caches chat
models per ``(provider, model)`` and LangChain ``default_headers`` are static
for the lifetime of the instance. Instead we guarantee every OpenCode Go
request carries a *stable* session id:

- **Chat runtime** (``store.ProviderStore.build_harness_configs``): one
  UUID per provider, generated once and persisted in the provider row's
  ``extra_json.headers`` so it survives restarts.
- **Connectivity probes / model listing** (``probe``): a throwaway UUID per
  invocation, because each probe is its own short-lived conversation.

User-supplied values always win — this helper never overwrites an existing
``x-opencode-session`` header.
"""

from __future__ import annotations

import uuid
from typing import Any
from urllib.parse import urlsplit

OPENCODE_SESSION_HEADER = "x-opencode-session"
_OPENCODE_GO_HOSTS = frozenset({"opencode.ai"})


def is_opencode_go_base_url(base_url: Any) -> bool:
    """True when *base_url* points at the OpenCode Go gateway.

    Matches ``https://opencode.ai/zen/go`` and ``/zen/go/v1`` (the OpenAI
    protocol variant) but not the Zen endpoints (``/zen``, ``/zen/v1``),
    which do not require the session header.
    """
    if not base_url:
        return False
    try:
        parts = urlsplit(str(base_url))
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    if host not in _OPENCODE_GO_HOSTS:
        return False
    path = (parts.path or "").rstrip("/")
    return path == "/zen/go" or path.startswith("/zen/go/")


def ensure_opencode_session_header(
    base_url: Any,
    headers: dict[str, str] | None,
    *,
    session_id: str | None = None,
) -> tuple[dict[str, str], str | None]:
    """Return ``(headers, injected_session_id)`` for an OpenCode Go base URL.

    Injects ``x-opencode-session`` when *base_url* is the Go gateway and the
    header is absent (checked case-insensitively). Existing values — the
    user's own or one persisted by the provider store — always win, so the
    returned ``injected_session_id`` is ``None`` in that case. Non-Go base
    URLs pass through untouched.
    """
    out = dict(headers) if headers else {}
    if any(key.lower() == OPENCODE_SESSION_HEADER for key in out):
        return out, None
    if not is_opencode_go_base_url(base_url):
        return out, None
    injected = session_id or uuid.uuid4().hex
    out[OPENCODE_SESSION_HEADER] = injected
    return out, injected


__all__ = [
    "OPENCODE_SESSION_HEADER",
    "ensure_opencode_session_header",
    "is_opencode_go_base_url",
]
