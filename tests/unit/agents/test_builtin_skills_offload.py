"""Seeding built-in skills must not walk the package tree on the event loop."""

from __future__ import annotations

import asyncio
import threading
import pytest

from octop.infra.agents import builtin_skills


class _Workspace:
    def __init__(self):
        self.uploaded: list[tuple[str, bytes]] = []

    async def amkdir(self, rel: str) -> None:
        return None

    def system_rel(self, rel: str) -> str:
        return rel

    async def aupload_many(self, pairs):
        self.uploaded.extend(pairs)
        return len(pairs)

    def __getattr__(self, name):
        async def _noop(*args, **kwargs):
            return None

        return _noop


@pytest.fixture(autouse=True)
def _stub_workspace_path(monkeypatch):
    from octop.infra.gateway.media import inbound_store

    monkeypatch.setattr(
        inbound_store, "agent_facing_workspace_path", lambda workspace, rel: f"/ws/{rel}"
    )


def test_the_scan_happens_off_the_event_loop(monkeypatch):
    seen: dict[str, int] = {}
    real_collect = builtin_skills._collect_files

    def _spy(source, prefix, out):
        seen.setdefault("scan", threading.get_ident())
        return real_collect(source, prefix, out)

    monkeypatch.setattr(builtin_skills, "_collect_files", _spy)

    async def _go():
        seen["loop"] = threading.get_ident()
        return await builtin_skills.sync_octop_builtin_skills(_Workspace())

    asyncio.run(_go())

    assert "scan" in seen, "the package tree was never walked"
    assert seen["scan"] != seen["loop"], "the package tree was walked on the event loop thread"


def test_builtin_skills_still_upload():
    workspace = _Workspace()
    names = asyncio.run(builtin_skills.sync_octop_builtin_skills(workspace))

    assert names, "no built-in skills were found"
    assert any(path.endswith("SKILL.md") for path, _ in workspace.uploaded)
