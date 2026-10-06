"""arXiv plugin query mapping, Atom parsing, and agent/market integration."""

from __future__ import annotations

import asyncio
import importlib.util
import inspect
import json
from collections.abc import Callable
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import httpx
import pytest
from octop_harness.plugins import PluginRegistry, build_plugin_tools, load_plugin_dir

from octop.infra.agents.plugins.bundled import default_bundled_plugins_root
from octop.infra.agents.plugins.manager import PluginManager
from octop.infra.agents.plugins.plugin_tool_defaults import expand_plugin_tools_default_on

_PLUGIN_DIR = default_bundled_plugins_root() / "arxiv-search"
_ASYNC_CLIENT = httpx.AsyncClient
_SUMMARY = (
    "We describe a scalable method for learning representations from scientific papers. "
    "The full abstract includes additional experimental results and limitations that "
    "must remain available when the plugin output is sent to an IM channel."
)
_ENTRY = f"""
<entry>
  <id>http://arxiv.org/abs/2501.01234v2</id>
  <title> Learning representations\n from scientific papers </title>
  <summary> {_SUMMARY}\n </summary>
  <published>2025-01-03T12:00:00Z</published>
  <updated>2025-02-04T13:00:00Z</updated>
  <author><name>Alice Researcher</name></author>
  <author><name> Bob\n Scientist </name></author>
  <category term="cs.CL" />
  <category term="cs.AI" />
  <ax:primary_category term="cs.CL" />
  <ax:doi>10.1234/example</ax:doi>
  <ax:journal_ref>Example Journal 1 (2025)</ax:journal_ref>
  <link href="http://arxiv.org/abs/2501.01234v2" rel="alternate" type="text/html" />
  <link href="http://arxiv.org/pdf/2501.01234v2" rel="related"
        title="pdf" type="application/pdf" />
</entry>
"""


def _feed(entries: str = _ENTRY, *, total: int = 42, start: int = 0) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:os="http://a9.com/-/spec/opensearch/1.1/"
      xmlns:ax="http://arxiv.org/schemas/atom">
  <os:totalResults>{total}</os:totalResults>
  <os:startIndex>{start}</os:startIndex>
  {entries}
