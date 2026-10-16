"""Strong memory editing uses the owner's workspace, including stopped agents."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from deepagents.backends import FilesystemBackend
from octop_harness.backends.workspace import BackendWorkspace

from octop.api.routers.agent_files import StrongMemoryBody, get_strong_memory, put_strong_memory
from octop.infra.errors import OctopError


def _server(ws: BackendWorkspace) -> SimpleNamespace:
    row = SimpleNamespace(agent_id="a1", user_id=1, is_shared=1, last_state="stopped")
    return SimpleNamespace(
        services=SimpleNamespace(agent_repo=SimpleNamespace(get=MagicMock(return_value=row))),
        app_runtime=SimpleNamespace(
            agent_registry=SimpleNamespace(
                get_row=MagicMock(return_value=row),
                workspace_for_agent=MagicMock(return_value=ws),
            )
        ),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("prefix", ["", ".octop"])
async def test_strong_memory_roundtrip_and_clear_for_stopped_agent(
    tmp_path: Path, prefix: str
) -> None:
    ws = BackendWorkspace(
        FilesystemBackend(root_dir=str(tmp_path), virtual_mode=True),
        tmp_path,
        system_files_path=prefix,
    )
    server = _server(ws)
    user = SimpleNamespace(id=1, is_admin=False)
    missing = await get_strong_memory("a1", user=user, server=server)
    assert missing.content == ""
    assert missing.exists is False
    content = "# 强记忆\n\n请始终先说明结论。\n"
    saved = await put_strong_memory(
        "a1", StrongMemoryBody(content=content), user=user, server=server
    )
    assert saved.content == content
    assert saved.exists is True
    assert ws.read_text("MEMORY.md") == content
    assert (await get_strong_memory("a1", user=user, server=server)).content == content
    await put_strong_memory("a1", StrongMemoryBody(content=""), user=user, server=server)
    cleared = await get_strong_memory("a1", user=user, server=server)
    assert cleared.content == "" and cleared.exists is True


@pytest.mark.asyncio
async def test_shared_agent_does_not_allow_non_owner_to_edit_strong_memory(tmp_path: Path) -> None:
    ws = BackendWorkspace(FilesystemBackend(root_dir=str(tmp_path), virtual_mode=True), tmp_path)
    server = _server(ws)
    other_user = SimpleNamespace(id=2, is_admin=False)
    with pytest.raises(OctopError):
        await put_strong_memory(
            "a1", StrongMemoryBody(content="forbidden"), user=other_user, server=server
        )
    assert not ws.exists("MEMORY.md")
