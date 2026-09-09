"""Local identity and endpoint resolution for the stdio MCP command."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import jwt

from octop.cli.support.db import open_cli_services
from octop.cli.support.state import default_state_path, load
from octop.infra.utils.paths import PathLayout


def resolve_mcp_username(explicit: str | None) -> str:
    """Resolve an explicit or CLI-pinned user without silently choosing one."""
    username = (explicit or "").strip()
    if username:
        return username
    pinned = (load(default_state_path()).default_user or "").strip()
    if pinned:
        return pinned
    raise ValueError("--user is required (or pin one with `octop config set-user USERNAME`)")


def issue_local_access_token(username: str, *, home: Path | None = None) -> str:
    """Mint a normal short-lived JWT for a local Octop user.

    The local CLI already has access to the Octop data directory. Using a JWT
    makes every management tool pass through the same ownership and permission
    checks as the dashboard instead of writing to the database directly.
    """
    with open_cli_services(home) as services:
        row = services.user_repo.get_by_username(username)
        if row is None:
            raise ValueError(f"user not found: {username}")
        if row.disabled:
            raise ValueError(f"user is disabled: {username}")
        secret = services.secret_repo.get("jwt")
        if secret is None:
            raise ValueError("Octop JWT secret is missing; run `octop init` first")
        now = int(time.time())
        return jwt.encode(
            {
                "sub": str(row.id),
                "uname": row.username,
                "role": row.role,
                "iat": now,
                "exp": now + int(services.config.access_token_ttl_seconds),
            },
            secret,
            algorithm="HS256",
        )


def resolve_mcp_base_url(explicit: str | None, *, home: Path | None = None) -> str:
    """Resolve the live Octop HTTP endpoint for the local MCP adapter."""
    configured = (explicit or os.environ.get("OCTOP_MCP_BASE_URL", "")).strip()
    if configured:
        return configured.rstrip("/")

    paths = PathLayout(home) if home is not None else PathLayout.from_env()
    port = 8088
    if paths.config.exists():
        try:
            raw: Any = json.loads(paths.config.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = {}
        if isinstance(raw, dict):
            configured_port = raw.get("port")
            if isinstance(configured_port, int) and not isinstance(configured_port, bool):
                port = configured_port
    return f"http://127.0.0.1:{port}"
