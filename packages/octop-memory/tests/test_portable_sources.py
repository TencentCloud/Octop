"""Discover Agent stores under current paths or an explicit migration path."""

from pathlib import Path

import pytest

from octop_memory import Memory
from octop_memory.operations.migration.portable.sources import list_sources


@pytest.fixture()
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    def expanduser(path: Path) -> Path:
        text = str(path)
        return tmp_path / text[2:] if text.startswith("~/") else path

    monkeypatch.setattr(Path, "expanduser", expanduser)
    return tmp_path


@pytest.mark.parametrize("location", [".octop/agents", ".octop-harness"])
def test_list_sources_discovers_agent_stores(isolated_home: Path, location: str) -> None:
    db_path = isolated_home / location / "demo" / "memory.sqlite"
    db_path.parent.mkdir(parents=True)
    memory = Memory("demo", backend_config={"db_path": str(db_path)})
    memory.store("User prefers Python", topic="preferences")

    sources = list_sources()

    assert len(sources) == 1
    source = sources[0]
    assert source.db_path == str(db_path)
    assert source.host_kind == "agent"
    assert source.agent_name == "demo"
    assert source.namespace == "demo"
    assert source.atom_count == 1
    assert memory.recall("Python")


def test_list_sources_accepts_explicit_previous_location(isolated_home: Path) -> None:
    db_path = isolated_home / "previous-install" / "demo" / "memory.sqlite"
    db_path.parent.mkdir(parents=True)
    memory = Memory("demo", backend_config={"db_path": str(db_path)})
    memory.store("User prefers Python", topic="preferences")

    assert list_sources() == []
    pattern = str(isolated_home / "previous-install" / "*" / "memory.sqlite")
    sources = list_sources(extra_paths=[("agent", pattern)])

    assert len(sources) == 1
    assert sources[0].db_path == str(db_path)
    assert sources[0].host_kind == "agent"
    assert sources[0].atom_count == 1
    assert db_path.exists()
    assert memory.recall("Python")
