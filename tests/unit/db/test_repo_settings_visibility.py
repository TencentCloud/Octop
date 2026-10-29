"""tests/unit/db/test_repo_settings_visibility.py — SettingsRepo expert visibility."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.settings import SettingsRepo


@pytest.fixture
def db(tmp_path: Path) -> SqlitePool:
    pool = SqlitePool(tmp_path / "x.db")
    run_migrations(pool)
    return pool


@pytest.fixture
def repo(db: SqlitePool) -> SettingsRepo:
    return SettingsRepo(db)


def test_defaults_when_unset(repo: SettingsRepo):
    # Historic behaviour: no policy row means both surfaces stay visible.
    assert repo.get_expert_visibility() == {
        "hide_builtin_experts": False,
        "hide_market": False,
    }


def test_set_get_roundtrip(repo: SettingsRepo):
    repo.set_expert_visibility(hide_builtin_experts=True, hide_market=False)
    assert repo.get_expert_visibility() == {
        "hide_builtin_experts": True,
        "hide_market": False,
    }
    repo.set_expert_visibility(hide_builtin_experts=False, hide_market=True)
    assert repo.get_expert_visibility() == {
        "hide_builtin_experts": False,
        "hide_market": True,
    }


def test_overwrite_persists_latest_value(repo: SettingsRepo):
    repo.set_expert_visibility(hide_builtin_experts=True, hide_market=True)
    repo.set_expert_visibility(hide_builtin_experts=False, hide_market=False)
    assert repo.get_expert_visibility() == {
        "hide_builtin_experts": False,
        "hide_market": False,
    }


def test_malformed_json_falls_back_to_defaults(repo: SettingsRepo, db: SqlitePool):
    repo.set("expert_visibility", "not-json{{{")
    assert repo.get_expert_visibility() == {
        "hide_builtin_experts": False,
        "hide_market": False,
    }


def test_non_dict_json_falls_back_to_defaults(repo: SettingsRepo):
    repo.set("expert_visibility", json.dumps(["hide_market"]))
    assert repo.get_expert_visibility() == {
        "hide_builtin_experts": False,
        "hide_market": False,
    }


def test_partial_dict_uses_false_for_missing_keys(repo: SettingsRepo):
    repo.set("expert_visibility", json.dumps({"hide_builtin_experts": True}))
    assert repo.get_expert_visibility() == {
        "hide_builtin_experts": True,
        "hide_market": False,
    }


def test_non_bool_values_are_coerced(repo: SettingsRepo):
    repo.set(
        "expert_visibility",
        json.dumps({"hide_builtin_experts": 1, "hide_market": "no"}),
    )
    # bool("no") is True in Python; the repo only coerces via bool(), so document it.
    assert repo.get_expert_visibility() == {
        "hide_builtin_experts": True,
        "hide_market": True,
    }
