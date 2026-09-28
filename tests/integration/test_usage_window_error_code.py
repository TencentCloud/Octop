"""A rejected ``window`` is the caller's mistake and must not be reported as a server fault.

``docs/api.md`` documents ``INTERNAL_ERROR`` as ``500 — Unhandled exception (logged with
traceback)``, and ``api/app.py`` only logs an ``OctopError`` when ``status >= 500``.
So a 400 that carries this code tells the client the server broke, replaces the real
reason with the localized "Internal server error." string, and leaves nothing behind in
``~/.octop/logs`` to prove it.
"""

from __future__ import annotations

from typing import Any

import pytest

# Window strings ``resolve_usage_window()`` rejects because of what the caller sent:
# unpadded fields, a day that is out of its month, a month 13, an inverted range.
BAD_WINDOWS = [
    "day:2026-9-7",
    "day:2026-02-30",
    "month:2026-13",
    "range:2026-03-01:2026-02-01",
]


@pytest.mark.parametrize("window", BAD_WINDOWS)
async def test_summary_reports_bad_window_as_client_error(env_usage: Any, window: str) -> None:
    c, _srv, _admin_auth, alice_auth, _ctx = env_usage
    r = await c.get(f"/api/usage/summary?window={window}", headers=alice_auth)
    assert r.status_code == 400
    err = r.json()["error"]
    assert err["code"] == "SLASH_BAD_ARGS"
    assert err["details"] == {"window": window}


@pytest.mark.parametrize("window", BAD_WINDOWS)
async def test_admin_summary_reports_bad_window_as_client_error(
    env_usage: Any, window: str
) -> None:
    c, _srv, admin_auth, _alice_auth, _ctx = env_usage
    r = await c.get(f"/api/admin/usage/summary?window={window}", headers=admin_auth)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "SLASH_BAD_ARGS"


async def test_export_reports_bad_window_as_client_error(env_usage: Any) -> None:
    c, _srv, _admin_auth, alice_auth, _ctx = env_usage
    r = await c.get("/api/usage/export.xlsx?window=day:2026-02-30", headers=alice_auth)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "SLASH_BAD_ARGS"


async def test_valid_windows_still_answer(env_usage: Any) -> None:
    """Guard against over-rejection: the documented aliases keep working."""
    c, _srv, _admin_auth, alice_auth, _ctx = env_usage
    for window in (
        "today",
        "last_7d",
        "day:2026-02-28",
        "month:2026-02",
        "range:2026-02-01:2026-02-28",
    ):
        r = await c.get(f"/api/usage/summary?window={window}", headers=alice_auth)
        assert r.status_code == 200, window
        assert r.json()["window"] == window
