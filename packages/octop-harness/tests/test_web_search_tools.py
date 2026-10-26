"""Tests for ``octop_harness.builtin.tools.web_search``."""

from __future__ import annotations

import json
import sys
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from octop_harness.builtin.tools.web_search import load_web_search_tools
from octop_harness.builtin.tools.web_search._registry import (
    WEB_SEARCH_PROVIDERS,
    _missing_env,
    _provider_available,
)
from octop_harness.builtin.tools.web_search.brave import brave_search
from octop_harness.builtin.tools.web_search.deepseek import deepseek_search
from octop_harness.builtin.tools.web_search.doubao import doubao_search
from octop_harness.builtin.tools.web_search.exa import exa_search
from octop_harness.builtin.tools.web_search.google import google_search
from octop_harness.builtin.tools.web_search.kimi import kimi_search
from octop_harness.builtin.tools.web_search.searchfree import searchfree_search
from octop_harness.builtin.tools.web_search.tavily import tavily_search
from octop_harness.builtin.tools.web_search.yuanbao import yuanbao_search

# ---------------------------------------------------------------------------
# Registry — provider lookup, env-var gating, policy dispatch
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_known_providers(self) -> None:
        assert set(WEB_SEARCH_PROVIDERS) == {
            "tavily",
            "brave",
            "doubao",
            "deepseek",
            "exa",
            "google",
            "kimi",
            "yuanbao",
            "searchfree",
            "you",
        }

    def test_provider_available_all_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FOO", "x")
        monkeypatch.setenv("BAR", "y")
        assert _provider_available(("FOO", "BAR")) is True

    def test_provider_available_one_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FOO", "x")
        monkeypatch.delenv("BAR", raising=False)
        assert _provider_available(("FOO", "BAR")) is False

    def test_missing_env_lists_blanks(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FOO", "x")
        monkeypatch.setenv("BAR", "")
        monkeypatch.delenv("BAZ", raising=False)
        assert _missing_env(("FOO", "BAR", "BAZ")) == ["BAR", "BAZ"]


class TestLoadWebSearchTools:
    @pytest.fixture(autouse=True)
    def _clear_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for var in (
            "TAVILY_API_KEY",
            "BRAVE_API_KEY",
            "DOUBAO_SEARCH_API_KEY",
            "DEEPSEEK_API_KEY",
            "EXA_API_KEY",
            "GOOGLE_API_KEY",
            "GOOGLE_CSE_ID",
            "MOONSHOT_API_KEY",
            "TENCENTCLOUD_WSA_APIKEY",
            "YDC_API_KEY",
        ):
            monkeypatch.delenv(var, raising=False)

    def test_false_returns_empty(self) -> None:
        assert load_web_search_tools(False) == []

    def test_auto_with_no_env_still_includes_searchfree(self) -> None:
        # ``searchfree`` has no env requirement, so it always loads under
        # ``auto`` even when every other provider is unconfigured.
        names_auto = {t.name for t in load_web_search_tools("auto")}
        names_true = {t.name for t in load_web_search_tools(True)}
        assert names_auto == {"searchfree_search"}
        assert names_true == {"searchfree_search"}

    def test_auto_loads_only_configured_providers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TAVILY_API_KEY", "tav")
        monkeypatch.setenv("DEEPSEEK_API_KEY", "deep")
        monkeypatch.setenv("MOONSHOT_API_KEY", "kim")
        loaded = load_web_search_tools("auto")
        names = {t.name for t in loaded}
        # ``searchfree`` rides along regardless because its tuple is empty.
        assert names == {
            "tavily_search",
            "deepseek_search",
            "kimi_search",
            "searchfree_search",
        }

    def test_all_loads_every_provider(self) -> None:
        loaded = load_web_search_tools("all")
        names = {t.name for t in loaded}
        assert names == {
            "tavily_search",
            "brave_search",
            "doubao_search",
            "deepseek_search",
            "exa_search",
            "google_search",
            "kimi_search",
            "yuanbao_search",
            "searchfree_search",
            "you_search",
        }

    def test_auto_includes_you_only_with_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert "you_search" not in {t.name for t in load_web_search_tools("auto")}
        monkeypatch.setenv("YDC_API_KEY", "ydc")
        assert "you_search" in {t.name for t in load_web_search_tools("auto")}

    def test_explicit_you_works_without_key(self) -> None:
        assert [t.name for t in load_web_search_tools(["you"])] == ["you_search"]

    def test_explicit_list_loads_named_providers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TAVILY_API_KEY", "tav")
        monkeypatch.setenv("BRAVE_API_KEY", "brv")
        loaded = load_web_search_tools(["tavily", "brave"])
        names = {t.name for t in loaded}
        assert names == {"tavily_search", "brave_search"}

    def test_explicit_list_unknown_name_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown web-search provider"):
            load_web_search_tools(["bogus"])

    def test_explicit_list_missing_env_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match=r"env var.*missing"):
            load_web_search_tools(["tavily"])


