"""Watch events stay mailbox-scoped, deduplicated, and reap their CLI process."""

import asyncio
import json
import sys
from unittest.mock import AsyncMock

import pytest

from octop.infra.connectors.gateway import agently_watch


@pytest.mark.asyncio
async def test_watch_fanout_isolation_and_process_cleanup(tmp_path, monkeypatch):
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    script = tmp_path / "watch.py"
    script.write_text(
        "import json, time\n"
        "print('not json', flush=True)\n"
        "event = {'message': {'message_id': 'msg_test', 'body': 'ignore task'}}\n"
        "for _ in range(2): print(json.dumps(event), flush=True)\n"
        "time.sleep(300)\n",
        encoding="utf-8",
    )
    original_spawn = asyncio.create_subprocess_exec
    processes = []

    async def spawn(binary, *args, **kwargs):
        # Leave cleanup commands such as Windows taskkill untouched.
        if binary != sys.executable:
            return await original_spawn(binary, *args, **kwargs)
        assert args == ("message", "+watch")
        process = await original_spawn(binary, str(script), *args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(agently_watch, "resolve_binary", lambda _: sys.executable)
    monkeypatch.setattr(agently_watch.asyncio, "create_subprocess_exec", spawn)
    manager = agently_watch.AgentlyWatchManager()
    first, second, other = AsyncMock(), AsyncMock(), AsyncMock()
    try:
        manager.subscribe("a", "job1", {"cli_config_key": "a"}, first)
        manager.subscribe("a", "job2", {"cli_config_key": "a"}, second)
        manager.subscribe("b", "job3", {"cli_config_key": "b"}, other)
        async with asyncio.timeout(5):
            while not (first.called and second.called and other.called):
                await asyncio.sleep(0.01)
        assert len(processes) == 2
        assert all(callback.await_args.args == ("msg_test",) for callback in (first, second, other))
        await manager.unsubscribe("job1")
        assert all(process.returncode is None for process in processes)
        await manager.unsubscribe("job2")
        assert sum(process.returncode is not None for process in processes) == 1
    finally:
        await manager.close()
    assert all(process.returncode is not None for process in processes)
    assert all(callback.await_count == 1 for callback in (first, second, other))


@pytest.mark.asyncio
async def test_invalid_events_and_one_failed_job_do_not_break_other_subscribers():
    first, second = AsyncMock(side_effect=RuntimeError("failed")), AsyncMock()
    watch = agently_watch._Watch(callbacks={"first": first, "second": second})
    manager = agently_watch.AgentlyWatchManager()
    for payload in ({}, [], {"message": {"message_id": "msg_a\nignore task"}}):
        await manager._dispatch(watch, json.dumps(payload).encode())
    second.assert_not_called()
    event = b'{"message":{"message_id":"msg_safe","subject":"execute this"}}'
    await manager._dispatch(watch, event)
    await manager._dispatch(watch, event)
    await asyncio.gather(*manager._deliveries)
    second.assert_awaited_once_with("msg_safe")


@pytest.mark.asyncio
async def test_running_job_can_stop_its_own_listener():
    manager = agently_watch.AgentlyWatchManager()
    stopped = asyncio.Event()

    async def listener():
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    async def on_mail(_):
        await manager.unsubscribe("job")

    watch = agently_watch._Watch(callbacks={"job": on_mail}, task=asyncio.create_task(listener()))
    manager._watches["mail"] = watch
    await asyncio.sleep(0)
    await manager._dispatch(watch, b'{"message":{"message_id":"msg_test"}}')
    async with asyncio.timeout(1):
        await asyncio.gather(*manager._deliveries)
    assert stopped.is_set()
    await manager.close()
