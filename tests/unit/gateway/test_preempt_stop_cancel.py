"""Gateway pre-lock /stop cancel preempts the in-flight turn."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from harness_gateway.models import ChannelSubject, InboundMessage, TextContent

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.sessions import SessionRepo
from octop.infra.db.repos.threads import ThreadRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.gateway.gateway import Gateway
from octop.infra.gateway.process.message_keys import session_key_from_message
from octop.infra.gateway.threads import ThreadRegistry


@pytest.mark.asyncio
async def test_preempt_cancel_on_stop_calls_cancel_stream(tmp_path: Path) -> None:
    db = SqlitePool(tmp_path / "gw.db")
    run_migrations(db)
    UserRepo(db).create(username="u", password_hash="h", role="user")
    AgentRepo(db).create(
        agent_id="agent1",
        user_id=1,
        name="bot",
        default_model="openai/gpt-4o",
    )
    registry = ThreadRegistry(session_repo=SessionRepo(db), thread_repo=ThreadRepo(db))
    agent_id = "agent1"
    sk = ThreadRegistry.make_key(agent_id=agent_id, channel_type="feishu", channel_subject_id="u1")
    tid = await registry.get_or_create_by_key(
        session_key=sk,
        agent_id=agent_id,
        user_id=1,
        channel_type="feishu",
    )

    agent_manager = MagicMock()
    gw = Gateway(agent_manager=agent_manager, repos=MagicMock())
    gw._thread_registry = registry  # noqa: SLF001 — test wiring

    msg = InboundMessage(
        channel_id="ch1",
        channel_type="feishu",
        content=[TextContent(text="/stop")],
        channel_subject=ChannelSubject(subject_id="u1"),
        tenant_id=agent_id,
    )
    assert session_key_from_message(msg, agent_id=agent_id) == sk

    await gw._preempt_cancel_on_stop("ch1", msg)  # noqa: SLF001

    agent_manager.cancel_stream.assert_called_once_with(agent_id, tid)


@pytest.mark.asyncio
async def test_preempt_cancel_ignores_non_stop() -> None:
    agent_manager = MagicMock()
    gw = Gateway(agent_manager=agent_manager, repos=MagicMock())
    gw._thread_registry = MagicMock()  # noqa: SLF001

    msg = InboundMessage(
        channel_id="ch1",
        channel_type="feishu",
        content=[TextContent(text="hello")],
        channel_subject=ChannelSubject(subject_id="u1"),
        tenant_id="a1",
    )
    await gw._preempt_cancel_on_stop("ch1", msg)  # noqa: SLF001
    agent_manager.cancel_stream.assert_not_called()