# ---------------------------------------------------------------------------
# tavily_search
# ---------------------------------------------------------------------------


class TestTavilySearch:
    @pytest.fixture(autouse=True)
    def _clean(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    @pytest.mark.asyncio
    async def test_missing_api_key_returns_error(self) -> None:
        result = await tavily_search.ainvoke({"query": "x"})
        assert isinstance(result, str)
        assert "TAVILY_API_KEY" in result

    @pytest.mark.asyncio
    async def test_calls_sdk_when_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TAVILY_API_KEY", "secret")

        captured: dict[str, Any] = {}

        class _FakeTavily:
            def __init__(self, **kwargs: Any) -> None:
                captured["init"] = kwargs

            async def ainvoke(self, payload: dict[str, Any]) -> dict[str, Any]:
                captured["payload"] = payload
                return {"answer": "42", "results": []}

        fake_module = ModuleType("langchain_tavily")
        fake_module.TavilySearch = _FakeTavily  # type: ignore[attr-defined]
        with patch.dict(sys.modules, {"langchain_tavily": fake_module}):
            result = await tavily_search.ainvoke(
                {"query": "what is the answer", "max_results": 3, "search_depth": "advanced"},
            )
        parsed = json.loads(result)
        assert parsed == {"answer": "42", "results": []}
        assert captured["init"]["api_key"] == "secret"
        assert captured["init"]["max_results"] == 3
        assert captured["init"]["search_depth"] == "advanced"
        assert captured["payload"] == {"query": "what is the answer"}

    @pytest.mark.asyncio
    async def test_missing_package_returns_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TAVILY_API_KEY", "secret")
        with patch.dict(sys.modules, {"langchain_tavily": None}):
            result = await tavily_search.ainvoke({"query": "x"})
        assert "langchain-tavily" in result


# ---------------------------------------------------------------------------
# brave_search
# ---------------------------------------------------------------------------


class TestBraveSearch:
    @pytest.fixture(autouse=True)
    def _clean(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("BRAVE_API_KEY", raising=False)

    @pytest.mark.asyncio
    async def test_missing_api_key_returns_error(self) -> None:
        result = await brave_search.ainvoke({"query": "x"})
        assert "BRAVE_API_KEY" in result

    @pytest.mark.asyncio
    async def test_calls_sdk_when_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BRAVE_API_KEY", "secret")
        captured: dict[str, Any] = {}

        class _FakeBraveSearch:
            @classmethod
            def from_api_key(cls, *, api_key: str, search_kwargs: dict[str, Any]) -> _FakeBraveSearch:
                captured["api_key"] = api_key
                captured["search_kwargs"] = search_kwargs
                return cls()

            def run(self, query: str) -> str:
                captured["query"] = query
                return "raw brave result"

        fake_tools_module = ModuleType("langchain_community.tools")
        fake_tools_module.BraveSearch = _FakeBraveSearch  # type: ignore[attr-defined]
        # Building a fake parent package so the ``from langchain_community.tools import …``
        # import works.
        fake_pkg = ModuleType("langchain_community")
        fake_pkg.tools = fake_tools_module  # type: ignore[attr-defined]
        with patch.dict(
            sys.modules,
            {"langchain_community": fake_pkg, "langchain_community.tools": fake_tools_module},
        ):
            result = await brave_search.ainvoke({"query": "hello", "count": 7})
        assert result == "raw brave result"
        assert captured == {
            "api_key": "secret",
            "search_kwargs": {"count": 7},
            "query": "hello",
        }

    @pytest.mark.asyncio
    async def test_missing_package_returns_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BRAVE_API_KEY", "secret")
        with patch.dict(sys.modules, {"langchain_community.tools": None}):
            result = await brave_search.ainvoke({"query": "x"})
        assert "langchain-community" in result


# ---------------------------------------------------------------------------
# deepseek_search
# ---------------------------------------------------------------------------


class TestDeepSeekSearch:
    @pytest.fixture(autouse=True)
    def _clean(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    @pytest.mark.asyncio
    async def test_missing_api_key_returns_error(self) -> None:
        result = await deepseek_search.ainvoke({"query": "x"})
        assert "DEEPSEEK_API_KEY" in result

    @pytest.mark.asyncio
    async def test_calls_search_api_with_bounded_context(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DEEPSEEK_API_KEY", "secret")
        captured: dict[str, Any] = {}

        class _Response:
            status_code = 200

            def json(self) -> dict[str, Any]:
                return {
                    "results": [
                        {
                            "title": "DeepSeek",
                            "url": "https://example.com",
                            "summary": "A result",
                            "content": "",
                        }
                    ]
                }

        class _Client:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                captured["client"] = kwargs

            async def __aenter__(self) -> _Client:
                return self

            async def __aexit__(self, *args: object) -> None:
                return None

            async def post(
                self,
                url: str,
                *,
                headers: dict[str, str],
                json: dict[str, Any],
            ) -> _Response:
                captured["url"] = url
                captured["headers"] = headers
                captured["payload"] = json
                return _Response()

        from octop_harness.builtin.tools.web_search import deepseek as mod

        with patch.object(mod.httpx, "AsyncClient", _Client):
            result = await deepseek_search.ainvoke({"query": "agent search", "count": 3})

        assert json.loads(result)[0]["url"] == "https://example.com"
        assert captured["url"] == "https://api.deepseek.com/v1/tools/search"
        assert captured["headers"]["Authorization"] == "Bearer secret"
        assert captured["payload"] == {
            "query": "agent search",
            "count": 3,
            "need_content": False,
        }

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("payload", "message"),
        [
            ({"query": ""}, "1 to 128"),
            ({"query": "x" * 129}, "1 to 128"),
            ({"query": "x", "count": 0}, "between 1 and 50"),
            ({"query": "x", "count": 51}, "between 1 and 50"),
        ],
    )
    async def test_rejects_invalid_parameters(
        self,
        monkeypatch: pytest.MonkeyPatch,
        payload: dict[str, Any],
        message: str,
    ) -> None:
        monkeypatch.setenv("DEEPSEEK_API_KEY", "secret")
        result = await deepseek_search.ainvoke(payload)
        assert message in result

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("status", "message"),
        [(401, "authentication failed"), (402, "insufficient balance"), (429, "rate limit")],
    )
    async def test_maps_actionable_http_errors(
        self,
        monkeypatch: pytest.MonkeyPatch,
        status: int,
        message: str,
    ) -> None:
        monkeypatch.setenv("DEEPSEEK_API_KEY", "secret")

        class _Response:
            status_code = status

        class _Client:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                pass

            async def __aenter__(self) -> _Client:
                return self

            async def __aexit__(self, *args: object) -> None:
                return None

            async def post(self, *args: Any, **kwargs: Any) -> _Response:
                return _Response()

        from octop_harness.builtin.tools.web_search import deepseek as mod

        with patch.object(mod.httpx, "AsyncClient", _Client):
            result = await deepseek_search.ainvoke({"query": "x"})
        assert message in result


# ---------------------------------------------------------------------------
# google_search
# ---------------------------------------------------------------------------


class TestGoogleSearch:
    @pytest.fixture(autouse=True)
    def _clean(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_CSE_ID", raising=False)

    @pytest.mark.asyncio
    async def test_missing_both_env_vars_lists_them(self) -> None:
        result = await google_search.ainvoke({"query": "x"})
        assert "GOOGLE_API_KEY" in result
        assert "GOOGLE_CSE_ID" in result

    @pytest.mark.asyncio
    async def test_missing_one_env_var_lists_only_that_one(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GOOGLE_API_KEY", "k")
        result = await google_search.ainvoke({"query": "x"})
        assert "GOOGLE_CSE_ID" in result
        assert "GOOGLE_API_KEY" not in result

    @pytest.mark.asyncio
    async def test_calls_sdk_when_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GOOGLE_API_KEY", "k")
        monkeypatch.setenv("GOOGLE_CSE_ID", "c")
        captured: dict[str, Any] = {}

        class _FakeWrapper:
            def __init__(self, **kwargs: Any) -> None:
                captured["init"] = kwargs

            def results(self, query: str, num_results: int) -> list[dict[str, Any]]:
                captured["call"] = (query, num_results)
                return [{"title": "Hello", "link": "https://example.com"}]

        fake_utilities = ModuleType("langchain_community.utilities")
        fake_utilities.GoogleSearchAPIWrapper = _FakeWrapper  # type: ignore[attr-defined]
        fake_pkg = ModuleType("langchain_community")
        fake_pkg.utilities = fake_utilities  # type: ignore[attr-defined]
        with patch.dict(
            sys.modules,
            {"langchain_community": fake_pkg, "langchain_community.utilities": fake_utilities},
        ):
            result = await google_search.ainvoke({"query": "hi", "num_results": 3})
        parsed = json.loads(result)
        assert parsed == [{"title": "Hello", "link": "https://example.com"}]
        assert captured["init"]["google_api_key"] == "k"
        assert captured["init"]["google_cse_id"] == "c"
        assert captured["call"] == ("hi", 3)


# ---------------------------------------------------------------------------
# kimi_search
# ---------------------------------------------------------------------------


class TestKimiSearch:
    @pytest.fixture(autouse=True)
    def _clean(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)

    @pytest.mark.asyncio
    async def test_missing_api_key_returns_error(self) -> None:
        result = await kimi_search.ainvoke({"query": "x"})
        assert "MOONSHOT_API_KEY" in result

    @pytest.mark.asyncio
    async def test_calls_sdk_when_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MOONSHOT_API_KEY", "secret")
        captured: dict[str, Any] = {}

        # Build a fake ``openai`` module exposing ``AsyncOpenAI``.
        class _FakeChatCompletions:
            async def create(self, **kwargs: Any) -> Any:
                captured["call"] = kwargs
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content="answer"))],
                )

        class _FakeChat:
            def __init__(self) -> None:
                self.completions = _FakeChatCompletions()

        class _FakeAsyncOpenAI:
            def __init__(self, **kwargs: Any) -> None:
                captured["init"] = kwargs
                self.chat = _FakeChat()

        fake_module = ModuleType("openai")
        fake_module.AsyncOpenAI = _FakeAsyncOpenAI  # type: ignore[attr-defined]
        with patch.dict(sys.modules, {"openai": fake_module}):
            result = await kimi_search.ainvoke({"query": "hello"})
        assert result == "answer"
        assert captured["init"]["api_key"] == "secret"
        assert captured["init"]["base_url"].startswith("https://api.moonshot.cn")
        assert captured["call"]["model"].startswith("moonshot-")
        assert any(t.get("type") == "web_search" for t in captured["call"]["tools"])


