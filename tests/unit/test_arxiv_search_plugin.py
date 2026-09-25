"""arXiv bundled plugin queries the public Atom endpoint safely."""

from __future__ import annotations

import importlib.util
import json
import sys
from types import SimpleNamespace
from typing import Any

from octop.infra.agents.plugins.bundled import default_bundled_plugins_root

_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom"
      xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
  <opensearch:totalResults>42</opensearch:totalResults>
  <entry>
    <id>http://arxiv.org/abs/2501.12345v2</id>
    <title>  A  Test Paper\nwith Whitespace </title>
    <summary> A concise\nabstract. </summary>
    <published>2025-01-20T00:00:00Z</published>
    <updated>2025-01-21T00:00:00Z</updated>
    <author><name>Alice Example</name></author>
    <author><name>Bob Example</name></author>
    <category term="cs.AI" />
    <category term="cs.LG" />
    <arxiv:primary_category term="cs.AI" />
    <arxiv:version version="v1" />
    <arxiv:version version="v2" />
    <arxiv:doi>10.1000/example</arxiv:doi>
    <arxiv:journal_ref>Journal of Tests 1 (2025)</arxiv:journal_ref>
    <arxiv:comment>12 pages</arxiv:comment>
  </entry>
</feed>"""

_EMPTY_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
  <opensearch:totalResults>0</opensearch:totalResults>
</feed>"""


