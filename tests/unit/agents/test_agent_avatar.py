"""Expert avatar file helpers."""

from __future__ import annotations

import pytest
from harness_agent.backends.utils import BackendOperationNotSupportedError

from octop.infra.agents.avatar import (
    MAX_AVATAR_BYTES,
    agent_avatar_api_path,
    delete_workspace_avatar,
    display_agent_icon_url,
    read_workspace_avatar,
    sniff_avatar_media_type,
    write_workspace_avatar,
)
from octop.infra.errors import ErrorCode, OctopError

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 8


class _MemoryWorkspace:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}

    async def aupload_bytes(self, path: str, data: bytes) -> None:
        self.files[path] = data

    async def adownload_bytes(self, path: str) -> bytes | None:
        return self.files.get(path)

    async def adelete(self, path: str) -> None:
        self.files.pop(path, None)


def test_sniff_and_reject() -> None:
    assert sniff_avatar_media_type(PNG) == "image/png"
    assert sniff_avatar_media_type(JPEG) == "image/jpeg"
    with pytest.raises(OctopError) as raised:
        sniff_avatar_media_type(b"")
    assert raised.value.code is ErrorCode.AVATAR_INVALID
    with pytest.raises(OctopError) as raised:
        sniff_avatar_media_type(b"not-an-image")
    assert raised.value.code is ErrorCode.AVATAR_INVALID
    with pytest.raises(OctopError) as raised:
        sniff_avatar_media_type(b"\x89PNG\r\n\x1a\n" + b"x" * (MAX_AVATAR_BYTES + 1))
    assert raised.value.code is ErrorCode.AVATAR_TOO_LARGE


@pytest.mark.asyncio
async def test_write_read_delete_roundtrip() -> None:
    workspace = _MemoryWorkspace()
    assert await write_workspace_avatar(workspace, JPEG) == ".octop/avatar.jpg"
    found = await read_workspace_avatar(workspace)
    assert found is not None
    data, media_type = found
    assert media_type == "image/jpeg"
    assert data == JPEG
    assert workspace.files == {".octop/avatar.jpg": JPEG}
    assert agent_avatar_api_path("agent01") == "/api/agents/agent01/avatar"
    await write_workspace_avatar(workspace, PNG)
    assert set(workspace.files) == {".octop/avatar.png"}
    await delete_workspace_avatar(workspace)
    assert await read_workspace_avatar(workspace) is None


@pytest.mark.asyncio
async def test_write_skips_unsupported_mkdir() -> None:
    class _NoMkdir(_MemoryWorkspace):
        async def amkdir(self, path: str) -> None:
            raise BackendOperationNotSupportedError("mkdir", "CosBackend")

    workspace = _NoMkdir()
    assert await write_workspace_avatar(workspace, PNG) == ".octop/avatar.png"
    assert workspace.files[".octop/avatar.png"] == PNG


@pytest.mark.asyncio
async def test_read_legacy_root_avatar() -> None:
    workspace = _MemoryWorkspace()
    workspace.files["avatar.png"] = PNG
    found = await read_workspace_avatar(workspace)
    assert found is not None
    assert found[0] == PNG


def test_display_agent_icon_url_cache_busts_local_avatar() -> None:
    local = "/api/agents/agt1/avatar"
    assert display_agent_icon_url(agent_id="agt1", stored=local, updated_at=42) == f"{local}?v=42"
    assert display_agent_icon_url(agent_id="agt1", stored="https://cdn/x.png", updated_at=42) == (
        "https://cdn/x.png"
    )
