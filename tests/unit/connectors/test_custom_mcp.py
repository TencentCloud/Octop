"""Unit tests for custom MCP validation and assembly."""

from __future__ import annotations

from pathlib import Path

import pytest

from octop.config import OctopConfig
from octop.infra.connectors.builder import build_mcp_server_configs_for_user, mcp_server_name
from octop.infra.connectors.custom_mcp import (
    CUSTOM_MCP_KIND,
    enabled_harness_configs,
    extract_servers,
    harness_spec_for_server,
    normalize_server_spec,
    validate_servers_map,
)
from octop.infra.connectors.service import ConnectorService
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import DBPool
from octop.infra.db.repos.connectors import ConnectorRepo
from octop.infra.db.repos.secrets import SecretRepo
from octop.infra.db.repos.settings import SettingsRepo
from octop.infra.utils.ulid import new_ulid


@pytest.fixture
def db(tmp_path: Path) -> DBPool:
    pool = DBPool(tmp_path / "octop.db")
    run_migrations(pool)
    return pool


@pytest.fixture
def svc(db: DBPool) -> ConnectorService:
    return ConnectorService(
        repo=ConnectorRepo(db),
        secret_repo=SecretRepo(db),
        settings_repo=SettingsRepo(db),
        config=OctopConfig(),
    )


def _ensure_user(db: DBPool) -> int:
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO users(username, password_hash, role, created_at) "
            "VALUES ('u1', 'x', 'user', 1)"
        )
        row = conn.execute("SELECT id FROM users WHERE username = 'u1'").fetchone()
    assert row is not None
    return int(row["id"])


def test_normalize_streamable_http_and_stdio():
    http = normalize_server_spec(
        "deepwiki",
        {
            "transport": "streamable_http",
            "url": "https://mcp.deepwiki.com/mcp",
            "headers": {"Authorization": "Bearer t"},
        },
    )
    assert http["transport"] == "streamable_http"
    assert http["url"] == "https://mcp.deepwiki.com/mcp"
    assert http["headers"]["Authorization"] == "Bearer t"
    assert http["enabled"] is True

    stdio = normalize_server_spec(
        "local",
        {
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "pkg"],
            "enabled": False,
        },
    )
    assert stdio["transport"] == "stdio"
    assert stdio["command"] == "npx"
    assert stdio["args"] == ["-y", "pkg"]
    assert stdio["enabled"] is False


def test_rejects_http_scheme_and_private_host():
    with pytest.raises(ValueError, match="https"):
        normalize_server_spec(
            "bad",
            {"transport": "streamable_http", "url": "http://example.com/mcp"},
        )
    with pytest.raises(ValueError, match="private|not allowed|blocked"):
        normalize_server_spec(
            "bad",
            {"transport": "streamable_http", "url": "https://10.0.0.1/mcp"},
        )


def test_allows_loopback_http_and_https():
    for url in (
        "http://localhost:8080/mcp",
        "https://127.0.0.1/mcp",
        "http://[::1]/mcp",
    ):
        spec = normalize_server_spec(
            "local",
            {"transport": "streamable_http", "url": url},
        )
        assert spec["url"] == url


def test_validate_servers_map_reserved_and_duplicate():
    with pytest.raises(ValueError, match="conflicts"):
        validate_servers_map(
            {"taken": {"transport": "stdio", "command": "x"}},
            reserved_names={"taken"},
        )
    with pytest.raises(ValueError, match="invalid server name"):
        validate_servers_map({"bad name": {"transport": "stdio", "command": "x"}})


def test_enabled_harness_configs_filters_disabled():
    servers = validate_servers_map(
        {
            "on": {
                "transport": "streamable_http",
                "url": "https://mcp.example.com/mcp",
            },
            "off": {
                "transport": "stdio",
                "command": "npx",
                "enabled": False,
            },
        }
    )
    configs = enabled_harness_configs(servers)
    assert set(configs) == {"on"}
    assert "enabled" not in configs["on"]
    assert configs["on"]["transport"] == "streamable_http"