</feed>"""


@pytest.fixture
def arxiv(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "bundled_arxiv_search_test", _PLUGIN_DIR / "main.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "_MIN_REQUEST_INTERVAL", 0)
    return module


def _mock_client(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], httpx.Response],
) -> list[httpx.Request]:
    requests: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    def client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        return _ASYNC_CLIENT(*args, **kwargs, transport=httpx.MockTransport(record))

    monkeypatch.setattr(httpx, "AsyncClient", client)
    return requests


def _success_client(
    monkeypatch: pytest.MonkeyPatch,
    body: str | None = None,
) -> list[httpx.Request]:
    return _mock_client(
        monkeypatch,
        lambda request: httpx.Response(200, text=body if body is not None else _feed()),
    )


def _assert_envelope(payload: dict[str, Any]) -> None:
    assert payload["octop_ui"] == {"renderer": "arxiv_search_list", "version": 1}
    assert isinstance(payload["text"], str)
    assert payload["text"]


async def test_search_parses_atom_metadata_and_keeps_complete_im_text(
    arxiv: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests = _success_client(monkeypatch, _feed(start=10))

    payload = json.loads(
        await arxiv.search_arxiv(
            "  representation learning  ",
            limit=3,
            start=10,
            sort_by="submittedDate",
            sort_order="ascending",
        )
    )

    _assert_envelope(payload)
    assert len(requests) == 1
    request = requests[0]
    assert request.url.scheme == "https"
    assert request.url.host == "export.arxiv.org"
    assert request.url.path == "/api/query"
    assert dict(request.url.params) == {
        "search_query": "all:representation learning",
        "start": "10",
        "max_results": "3",
        "sortBy": "submittedDate",
        "sortOrder": "ascending",
    }
    assert "Octop" in request.headers["User-Agent"]
    assert payload["data"]["query"] == "representation learning"
    assert payload["data"]["total"] == 42
    assert payload["data"]["start"] == 10
    item = payload["data"]["items"][0]
    assert item == {
        "id": "2501.01234v2",
        "title": "Learning representations from scientific papers",
        "authors": ["Alice Researcher", "Bob Scientist"],
        "summary": _SUMMARY,
        "published": "2025-01-03T12:00:00Z",
        "updated": "2025-02-04T13:00:00Z",
        "categories": ["cs.CL", "cs.AI"],
        "primary_category": "cs.CL",
        "url": "https://arxiv.org/abs/2501.01234v2",
        "pdf_url": "https://arxiv.org/pdf/2501.01234v2",
        "doi": "10.1234/example",
        "journal_ref": "Example Journal 1 (2025)",
    }
    for value in (item["title"], *item["authors"], _SUMMARY, item["url"], item["pdf_url"]):
        assert value in payload["text"]


@pytest.mark.parametrize(
    "query",
    [
        'ti:"large language model" AND cat:cs.CL',
        "au:Smith",
        "cat:hep-th AND submittedDate:[202501010000 TO 202512312359]",
    ],
)
async def test_advanced_query_is_passed_to_arxiv_unchanged(
    arxiv: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    query: str,
) -> None:
    requests = _success_client(monkeypatch)
    await arxiv.search_arxiv(query)
    assert requests[0].url.params["search_query"] == query


@pytest.mark.parametrize(
    ("query", "paper_id"),
    [
        ("2501.01234", "2501.01234"),
        ("arXiv:2501.01234v2", "2501.01234v2"),
        ("id:2501.01234v2", "2501.01234v2"),
        ("https://arxiv.org/abs/2501.01234v2", "2501.01234v2"),
        ("https://arxiv.org/pdf/2501.01234v2.pdf", "2501.01234v2"),
        ("hep-th/9901001v2", "hep-th/9901001v2"),
        ("http://arxiv.org/pdf/math.GT/0309136.pdf", "math.GT/0309136"),
    ],
)
async def test_paper_ids_and_urls_use_id_list(
    arxiv: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    query: str,
    paper_id: str,
) -> None:
    requests = _success_client(monkeypatch)
    await arxiv.search_arxiv(query)
    assert requests[0].url.params["id_list"] == paper_id
    assert "search_query" not in requests[0].url.params


async def test_legacy_entry_keeps_full_id_and_https_links(
    arxiv: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = _ENTRY.replace("2501.01234v2", "hep-th/9901001v2")
    _success_client(monkeypatch, _feed(entry))

    payload = json.loads(await arxiv.search_arxiv("hep-th/9901001v2"))

    item = payload["data"]["items"][0]
    assert item["id"] == "hep-th/9901001v2"
    assert item["url"] == "https://arxiv.org/abs/hep-th/9901001v2"
    assert item["pdf_url"] == "https://arxiv.org/pdf/hep-th/9901001v2"


@pytest.mark.parametrize(("limit", "start", "expected_limit"), [(0, -5, "1"), (100, -1, "20")])
async def test_pagination_is_clamped_to_plugin_limits(
    arxiv: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    limit: int,
    start: int,
    expected_limit: str,
) -> None:
    requests = _success_client(monkeypatch)
    await arxiv.search_arxiv("quantum", limit=limit, start=start, sort_by="lastUpdatedDate")
    assert requests[0].url.params["max_results"] == expected_limit
    assert requests[0].url.params["start"] == "0"
    assert requests[0].url.params["sortBy"] == "lastUpdatedDate"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"query": " "},
        {"query": "quantum", "sort_by": "invalid"},
        {"query": "quantum", "sort_order": "invalid"},
    ],
)
async def test_invalid_input_returns_readable_error_without_network(
    arxiv: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    kwargs: dict[str, Any],
) -> None:
    requests = _success_client(monkeypatch)
    payload = json.loads(await arxiv.search_arxiv(**kwargs))
    _assert_envelope(payload)
    assert payload["data"]["items"] == []
    assert payload["data"]["error"]
    assert requests == []


async def test_empty_result_has_explicit_text(
    arxiv: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _success_client(monkeypatch, _feed("", total=0))
    payload = json.loads(await arxiv.search_arxiv("no such paper"))
    _assert_envelope(payload)
    assert payload["data"]["items"] == []
    assert payload["data"]["total"] == 0
    assert "error" not in payload["data"]
    assert not payload["data"].get("silent")


@pytest.mark.parametrize(("locale", "expected"), [("en", "Please provide"), ("zh-CN", "请提供")])
async def test_runtime_locale_localizes_input_error(
    arxiv: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    locale: str,
    expected: str,
) -> None:
    monkeypatch.setattr(arxiv, "get_config", lambda: {"configurable": {"locale": locale}})
    payload = json.loads(await arxiv.search_arxiv(" "))
    assert payload["text"].startswith(expected)


async def test_concurrent_queries_keep_three_seconds_between_requests(
    arxiv: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = [100.0]
    requested_at: list[float] = []
    slept: list[float] = []

    async def sleep(delay: float) -> None:
        slept.append(delay)
        await asyncio.sleep(0)
        now[0] += delay

    def respond(request: httpx.Request) -> httpx.Response:
        requested_at.append(now[0])
        return httpx.Response(200, text=_feed())

    monkeypatch.setattr(arxiv, "_MIN_REQUEST_INTERVAL", 3.0)
    monkeypatch.setattr(arxiv, "time", SimpleNamespace(monotonic=lambda: now[0]))
    monkeypatch.setattr(arxiv, "asyncio", SimpleNamespace(sleep=sleep))
    _mock_client(monkeypatch, respond)

    results = await asyncio.gather(
        *(arxiv.search_arxiv(query) for query in ("one", "two", "three"))
    )

    assert all(json.loads(result)["data"]["items"] for result in results)
    assert requested_at == [100.0, 103.0, 106.0]
    assert slept == [3.0, 3.0]


@pytest.mark.parametrize("failure", ["http", "timeout", "xml", "atom"])
async def test_remote_failures_return_error_envelope(
    arxiv: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if failure == "timeout":
            raise httpx.ReadTimeout("arXiv timeout", request=request)
        if failure == "http":
            return httpx.Response(503, text="temporarily unavailable")
        if failure == "xml":
            return httpx.Response(200, text="<feed><entry>")
        error_entry = """<entry>
            <id>http://arxiv.org/api/errors#incorrect_id_format</id>
            <title>Error</title><summary>incorrect id format</summary>
        </entry>"""
        return httpx.Response(200, text=_feed(error_entry, total=0))

    _mock_client(monkeypatch, respond)
    payload = json.loads(await arxiv.search_arxiv("quantum"))
    _assert_envelope(payload)
    assert payload["data"]["items"] == []
    assert payload["data"]["error"]


@pytest.mark.parametrize(("locale", "authors_label"), [("en", "Authors:"), ("zh", "作者：")])
async def test_globally_enabled_plugin_is_callable_without_agent_opt_in(
    monkeypatch: pytest.MonkeyPatch,
    locale: str,
    authors_label: str,
) -> None:
    PluginRegistry.reset()
    try:
        loaded = load_plugin_dir(_PLUGIN_DIR, install_deps=False)
        assert loaded.manifest.id == "arxiv-search"
        assert [tool.name for tool in loaded.tools] == ["search_arxiv"]
        assert inspect.iscoroutinefunction(loaded.tools[0].fn)
        monkeypatch.setitem(loaded.tools[0].fn.__globals__, "_MIN_REQUEST_INTERVAL", 0)
        requests = _success_client(monkeypatch)
        global_plugins = {"arxiv-search": True}
        tools = build_plugin_tools(
            agent_plugins=expand_plugin_tools_default_on(
                {},
                registered_tools=[(tool.plugin_id, tool.name) for tool in loaded.tools],
                global_plugins=global_plugins,
            ),
            global_plugins=global_plugins,
        )
        assert len(tools) == 1
        payload = json.loads(
            await tools[0].ainvoke(
                {"query": "quantum"}, config={"configurable": {"locale": locale}}
            )
        )
        assert len(requests) == 1
        assert payload["data"]["items"][0]["id"] == "2501.01234v2"
        assert authors_label in payload["text"]
    finally:
        PluginRegistry.reset()


def test_market_installs_arxiv_plugin_and_ui_assets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    PluginRegistry.reset()
    try:
        manager = PluginManager(
            plugins_dir=tmp_path / "plugins",
            config_path=tmp_path / "config.json",
        )
        item = next(item for item in manager.list_market() if item.get("id") == "arxiv-search")
        assert not item.get("error")
        assert item["icon"] == "/api/plugins/market/arxiv-search/ui/icon.svg"
        loaded = manager.install_from_market("arxiv-search")
        assert [tool.name for tool in loaded.tools] == ["search_arxiv"]
        installed = tmp_path / "plugins" / "arxiv-search"
        for asset in ("icon.svg", "ui/index.js", "ui/manifest.json"):
            assert (installed / asset).is_file()
        config = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
        assert config["plugins"]["arxiv-search"]["enabled"] is True
        assert manager.global_enabled_map()["arxiv-search"] is True
    finally:
        PluginRegistry.reset()
