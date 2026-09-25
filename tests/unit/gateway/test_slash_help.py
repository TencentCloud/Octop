"""tests/unit/test_slash_help.py"""

from __future__ import annotations

from octop.infra.gateway.slash.catalog import channel_origin, list_specs
from octop.infra.gateway.slash.help import format_help


def test_channel_origin_maps_surfaces():
    assert channel_origin("dashboard") == "ui"
    assert channel_origin("cli") == "cli"
    for im_channel in ("feishu", "telegram", "dingtalk", "wecom", "unknown"):
        assert channel_origin(im_channel) == "im"


def test_im_help_lists_hitl_commands():
    """/approve, /reject and /pending are declared im-only, so IM /help must show them."""
    for im_channel in ("feishu", "telegram", "unknown"):
        specs = list_specs(origin=channel_origin(im_channel))
        names = {s.name for s in specs}
        assert {"approve", "reject", "pending"} <= names
        text = format_help(specs, "en")
        assert "`/approve [pending_id]`" in text
        assert "`/pending`" in text


def test_help_groups_by_category_zh():
    text = format_help(list_specs(origin="ui"), "zh")
    assert "**可用指令**" in text
    assert "**核心命令**" in text
    assert "**会话管理**" in text
    assert "**系统**" in text
    assert "`/status`" in text
    assert "`/help`" in text
    # Core section should appear before session section
    assert text.index("核心命令") < text.index("会话管理")


def test_help_groups_by_category_en():
    text = format_help(list_specs(origin="ui"), "en")
    assert "**Available commands**" in text
    assert "**Core**" in text
    assert "**Sessions**" in text
    assert text.index("Core") < text.index("Sessions")


def test_sessions_alias_in_catalog():
    from octop.infra.gateway.slash.catalog import spec_for

    assert spec_for("sessions") is not None
    assert spec_for("sessions").name == "list"  # type: ignore[union-attr]
    assert spec_for("models") is not None
    assert spec_for("models").name == "model"  # type: ignore[union-attr]
