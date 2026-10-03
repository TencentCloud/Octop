"""Composer context for dashboard chat turns."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from octop.api.routers.chat import turn as turn_mod
from octop.api.routers.chat.models import ChatTurnBody, UserTurnWsFrame
from octop.api.routers.chat.turn import (
    PreparedDashboardTurn,
    build_dashboard_inbound,
    resolve_thread_id,
)
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.gateway.process.message_keys import build_composer_context


class _ThreadRegistry:
    def __init__(self, row: object) -> None:
        self.row = row
        self.rebound = False

    def get_thread(self, thread_id: str) -> object:
        assert thread_id == "owner-thread"
        return self.row

    async def rebind(self, **_kwargs: object) -> None:
        self.rebound = True


@pytest.mark.parametrize(
    "enabled,model,expected",
    [(True, "p/default", True), (False, "p/default", False), (True, None, False)],
)
async def test_prepare_team_turn_persists_the_switch_in_composer_history(
    monkeypatch: pytest.MonkeyPatch,
    enabled: bool,
    model: str | None,
    expected: bool,
) -> None:
    row = SimpleNamespace(default_model="p/default", kind="team")
    monkeypatch.setattr(turn_mod, "require_agent_row", lambda *_a, **_k: row)
    monkeypatch.setattr(turn_mod, "validate_chat_mcp_servers", AsyncMock(return_value=None))
    monkeypatch.setattr(turn_mod, "validate_chat_skills", AsyncMock(return_value=None))
    monkeypatch.setattr(turn_mod, "resolve_thread_id", AsyncMock(return_value=("room", "sk")))
    server = MagicMock()
    server.app_runtime.agent_registry.providers.is_model_ref_usable.return_value = True
    prepared = await turn_mod.prepare_dashboard_turn(
        server,
        agent_id="host",
        user=SimpleNamespace(id=1),
        turn=ChatTurnBody(text="hi", default_model=model, apply_model_to_team=enabled),
    )
    assert prepared.composer_context == {"applyModelToTeam": expected}
    assert row.default_model == "p/default"


@pytest.mark.parametrize("enabled,model", [(True, "p/chosen"), (False, "p/chosen"), (True, None)])
def test_team_override_ws_flag_requires_an_explicit_model(enabled: bool, model: str | None) -> None:
    turn = UserTurnWsFrame(text="hi", model=model, apply_model_to_team=enabled).to_turn_body()
    assert ChatTurnBody().apply_model_to_team is False
    assert turn.apply_model_to_team is enabled
    prepared = PreparedDashboardTurn(
        thread_id="t",
        session_key="sk",
        mcp_servers=None,
        skills=None,
        model_ref=model,
        inbound_content=[],
        composer_context=None,
        inbound_attachments=[],
    )
    inbound = build_dashboard_inbound(
        agent_id="host", user_id=1, prepared=prepared, turn=turn, ws_connection_id="ws"
    )
    assert inbound.metadata.get("apply_model_to_team", False) is bool(enabled and model)


async def test_resolve_thread_id_rejects_another_users_thread() -> None:
    registry = _ThreadRegistry(SimpleNamespace(agent_id="shared-agent", user_id=1))

    with pytest.raises(OctopError) as exc_info:
        await resolve_thread_id(
            agent_id="shared-agent",
            user_id=2,
            thread_registry=registry,
            thread_id="owner-thread",
            session_key=None,
        )

    assert exc_info.value.code == ErrorCode.FORBIDDEN
    assert registry.rebound is False


def test_build_composer_context_omits_default_model() -> None:
    ctx = build_composer_context(
        mcp_servers=["github"],
        skills=["docx"],
        target_agent_ids=["agent-b"],
        model_ref="openai/gpt-4o",
        default_model="openai/gpt-4o",
    )
    assert ctx == {
        "connectors": ["github"],
        "skills": ["docx"],
        "targetAgents": ["agent-b"],
    }


def test_build_composer_context_includes_model_override() -> None:
    ctx = build_composer_context(
        mcp_servers=None,
        skills=None,
        target_agent_ids=None,
        model_ref="openai/gpt-4o-mini",
        default_model="openai/gpt-4o",
    )
    assert ctx == {"model": "openai/gpt-4o-mini"}
