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
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.connectors import ConnectorRepo
from octop.infra.db.repos.secrets import SecretRepo
from octop.infra.db.repos.settings import SettingsRepo
from octop.infra.utils.ulid import new_ulid


@pytest.fixture
def db(tmp_path: Path) -> SqlitePool:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    return pool


@pytest.fixture
def svc(db: SqlitePool) -> ConnectorService:
    return ConnectorService(
        repo=ConnectorRepo(db),
        secret_repo=SecretRepo(db),
        settings_repo=SettingsRepo(db),
        config=OctopConfig(),
    )


def _ensure_user(db: SqlitePool) -> int:
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
                "display_name": "示例搜索",
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
    assert "display_name" not in configs["on"]
    assert configs["on"]["transport"] == "streamable_http"


def test_display_name_normalized_and_used_in_list_api(svc: ConnectorService, db: SqlitePool):
    uid = _ensure_user(db)
    servers = svc.put_custom_servers(
        uid,
        {
            "http-server-1": {
                "transport": "streamable_http",
                "url": "https://mcp.example.com/mcp",
                "display_name": "  我的知识库  ",
            },
        },
    )
    assert servers["http-server-1"]["display_name"] == "我的知识库"
    listed = svc.list_instances_for_api(uid)
    assert len(listed) == 1
    assert listed[0]["mcp_server_name"] == "http-server-1"
    assert listed[0]["display_name"] == "我的知识库"


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


def test_put_and_expand_custom_mcp(svc: ConnectorService, db: SqlitePool):
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


def test_put_empty_servers_deletes_parent_row(svc: ConnectorService, db: SqlitePool):
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


def test_build_mcp_configs_merges_enabled_custom(svc: ConnectorService, db: SqlitePool):
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


def test_custom_mcp_name_conflicts_with_builtin(svc: ConnectorService, db: SqlitePool):
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


def test_normalize_preserves_default_open():
    spec = normalize_server_spec(
        "deepwiki",
        {
            "transport": "streamable_http",
            "url": "https://mcp.deepwiki.com/mcp",
            "default_open": True,
        },
    )
    assert spec["default_open"] is True
    harness = harness_spec_for_server(spec)
    assert "default_open" not in harness


def test_default_open_false_by_default_and_listed(svc: ConnectorService, db: SqlitePool):
    uid = _ensure_user(db)
    svc.put_custom_servers(
        uid,
        {
            "always": {
                "transport": "streamable_http",
                "url": "https://mcp.example.com/mcp",
                "default_open": True,
            },
            "opt": {
                "transport": "stdio",
                "command": "npx",
            },
        },
    )
    listed = {row["mcp_server_name"]: row for row in svc.list_instances_for_api(uid)}
    assert listed["always"]["default_open"] is True
    assert listed["opt"]["default_open"] is False


def test_list_default_open_mcp_server_names(svc: ConnectorService, db: SqlitePool):
    uid = _ensure_user(db)
    iid = new_ulid()
    svc._repo.create(
        instance_id=iid,
        user_id=uid,
        kind="tencent-docs",
        display_name="docs",
        mcp_server_name=mcp_server_name("tencent-docs", iid),
        config_json='{"default_open": true}',
    )
    from octop.infra.connectors.crypto import encrypt_credentials

    blob = encrypt_credentials(svc._secret_repo, {"token": "t", "instance_id": iid})
    svc._repo.upsert_credentials(instance_id=iid, blob=blob)

    svc.put_custom_servers(
        uid,
        {
            "always": {
                "transport": "streamable_http",
                "url": "https://mcp.example.com/mcp",
                "default_open": True,
            },
            "opt": {
                "transport": "stdio",
                "command": "npx",
            },
        },
    )
    names = svc.list_default_open_mcp_server_names(uid)
    assert mcp_server_name("tencent-docs", iid) in names
    assert "always" in names
    assert "opt" not in names
