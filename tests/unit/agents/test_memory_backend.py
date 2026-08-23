from __future__ import annotations

from pathlib import Path

import pytest

from octop.config import DatabaseConfig, OctopConfig
from octop.infra.agents.memory_backend import memory_backend_from_agent_config, open_memory_kwargs
from octop.infra.errors import OctopError


def test_default_memory_backend_empty_on_sqlite_control_plane() -> None:
    assert memory_backend_from_agent_config({}, octop_config=OctopConfig()) == {}


def test_default_memory_backend_follows_postgresql_control_plane() -> None:
    cfg = OctopConfig(
        database=DatabaseConfig(
            driver="postgresql",
            host="127.0.0.1",
            database="octop",
            user="octop",
            password="x",
        )
    )
    out = memory_backend_from_agent_config({}, octop_config=cfg)
    assert out["memory_backend"]["type"] == "postgres"
    assert "127.0.0.1" in out["memory_backend"]["dsn"]
    assert (
        out["memory_backend"]["dsn"].endswith("/octop") or "/octop" in out["memory_backend"]["dsn"]
    )


def test_explicit_sqlite_overrides_postgresql_control_plane() -> None:
    cfg = OctopConfig(
        database=DatabaseConfig(
            driver="postgresql",
            host="127.0.0.1",
            database="octop",
            user="octop",
            password="x",
        )
    )
    out = memory_backend_from_agent_config(
        {"memory": {"backend": {"type": "sqlite"}}},
        octop_config=cfg,
        workspace_dir=Path("/tmp/ws"),
    )
    assert out["memory_backend"]["type"] == "sqlite"
    # Compare as Path so the assertion is separator-agnostic (Windows renders
    # the db_path with backslashes; the code uses pathlib, not literal "/").
    assert Path(out["memory_backend"]["db_path"]) == Path("/tmp/ws") / "memory.sqlite"


def test_sqlite_explicit_uses_system_files_path(tmp_path: Path) -> None:
    out = memory_backend_from_agent_config(
        {"memory": {"backend": {"type": "sqlite"}}, "system_files_path": ".octop"},
        octop_config=OctopConfig(),
        workspace_dir=tmp_path,
    )
    assert Path(out["memory_backend"]["db_path"]) == tmp_path / ".octop" / "memory.sqlite"


def test_postgres_explicit_dsn() -> None:
    out = memory_backend_from_agent_config(
        {"memory": {"backend": {"type": "postgres", "dsn": "postgresql://a@b/c"}}},
        octop_config=OctopConfig(),
    )
    assert out["memory_backend"] == {"type": "postgres", "dsn": "postgresql://a@b/c"}


def test_postgres_use_control_plane_dsn() -> None:
    cfg = OctopConfig(
        database=DatabaseConfig(
            driver="postgresql",
            host="127.0.0.1",
            database="octop",
            user="octop",
            password="x",
            url="postgresql://octop:x@127.0.0.1:5432/octop?sslmode=require",
        )
    )
    out = memory_backend_from_agent_config(
        {"memory": {"backend": {"type": "postgres", "use_control_plane_dsn": True}}},
        octop_config=cfg,
    )
    assert out["memory_backend"]["type"] == "postgres"
    assert "sslmode=require" in out["memory_backend"]["dsn"]


def test_use_control_plane_dsn_requires_postgresql() -> None:
    with pytest.raises(OctopError, match="control plane"):
        memory_backend_from_agent_config(
            {"memory": {"backend": {"type": "postgres", "use_control_plane_dsn": True}}},
            octop_config=OctopConfig(),
        )


def test_open_memory_kwargs_follows_postgresql_control_plane(tmp_path: Path) -> None:
    cfg = OctopConfig(
        database=DatabaseConfig(
            driver="postgresql",
            host="127.0.0.1",
            database="octop",
            user="octop",
            password="x",
        )
    )
    ns, backend, backend_config = open_memory_kwargs(
        agent_id="a1",
        cfg={},
        octop_config=cfg,
        workspace_dir=tmp_path,
    )
    assert ns == "agent_a1"
    assert backend == "postgres"
    assert backend_config is not None
    assert "dsn" in backend_config


def test_memory_db_path_prefers_existing_nested(tmp_path: Path) -> None:
    from octop.api.common.memory_client import memory_db_path

    nested = tmp_path / ".octop" / "memory.sqlite"
    nested.parent.mkdir(parents=True)
    nested.write_text("", encoding="utf-8")
    assert memory_db_path(tmp_path) == nested


def test_memory_db_path_legacy_when_only_root_exists(tmp_path: Path) -> None:
    from octop.api.common.memory_client import memory_db_path

    root = tmp_path / "memory.sqlite"
    root.write_text("", encoding="utf-8")
    assert memory_db_path(tmp_path) == root


def test_memory_db_path_new_layout_signal_without_sqlite_yet(tmp_path: Path) -> None:
    from octop.api.common.memory_client import memory_db_path

    (tmp_path / ".octop" / "_builtin_skills").mkdir(parents=True)
    assert memory_db_path(tmp_path) == tmp_path / ".octop" / "memory.sqlite"


def test_memory_db_path_empty_octop_dir_stays_legacy(tmp_path: Path) -> None:
    from octop.api.common.memory_client import memory_db_path

    (tmp_path / ".octop").mkdir()
    assert memory_db_path(tmp_path) == tmp_path / "memory.sqlite"
