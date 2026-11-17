"""Overlapping ACP permission requests must not drop the earlier waiter."""

from __future__ import annotations

import asyncio

import pytest
from octop_harness.acp.client import ACPHostedClient
from octop_harness.acp.models import ACPRunnerConfig

from octop.infra.agents.acp_permission_compat import install_acp_permission_queue

_OPTIONS = [
    {"optionId": "allow-once", "name": "Allow once", "kind": "allow_once"},
    {"optionId": "reject-once", "name": "Reject", "kind": "reject_once"},
]


def _client() -> ACPHostedClient:
    install_acp_permission_queue()
    client = ACPHostedClient(
        runner_name="cursor_cli",
        runner_config=ACPRunnerConfig(command="agent", args=["acp"]),
        cwd=".",
    )

    async def _on_message(_payload: dict[str, object], _is_last: bool) -> None:
        return None

    client.start_prompt(_on_message)
    return client


@pytest.mark.asyncio
async def test_second_permission_waits_until_the_first_is_answered() -> None:
    client = _client()
    first = asyncio.create_task(
        client.request_permission(
            _OPTIONS,
            "session",
            {"title": "Web search: one", "kind": "fetch"},
        )
    )
    await asyncio.sleep(0)
    assert client.pending_permission is not None
    assert client.pending_permission.summary == "Web search: one"

    second = asyncio.create_task(
        client.request_permission(
            _OPTIONS,
            "session",
            {"title": "Web search: two", "kind": "fetch"},
        )
    )
    await asyncio.sleep(0)
    assert client.pending_permission.summary == "Web search: one"
    assert not second.done()

    client.resolve_permission("allow-once")
    first_result = await asyncio.wait_for(first, timeout=1)
    assert getattr(first_result.outcome, "option_id", None) == "allow-once"

    await asyncio.sleep(0)
    assert not second.done()
    assert client.pending_permission is not None
    assert client.pending_permission.summary == "Web search: two"

    client.resolve_permission("allow-once")
    second_result = await asyncio.wait_for(second, timeout=1)
    assert getattr(second_result.outcome, "option_id", None) == "allow-once"
