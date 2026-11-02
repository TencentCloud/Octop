"""Built-in connector catalog is JSON-backed and bilingual."""

from __future__ import annotations

from pathlib import Path

from octop.infra.connectors.catalog import (
    catalog_entry_to_dict,
    get_catalog_entry,
    list_catalog,
)


def test_catalog_localizes_name_description_and_fields() -> None:
    entry = get_catalog_entry("weknora")
    assert entry is not None
    zh = catalog_entry_to_dict(entry, locale="zh")
    en = catalog_entry_to_dict(entry, locale="en")
    assert zh["name"] == "WeKnora"
    assert zh["description"] == "连接 WeKnora 私有知识库，提供只读检索与文档阅读"
    assert en["description"] == (
        "Connect a private WeKnora knowledge base for read-only search and document reading"
    )
    zh_fields = {item["key"]: item for item in zh["credential_fields"]}
    en_fields = {item["key"]: item for item in en["credential_fields"]}
    assert zh_fields["base_url"]["label"] == "服务地址"
    assert en_fields["base_url"]["label"] == "Service URL"
    assert zh_fields["base_url"]["help"] == "未包含 /api/v1 时会自动补齐"
    assert "appends /api/v1" in str(en_fields["base_url"]["help"])


def test_every_catalog_entry_has_en_and_zh_copy() -> None:
    for entry in list_catalog():
        assert entry.name.en.strip()
        assert entry.name.zh.strip()
        assert entry.description.en.strip()
        assert entry.description.zh.strip()
        zh = catalog_entry_to_dict(entry, locale="zh")
        en = catalog_entry_to_dict(entry, locale="en")
        assert zh["name"] == entry.name.zh
        assert en["name"] == entry.name.en
        assert zh["description"] == entry.description.zh
        assert en["description"] == entry.description.en
        if entry.auth_hint is not None:
            assert zh["auth_hint"] == entry.auth_hint.zh
            assert en["auth_hint"] == entry.auth_hint.en
        for field in entry.credential_fields:
            assert field.label.en.strip()
            assert field.label.zh.strip()


def _docs_catalog_table_rows(text: str) -> list[tuple[str, str, str, str, str, str]]:
    header = "| Kind | Name | 名称 | Category | Auth | MCP mode |"
    start = text.find(header)
    assert start >= 0, "docs/connectors.md is missing the catalog table header"
    rows: list[tuple[str, str, str, str, str, str]] = []
    for line in text[start:].splitlines()[2:]:
        if not line.startswith("|"):
            break
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 6:
            break
        kind = cells[0].strip("`")
        rows.append((kind, cells[1], cells[2], cells[3], cells[4], cells[5]))
    return rows


def test_docs_catalog_table_matches_json() -> None:
    docs = Path(__file__).resolve().parents[3] / "docs" / "connectors.md"
    text = docs.read_text(encoding="utf-8")
    expected = [
        (
            entry.kind,
            entry.name.en,
            entry.name.zh,
            entry.category,
            entry.auth_kind,
            entry.mcp_mode,
        )
        for entry in list_catalog()
    ]
    assert _docs_catalog_table_rows(text) == expected
