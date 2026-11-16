"""Composer context for dashboard chat turns."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from octop.api.routers.chat.turn import resolve_thread_id
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


class _BoundRegistry:
    """Registry whose ``session_key`` is already bound to ``bound``'s thread."""

    def __init__(self, row: object, *, bound: str | None) -> None:
        self.row = row
        self.bound = bound
        self.rebound = False
        self.created = False

    def get_bound_thread_id(self, session_key: str) -> str | None:
        assert session_key == "shared-agent:dashboard:1:dm"
        return self.bound

    def get_thread(self, thread_id: str) -> object:
        assert thread_id == self.bound
        return self.row

    async def rebind(self, **_kwargs: object) -> None:
        self.rebound = True

    async def get_or_create_by_key(self, **_kwargs: object) -> str:
        self.created = True
        return "new-thread"


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


async def test_resolve_thread_id_rejects_another_users_session_key() -> None:
    registry = _BoundRegistry(
        SimpleNamespace(agent_id="shared-agent", user_id=1),
        bound="owner-thread",
    )

    with pytest.raises(OctopError) as exc_info:
        await resolve_thread_id(
            agent_id="shared-agent",
            user_id=2,
            thread_registry=registry,
            thread_id=None,
            session_key="shared-agent:dashboard:1:dm",
        )

    assert exc_info.value.code == ErrorCode.FORBIDDEN
    assert registry.created is False


async def test_resolve_thread_id_rejects_session_key_bound_to_another_agent() -> None:
    registry = _BoundRegistry(
        SimpleNamespace(agent_id="other-agent", user_id=2),
        bound="other-thread",
    )

    with pytest.raises(OctopError) as exc_info:
        await resolve_thread_id(
            agent_id="shared-agent",
            user_id=2,
            thread_registry=registry,
            thread_id=None,
            session_key="shared-agent:dashboard:1:dm",
        )

    assert exc_info.value.code == ErrorCode.AGENT_NOT_FOUND
    assert registry.created is False


async def test_resolve_thread_id_follows_own_session_key() -> None:
    registry = _BoundRegistry(
        SimpleNamespace(agent_id="shared-agent", user_id=1),
        bound="owner-thread",
    )

    assert await resolve_thread_id(
        agent_id="shared-agent",
        user_id=1,
        thread_registry=registry,
        thread_id=None,
        session_key="shared-agent:dashboard:1:dm",
    ) == ("owner-thread", "shared-agent:dashboard:1:dm")
    assert registry.created is False


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
