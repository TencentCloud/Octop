"""Unit tests for the module permission catalog."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from octop.infra.users.permissions import (
    ALL_PERMISSION_KEYS,
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
    for key in ALL_PERMISSION_KEYS:
        assert user_has_permission(admin, key) is True


def test_user_has_permission_normal_hit_and_miss() -> None:
    u = _FakeUser(is_admin=False, permissions=["browser", "users"])
    assert user_has_permission(u, "browser") is True
    assert user_has_permission(u, "providers") is False
    assert user_has_permission(u, "unknown_key") is False


def test_baseline_is_settings_group() -> None:
    assert {
        key for key, p in PERMISSIONS.items() if p.category == "settings"
    } == BASELINE_PERMISSIONS
    assert BASELINE_PERMISSIONS
    assert all(PERMISSIONS[k].category == "settings" for k in BASELINE_PERMISSIONS)


def test_categories_match_nav_groups() -> None:
    allowed = {"settings", "control", "admin"}
    for p in PERMISSIONS.values():
        assert p.category in allowed
    assert {k for k, p in PERMISSIONS.items() if p.category == "settings"} == {
        "channels",
        "connectors",
        "skill_packages",
        "knowledge_bases",
    }
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
    assert PERMISSIONS["plugins"].page == "plugins"
    assert not PERMISSIONS["plugins"].extra_tabs
    assert "agents" not in PERMISSIONS


def test_validate_permission_keys_rejects_unknown() -> None:
    assert validate_permission_keys(["browser", "users"]) == ["browser", "users"]
    with pytest.raises(ValueError):
        validate_permission_keys(["browser", "not_a_real_key"])


def test_effective_permissions_admin_gets_catalog() -> None:
    admin = _FakeUser(is_admin=True, permissions=[])
    assert effective_permissions(admin) == sorted(ALL_PERMISSION_KEYS)
