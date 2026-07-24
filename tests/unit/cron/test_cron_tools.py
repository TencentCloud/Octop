"""Unit tests for built-in cronjob LangChain tools."""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from langgraph.config import var_child_runnable_config

from octop.config import OctopConfig
from octop.infra.cron.manager import CronManager
from octop.infra.cron.tools import build_cronjob_tools
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.services import build_shared_services
from octop.infra.gateway.threads import ThreadRegistry
from octop.infra.utils.paths import PathLayout
from octop.infra.utils.ulid import new_ulid


@contextmanager
def _configurable(**kwargs: object):
    token = var_child_runnable_config.set({"configurable": kwargs})
    try:
        yield
    finally:
        var_child_runnable_config.reset(token)


def _make_services(tmp_path: Path):
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    return build_shared_services(db=db, paths=PathLayout(tmp_path), config=OctopConfig())


def _make_manager(services) -> CronManager:
    gw = MagicMock()
    gw.thread_registry = MagicMock()
    gw.thread_registry.get_session = MagicMock(return_value=None)
    gw.thread_registry.get_or_create_by_key = AsyncMock(return_value="thr_test")
    mgr = CronManager(gateway=gw, repos=services.repos, timezone="UTC")
    mgr._scheduler = MagicMock()
    mgr._scheduler.get_job = MagicMock(return_value=None)
    return mgr


def _tool_by_name(tools: list, name: str):
    for tool in tools:
        if tool.name == name:
            return tool
    raise KeyError(name)


@pytest.mark.asyncio
async def test_cronjob_create_and_list(tmp_path: Path) -> None:
    services = _make_services(tmp_path)
    agent_id = new_ulid()
    user_id = services.repos.user_repo.create(username="u1", password_hash="x", role="user")
    services.repos.agent_repo.create(agent_id=agent_id, user_id=user_id, name="a1")
    mgr = _make_manager(services)
    tools = build_cronjob_tools(mgr)
    create = _tool_by_name(tools, "cronjob_create")
    list_tool = _tool_by_name(tools, "cronjob_list")

    with _configurable(agent_id=agent_id, user=str(user_id)):
        out = await create.ainvoke(
            {
                "trigger": "interval:120",
                "prompt": "say hi",
            }
        )
        data = json.loads(out)
        assert data["prompt"] == "say hi"
        assert data["trigger"] == "interval:120"
        assert data["task_type"] == "text"
        cron_id = data["id"]

        listed = json.loads(await list_tool.ainvoke({"include_disabled": True}))
        assert len(listed) == 1
        assert listed[0]["id"] == cron_id


@pytest.mark.asyncio
async def test_cronjob_isolated_by_agent_and_user(tmp_path: Path) -> None:
    services = _make_services(tmp_path)
    agent_a = new_ulid()
    agent_b = new_ulid()
    uid = services.repos.user_repo.create(username="owner", password_hash="x", role="user")
    other_uid = services.repos.user_repo.create(username="other", password_hash="x", role="user")
    services.repos.agent_repo.create(agent_id=agent_a, user_id=uid, name="a")
    services.repos.agent_repo.create(agent_id=agent_b, user_id=uid, name="b")
    mgr = _make_manager(services)
    tools = build_cronjob_tools(mgr)
    create = _tool_by_name(tools, "cronjob_create")
    get_tool = _tool_by_name(tools, "cronjob_get")

    with _configurable(agent_id=agent_a, user=str(uid)):
        created = json.loads(await create.ainvoke({"trigger": "interval:60", "prompt": "a"}))
    cron_id = created["id"]

    with _configurable(agent_id=agent_b, user=str(uid)):
        err = json.loads(await get_tool.ainvoke({"cron_id": cron_id}))
        assert "error" in err

    with _configurable(agent_id=agent_a, user=str(other_uid)):
        err = json.loads(await get_tool.ainvoke({"cron_id": cron_id}))
        assert "error" in err


@pytest.mark.asyncio
async def test_cronjob_delete(tmp_path: Path) -> None:
    services = _make_services(tmp_path)
    agent_id = new_ulid()
    user_id = services.repos.user_repo.create(username="del", password_hash="x", role="user")
    services.repos.agent_repo.create(agent_id=agent_id, user_id=user_id, name="a")
    mgr = _make_manager(services)
    tools = build_cronjob_tools(mgr)
    create = _tool_by_name(tools, "cronjob_create")
    delete = _tool_by_name(tools, "cronjob_delete")

    with _configurable(agent_id=agent_id, user=str(user_id)):
        created = json.loads(await create.ainvoke({"trigger": "interval:30", "prompt": "p"}))
        cron_id = created["id"]
        out = json.loads(await delete.ainvoke({"cron_id": cron_id}))
        assert out["deleted"] == cron_id
        assert mgr.get(cron_id) is None


@pytest.mark.asyncio
async def test_cronjob_run_now(tmp_path: Path) -> None:
    services = _make_services(tmp_path)
    agent_id = new_ulid()
    user_id = services.repos.user_repo.create(username="run", password_hash="x", role="user")
    services.repos.agent_repo.create(agent_id=agent_id, user_id=user_id, name="a")
    mgr = _make_manager(services)
    mgr.run_now = AsyncMock()  # type: ignore[method-assign]
    tools = build_cronjob_tools(mgr)
    create = _tool_by_name(tools, "cronjob_create")
    run_now = _tool_by_name(tools, "cronjob_run_now")

    with _configurable(agent_id=agent_id, user=str(user_id)):
        created = json.loads(await create.ainvoke({"trigger": "interval:30", "prompt": "p"}))
        cron_id = created["id"]
        out = json.loads(await run_now.ainvoke({"cron_id": cron_id}))
        assert out["triggered"] == cron_id
        mgr.run_now.assert_awaited_once_with(cron_id)


@pytest.mark.asyncio
async def test_cronjob_create_uses_configurable_session_key(tmp_path: Path) -> None:
    services = _make_services(tmp_path)
    agent_id = new_ulid()
    user_id = services.repos.user_repo.create(username="sk", password_hash="x", role="user")
    services.repos.agent_repo.create(agent_id=agent_id, user_id=user_id, name="a")
    mgr = _make_manager(services)
    tools = build_cronjob_tools(mgr)
    create = _tool_by_name(tools, "cronjob_create")
    feishu_sk = ThreadRegistry.make_key(
        agent_id=agent_id,
        channel_type="feishu",
        channel_subject_id="ou_abc",
        channel_chat_type=ThreadRegistry.CHAT_TYPE_DM,
    )

    with _configurable(agent_id=agent_id, user=str(user_id), session_key=feishu_sk):
        out = await create.ainvoke({"trigger": "interval:30", "prompt": "ping"})
    data = json.loads(out)
    assert data["session_key"] == feishu_sk


@pytest.mark.asyncio
async def test_cronjob_create_persists_task_type(tmp_path: Path) -> None:
    services = _make_services(tmp_path)
    agent_id = new_ulid()
    user_id = services.repos.user_repo.create(username="tt", password_hash="x", role="user")
    services.repos.agent_repo.create(agent_id=agent_id, user_id=user_id, name="a")
    mgr = _make_manager(services)
    tools = build_cronjob_tools(mgr)
    create = _tool_by_name(tools, "cronjob_create")

    with _configurable(agent_id=agent_id, user=str(user_id)):
        out = await create.ainvoke(
            {"trigger": "interval:30", "prompt": "ping", "task_type": "text"}
        )
    data = json.loads(out)
    assert data["task_type"] == "text"
    row = mgr.get(data["id"])
    assert row is not None
    assert row.task_type == "text"
