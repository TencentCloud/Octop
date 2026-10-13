"""Tests for `octop captcha reset` (lockout escape hatch)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from octop.cli.main import cli
from octop.cli.support.db import open_cli_services
from octop.infra.auth.captcha.config import snapshot_env
from octop.infra.auth.captcha.store import SETTINGS_KEY, load_effective


@pytest.fixture
def octop_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    return tmp_path


def _seed_blob(active: str = "recaptcha-v3") -> None:
    with open_cli_services() as services:
        services.settings_repo.set(
            SETTINGS_KEY,
            json.dumps(
                {
                    "active": active,
                    "providers": {active: {"site_key": "k", "secret_enc": ""}},
                }
            ),
        )


def test_reset_clears_stored_settings_and_falls_back_to_slider(octop_home: Path) -> None:
    _seed_blob()
    r = CliRunner().invoke(cli, ["captcha", "reset"])
    assert r.exit_code == 0, r.output
    with open_cli_services() as services:
        assert services.settings_repo.get(SETTINGS_KEY) is None
        effective = load_effective(services.settings_repo, services.secret_repo, snapshot_env({}))
    assert effective.slug == "slider"
    assert "slider" in r.output


def test_reset_is_idempotent(octop_home: Path) -> None:
    r = CliRunner().invoke(cli, ["captcha", "reset"])
    assert r.exit_code == 0, r.output
    assert "already at default" in r.output
