"""Database credentials survive setup payload parsing and config persistence."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from psycopg.conninfo import conninfo_to_dict

from octop.config import load_config
from octop.infra.db.rebind import database_config_from_payload, persist_database_config


@pytest.mark.parametrize("query", ["", "?sslmode=require&application_name=h09"])
@pytest.mark.parametrize(
    ("auth", "user", "password"),
    [
        ("alice:secret", "alice", "secret"),
        ("db%20user:my%20pass", "db user", "my pass"),
        ("db+user:pass+word", "db+user", "pass+word"),
        ("db%40user:pass%40word", "db@user", "pass@word"),
        ("db%25user:pass%25word", "db%user", "pass%word"),
        ("db%2Fuser:pass%2Fword", "db/user", "pass/word"),
        ("%E7%94%A8%E6%88%B7:%E5%AF%86%E7%A0%81", "用户", "密码"),
        ("db%2540user:pass%2540word", "db%40user", "pass%40word"),
        ("alice", "alice", None),
        ("alice:", "alice", None),
    ],
)
def test_postgresql_url_credentials_survive_persistence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    auth: str,
    user: str,
    password: str | None,
    query: str,
) -> None:
    for key in list(os.environ):
        if key.startswith("OCTOP_DATABASE_"):
            monkeypatch.delenv(key)
    url = f"postgresql://{auth}@db.example.com:5433/mydb{query}"
    configured = database_config_from_payload({"url": url})
    assert configured.postgresql_conninfo() == url

    config_path = tmp_path / "config.json"
    persist_database_config(config_path, configured)
    stored = json.loads(config_path.read_text(encoding="utf-8"))["database"]
    assert stored["user"] == user
    assert stored.get("password") == password
    assert stored.get("url") == (url if query else None)

    reloaded = load_config(config_path).database
    info = conninfo_to_dict(reloaded.postgresql_conninfo())
    assert info["user"] == user
    assert info.get("password") == password
    assert info["host"] == "db.example.com"
    assert info["port"] == "5433"
    assert info["dbname"] == "mydb"
    if query:
        assert reloaded.postgresql_conninfo() == url
        assert info["sslmode"] == "require"
        assert info["application_name"] == "h09"
