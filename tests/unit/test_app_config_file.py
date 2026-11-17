"""config.json admin editor: merge, redact, and reject invalid documents."""

from __future__ import annotations

import json

import pytest

from octop.infra.app_config import read_app_config, save_raw_config, save_structured_config
from octop.infra.errors import ErrorCode, OctopError


def _body(**overrides: object) -> dict:
    database = {
        "driver": "sqlite",
        "sqlite_path": "octop.db",
        "host": "127.0.0.1",
        "port": 5432,
        "database": "octop",
        "user": "octop",
        "password": None,
        "url": None,
    }
    tls = {
        "enabled": False,
        "mode": "",
        "domains": [],
        "cert_file": "",
        "key_file": "",
        "issued_at": "",
        "expires_at": "",
        "acme_staging": False,
        "http_port": 80,
    }
    body = {
        "bind_host": "127.0.0.1",
        "port": 8088,
        "log_level": "info",
        "access_token_ttl_seconds": 86400,
        "login_max_attempts": 5,
        "login_lockout_seconds": 900,
        "cors_origins": [],
        "default_timezone": "Asia/Shanghai",
        "enable_dashboard": True,
        "enable_api_docs": False,
        "require_setup_password": True,
        "max_upload_mb": 100,
        "database": database,
        "tls": tls,
    }
    body.update(overrides)
    return body


def test_structured_save_keeps_unknown_keys_and_password(tmp_path) -> None:
    path = tmp_path / "config.json"
    secret = "super-secret-db-password"
    path.write_text(
        json.dumps(
            {
                "port": 8088,
                "plugins": {"demo": {"enabled": False}},
                "bundled_plugins_seeded": ["demo"],
                "database": {
                    "driver": "postgresql",
                    "host": "db.internal",
                    "port": 5432,
                    "database": "octop",
                    "user": "octop",
                    "password": secret,
                },
            }
        ),
        encoding="utf-8",
    )
    body = _body()
    body["database"] = {
        **body["database"],
        "driver": "postgresql",
        "host": "db.internal",
        "password": None,
    }
    body["port"] = 9090
    save_structured_config(path, body)

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["plugins"] == {"demo": {"enabled": False}}
    assert saved["bundled_plugins_seeded"] == ["demo"]
    assert saved["port"] == 9090
    assert saved["database"]["password"] == secret

    view = read_app_config(path)
    assert view.valid is True
    assert view.config is not None
    assert view.config["database"]["password"] is None
    assert view.has_database_password is True
    assert secret in view.raw
    assert secret not in json.dumps(view.config)


def test_clear_and_replace_database_password(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "database": {
                    "driver": "postgresql",
                    "host": "127.0.0.1",
                    "port": 5432,
                    "database": "octop",
                    "user": "octop",
                    "password": "old",
                }
            }
        ),
        encoding="utf-8",
    )
    body = _body()
    body["database"] = {**body["database"], "driver": "postgresql", "password": ""}
    save_structured_config(path, body)
    assert "password" not in json.loads(path.read_text(encoding="utf-8"))["database"]

    body["database"] = {**body["database"], "password": "next"}
    save_structured_config(path, body)
    assert json.loads(path.read_text(encoding="utf-8"))["database"]["password"] == "next"


def test_database_url_replaces_discrete_fields(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text("{}", encoding="utf-8")
    body = _body()
    body["database"] = {
        **body["database"],
        "driver": "postgresql",
        "url": "postgresql://app:s3cret@db.example:5433/octop?sslmode=require",
    }
    save_structured_config(path, body)
    saved = json.loads(path.read_text(encoding="utf-8"))["database"]
    assert saved["host"] == "db.example"
    assert saved["port"] == 5433
    assert saved["user"] == "app"
    assert saved["password"] == "s3cret"
    assert saved["url"].endswith("sslmode=require")


def test_invalid_save_does_not_change_the_file(tmp_path) -> None:
    path = tmp_path / "config.json"
    original = json.dumps({"port": 8088, "plugins": {"demo": {"enabled": True}}})
    path.write_text(original, encoding="utf-8")
    body = _body(port=70000)
    with pytest.raises(OctopError) as exc:
        save_structured_config(path, body)
    assert exc.value.code is ErrorCode.APP_CONFIG_INVALID
    assert "70000" not in str(exc.value) or "port" in str(exc.value)
    assert path.read_text(encoding="utf-8") == original


def test_raw_save_rejects_invalid_json_and_keeps_extra_keys(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(OctopError) as exc:
        save_raw_config(path, "{")
    assert exc.value.code is ErrorCode.APP_CONFIG_INVALID
    assert path.read_text(encoding="utf-8") == "{}\n"

    save_raw_config(
        path,
        json.dumps({"port": 8088, "plugins": {"demo": {"enabled": True}}, "log_level": "debug"}),
    )
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["plugins"]["demo"]["enabled"] is True
    assert saved["log_level"] == "debug"


def test_corrupt_file_is_not_replaced_by_a_form_save(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text("{ not json", encoding="utf-8")
    view = read_app_config(path)
    assert view.valid is False
    assert view.config is None
    with pytest.raises(OctopError) as exc:
        save_structured_config(path, _body())
    assert exc.value.code is ErrorCode.CONFIG_FILE_CORRUPT
    assert path.read_text(encoding="utf-8") == "{ not json"


def test_env_override_and_restart_flag(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OCTOP_PORT", "9091")
    monkeypatch.delenv("OCTOP_SERVICE_MODE", raising=False)
    monkeypatch.delenv("OCTOP_DESKTOP", raising=False)
    monkeypatch.delenv("OCTOP_DESKTOP_SHELL", raising=False)
    monkeypatch.delenv("OCTOP_GREEN_PACKAGES", raising=False)
    view = read_app_config(tmp_path / "missing.json")
    assert "OCTOP_PORT" in view.overrides
    assert view.restart_available is False

    monkeypatch.setenv("OCTOP_SERVICE_MODE", "systemd")
    view = read_app_config(tmp_path / "missing.json")
    assert view.service_mode == "systemd"
    assert view.restart_available is True
