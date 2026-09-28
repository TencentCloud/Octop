"""tests/integration/test_memory_rpc_error_code.py - client mistakes in
memory-dashboard list queries must not be reported as server failures.

``call_memory_rpc`` maps the memory bridge's JSON-RPC ``-32602`` (invalid
params) onto an HTTP 400, which is the right status, but tags the envelope
``ErrorCode.INTERNAL_ERROR`` - the one code that
``infra/errors._DEFAULT_STATUS`` pins to 500 and that ``docs/api.md`` documents
as "Unhandled exception". The caller is served the generic internal-error copy
for a typo in a list filter. These tests drive the real router so the status
*and* the code are both checked.
"""

from __future__ import annotations

from typing import Any

import pytest

# Same gate as tests/integration/test_memory_api.py: the bridge is what turns
# caller params into -32602, so skip rather than fail when it is not installed.
pytest.importorskip("octop_memory.adapters.bridge.handlers")


# ``(route suffix, request body)`` for params the pinned octop_memory bridge
# rejects with -32602 before it touches storage; none of these can be a
# server-side fault.
_BAD_PARAMS: list[tuple[str, dict[str, Any]]] = [
    ("atoms/list", {"order": "sideways"}),
    ("atoms/list", {"order_by": "bogus"}),
    ("atoms/list", {"importance_min": "urgent"}),
    ("entities/list", {"order": "sideways"}),
    ("raw_events/list", {"event_type": "bogus"}),
    ("journal/list", {"target_type": "bogus"}),
    ("candidates/list", {"status": "bogus"}),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("suffix,body", _BAD_PARAMS)
async def test_invalid_memory_params_is_not_internal_error(
    env_with_main_agent: tuple[Any, Any, dict[str, str], str],
    suffix: str,
    body: dict[str, Any],
) -> None:
    client, _srv, auth, aid = env_with_main_agent

    r = await client.post(f"/api/agents/{aid}/memory/{suffix}", headers=auth, json=body)

    assert r.status_code == 400, r.text
    code = r.json()["error"]["code"]
    assert code != "INTERNAL_ERROR", f"client input reported as a server failure: {code}"
    assert code == "SLASH_BAD_ARGS"


@pytest.mark.asyncio
async def test_valid_memory_query_still_succeeds(
    env_with_main_agent: tuple[Any, Any, dict[str, str], str],
) -> None:
    """The guard must not start rejecting queries it used to answer."""
    client, _srv, auth, aid = env_with_main_agent

    r = await client.post(
        f"/api/agents/{aid}/memory/atoms/list",
        headers=auth,
        json={"order_by": "created_at", "order": "desc", "limit": 10},
    )

    assert r.status_code == 200, r.text
    assert "items" in r.json()


@pytest.mark.asyncio
async def test_unknown_memory_atom_is_still_404(
    env_with_main_agent: tuple[Any, Any, dict[str, str], str],
) -> None:
    """-32010 (bridge path-not-found) keeps mapping to NOT_FOUND."""
    client, _srv, auth, aid = env_with_main_agent

    r = await client.get(f"/api/agents/{aid}/memory/atoms/no-such-id", headers=auth)

    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "NOT_FOUND"
