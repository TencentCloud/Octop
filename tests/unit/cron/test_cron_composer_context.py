"""Cron agent runs should stamp composer_context on the stored user message."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import HumanMessage

from octop.infra.cron.delivery import CronDeliveryCommand, CronDeliveryService
from octop.infra.gateway.process.message_keys import (
    COMPOSER_CTX_KEY,
    build_composer_context,
)
from octop.infra.gateway.threads import ThreadRegistry


def test_cron_composer_context_includes_connectors_and_model() -> None:
    ctx = build_composer_context(
        mcp_servers=["github__1", "feishu__2"],
        skills=None,
        target_agent_ids=None,
        model_ref="openai/gpt-4o-mini",
        default_model="openai/gpt-4o",
    )
    assert ctx == {
        "connectors": ["github__1", "feishu__2"],
        "model": "openai/gpt-4o-mini",
    }


def _dashboard_session() -> MagicMock:
    session = MagicMock()
    session.channel_type = ThreadRegistry.CHANNEL_DASHBOARD
    session.thread_id = "thr1"
    session.user_id = 1
    session.agent_id = "a1"
    session.session_key = "a1:dashboard:1:dm"
    session.channel_id = None
    return session


async def _run_locked(_agent_id: str, _session_key: str, operation) -> None:
    await operation()


def _command(**overrides: object) -> CronDeliveryCommand:
    values: dict[str, object] = {
        "cron_id": "j1",
        "cron_name": "nightly",
        "agent_id": "a1",
        "user_id": 1,
        "session_key": "a1:dashboard:1:dm",
        "prompt": "cron prompt",
        "fresh_thread": False,
        "task_type": "agent",
        "model": None,
        "mcp_servers": (),
    }
    values.update(overrides)
    return CronDeliveryCommand(**values)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_deliver_agent_stamps_composer_on_human_message() -> None:
    session = _dashboard_session()
    agent_row = MagicMock()
    agent_row.default_model = "openai/gpt-4o"

    async def _stream(_aid: str, request: dict):
        msgs = request.get("messages") or []
        assert msgs, "expected messages on harness request"
        human = msgs[0]
        assert isinstance(human, HumanMessage)
        assert human.additional_kwargs.get(COMPOSER_CTX_KEY) == {
            "connectors": ["github__1"],
            "model": "openai/gpt-4o-mini",
        }
        yield {"type": "token", "content": "ok"}

    agent_manager = MagicMock()
    agent_manager.merge_turn_mcp_servers = MagicMock(
        side_effect=lambda _uid, explicit, apply_defaults=None: list(explicit) if explicit else None
    )
    agent_manager.prepare_chat_mcp = AsyncMock(return_value=[])
    agent_manager.stream = _stream
    agent_manager.get_row = MagicMock(return_value=agent_row)

    gateway = MagicMock()
    gateway.run_in_session = _run_locked
    gateway.require_session = MagicMock(return_value=session)
    gateway.push_session_text = AsyncMock()
    gateway.notify_dashboard_push = AsyncMock()

    service = CronDeliveryService(
        gateway=gateway,
        agent_manager=agent_manager,
        repos=MagicMock(),
    )
    await service.deliver(_command(model="openai/gpt-4o-mini", mcp_servers=("github__1",)))

    agent_manager.prepare_chat_mcp.assert_awaited()
    gateway.push_session_text.assert_awaited_once()
    assert gateway.push_session_text.await_args.args[1] == "ok"


@pytest.mark.asyncio
async def test_deliver_agent_merges_default_open_when_empty() -> None:
    session = _dashboard_session()
    agent_row = MagicMock()
    agent_row.default_model = "openai/gpt-4o"

    async def _stream(_aid: str, request: dict):
        assert request.get("mcp_servers") == ["always__1"]
        human = (request.get("messages") or [])[0]
        assert isinstance(human, HumanMessage)
        assert human.additional_kwargs.get(COMPOSER_CTX_KEY) == {
            "connectors": ["always__1"],
        }
        yield {"type": "token", "content": "ok"}

    agent_manager = MagicMock()
    agent_manager.merge_turn_mcp_servers = MagicMock(return_value=["always__1"])
    agent_manager.prepare_chat_mcp = AsyncMock(return_value=[])
    agent_manager.stream = _stream
    agent_manager.get_row = MagicMock(return_value=agent_row)

    gateway = MagicMock()
    gateway.run_in_session = _run_locked
    gateway.require_session = MagicMock(return_value=session)
    gateway.push_session_text = AsyncMock()
    gateway.notify_dashboard_push = AsyncMock()

    service = CronDeliveryService(
        gateway=gateway,
        agent_manager=agent_manager,
        repos=MagicMock(),
    )
    await service.deliver(_command(mcp_servers=()))

    agent_manager.merge_turn_mcp_servers.assert_called_once_with(1, None, apply_defaults=True)
    agent_manager.prepare_chat_mcp.assert_awaited()
    gateway.push_session_text.assert_awaited()


@pytest.mark.asyncio
async def test_deliver_agent_explicit_mcp_overrides_defaults() -> None:
    session = _dashboard_session()
    agent_row = MagicMock()
    agent_row.default_model = None

    async def _stream(_aid: str, request: dict):
        assert request.get("mcp_servers") == ["picked__1"]
        yield {"type": "token", "content": "ok"}

    agent_manager = MagicMock()
    agent_manager.merge_turn_mcp_servers = MagicMock(return_value=["picked__1"])
    agent_manager.prepare_chat_mcp = AsyncMock(return_value=[])
    agent_manager.stream = _stream
    agent_manager.get_row = MagicMock(return_value=agent_row)

    gateway = MagicMock()
    gateway.run_in_session = _run_locked
    gateway.require_session = MagicMock(return_value=session)
    gateway.push_session_text = AsyncMock()
    gateway.notify_dashboard_push = AsyncMock()

    service = CronDeliveryService(
        gateway=gateway,
        agent_manager=agent_manager,
        repos=MagicMock(),
    )
    await service.deliver(_command(mcp_servers=("picked__1",)))

    agent_manager.merge_turn_mcp_servers.assert_called_once_with(
        1, ["picked__1"], apply_defaults=False
    )
    gateway.push_session_text.assert_awaited()
