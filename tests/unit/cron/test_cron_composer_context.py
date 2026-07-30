"""Cron agent runs should stamp composer_context on the stored user message."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import HumanMessage

from octop.infra.gateway.process.message_keys import (
    COMPOSER_CTX_KEY,
    build_composer_context,
)


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


@pytest.mark.asyncio
async def test_push_text_from_session_stamps_composer_on_human_message() -> None:
    """Agent cron path must put COMPOSER_CTX_KEY on HumanMessage additional_kwargs."""
    from octop.infra.gateway.gateway import Gateway

    session = MagicMock()
    session.channel_type = "dashboard"
    session.thread_id = "thr1"
    session.user_id = 1
    session.channel_id = None
    session.to_channel_subject = MagicMock(return_value=MagicMock())

    agent_row = MagicMock()
    agent_row.default_model = "openai/gpt-4o"

    chunks = [{"type": "token", "content": "ok"}]

    async def _stream(_aid: str, request: dict):
        msgs = request.get("messages") or []
        assert msgs, "expected messages on harness request"
        human = msgs[0]
        assert isinstance(human, HumanMessage)
        assert human.additional_kwargs.get(COMPOSER_CTX_KEY) == {
            "connectors": ["github__1"],
            "model": "openai/gpt-4o-mini",
        }
        for c in chunks:
            yield c

    agent_manager = MagicMock()
    agent_manager.prepare_chat_mcp = AsyncMock(return_value=[])
    agent_manager.stream = _stream
    agent_manager.get_row = MagicMock(return_value=agent_row)

    gw = Gateway.__new__(Gateway)
    gw._agent_manager = agent_manager
    gw._thread_registry = MagicMock()
    gw._thread_registry.get_session = MagicMock(return_value=session)
    gw._require_session = MagicMock(return_value=session)
    gw._bump_dashboard_session = MagicMock()
    gw.push_text = AsyncMock()
    gw._resolve_push_subject = MagicMock(return_value=MagicMock())

    await Gateway.push_text_from_session(
        gw,
        "a1",
        "a1:dashboard:1:dm",
        "cron prompt",
        task_type="agent",
        model="openai/gpt-4o-mini",
        mcp_servers=["github__1"],
    )

    agent_manager.prepare_chat_mcp.assert_awaited()
    gw.push_text.assert_awaited()
