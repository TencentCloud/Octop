"""Real HTTP + SQLite maintenance, including access and confirmation boundaries."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from langgraph.checkpoint.base import empty_checkpoint
from octop_memory import Memory


@pytest.mark.asyncio
async def test_storage_inspection_and_background_job(env_with_main_agent, monkeypatch, tmp_path):
    client, srv, auth, aid = env_with_main_agent
    registry = srv.app_runtime.agent_registry
    memory = Memory("test_storage", backend_config={"db_path": str(tmp_path / "store.sqlite")})
    cp = empty_checkpoint()
    cp["channel_values"] = {"memory_contents": {"USER.md": "preserve me" * 1000}}
    cfg = memory.put({"configurable": {"thread_id": "t", "checkpoint_ns": ""}}, cp, {}, {})
    monkeypatch.setattr(
        registry,
        "get_agent",
        lambda _: SimpleNamespace(_memory_runtime=SimpleNamespace(memory=memory)),
    )
    base = f"/api/agents/{aid}/memory/storage"
    try:
        check = await client.get(base + "/check", headers=auth)
        assert check.status_code == 200, check.text
        assert check.json()["maintenance_supported"] is True
        assert check.json()["scope"] == "agent"
        assert check.json()["elapsed_ms"] >= 0
        assert check.json()["memory_counts"][0]["table"] == "raw_events"
        assert check.json()["checkpoint_counts"][0]["rows"] == 1
        for body in ({}, {"confirmed": False}):
            denied = await client.post(base + "/maintenance", headers=auth, json=body)
            assert denied.status_code == 422
        assert registry.memory_slim.task is None
        response = await client.post(base + "/maintenance", headers=auth, json={"confirmed": True})
        assert response.status_code == 202, response.text
        await registry.memory_slim.task
        status = await client.get(base + "/maintenance", headers=auth)
        assert status.status_code == 200
        assert status.json()["job"]["phase"] == "done"
        assert status.json()["job"]["report"]["stats"]["scanned"] == 1
        assert (
            status.json()["job"]["report"]["inspection_before"]["checkpoint_counts"][0]["rows"] == 1
        )
        assert (
            status.json()["job"]["report"]["inspection_after"]["checkpoint_counts"][0]["rows"] == 1
        )
        assert memory.get_tuple(cfg).checkpoint == cp
        from octop.api.app import build_app

        schema = build_app(srv).openapi()
        assert "/api/agents/{agent_id}/memory/storage/check" in schema["paths"]
        backups = await client.get(base + "/backups", headers=auth)
        assert backups.status_code == 200
        backup_id = backups.json()[0]["backup_id"]
        for body in ({"backup_id": backup_id}, {"backup_id": backup_id, "confirmed": False}):
            assert (
                await client.post(base + "/restore", headers=auth, json=body)
            ).status_code == 422
        assert (
            await client.post(
                base + "/restore",
                headers=auth,
                json={"confirmed": True, "backup_id": "../outside.bak"},
            )
        ).status_code == 409

        async def isolated_restore(agent_id, current, operation, **kwargs):
            import asyncio

            assert agent_id == aid and current is memory
            return await asyncio.to_thread(operation)

        monkeypatch.setattr(registry, "restore_memory_store", isolated_restore)
        response = await client.post(
            base + "/restore", headers=auth, json={"confirmed": True, "backup_id": backup_id}
        )
        assert response.status_code == 202
        await registry.memory_slim.task
        status = (await client.get(base + "/maintenance", headers=auth)).json()
        assert status["job"]["phase"] == "done"
        assert status["job"]["operation"] == "restore"
        assert status["job"]["report"]["restored_backup_id"] == backup_id
        assert len((await client.get(base + "/backups", headers=auth)).json()) == 2
        entries = (await client.get(base + "/backups", headers=auth)).json()
        safety_id = next(item["backup_id"] for item in entries if item["kind"] == "before_restore")
        original_checkpoint = memory.get_tuple(cfg).checkpoint
        for body in ({"backup_id": backup_id}, {"backup_id": backup_id, "confirmed": False}):
            assert (
                await client.request("DELETE", base + "/backups", headers=auth, json=body)
            ).status_code == 422
        # Neither traversal, the active DB nor a symlink is an eligible backup.
        other_dir = tmp_path / "other-expert"
        other_dir.mkdir()
        other = other_dir / backup_id
        other.write_bytes(b"other expert backup")
        link = tmp_path / ("store.sqlite.before-slim." + "f" * 32 + ".bak")
        invalid_ids = ["../other-expert/" + backup_id, "store.sqlite"]
        try:
            link.symlink_to(other)
        except OSError:
            pass  # Windows may not grant symlink creation to the test account.
        else:
            invalid_ids.append(link.name)
        for invalid in invalid_ids:
            response = await client.request(
                "DELETE",
                base + "/backups",
                headers=auth,
                json={"confirmed": True, "backup_id": invalid},
            )
            assert response.status_code == 409
        response = await client.request(
            "DELETE",
            base + "/backups",
            headers=auth,
            json={"confirmed": True, "backup_id": backup_id},
        )
        assert response.status_code == 204
        assert not (tmp_path / backup_id).exists()
        assert (tmp_path / safety_id).exists()
        assert other.read_bytes() == b"other expert backup"
        assert memory.get_tuple(cfg).checkpoint == original_checkpoint
        assert [
            item["backup_id"] for item in (await client.get(base + "/backups", headers=auth)).json()
        ] == [safety_id]
        assert (
            await client.request(
                "DELETE",
                base + "/backups",
                headers=auth,
                json={"confirmed": True, "backup_id": backup_id},
            )
        ).status_code == 409
    finally:
        memory._checkpointer.conn.close()
        memory.backend.close()


@pytest.mark.asyncio
async def test_storage_routes_require_owner(env_alice_bob_agent):
    client, srv, _alice_auth, bob_auth, aid = env_alice_bob_agent
    base = f"/api/agents/{aid}/memory/storage"
    for suffix in ("/check", "/maintenance", "/backups"):
        response = await client.get(base + suffix, headers=bob_auth)
        assert response.status_code == 403
    response = await client.post(base + "/maintenance", headers=bob_auth, json={"confirmed": True})
    assert response.status_code == 403
    assert srv.app_runtime.agent_registry.memory_slim.task is None
    response = await client.post(
        base + "/restore", headers=bob_auth, json={"confirmed": True, "backup_id": "anything"}
    )
    assert response.status_code == 403

    response = await client.request(
        "DELETE",
        base + "/backups",
        headers=bob_auth,
        json={"confirmed": True, "backup_id": "anything"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_backup_deletion_excludes_maintenance_and_restore(
    env_with_main_agent, monkeypatch, tmp_path
):
    import asyncio
    import threading

    from octop.infra.agents.memory import sqlite_restore

    client, srv, auth, aid = env_with_main_agent
    registry = srv.app_runtime.agent_registry
    coordinator = registry.memory_slim
    memory = Memory("test_storage", backend_config={"db_path": str(tmp_path / "store.sqlite")})
    monkeypatch.setattr(
        registry,
        "get_agent",
        lambda _: SimpleNamespace(_memory_runtime=SimpleNamespace(memory=memory)),
    )
    base = f"/api/agents/{aid}/memory/storage"
    release = threading.Event()
    started = threading.Event()

    def slow_delete(*args):
        started.set()
        assert release.wait(10)

    monkeypatch.setattr(sqlite_restore, "delete_backup", slow_delete)
    deleting = asyncio.create_task(
        client.request(
            "DELETE",
            base + "/backups",
            headers=auth,
            json={"confirmed": True, "backup_id": "placeholder"},
        )
    )
    try:
        assert await asyncio.to_thread(started.wait, 5)
        assert coordinator.busy
        for method, suffix, body in (
            ("POST", "/maintenance", {"confirmed": True}),
            ("POST", "/restore", {"confirmed": True, "backup_id": "placeholder"}),
            ("DELETE", "/backups", {"confirmed": True, "backup_id": "placeholder"}),
        ):
            assert (
                await client.request(method, base + suffix, headers=auth, json=body)
            ).status_code == 409
    finally:
        release.set()
        response = await deleting
        memory._checkpointer.conn.close()
        memory.backend.close()
    assert response.status_code == 204
    assert not coordinator.busy
