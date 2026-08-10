"""Unit tests for connector default_open config helpers."""

from __future__ import annotations

from octop.infra.connectors.default_open import (
    build_instance_config_json,
    merge_mcp_servers_with_defaults,
    read_default_open,
)


def test_read_default_open_defaults_false():
    assert read_default_open(None) is False
    assert read_default_open({}) is False
    assert read_default_open({"default_open": False}) is False
    assert read_default_open({"default_open": "yes"}) is False


def test_read_default_open_true():
    assert read_default_open({"default_open": True}) is True


def test_build_instance_config_json_omits_when_false():
    assert build_instance_config_json(kind="tencent-docs", default_open=False) is None
    assert (
        build_instance_config_json(
            kind="qq-mail",
            default_open=False,
            email="a@qq.com",
        )
        == '{"email": "a@qq.com"}'
    )


def test_build_instance_config_json_includes_when_true():
    raw = build_instance_config_json(kind="tencent-docs", default_open=True)
    assert raw == '{"default_open": true}'
    raw_mail = build_instance_config_json(
        kind="qq-mail",
        default_open=True,
        email="a@qq.com",
    )
    assert '"default_open": true' in raw_mail
    assert '"email": "a@qq.com"' in raw_mail


def test_merge_mcp_servers_with_defaults_unions_and_dedupes():
    # Default: apply defaults only when explicit is None (IM-style).
    assert merge_mcp_servers_with_defaults(None, ["a", "b"]) == ["a", "b"]
    assert merge_mcp_servers_with_defaults(["b", "c"], ["a", "b"]) == ["b", "c"]
    assert merge_mcp_servers_with_defaults(["x"], []) == ["x"]
    assert merge_mcp_servers_with_defaults(None, []) is None
    assert merge_mcp_servers_with_defaults([], []) is None
    # Cron-style force union.
    assert merge_mcp_servers_with_defaults(["b", "c"], ["a", "b"], apply_defaults=True) == [
        "b",
        "c",
        "a",
    ]


def test_merge_respects_dashboard_opt_out():
    # Explicit list (including empty) must not re-add defaults.
    assert merge_mcp_servers_with_defaults(["b"], ["a"], apply_defaults=False) == ["b"]
    assert merge_mcp_servers_with_defaults([], ["a"], apply_defaults=False) is None
    # IM / Cron force defaults.
    assert merge_mcp_servers_with_defaults([], ["a"], apply_defaults=True) == ["a"]
    assert merge_mcp_servers_with_defaults(None, ["a"], apply_defaults=True) == ["a"]
