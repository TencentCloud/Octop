"""Tests for the ``browser_use`` built-in tool.

The real ``octop_browser.browser_tool`` would launch Chrome over CDP;
we replace that single entry-point with a fake during each test so the
suite is hermetic. We still construct the **real**
:class:`octop_browser.ToolResult` pydantic model so the wrapper's
projection of the result is genuinely exercised.
"""

from __future__ import annotations

import json
import sys
import types
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

# ``octop-browser`` ships in the dev group, so the real model is available.
from octop_browser import ActionMetrics, ToolResult

import octop_harness.builtin.tools.browser_use  # noqa: F401  # pylint: disable=unused-import
from octop_harness.builtin.tools.browser_use import browser_use

# The package's ``__init__`` rebinds ``octop_harness.builtin.tools.browser_use``
# to the StructuredTool, so reach for the underlying module via ``sys.modules``
# to access its private test helper.
_browser_use_pkg = sys.modules["octop_harness.builtin.tools.browser_use"]


def _make_metrics(action: str, **overrides: Any) -> ActionMetrics:
    base: dict[str, Any] = {
        "action": action,
        "duration_ms": 12,
        "dom_nodes_scanned": 0,
        "estimated_tokens": 0,
    }
    base.update(overrides)
    return ActionMetrics(**base)


@pytest.fixture(autouse=True)
def _reset_history() -> Iterator[None]:
    """Per-test isolation of the in-process action_history ring buffer."""
    _browser_use_pkg._reset_history_for_tests()
    yield
    _browser_use_pkg._reset_history_for_tests()


@pytest.fixture
def install_fake() -> Iterator[
    Callable[
        [Callable[..., ToolResult]],
        list[dict[str, Any]],
    ]
]:
    """Install a fake ``octop_browser`` module for the duration of the test.

    The fixture yields a registrar; tests call it with a function that
    builds the desired :class:`ToolResult` from the action+kwargs, and
    receive a ``captured`` list they can assert against.
    """
    contexts: list[Any] = []

    def register(builder: Callable[..., ToolResult]) -> list[dict[str, Any]]:
        captured: list[dict[str, Any]] = []

        async def fake_browser_tool(action: str, profile: str = "default", **kwargs: Any) -> ToolResult:
            captured.append({"action": action, "profile": profile, **kwargs})
            return builder(action=action, profile=profile, **kwargs)

        module = types.ModuleType("octop_browser")
        module.browser_tool = fake_browser_tool  # type: ignore[attr-defined]
        ctx = patch.dict(sys.modules, {"octop_browser": module})
        ctx.__enter__()
        contexts.append(ctx)
        return captured

    yield register

    for ctx in contexts:
        ctx.__exit__(None, None, None)


