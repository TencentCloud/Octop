"""Per-user identity placeholders (``${octop.*}``) in custom MCP connector headers.

Motivation: a ``shared: true`` connector carries **one** static header set, so a
multi-tenant MCP server cannot tell which end user a call belongs to — every user
collapses onto one server-side session. Allowing ``${octop.user_id}`` /
``${octop.username}`` inside header values lets Octop attribute each request to the
requesting user while the admin still configures the connector exactly once.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from octop.config import OctopConfig
from octop.infra.connectors.custom_mcp import (
    _SCOPE_VALUE_MAX,
    apply_user_scope,
    enabled_harness_configs,
    harness_spec_for_server,
    normalize_server_spec,
    resolve_user_scope_url,
    user_scope_context,
)
from octop.infra.connectors.mcp_tool_cache import fingerprint_mcp_spec
from octop.infra.connectors.service import ConnectorService
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.connectors import ConnectorRepo
from octop.infra.db.repos.secrets import SecretRepo
from octop.infra.db.repos.settings import SettingsRepo
from octop.infra.db.repos.users import UserRepo

_ERP_URL = "https://mcp.example.com/erp/mcp"
_TENANT_HEADER = "X-Tenant-Key"


@pytest.fixture
def db(tmp_path: Path) -> SqlitePool:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    return pool


def _svc(db: SqlitePool) -> ConnectorService:
    return ConnectorService(
        repo=ConnectorRepo(db),
        secret_repo=SecretRepo(db),
        settings_repo=SettingsRepo(db),
        config=OctopConfig(),
        user_repo=UserRepo(db),
    )


def _add_user(db: SqlitePool, username: str) -> int:
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO users(username, password_hash, role, created_at) "
            f"VALUES ('{username}', 'x', 'user', 1)"
        )
        row = conn.execute(f"SELECT id FROM users WHERE username = '{username}'").fetchone()
    assert row is not None
    return int(row["id"])


def _tenant_spec(token: str = "username") -> dict[str, object]:
    return {
        "transport": "streamable_http",
        "url": _ERP_URL,
        "headers": {_TENANT_HEADER: f"acme_${{octop.{token}}}"},
    }


# --------------------------------------------------------------------------- pure helpers


def test_scope_prefers_username_and_falls_back_to_id() -> None:
    scope = user_scope_context(user_id=42, username="alice")
    assert scope == {"user_id": "42", "username": "alice"}
    # A missing row must not send the literal template: that would collapse every
    # user onto the same server-side tenant/session.
    assert user_scope_context(user_id=42, username=None)["username"] == "42"


def test_scope_values_are_header_sanitized() -> None:
    value = user_scope_context(user_id=7, username="jing\r\nX-Evil: yes 李")["username"]
    assert "\r" not in value and "\n" not in value and " " not in value
    assert value.isascii()


def test_scope_values_stay_inside_the_downstream_key_charset() -> None:
    # ``@`` and ``:`` travel fine in a header but are rejected by tenant-key style
    # validators, and the rejection fallback is one shared default identity.
    assert user_scope_context(user_id=7, username="jing@corp.example")["username"] == (
        "jing_corp.example"
    )
    assert user_scope_context(user_id=7, username="a:b")["username"] == "a_b"
    # A name made only of dots is not an identity either -> numeric id.
    assert user_scope_context(user_id=9, username="..")["username"] == "9"


def test_long_username_falls_back_to_id_instead_of_truncating() -> None:
    # Truncating could collide (two long names sharing a prefix would merge); the
    # numeric id is always short and unique.
    assert user_scope_context(user_id=12, username="u" * 80)["username"] == "12"


def test_apply_user_scope_prefers_numeric_id_over_truncating() -> None:
    prefix = "p" * (_SCOPE_VALUE_MAX - 3)
    headers = {_TENANT_HEADER: f"{prefix}_${{octop.username}}"}
    out = apply_user_scope(headers, user_scope_context(user_id=5, username="alice"))
    assert out[_TENANT_HEADER] == f"{prefix}_5"
    assert len(out[_TENANT_HEADER]) <= _SCOPE_VALUE_MAX


def test_apply_user_scope_raises_when_no_value_fits() -> None:
    headers = {_TENANT_HEADER: "q" * (_SCOPE_VALUE_MAX + 10) + "_${octop.username}"}
    with pytest.raises(ValueError, match="does not fit"):
        apply_user_scope(headers, user_scope_context(user_id=5, username="alice"))


def test_unresolvable_server_is_dropped_rather_than_sent() -> None:
    # No request goes out with a collapsed identity: the server simply is not
    # exposed for this user.
    servers = {
        "erp": {"transport": "streamable_http", "url": _ERP_URL},
        "broken": {
            "transport": "streamable_http",
            "url": _ERP_URL,
            "headers": {_TENANT_HEADER: "q" * 200 + "_${octop.username}"},
        },
    }
    configs = enabled_harness_configs(servers, user_scope=user_scope_context(user_id=1))
    assert list(configs) == ["erp"]


def test_apply_user_scope_touches_only_matching_values() -> None:
    headers = {
        _TENANT_HEADER: "acme_${octop.username}",
        "Accept": "application/json, text/event-stream",
    }
    scope = user_scope_context(user_id=3, username="alice")
    out = apply_user_scope(headers, scope)
    assert out[_TENANT_HEADER] == "acme_alice"
    assert out["Accept"] == headers["Accept"]
    assert apply_user_scope(headers, None) == headers


# ------------------------------------------------------------------- spec build / validation


def test_placeholder_stored_verbatim_and_unknown_token_rejected() -> None:
    spec = normalize_server_spec("erp", _tenant_spec())
    assert spec["headers"][_TENANT_HEADER] == "acme_${octop.username}"

    typo = _tenant_spec()
    typo["headers"][_TENANT_HEADER] = "acme_${octop.usre_id}"
    with pytest.raises(ValueError, match="unknown placeholder"):
        normalize_server_spec("erp", typo)


def test_harness_spec_substitutes_only_when_scope_given() -> None:
    spec = normalize_server_spec("erp", _tenant_spec("user_id"))
    preview = harness_spec_for_server(spec)
    assert preview["headers"][_TENANT_HEADER] == "acme_${octop.user_id}"

    live = harness_spec_for_server(spec, user_scope=user_scope_context(user_id=11, username="a"))
    assert live["headers"][_TENANT_HEADER] == "acme_11"


# --------------------------------------------------------------------------- url templating


def test_url_may_be_templated_below_the_host() -> None:
    spec = normalize_server_spec(
        "erp",
        {
            "transport": "streamable_http",
            "url": _ERP_URL + "/${octop.username}",
            "headers": {_TENANT_HEADER: "acme_${octop.username}"},
        },
    )
    assert spec["url"] == _ERP_URL + "/${octop.username}"

    preview = harness_spec_for_server(spec)
    assert preview["url"] == _ERP_URL + "/${octop.username}"

    live = harness_spec_for_server(spec, user_scope=user_scope_context(user_id=4, username="bob"))
    assert live["url"] == _ERP_URL + "/bob"
    assert live["headers"][_TENANT_HEADER] == "acme_bob"


def test_url_template_rejected_in_host_and_unknown_token() -> None:
    with pytest.raises(ValueError, match="not the host"):
        normalize_server_spec(
            "erp",
            {"transport": "streamable_http", "url": "https://${octop.username}.example.com/mcp"},
        )
    with pytest.raises(ValueError, match="unknown placeholder"):
        normalize_server_spec(
            "erp",
            {"transport": "streamable_http", "url": _ERP_URL + "/${octop.bogus}"},
        )


def test_resolve_user_scope_url_leaves_plain_urls_alone() -> None:
    scope = user_scope_context(user_id=1, username="a")
    assert resolve_user_scope_url(_ERP_URL, scope) == _ERP_URL
    assert resolve_user_scope_url(_ERP_URL, None) == _ERP_URL


# ---------------------------------------------------------------------- end-to-end isolation


def test_shared_connector_carries_per_viewer_identity(db: SqlitePool) -> None:
    owner = _add_user(db, "owner")
    alice = _add_user(db, "alice")
    bob = _add_user(db, "bob")
    svc = _svc(db)
    spec = _tenant_spec()
    spec["shared"] = True
    svc.put_custom_servers(owner, {"erp": spec})

    a_cfg = svc.custom_harness_configs(alice)
    b_cfg = svc.custom_harness_configs(bob)
    assert list(a_cfg) == list(b_cfg), "same shared server exposed to both viewers"
    name = next(iter(a_cfg))

    key_a = a_cfg[name]["headers"][_TENANT_HEADER]
    key_b = b_cfg[name]["headers"][_TENANT_HEADER]
    assert key_a == "acme_alice"
    assert key_b == "acme_bob"

    # Distinct fingerprints ⇒ the (user_id, server, fingerprint) tool cache can never
    # hand one user's live MCP session to another.
    assert fingerprint_mcp_spec(a_cfg[name]) != fingerprint_mcp_spec(b_cfg[name])


def test_private_connector_is_scoped_to_its_owner(db: SqlitePool) -> None:
    owner = _add_user(db, "owner")
    svc = _svc(db)
    svc.put_custom_servers(owner, {"erp": _tenant_spec()})

    cfg = svc.custom_harness_configs(owner)
    assert cfg["erp"]["headers"][_TENANT_HEADER] == "acme_owner"


def test_stored_spec_keeps_template_after_scope_used(db: SqlitePool) -> None:
    owner = _add_user(db, "owner")
    svc = _svc(db)
    svc.put_custom_servers(owner, {"erp": _tenant_spec()})

    svc.custom_harness_configs(owner)
    saved = svc.get_custom_servers(owner)["erp"]
    assert saved["headers"][_TENANT_HEADER] == "acme_${octop.username}"
    # API views must keep showing the template, not a resolved identity.
    redacted = svc.get_custom_servers_for_api(owner)["erp"]
    assert redacted["headers"][_TENANT_HEADER] == "acme_${octop.username}"
