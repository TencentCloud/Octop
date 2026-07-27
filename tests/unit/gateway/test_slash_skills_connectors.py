"""tests/unit/test_slash_skills_connectors.py"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.connectors import ConnectorRepo
from octop.infra.db.repos.sessions import SessionRepo
from octop.infra.db.repos.threads import ThreadRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.gateway.slash import BufferSink, SlashCommand, build_default_dispatcher
from octop.infra.gateway.slash.ctx import SlashCtx
from octop.infra.gateway.threads import ThreadRegistry


@pytest.fixture
def ctx(tmp_path: Path):
    db = SqlitePool(tmp_path / "x.db")
    run_migrations(db)
    UserRepo(db).create(username="u", password_hash="h", role="user")
    AgentRepo(db).create(agent_id="a1", user_id=1, name="bot")
    repo = ConnectorRepo(db)
    repo.create(
        instance_id="inst1",
        user_id=1,
        kind="feishu",
        display_name="Feishu Bot",
        mcp_server_name="feishu_inst1",
    )
    repo.upsert_credentials(instance_id="inst1", blob=b"enc")
    registry = ThreadRegistry(session_repo=SessionRepo(db), thread_repo=ThreadRepo(db))
    sk = ThreadRegistry.make_key(agent_id="a1", channel_type="ui", channel_subject_id="1")
    return SlashCtx(
        agent_id="a1",
        user_id=1,
        channel_type="ui",
        session_key=sk,
        thread_registry=registry,
        agent_repo=AgentRepo(db),
        connector_repo=ConnectorRepo(db),
        agent_manager=object(),
    )


@pytest.fixture
def dispatcher():
    return build_default_dispatcher()


async def test_connectors_list(dispatcher, ctx):
    sink = BufferSink()
    await dispatcher.handle(SlashCommand("connectors", ""), ctx, sink)
    text = "\n".join(sink.lines)
    assert "Feishu Bot" in text
    assert "feishu_inst1" in text


async def test_skills_list_mocked(dispatcher, ctx):
    sink = BufferSink()
    fake = [{"name": "pdf", "description": "read pdfs", "enabled": True, "kind": "workspace"}]
    ctx.agent_manager = MagicMock()
    ctx.agent_manager.list_skill_summaries = AsyncMock(return_value=fake)
    await dispatcher.handle(SlashCommand("skills", ""), ctx, sink)
    text = "\n".join(sink.lines)
    assert "pdf" in text