class TestArgumentForwarding:
    """Argument forwarding from wrapper kwargs to ``browser_tool``."""

    async def test_navigate_passes_url(
        self,
        install_fake: Callable[..., list[dict[str, Any]]],
    ) -> None:
        def builder(*, action: str, **_: Any) -> ToolResult:
            if action == "list_tabs":
                return ToolResult(
                    success=True,
                    content="[T-1] Other — https://other.example/",
                    metrics=_make_metrics(action),
                )
            return ToolResult(
                success=True,
                content="navigated",
                metrics=_make_metrics(action),
            )

        captured = install_fake(builder)
        result = await browser_use.ainvoke({"action": "navigate", "url": "https://example.com", "profile": "work"})
        assert isinstance(result, str)

        payload = json.loads(result)
        assert payload["tool"] == "browser_use"
        assert payload["action"] == "navigate"
        assert payload["profile"] == "work"
        assert payload["success"] is True
        assert payload["content"] == "navigated"
        assert payload["metrics"]["duration_ms"] == 12

        assert list(captured) == [
            {"action": "list_tabs", "profile": "work"},
            {"action": "navigate", "profile": "work", "url": "https://example.com"},
        ]

    async def test_only_set_kwargs_forwarded(
        self,
        install_fake: Callable[..., list[dict[str, Any]]],
    ) -> None:
        """``None`` kwargs must be dropped before reaching browser_tool."""

        def builder(*, action: str, **_: Any) -> ToolResult:
            return ToolResult(success=True, content="", metrics=_make_metrics(action))

        captured = install_fake(builder)
        await browser_use.ainvoke({"action": "dom_tree", "level": "interactive"})

        assert list(captured) == [{"action": "dom_tree", "profile": "default", "level": "interactive"}]

    async def test_click_with_ref(self, install_fake: Callable[..., list[dict[str, Any]]]) -> None:
        def builder(*, action: str, **_: Any) -> ToolResult:
            return ToolResult(success=True, content="clicked", metrics=_make_metrics(action))

        captured = install_fake(builder)
        await browser_use.ainvoke({"action": "click", "ref": "btn_2"})
        assert list(captured) == [{"action": "click", "profile": "default", "ref": "btn_2"}]

    async def test_type_with_text(self, install_fake: Callable[..., list[dict[str, Any]]]) -> None:
        def builder(*, action: str, **_: Any) -> ToolResult:
            return ToolResult(success=True, content="typed", metrics=_make_metrics(action))

        captured = install_fake(builder)
        await browser_use.ainvoke({"action": "type", "text": "hello", "ref": "inp_1"})
        assert list(captured) == [{"action": "type", "profile": "default", "text": "hello", "ref": "inp_1"}]

    async def test_scroll_with_direction_and_amount(self, install_fake: Callable[..., list[dict[str, Any]]]) -> None:
        def builder(*, action: str, **_: Any) -> ToolResult:
            return ToolResult(success=True, content="scrolled", metrics=_make_metrics(action))

        captured = install_fake(builder)
        await browser_use.ainvoke({"action": "scroll", "direction": "down", "amount": 600})
        assert list(captured) == [
            {
                "action": "scroll",
                "profile": "default",
                "direction": "down",
                "amount": 600,
            }
        ]

    async def test_eval_js_with_expression(self, install_fake: Callable[..., list[dict[str, Any]]]) -> None:
        def builder(*, action: str, expression: str = "", **_: Any) -> ToolResult:
            return ToolResult(
                success=True,
                content=f"eval:{expression}",
                metrics=_make_metrics(action),
            )

        captured = install_fake(builder)
        result = await browser_use.ainvoke({"action": "eval_js", "expression": "document.title"})
        assert isinstance(result, str)

        payload = json.loads(result)
        assert payload["content"] == "eval:document.title"
        assert list(captured) == [
            {
                "action": "eval_js",
                "profile": "default",
                "expression": "document.title",
            }
        ]


class TestActionHistory:
    """Per-profile ring buffer surfaced in every JSON envelope."""

    async def test_history_grows_per_profile(self, install_fake: Callable[..., list[dict[str, Any]]]) -> None:
        def builder(*, action: str, **_: Any) -> ToolResult:
            return ToolResult(success=True, content="ok", metrics=_make_metrics(action))

        install_fake(builder)
        first = json.loads(await browser_use.ainvoke({"action": "navigate", "url": "https://a.com", "profile": "p"}))
        second = json.loads(await browser_use.ainvoke({"action": "click", "ref": "btn_1", "profile": "p"}))
        third = json.loads(await browser_use.ainvoke({"action": "type", "text": "x", "profile": "p"}))

        assert first["total_actions_in_session"] == 1
        assert first["action_history"] == [{"action": "navigate", "success": True}]

        assert third["total_actions_in_session"] == 3
        assert [e["action"] for e in third["action_history"]] == [
            "navigate",
            "click",
            "type",
        ]
        # All three reached the underlying tool.
        assert second["success"] is True

    async def test_history_isolated_between_profiles(self, install_fake: Callable[..., list[dict[str, Any]]]) -> None:
        def builder(*, action: str, **_: Any) -> ToolResult:
            return ToolResult(success=True, content="ok", metrics=_make_metrics(action))

        install_fake(builder)
        await browser_use.ainvoke({"action": "navigate", "url": "https://a", "profile": "alice"})
        await browser_use.ainvoke({"action": "navigate", "url": "https://b", "profile": "alice"})
        bob_payload = json.loads(
            await browser_use.ainvoke({"action": "navigate", "url": "https://c", "profile": "bob"})
        )

        # Bob's first action should not see alice's history.
        assert bob_payload["total_actions_in_session"] == 1
        assert bob_payload["action_history"] == [{"action": "navigate", "success": True}]

    async def test_history_records_failures(self, install_fake: Callable[..., list[dict[str, Any]]]) -> None:
        def builder(*, action: str, **_: Any) -> ToolResult:
            return ToolResult(
                success=False,
                content="",
                error="boom",
                metrics=_make_metrics(action),
            )

        install_fake(builder)
        payload = json.loads(await browser_use.ainvoke({"action": "click", "ref": "btn_x"}))
        assert payload["success"] is False
        assert payload["error"] == "boom"
        assert payload["action_history"] == [{"action": "click", "success": False}]

    async def test_history_window_caps_at_twenty(self, install_fake: Callable[..., list[dict[str, Any]]]) -> None:
        def builder(*, action: str, **_: Any) -> ToolResult:
            return ToolResult(success=True, content="ok", metrics=_make_metrics(action))

        install_fake(builder)
        last_payload: dict[str, Any] = {}
        for i in range(25):
            raw = await browser_use.ainvoke({"action": "scroll", "amount": i})
            last_payload = json.loads(raw)

        assert last_payload["total_actions_in_session"] == 25
        # Only the last 20 are surfaced.
        assert len(last_payload["action_history"]) == 20


