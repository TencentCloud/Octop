"""Effective captcha config — settings blob vs env snapshot."""

from __future__ import annotations

import json
from pathlib import Path

from octop.infra.auth.captcha import snapshot_env
from octop.infra.auth.captcha.store import SETTINGS_KEY, load_effective, public_config
from octop.infra.auth.sso.crypto import encrypt_secret
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.secrets import SecretRepo
from octop.infra.db.repos.settings import SettingsRepo


def _repos(tmp_path: Path) -> tuple[SettingsRepo, SecretRepo]:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    return SettingsRepo(db), SecretRepo(db)


def _put_blob(
    settings: SettingsRepo,
    secrets: SecretRepo,
    *,
    active: str,
    providers: dict[str, dict[str, str]],
) -> None:
    encoded: dict[str, dict[str, str]] = {}
    for slug, pair in providers.items():
        row: dict[str, str] = {}
        if "site_key" in pair:
            row["site_key"] = pair["site_key"]
        if "secret" in pair:
            row["secret_enc"] = encrypt_secret(secrets, pair["secret"]).decode("ascii")
        encoded[slug] = row
    settings.set(SETTINGS_KEY, json.dumps({"active": active, "providers": encoded}))


def test_no_blob_uses_slider_env(tmp_path: Path) -> None:
    settings, secrets = _repos(tmp_path)
    env = snapshot_env({})
    effective = load_effective(settings, secrets, env)
    assert public_config(effective) == {"provider": "slider"}
    assert effective.source == "env"


def test_settings_slider_beats_strong_env(tmp_path: Path) -> None:
    settings, secrets = _repos(tmp_path)
    _put_blob(settings, secrets, active="slider", providers={})
    env = snapshot_env(
        {
            "OCTOP_CAPTCHA_PROVIDER": "turnstile",
            "OCTOP_CAPTCHA_SITE_KEY": "0xenv",
            "OCTOP_CAPTCHA_SECRET": "env-secret",
        }
    )
    effective = load_effective(settings, secrets, env)
    assert public_config(effective) == {"provider": "slider"}
    assert effective.source == "settings"


def test_complete_settings_strong_wins_over_different_env(tmp_path: Path) -> None:
    settings, secrets = _repos(tmp_path)
    _put_blob(
        settings,
        secrets,
        active="hcaptcha",
        providers={"hcaptcha": {"site_key": "hc-site", "secret": "hc-secret"}},
    )
    env = snapshot_env(
        {
            "OCTOP_CAPTCHA_PROVIDER": "turnstile",
            "OCTOP_CAPTCHA_SITE_KEY": "0xenv",
            "OCTOP_CAPTCHA_SECRET": "env-secret",
        }
    )
    effective = load_effective(settings, secrets, env)
    assert public_config(effective) == {"provider": "hcaptcha", "site_key": "hc-site"}
    assert effective.secret == "hc-secret"
    assert effective.source == "settings"


def test_incomplete_pair_gap_fills_same_provider_env(tmp_path: Path) -> None:
    settings, secrets = _repos(tmp_path)
    settings.set(SETTINGS_KEY, json.dumps({"active": "turnstile", "providers": {}}))
    env = snapshot_env(
        {
            "OCTOP_CAPTCHA_PROVIDER": "turnstile",
            "OCTOP_CAPTCHA_SITE_KEY": "0xenv",
            "OCTOP_CAPTCHA_SECRET": "env-secret",
        }
    )
    effective = load_effective(settings, secrets, env)
    assert public_config(effective) == {"provider": "turnstile", "site_key": "0xenv"}
    assert effective.secret == "env-secret"
    assert effective.source == "settings"


def test_incomplete_pair_without_env_fill_degrades_to_slider(tmp_path: Path) -> None:
    settings, secrets = _repos(tmp_path)
    settings.set(SETTINGS_KEY, json.dumps({"active": "hcaptcha", "providers": {}}))
    env = snapshot_env({})
    effective = load_effective(settings, secrets, env)
    assert public_config(effective) == {"provider": "slider"}
    assert effective.source == "settings"


def test_unknown_stored_active_degrades_to_slider(tmp_path: Path) -> None:
    settings, secrets = _repos(tmp_path)
    settings.set(SETTINGS_KEY, json.dumps({"active": "not-registered", "providers": {}}))
    env = snapshot_env({})
    effective = load_effective(settings, secrets, env)
    assert public_config(effective) == {"provider": "slider"}
    assert effective.stored_active == "not-registered"


def test_unreadable_blob_falls_through_to_env(tmp_path: Path) -> None:
    settings, secrets = _repos(tmp_path)
    settings.set(SETTINGS_KEY, "{not-json")
    env = snapshot_env(
        {
            "OCTOP_CAPTCHA_PROVIDER": "turnstile",
            "OCTOP_CAPTCHA_SITE_KEY": "0xenv",
            "OCTOP_CAPTCHA_SECRET": "env-secret",
        }
    )
    effective = load_effective(settings, secrets, env)
    assert public_config(effective) == {"provider": "turnstile", "site_key": "0xenv"}
    assert effective.source == "env"
