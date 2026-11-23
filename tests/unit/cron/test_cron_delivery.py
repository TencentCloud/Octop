"""CronDeliveryService: canonical checkpoint, channel push, and best-effort extras."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from octop.infra.agents.security.hitl_session import HitlSessionPolicy, HitlSessionPolicyStore
from octop.infra.cron.delivery import CronDeliveryCommand, CronDeliveryService
from octop.infra.cron.script_run import ScriptRunError, ScriptRunResult
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.sessions import SessionRepo
from octop.infra.db.repos.thread_messages import ThreadMessageRepo
from octop.infra.db.repos.threads import ThreadRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.gateway.threads import ThreadRegistry


def _command(**overrides: object) -> CronDeliveryCommand:
    values: dict[str, object] = {
        "cron_id": "j1",
        "cron_name": "喝水提醒",
        "agent_id": "a1",
        "user_id": 1,
        "session_key": "sk",
        "prompt": "记得喝水",
        "fresh_thread": False,
        "task_type": "text",
        "model": None,
        "mcp_servers": (),
    }
    values.update(overrides)
    return CronDeliveryCommand(**values)  # type: ignore[arg-type]


async def _run_locked(_agent_id: str, _session_key: str, operation) -> None:
    await operation()


def _session(*, channel_type: str, thread_id: str = "thr1") -> MagicMock:
    session = MagicMock()
    session.channel_type = channel_type
    session.thread_id = thread_id
    session.user_id = 1
    session.agent_id = "a1"
    session.session_key = "sk"
    session.channel_id = "ch-1"
    return session


def _seed_dashboard_thread(tmp_path: Path, *, thread_id: str) -> tuple[SqlitePool, Any]:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    UserRepo(db).create(username="u", password_hash="h", role="user")
    AgentRepo(db).create(agent_id="a1", user_id=1, name="bot")
    session_key = ThreadRegistry.dashboard_key(agent_id="a1", user_id=1)
    ThreadRepo(db).insert(
        thread_id=thread_id,
        agent_id="a1",
        user_id=1,
        channel_type=ThreadRegistry.CHANNEL_DASHBOARD,
        session_key=session_key,
    )
    SessionRepo(db).upsert(
        session_key=session_key,
        agent_id="a1",
        user_id=1,
        channel_type=ThreadRegistry.CHANNEL_DASHBOARD,
        chat_type=ThreadRegistry.CHAT_TYPE_DM,
        thread_id=thread_id,
    )
    session = SessionRepo(db).get(session_key)
    assert session is not None
    return db, session


@pytest.mark.asyncio
async def test_text_dashboard_appends_checkpoint_before_push() -> None:
    session = _session(channel_type=ThreadRegistry.CHANNEL_DASHBOARD)
    human = HumanMessage(content="Task j1: 喝水提醒 executed.", id="cron:x:human")
    ai = AIMessage(content="记得喝水", id="cron:x:assistant")
    harness = MagicMock()
    agent_manager = MagicMock()
    agent_manager.get_agent.return_value = harness

    order: list[str] = []

    async def append(_thread_id: str, _messages):
        order.append("checkpoint")
        return [human, ai]

    harness.aappend_messages = append

    async def push(*_args, **_kwargs):
        order.append("push")

    async def notify(*_args, **_kwargs):
        order.append("toast")

    gateway = MagicMock()
    gateway.run_in_session = _run_locked
    gateway.require_session = MagicMock(return_value=session)
    gateway.push_session_text = push
    gateway.notify_dashboard_push = notify

    repos = MagicMock()
    repos.user_repo.get.return_value = MagicMock(locale="en")
    repos.thread_message_repo.append_if_ready.side_effect = lambda *_a, **_k: (
        order.append("project") or 2
    )

    service = CronDeliveryService(gateway=gateway, agent_manager=agent_manager, repos=repos)
    await service.deliver(_command())

    assert order == ["checkpoint", "project", "push", "toast"]
    assert repos.thread_message_repo.append_if_ready.call_args.args[0] == "thr1"


@pytest.mark.asyncio
async def test_text_checkpoint_failure_skips_push() -> None:
    session = _session(channel_type=ThreadRegistry.CHANNEL_DASHBOARD)
    harness = MagicMock()
    harness.aappend_messages = AsyncMock(side_effect=RuntimeError("checkpoint down"))
    agent_manager = MagicMock()
    agent_manager.get_agent.return_value = harness

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
    with pytest.raises(RuntimeError, match="checkpoint down"):
        await service.deliver(_command())
    gateway.push_session_text.assert_not_awaited()
    gateway.notify_dashboard_push.assert_not_awaited()


@pytest.mark.asyncio
async def test_text_projection_and_toast_failure_still_pushes() -> None:
    session = _session(channel_type=ThreadRegistry.CHANNEL_DASHBOARD)
    harness = MagicMock()
    harness.aappend_messages = AsyncMock(
        return_value=[
            HumanMessage(content="h", id="cron:x:human"),
            AIMessage(content="记得喝水", id="cron:x:assistant"),
        ]
    )
    agent_manager = MagicMock()
    agent_manager.get_agent.return_value = harness

    gateway = MagicMock()
    gateway.run_in_session = _run_locked
    gateway.require_session = MagicMock(return_value=session)
    gateway.push_session_text = AsyncMock()
    gateway.notify_dashboard_push = AsyncMock(side_effect=RuntimeError("toast down"))

    repos = MagicMock()
    repos.user_repo.get.return_value = MagicMock(locale="zh")
    repos.thread_message_repo.append_if_ready.side_effect = RuntimeError("project down")

    service = CronDeliveryService(gateway=gateway, agent_manager=agent_manager, repos=repos)
    await service.deliver(_command())
    gateway.push_session_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_text_im_skips_checkpoint() -> None:
    session = _session(channel_type="feishu")
    agent_manager = MagicMock()
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
    await service.deliver(_command())
    agent_manager.get_agent.assert_not_called()
    gateway.push_session_text.assert_awaited_once()
    gateway.notify_dashboard_push.assert_not_awaited()


@pytest.mark.asyncio
async def test_allow_all_stamps_managed_mode_without_saving_policy() -> None:
    session = _session(channel_type="feishu")
    seen: dict[str, object] = {}

    async def _stream(_aid: str, request: dict):
        seen["request"] = request
        yield {"type": "token", "content": "done"}

    row = MagicMock()
    row.kind = "managed"
    agent_manager = MagicMock()
    agent_manager.merge_turn_mcp_servers = MagicMock(return_value=None)
    agent_manager.prepare_chat_mcp = AsyncMock(return_value=[])
    agent_manager.stream = _stream
    agent_manager.get_row = MagicMock(return_value=row)
    agent_manager.get_config = MagicMock(return_value={"managed_runner": "codebuddy"})
    store = MagicMock()
    agent_manager._hitl_session_store = store

    gateway = MagicMock()
    gateway.run_in_session = _run_locked
    gateway.require_session = MagicMock(return_value=session)
    gateway.push_session_text = AsyncMock()
    repos = MagicMock()
    service = CronDeliveryService(gateway=gateway, agent_manager=agent_manager, repos=repos)
    await service.deliver(_command(task_type="agent", prompt="run", allow_all=True))
    request = seen["request"]
    assert isinstance(request, dict)
    assert request["session_mode"] == "bypassPermissions"
    configurable = request["configurable"]
    assert isinstance(configurable, dict)
    assert configurable["acp_permission_mode"] == "yolo"
    store.set.assert_not_called()


def _policy_store() -> tuple[HitlSessionPolicyStore, MagicMock]:
    repo = MagicMock()
    repo.get.return_value = SimpleNamespace(hitl_policy=None)
    return HitlSessionPolicyStore(repo), repo


def _agent_delivery(
    stream,
    *,
    store: HitlSessionPolicyStore,
    kind: str = "native",
) -> tuple[CronDeliveryService, MagicMock]:
    session = _session(channel_type="feishu")
    row = MagicMock()
    row.kind = kind
    agent_manager = MagicMock()
    agent_manager.merge_turn_mcp_servers = MagicMock(return_value=None)
    agent_manager.prepare_chat_mcp = AsyncMock(return_value=[])
    agent_manager.stream = stream
    agent_manager.get_row = MagicMock(return_value=row)
    agent_manager.get_config = MagicMock(return_value={"managed_runner": "codebuddy"})
    agent_manager._hitl_session_store = store
    gateway = MagicMock()
    gateway.run_in_session = _run_locked
    gateway.require_session = MagicMock(return_value=session)
    gateway.push_session_text = AsyncMock()
    service = CronDeliveryService(
        gateway=gateway,
        agent_manager=agent_manager,
        repos=MagicMock(),
    )
    return service, gateway


@pytest.mark.asyncio
async def test_native_allow_all_applies_only_during_the_run() -> None:
    store, repo = _policy_store()
    seen: dict[str, object] = {}

    async def _stream(_aid: str, request: dict):
        seen["request"] = request
        seen["bash"] = store.allows("thr1", "bash")
        seen["question"] = store.allows("thr1", "ask_user_question")
        yield {"type": "token", "content": "done"}

    service, gateway = _agent_delivery(_stream, store=store)
    await service.deliver(_command(task_type="agent", prompt="run", allow_all=True))
    request = seen["request"]
    assert isinstance(request, dict)
    assert "session_mode" not in request
    assert seen["bash"] is True
    assert seen["question"] is False
    assert store.allows("thr1", "bash") is False
    repo.update_composer.assert_not_called()
    gateway.push_session_text.assert_awaited()


@pytest.mark.asyncio
async def test_allow_all_off_keeps_the_saved_policy() -> None:
    store, repo = _policy_store()
    store.set("thr1", HitlSessionPolicy(mode="allow_all"))
    repo.update_composer.reset_mock()
    seen: dict[str, bool] = {}

    async def _stream(_aid: str, request: dict):
        seen["during"] = store.allows("thr1", "bash")
        assert "session_mode" not in request
        yield {"type": "token", "content": "done"}

    service, _gateway = _agent_delivery(_stream, store=store)
    await service.deliver(_command(task_type="agent", prompt="run", allow_all=False))
    assert seen["during"] is True
    assert store.allows("thr1", "bash") is True
    repo.update_composer.assert_not_called()


@pytest.mark.asyncio
async def test_managed_allow_all_still_fails_when_the_run_asks() -> None:
    store, repo = _policy_store()

    async def _stream(_aid: str, _request: dict):
        yield {"type": "token", "content": "partial"}
        yield {"type": "hitl_required"}

    service, gateway = _agent_delivery(_stream, store=store, kind="managed")
    with pytest.raises(RuntimeError, match="interaction"):
        await service.deliver(_command(task_type="agent", prompt="run", allow_all=True))
    gateway.push_session_text.assert_not_awaited()
    repo.update_composer.assert_not_called()


def _script_service() -> tuple[CronDeliveryService, MagicMock]:
    session = _session(channel_type="feishu")
    agent_manager = MagicMock()
    agent_manager.workspace_for_agent = MagicMock(return_value=object())
    agent_manager.get_row = MagicMock(return_value=None)
    gateway = MagicMock()
    gateway.run_in_session = _run_locked
    gateway.require_session = MagicMock(return_value=session)
    gateway.push_session_text = AsyncMock()
    repos = MagicMock()
    repos.user_repo.get.return_value = None
    service = CronDeliveryService(
        gateway=gateway,
        agent_manager=agent_manager,
        repos=repos,
    )
    return service, gateway


@pytest.mark.asyncio
async def test_script_pushes_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _run(**_kwargs: object) -> ScriptRunResult:
        return ScriptRunResult(exit_code=0, stdout="hello\n", stderr="")

    monkeypatch.setattr("octop.infra.cron.delivery.run_cron_script", _run)
    service, gateway = _script_service()
    await service.deliver(
        _command(
            task_type="script",
            prompt="print('hello')",
            script_lang="python",
            script_source="inline",
        )
    )
    assert gateway.push_session_text.await_args.args[1] == "hello"


@pytest.mark.asyncio
async def test_script_empty_stdout_pushes_a_notice(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _run(**_kwargs: object) -> ScriptRunResult:
        return ScriptRunResult(exit_code=0, stdout=" \n", stderr="")

    monkeypatch.setattr("octop.infra.cron.delivery.run_cron_script", _run)
    service, gateway = _script_service()
    await service.deliver(
        _command(
            task_type="script",
            prompt="pass",
            cron_name="夜间脚本",
            script_lang="python",
            script_source="inline",
        )
    )
    text = gateway.push_session_text.await_args.args[1]
    assert "夜间脚本" in text
    assert "没有输出" in text


@pytest.mark.asyncio
async def test_script_failure_does_not_push(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _run(**_kwargs: object) -> ScriptRunResult:
        return ScriptRunResult(exit_code=2, stdout="", stderr="boom")

    monkeypatch.setattr("octop.infra.cron.delivery.run_cron_script", _run)
    service, gateway = _script_service()
    with pytest.raises(RuntimeError, match="boom"):
        await service.deliver(
            _command(
                task_type="script",
                prompt="raise SystemExit(2)",
                script_lang="python",
                script_source="inline",
            )
        )
    gateway.push_session_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_script_missing_interpreter_is_localized(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _run(**_kwargs: object) -> ScriptRunResult:
        raise ScriptRunError("interpreter_missing", "python")

    monkeypatch.setattr("octop.infra.cron.delivery.run_cron_script", _run)
    service, gateway = _script_service()
    with pytest.raises(RuntimeError, match="python"):
        await service.deliver(
            _command(
                task_type="script",
                prompt="print(1)",
                script_lang="python",
                script_source="inline",
            )
        )
    gateway.push_session_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_agent_hitl_does_not_push() -> None:
    session = _session(channel_type=ThreadRegistry.CHANNEL_DASHBOARD)

    async def _stream(_aid: str, _request: dict):
        yield {"type": "token", "content": "partial"}
        yield {"type": "hitl_required"}

    agent_manager = MagicMock()
    agent_manager.merge_turn_mcp_servers = MagicMock(return_value=None)
    agent_manager.prepare_chat_mcp = AsyncMock(return_value=[])
    agent_manager.stream = _stream
    agent_manager.get_row = MagicMock(return_value=None)

    gateway = MagicMock()
    gateway.run_in_session = _run_locked
    gateway.require_session = MagicMock(return_value=session)
    gateway.push_session_text = AsyncMock()

    repos = MagicMock()
    service = CronDeliveryService(
        gateway=gateway,
        agent_manager=agent_manager,
        repos=repos,
    )
    with pytest.raises(RuntimeError, match="interaction"):
        await service.deliver(_command(task_type="agent", prompt="run"))
    gateway.push_session_text.assert_not_awaited()
    projected = repos.thread_message_repo.append_if_ready.call_args.args[1]
    assert projected[0].role == "human"
    assert "run" in projected[0].message_json


@pytest.mark.asyncio
async def test_agent_empty_reply_does_not_push() -> None:
    session = _session(channel_type="feishu")

    async def _stream(_aid: str, _request: dict):
        yield {"type": "token", "content": "   "}

    agent_manager = MagicMock()
    agent_manager.merge_turn_mcp_servers = MagicMock(return_value=None)
    agent_manager.prepare_chat_mcp = AsyncMock(return_value=[])
    agent_manager.stream = _stream
    agent_manager.get_row = MagicMock(return_value=None)

    gateway = MagicMock()
    gateway.run_in_session = _run_locked
    gateway.require_session = MagicMock(return_value=session)
    gateway.push_session_text = AsyncMock()

    repos = MagicMock()
    service = CronDeliveryService(
        gateway=gateway,
        agent_manager=agent_manager,
        repos=repos,
    )
    with pytest.raises(RuntimeError, match="no visible response"):
        await service.deliver(_command(task_type="agent", prompt="run"))
    gateway.push_session_text.assert_not_awaited()
    projected = repos.thread_message_repo.append_if_ready.call_args.args[1]
    assert projected[0].role == "human"
    assert "run" in projected[0].message_json


@pytest.mark.asyncio
async def test_agent_strips_orphan_thinking_prefix() -> None:
    session = _session(channel_type="weixin")

    async def _stream(_aid: str, _request: dict):
        yield {"type": "token", "content": "internal reasoning"}
        yield {"type": "token", "content": "</think>"}
        yield {"type": "token", "content": "最终学习内容"}

    agent_manager = MagicMock()
    agent_manager.merge_turn_mcp_servers = MagicMock(return_value=None)
    agent_manager.prepare_chat_mcp = AsyncMock(return_value=[])
    agent_manager.stream = _stream
    agent_manager.get_row = MagicMock(return_value=None)

    gateway = MagicMock()
    gateway.run_in_session = _run_locked
    gateway.require_session = MagicMock(return_value=session)
    gateway.push_session_text = AsyncMock()

    service = CronDeliveryService(
        gateway=gateway,
        agent_manager=agent_manager,
        repos=MagicMock(),
    )
    await service.deliver(_command(task_type="agent", prompt="run"))
    assert gateway.push_session_text.await_args.args[1] == "最终学习内容"


@pytest.mark.asyncio
async def test_delivery_binds_channel_to_latest_conversation(tmp_path: Path) -> None:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    UserRepo(db).create(username="u", password_hash="h", role="user")
    AgentRepo(db).create(agent_id="a1", user_id=1, name="bot")
    session_key = ThreadRegistry.dashboard_key(agent_id="a1", user_id=1)
    threads = ThreadRepo(db)
    threads.insert(
        thread_id="thr_open",
        agent_id="a1",
        user_id=1,
        channel_type=ThreadRegistry.CHANNEL_DASHBOARD,
        session_key=session_key,
        title="正在看的旧对话",
        last_active=10,
    )
    threads.insert(
        thread_id="thr_latest",
        agent_id="a1",
        user_id=1,
        channel_type=ThreadRegistry.CHANNEL_DASHBOARD,
        session_key=session_key,
        title="最近一次会话",
        last_active=20,
    )
    threads.insert(
        thread_id="thr_blank",
        agent_id="a1",
        user_id=1,
        channel_type=ThreadRegistry.CHANNEL_DASHBOARD,
        session_key=session_key,
        title="空白新对话",
        last_active=0,
    )
    SessionRepo(db).upsert(
        session_key=session_key,
        agent_id="a1",
        user_id=1,
        channel_type=ThreadRegistry.CHANNEL_DASHBOARD,
        chat_type=ThreadRegistry.CHAT_TYPE_DM,
        thread_id="thr_open",
    )
    registry = ThreadRegistry(session_repo=SessionRepo(db), thread_repo=threads)

    seen: list[str] = []

    async def append(thread_id: str, _messages):
        seen.append(thread_id)
        return [
            HumanMessage(content="h", id="cron:x:human"),
            AIMessage(content="记得喝水", id="cron:x:assistant"),
        ]

    harness = MagicMock()
    harness.aappend_messages = append
    agent_manager = MagicMock()
    agent_manager.get_agent.return_value = harness

    gateway = MagicMock()
    gateway.thread_registry = registry
    gateway.run_in_session = _run_locked
    gateway.require_session = lambda _agent_id, key: registry.get_session(key)
    gateway.push_session_text = AsyncMock()
    gateway.notify_dashboard_push = AsyncMock()

    repos = MagicMock()
    repos.user_repo.get.return_value = MagicMock(locale="zh")
    repos.thread_message_repo.append_if_ready.return_value = 2

    service = CronDeliveryService(
        gateway=gateway,
        agent_manager=agent_manager,
        repos=repos,
    )
    await service.deliver(_command(session_key=session_key))

    assert seen == ["thr_latest"]
    bound = registry.get_session(session_key)
    assert bound is not None
    assert bound.thread_id == "thr_latest"


@pytest.mark.asyncio
async def test_delivery_pins_historical_thread(tmp_path: Path) -> None:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    UserRepo(db).create(username="u", password_hash="h", role="user")
    AgentRepo(db).create(agent_id="a1", user_id=1, name="bot")
    session_key = ThreadRegistry.dashboard_key(agent_id="a1", user_id=1)
    threads = ThreadRepo(db)
    threads.insert(
        thread_id="thr_old",
        agent_id="a1",
        user_id=1,
        channel_type=ThreadRegistry.CHANNEL_DASHBOARD,
        session_key=session_key,
        title="历史会话",
        last_active=10,
    )
    threads.insert(
        thread_id="thr_latest",
        agent_id="a1",
        user_id=1,
        channel_type=ThreadRegistry.CHANNEL_DASHBOARD,
        session_key=session_key,
        title="最近一次会话",
        last_active=20,
    )
    SessionRepo(db).upsert(
        session_key=session_key,
        agent_id="a1",
        user_id=1,
        channel_type=ThreadRegistry.CHANNEL_DASHBOARD,
        chat_type=ThreadRegistry.CHAT_TYPE_DM,
        thread_id="thr_latest",
    )
    registry = ThreadRegistry(session_repo=SessionRepo(db), thread_repo=threads)
    seen: list[str] = []

    async def append(thread_id: str, _messages):
        seen.append(thread_id)
        return [
            HumanMessage(content="h", id="cron:x:human"),
            AIMessage(content="记得喝水", id="cron:x:assistant"),
        ]

    harness = MagicMock()
    harness.aappend_messages = append
    agent_manager = MagicMock()
    agent_manager.get_agent.return_value = harness
    gateway = MagicMock()
    gateway.thread_registry = registry
    gateway.run_in_session = _run_locked
    gateway.require_session = lambda _agent_id, key: registry.get_session(key)
    gateway.push_session_text = AsyncMock()
    gateway.notify_dashboard_push = AsyncMock()
    repos = MagicMock()
    repos.user_repo.get.return_value = MagicMock(locale="zh")
    repos.thread_message_repo.append_if_ready.return_value = 2

    service = CronDeliveryService(
        gateway=gateway,
        agent_manager=agent_manager,
        repos=repos,
    )
    await service.deliver(_command(session_key="thread:thr_old"))

    assert seen == ["thr_old"]
    bound = registry.get_session(session_key)
    assert bound is not None
    assert bound.thread_id == "thr_old"


@pytest.mark.asyncio
async def test_fresh_thread_does_not_return_to_latest_conversation(tmp_path: Path) -> None:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    UserRepo(db).create(username="u", password_hash="h", role="user")
    AgentRepo(db).create(agent_id="a1", user_id=1, name="bot")
    session_key = ThreadRegistry.dashboard_key(agent_id="a1", user_id=1)
    threads = ThreadRepo(db)
    threads.insert(
        thread_id="thr_latest",
        agent_id="a1",
        user_id=1,
        channel_type=ThreadRegistry.CHANNEL_DASHBOARD,
        session_key=session_key,
        last_active=20,
    )
    SessionRepo(db).upsert(
        session_key=session_key,
        agent_id="a1",
        user_id=1,
        channel_type=ThreadRegistry.CHANNEL_DASHBOARD,
        chat_type=ThreadRegistry.CHAT_TYPE_DM,
        thread_id="thr_latest",
        channel_subject_id="1",
        channel_chat_type=ThreadRegistry.CHAT_TYPE_DM,
    )
    registry = ThreadRegistry(session_repo=SessionRepo(db), thread_repo=threads)

    seen: list[str] = []

    async def append(thread_id: str, _messages):
        seen.append(thread_id)
        return [
            HumanMessage(content="h", id="cron:x:human"),
            AIMessage(content="记得喝水", id="cron:x:assistant"),
        ]

    harness = MagicMock()
    harness.aappend_messages = append
    agent_manager = MagicMock()
    agent_manager.get_agent.return_value = harness

    gateway = MagicMock()
    gateway.thread_registry = registry
    gateway.run_in_session = _run_locked
    gateway.require_session = lambda _agent_id, key: registry.get_session(key)
    gateway.push_session_text = AsyncMock()
    gateway.notify_dashboard_push = AsyncMock()

    repos = MagicMock()
    repos.user_repo.get.return_value = MagicMock(locale="zh")
    repos.thread_message_repo.append_if_ready.return_value = 2

    service = CronDeliveryService(
        gateway=gateway,
        agent_manager=agent_manager,
        repos=repos,
    )
    await service.deliver(_command(session_key=session_key, fresh_thread=True))

    assert seen and seen[0] != "thr_latest"
    bound = registry.get_session(session_key)
    assert bound is not None
    assert bound.thread_id == seen[0]


@pytest.mark.asyncio
async def test_fresh_thread_validates_session_before_reset() -> None:
    session = _session(channel_type="feishu")
    order: list[str] = []

    async def reset(_key: str) -> str:
        order.append("reset")
        return "thr_new"

    def require(_agent_id: str, _key: str):
        order.append("require")
        return session

    gateway = MagicMock()
    gateway.run_in_session = _run_locked
    gateway.thread_registry.reset_by_session_key = reset
    gateway.require_session = require
    gateway.push_session_text = AsyncMock()

    service = CronDeliveryService(
        gateway=gateway,
        agent_manager=MagicMock(),
        repos=MagicMock(),
    )
    await service.deliver(_command(fresh_thread=True, task_type="text"))
    assert order == ["require", "reset", "require"]


@pytest.mark.asyncio
async def test_wrong_user_rejects_session() -> None:
    session = _session(channel_type="dashboard")
    session.user_id = 9
    gateway = MagicMock()
    gateway.run_in_session = _run_locked
    gateway.require_session = MagicMock(return_value=session)
    gateway.push_session_text = AsyncMock()

    service = CronDeliveryService(
        gateway=gateway,
        agent_manager=MagicMock(),
        repos=MagicMock(),
    )
    with pytest.raises(ValueError, match="does not belong to user"):
        await service.deliver(_command())
    gateway.push_session_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_dashboard_text_projects_into_real_sqlite(tmp_path: Path) -> None:
    db, session = _seed_dashboard_thread(tmp_path, thread_id="thr_hist")

    human = HumanMessage(
        content="Task j1: 喝水提醒 executed.",
        id="cron:01TESTHUMAN00000000000000:human",
    )
    ai = AIMessage(content="记得喝水", id="cron:01TESTHUMAN00000000000000:assistant")
    harness = MagicMock()
    harness.aappend_messages = AsyncMock(return_value=[human, ai])
    agent_manager = MagicMock()
    agent_manager.get_agent.return_value = harness

    gateway = MagicMock()
    gateway.run_in_session = _run_locked
    gateway.require_session = MagicMock(return_value=session)
    gateway.thread_registry = ThreadRegistry(
        session_repo=SessionRepo(db), thread_repo=ThreadRepo(db)
    )
    gateway.push_session_text = AsyncMock()
    gateway.notify_dashboard_push = AsyncMock()

    repos = MagicMock()
    repos.user_repo = UserRepo(db)
    repos.thread_message_repo = ThreadMessageRepo(db)

    service = CronDeliveryService(gateway=gateway, agent_manager=agent_manager, repos=repos)
    await service.deliver(_command(session_key=session.session_key))

    page, _has_more = ThreadMessageRepo(db).page("thr_hist", limit=10)
    assert [row.role for row in page] == ["human", "ai"]
    assert page[0].message_id == human.id
    assert page[1].message_id == ai.id
    assert "j1" in page[0].message_json
    assert "记得喝水" in page[1].message_json
    titled = ThreadRepo(db).get("thr_hist")
    assert titled is not None
    assert titled.title == "喝水提醒"
    gateway.push_session_text.assert_awaited_once()
    db.close()


@pytest.mark.asyncio
async def test_agent_failure_projects_the_prompt(tmp_path: Path) -> None:
    """A run that dies mid-stream must not leave an empty conversation (#516)."""
    db, session = _seed_dashboard_thread(tmp_path, thread_id="thr_fail")

    async def _stream(_aid: str, _request: dict):
        yield {"type": "token", "content": "先查一下"}
        raise RuntimeError("tool call failed")

    agent_manager = MagicMock()
    agent_manager.merge_turn_mcp_servers = MagicMock(return_value=None)
    agent_manager.prepare_chat_mcp = AsyncMock(return_value=[])
    agent_manager.stream = _stream
    agent_manager.get_row = MagicMock(return_value=None)

    gateway = MagicMock()
    gateway.run_in_session = _run_locked
    gateway.require_session = MagicMock(return_value=session)
    gateway.thread_registry = ThreadRegistry(
        session_repo=SessionRepo(db), thread_repo=ThreadRepo(db)
    )
    gateway.push_session_text = AsyncMock()
    gateway.notify_dashboard_push = AsyncMock()

    repos = MagicMock()
    repos.user_repo = UserRepo(db)
    repos.thread_message_repo = ThreadMessageRepo(db)

    service = CronDeliveryService(gateway=gateway, agent_manager=agent_manager, repos=repos)
    with pytest.raises(RuntimeError, match="tool call failed"):
        await service.deliver(
            _command(task_type="agent", prompt="记得喝水", session_key=session.session_key)
        )

    gateway.push_session_text.assert_not_awaited()
    page, _has_more = ThreadMessageRepo(db).page("thr_fail", limit=10)
    assert [row.role for row in page] == ["human", "ai"]
    assert "记得喝水" in page[0].message_json
    assert "先查一下" in page[1].message_json
    titled = ThreadRepo(db).get("thr_fail")
    assert titled is not None
    assert titled.title == "喝水提醒"
    db.close()


@pytest.mark.asyncio
async def test_telegram_cron_reloads_topic_routing_from_persisted_session(tmp_path: Path) -> None:
    from octop_gateway.models import ChannelSubject, InboundMessage

    from octop.infra.gateway.gateway import Gateway
    from octop.infra.gateway.process.message_keys import (
        sanitize_im_metadata,
        session_key_from_message,
    )

    db, _ = _seed_dashboard_thread(tmp_path, thread_id="dashboard-thread")
    sessions = SessionRepo(db)
    registry = ThreadRegistry(session_repo=sessions, thread_repo=ThreadRepo(db))
    inbound = InboundMessage(
        channel_type="telegram",
        channel_id="telegram-bot",
        content=[],
        channel_subject=ChannelSubject(subject_id="-100123", chat_type="group"),
        metadata={
            "chat_id": "-100123",
            "chat_type": "group",
            "message_thread_id": 42,
            "topic_isolation": True,
            "message_id": 999,
        },
    )
    key = session_key_from_message(inbound, agent_id="a1")
    await registry.get_or_create_by_key(
        session_key=key,
        agent_id="a1",
        user_id=1,
        channel_type="telegram",
        channel_channel_id="telegram-bot",
        channel_metadata=sanitize_im_metadata(inbound),
    )
    # Cron can create a fresh thread; routing must survive the reset and DB reload.
    await registry.reset_by_session_key(key)
    session = SessionRepo(db).get(key)
    assert session is not None
    gateway = MagicMock()
    gateway.run_in_session = _run_locked
    gateway.require_session.return_value = session
    gateway.push_session_text = AsyncMock()
    gateway.notify_dashboard_push = AsyncMock()
    service = CronDeliveryService(gateway=gateway, agent_manager=MagicMock(), repos=MagicMock())
    await service.deliver(_command(session_key=key))
    delivered_session = gateway.push_session_text.call_args.args[0]
    subject = Gateway._resolve_push_subject(gateway, delivered_session)
    assert subject.metadata["chat_id"] == "-100123"
    assert subject.metadata["message_thread_id"] == 42
    assert subject.metadata["channel_id"] == "telegram-bot"
    assert "message_id" not in subject.metadata
    db.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("channel_type", [ThreadRegistry.CHANNEL_DASHBOARD, "feishu"])
async def test_text_silent_marker_skips_delivery(channel_type: str) -> None:
    session = _session(channel_type=channel_type)
    agent_manager = MagicMock()
    gateway = MagicMock()
    gateway.run_in_session = _run_locked
    gateway.require_session = MagicMock(return_value=session)
    gateway.push_session_text = AsyncMock()
    gateway.notify_dashboard_push = AsyncMock()
    gateway.thread_registry.reset_by_session_key = AsyncMock()
    repos = MagicMock()

    service = CronDeliveryService(gateway=gateway, agent_manager=agent_manager, repos=repos)
    await service.deliver(_command(prompt="  [SILENT]\n", fresh_thread=True))

    gateway.thread_registry.reset_by_session_key.assert_not_awaited()
    agent_manager.get_agent.assert_not_called()
    repos.thread_message_repo.append_if_ready.assert_not_called()
    gateway.push_session_text.assert_not_awaited()
    gateway.notify_dashboard_push.assert_not_awaited()


@pytest.mark.asyncio
async def test_text_marker_inside_message_is_delivered() -> None:
    session = _session(channel_type="feishu")
    gateway = MagicMock()
    gateway.run_in_session = _run_locked
    gateway.require_session = MagicMock(return_value=session)
    gateway.push_session_text = AsyncMock()

    service = CronDeliveryService(gateway=gateway, agent_manager=MagicMock(), repos=MagicMock())
    await service.deliver(_command(prompt="[SILENT] is the no-change marker"))

    assert gateway.push_session_text.await_args.args[1] == "[SILENT] is the no-change marker"


@pytest.mark.asyncio
async def test_agent_silent_marker_after_thinking_skips_delivery() -> None:
    session = _session(channel_type=ThreadRegistry.CHANNEL_DASHBOARD)

    async def _stream(_aid: str, _request: dict):
        yield {"type": "token", "content": "<think>nothing changed</think>  [SI"}
        yield {"type": "token", "content": "LENT]\n"}
        yield {"type": "usage", "usage": {"input_tokens": 8, "output_tokens": 2}}

    agent_manager = MagicMock()
    agent_manager.merge_turn_mcp_servers = MagicMock(return_value=None)
    agent_manager.prepare_chat_mcp = AsyncMock(return_value=[])
    agent_manager.stream = _stream
    agent_manager.get_row = MagicMock(return_value=None)

    gateway = MagicMock()
    gateway.run_in_session = _run_locked
    gateway.require_session = MagicMock(return_value=session)
    gateway.push_session_text = AsyncMock()
    gateway.notify_dashboard_push = AsyncMock()
    repos = MagicMock()

    service = CronDeliveryService(gateway=gateway, agent_manager=agent_manager, repos=repos)
    await service.deliver(_command(task_type="agent", prompt="scan"))

    gateway.push_session_text.assert_not_awaited()
    gateway.notify_dashboard_push.assert_not_awaited()
    projected = repos.thread_message_repo.append_if_ready.call_args.args[1]
    assert any("[SILENT]" in item.message_json for item in projected)
    assert repos.usage_repo.record.call_args.kwargs["source"] == "cron"
    assert repos.usage_repo.record.call_args.kwargs["input_tokens"] == 8


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_mode", [None, "checkpoint", "rebind"])
@pytest.mark.parametrize("pinned_target", [False, True], ids=["channel", "history-pin"])
async def test_silent_agent_fresh_thread_restores_binding_and_removes_empty_thread(
    tmp_path: Path,
    failure_mode: str | None,
    pinned_target: bool,
) -> None:
    db, previous = _seed_dashboard_thread(tmp_path, thread_id="thr_previous")
    registry = ThreadRegistry(session_repo=SessionRepo(db), thread_repo=ThreadRepo(db))
    if failure_mode == "rebind":
        registry.rebind = AsyncMock(side_effect=ValueError("previous thread was deleted"))
    generated_threads: list[str] = []

    async def _stream(_aid: str, request: dict):
        generated_threads.append(request["thread_id"])
        yield {"type": "token", "content": "[SILENT]"}

    agent_manager = MagicMock()
    agent_manager.merge_turn_mcp_servers = MagicMock(return_value=None)
    agent_manager.prepare_chat_mcp = AsyncMock(return_value=[])
    agent_manager.stream = _stream
    agent_manager.get_row = MagicMock(return_value=None)
    agent_manager.delete_thread_checkpoint = AsyncMock(
        side_effect=RuntimeError("checkpoint cleanup failed")
        if failure_mode == "checkpoint"
        else None
    )

    gateway = MagicMock()
    gateway.run_in_session = _run_locked
    gateway.require_session.side_effect = lambda _aid, key: SessionRepo(db).get(key)
    gateway.thread_registry = registry
    gateway.push_session_text = AsyncMock()
    gateway.notify_dashboard_push = AsyncMock()
    repos = MagicMock()
    repos.user_repo = UserRepo(db)
    repos.thread_message_repo = ThreadMessageRepo(db)

    service = CronDeliveryService(gateway=gateway, agent_manager=agent_manager, repos=repos)
    command = _command(
        task_type="agent",
        prompt="scan",
        session_key=f"thread:{previous.thread_id}" if pinned_target else previous.session_key,
        fresh_thread=True,
    )
    if failure_mode:
        with pytest.raises((RuntimeError, ValueError)):
            await service.deliver(command)
    else:
        await service.deliver(command)

    new_thread_id = generated_threads[0]
    assert new_thread_id != previous.thread_id
    if failure_mode:
        # Keep the failed cleanup visible and bound so it can be retried.
        assert SessionRepo(db).get(previous.session_key).thread_id == new_thread_id
        assert ThreadRepo(db).get(new_thread_id) is not None
    else:
        assert SessionRepo(db).get(previous.session_key).thread_id == previous.thread_id
        assert ThreadRepo(db).get(new_thread_id) is None
    if failure_mode == "rebind":
        agent_manager.delete_thread_checkpoint.assert_not_awaited()
    else:
        agent_manager.delete_thread_checkpoint.assert_awaited_once_with(
            "a1", new_thread_id, reclaim=False
        )
    gateway.push_session_text.assert_not_awaited()
    db.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("reply", ["OK", "[SILENT] urgent alert"])
async def test_agent_non_marker_reply_is_delivered(reply: str) -> None:
    session = _session(channel_type="feishu")

    async def _stream(_aid: str, _request: dict):
        yield {"type": "token", "content": reply}

    agent_manager = MagicMock()
    agent_manager.merge_turn_mcp_servers = MagicMock(return_value=None)
    agent_manager.prepare_chat_mcp = AsyncMock(return_value=[])
    agent_manager.stream = _stream
    agent_manager.get_row = MagicMock(return_value=None)

    gateway = MagicMock()
    gateway.run_in_session = _run_locked
    gateway.require_session = MagicMock(return_value=session)
    gateway.push_session_text = AsyncMock()

    service = CronDeliveryService(gateway=gateway, agent_manager=agent_manager, repos=MagicMock())
    await service.deliver(_command(task_type="agent", prompt="scan"))

    assert gateway.push_session_text.await_args.args[1] == reply