class TestScreenshotMultimodal:
    """``screenshot`` returns multimodal blocks on success."""

    async def test_default_screenshot_returns_image_and_text_blocks(
        self,
        install_fake: Callable[..., list[dict[str, Any]]],
        tmp_path: Path,
    ) -> None:
        png_path = tmp_path / "shot.png"

        def builder(*, action: str, **_: Any) -> ToolResult:
            png_path.write_bytes(b"\x89PNG\r\n\x1a\n")
            return ToolResult(
                success=True,
                content=str(png_path),
                metrics=_make_metrics(action, screenshot_size_kb=42),
                metadata={
                    "url": "https://example.com",
                    "title": "Example",
                    "full_page": False,
                    "width": 1280,
                    "height": 800,
                },
            )

        captured = install_fake(builder)
        result = await browser_use.ainvoke({"action": "screenshot"})

        # Multimodal block list, not JSON.
        assert isinstance(result, list)
        assert len(result) == 2

        image_block, text_block = result
        assert image_block["type"] == "image"
        assert image_block["filename"] == "shot.png"
        assert image_block["path"] == str(png_path.absolute())
        assert image_block["source"]["type"] == "url"
        assert image_block["source"]["url"].startswith("file://")
        assert image_block["source"]["url"].endswith("shot.png")
        assert image_block["source"]["media_type"] == "image/png"

        assert text_block["type"] == "text"
        text = text_block["text"]
        assert str(png_path) in text
        assert "42 KB" in text
        assert "1280x800" in text
        assert "page_title: Example" in text
        assert "page_url: https://example.com" in text
        # Ring buffer is surfaced inside the text block too.
        assert "recent_actions" in text

        assert list(captured) == [{"action": "screenshot", "profile": "default"}]

    async def test_full_page_flag_forwarded_and_summarised(
        self,
        install_fake: Callable[..., list[dict[str, Any]]],
        tmp_path: Path,
    ) -> None:
        target = tmp_path / "fp.png"

        def builder(*, action: str, full_page: bool = False, **_: Any) -> ToolResult:
            target.write_bytes(b"\x89PNG\r\n\x1a\n")
            return ToolResult(
                success=True,
                content=str(target),
                metrics=_make_metrics(action, screenshot_size_kb=2048),
                metadata={"full_page": full_page, "width": 1425, "height": 7419},
            )

        captured = install_fake(builder)
        result = await browser_use.ainvoke({"action": "screenshot", "full_page": True})

        assert isinstance(result, list)
        text = result[1]["text"]
        assert "full_page" in text
        assert "2048 KB" in text
        assert "1425x7419" in text

        assert list(captured) == [{"action": "screenshot", "profile": "default", "full_page": True}]

    async def test_crop_with_ref(
        self,
        install_fake: Callable[..., list[dict[str, Any]]],
        tmp_path: Path,
    ) -> None:
        out = tmp_path / "crop.png"

        def builder(*, action: str, **_: Any) -> ToolResult:
            out.write_bytes(b"\x89PNG\r\n\x1a\n")
            return ToolResult(
                success=True,
                content=str(out),
                metrics=_make_metrics(action),
            )

        captured = install_fake(builder)
        result = await browser_use.ainvoke({"action": "screenshot", "crop": True, "ref": "btn_5"})
        assert isinstance(result, list)
        assert result[0]["filename"] == "crop.png"

        assert list(captured) == [
            {
                "action": "screenshot",
                "profile": "default",
                "crop": True,
                "ref": "btn_5",
            }
        ]

    async def test_explicit_output_path(
        self,
        install_fake: Callable[..., list[dict[str, Any]]],
        tmp_path: Path,
    ) -> None:
        out = tmp_path / "out.png"

        def builder(*, action: str, path: str | None = None, **_: Any) -> ToolResult:
            if path:
                Path(path).write_bytes(b"\x89PNG\r\n\x1a\n")
            return ToolResult(
                success=True,
                content=path or "",
                metrics=_make_metrics(action),
            )

        captured = install_fake(builder)
        result = await browser_use.ainvoke({"action": "screenshot", "path": str(out)})

        assert isinstance(result, list)
        assert result[0]["path"] == str(out.absolute())
        assert out.is_file()

        assert list(captured) == [{"action": "screenshot", "profile": "default", "path": str(out)}]

    async def test_screenshot_failure_falls_back_to_json(
        self,
        install_fake: Callable[..., list[dict[str, Any]]],
    ) -> None:
        """Failures are visible to the agent as JSON, not silently dropped."""

        def builder(*, action: str, **_: Any) -> ToolResult:
            return ToolResult(
                success=False,
                content="",
                error="screenshot timeout",
                metrics=_make_metrics(action),
            )

        install_fake(builder)
        result = await browser_use.ainvoke({"action": "screenshot"})

        assert isinstance(result, str)
        payload = json.loads(result)
        assert payload["success"] is False
        assert payload["error"] == "screenshot timeout"
        assert payload["action_history"] == [{"action": "screenshot", "success": False}]

    async def test_screenshot_missing_file_falls_back_to_json(
        self,
        install_fake: Callable[..., list[dict[str, Any]]],
        tmp_path: Path,
    ) -> None:
        """If browser_tool says success but the PNG isn't there, surface JSON."""
        ghost = tmp_path / "ghost.png"  # never written

        def builder(*, action: str, **_: Any) -> ToolResult:
            return ToolResult(
                success=True,
                content=str(ghost),
                metrics=_make_metrics(action),
            )

        install_fake(builder)
        result = await browser_use.ainvoke({"action": "screenshot"})
        assert isinstance(result, str)
        payload = json.loads(result)
        assert payload["success"] is True
        assert payload["content"] == str(ghost)

    async def test_screenshot_after_navigate_flow(
        self,
        install_fake: Callable[..., list[dict[str, Any]]],
        tmp_path: Path,
    ) -> None:
        """End-to-end-ish: navigate -> screenshot using the same profile.

        Verifies the multimodal block is returned for screenshot AND that
        the action_history surfaces both steps.
        """
        out = tmp_path / "after_nav.png"

        def builder(*, action: str, **kwargs: Any) -> ToolResult:
            if action == "list_tabs":
                return ToolResult(
                    success=True,
                    content="[T-1] Other — https://other.example/",
                    metrics=_make_metrics(action),
                )
            if action == "navigate":
                return ToolResult(
                    success=True,
                    content=f"loaded {kwargs.get('url', '')}",
                    metrics=_make_metrics(action),
                )
            if action == "screenshot":
                target = kwargs.get("path") or str(out)
                Path(target).write_bytes(b"\x89PNG\r\n\x1a\n")
                return ToolResult(
                    success=True,
                    content=target,
                    metrics=_make_metrics(action, screenshot_size_kb=8),
                    metadata={"url": "https://example.com", "title": "Example"},
                )
            raise AssertionError(f"unexpected action {action}")  # pragma: no cover

        captured = install_fake(builder)

        nav_raw = await browser_use.ainvoke(
            {
                "action": "navigate",
                "url": "https://example.com",
                "profile": "demo",
            }
        )
        shot_result = await browser_use.ainvoke({"action": "screenshot", "profile": "demo", "path": str(out)})

        assert isinstance(nav_raw, str)
        nav_payload = json.loads(nav_raw)
        assert nav_payload["content"] == "loaded https://example.com"
        assert nav_payload["action_history"] == [{"action": "navigate", "success": True}]

        assert isinstance(shot_result, list)
        text = shot_result[1]["text"]
        assert str(out) in text
        # Both nav and screenshot should appear in recent_actions.
        assert "navigate" in text
        assert "screenshot" in text

        assert all(c["profile"] == "demo" for c in captured)
        assert [c["action"] for c in captured] == ["list_tabs", "navigate", "screenshot"]


