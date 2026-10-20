"""Tests for built-in tools."""

from __future__ import annotations

import re
from unittest.mock import patch

import httpx

from octop_harness.builtin.tools.current_time import CurrentTimeTool, current_time
from octop_harness.builtin.tools.web_fetch import web_fetch

_WEEKDAYS_EN = {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"}
_WEEKDAYS_ZH = {"周一", "周二", "周三", "周四", "周五", "周六", "周日"}
# ``YYYY-MM-DD HH:MM:SS <tzname> (UTC±HHMM) <Weekday> (<localized weekday>)``
_TS_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2}) (?P<time>\d{2}:\d{2}:\d{2}) "
    r"(?P<tzname>\S+) \(UTC(?P<offset>[+-]\d{4})\) "
    r"(?P<wd_en>[A-Z][a-z]+) \((?P<wd_zh>[\u4e00-\u9fff]+)\)$",
)


class TestCurrentTime:
    def test_default_returns_human_readable_with_weekday(self) -> None:
        result = current_time.invoke({})
        assert isinstance(result, str)
        match = _TS_RE.match(result)
        assert match is not None, f"unexpected format: {result!r}"
        assert match["wd_en"] in _WEEKDAYS_EN
        assert match["wd_zh"] in _WEEKDAYS_ZH

    def test_explicit_utc_timezone(self) -> None:
        result = current_time.invoke({"tz": "UTC"})
        match = _TS_RE.match(result)
        assert match is not None, result
        assert match["offset"] == "+0000"
        assert match["tzname"] == "UTC"

    def test_named_timezone_shanghai(self) -> None:
        result = current_time.invoke({"tz": "Asia/Shanghai"})
        match = _TS_RE.match(result)
        assert match is not None, result
        # CST is +08:00; offset in the rendered string must agree.
        assert match["offset"] == "+0800"

    def test_weekday_consistency(self) -> None:
        """English & Chinese weekday must always agree (same index)."""
        order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        zh_order = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        result = current_time.invoke({"tz": "UTC"})
        match = _TS_RE.match(result)
        assert match is not None
        assert order.index(match["wd_en"]) == zh_order.index(match["wd_zh"])

    def test_unknown_timezone_returns_error(self) -> None:
        result = current_time.invoke({"tz": "Mars/Olympus"})
        assert isinstance(result, str)
        assert result.startswith("Error:")
        assert "Unknown timezone" in result
        assert "Mars/Olympus" in result

    def test_default_timezone_when_tz_omitted(self) -> None:
        tool = CurrentTimeTool("Asia/Shanghai").as_tool()
        result = tool.invoke({})
        match = _TS_RE.match(result)
        assert match is not None, result
        assert match["offset"] == "+0800"


class TestWebFetch:
    def test_rejects_non_http_url(self) -> None:
        result = web_fetch.invoke({"url": "ftp://example.com"})
        assert isinstance(result, str)
        assert result.startswith("Error:")
        assert "http" in result
        assert "ftp://" in result

    def test_oversized_response_returns_error(self) -> None:
        huge = b"x" * (5 * 1024 * 1024 + 1)

        class FakeResponse:
            status_code = 200
            is_error = False
            content = huge
            text = ""
            headers = {"content-type": "application/octet-stream"}
            request = type("Req", (), {"url": "https://example.com/big"})()

        class FakeClient:
            def __init__(self, *args: object, **kwargs: object) -> None:
                pass

            def __enter__(self) -> FakeClient:
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def get(self, url: str) -> FakeResponse:
                return FakeResponse()

        with (
            patch(
                "octop_harness.builtin.tools.web_fetch.validate_agent_fetch_url",
                side_effect=lambda u: u,
            ),
            patch("octop_harness.builtin.tools.web_fetch.httpx.Client", FakeClient),
        ):
            result = web_fetch.invoke({"url": "https://example.com/big"})
        assert result.startswith("Error:")
        assert "exceeding" in result

    def test_html_to_markdown(self) -> None:
        html = "<html><body><h1>Title</h1><p>Hello <b>world</b></p></body></html>"

        class FakeResponse:
            status_code = 200
            is_error = False
            content = html.encode("utf-8")
            text = html
            headers = {"content-type": "text/html; charset=utf-8"}

        class FakeClient:
            def __init__(self, *args: object, **kwargs: object) -> None:
                pass

            def __enter__(self) -> FakeClient:
                return self

            def __exit__(self, *args: object) -> None:
                pass

            def get(self, url: str) -> FakeResponse:
                """Return canned HTML."""
                return FakeResponse()

        with patch("octop_harness.builtin.tools.web_fetch.httpx.Client", FakeClient):
            md = web_fetch.invoke({"url": "https://example.com"})
        # Basic markdown markers we expect from markdownify.
        assert "Title" in md
        assert "Hello" in md
        assert "world" in md

    def test_http_error_returned_as_string(self) -> None:
        """HTTP 4xx/5xx must surface as a plain ``Error: ...`` string so
        the agent's tool loop stays alive and the model can decide how
        to recover (try a different URL, switch tools, give up
        gracefully). Regression: previously ``raise_for_status`` made
        the whole graph terminate."""

        class FakeResponse:
            status_code = 404
            reason_phrase = "Not Found"
            is_error = True
            content = b"not found"
            text = "not found"
            headers = {"content-type": "text/plain"}
            request = type("Req", (), {"url": "https://example.com/missing"})()

        class FakeClient:
            def __init__(self, *args: object, **kwargs: object) -> None:
                pass

            def __enter__(self) -> FakeClient:
                return self

            def __exit__(self, *args: object) -> None:
                pass

            def get(self, url: str) -> FakeResponse:
                return FakeResponse()

        with patch("octop_harness.builtin.tools.web_fetch.httpx.Client", FakeClient):
            result = web_fetch.invoke({"url": "https://example.com/missing"})

        assert isinstance(result, str)
        assert result.startswith("Error: HTTP 404")
        assert "Not Found" in result
        assert "https://example.com/missing" in result

    def test_network_error_returned_as_string(self) -> None:
        """DNS / connection failures also turn into a string, not a raise."""

        class FakeClient:
            def __init__(self, *args: object, **kwargs: object) -> None:
                pass

            def __enter__(self) -> FakeClient:
                return self

            def __exit__(self, *args: object) -> None:
                pass

            def get(self, url: str) -> object:
                raise httpx.ConnectError("Name or service not known")

        with patch("octop_harness.builtin.tools.web_fetch.httpx.Client", FakeClient):
            result = web_fetch.invoke({"url": "https://no-such-host.invalid/"})

        assert isinstance(result, str)
        assert result.startswith("Error:")
        assert "ConnectError" in result or "cannot resolve" in result
