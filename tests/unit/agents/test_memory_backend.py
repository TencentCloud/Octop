from __future__ import annotations

from pathlib import Path

import pytest

from octop.config import DatabaseConfig, OctopConfig
from octop.infra.agents.memory_backend import (
    apply_memory_backend_choice,
    describe_memory_store,
    memory_backend_choice,
    memory_backend_from_agent_config,
    memory_config_for_choice,
    memory_postgres_connection_fields,
    memory_store_has_data,
    open_memory_kwargs,
    redact_memory_location,
)
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


def test_memory_backend_choice_omitted_is_follow() -> None:
    assert memory_backend_choice({}) == "follow"
    assert memory_backend_choice({"memory": {"extract_idle_seconds": 30}}) == "follow"


def test_memory_backend_choice_reads_type() -> None:
    assert memory_backend_choice({"memory": {"backend": {"type": "sqlite"}}}) == "sqlite"
    assert memory_backend_choice({"memory": {"backend": {"type": "postgres"}}}) == "postgres"


def test_memory_config_for_choice_follow_is_none() -> None:
    assert memory_config_for_choice("follow", OctopConfig()) is None
    assert memory_config_for_choice(None, OctopConfig()) is None


def test_memory_config_for_choice_sqlite() -> None:
    assert memory_config_for_choice("sqlite", OctopConfig()) == {"backend": {"type": "sqlite"}}


def test_memory_config_for_choice_postgres_requires_dsn_on_sqlite() -> None:
    with pytest.raises(OctopError, match="requires a DSN"):
        memory_config_for_choice("postgres", OctopConfig())


def test_memory_config_for_choice_postgres_explicit_dsn() -> None:
    out = memory_config_for_choice(
        "postgres",
        OctopConfig(),
        dsn="postgresql://octop:x@db.example:5432/mem",
    )
    assert out == {
        "backend": {"type": "postgres", "dsn": "postgresql://octop:x@db.example:5432/mem"}
    }


def test_build_memory_postgres_dsn() -> None:
    from octop.infra.agents.memory_backend import build_memory_postgres_dsn

    assert (
        build_memory_postgres_dsn(
            host="127.0.0.1",
            database="octop",
            user="octop",
            password="p@ss",
        )
        == "postgresql://octop:p%40ss@127.0.0.1:5432/octop"
    )


def test_probe_memory_postgres_dsn_unreachable() -> None:
    from octop.infra.agents.memory_backend import probe_memory_postgres_dsn

    with pytest.raises(OctopError, match="database connection failed"):
        probe_memory_postgres_dsn("postgresql://octop:x@127.0.0.1:1/octop", timeout=1)


def test_normalize_rejects_non_postgres_dsn() -> None:
    from octop.infra.agents.memory_backend import normalize_memory_dsn

    with pytest.raises(OctopError, match="postgresql://"):
        normalize_memory_dsn("mysql://localhost/db")


def test_apply_follow_keeps_extract_settings() -> None:
    cfg = {
        "memory": {
            "backend": {"type": "sqlite"},
            "extract_idle_seconds": 120,
        }
    }
    out = apply_memory_backend_choice(cfg, "follow", octop_config=OctopConfig())
    assert "backend" not in out["memory"]
    assert out["memory"]["extract_idle_seconds"] == 120


def test_apply_postgres_preserves_custom_dsn() -> None:
    cfg = OctopConfig(
        database=DatabaseConfig(
            driver="postgresql",
            host="127.0.0.1",
            database="octop",
            user="octop",
            password="x",
        )
    )
    out = apply_memory_backend_choice(
        {"memory": {"backend": {"type": "postgres", "dsn": "postgresql://a@b/c"}}},
        "postgres",
        octop_config=cfg,
    )
    assert out["memory"]["backend"] == {"type": "postgres", "dsn": "postgresql://a@b/c"}


def test_redact_memory_location_strips_password() -> None:
    assert (
        redact_memory_location(
            backend_type="postgres",
            db_path=None,
            dsn="postgresql://octop:secret@db.example:5432/octop?sslmode=require",
        )
        == "db.example:5432/octop"
    )
    assert (
        redact_memory_location(
            backend_type="sqlite",
            db_path="/tmp/ws/memory.sqlite",
            dsn=None,
        )
        == "/tmp/ws/memory.sqlite"
    )


def test_sqlite_has_data_false_when_missing(tmp_path: Path) -> None:
    has_data, unknown = memory_store_has_data(
        backend="sqlite",
        namespace="agent_a1",
        db_path=str(tmp_path / "missing.sqlite"),
    )
    assert has_data is False
    assert unknown is False


def test_sqlite_has_data_true_with_raw_event(tmp_path: Path) -> None:
    import sqlite3

    path = tmp_path / "memory.sqlite"
    con = sqlite3.connect(path)
    con.execute('CREATE TABLE "agent_a1_raw_events" (id TEXT)')
    con.execute('INSERT INTO "agent_a1_raw_events" VALUES ("e1")')
    con.commit()
    con.close()
    has_data, unknown = memory_store_has_data(
        backend="sqlite",
        namespace="agent_a1",
        db_path=str(path),
    )
    assert has_data is True
    assert unknown is False


def test_describe_memory_store_follow_sqlite(tmp_path: Path) -> None:
    status = describe_memory_store(
        agent_id="a1",
        cfg={},
        octop_config=OctopConfig(),
        workspace_dir=tmp_path,
    )
    assert status["choice"] == "follow"
    assert status["control_plane"] == "sqlite"
    assert status["resolved"]["type"] == "sqlite"
    assert status["resolved"]["namespace"] == "agent_a1"
    assert status["has_data"] is False
    assert str(tmp_path) in status["resolved"]["location"]
    assert status["connection"] is None


def test_memory_postgres_connection_fields_omits_password() -> None:
    assert memory_postgres_connection_fields(
        "postgresql://yingningchen:secret@127.0.0.1:5432/octop_test"
    ) == {
        "host": "127.0.0.1",
        "port": 5432,
        "database": "octop_test",
        "user": "yingningchen",
    }


def test_describe_memory_store_postgres_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "octop.infra.agents.memory_backend.memory_store_has_data",
        lambda **_kwargs: (False, False),
    )
    status = describe_memory_store(
        agent_id="Y61057",
        cfg={
            "memory": {
                "backend": {
                    "type": "postgres",
                    "dsn": "postgresql://yingningchen@127.0.0.1:5432/octop_test",
                }
            }
        },
        octop_config=OctopConfig(),
        workspace_dir=Path("/tmp/ws"),
    )
    assert status["choice"] == "postgres"
    assert status["resolved"]["type"] == "postgres"
    assert status["resolved"]["location"] == "127.0.0.1:5432/octop_test"
    assert status["has_custom_dsn"] is True
    assert status["connection"] == {
        "host": "127.0.0.1",
        "port": 5432,
        "database": "octop_test",
        "user": "yingningchen",
    }
