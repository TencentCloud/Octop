"""tests/unit/test_config.py"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from octop.config import load_config, parse_database_config


def test_defaults_when_missing(tmp_path: Path):
    cfg_path = tmp_path / "config.json"
    cfg = load_config(cfg_path)
    assert cfg.bind_host == "127.0.0.1"
    assert cfg.port == 8088
    assert cfg.access_token_ttl_seconds == 86400
    assert cfg.enable_dashboard is True
    assert cfg.enable_api_docs is False
    assert cfg.require_setup_password is True
    assert cfg.database.driver == "sqlite"
    assert cfg.database.sqlite_path == "octop.db"
    assert cfg.database.is_sqlite
    assert cfg.database_in_file is False
    assert cfg_path.exists()  # file written with defaults
    written = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert "password" not in written.get("database", {})


def test_loads_existing(tmp_path: Path):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({"port": 9000, "log_level": "debug"}))
    cfg = load_config(cfg_path)
    assert cfg.port == 9000
    assert cfg.log_level == "debug"
    assert cfg.bind_host == "127.0.0.1"  # default fills


def test_loads_database_section(tmp_path: Path):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(
        json.dumps(
            {
                "database": {
                    "driver": "sqlite",
                    "sqlite_path": "data/custom.db",
                }
            }
        )
    )
    cfg = load_config(cfg_path)
    assert cfg.database.sqlite_path == "data/custom.db"
    assert cfg.database_in_file is True
    assert cfg.database.resolve_sqlite_path(tmp_path) == tmp_path / "data" / "custom.db"


def test_env_overrides(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OCTOP_PORT", "7000")
    monkeypatch.setenv("OCTOP_LOG_LEVEL", "warning")
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({"port": 8088}))
    cfg = load_config(cfg_path)
    assert cfg.port == 7000
    assert cfg.log_level == "warning"


def test_database_env_sqlite_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OCTOP_DATABASE_SQLITE_PATH", "/tmp/octop-test.db")
    cfg = load_config(tmp_path / "config.json")
    assert cfg.database.sqlite_path == "/tmp/octop-test.db"
    assert cfg.database.resolve_sqlite_path(tmp_path) == Path("/tmp/octop-test.db")


def test_database_env_url_postgresql(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OCTOP_DATABASE_URL", "postgresql://alice:secret@db.example.com:5433/mydb")
    cfg = load_config(tmp_path / "config.json")
    assert cfg.database.is_postgresql
    assert cfg.database.host == "db.example.com"
    assert cfg.database.port == 5433
    assert cfg.database.database == "mydb"
    assert cfg.database.user == "alice"
    assert cfg.database.password == "secret"


def test_database_env_password_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(
        json.dumps(
            {
                "database": {
                    "driver": "postgresql",
                    "host": "localhost",
                    "database": "octop",
                    "user": "octop",
                }
            }
        )
    )
    monkeypatch.setenv("OCTOP_DATABASE_PASSWORD", "from-env")
    cfg = load_config(cfg_path)
    assert cfg.database.password == "from-env"


def test_invalid_port_falls_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OCTOP_PORT", "not-a-number")
    cfg_path = tmp_path / "config.json"
    cfg = load_config(cfg_path)
    assert cfg.port == 8088


def test_invalid_database_driver_raises(tmp_path: Path):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({"database": {"driver": "mysql"}}))
    with pytest.raises(ValueError, match="database.driver"):
        load_config(cfg_path)


def test_postgresql_missing_user_raises(tmp_path: Path):
    with pytest.raises(ValueError, match="database.user"):
        parse_database_config(
            {
                "driver": "postgresql",
                "host": "localhost",
                "database": "octop",
                "user": "",
            }
        )


def test_feature_flags_env_overrides(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OCTOP_ENABLE_DASHBOARD", "false")
    monkeypatch.setenv("OCTOP_ENABLE_API_DOCS", "true")
    monkeypatch.setenv("OCTOP_REQUIRE_SETUP_PASSWORD", "0")
    cfg = load_config(tmp_path / "config.json")
    assert cfg.enable_dashboard is False
    assert cfg.enable_api_docs is True
    assert cfg.require_setup_password is False


def test_feature_flags_from_file(tmp_path: Path):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(
        json.dumps(
            {
                "enable_dashboard": False,
                "enable_api_docs": True,
                "require_setup_password": False,
            }
        )
    )
    cfg = load_config(cfg_path)
    assert cfg.enable_dashboard is False
    assert cfg.enable_api_docs is True
    assert cfg.require_setup_password is False


def test_database_section_must_be_object(tmp_path: Path):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({"database": "sqlite"}))
    with pytest.raises(ValueError, match="config.database must be an object"):
        load_config(cfg_path)


def test_tls_defaults(tmp_path: Path):
    cfg = load_config(tmp_path / "config.json")
    assert cfg.tls.enabled is False
    assert cfg.tls.domains == []
    assert cfg.tls.http_port == 80


def test_tls_from_file(tmp_path: Path):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(
        json.dumps(
            {
                "tls": {
                    "enabled": True,
                    "mode": "letsencrypt",
                    "domains": ["a.example.com"],
                    "cert_file": "ssl/fullchain.pem",
                    "key_file": "ssl/privkey.pem",
                    "expires_at": "2030-01-01T00:00:00+00:00",
                }
            }
        )
    )
    cfg = load_config(cfg_path)
    assert cfg.tls.enabled is True
    assert cfg.tls.mode == "letsencrypt"
    assert cfg.tls.domains == ["a.example.com"]