def _load_arxiv_search() -> Any:
    path = default_bundled_plugins_root() / "arxiv-search" / "main.py"
    spec = importlib.util.spec_from_file_location("bundled_arxiv_search", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeResponse:
    def __init__(self, text: str, *, status: int = 200) -> None:
        self.text = text
        self.status = status
        self.status_code = status

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise RuntimeError(f"http {self.status}")


class _RecordingAsyncClient:
    last_url = ""
    last_params: dict[str, str | int] = {}
    last_headers: dict[str, str] = {}
    response = _FakeResponse(_FEED)
    responses: list[_FakeResponse] = []
    calls = 0

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        type(self).last_headers = dict(kwargs.get("headers") or {})

    async def __aenter__(self) -> _RecordingAsyncClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def get(self, url: str, **kwargs: Any) -> _FakeResponse:
        type(self).calls += 1
        type(self).last_url = url
        type(self).last_params = dict(kwargs.get("params") or {})
        if type(self).responses:
            return type(self).responses.pop(0)
        return type(self).response


class _ToolContext:
    def __init__(self) -> None:
        self.tools: list[tuple[str, Any]] = []

    def tool(self, name: str, function: Any, **kwargs: Any) -> None:
        self.tools.append((name, function))


def _data(payload: str) -> dict[str, Any]:
    return json.loads(payload)["data"]


def _reset_client(*responses: _FakeResponse) -> None:
    _RecordingAsyncClient.last_url = ""
    _RecordingAsyncClient.last_params = {}
    _RecordingAsyncClient.last_headers = {}
    _RecordingAsyncClient.response = responses[-1] if responses else _FakeResponse(_FEED)
    _RecordingAsyncClient.responses = list(responses)
    _RecordingAsyncClient.calls = 0


async def test_search_builds_safe_params_and_parses_atom(monkeypatch: Any) -> None:
    module = _load_arxiv_search()
    _reset_client()
    monkeypatch.setattr(module.httpx, "AsyncClient", _RecordingAsyncClient)

    payload = await module.arxiv_search(
        'transformer "models"', category="cs.AI", limit=99, offset=-3, sort="updated"
    )

    assert _RecordingAsyncClient.last_url == "https://export.arxiv.org/api/query"
    assert _RecordingAsyncClient.last_headers["User-Agent"] == "Octop-arxiv-search/0.1.0"
    assert _RecordingAsyncClient.last_params == {
        "search_query": 'all:"transformer \\"models\\"" AND cat:cs.AI',
        "start": 0,
        "max_results": 20,
        "sortBy": "lastUpdatedDate",
        "sortOrder": "descending",
    }
    data = _data(payload)
    assert data["total_results"] == 42
    assert data["empty"] is False
    assert data["items"] == [
        {
            "id": "2501.12345v2",
            "title": "A Test Paper with Whitespace",
            "authors": ["Alice Example", "Bob Example"],
            "summary": "A concise abstract.",
            "categories": ["cs.AI", "cs.LG"],
            "primary_category": "cs.AI",
            "published": "2025-01-20T00:00:00Z",
            "updated": "2025-01-21T00:00:00Z",
            "version": "v2",
            "abs_url": "https://arxiv.org/abs/2501.12345v2",
            "pdf_url": "https://arxiv.org/pdf/2501.12345v2",
            "doi": "10.1000/example",
            "journal_ref": "Journal of Tests 1 (2025)",
            "comment": "12 pages",
        }
    ]


async def test_detail_queries_one_valid_paper_id(monkeypatch: Any) -> None:
    module = _load_arxiv_search()
    _reset_client()
    monkeypatch.setattr(module.httpx, "AsyncClient", _RecordingAsyncClient)

    payload = await module.arxiv_paper("hep-th/9901001")

    assert _RecordingAsyncClient.last_params == {"id_list": "hep-th/9901001", "max_results": 1}
    data = _data(payload)
    assert data["arxiv_id"] == "hep-th/9901001"
    assert data["paper"]["title"] == "A Test Paper with Whitespace"


async def test_empty_search_and_malformed_response_are_structured(monkeypatch: Any) -> None:
    module = _load_arxiv_search()
    monkeypatch.setattr(module.httpx, "AsyncClient", _RecordingAsyncClient)

    _reset_client(_FakeResponse(_EMPTY_FEED))
    empty = _data(await module.arxiv_search("quantum computing"))
    assert empty["empty"] is True
    assert empty["items"] == []

    _reset_client(_FakeResponse("not xml"))
    malformed = _data(await module.arxiv_search("quantum computing"))
    assert malformed["error"] == "invalid_response"


async def test_invalid_input_and_request_errors_do_not_call_or_raise(monkeypatch: Any) -> None:
    module = _load_arxiv_search()
    monkeypatch.setattr(module.httpx, "AsyncClient", _RecordingAsyncClient)

    _reset_client()
    assert _data(await module.arxiv_search("", category="cs.AI"))["error"] == "empty_query"
    assert _data(await module.arxiv_search(None))["error"] == "empty_query"
    assert _data(await module.arxiv_search("test", category="cs.AI AND all:x"))["error"] == (
        "invalid_category"
    )
    assert _data(await module.arxiv_search("test", sort="newest"))["error"] == "invalid_sort"
    assert (
        _data(await module.arxiv_paper("https://arxiv.org/abs/2501.12345"))["error"] == "invalid_id"
    )
    assert _RecordingAsyncClient.calls == 0

    _reset_client(_FakeResponse("failure", status=503))
    failed = _data(await module.arxiv_paper("2501.12345"))
    assert failed["error"] == "request_failed"


async def test_search_retries_one_406_after_arxiv_recommended_delay(monkeypatch: Any) -> None:
    module = _load_arxiv_search()
    _reset_client(_FakeResponse("not acceptable", status=406), _FakeResponse(_FEED))
    monkeypatch.setattr(module.httpx, "AsyncClient", _RecordingAsyncClient)
    delays: list[float] = []

    async def record_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr(
        module,
        "asyncio",
        SimpleNamespace(sleep=record_sleep),
        raising=False,
    )

    data = _data(await module.arxiv_search("LLM"))

    assert data.get("error") is None
    assert data["items"][0]["id"] == "2501.12345v2"
    assert _RecordingAsyncClient.calls == 2
    assert delays == [3.0]


def test_setup_registers_the_search_and_detail_tools() -> None:
    module = _load_arxiv_search()
    context = _ToolContext()

    module.setup(context)

    assert [name for name, _ in context.tools] == ["arxiv_search", "arxiv_paper"]


def test_plugin_loads_through_the_harness_registry(monkeypatch: Any) -> None:
    from octop_harness.plugins import PluginRegistry, load_plugin_dir

    monkeypatch.setitem(sys.modules, "harness_agent", None)
    monkeypatch.setitem(sys.modules, "harness_agent.plugins", None)
    PluginRegistry.reset()
    try:
        plugin = load_plugin_dir(
            default_bundled_plugins_root() / "arxiv-search",
            install_deps=False,
        )
        assert plugin.manifest.id == "arxiv-search"
        assert [tool.name for tool in plugin.tools] == ["arxiv_search", "arxiv_paper"]
    finally:
        PluginRegistry.reset()
