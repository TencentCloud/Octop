"""Composer context for dashboard chat turns."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import HumanMessage

from octop.api.routers.chat.turn import resolve_thread_id
from octop.infra.agents.turn_resources import resolve_turn_mcp
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.gateway.process.message_keys import (
    COMPOSER_CTX_KEY,
    build_composer_context,
    stamp_composer_fields,
)


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


def test_build_composer_context_includes_knowledge_bases() -> None:
    ctx = build_composer_context(
        mcp_servers=["docs"],
        skills=None,
        target_agent_ids=None,
        model_ref=None,
        default_model=None,
        knowledge_base_ids=["kb-1", ""],
    )
    assert ctx == {"connectors": ["docs"], "knowledgeBaseIds": ["kb-1"]}


def test_stamp_composer_fields_adds_knowledge_to_the_user_message() -> None:
    message = HumanMessage(content="hello", additional_kwargs={})
    stamp_composer_fields(
        {"messages": [message]},
        connectors=["docs"],
        knowledge_base_ids=["kb-1"],
    )
    assert message.additional_kwargs[COMPOSER_CTX_KEY] == {
        "connectors": ["docs"],
        "knowledgeBaseIds": ["kb-1"],
    }


async def test_managed_connectors_skip_inprocess_tool_load() -> None:
    manager = MagicMock()
    manager.get_row.return_value = SimpleNamespace(kind="managed", user_id=1)
    manager.default_mcp_servers.return_value = []
    manager.merge_turn_mcp_servers.return_value = ["docs"]
    manager.prepare_chat_mcp = AsyncMock(return_value=["docs"])

    resolved = await resolve_turn_mcp(
        manager,
        agent_id="managed-1",
        user_id=1,
        explicit=["docs"],
    )

    assert resolved is not None
    assert resolved.shown == ["docs"]
    assert resolved.failed == []
    manager.prepare_chat_mcp.assert_not_awaited()


def test_build_composer_context_includes_model_override() -> None:
    ctx = build_composer_context(
        mcp_servers=None,
        skills=None,
        target_agent_ids=None,
        model_ref="openai/gpt-4o-mini",
        default_model="openai/gpt-4o",
    )
    assert ctx == {"model": "openai/gpt-4o-mini"}
