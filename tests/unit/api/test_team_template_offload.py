"""The team template preview must not read files on the event loop."""

from __future__ import annotations

import asyncio
import threading

from octop.api.routers import teams as teams_router


def test_template_reads_happen_off_the_event_loop(tmp_path, monkeypatch):
    (tmp_path / "a.md").write_text("# a", encoding="utf-8")
    (tmp_path / "b.md").write_text("# b", encoding="utf-8")
    monkeypatch.setattr(teams_router, "TEMPLATE_DIR", tmp_path)

    seen: dict[str, int] = {}
    real_iterdir = type(tmp_path).iterdir

    def _spy(self):
        seen.setdefault("walk", threading.get_ident())
        return real_iterdir(self)

    monkeypatch.setattr(type(tmp_path), "iterdir", _spy)

    async def _go():
        seen["loop"] = threading.get_ident()
        return await teams_router.team_template_files(_user=None)

    files = asyncio.run(_go())

    assert [f["name"] for f in files] == ["a.md", "b.md"]
    assert seen["walk"] != seen["loop"], "the template directory was walked on the event loop"
