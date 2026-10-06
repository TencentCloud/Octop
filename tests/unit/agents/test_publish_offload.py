"""Publishing a snapshot must not write the workspace on the event loop."""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path

from octop.infra.agents.experts import publish


class _Workspace:
    def __init__(self, files):
        self._files = files

    async def aiter_files(self, *args, **kwargs):
        for name in self._files:
            yield name

    async def adownload_bytes(self, rel):
        return self._files.get(rel)

    async def aread_text(self, rel):
        return None

    def __getattr__(self, name):
        async def _noop(*args, **kwargs):
            return None

        return _noop


def test_the_snapshot_files_are_written_off_the_event_loop(tmp_path, monkeypatch):
    files = {"persona.md": b"# persona", "manifest.json": json.dumps({"name": "demo"}).encode()}
    workspace = _Workspace(files)
    monkeypatch.setattr(publish, "_workspace_file_paths", lambda ws: _paths(files))

    seen: dict[str, int] = {}
    real = Path.write_bytes

    def _spy(self, content):
        seen.setdefault("threads", set()).add(threading.get_ident())
        return real(self, content)

    monkeypatch.setattr(Path, "write_bytes", _spy)

    async def _go():
        seen["loop"] = threading.get_ident()
        return await publish.export_agent_workspace_to_dir(
            workspace=workspace, dest=tmp_path / "snapshot"
        )

    exported = asyncio.run(_go())

    assert exported
    threads = seen["threads"]
    assert threads, "no snapshot file was written"
    # Every write has to happen off the loop, not just the first one.
    assert seen["loop"] not in threads, "a snapshot file was written on the event loop thread"


async def _paths(files):
    return list(files)
