"""Lift expert display fields out of agents.config_json."""

from __future__ import annotations

import json
from pathlib import Path

from octop.infra.agents.profile import (
    extract_profile_from_config,
    strip_profile_config,
    welcome_from_row,
)
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRow


def test_extract_profile_from_config_lifts_legacy_keys() -> None:
    profile = extract_profile_from_config(
        {
            "expert_id": "general-assistant",
            "icon_name": "zap",
            "color": "#6366f1",
            "skill_package_ids": ["PACK01", ""],
            "backend": {"type": "local_shell"},
        }
    )
    assert profile["template_name"] == "general-assistant"
    assert profile["icon_name"] == "zap"
    assert profile["color"] == "#6366f1"
    assert json.loads(profile["skill_package_ids"]) == ["PACK01"]
    assert strip_profile_config({"expert_id": "x", "backend": {"type": "local_shell"}}) == {
        "backend": {"type": "local_shell"}
    }


def test_welcome_from_row_requires_nonempty_text() -> None:
    empty = AgentRow(
        id=1,
        agent_id="a",
        user_id=1,
        name="n",
        description=None,
        persona_mbti=None,
        default_model=None,
        system_prompt=None,
        enabled=1,
        config_json="{}",
        last_state=None,
        last_error=None,
        created_at=0,
        updated_at=0,
        welcome_message="  ",
    )
    assert welcome_from_row(empty) is None
    filled = AgentRow(
        id=1,
        agent_id="a",
        user_id=1,
        name="n",
        description=None,
        persona_mbti=None,
        default_model=None,
        system_prompt=None,
        enabled=1,
        config_json="{}",
        last_state=None,
        last_error=None,
        created_at=0,
        updated_at=0,
        welcome_message="你好",
    )
    assert welcome_from_row(filled) == "你好"


def test_migration_007_backfills_profile_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "octop.db"
    pool = SqlitePool(db_path)
    with pool.connect() as conn:
        conn.executescript(
            (
                Path(__file__).resolve().parents[3]
                / "src/octop/infra/db/migrations/001_initial.sql"
            ).read_text()
        )
        conn.execute("UPDATE _schema_version SET version = 6")
        conn.execute(
            "INSERT INTO agents(agent_id, user_id, name, enabled, config_json, "
            "created_at, updated_at) VALUES (?, NULL, ?, 1, ?, 1, 1)",
            (
                "ag1",
                "bot",
                json.dumps(
                    {
                        "expert_id": "general-assistant",
                        "icon_name": "zap",
                        "icon_url": "https://cdn.example.com/a.png",
                        "color": "#6366f1",
                        "skill_package_ids": ["PACK01"],
                        "published_expert_id": "pub1",
                        "welcome_message": {"zh": "嗨", "en": "Hi"},
                        "backend": {"type": "local_shell"},
                    }
                ),
            ),
        )

    run_migrations(pool)

    with pool.connect() as conn:
        version = conn.execute("SELECT version FROM _schema_version").fetchone()[0]
        row = conn.execute("SELECT * FROM agents WHERE agent_id = ?", ("ag1",)).fetchone()
    assert version == 10
    assert row["template_name"] == "general-assistant"
    assert row["icon_name"] == "zap"
    assert row["icon_url"] == "https://cdn.example.com/a.png"
    assert row["color"] == "#6366f1"
    assert json.loads(row["skill_package_ids"]) == ["PACK01"]
    assert row["published_expert_id"] == "pub1"
    assert row["welcome_message"] == "嗨"
    cfg = json.loads(row["config_json"])
    assert "expert_id" not in cfg
    assert "icon_name" not in cfg
    assert cfg["backend"] == {"type": "local_shell"}


def test_legacy_zh_en_welcome_collapses_to_single_column(tmp_path: Path) -> None:
    db_path = tmp_path / "octop.db"
    pool = SqlitePool(db_path)
    with pool.connect() as conn:
        conn.executescript(
            (
                Path(__file__).resolve().parents[3]
                / "src/octop/infra/db/migrations/001_initial.sql"
            ).read_text()
        )
        conn.execute("ALTER TABLE agents ADD COLUMN welcome_message_zh TEXT")
        conn.execute("ALTER TABLE agents ADD COLUMN welcome_message_en TEXT")
        conn.execute(
            "INSERT INTO agents(agent_id, user_id, name, enabled, "
            "welcome_message_zh, welcome_message_en, created_at, updated_at) "
            "VALUES (?, NULL, ?, 1, ?, ?, 1, 1)",
            ("ag1", "bot", "你好", "Hi"),
        )

    run_migrations(pool)

    with pool.connect() as conn:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(agents)").fetchall()}
        row = conn.execute("SELECT * FROM agents WHERE agent_id = ?", ("ag1",)).fetchone()
    assert "welcome_message" in cols
    assert "welcome_message_zh" not in cols
    assert "welcome_message_en" not in cols
    assert row["welcome_message"] == "你好"