# ---------------------------------------------------------------------------
# yuanbao_search
# ---------------------------------------------------------------------------


class TestYuanbaoSearch:
    @pytest.fixture(autouse=True)
    def _clean(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TENCENTCLOUD_WSA_APIKEY", raising=False)

    @pytest.mark.asyncio
    async def test_missing_api_key_returns_error(self) -> None:
        result = await yuanbao_search.ainvoke({"query": "x"})
        assert "TENCENTCLOUD_WSA_APIKEY" in result

    @pytest.mark.asyncio
    async def test_parses_stringified_pages(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TENCENTCLOUD_WSA_APIKEY", "sk-test")
        captured: dict[str, Any] = {}

        class _Resp:
            status_code = 200

            def json(self) -> dict[str, Any]:
                page = json.dumps(
                    {
                        "title": "三星堆",
                        "url": "https://example.com",
                        "passage": "摘要",
                        "site": "示例",
                        "date": "2024-06-07",
                        "score": 0.9,
                        "content": "long body",
                    },
                    ensure_ascii=False,
                )
                return {"Response": {"Pages": [page], "Query": "三星堆"}}

        class _FakeClient:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                pass

            async def __aenter__(self) -> _FakeClient:
                return self

            async def __aexit__(self, *args: object) -> None:
                """No-op."""

            async def post(self, url: str, headers: dict[str, str], json: dict[str, Any]) -> _Resp:
                captured["url"] = url
                captured["headers"] = headers
                captured["json"] = json
                return _Resp()

        from octop_harness.builtin.tools.web_search import yuanbao as mod

        with patch.object(mod.httpx, "AsyncClient", _FakeClient):
            result = await yuanbao_search.ainvoke({"query": "三星堆", "max_results": 5})
        assert captured["url"].endswith("/SearchPro")
        assert captured["headers"]["Authorization"] == "Bearer sk-test"
        assert captured["json"] == {"Query": "三星堆", "Cnt": 10}
        assert json.loads(result) == [
            {
                "title": "三星堆",
                "url": "https://example.com",
                "snippet": "摘要",
                "site": "示例",
                "date": "2024-06-07",
                "score": 0.9,
            }
        ]

    @pytest.mark.asyncio
    async def test_api_error_object(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TENCENTCLOUD_WSA_APIKEY", "sk-test")

        class _Resp:
            status_code = 200

            def json(self) -> dict[str, Any]:
                return {"Response": {"Error": {"Code": "UnauthorizedOperation", "Message": "bad key"}}}

        class _FakeClient:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                pass

            async def __aenter__(self) -> _FakeClient:
                return self

            async def __aexit__(self, *args: object) -> None:
                """No-op."""

            async def post(self, url: str, headers: dict[str, str], json: dict[str, Any]) -> _Resp:
                return _Resp()

        from octop_harness.builtin.tools.web_search import yuanbao as mod

        with patch.object(mod.httpx, "AsyncClient", _FakeClient):
            result = await yuanbao_search.ainvoke({"query": "hi"})
        assert "authentication failed" in result

    @pytest.mark.asyncio
    async def test_http_error_returns_plain_text(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TENCENTCLOUD_WSA_APIKEY", "sk-test")

        class _Resp:
            status_code = 503

            def json(self) -> dict[str, Any]:
                return {}

        class _FakeClient:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                pass

            async def __aenter__(self) -> _FakeClient:
                return self

            async def __aexit__(self, *args: object) -> None:
                """No-op."""

            async def post(self, url: str, headers: dict[str, str], json: dict[str, Any]) -> _Resp:
                return _Resp()

        from octop_harness.builtin.tools.web_search import yuanbao as mod

        with patch.object(mod.httpx, "AsyncClient", _FakeClient):
            result = await yuanbao_search.ainvoke({"query": "hi"})
        assert "HTTP 503" in result


# ---------------------------------------------------------------------------
# searchfree (zero-config public fallback)
# ---------------------------------------------------------------------------


class TestSearchFreeSearch:
    @pytest.mark.asyncio
    async def test_returns_results_array_when_wrapped(self) -> None:
        class _Resp:
            status_code = 200

            def json(self) -> dict[str, Any]:
                return {"results": [{"title": "Hi", "url": "https://example.com"}]}

        class _FakeClient:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                pass

            async def __aenter__(self) -> _FakeClient:
                return self

            async def __aexit__(self, *args: object) -> None:
                """No-op."""

            async def post(self, url: str, json: dict[str, Any]) -> _Resp:
                assert url.endswith("/api/search")
                assert json["query"] == "hello"
                return _Resp()

        from octop_harness.builtin.tools.web_search import searchfree as mod

        with patch.object(mod.httpx, "AsyncClient", _FakeClient):
            result = await searchfree_search.ainvoke({"query": "hello"})
        parsed = json.loads(result)
        assert parsed == [{"title": "Hi", "url": "https://example.com"}]

    @pytest.mark.asyncio
    async def test_returns_body_when_no_results_key(self) -> None:
        class _Resp:
            status_code = 200

            def json(self) -> list[dict[str, str]]:
                return [{"title": "Bare list"}]

        class _FakeClient:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                pass

            async def __aenter__(self) -> _FakeClient:
                return self

            async def __aexit__(self, *args: object) -> None:
                """No-op."""

            async def post(self, url: str, json: dict[str, Any]) -> _Resp:
                return _Resp()

        from octop_harness.builtin.tools.web_search import searchfree as mod

        with patch.object(mod.httpx, "AsyncClient", _FakeClient):
            result = await searchfree_search.ainvoke({"query": "hello"})
        parsed = json.loads(result)
        assert parsed == [{"title": "Bare list"}]

    @pytest.mark.asyncio
    async def test_http_error_returns_plain_text(self) -> None:
        class _Resp:
            status_code = 503

            def json(self) -> dict[str, Any]:
                return {}

        class _FakeClient:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                pass

            async def __aenter__(self) -> _FakeClient:
                return self

            async def __aexit__(self, *args: object) -> None:
                """No-op."""

            async def post(self, url: str, json: dict[str, Any]) -> _Resp:
                return _Resp()

        from octop_harness.builtin.tools.web_search import searchfree as mod

        with patch.object(mod.httpx, "AsyncClient", _FakeClient):
            result = await searchfree_search.ainvoke({"query": "hi"})
        assert "HTTP 503" in result

    @pytest.mark.asyncio
    async def test_network_failure_returns_plain_text(self) -> None:
        from octop_harness.builtin.tools.web_search import searchfree as mod

        class _FakeClient:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                pass

            async def __aenter__(self) -> _FakeClient:
                return self

            async def __aexit__(self, *args: object) -> None:
                """No-op."""

            async def post(self, url: str, json: dict[str, Any]) -> Any:
                raise mod.httpx.ConnectError("connection refused")

        with patch.object(mod.httpx, "AsyncClient", _FakeClient):
            result = await searchfree_search.ainvoke({"query": "hi"})
        assert "searchfree request failed" in result


# ---------------------------------------------------------------------------
# Integration: HarnessAgentConfig.web_search_tools
# ---------------------------------------------------------------------------


class TestConfigIntegration:
    def test_default_is_auto(self) -> None:
        from octop_harness import HarnessAgentConfig, ModelConfig, ProviderConfig

        cfg = HarnessAgentConfig(
            providers=[
                ProviderConfig(
                    id="p",
                    base_url="http://x",
                    api_key="x",
                    models=[ModelConfig(id="m", input=["text"])],
                ),
            ],
        )
        assert cfg.web_search_tools == "auto"

    def test_round_trips_through_to_dict(self) -> None:
        from octop_harness import HarnessAgentConfig, ModelConfig, ProviderConfig

        cfg = HarnessAgentConfig(
            providers=[
                ProviderConfig(
                    id="p",
                    base_url="http://x",
                    api_key="x",
                    models=[ModelConfig(id="m", input=["text"])],
                ),
            ],
            web_search_tools=["tavily", "kimi"],
        )
        data = cfg.to_dict()
        assert data["web_search_tools"] == ["tavily", "kimi"]
        restored = HarnessAgentConfig.from_dict(data)
        assert restored.web_search_tools == ["tavily", "kimi"]

    def test_round_trip_auto(self) -> None:
        from octop_harness import HarnessAgentConfig, ModelConfig, ProviderConfig

        cfg = HarnessAgentConfig(
            providers=[
                ProviderConfig(
                    id="p",
                    base_url="http://x",
                    api_key="x",
                    models=[ModelConfig(id="m", input=["text"])],
                ),
            ],
            web_search_tools="auto",
        )
        assert cfg.to_dict()["web_search_tools"] == "auto"
        restored = HarnessAgentConfig.from_dict(cfg.to_dict())
        assert restored.web_search_tools == "auto"


def test_load_web_search_tools_invokes_lazy_loader_only_when_needed() -> None:
    """``langchain_tavily`` etc. must NOT be imported just by importing the registry."""
    # Sanity: importing the registry should not have pulled the optional deps in.
    assert "langchain_tavily" not in sys.modules
    # And explicitly clear before we test.
    sys.modules.pop("langchain_tavily", None)
    # ``"all"`` policy imports the *@tool wrappers* but each tool only imports
    # its SDK at invocation time, so the SDK module still shouldn't be present.
    tools = load_web_search_tools("all")
    assert any(t.name == "tavily_search" for t in tools)
    assert "langchain_tavily" not in sys.modules


# ---------------------------------------------------------------------------
# you_search (keyless by default, YDC_API_KEY optional)
# ---------------------------------------------------------------------------


class _YouResp:
    def __init__(self, status_code: int = 200, body: Any = None, headers: dict[str, str] | None = None) -> None:
        self.status_code = status_code
        self._body = body
        self.headers = headers or {}

    def json(self) -> Any:
        return self._body


def _you_client(resp: _YouResp, calls: list[dict[str, Any]]) -> type:
    class _FakeClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> _FakeClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            """No-op."""

        async def get(self, url: str, params: dict[str, Any], headers: dict[str, str]) -> _YouResp:
            calls.append({"method": "GET", "url": url, "params": params, "headers": headers})
            return resp

        async def post(self, url: str, json: dict[str, Any], headers: dict[str, str]) -> _YouResp:
            calls.append({"method": "POST", "url": url, "json": json, "headers": headers})
            return resp

    return _FakeClient


_YOU_BODY = {
    "results": {
        "web": [
            {
                "url": "https://example.com",
                "title": "Example",
                "description": "desc",
                "snippets": ["s1"],
                "page_age": "2026-01-01T00:00:00",
            }
        ]
    }
}


class TestYouSearch:
    @pytest.fixture(autouse=True)
    def _clear_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("YDC_API_KEY", raising=False)

    @pytest.mark.asyncio
    async def test_keyless_uses_free_endpoint(self) -> None:
        from octop_harness.builtin.tools.web_search import you as mod

        calls: list[dict[str, Any]] = []
        with patch.object(mod.httpx, "AsyncClient", _you_client(_YouResp(body=_YOU_BODY), calls)):
            result = await mod.you_search.ainvoke({"query": "hello", "max_results": 3})
        assert calls[0]["method"] == "GET"
        assert calls[0]["url"] == mod.FREE_ENDPOINT
        assert calls[0]["params"] == {"query": "hello", "count": 3}
        assert calls[0]["headers"]["User-Agent"] == "youdotcom-integration/tencentcloud-octop-harness"
        assert "X-API-Key" not in calls[0]["headers"]
        assert json.loads(result) == [
            {
                "title": "Example",
                "url": "https://example.com",
                "description": "desc",
                "snippets": ["s1"],
                "page_age": "2026-01-01T00:00:00",
            }
        ]

    @pytest.mark.asyncio
    async def test_key_uses_keyed_endpoint(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from octop_harness.builtin.tools.web_search import you as mod

        monkeypatch.setenv("YDC_API_KEY", "ydc-test")
        calls: list[dict[str, Any]] = []
        with patch.object(mod.httpx, "AsyncClient", _you_client(_YouResp(body=_YOU_BODY), calls)):
            await mod.you_search.ainvoke({"query": "hello"})
        assert calls[0]["method"] == "POST"
        assert calls[0]["url"] == mod.KEYED_ENDPOINT
        assert calls[0]["json"] == {"query": "hello", "count": 5}
        assert calls[0]["headers"]["X-API-Key"] == "ydc-test"

    @pytest.mark.asyncio
    async def test_rate_limit_returns_plain_text(self) -> None:
        from octop_harness.builtin.tools.web_search import you as mod

        resp = _YouResp(status_code=429, headers={"Retry-After": "30"})
        with patch.object(mod.httpx, "AsyncClient", _you_client(resp, [])):
            result = await mod.you_search.ainvoke({"query": "hi"})
        assert "HTTP 429" in result
        assert "Retry after 30s" in result
        assert "YDC_API_KEY" in result

    @pytest.mark.asyncio
    async def test_bad_key_returns_plain_text(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from octop_harness.builtin.tools.web_search import you as mod

        monkeypatch.setenv("YDC_API_KEY", "bad")
        with patch.object(mod.httpx, "AsyncClient", _you_client(_YouResp(status_code=401), [])):
            result = await mod.you_search.ainvoke({"query": "hi"})
        assert "HTTP 401" in result

    @pytest.mark.asyncio
    async def test_empty_results(self) -> None:
        from octop_harness.builtin.tools.web_search import you as mod

        with patch.object(mod.httpx, "AsyncClient", _you_client(_YouResp(body={"results": {"web": []}}), [])):
            result = await mod.you_search.ainvoke({"query": "hi"})
        assert result == "No results found."

# ---------------------------------------------------------------------------
# doubao_search
# ---------------------------------------------------------------------------


def _fake_http_client(
    resp_status: int,
    resp_json: Any,
    *,
    captured: dict[str, Any] | None = None,
    raise_exc: Exception | None = None,
) -> type:
    """Build a fake ``httpx.AsyncClient`` class (same patch style as searchfree tests)."""

    class _Resp:
        status_code = resp_status
        text = "raw body"

        def json(self) -> Any:
            if isinstance(resp_json, Exception):
                raise resp_json
            return resp_json

    class _FakeClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> _FakeClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            """No-op."""

        async def post(self, url: str, **kwargs: Any) -> _Resp:
            if captured is not None:
                captured["url"] = url
                captured.update(kwargs)
            if raise_exc is not None:
                raise raise_exc
            return _Resp()

    return _FakeClient


class TestDoubaoSearch:
    @pytest.fixture(autouse=True)
    def _clean(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DOUBAO_SEARCH_API_KEY", raising=False)

    @pytest.mark.asyncio
    async def test_missing_api_key_returns_error(self) -> None:
        result = await doubao_search.ainvoke({"query": "x"})
        assert "DOUBAO_SEARCH_API_KEY" in result

    @pytest.mark.asyncio
    async def test_success_returns_trimmed_results(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DOUBAO_SEARCH_API_KEY", "secret")
        payload = {
            "ResponseMetadata": {"RequestId": "r1"},
            "Result": {
                "TotalDocCount": 2,
                "ErrorCode": 0,
                "ErrorMsg": "",
                "Documents": [
                    {
                        "Rank": 0,
                        "Title": "天安门",
                        "Url": "https://example.com/a",
                        "Snippet": [
                            {"Type": "text", "Text": "第一段摘要"},
                            {"Type": "image", "Image": {"ImageUrl": "x.jpg"}},
                            {"Type": "text", "Text": "第二段摘要"},
                        ],
                        "DocumentInfo": {"PublishTime": "2026-08-22T09:16:00+08:00"},
                        "HostInfo": {
                            "Hostname": "抖音百科",
                            "AuthorityLevel": "very_high",
                        },
                    },
                    {"Rank": 1, "Title": "另一条", "Url": "https://example.com/b"},
                ],
            },
        }
        captured: dict[str, Any] = {}
        fake = _fake_http_client(200, payload, captured=captured)
        from octop_harness.builtin.tools.web_search import doubao as mod

        with patch.object(mod.httpx, "AsyncClient", fake):
            result = await doubao_search.ainvoke({"query": "北京游玩", "max_results": 5})
        parsed = json.loads(result)
        assert parsed["total"] == 2
        assert parsed["results"][0] == {
            "title": "天安门",
            "url": "https://example.com/a",
            "snippet": "第一段摘要\n第二段摘要",
            "publish_time": "2026-08-22T09:16:00+08:00",
            "site": "抖音百科",
            "authority": "very_high",
        }
        assert parsed["results"][1]["snippet"] == ""
        assert parsed["results"][1]["site"] == ""
        # PascalCase request contract.
        assert captured["url"] == "https://open.feedcoopapi.com/search_api/global_search"
        assert captured["json"]["SearchType"] == "web"
        assert captured["json"]["Query"] == "北京游玩"
        assert captured["json"]["DocCount"] == 5
        assert captured["json"]["MaxSnippetLength"] == 1000
        assert captured["headers"]["Authorization"] == "Bearer secret"

    @pytest.mark.asyncio
    async def test_query_truncated_to_100_chars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DOUBAO_SEARCH_API_KEY", "secret")
        payload = {"Result": {"ErrorCode": 0, "Documents": []}}
        captured: dict[str, Any] = {}
        fake = _fake_http_client(200, payload, captured=captured)
        from octop_harness.builtin.tools.web_search import doubao as mod

        with patch.object(mod.httpx, "AsyncClient", fake):
            await doubao_search.ainvoke({"query": "q" * 300})
        assert len(captured["json"]["Query"]) == 100

    @pytest.mark.asyncio
    async def test_http_error_surfaces_api_error_code(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DOUBAO_SEARCH_API_KEY", "secret")
        payload = {
            "ResponseMetadata": {
                "Error": {"Code": "700901", "Message": "APIKey 无效"},
            },
            "Result": None,
        }
        fake = _fake_http_client(401, payload)
        from octop_harness.builtin.tools.web_search import doubao as mod

        with patch.object(mod.httpx, "AsyncClient", fake):
            result = await doubao_search.ainvoke({"query": "x"})
        assert "700901" in result
        assert "APIKey" in result

    @pytest.mark.asyncio
    async def test_business_error_code_surfaces(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DOUBAO_SEARCH_API_KEY", "secret")
        payload = {"Result": {"ErrorCode": 10406, "ErrorMsg": "免费搜索额度用尽"}}
        fake = _fake_http_client(200, payload)
        from octop_harness.builtin.tools.web_search import doubao as mod

        with patch.object(mod.httpx, "AsyncClient", fake):
            result = await doubao_search.ainvoke({"query": "x"})
        assert "10406" in result
        assert "额度" in result

    @pytest.mark.asyncio
    async def test_invalid_json_returns_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DOUBAO_SEARCH_API_KEY", "secret")
        fake = _fake_http_client(200, ValueError("bad json"))
        from octop_harness.builtin.tools.web_search import doubao as mod

        with patch.object(mod.httpx, "AsyncClient", fake):
            result = await doubao_search.ainvoke({"query": "x"})
        assert "invalid JSON" in result

    @pytest.mark.asyncio
    async def test_network_failure_returns_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DOUBAO_SEARCH_API_KEY", "secret")
        from octop_harness.builtin.tools.web_search import doubao as mod

        fake = _fake_http_client(200, {}, raise_exc=mod.httpx.ConnectError("refused"))
        with patch.object(mod.httpx, "AsyncClient", fake):
            result = await doubao_search.ainvoke({"query": "x"})
        assert "doubao_search request failed" in result



# ---------------------------------------------------------------------------
# exa_search
# ---------------------------------------------------------------------------


class TestExaSearch:
    @pytest.fixture(autouse=True)
    def _clean(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("EXA_API_KEY", raising=False)

    @pytest.mark.asyncio
    async def test_missing_api_key_returns_error(self) -> None:
        result = await exa_search.ainvoke({"query": "x"})
        assert "EXA_API_KEY" in result

    @pytest.mark.asyncio
    async def test_success_joins_highlights(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EXA_API_KEY", "secret")
        payload = {
            "results": [
                {
                    "title": "Exa result",
                    "url": "https://example.com/exa",
                    "highlights": ["highlight one", "highlight two"],
                    "publishedDate": "2026-08-22T00:00:00Z",
                    "author": "Alice",
                },
                {"title": "Bare", "url": "https://example.com/b", "text": "fallback text"},
            ],
        }
        captured: dict[str, Any] = {}
        fake = _fake_http_client(200, payload, captured=captured)
        from octop_harness.builtin.tools.web_search import exa as mod

        with patch.object(mod.httpx, "AsyncClient", fake):
            result = await exa_search.ainvoke({"query": "hello", "max_results": 2})
        parsed = json.loads(result)
        assert parsed["results"][0]["snippet"] == "highlight one highlight two"
        assert parsed["results"][0]["author"] == "Alice"
        assert parsed["results"][1]["snippet"] == "fallback text"
        assert captured["url"] == "https://api.exa.ai/search"
        assert captured["json"]["numResults"] == 2
        assert captured["json"]["contents"] == {"highlights": True}
        assert captured["headers"]["x-api-key"] == "secret"

    @pytest.mark.asyncio
    async def test_http_error_returns_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EXA_API_KEY", "secret")
        fake = _fake_http_client(403, {"message": "forbidden"})
        from octop_harness.builtin.tools.web_search import exa as mod

        with patch.object(mod.httpx, "AsyncClient", fake):
            result = await exa_search.ainvoke({"query": "x"})
        assert "HTTP 403" in result

    @pytest.mark.asyncio
    async def test_network_failure_returns_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EXA_API_KEY", "secret")
        from octop_harness.builtin.tools.web_search import exa as mod

        fake = _fake_http_client(200, {}, raise_exc=mod.httpx.ConnectError("refused"))
        with patch.object(mod.httpx, "AsyncClient", fake):
            result = await exa_search.ainvoke({"query": "x"})
        assert "exa_search request failed" in result


