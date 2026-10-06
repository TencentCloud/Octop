"""The local media fallback must not block the loop or abort the turn."""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path

import pytest

from octop.infra.gateway.media import attachment_hints as ah


class _Part:
    def __init__(self, local_path: str):
        self.local_path = local_path
        self.mime_type = "image/png"
        self.data = None


class _Backend:
    def __init__(self, local: Path):
        self._local = local
        self.read_threads: list[int] = []

    async def read(self, path: str):
        raise FileNotFoundError(path)

    def get_local_path(self, path: str) -> str:
        return str(self._local)


def _run(local: Path, tmp_path: Path):
    part = _Part("inbound/shot.png")
    backend = _Backend(local)
    seen: dict[str, int] = {}
    real_read = Path.read_bytes

    def _spy(self):
        seen["thread"] = threading.get_ident()
        return real_read(self)

    return part, backend, seen, _spy


def test_the_fallback_read_happens_off_the_event_loop(tmp_path, monkeypatch):
    local = tmp_path / "shot.png"
    local.write_bytes(b"\x89PNG")
    part, backend, seen, spy = _run(local, tmp_path)
    monkeypatch.setattr(Path, "read_bytes", spy)

    async def _go():
        seen["loop"] = threading.get_ident()
        return await ah.materialize_image_part(part, media_backend=backend, workspace=None)

    asyncio.run(_go())

    assert seen["thread"] != seen["loop"], "read_bytes ran on the event loop thread"


def test_an_unreadable_local_file_degrades_instead_of_raising(tmp_path, monkeypatch):
    local = tmp_path / "shot.png"
    local.write_bytes(b"\x89PNG")
    part, backend, _, _ = _run(local, tmp_path)

    def _boom(self):
        raise PermissionError("locked")

    monkeypatch.setattr(Path, "read_bytes", _boom)

    # The sibling branches degrade to a path hint; this one must not raise.
    result = asyncio.run(ah.materialize_image_part(part, media_backend=backend, workspace=None))

    assert result is not None
