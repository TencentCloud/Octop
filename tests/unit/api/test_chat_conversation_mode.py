"""ChatTurnBody / inbound metadata for conversation_mode (#616 M1 API)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from octop.api.routers.chat.models import ChatTurnBody


def test_chat_turn_body_accepts_ask_plan_craft() -> None:
    for mode in ("ask", "plan", "craft"):
        body = ChatTurnBody(text="hi", conversation_mode=mode)  # type: ignore[arg-type]
        assert body.conversation_mode == mode


def test_chat_turn_body_rejects_unknown_mode() -> None:
    with pytest.raises(ValidationError):
        ChatTurnBody(text="hi", conversation_mode="agent")  # type: ignore[arg-type]


def test_chat_turn_body_omitted_mode_is_none() -> None:
    body = ChatTurnBody(text="hi")
    assert body.conversation_mode is None


def test_from_ws_payload_parses_conversation_mode() -> None:
    body = ChatTurnBody.from_ws_payload({"text": "hi", "conversation_mode": "ask"})
    assert body.conversation_mode == "ask"


def test_from_ws_payload_drops_unknown_conversation_mode() -> None:
    body = ChatTurnBody.from_ws_payload({"text": "hi", "conversation_mode": "agent"})
    assert body.conversation_mode is None


def test_build_dashboard_inbound_stamps_conversation_mode_metadata() -> None:
    from harness_gateway.models import TextContent

    from octop.api.routers.chat.turn import PreparedDashboardTurn, build_dashboard_inbound

    prepared = PreparedDashboardTurn(
        thread_id="t1",
        session_key="sk",
        mcp_servers=None,
        skills=None,
        model_ref=None,
        inbound_content=[TextContent(text="hi")],
        composer_context=None,
        inbound_attachments=[],
    )
    inbound = build_dashboard_inbound(
        agent_id="agent-1",
        user_id=1,
        prepared=prepared,
        turn=ChatTurnBody(text="hi", conversation_mode="ask"),
        ws_connection_id="conn",
    )
    assert inbound.metadata["conversation_mode"] == "ask"


def test_build_dashboard_inbound_stamps_plan_brief_metadata() -> None:
    from harness_gateway.models import TextContent

    from octop.api.routers.chat.turn import PreparedDashboardTurn, build_dashboard_inbound

    prepared = PreparedDashboardTurn(
        thread_id="t1",
        session_key="sk",
        mcp_servers=None,
        skills=None,
        model_ref=None,
        inbound_content=[TextContent(text="按计划执行")],
        composer_context=None,
        inbound_attachments=[],
    )
    inbound = build_dashboard_inbound(
        agent_id="agent-1",
        user_id=1,
        prepared=prepared,
        turn=ChatTurnBody(
            text="按计划执行",
            conversation_mode="craft",
            plan_brief="## Approved plan\n\nDo it.",
        ),
        ws_connection_id="conn",
    )
    assert inbound.metadata["conversation_mode"] == "craft"
    assert inbound.metadata["plan_brief"] == "## Approved plan\n\nDo it."


def test_turn_has_content_accepts_plan_brief_only() -> None:
    from octop.api.routers.chat.turn import turn_has_content

    assert turn_has_content(ChatTurnBody(text="", plan_brief="## Approved plan\n\nDo it."))
    assert not turn_has_content(ChatTurnBody(text=""))


def test_content_parts_injects_trigger_for_plan_brief_only() -> None:
    from harness_gateway.models import TextContent

    from octop.api.routers.chat.turn import content_parts_from_dashboard_turn
    from octop.infra.agents.plan_artifact import PLAN_EXECUTE_USER_TRIGGER

    parts = content_parts_from_dashboard_turn(
        ChatTurnBody(text="", plan_brief="## Approved plan\n\nDo it.")
    )
    assert len(parts) == 1
    assert isinstance(parts[0], TextContent)
    assert parts[0].text == PLAN_EXECUTE_USER_TRIGGER
