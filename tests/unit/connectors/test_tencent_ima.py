"""Unit tests for Tencent IMA gateway adapter (JSON OpenAPI tools)."""

from __future__ import annotations

from typing import Any

import pytest


def _install_httpx_mock(monkeypatch: pytest.MonkeyPatch, captured: dict[str, object]) -> None:
    class _Resp:
        status_code = 200

        def json(self) -> dict[str, object]:
            return {"code": 0, "data": {}}

    class _Client:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        def __enter__(self) -> _Client:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def post(self, url: str, *, headers: dict[str, str], json: dict[str, object]) -> _Resp:
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return _Resp()

    monkeypatch.setattr(
        "octop.infra.connectors.gateway.adapters.tencent_ima.httpx.Client",
        _Client,
    )


def _call(name: str, args: dict[str, Any] | None = None) -> str:
    from octop.infra.connectors.gateway.adapters.tencent_ima import call_tool

    return call_tool(
        {"api_key": "k", "client_id": "c"},
        name,
        args or {},
    )


def test_list_tools_covers_json_openapi_surface() -> None:
    from octop.infra.connectors.gateway.adapters.tencent_ima import list_tools

    names = {t["name"] for t in list_tools()}
    assert names == {
        "list_notebooks",
        "list_notes",
        "get_note",
        "search_notes",
        "create_note",
        "append_note",
        "list_knowledge_bases",
        "list_addable_knowledge_bases",
        "get_knowledge_base",
        "list_knowledge",
        "search_knowledge",
        "import_urls",
        "add_note_to_knowledge",
        "get_media",
    }


def test_list_notebooks_defaults_cursor_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    _install_httpx_mock(monkeypatch, captured)
    _call("list_notebooks", {"limit": 10})
    assert captured["url"] == "https://ima.qq.com/openapi/note/v1/list_notebook"
    assert captured["json"] == {"cursor": "0", "limit": 10}


def test_get_note_uses_plaintext(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    _install_httpx_mock(monkeypatch, captured)
    _call("get_note", {"note_id": "n1"})
    assert captured["url"] == "https://ima.qq.com/openapi/note/v1/get_doc_content"
    assert captured["json"] == {"note_id": "n1", "target_content_format": 0}


def test_search_notes_content_type(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    _install_httpx_mock(monkeypatch, captured)
    _call("search_notes", {"query": "排期", "search_type": 1})
    assert captured["url"] == "https://ima.qq.com/openapi/note/v1/search_note"
    assert captured["json"] == {
        "search_type": 1,
        "query_info": {"content": "排期"},
        "start": 0,
        "end": 20,
    }


def test_create_note_markdown(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    _install_httpx_mock(monkeypatch, captured)
    _call("create_note", {"content": "# hi", "folder_id": "f1"})
    assert captured["url"] == "https://ima.qq.com/openapi/note/v1/import_doc"
    assert captured["json"] == {
        "content_format": 1,
        "content": "# hi",
        "folder_id": "f1",
    }


def test_append_note_requires_note_id(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    _install_httpx_mock(monkeypatch, captured)
    with pytest.raises(ValueError, match="note_id"):
        _call("append_note", {"content": "x"})
    _call("append_note", {"note_id": "n1", "content": "more"})
    assert captured["url"] == "https://ima.qq.com/openapi/note/v1/append_doc"
    assert captured["json"] == {
        "note_id": "n1",
        "content_format": 1,
        "content": "more",
    }


def test_list_knowledge_bases_cursor_query(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    _install_httpx_mock(monkeypatch, captured)
    _call("list_knowledge_bases", {})
    assert captured["url"] == "https://ima.qq.com/openapi/wiki/v1/search_knowledge_base"
    assert captured["json"] == {"query": "", "cursor": "", "limit": 20}


def test_list_addable_knowledge_bases(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    _install_httpx_mock(monkeypatch, captured)
    _call("list_addable_knowledge_bases", {"limit": 5})
    assert captured["url"] == "https://ima.qq.com/openapi/wiki/v1/get_addable_knowledge_base_list"
    assert captured["json"] == {"cursor": "", "limit": 5}


def test_get_knowledge_base(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    _install_httpx_mock(monkeypatch, captured)
    _call("get_knowledge_base", {"ids": ["kb1", "kb2"]})
    assert captured["url"] == "https://ima.qq.com/openapi/wiki/v1/get_knowledge_base"
    assert captured["json"] == {"ids": ["kb1", "kb2"]}


def test_list_knowledge(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    _install_httpx_mock(monkeypatch, captured)
    _call("list_knowledge", {"knowledge_base_id": "kb1", "folder_id": "fd1"})
    assert captured["url"] == "https://ima.qq.com/openapi/wiki/v1/get_knowledge_list"
    assert captured["json"] == {
        "knowledge_base_id": "kb1",
        "folder_id": "fd1",
        "cursor": "",
        "limit": 20,
    }


def test_search_knowledge_requires_kb_and_cursor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    _install_httpx_mock(monkeypatch, captured)
    with pytest.raises(ValueError, match="knowledge_base_id"):
        _call("search_knowledge", {"query": "x"})
    _call("search_knowledge", {"query": "x", "knowledge_base_id": "kb1"})
    assert captured["url"] == "https://ima.qq.com/openapi/wiki/v1/search_knowledge"
    assert captured["json"] == {
        "query": "x",
        "knowledge_base_id": "kb1",
        "cursor": "",
    }


def test_import_urls_defaults_folder_to_kb(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    _install_httpx_mock(monkeypatch, captured)
    _call(
        "import_urls",
        {
            "knowledge_base_id": "kb1",
            "urls": ["https://example.com/a"],
        },
    )
    assert captured["url"] == "https://ima.qq.com/openapi/wiki/v1/import_urls"
    assert captured["json"] == {
        "knowledge_base_id": "kb1",
        "folder_id": "kb1",
        "urls": ["https://example.com/a"],
    }


def test_import_urls_rejects_too_many() -> None:
    with pytest.raises(ValueError, match="at most 10"):
        _call(
            "import_urls",
            {
                "knowledge_base_id": "kb1",
                "urls": [f"https://example.com/{i}" for i in range(11)],
            },
        )


def test_add_note_to_knowledge(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    _install_httpx_mock(monkeypatch, captured)
    _call(
        "add_note_to_knowledge",
        {
            "knowledge_base_id": "kb1",
            "note_id": "n1",
            "title": "纪要",
        },
    )
    assert captured["url"] == "https://ima.qq.com/openapi/wiki/v1/add_knowledge"
    assert captured["json"] == {
        "media_type": 11,
        "title": "纪要",
        "knowledge_base_id": "kb1",
        "note_info": {"content_id": "n1"},
    }


def test_get_media(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    _install_httpx_mock(monkeypatch, captured)
    _call("get_media", {"media_id": "m1"})
    assert captured["url"] == "https://ima.qq.com/openapi/wiki/v1/get_media_info"
    assert captured["json"] == {"media_id": "m1"}
