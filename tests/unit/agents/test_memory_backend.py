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
    assert out["memory_backend"]["db_path"] == "/tmp/ws/memory.sqlite"


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
