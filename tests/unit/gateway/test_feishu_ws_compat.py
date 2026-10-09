"""Feishu teardown and credential probes against the SDK's real WebSocket loop."""

from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from harness_gateway.channels import feishu
from websockets.asyncio.server import serve

from octop.infra.gateway import feishu_ws_compat as compat
from octop.infra.gateway.gateway import _probe_processor


@pytest.mark.parametrize("public_stop", [False, True])
def test_patch_guard_and_idempotence(monkeypatch: pytest.MonkeyPatch, public_stop: bool) -> None:
    import lark_oapi as lark

    class Channel:
        _run_ws_thread = object()
        _stop_ws_client = object()

    original_stop = Channel._stop_ws_client
    monkeypatch.setattr(feishu, "FeishuChannel", Channel)
    if public_stop:
        monkeypatch.setattr(lark.ws.Client, "stop", lambda self: None, raising=False)
    else:
        monkeypatch.delattr(lark.ws.Client, "stop", raising=False)

    assert compat.ensure_feishu_ws_stop_fix() is (not public_stop)
    assert compat.ensure_feishu_ws_stop_fix() is False
    if public_stop:
        assert Channel._stop_ws_client is original_stop
    else:
        assert Channel._stop_ws_client is compat._fixed_stop_ws_client
        assert Channel._run_ws_thread is compat._fixed_run_ws_thread


