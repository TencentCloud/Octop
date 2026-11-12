"""Unit tests for the module permission catalog."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from octop.infra.users.permissions import (
    ASSIGNABLE_PERMISSION_KEYS,
    BASELINE_PERMISSIONS,
    PERMISSIONS,
    effective_permissions,
    user_has_permission,
    validate_permission_keys,
)


@dataclass
class _FakeUser:
    is_admin: bool
    permissions: list[str] | None = None


def test_catalog_has_no_empty_keys_and_no_deferred_dead_keys() -> None:
    assert PERMISSIONS
    for key in PERMISSIONS:
        assert key == PERMISSIONS[key].key
        assert PERMISSIONS[key].label_zh and PERMISSIONS[key].label_en
    assert "acp" not in PERMISSIONS


def test_user_has_permission_admin_bypass() -> None:
    admin = _FakeUser(is_admin=True, permissions=[])
    for key in PERMISSIONS:
        assert user_has_permission(admin, key) is True


def test_user_has_permission_normal_hit_and_miss() -> None:
    u = _FakeUser(is_admin=False, permissions=["browser", "users"])
    assert user_has_permission(u, "browser") is True
    assert user_has_permission(u, "providers") is False
    assert user_has_permission(u, "unknown_key") is False


def test_baseline_is_settings_group() -> None:
    assert {
        key
        for key, perm in PERMISSIONS.items()
        if perm.assignable and perm.category in {"settings", "nav"}
    } == BASELINE_PERMISSIONS
    assert BASELINE_PERMISSIONS
    assert "experts" in BASELINE_PERMISSIONS
    assert "tasks" in BASELINE_PERMISSIONS
    assert "token_usage" in BASELINE_PERMISSIONS


def test_categories_match_nav_groups() -> None:
    allowed = {"settings", "control", "admin", "nav"}
    for p in PERMISSIONS.values():
        assert p.category in allowed
    assert {k for k, p in PERMISSIONS.items() if p.category == "settings"} == {
        "skills",
        "skill_builtin",
        "skill_market",
        "subagents",
        "tools",
        "agent_plugins",
        "mbti",
        "memory",
        "channels",
        "connectors",
        "connector_enabled",
        "connector_builtin",
        "connector_custom",
        "skill_packages",
        "knowledge_bases",
        "bridge",
    }
    assert not PERMISSIONS["connectors"].assignable
    assert "connectors" not in BASELINE_PERMISSIONS
    assert "connector_enabled" in BASELINE_PERMISSIONS
    assert "skill_builtin" in BASELINE_PERMISSIONS
    assert "bridge" in BASELINE_PERMISSIONS
    assert PERMISSIONS["skills"].page == "personalization"
    assert PERMISSIONS["agent_plugins"].page == "personalization"
    assert {k for k, p in PERMISSIONS.items() if p.category == "control"} == {
        "terminal",
        "browser",
        "desktop",
        "mobile",
    }
    assert PERMISSIONS["envs"].page == "advanced"
    assert PERMISSIONS["voice"].page == "models"
    assert PERMISSIONS["search"].page == "models"
    assert PERMISSIONS["knowledge_settings"].page == "advanced"
    assert PERMISSIONS["knowledge_settings"].category == "admin"
    assert "knowledge_settings" not in BASELINE_PERMISSIONS
    assert PERMISSIONS["users"].page == "users"
    assert PERMISSIONS["sso_wecom"].page == "users"
    assert PERMISSIONS["sso_wecom"].label_zh == "企微登录"
    assert not PERMISSIONS["sso"].assignable
    assert PERMISSIONS["user_roles"].label_zh == "角色管理"
    assert PERMISSIONS["security_hitl"].label_zh == "工具审批"
    assert PERMISSIONS["plugin_market"].page == "plugins"
    assert PERMISSIONS["model_generation"].page == "models"
    assert PERMISSIONS["plugins"].page == "plugins"
    assert not PERMISSIONS["plugins"].extra_tabs
    assert "agents" not in PERMISSIONS


def test_validate_permission_keys_rejects_unknown() -> None:
    assert validate_permission_keys(["browser", "users"]) == ["browser", "users"]
    with pytest.raises(ValueError):
        validate_permission_keys(["browser", "not_a_real_key"])


def test_effective_permissions_admin_gets_catalog() -> None:
    admin = _FakeUser(is_admin=True, permissions=[])
    assert effective_permissions(admin) == sorted(ASSIGNABLE_PERMISSION_KEYS)


def test_legacy_umbrella_expands_to_tabs() -> None:
    user = _FakeUser(is_admin=False, permissions=["sso", "browser"])
    assert user_has_permission(user, "sso_wecom") is True
    assert user_has_permission(user, "sso_ldap") is True
    assert user_has_permission(user, "sso") is True
    shown = effective_permissions(user)
    assert "sso" not in shown
    assert "sso_wecom" in shown
    assert "browser" in shown
    stored = validate_permission_keys(["sso", "browser"])
    assert stored == ["sso_feishu", "sso_wecom", "sso_dingtalk", "sso_oidc", "sso_ldap", "browser"]


def test_connector_tab_satisfies_legacy_route_key() -> None:
    user = _FakeUser(is_admin=False, permissions=["connector_custom"])
    assert user_has_permission(user, "connectors") is True
    assert user_has_permission(user, "connector_enabled") is False
