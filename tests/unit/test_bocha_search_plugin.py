"""Unit tests for the bocha-search plugin's pure logic (plugins/bocha-search)."""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
from typing import Any

_PLUGIN_MAIN = Path(__file__).resolve().parents[2] / "plugins" / "bocha-search" / "main.py"


def _load_plugin() -> Any:
    spec = importlib.util.spec_from_file_location("bocha_search_plugin", _PLUGIN_MAIN)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mod = _load_plugin()


def _item(**overrides: Any) -> dict[str, Any]:
    base = {
        "name": "Example page",
        "url": "https://example.com/a",
        "snippet": "plain snippet",
        "summary": "",
        "datePublished": "",
        "dateLastCrawled": "",
    }
    base.update(overrides)
    return base


def _payload(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "code": 200,
        "data": {"webPages": {"value": []}},
    }
    base.update(overrides)
    return base


class TestBuildPayload:
    def test_defaults(self) -> None:
        payload = mod.build_payload("hello world", 0, "")
        assert payload == {
            "query": "hello world",
            "freshness": "noLimit",
            "summary": True,
            "count": 10,
        }

    def test_count_clamped(self) -> None:
        assert mod.build_payload("q", 100, "oneDay")["count"] == 50
        assert mod.build_payload("q", -3, "noLimit")["count"] == 10
        assert mod.build_payload("q", 7, "oneWeek")["count"] == 7

    def test_empty_query_rejected(self) -> None:
        import pytest

        with pytest.raises(ValueError, match="query is empty"):
            mod.build_payload("   ", 10, "noLimit")

    def test_invalid_freshness_rejected(self) -> None:
        import pytest

        with pytest.raises(ValueError, match="invalid freshness"):
            mod.build_payload("q", 10, "twoDays")


class TestParseResults:
    def test_summary_wins_over_snippet(self) -> None:
        results = mod.parse_results(
            _payload(data={"webPages": {"value": [_item(summary="AI 摘要")]}}), 10
        )
        assert results[0]["snippet"] == "AI 摘要"

    def test_snippet_fallback(self) -> None:
        results = mod.parse_results(_payload(data={"webPages": {"value": [_item()]}}), 10)
        assert results[0]["snippet"] == "plain snippet"

    def test_rfc3339_date_parsed(self) -> None:
        results = mod.parse_results(
            _payload(
                data={"webPages": {"value": [_item(datePublished="2026-09-01T08:30:00+08:00")]}}
            ),
            10,
        )
        assert results[0]["published"] == "2026-09-01T08:30:00+08:00"

    def test_plain_date_and_crawled_fallback(self) -> None:
        results = mod.parse_results(
            _payload(
                data={
                    "webPages": {"value": [_item(datePublished="2026-09-01", dateLastCrawled="")]}
                }
            ),
            10,
        )
        assert results[0]["published"] == "2026-09-01T00:00:00"
        crawled = mod.parse_results(
            _payload(
                data={
                    "webPages": {
                        "value": [
                            _item(
                                datePublished="not a date",
                                dateLastCrawled="2026-09-02 10:00:00",
                            )
                        ]
                    }
                }
            ),
            10,
        )
        assert crawled[0]["published"] == "2026-09-02T10:00:00"

    def test_skip_empty_name_and_url(self) -> None:
        results = mod.parse_results(
            _payload(data={"webPages": {"value": [_item(name="", url=""), _item()]}}),
            10,
        )
        assert len(results) == 1

    def test_truncated_to_limit(self) -> None:
        results = mod.parse_results(
            _payload(data={"webPages": {"value": [_item() for _ in range(8)]}}), 3
        )
        assert len(results) == 3

    def test_api_level_error_codes_raise(self) -> None:
        import pytest

        for code in (401, "500", "message"):
            with pytest.raises(ValueError, match="code"):
                mod.parse_results(_payload(code=code), 10)

    def test_string_success_code_accepted(self) -> None:
        results = mod.parse_results(_payload(code="200"), 10)
        assert results == []

    def test_empty_value_array(self) -> None:
        assert mod.parse_results(_payload(), 10) == []


class TestParseErrorBody:
    def test_message_shape(self) -> None:
        assert (
            mod.parse_error_body(401, '{"code":"401","message":"Invalid API KEY"}')
            == "Bocha API returned status 401: Invalid API KEY"
        )

    def test_msg_shape(self) -> None:
        assert (
            mod.parse_error_body(429, '{"code":"429","msg":"rate limited"}')
            == "Bocha API returned status 429: rate limited"
        )

    def test_plain_text_fallback(self) -> None:
        assert (
            mod.parse_error_body(502, "Bad Gateway") == "Bocha API returned status 502: Bad Gateway"
        )

    def test_long_body_clipped(self) -> None:
        detail = mod.parse_error_body(500, "x" * 10_000)
        assert len(detail) < 4_200

    def test_empty_body(self) -> None:
        assert mod.parse_error_body(500, "") == "Bocha API returned status 500"


class TestFormatAndTool:
    def test_format_empty(self) -> None:
        assert mod._format_results([]) == "No results found."

    def test_format_row(self) -> None:
        text = mod._format_results(
            [{"title": "T", "url": "https://e.com", "snippet": "S", "published": "2026-09-01"}]
        )
        assert "1. T" in text and "https://e.com" in text and "S" in text

    def test_unconfigured_tool_returns_error(self, monkeypatch: Any) -> None:
        monkeypatch.setattr(mod, "get_tool_config", lambda _name: None)
        result = asyncio.run(mod.bocha_search("hello"))
        assert result.startswith("Error: bocha_search is not configured")

    def test_bad_args_return_error_not_raise(self, monkeypatch: Any) -> None:
        monkeypatch.setattr(mod, "get_tool_config", lambda _name: {"api_key": "k"})
        assert asyncio.run(mod.bocha_search("", 10, "bad")).startswith("Error:")