def test_harness_spec_stdio_default_args():
    spec = harness_spec_for_server({"transport": "stdio", "command": "uvx", "enabled": True})
    assert spec["args"] == []
    assert "enabled" not in spec


def test_harness_spec_streamable_http_adds_accept():
    spec = harness_spec_for_server(
        {
            "transport": "streamable_http",
            "url": "https://mcp.example.com/mcp",
            "headers": {"Authorization": "Bearer x"},
            "enabled": True,
        }
    )
    assert spec["headers"]["Authorization"] == "Bearer x"
    assert spec["headers"]["Accept"] == "application/json, text/event-stream"
    assert "enabled" not in spec


def test_put_and_expand_custom_mcp(svc: ConnectorService, db: DBPool):
    uid = _ensure_user(db)
    servers = svc.put_custom_servers(
        uid,
        {
            "deepwiki": {
                "transport": "streamable_http",
                "url": "https://mcp.deepwiki.com/mcp",
            },
            "local": {
                "transport": "stdio",
                "command": "npx",
                "args": ["-y", "x"],
                "enabled": False,
            },
        },
    )
    assert set(servers) == {"deepwiki", "local"}
    assert extract_servers(
        svc.decrypt(svc._repo.get_by_user_kind(uid, CUSTOM_MCP_KIND).instance_id)
    )  # noqa: SLF001

    listed = svc.list_instances_for_api(uid)
    assert len(listed) == 2
    by_name = {row["mcp_server_name"]: row for row in listed}
    assert by_name["deepwiki"]["status"] == "active"
    assert by_name["local"]["status"] == "disabled"
    assert by_name["deepwiki"]["instance_id"] == "custom:deepwiki"

    active = svc.list_active_mcp_server_names(uid)
    assert active == ["deepwiki"]

    svc.patch_custom_server_enabled(uid, "local", enabled=True)
    assert set(svc.list_active_mcp_server_names(uid)) == {"deepwiki", "local"}


def test_put_empty_servers_deletes_parent_row(svc: ConnectorService, db: DBPool):
    uid = _ensure_user(db)
    svc.put_custom_servers(
        uid,
        {
            "only": {
                "transport": "stdio",
                "command": "npx",
            },
        },
    )
    assert svc._repo.get_by_user_kind(uid, CUSTOM_MCP_KIND) is not None  # noqa: SLF001
    assert svc.put_custom_servers(uid, {}) == {}
    assert svc._repo.get_by_user_kind(uid, CUSTOM_MCP_KIND) is None  # noqa: SLF001
    assert svc.list_instances_for_api(uid) == []


def test_build_mcp_configs_merges_enabled_custom(svc: ConnectorService, db: DBPool):
    uid = _ensure_user(db)
    # Built-in-style row that catalog would skip if unknown — use real catalog kind optional.
    # Only custom servers here.
    svc.put_custom_servers(
        uid,
        {
            "a": {
                "transport": "streamable_http",
                "url": "https://mcp.example.com/a",
            },
            "b": {
                "transport": "stdio",
                "command": "npx",
                "enabled": False,
            },
        },
    )
    configs = build_mcp_server_configs_for_user(
        svc=svc,
        connector_repo=svc._repo,  # noqa: SLF001
        user_id=uid,
        agent_id="agent-1",
        agent_user_id=uid,
        config=OctopConfig(),
        log=False,
    )
    assert set(configs) == {"a"}
    # Custom MCP is deferred (placeholder) until prepare_chat_mcp.
    assert configs["a"] == {}
    assert "transport" not in configs["a"]


def test_custom_mcp_name_conflicts_with_builtin(svc: ConnectorService, db: DBPool):
    uid = _ensure_user(db)
    iid = new_ulid()
    name = mcp_server_name("tencent-docs", iid)
    svc._repo.create(  # noqa: SLF001
        instance_id=iid,
        user_id=uid,
        kind="tencent-docs",
        display_name="Docs",
        mcp_server_name=name,
    )
    with pytest.raises(ValueError, match="conflicts"):
        svc.put_custom_servers(
            uid,
            {
                name: {
                    "transport": "stdio",
                    "command": "npx",
                }
            },
        )
