"""Durable monitoring uses separate sessions and never resubmits generation."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from mcp import types

from octop.infra.connectors import open_design_tasks as module
from octop.infra.connectors.open_design_tasks import OpenDesignTasks
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.services import RepoBundle
from octop.infra.errors import OctopError


@pytest.fixture
def services(tmp_path: Path) -> Any:
    pool = SqlitePool(tmp_path / "tasks.db")
    run_migrations(pool)
    repos = RepoBundle.from_pool(pool)
    repos.user_repo.create(username="owner", role="user")
    user = repos.user_repo.get_by_username("owner")
    assert user is not None
    repos.agent_repo.create(agent_id="a", user_id=user.id, name="Designer")
    repos.thread_repo.insert(
        thread_id="t", agent_id="a", user_id=user.id, channel_type="web", session_key="session"
    )
    instance = SimpleNamespace(instance_id="i", kind="open-design")
    service = SimpleNamespace(
        list_user_instances=lambda *a, **k: [instance],
        decrypt=lambda _: {"command": "stub", "args": [], "env": {"TOKEN": "sensitive-value"}},
    )
    yield OpenDesignTasks(service, repos), user.id, repos
    pool.close()


async def record(
    tasks: OpenDesignTasks, user: int, request: str = "request", run: str | None = "run"
) -> None:
    await tasks.register(
        user,
        "i",
        "a",
        "t",
        {
            "project": "p",
            "requestId": request,
            "runId": run,
            "status": "queued" if run else "submitting",
        },
    )


def fake_client(
    monkeypatch: pytest.MonkeyPatch, *, payload: dict[str, Any] | None = None, failure: bool = False
) -> AsyncMock:
    call = AsyncMock()

    async def invoke(name: str, arguments: dict[str, Any]) -> Any:
        await call(name, arguments)
        if failure:
            raise RuntimeError("transport sensitive-value")
        return types.CallToolResult(
            content=[],
            structuredContent=payload
            or {"status": "succeeded", "previewUrl": "http://localhost/preview"},
        )

    client = SimpleNamespace(call_tool=invoke)

    class Context:
        async def __aenter__(self) -> Any:
            return client

        async def __aexit__(self, *args: Any) -> None:
            pass

    monkeypatch.setattr(module, "_new_client", lambda _: Context())
    return call


@pytest.mark.asyncio
async def test_idempotence_restart_recovery_and_no_resubmission(
    services: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    tasks, user, repos = services
    await record(tasks, user)
    first = (await tasks.list_authorized(user, "a", "t"))[0]
    await record(tasks, user)
    assert len(await tasks.list_authorized(user, "a", "t")) == 1
    assert (await tasks.list_authorized(user, "a", "t"))[0]["task_id"] == first["task_id"]
    restored = OpenDesignTasks(tasks.service, repos)
    call = fake_client(monkeypatch)
    async with restored.watch(user, "a", "t") as queue:
        await restored.start()
        await asyncio.wait_for(queue.get(), 2)
        await restored.stop()
    result = (await restored.list_authorized(user, "a", "t"))[0]
    assert result["status"] == "succeeded"
    assert result["result"]["previewUrl"] == "http://localhost/preview"
    call.assert_awaited_once_with("get_run", {"runId": "run"})
    assert repos.open_design_task_repo.due(2**40) == []


@pytest.mark.asyncio
async def test_transient_failure_backoff_and_secret_redaction(
    services: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    tasks, user, repos = services
    await record(tasks, user)
    monkeypatch.setattr(module.time, "time", lambda: 1000)
    fake_client(monkeypatch, failure=True)
    row = repos.open_design_task_repo.due(1000)[0]
    await tasks.refresh(row)
    updated = repos.open_design_task_repo.get(row["task_id"])
    assert updated is not None
    assert updated["status"] == "unavailable" and updated["next_check"] == 1060
    await tasks.refresh(updated)
    updated = repos.open_design_task_repo.get(row["task_id"])
    assert updated is not None and updated["next_check"] == 1120
    assert "sensitive-value" not in json.dumps(updated)
    fake_client(monkeypatch, payload={"status": "failed", "error": "bad sensitive-value"})
    await tasks.refresh(updated)
    assert "sensitive-value" not in json.dumps(await tasks.list_authorized(user, "a", "t"))


@pytest.mark.asyncio
async def test_access_revoked_and_cross_user_isolation(
    services: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    tasks, user, repos = services
    await record(tasks, user)
    with pytest.raises(OctopError):
        await tasks.list_authorized(user + 1, "a", "t")
    call = fake_client(monkeypatch)
    tasks.service.list_user_instances = lambda *a, **k: []
    await tasks.refresh(repos.open_design_task_repo.due(2**40)[0])
    assert (await tasks.list_authorized(user, "a", "t"))[0]["status"] == "paused"
    call.assert_not_awaited()


@pytest.mark.asyncio
async def test_legacy_import_and_missing_run_id_do_not_submit(
    services: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    tasks, user, repos = services
    state = {"project": "p", "requestId": "old", "runId": "old-run", "status": "queued"}
    repos.settings_repo.set(f"open_design:task:{user}:i:a:t", json.dumps(state))
    tasks._import_legacy()
    tasks._import_legacy()
    assert len(await tasks.list_authorized(user, "a", "t")) == 1
    await record(tasks, user, request="unknown", run=None)
    assert len(repos.open_design_task_repo.due(2**40)) == 1
    call = fake_client(monkeypatch)
    await tasks.refresh(repos.open_design_task_repo.due(2**40)[0])
    call.assert_awaited_once_with("get_run", {"runId": "old-run"})


@pytest.mark.asyncio
async def test_global_and_per_instance_concurrency(
    services: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    tasks, user, repos = services
    instances = [SimpleNamespace(instance_id=f"i{i}", kind="open-design") for i in range(6)]
    tasks.service.list_user_instances = lambda *a, **k: instances
    tasks.service.decrypt = lambda instance: {
        "command": "stub",
        "args": [],
        "env": {"INSTANCE": instance},
    }
    active: dict[str, int] = {}
    total = peak = 0
    entered = asyncio.Event()
    release = asyncio.Event()

    class Client:
        def __init__(self, spec: dict[str, Any]) -> None:
            self.instance = spec["env"]["INSTANCE"]

        async def __aenter__(self) -> Any:
            return self

        async def __aexit__(self, *args: Any) -> None:
            pass

        async def call_tool(self, name: str, args: dict[str, Any]) -> Any:
            nonlocal total, peak
            active[self.instance] = active.get(self.instance, 0) + 1
            assert active[self.instance] == 1
            total += 1
            peak = max(peak, total)
            if total == 4:
                entered.set()
            await release.wait()
            active[self.instance] -= 1
            total -= 1
            return types.CallToolResult(content=[], structuredContent={"status": "succeeded"})

    monkeypatch.setattr(module, "_new_client", Client)
    for i in range(12):
        await tasks.register(
            user,
            f"i{i % 6}",
            "a",
            "t",
            {"project": "p", "requestId": str(i), "runId": str(i), "status": "queued"},
        )
    running = asyncio.gather(
        *(tasks.refresh(row) for row in repos.open_design_task_repo.due(2**40))
    )
    try:
        await asyncio.wait_for(entered.wait(), 2)
        assert total == 4
    finally:
        release.set()
        await running
    assert peak == 4
    assert repos.open_design_task_repo.due(2**40) == []


@pytest.mark.asyncio
async def test_history_anchors_stay_in_submission_turn_after_queries(services: Any) -> None:
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage, message_to_dict

    from octop.infra.db.repos.thread_messages import ThreadMessageInput

    tasks, user, repos = services
    messages = [
        HumanMessage(content="Generate", id="u1"),
        AIMessage(
            content="",
            id="a1-start",
            tool_calls=[{"name": "open-design__i_start_run", "args": {}, "id": "call1"}],
        ),
        ToolMessage(
            content=[{"type": "text", "text": '{"runId":"run"}'}],
            name="open-design__i_start_run",
            tool_call_id="call1",
            id="submit",
        ),
        AIMessage(content="Submitted", id="a1-final"),
        HumanMessage(content="Check again", id="u2"),
        AIMessage(
            content="",
            id="a2-check",
            tool_calls=[{"name": "open-design__i_get_run", "args": {}, "id": "call2"}],
        ),
        ToolMessage(
            content='{"runId":"run"}',
            name="open-design__i_get_run",
            tool_call_id="call2",
            id="query",
        ),
        AIMessage(content="Completed", id="a2-final"),
    ]
    repos.thread_message_repo.append_legacy_interval(
        "t",
        [
            ThreadMessageInput(message.id, message.type, json.dumps(message_to_dict(message)), 1)
            for message in messages
        ],
    )
    await record(tasks, user)
    first = (await tasks.list_authorized(user, "a", "t"))[0]
    assert first["anchor_message_ids"] == ["a1-final", "a1-start"]
    await tasks._save(repos.open_design_task_repo.get(first["task_id"]), {"status": "succeeded"})
    completed = (await tasks.list_authorized(user, "a", "t"))[0]
    assert completed["anchor_message_ids"] == first["anchor_message_ids"]


@pytest.mark.asyncio
async def test_rejected_submission_without_run_id_keeps_its_original_turn(services: Any) -> None:
    from langchain_core.messages import AIMessage, HumanMessage, message_to_dict

    from octop.infra.db.repos.thread_messages import ThreadMessageInput

    tasks, user, repos = services

    def append(messages: list[Any]) -> None:
        repos.thread_message_repo.append_legacy_interval(
            "t",
            [
                ThreadMessageInput(
                    message.id, message.type, json.dumps(message_to_dict(message)), 1
                )
                for message in messages
            ],
        )

    append([HumanMessage(content="Generate", id="u1"), AIMessage(content="Submitting", id="a1")])
    await record(tasks, user, run=None)
    first = (await tasks.list_authorized(user, "a", "t"))[0]
    row = repos.open_design_task_repo.get(first["task_id"])
    assert row is not None
    await tasks._save(row, {"status": "failed", "error": "generation_rejected"})
    append(
        [HumanMessage(content="Another question", id="u2"), AIMessage(content="Answer", id="a2")]
    )
    rejected = (await tasks.list_authorized(user, "a", "t"))[0]
    assert rejected["anchor_message_ids"] == ["a1"]
    assert "_originUserSeq" not in rejected["result"]
    # An idempotent retry does not move this task to the retry's turn.
    await record(tasks, user, run=None)
    assert (await tasks.list_authorized(user, "a", "t"))[0]["anchor_message_ids"] == ["a1"]
