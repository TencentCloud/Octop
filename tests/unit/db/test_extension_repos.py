"""``repos(db)``: extension repos live on ``RepoBundle`` and follow the pool."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from tests.support.app import ensure_control_plane_bound

from octop.infra import extensions
from octop.infra.db.extension_migrations import ExtensionMigrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.services import RepoBundle
from octop.infra.server import OctopServer


class _RoomRepo:
    def __init__(self, db: Any) -> None:
        self.db = db

    def add(self, room_id: str) -> None:
        with self.db.connect() as conn:
            conn.execute("INSERT INTO demo_rooms (id) VALUES (?)", (room_id,))

    def ids(self) -> list[str]:
        with self.db.connect() as conn:
            return [r[0] for r in conn.execute("SELECT id FROM demo_rooms").fetchall()]


@pytest.fixture()
def demo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    mig = tmp_path / "demo_migrations"
    mig.mkdir()
    (mig / "001_rooms.sql").write_text(
        "CREATE TABLE IF NOT EXISTS demo_rooms (id TEXT PRIMARY KEY);\n", encoding="utf-8"
    )
    ext = SimpleNamespace(
        migrations=lambda: ExtensionMigrations("demo", mig),
        repos=lambda db: SimpleNamespace(rooms=_RoomRepo(db)),
    )
    entries = [SimpleNamespace(name="demo", load=lambda: ext)]
    monkeypatch.setattr(extensions, "entry_points", lambda group: entries)
    extensions.load_extensions.cache_clear()
    yield
    extensions.load_extensions.cache_clear()


def test_bundle_has_no_extension_repos_by_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(extensions, "entry_points", lambda group: [])
    extensions.load_extensions.cache_clear()
    try:
        bundle = RepoBundle.from_pool(SqlitePool(tmp_path / "octop.db"))
    finally:
        extensions.load_extensions.cache_clear()
    assert dict(bundle.ext) == {}
    with pytest.raises(KeyError, match="no repos registered by extension 'demo'"):
        bundle.extension("demo")


def test_repos_are_built_per_pool_and_read_only(demo: None, tmp_path: Path) -> None:
    first = SqlitePool(tmp_path / "a.db")
    second = SqlitePool(tmp_path / "b.db")
    a = RepoBundle.from_pool(first)
    b = RepoBundle.from_pool(second)
    assert a.extension("demo").rooms.db is first
    assert b.extension("demo").rooms.db is second
    with pytest.raises(TypeError):
        a.ext["other"] = object()  # type: ignore[index]


@pytest.mark.asyncio
async def test_server_services_expose_extension_repos(demo: None, tmp_path: Path) -> None:
    server = OctopServer(home=tmp_path)
    await server.start()
    await ensure_control_plane_bound(server)
    try:
        assert server.services is not None
        rooms = server.services.repos.extension("demo").rooms
        rooms.add("r1")
        assert rooms.ids() == ["r1"]
        assert rooms.db is server.services.db
    finally:
        await server.stop()