class TestActionAliasesAndValidation:
    """Action aliases and pre-flight parameter validation."""

    async def test_goto_alias_forwards_as_navigate(self, install_fake: Callable[..., list[dict[str, Any]]]) -> None:
        def builder(*, action: str, **_: Any) -> ToolResult:
            if action == "list_tabs":
                return ToolResult(success=True, content="", metrics=_make_metrics(action))
            return ToolResult(success=True, content="ok", metrics=_make_metrics(action))

        captured = install_fake(builder)
        payload = json.loads(await browser_use.ainvoke({"action": "goto", "url": "https://a.com"}))
        assert payload["action"] == "goto"
        assert payload["success"] is True
        assert list(captured) == [
            {"action": "list_tabs", "profile": "default"},
            {"action": "navigate", "profile": "default", "url": "https://a.com"},
        ]

    async def test_snapshot_alias_forwards_as_screenshot(
        self,
        install_fake: Callable[..., list[dict[str, Any]]],
        tmp_path: Path,
    ) -> None:
        out = tmp_path / "snap.png"

        def builder(*, action: str, **_: Any) -> ToolResult:
            out.write_bytes(b"\x89PNG\r\n\x1a\n")
            return ToolResult(success=True, content=str(out), metrics=_make_metrics(action))

        captured = install_fake(builder)
        result = await browser_use.ainvoke({"action": "snapshot"})
        assert isinstance(result, list)
        assert list(captured) == [{"action": "screenshot", "profile": "default"}]

    async def test_navigate_without_url_returns_clear_error(self) -> None:
        payload = json.loads(await browser_use.ainvoke({"action": "navigate", "profile": "default"}))
        assert payload["success"] is False
        assert "url" in payload["error"].lower()
        assert "navigate requires" in payload["error"]

    async def test_target_url_used_when_url_missing(self, install_fake: Callable[..., list[dict[str, Any]]]) -> None:
        def builder(*, action: str, **_: Any) -> ToolResult:
            if action == "list_tabs":
                return ToolResult(success=True, content="", metrics=_make_metrics(action))
            return ToolResult(success=True, content="ok", metrics=_make_metrics(action))

        captured = install_fake(builder)
        await browser_use.ainvoke({"action": "navigate", "target_url": "https://b.com"})
        assert list(captured) == [
            {"action": "list_tabs", "profile": "default"},
            {"action": "navigate", "profile": "default", "url": "https://b.com"},
        ]

    async def test_query_alias_used_for_navigate(self, install_fake: Callable[..., list[dict[str, Any]]]) -> None:
        def builder(*, action: str, **_: Any) -> ToolResult:
            if action == "list_tabs":
                return ToolResult(success=True, content="", metrics=_make_metrics(action))
            return ToolResult(success=True, content="ok", metrics=_make_metrics(action))

        captured = install_fake(builder)
        await browser_use.ainvoke({"action": "navigate", "query": "https://c.com"})
        assert list(captured) == [
            {"action": "list_tabs", "profile": "default"},
            {"action": "navigate", "profile": "default", "url": "https://c.com"},
        ]

    async def test_scroll_down_sets_direction(self, install_fake: Callable[..., list[dict[str, Any]]]) -> None:
        def builder(*, action: str, **_: Any) -> ToolResult:
            return ToolResult(success=True, content="ok", metrics=_make_metrics(action))

        captured = install_fake(builder)
        await browser_use.ainvoke({"action": "scroll_down", "amount": 3})
        assert list(captured) == [{"action": "scroll", "profile": "default", "direction": "down", "amount": 3}]


