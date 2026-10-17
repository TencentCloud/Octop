"""Seeding an expert must not read megabytes of templates on the event loop."""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path

from octop.infra.agents.experts import catalog


class _Workspace:
    def __init__(self):
        self.uploaded: list[tuple[str, bytes]] = []

    async def aupload_many(self, pairs):
        self.uploaded.extend(pairs)
        return len(pairs)


def test_seed_reads_happen_off_the_event_loop(tmp_path, monkeypatch):
    expert_dir = tmp_path / "expert"
    expert_dir.mkdir()
    (expert_dir / "persona.md").write_text("# persona", encoding="utf-8")
    (expert_dir / "manifest.json").write_text("{}", encoding="utf-8")

    seen: dict[str, int] = {}
    real_read = Path.read_bytes

    def _spy(self):
        seen.setdefault("read", threading.get_ident())
        return real_read(self)

    monkeypatch.setattr(Path, "read_bytes", _spy)
    workspace = _Workspace()

    async def _go():
        seen["loop"] = threading.get_ident()
        return await catalog.seed_expert_directory(expert_dir=expert_dir, workspace=workspace)

    count = asyncio.run(_go())

    assert count >= 1
    assert seen["read"] != seen["loop"], "templates were read on the event loop thread"


def test_seed_still_uploads_the_templates(tmp_path):
    expert_dir = tmp_path / "expert"
    expert_dir.mkdir()
    (expert_dir / "persona.md").write_text("# persona", encoding="utf-8")

    workspace = _Workspace()
    count = asyncio.run(catalog.seed_expert_directory(expert_dir=expert_dir, workspace=workspace))

    assert count == len(workspace.uploaded)
    assert any(name.endswith("persona.md") for name, _ in workspace.uploaded)
