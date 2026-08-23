"""tests/unit/i18n/test_tools.py"""

from __future__ import annotations

import json
from pathlib import Path

from octop.i18n import all_tool_labels, hitl_tool_catalog, tool_display_name
from octop.i18n.domains.tools import resolve_tool_display_name


def test_tool_display_name_known_zh():
    assert tool_display_name("read_file", "zh") == "读取文件"
    assert tool_display_name("write_todos", "zh") == "编写计划"
    assert tool_display_name("read_env_file", "zh") == "读取环境变量"
    assert tool_display_name("write_env_file", "en") == "Write env file"


def test_tool_display_name_unknown_passthrough():
    assert tool_display_name("custom_plugin_tool", "en") == "custom_plugin_tool"


def test_resolve_tool_display_name_mcp_connector_label():
    label = resolve_tool_display_name(
        "my_docs_search",
        "zh",
        mcp_server_labels={"my_docs": "腾讯文档"},
    )
    assert label == "腾讯文档 · Search"


def test_resolve_tool_display_name_plugin_original_label():
    label = resolve_tool_display_name(
        "tianqichaxun",
        "zh",
        plugin_labels={"tianqichaxun": "天气查询"},
    )
    assert label == "天气查询"


def test_tool_display_name_empty_uses_unknown():
    assert tool_display_name(None, "en") == "Unknown tool"


def test_all_tool_labels_includes_unknown():
    labels = all_tool_labels("en")
    assert labels["grep"] == "Search content"
    assert "unknown" in labels


def test_hitl_tool_catalog_excludes_must_use_tools():
    names = {entry.name for entry in hitl_tool_catalog()}
    assert "unknown" not in names
    assert "current_time" not in names
    assert "write_todos" not in names
    assert "memory_search" not in names
    assert "search_knowledge" not in names
    assert "cronjob_create" not in names
    assert "task" not in names
    assert "ask_agent" not in names


def test_hitl_tool_catalog_includes_common_tools():
    names = {entry.name for entry in hitl_tool_catalog()}
    assert "bash" in names
    assert "write_file" in names
    assert "browser_use" in names
    assert "web_fetch" in names


def test_hitl_tool_catalog_bilingual_labels():
    entry = next(e for e in hitl_tool_catalog() if e.name == "read_file")
    assert entry.label_zh == "读取文件"
    assert entry.label_en == "Read file"


def test_dashboard_tools_match_backend():
    repo = Path(__file__).resolve().parents[3]
    dash_en = json.loads((repo / "dashboard/src/locales/en.json").read_text(encoding="utf-8"))
    backend_en = json.loads((repo / "src/octop/i18n/en.json").read_text(encoding="utf-8"))
    assert dash_en["tools"] == backend_en["tools"]
