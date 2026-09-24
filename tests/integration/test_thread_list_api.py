"""Page bounds for ``GET /api/agents/{agent_id}/threads``."""

from __future__ import annotations

from typing import Any

from octop.api.routers.chat.serialize import HISTORY_MAX_LIMIT


async def _create_threads(client: Any, auth: dict[str, str], agent_id: str, count: int) -> None:
    for _ in range(count):
        response = await client.post(f"/api/agents/{agent_id}/threads", headers=auth)
        assert response.status_code == 201, response.text


async def test_thread_list_rejects_limit_below_one(env_alice_bob_agent: Any) -> None:
    """A non-positive ``limit`` must not be handed to SQL ``LIMIT``.

    SQLite reads a negative LIMIT as "no limit at all" and ``LIMIT 0`` as "no rows",
    so both answer a paginated request with the wrong page instead of rejecting it.
    """
    client, _srv, alice, _bob, agent_id = env_alice_bob_agent
    await _create_threads(client, alice, agent_id, 3)

    for bad in (0, -1):
        response = await client.get(f"/api/agents/{agent_id}/threads?limit={bad}", headers=alice)
        assert response.status_code == 422, (
            f"limit={bad} -> {response.status_code}: {response.text}"
        )


async def test_thread_list_caps_limit_like_the_message_page(
    env_alice_bob_agent: Any,
) -> None:
    """The thread ceiling is the one this module already uses for message pages."""
    client, _srv, alice, _bob, agent_id = env_alice_bob_agent
    await _create_threads(client, alice, agent_id, 2)

    ok = await client.get(
        f"/api/agents/{agent_id}/threads?limit={HISTORY_MAX_LIMIT}", headers=alice
    )
    assert ok.status_code == 200, ok.text
    assert len(ok.json()) == 2

    too_big = await client.get(
        f"/api/agents/{agent_id}/threads?limit={HISTORY_MAX_LIMIT + 1}", headers=alice
    )
    assert too_big.status_code == 422, too_big.text
