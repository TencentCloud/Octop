"""Strong memory editing uses the owner's workspace, including stopped agents."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from deepagents.backends import FilesystemBackend
from octop_harness.backends.workspace import BackendWorkspace

from octop.api.routers.agent_files import (
    StrongMemoryBody,
    UserProfileBody,
    get_manual_memory_review,
    get_strong_memory,
    get_user_profile,
    put_strong_memory,
    put_user_profile,
    review_manual_memory,
)
from octop.infra.errors import OctopError


def _server(ws: BackendWorkspace) -> SimpleNamespace:
    row = SimpleNamespace(agent_id="a1", user_id=1, is_shared=1, last_state="stopped")

    async def save(_agent_id: str, filename: str, content: str) -> None:
        await ws.awrite_text(filename, content, force=True)

    return SimpleNamespace(
        services=SimpleNamespace(agent_repo=SimpleNamespace(get=MagicMock(return_value=row))),
        app_runtime=SimpleNamespace(
            agent_registry=SimpleNamespace(
                get_row=MagicMock(return_value=row),
                workspace_for_agent=MagicMock(return_value=ws),
                save_manual_memory_document=AsyncMock(side_effect=save),
                review_manual_memory_documents=AsyncMock(
                    return_value={
                        "status": "complete",
                        "conflicts": 1,
                        "candidate_ids": ["candidate-1"],
                    }
                ),
            )
        ),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("prefix", ["", ".octop"])
@pytest.mark.parametrize("filename", ["MEMORY.md", "USER.md"])
async def test_strong_memory_roundtrip_and_clear_for_stopped_agent(
    tmp_path: Path, prefix: str, filename: str
) -> None:
    ws = BackendWorkspace(
        FilesystemBackend(root_dir=str(tmp_path), virtual_mode=True),
        tmp_path,
        system_files_path=prefix,
    )
    server = _server(ws)
    user = SimpleNamespace(id=1, is_admin=False)
    get_file, put_file, body_type = (
        (get_strong_memory, put_strong_memory, StrongMemoryBody)
        if filename == "MEMORY.md"
        else (get_user_profile, put_user_profile, UserProfileBody)
    )
    missing = await get_file("a1", user=user, server=server)
    assert missing.content == ""
    assert missing.exists is False
    content = "# 强记忆\n\n请始终先说明结论。\n"
    saved = await put_file("a1", body_type(content=content), user=user, server=server)
    assert saved.content == content
    assert saved.exists is True
    assert ws.read_text(filename) == content
    assert (await get_file("a1", user=user, server=server)).content == content
    await put_file("a1", body_type(content=""), user=user, server=server)
    cleared = await get_file("a1", user=user, server=server)
    assert cleared.content == "" and cleared.exists is True


@pytest.mark.asyncio
@pytest.mark.parametrize("filename", ["MEMORY.md", "USER.md"])
async def test_shared_agent_does_not_allow_non_owner_to_edit_strong_memory(
    tmp_path: Path, filename: str
) -> None:
    ws = BackendWorkspace(FilesystemBackend(root_dir=str(tmp_path), virtual_mode=True), tmp_path)
    server = _server(ws)
    other_user = SimpleNamespace(id=2, is_admin=False)
    put_file, body_type = (
        (put_strong_memory, StrongMemoryBody)
        if filename == "MEMORY.md"
        else (put_user_profile, UserProfileBody)
    )
    with pytest.raises(OctopError):
        await put_file("a1", body_type(content="forbidden"), user=other_user, server=server)
    assert not ws.exists(filename)
    server.app_runtime.agent_registry.save_manual_memory_document.assert_not_awaited()


@pytest.mark.asyncio
async def test_review_is_owner_only_and_reports_candidates(tmp_path: Path) -> None:
    ws = BackendWorkspace(FilesystemBackend(root_dir=str(tmp_path), virtual_mode=True), tmp_path)
    server = _server(ws)
    with pytest.raises(OctopError):
        await review_manual_memory("a1", user=SimpleNamespace(id=2, is_admin=False), server=server)
    server.app_runtime.agent_registry.review_manual_memory_documents.assert_not_awaited()
    result = await review_manual_memory(
        "a1", user=SimpleNamespace(id=1, is_admin=False), server=server
    )
    assert result.conflicts == 1 and result.candidate_ids == ["candidate-1"]


@pytest.mark.asyncio
async def test_review_status_reads_current_files_without_running_audit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = BackendWorkspace(FilesystemBackend(root_dir=str(tmp_path), virtual_mode=True), tmp_path)
    ws.write_text("USER.md", "Current owner profile", force=True)
    server = _server(ws)
    rpc = MagicMock(return_value={"status": "stale"})
    monkeypatch.setattr("octop.api.routers.agent_files.call_memory_rpc", rpc)
    with pytest.raises(OctopError):
        await get_manual_memory_review(
            "a1", user=SimpleNamespace(id=2, is_admin=False), server=server
        )
    rpc.assert_not_called()
    result = await get_manual_memory_review(
        "a1", user=SimpleNamespace(id=1, is_admin=False), server=server
    )
    assert result.status == "stale"
    assert rpc.call_args.kwargs["method"] == "manual_document_review_status"
    assert rpc.call_args.kwargs["params"]["documents"] == {
        "USER.md": "Current owner profile",
        "MEMORY.md": "",
    }
    server.app_runtime.agent_registry.review_manual_memory_documents.assert_not_awaited()


def test_candidate_approval_supplies_current_workspace_documents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from octop.api.common.memory_client import call_memory_rpc

    ws = BackendWorkspace(FilesystemBackend(root_dir=str(tmp_path), virtual_mode=True), tmp_path)
    ws.write_text("USER.md", "Updated profile", force=True)
    server = _server(ws)
    server.app_runtime.agent_registry.memory_slim = SimpleNamespace(status=lambda _: None)
    memory = SimpleNamespace(
        get_candidate=lambda _: SimpleNamespace(payload={"manual_revision": "old"})
    )
    bridge = SimpleNamespace(handle=MagicMock(return_value={"result": {"promoted": 0}}))
    monkeypatch.setattr(
        "octop.api.common.memory_client._open_memory_for_agent", lambda *_: (memory, bridge)
    )
    call_memory_rpc(
        agent_id="a1",
        method="promote_candidate",
        params={"candidate_id": "c1"},
        user=SimpleNamespace(id=1, is_admin=False),
        as_user=None,
        server=server,
    )
    assert bridge.handle.call_args.args[0]["params"]["manual_documents"] == {
        "USER.md": "Updated profile",
        "MEMORY.md": "",
    }
