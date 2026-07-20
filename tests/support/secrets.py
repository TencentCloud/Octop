"""Helpers for live tests that need real credentials.

The repo-root ``.env`` is loaded by ``tests/live/conftest.py`` via python-dotenv,
so these helpers read from ``os.environ`` directly — the same code path used both
locally (``.env``) and in CI (GitHub Secrets mapped to env vars).

Missing credentials should never make CI red: call :func:`require_env` inside a
test and it will ``pytest.skip`` gracefully.
"""

from __future__ import annotations

import os

import pytest


def optional_env(name: str, default: str | None = None) -> str | None:
    """Return the env var value, or ``default`` when unset/empty."""
    value = os.environ.get(name, "")
    return value if value else default


def require_env(name: str) -> str:
    """Return the env var value, or skip the test when missing.

    Use inside a test (or a fixture) so that absent secrets cause a skip
    rather than a failure. This keeps CI green when credentials are not
    configured while still running the real integration when they are.
    """
    value = os.environ.get(name, "").strip()
    if not value:
        pytest.skip(f"set {name} to run this live test")
    return value
