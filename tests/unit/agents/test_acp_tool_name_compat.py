"""A later ACP tool update must keep the title from the first event."""

from __future__ import annotations

from types import SimpleNamespace

from octop_harness.acp.client import ACPHostedClient
from octop_harness.acp.models import ACPRunnerConfig

from octop.infra.agents.acp_tool_name_compat import install_acp_tool_titles

_CALL = "call-0\nfc_0"


def _client() -> ACPHostedClient:
    install_acp_tool_titles()
    client = ACPHostedClient(
        runner_name="cursor_cli",
        runner_config=ACPRunnerConfig(command="agent", args=["acp"]),
        cwd=".",
    )
    client.start_prompt(lambda _payload, _is_last: None)
    return client


def _update(title: str | None) -> SimpleNamespace:
    return SimpleNamespace(
        tool_call_id=_CALL,
        title=title,
        kind="other",
        status="completed",
        raw_input=None,
        content=None,
        raw_output=None,
    )


def test_titleless_update_keeps_the_first_tool_name() -> None:
    client = _client()
    opened = client._tool_event_from_state(_update("Web Search"))
    assert opened is not None
    assert opened["name"] == "Web Search"

    finished = client._tool_event_from_state(_update(None))
    assert finished is not None
    assert finished["name"] == "Web Search"
    assert finished["title"] == "Web Search"


def test_new_prompt_does_not_reuse_the_previous_title() -> None:
    client = _client()
    client._tool_event_from_state(_update("Web Search"))
    client.start_prompt(lambda _payload, _is_last: None)

    finished = client._tool_event_from_state(_update(None))
    assert finished is not None
    assert finished["name"] == "unknown"
