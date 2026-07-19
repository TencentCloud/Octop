"""Built-in OAuth client credentials shipped with Octop (override via env/settings)."""

from __future__ import annotations

import os
from typing import Any

# Octop releases may pre-fill registered OAuth apps here; users need not set env vars.
# Self-hosted deployments can still override via OCTOP_* env vars or settings.
_BUILTIN_CLIENTS: dict[str, tuple[str, str]] = {}


def builtin_client(kind: str) -> tuple[str, str]:
    return _BUILTIN_CLIENTS.get(kind, ("", ""))


def resolve_client(
    kind: str,
    *,
    settings_repo: Any,
    env_id_key: str,
    env_secret_key: str,
    settings_id_key: str,
    settings_secret_key: str,
) -> tuple[str, str]:
    client_id = os.environ.get(env_id_key, "").strip()
    client_secret = os.environ.get(env_secret_key, "").strip()
    if not client_id:
        client_id = (settings_repo.get(settings_id_key) or "").strip()
    if not client_secret:
        client_secret = (settings_repo.get(settings_secret_key) or "").strip()
    if not client_id or not client_secret:
        bid, bsec = builtin_client(kind)
        client_id = client_id or bid
        client_secret = client_secret or bsec
    return client_id, client_secret
