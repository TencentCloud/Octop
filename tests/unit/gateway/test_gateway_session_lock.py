"""Proactive turns must use the registered channel's inbound session lock."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from octop_gateway.channels.feishu import FeishuChannel, FeishuConfig
from octop_gateway.manager import ChannelManager
from octop_gateway.models import ChannelSubject, InboundMessage, MessageEvent, TextContent

from octop.config import OctopConfig
from octop.infra.cron.delivery import CronDeliveryService
from octop.infra.cron.manager import CronManager
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.services import build_shared_services
from octop.infra.gateway.cli import CLI_CHANNEL_ID, CliChannel
from octop.infra.gateway.gateway import Gateway
from octop.infra.gateway.threads import ThreadRegistry
from octop.infra.gateway.ws import WS_CHANNEL_ID, WebSocketChannel, WebSocketHub
from octop.infra.utils.paths import PathLayout


@pytest.fixture
def gateway(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Gateway]:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    services = build_shared_services(db=db, paths=PathLayout(tmp_path), config=OctopConfig())
    services.repos.user_repo.create(username="test", password_hash="unused", role="user")
    services.repos.agent_repo.create(agent_id="a1", user_id=1, name="Test")
    try:
        yield Gateway(agent_manager=MagicMock(), repos=services.repos)
    finally:
        db.close()


@pytest.mark.parametrize("task_type", ["text", "agent"])
async def test_fresh_cron_waits_for_already_queued_im_followup(
    gateway: Gateway, monkeypatch: pytest.MonkeyPatch, task_type: str
) -> None:
    """A fresh cron must not redirect an earlier queued follow-up to its new thread."""
    repos = gateway._repos
    user_id = 1
    registry = gateway.thread_registry
    session_key = ThreadRegistry.make_key(
        agent_id="a1", channel_type="feishu", channel_subject_id="ou_test"
    )
    old_thread = await registry.get_or_create(
        agent_id="a1",
        user_id=user_id,
        channel_type="feishu",
        channel_subject_id="ou_test",
        channel_id="ch-1",
    )
    first_entered = asyncio.Event()
    release_first = asyncio.Event()
    followup_waiting = asyncio.Event()
    routed: dict[str, str] = {}

    async def processor(message: InboundMessage):
        # Keep thread binding real; only the model response is synthetic.
        routed[message.text] = await registry.get_or_create_by_key(
            session_key=session_key,
            agent_id="a1",
            user_id=user_id,
            channel_type="feishu",
            channel_channel_id="ch-1",
        )
        if message.text == "first":
            first_entered.set()
            await release_first.wait()
        yield MessageEvent.completed()

    channel = FeishuChannel(
        processor,
        FeishuConfig(app_id="test-app", app_secret="test-secret"),
        channel_id="ch-1",
        tenant_id="a1",
    )
    channel._send_text = AsyncMock()
    inbound_key = channel.get_debounce_key

    def get_key(message: InboundMessage) -> str:
        if message.text == "followup":
            followup_waiting.set()
        return inbound_key(message)

    monkeypatch.setattr(channel, "get_debounce_key", get_key)
    manager = ChannelManager(channels={"ch-1": channel})
    gateway._channel_manager = manager
    # Start real queue workers without starting the Feishu SDK or network.
    manager._running = True
    queue: asyncio.Queue[InboundMessage] = asyncio.Queue()
    manager._queues["ch-1"] = queue
    workers = [asyncio.create_task(manager._worker_loop("ch-1")) for _ in range(2)]
    cron_task: asyncio.Task[None] | None = None

    def inbound(text: str) -> InboundMessage:
        return InboundMessage(
            channel_id="ch-1",
            channel_type="feishu",
            tenant_id="a1",
            channel_subject=ChannelSubject(subject_id="ou_test"),
            content=[TextContent(text=text)],
        )

    try:
        await queue.put(inbound("first"))
        await asyncio.wait_for(first_entered.wait(), 1)
        await queue.put(inbound("followup"))
        await asyncio.wait_for(followup_waiting.wait(), 1)
        repos.cron_repo.create(
            cron_id="j1",
            agent_id="a1",
            user_id=user_id,
            name="Reminder",
            trigger="interval:3600",
            prompt="reminder",
            session_key=session_key,
            fresh_thread=True,
            task_type=task_type,
        )

        async def stream(_agent_id, _request):
            yield {"type": "token", "content": "reminder"}

        agent_manager = MagicMock()
        agent_manager.get_row.return_value = None
        agent_manager.default_mcp_servers.return_value = []
        agent_manager.merge_turn_mcp_servers.return_value = []
        agent_manager.stream = stream
        cron = CronManager(
            gateway=gateway,
            delivery_service=CronDeliveryService(
                gateway=gateway, agent_manager=agent_manager, repos=repos
            ),
            repos=repos,
        )
        cron_task = asyncio.create_task(cron._run_user_job("j1", raise_on_error=True))
        await asyncio.sleep(0)
        assert registry.get_bound_thread_id(session_key) == old_thread
        release_first.set()
        await asyncio.wait_for(cron_task, 1)
        assert routed["followup"] == old_thread
        assert registry.get_bound_thread_id(session_key) != old_thread
        assert repos.cron_repo.get("j1").last_status == "ok"
    finally:
        release_first.set()
        if cron_task is not None:
            await asyncio.wait_for(cron_task, 1)
        manager._running = False
        for worker in workers:
            worker.cancel()
        await asyncio.gather(*workers, return_exceptions=True)


@pytest.mark.parametrize(
    ("channel_type", "channel_id", "native_key"),
    [
        ("feishu", "ch-1", "subject-1"),
        ("dashboard", WS_CHANNEL_ID, "thread:thr_original"),
        ("cli", CLI_CHANNEL_ID, "a1:cli:subject-1:dm"),
    ],
)
async def test_proactive_operation_waits_for_channel_specific_inbound_key(
    gateway: Gateway, channel_type: str, channel_id: str, native_key: str
) -> None:
    """The channel owns the key policy, including virtual per-thread/session keys."""
    session_key = ThreadRegistry.make_key(
        agent_id="a1", channel_type=channel_type, channel_subject_id="subject-1"
    )
    gateway._repos.thread_repo.insert(
        thread_id="thr_original",
        agent_id="a1",
        user_id=1,
        channel_type=channel_type,
        session_key=session_key,
    )
    gateway._repos.session_repo.upsert(
        session_key=session_key,
        agent_id="a1",
        user_id=1,
        channel_type=channel_type,
        chat_type="dm",
        thread_id="thr_original",
        channel_subject_id="subject-1",
        channel_id=channel_id,
    )
    processor = MagicMock()
    if channel_type == "feishu":
        channel = FeishuChannel(processor, FeishuConfig(), channel_id=channel_id)
    elif channel_type == "dashboard":
        channel = WebSocketChannel(processor, hub=WebSocketHub())
    else:
        channel = CliChannel(processor, hub=WebSocketHub())
    manager = ChannelManager(channels={channel_id: channel})
    gateway._channel_manager = manager
    active, release, proactive_entered = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def inbound() -> None:
        active.set()
        await release.wait()

    async def proactive() -> None:
        proactive_entered.set()

    inbound_task = asyncio.create_task(manager.run_in_session(channel_id, native_key, inbound))
    proactive_task = None
    try:
        await asyncio.wait_for(active.wait(), 1)
        proactive_task = asyncio.create_task(gateway.run_in_session("a1", session_key, proactive))
        await asyncio.sleep(0)
        assert not proactive_entered.is_set()
        release.set()
        await asyncio.wait_for(proactive_task, 1)
        assert proactive_entered.is_set()
    finally:
        release.set()
        await inbound_task
        if proactive_task is not None:
            await proactive_task


async def test_proactive_operations_keep_distinct_im_subjects_parallel(gateway: Gateway) -> None:
    """Normalizing the lock must not turn every conversation into one channel-wide lock."""
    keys = []
    for subject in ("ou_first", "ou_second"):
        await gateway.thread_registry.get_or_create(
            agent_id="a1",
            user_id=1,
            channel_type="feishu",
            channel_subject_id=subject,
            channel_id="ch-1",
        )
        keys.append(
            ThreadRegistry.make_key(
                agent_id="a1", channel_type="feishu", channel_subject_id=subject
            )
        )
    channel = FeishuChannel(MagicMock(), FeishuConfig(), channel_id="ch-1")
    gateway._channel_manager = ChannelManager(channels={"ch-1": channel})
    first_active, release, second_active = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def first() -> None:
        first_active.set()
        await release.wait()

    async def second() -> None:
        second_active.set()

    task = asyncio.create_task(gateway.run_in_session("a1", keys[0], first))
    try:
        await asyncio.wait_for(first_active.wait(), 1)
        await asyncio.wait_for(gateway.run_in_session("a1", keys[1], second), 1)
        assert second_active.is_set()
    finally:
        release.set()
        await task


async def test_cancelling_waiting_proactive_turn_keeps_inbound_lock(gateway: Gateway) -> None:
    """Cancelling a waiter must neither run it nor release the active inbound lock."""
    await gateway.thread_registry.get_or_create(
        agent_id="a1",
        user_id=1,
        channel_type="feishu",
        channel_subject_id="ou_test",
        channel_id="ch-1",
    )
    session_key = "a1:feishu:ou_test:dm"
    channel = FeishuChannel(MagicMock(), FeishuConfig(), channel_id="ch-1")
    manager = ChannelManager(channels={"ch-1": channel})
    gateway._channel_manager = manager
    active, release, cancelled_entered, next_entered = (
        asyncio.Event(),
        asyncio.Event(),
        asyncio.Event(),
        asyncio.Event(),
    )

    async def inbound() -> None:
        active.set()
        await release.wait()

    async def cancelled() -> None:
        cancelled_entered.set()

    async def next_turn() -> None:
        next_entered.set()

    inbound_task = asyncio.create_task(manager.run_in_session("ch-1", "ou_test", inbound))
    cancelled_task = None
    next_task = None
    try:
        await asyncio.wait_for(active.wait(), 1)
        cancelled_task = asyncio.create_task(gateway.run_in_session("a1", session_key, cancelled))
        await asyncio.sleep(0)
        cancelled_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await cancelled_task
        next_task = asyncio.create_task(gateway.run_in_session("a1", session_key, next_turn))
        await asyncio.sleep(0)
        assert not cancelled_entered.is_set()
        assert not next_entered.is_set()
        release.set()
        await asyncio.wait_for(next_task, 1)
        assert next_entered.is_set()
    finally:
        release.set()
        await inbound_task
        await asyncio.gather(
            *(task for task in (cancelled_task, next_task) if task is not None),
            return_exceptions=True,
        )
