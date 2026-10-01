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


class _SessionKeyThreadRegistry(_ThreadRegistry):
    """Registry fake that also answers session-key binding lookups."""

    def __init__(self, row: object, bound: str | None) -> None:
        super().__init__(row)
        self.bound = bound

    def get_bound_thread_id(self, session_key: str) -> str | None:
        return self.bound


async def test_resolve_thread_id_rejects_another_users_session_key() -> None:
    registry = _SessionKeyThreadRegistry(
        SimpleNamespace(agent_id="shared-agent", user_id=1),
        "owner-thread",
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


async def test_resolve_thread_id_reuses_the_callers_own_session_key_thread() -> None:
    registry = _SessionKeyThreadRegistry(
        SimpleNamespace(agent_id="shared-agent", user_id=1),
        "owner-thread",
    )

    resolved = await resolve_thread_id(
        agent_id="shared-agent",
        user_id=1,
        thread_registry=registry,
        thread_id=None,
        session_key="shared-agent:dashboard:1:dm",
    )

    assert resolved == ("owner-thread", "shared-agent:dashboard:1:dm")


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