@pytest.fixture
async def live_channel(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest):
    import lark_oapi.ws.client as sdk

    if getattr(request, "param", "default") == "legacy":
        from websockets.legacy.client import connect

        monkeypatch.setattr(sdk.websockets, "connect", connect)

    class Channel(feishu.FeishuChannel):
        _run_ws_thread = compat._fixed_run_ws_thread
        _stop_ws_client = compat._fixed_stop_ws_client

    main_loop = asyncio.get_running_loop()
    connections: asyncio.Queue[Any] = asyncio.Queue()
    messages: asyncio.Queue[bytes] = asyncio.Queue()

    async def accept(connection: Any) -> None:
        await connections.put(connection)
        await connection.wait_closed()

    async def handle_message(self: Any, message: bytes) -> None:
        main_loop.call_soon_threadsafe(messages.put_nowait, message)

    monkeypatch.setattr(sdk, "loop", sdk.loop)
    monkeypatch.setattr(sdk.Client, "_handle_message", handle_message)
    monkeypatch.setattr(feishu.FeishuChannel, "_refresh_token", AsyncMock(return_value="token"))

    async with serve(accept, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        monkeypatch.setattr(
            sdk.Client,
            "_get_conn_url",
            lambda self: f"ws://127.0.0.1:{port}/?device_id=test&service_id=1",
        )
        channel = Channel(
            _probe_processor, config=feishu.FeishuConfig(app_id="test", app_secret="test")
        )
        try:
            await channel.start()
            connection = await asyncio.wait_for(connections.get(), 3)
            await connection.send(b"ready")
            assert await asyncio.wait_for(messages.get(), 3) == b"ready"
            yield SimpleNamespace(
                channel=channel,
                connection=connection,
                connections=connections,
                messages=messages,
            )
        finally:
            await channel.stop()


async def test_probe_keeps_live_channel_receiving(live_channel: Any) -> None:
    state = live_channel
    await state.connection.send(b"before")
    assert await asyncio.wait_for(state.messages.get(), 3) == b"before"

    await compat.probe_feishu_credentials(
        {"app_id": "test", "app_secret": "test"}, _probe_processor
    )

    await state.connection.send(b"after")
    assert await asyncio.wait_for(state.messages.get(), 3) == b"after"
    assert state.connections.empty()


@pytest.mark.parametrize("live_channel", ["default", "legacy"], indirect=True)
async def test_stop_and_restart_close_socket_tasks_and_loop(
    live_channel: Any, caplog: pytest.LogCaptureFixture
) -> None:
    state = live_channel
    for _ in range(2):
        client = state.channel._ws_client
        worker = state.channel._ws_thread
        worker_loop = state.channel._ws_loop
        await state.channel.stop()
        await asyncio.wait_for(state.connection.wait_closed(), 3)

        assert not worker.is_alive()
        assert worker_loop.is_closed()
        assert not asyncio.all_tasks(worker_loop)
        assert client._auto_reconnect is False
        assert state.channel._ws_client is None
        assert state.channel._ws_thread is None
        assert state.channel._ws_loop is None
        assert state.channel._ws_session_id is None

        await state.channel.start()
        state.connection = await asyncio.wait_for(state.connections.get(), 3)
        await state.connection.send(b"restarted")
        assert await asyncio.wait_for(state.messages.get(), 3) == b"restarted"
    assert "Feishu WebSocket thread failed" not in caplog.text
    assert "Event loop stopped" not in caplog.text


@pytest.mark.parametrize("close_failure", ["timeout", "error"])
@pytest.mark.parametrize("live_channel", ["default", "legacy"], indirect=True)
async def test_failed_disconnect_aborts_socket_and_ends_worker(
    live_channel: Any,
    monkeypatch: pytest.MonkeyPatch,
    close_failure: str,
) -> None:
    state = live_channel
    worker = state.channel._ws_thread
    worker_loop = state.channel._ws_loop
    transport = state.channel._ws_client._conn.transport
    monkeypatch.setattr(compat, "_STOP_TIMEOUT_SECONDS", 0.05)

    async def fail_disconnect() -> None:
        if close_failure == "timeout":
            await asyncio.Event().wait()
        raise OSError("close failed")

    monkeypatch.setattr(state.channel._ws_client, "_disconnect", fail_disconnect)
    await state.channel.stop()
    await asyncio.wait_for(state.connection.wait_closed(), 3)

    assert transport.is_closing()
    assert not worker.is_alive()
    assert worker_loop.is_closed()
    assert not asyncio.all_tasks(worker_loop)
    assert state.channel._ws_client is None


async def test_stop_does_not_block_main_loop(
    live_channel: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = live_channel.channel._ws_client
    disconnect = client._disconnect
    main_loop = asyncio.get_running_loop()
    progressed = asyncio.Event()

    async def main_loop_work() -> None:
        progressed.set()

    async def disconnect_after_main_loop_work() -> None:
        future = asyncio.run_coroutine_threadsafe(main_loop_work(), main_loop)
        await asyncio.wrap_future(future)
        await disconnect()

    monkeypatch.setattr(client, "_disconnect", disconnect_after_main_loop_work)
    await live_channel.channel.stop()
    assert progressed.is_set()


@pytest.mark.parametrize("delayed_exit", [False, True])
async def test_stop_before_worker_initializes_loop(
    monkeypatch: pytest.MonkeyPatch, delayed_exit: bool
) -> None:
    import lark_oapi.ws.client as sdk

    original_loop = sdk.loop
    released = threading.Event()
    client = SimpleNamespace(
        _auto_reconnect=True, _conn=None, _connect=AsyncMock(), _disconnect=AsyncMock()
    )
    channel = SimpleNamespace(_ws_client=client, _running=True, _ws_session_id="test")

    def run() -> None:
        released.wait()
        compat._fixed_run_ws_thread(channel)

    worker = threading.Thread(target=run, daemon=True)
    channel._ws_thread = worker
    worker.start()
    monkeypatch.setattr(compat, "_STOP_TIMEOUT_SECONDS", 0.01)
    try:
        stop = asyncio.create_task(compat._fixed_stop_ws_client(channel))
        # Let stop() mark the channel stopped before the worker initializes its loop.
        await asyncio.sleep(0)
        if delayed_exit:
            await stop
            assert worker.is_alive()
            assert channel._ws_client is client
            assert channel._ws_thread is worker
        released.set()
        await stop
        await asyncio.get_running_loop().run_in_executor(None, worker.join, 3)
        assert not worker.is_alive()
        assert channel._ws_client is None
        assert channel._ws_loop is None
        client._connect.assert_not_awaited()
        assert sdk.loop is original_loop
    finally:
        released.set()
        await compat._fixed_stop_ws_client(channel)


@pytest.mark.parametrize("rejected", [False, True])
async def test_credential_probe_closes_http_on_success_and_failure(
    monkeypatch: pytest.MonkeyPatch, rejected: bool
) -> None:
    sessions = []

    async def refresh(channel: Any) -> str:
        sessions.append(await channel._ensure_http())
        if rejected:
            raise RuntimeError("Feishu token refresh failed: invalid credentials")
        return "token"

    monkeypatch.setattr(feishu.FeishuChannel, "_refresh_token", refresh)
    config = {"app_id": "test", "app_secret": "test"}
    if rejected:
        with pytest.raises(RuntimeError, match="invalid credentials"):
            await compat.probe_feishu_credentials(config, _probe_processor)
    else:
        await compat.probe_feishu_credentials(config, _probe_processor)
    assert len(sessions) == 1
    assert sessions[0].closed


async def test_credential_probe_rejects_missing_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from harness_gateway.channel import ChannelCredentialsError

    refresh = AsyncMock()
    monkeypatch.setattr(feishu.FeishuChannel, "_refresh_token", refresh)
    with pytest.raises(ChannelCredentialsError):
        await compat.probe_feishu_credentials({"app_id": "test"}, _probe_processor)
    refresh.assert_not_awaited()
