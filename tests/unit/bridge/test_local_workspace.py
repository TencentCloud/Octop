"""Cloud-local file tools call back to a directory on the initiator."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from octop.infra.bridge.local_workspace import (
    LocalDirectoryError,
    clear_local_workspace_state,
    file_target_metadata,
    open_local_workspace,
    peer_target_for_thread,
    register_peer_target,
    run_local_workspace_op,
    stamp_bridge_file_target,
)


@pytest.fixture(autouse=True)
def _reset() -> None:
    clear_local_workspace_state()


def test_open_creates_the_default_agent_workspace(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    target = tmp_path / "agents" / "EXPERT1"
    grant = open_local_workspace(str(target), "conn")
    assert target.is_dir()
    assert grant.directory == str(target.resolve())


def test_open_rejects_a_relative_or_missing_directory(tmp_path: Any) -> None:
    with pytest.raises(LocalDirectoryError) as relative:
        open_local_workspace("notes", "conn")
    assert relative.value.code == "relative"
    missing = tmp_path / "missing"
    with pytest.raises(LocalDirectoryError) as absent:
        open_local_workspace(str(missing), "conn")
    assert absent.value.code == "missing"


@pytest.mark.asyncio
async def test_a_different_connection_cannot_use_the_grant(tmp_path: Any) -> None:
    grant = open_local_workspace(str(tmp_path), "conn")
    assert grant.directory == str(tmp_path.resolve())
    assert open_local_workspace(str(tmp_path), "conn").token == grant.token
    await run_local_workspace_op(
        token=grant.token,
        connection_id="conn",
        op="write_file",
        args={"file_path": "notes.md", "content": "hello"},
    )
    with pytest.raises(PermissionError):
        await run_local_workspace_op(
            token=grant.token,
            connection_id="other",
            op="read_file",
            args={"file_path": "notes.md"},
        )
    read = await run_local_workspace_op(
        token=grant.token,
        connection_id="conn",
        op="read_file",
        args={"file_path": "notes.md"},
    )
    assert "hello" in read["text"]


def test_stamp_keeps_device_capabilities_and_ignores_execute_override() -> None:
    target = register_peer_target("tok2", session=object(), directory="/data", execute=True)
    request: dict[str, Any] = {}
    stamp_bridge_file_target(
        request,
        file_target_metadata(
            {
                "file_target_token": target.token,
                "local_directory": target.directory,
                "local_execute": True,
                "local_capabilities": {"contacts": True, "execute": False, "file": False},
            }
        ),
        locale="en",
        thread_id="room-2",
    )
    caps = request["configurable"]["octop_turn_capabilities"]
    assert caps["file"] is True
    assert caps["execute"] is True
    assert caps["contacts"] is True
    assert request["configurable"]["octop_team_file_execute"] == "1"


def test_stamp_remembers_the_thread_target() -> None:
    target = register_peer_target(
        "tok",
        session=object(),
        directory="/data",
        execute=True,
    )
    request: dict[str, Any] = {}
    stamp_bridge_file_target(
        request,
        file_target_metadata(
            {
                "file_target_token": target.token,
                "local_directory": target.directory,
                "local_execute": True,
            }
        ),
        locale="zh",
        thread_id="room",
    )
    cfg = request["configurable"]
    assert cfg["octop_bridge_file_target"] == "tok"
    assert cfg["octop_team_file_dir"] == "/data"
    assert cfg["octop_team_file_execute"] == "1"
    assert cfg["octop_turn_capabilities"] == {"file": True, "execute": True}
    assert "本地目录" in cfg["octop_team_dispatch_briefing"]
    assert peer_target_for_thread("room") is target


@pytest.mark.asyncio
async def test_peer_target_round_trip() -> None:
    loop = asyncio.get_running_loop()
    pending: dict[str, asyncio.Future[dict[str, Any]]] = {}

    class _Session:
        def expect_workspace_result(self, req_id: str) -> asyncio.Future[dict[str, Any]]:
            fut: asyncio.Future[dict[str, Any]] = loop.create_future()
            pending[req_id] = fut
            return fut

        def drop_workspace_waiter(self, req_id: str) -> None:
            pending.pop(req_id, None)

        async def send_json(self, payload: dict[str, Any]) -> None:
            fut = pending[str(payload["id"])]
            fut.set_result({"ok": True, "text": f"saw {payload['op']}"})

    target = register_peer_target("tok", session=_Session(), directory="/data", execute=False)
    assert await target.call_text("ls", {}) == "saw ls"
