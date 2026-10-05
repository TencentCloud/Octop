"""Composer context for dashboard chat turns."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import HumanMessage

from octop.api.routers.chat import turn as chat_turn
from octop.api.routers.chat.models import ChatTurnBody
from octop.api.routers.chat.serialize import _serialize_history_message
from octop.api.routers.chat.turn import resolve_thread_id
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.gateway.process.message_keys import COMPOSER_CTX_KEY, build_composer_context


class _ThreadRegistry:
    def __init__(self, row: object) -> None:
        self.row = row
        self.rebound = False

    def get_thread(self, thread_id: str) -> object:
        assert thread_id == "owner-thread"
        return self.row

    async def rebind(self, **_kwargs: object) -> None:
        self.rebound = True


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


@pytest.mark.parametrize("knowledge_ids", [["general"], []])
async def test_dashboard_knowledge_selection_survives_history_serialization(
    monkeypatch: pytest.MonkeyPatch, knowledge_ids: list[str]
) -> None:
    monkeypatch.setattr(
        chat_turn,
        "require_agent_row",
        lambda *_args, **_kwargs: SimpleNamespace(default_model=None),
    )
    monkeypatch.setattr(chat_turn, "validate_chat_mcp_servers", AsyncMock(return_value=None))
    monkeypatch.setattr(chat_turn, "validate_chat_skills", AsyncMock(return_value=None))
    monkeypatch.setattr(
        chat_turn, "resolve_thread_id", AsyncMock(return_value=("thread-1", "session-1"))
    )
    server = SimpleNamespace(
        app_runtime=SimpleNamespace(gateway=SimpleNamespace(thread_registry=object()))
    )
    body = ChatTurnBody(text="hello", knowledge_base_ids=knowledge_ids)
    prepared = await chat_turn.prepare_dashboard_turn(
        server, agent_id="agent-1", user=SimpleNamespace(id=1), turn=body
    )
    inbound = chat_turn.build_dashboard_inbound(
        agent_id="agent-1",
        user_id=1,
        prepared=prepared,
        turn=body,
        ws_connection_id="connection-1",
    )
    context = inbound.metadata[COMPOSER_CTX_KEY]
    assert context["knowledgeBaseIds"] == knowledge_ids

    entry = _serialize_history_message(
        HumanMessage(content="hello", additional_kwargs={COMPOSER_CTX_KEY: context})
    )
    assert entry is not None
    assert entry["composer_context"]["knowledgeBaseIds"] == knowledge_ids