class TestTabsAndErrors:
    async def test_new_tab_with_url(self, install_fake: Callable[..., list[dict[str, Any]]]) -> None:
        def builder(*, action: str, **_: Any) -> ToolResult:
            if action == "list_tabs":
                return ToolResult(
                    success=True,
                    content="[T-1] Other — https://other.example/",
                    metrics=_make_metrics(action),
                )
            return ToolResult(success=True, content="tab-id-42", metrics=_make_metrics(action))

        captured = install_fake(builder)
        await browser_use.ainvoke({"action": "new_tab", "url": "https://b.com"})

        assert list(captured) == [
            {"action": "list_tabs", "profile": "default"},
            {"action": "new_tab", "profile": "default", "url": "https://b.com"},
        ]

    async def test_new_tab_reuses_existing_matching_url(
        self,
        install_fake: Callable[..., list[dict[str, Any]]],
    ) -> None:
        def builder(*, action: str, tab_id: str = "", **_: Any) -> ToolResult:
            if action == "list_tabs":
                return ToolResult(
                    success=True,
                    content="[TAB-1] 天气网 — https://www.weather.com.cn/",
                    metrics=_make_metrics(action),
                )
            if action == "switch_tab":
                assert tab_id == "TAB-1"
                return ToolResult(
                    success=True,
                    content="Activated tab TAB-1",
                    metrics=_make_metrics(action),
                )
            raise AssertionError(f"unexpected action {action}")

        captured = install_fake(builder)
        result = await browser_use.ainvoke({"action": "new_tab", "url": "https://www.weather.com.cn"})

        assert isinstance(result, str)
        payload = json.loads(result)
        assert payload["action"] == "new_tab"
        assert payload["success"] is True
        assert payload["content"] == "Reused existing tab TAB-1 for https://www.weather.com.cn"
        assert payload["metadata"]["reused_existing_tab"] is True
        assert payload["metadata"]["matched_url"] == "https://www.weather.com.cn/"
        assert payload["action_history"] == [{"action": "new_tab", "success": True}]
        assert list(captured) == [
            {"action": "list_tabs", "profile": "default"},
            {"action": "switch_tab", "profile": "default", "tab_id": "TAB-1"},
        ]

    async def test_new_tab_reuses_matching_url_from_structured_tab_metadata(
        self,
        install_fake: Callable[..., list[dict[str, Any]]],
    ) -> None:
        def builder(*, action: str, tab_id: str = "", **_: Any) -> ToolResult:
            if action == "list_tabs":
                return ToolResult(
                    success=True,
                    content="[TAB-1] Title — With dash — not-a-url",
                    metrics=_make_metrics(action),
                    metadata={
                        "tabs": [
                            {
                                "tab_id": "TAB-1",
                                "url": "https://www.weather.com.cn/",
                                "title": "Title — With dash",
                                "active": False,
                            }
                        ]
                    },
                )
            if action == "switch_tab":
                assert tab_id == "TAB-1"
                return ToolResult(
                    success=True,
                    content="Activated tab TAB-1",
                    metrics=_make_metrics(action),
                )
            raise AssertionError(f"unexpected action {action}")

        captured = install_fake(builder)
        result = await browser_use.ainvoke({"action": "new_tab", "url": "https://www.weather.com.cn"})

        assert isinstance(result, str)
        payload = json.loads(result)
        assert payload["success"] is True
        assert payload["metadata"]["reused_existing_tab"] is True
        assert payload["metadata"]["matched_url"] == "https://www.weather.com.cn/"
        assert list(captured) == [
            {"action": "list_tabs", "profile": "default"},
            {"action": "switch_tab", "profile": "default", "tab_id": "TAB-1"},
        ]

    async def test_navigate_reuses_existing_matching_url_after_redirect(
        self,
        install_fake: Callable[..., list[dict[str, Any]]],
    ) -> None:
        def builder(*, action: str, tab_id: str = "", **_: Any) -> ToolResult:
            if action == "list_tabs":
                return ToolResult(
                    success=True,
                    content=("[WB] 微博 — https://weibo.com/newlogin?tabtype=weibo&url=https%3A%2F%2Fweibo.com%2F"),
                    metrics=_make_metrics(action),
                )
            if action == "switch_tab":
                assert tab_id == "WB"
                return ToolResult(
                    success=True,
                    content="Activated tab WB",
                    metrics=_make_metrics(action),
                )
            raise AssertionError(f"unexpected action {action}")

        captured = install_fake(builder)
        result = await browser_use.ainvoke({"action": "navigate", "url": "https://weibo.com/"})

        assert isinstance(result, str)
        payload = json.loads(result)
        assert payload["action"] == "navigate"
        assert payload["success"] is True
        assert payload["metadata"]["reused_existing_tab"] is True
        assert list(captured) == [
            {"action": "list_tabs", "profile": "default"},
            {"action": "switch_tab", "profile": "default", "tab_id": "WB"},
        ]

    async def test_switch_tab_passes_tab_id(self, install_fake: Callable[..., list[dict[str, Any]]]) -> None:
        def builder(*, action: str, **_: Any) -> ToolResult:
            return ToolResult(success=True, content="switched", metrics=_make_metrics(action))

        captured = install_fake(builder)
        await browser_use.ainvoke({"action": "switch_tab", "tab_id": "T-1"})

        assert list(captured) == [{"action": "switch_tab", "profile": "default", "tab_id": "T-1"}]

    async def test_close_session_propagates(self, install_fake: Callable[..., list[dict[str, Any]]]) -> None:
        def builder(*, action: str, **_: Any) -> ToolResult:
            return ToolResult(
                success=True,
                content="Session 'work' closed.",
                metrics=_make_metrics(action),
            )

        captured = install_fake(builder)
        result = await browser_use.ainvoke({"action": "close_session", "profile": "work"})
        assert isinstance(result, str)

        payload = json.loads(result)
        assert payload["success"] is True
        assert "closed" in payload["content"]
        assert list(captured) == [{"action": "close_session", "profile": "work"}]

    async def test_close_session_can_terminate_chrome(self, install_fake: Callable[..., list[dict[str, Any]]]) -> None:
        def builder(*, action: str, **_: Any) -> ToolResult:
            return ToolResult(
                success=True,
                content="Session 'work' closed.",
                metrics=_make_metrics(action),
            )

        captured = install_fake(builder)
        await browser_use.ainvoke({"action": "close_session", "profile": "work", "kill": True})
        assert list(captured) == [
            {
                "action": "close_session",
                "profile": "work",
                "kill": True,
            }
        ]

    async def test_failure_round_trips(self, install_fake: Callable[..., list[dict[str, Any]]]) -> None:
        """Underlying ToolResult.success=False survives the JSON round-trip."""

        def builder(*, action: str, **_: Any) -> ToolResult:
            return ToolResult(
                success=False,
                content="",
                error="navigation timeout",
                metrics=_make_metrics(action),
            )

        install_fake(builder)
        result = await browser_use.ainvoke({"action": "navigate", "url": "https://flaky.example"})
        assert isinstance(result, str)

        payload = json.loads(result)
        assert payload["success"] is False
        assert payload["error"] == "navigation timeout"

    async def test_unexpected_exception_returns_envelope(
        self, install_fake: Callable[..., list[dict[str, Any]]]
    ) -> None:
        """If browser_tool raises, the wrapper still returns a clean envelope."""

        def builder(*, action: str, **_: Any) -> ToolResult:
            raise RuntimeError("websocket dropped")

        install_fake(builder)
        result = await browser_use.ainvoke({"action": "navigate", "url": "https://x"})
        assert isinstance(result, str)

        payload = json.loads(result)
        assert payload["success"] is False
        assert "websocket dropped" in payload["error"]
        # Failure recorded in history too.
        assert payload["action_history"] == [{"action": "navigate", "success": False}]

    async def test_missing_dependency_returns_install_hint(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Drop any real or fake octop_browser from sys.modules and force
        # the import to fail.
        import builtins

        monkeypatch.delitem(sys.modules, "octop_browser", raising=False)
        real_import = builtins.__import__

        def fake_import(
            name: str,
            globals: dict[str, Any] | None = None,
            locals: dict[str, Any] | None = None,
            fromlist: tuple[str, ...] = (),
            level: int = 0,
        ) -> Any:
            if name == "octop_browser":
                raise ImportError("simulated missing dependency")
            return real_import(name, globals, locals, fromlist, level)

        with patch("builtins.__import__", fake_import):
            result = await browser_use.ainvoke({"action": "navigate", "url": "https://example.com"})

        assert isinstance(result, str)
        assert "octop-browser" in result
        assert "octop-browser" in result  # install-hint mentions the package name
        # install hint should suggest reinstalling the parent package or
        # the browser package directly — no longer references the
        # removed ``[browser]`` extras.
        assert "pip install" in result
        assert "[browser]" not in result
