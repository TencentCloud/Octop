"""QCC catalog integration with API Key and the internal HTTP aggregator."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from octop.config import OctopConfig
from octop.infra.connectors.builder import (
    build_http_mcp_spec,
    build_mcp_server_configs_for_user,
    gateway_mcp_server_names,
    validate_create_credentials,
)
from octop.infra.connectors.catalog import (
    get_catalog_entry,
    get_mcp_oauth_remote,
    is_inprocess_gateway,
    uses_internal_http_mcp,
)
from octop.infra.connectors.probe import probe_connector
from octop.infra.connectors.service import ConnectorService
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.connectors import ConnectorRepo
from octop.infra.db.repos.secrets import SecretRepo
from octop.infra.db.repos.settings import SettingsRepo


@pytest.mark.asyncio
async def test_qcc_credentials_build_and_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    entry = get_catalog_entry("qcc")
    assert entry is not None
    assert entry.mcp_mode == "internal"
    assert uses_internal_http_mcp(entry)
    assert not is_inprocess_gateway(entry)
    assert get_mcp_oauth_remote("qcc") is None
    creds = validate_create_credentials("qcc", {"api_key": "test-qcc-token"})
    assert creds["api_key"] == "test-qcc-token"
    assert creds["internal_token"]
    creds["internal_token"] = "local-gateway-token"
    spec = build_http_mcp_spec(
        entry=entry, instance_id="qcc-test", creds=creds, config=OctopConfig()
    )
    assert spec["transport"] == "http"
    assert "/api/internal/mcp/qcc/qcc-test?token=local-gateway-token" in spec["url"]
    assert "test-qcc-token" not in str(spec)
    probe = AsyncMock(return_value={"ok": True, "tools": []})
    monkeypatch.setattr("octop.infra.connectors.qcc.probe", probe)
    result = await probe_connector(entry, creds, instance_id="qcc-test", config=OctopConfig())
    assert result["ok"] is True
    probe.assert_awaited_once_with("test-qcc-token")


def test_qcc_harness_config_uses_http_not_inprocess_gateway(tmp_path: Path) -> None:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    with pool.transaction() as conn:
        conn.execute(
            "INSERT INTO users(id,username,password_hash,role,created_at) VALUES (1,'qcc','x','user',1)"
        )
    repo = ConnectorRepo(pool)
    repo.create(
        instance_id="qcc1",
        user_id=1,
        kind="qcc",
        display_name="QCC",
        mcp_server_name="qcc__qcc1",
    )
    svc = ConnectorService(
        repo=repo,
        secret_repo=SecretRepo(pool),
        settings_repo=SettingsRepo(pool),
        config=OctopConfig(),
    )
    svc.encrypt_and_store(instance_id="qcc1", payload={"api_key": "k", "internal_token": "tok"})
    configs = build_mcp_server_configs_for_user(
        svc=svc,
        connector_repo=repo,
        user_id=1,
        agent_id="agent",
        agent_user_id=1,
        config=OctopConfig(),
        log=False,
    )
    spec = configs["qcc__qcc1"]
    assert spec.get("transport") == "http"
    assert "/api/internal/mcp/qcc/qcc1?token=tok" in spec["url"]
    assert "qcc__qcc1" not in gateway_mcp_server_names(connector_repo=repo, user_id=1)
