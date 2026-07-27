"""tests/unit/i18n/test_tools.py"""

from __future__ import annotations

import json
from pathlib import Path

from octop.i18n import all_tool_labels, tool_display_name


def test_tool_display_name_known_zh():
    assert tool_display_name("read_file", "zh") == "读取文件"
    assert tool_display_name("write_todos", "zh") == "编写计划"


def test_tool_display_name_unknown_passthrough():
    assert tool_display_name("custom_plugin_tool", "en") == "custom_plugin_tool"


def test_tool_display_name_empty_uses_unknown():
    assert tool_display_name(None, "en") == "Unknown tool"


def test_all_tool_labels_includes_unknown():
    labels = all_tool_labels("en")
    assert labels["grep"] == "Search content"
    assert "unknown" in labels


def test_dashboard_tools_match_backend():
    repo = Path(__file__).resolve().parents[3]
    dash_en = json.loads((repo / "dashboard/src/locales/en.json").read_text(encoding="utf-8"))
    backend_en = json.loads((repo / "src/octop/i18n/en.json").read_text(encoding="utf-8"))
    assert dash_en["tools"] == backend_en["tools"]
