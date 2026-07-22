"""Unit tests for Langfuse settings store."""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from unittest import mock

import pytest

from octop.infra.agents.langfuse import LangfuseSettingsStore, verify_langfuse_credentials
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.secrets import SecretRepo
from octop.infra.db.repos.settings import SettingsRepo
from octop.infra.errors import OctopError


@pytest.fixture
def store(tmp_path: Path) -> LangfuseSettingsStore:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    return LangfuseSettingsStore(settings_repo=SettingsRepo(db), secret_repo=SecretRepo(db))


def test_langfuse_settings_roundtrip(store: LangfuseSettingsStore) -> None:
    cfg = store.save(
        enabled=True,
        public_key="pk-test",
        host="http://langfuse.example",
        secret_key="sk-test",
    )
    assert cfg.enabled is True
    assert cfg.public_key == "pk-test"
    assert cfg.host == "http://langfuse.example"
    assert cfg.secret_key_set is True

    loaded = store.load()
    assert loaded.enabled is True
    assert loaded.public_key == "pk-test"
    assert loaded.configured is True


def test_langfuse_requires_secret_when_enabling(store: LangfuseSettingsStore) -> None:
    with pytest.raises(OctopError):
        store.save(enabled=True, public_key="pk", host="http://x")


def test_langfuse_harness_config(store: LangfuseSettingsStore) -> None:
    from harness_agent.observability.langfuse import LangfuseConfig

    assert store.harness_config() == LangfuseConfig(enabled=False)
    store.save(
        enabled=True,
        public_key="pk-test",
        host="http://langfuse.example",
        secret_key="sk-test",
    )
    hc = store.harness_config()
    assert isinstance(hc, LangfuseConfig)
    assert hc.enabled is True
    assert hc.public_key == "pk-test"
    assert hc.host == "http://langfuse.example"
    assert hc.secret_key == "sk-test"


def test_verify_langfuse_credentials_accepts_legacy_project_shape() -> None:
    payload = json.dumps({"data": [{"id": "proj-1", "name": "octop", "metadata": {}}]}).encode()

    class _Resp:
        status = 200

        def read(self) -> bytes:
            return payload

        def __enter__(self) -> _Resp:
            return self

        def __exit__(self, *args: object) -> None:
            return None

    def fake_urlopen(req: urllib.request.Request, timeout: float = 15) -> _Resp:
        assert req.get_method() == "GET"
        assert req.full_url.endswith("/api/public/projects")
        auth = req.headers["Authorization"]
        assert auth.startswith("Basic ")
        return _Resp()

    with mock.patch("urllib.request.urlopen", fake_urlopen):
        result = verify_langfuse_credentials("http://langfuse.example", "pk", "sk")

    assert result == {"ok": True}
