"""First-message conversation titles."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from octop.infra.gateway.process.processor import GlobalProcessor
from octop.infra.gateway.process.thread_title import (
    TITLE_SOURCE_MAX,
    clean_generated_title,
    clip_title_source,
    should_autotitle,
)
from octop.infra.gateway.slash.dispatcher import SlashDispatcher


def test_should_autotitle_skips_slash_and_existing() -> None:
    assert should_autotitle("帮我写周报", None) is True
    assert should_autotitle("帮我写周报", "") is True
    assert should_autotitle("/help", None) is False
    assert should_autotitle("  ", None) is False
    assert should_autotitle("帮我写周报", "已有标题") is False


def test_clip_title_source_bounds_long_text() -> None:
    assert clip_title_source("  a\nb  ") == "a b"
    long = "字" * (TITLE_SOURCE_MAX + 20)
    assert len(clip_title_source(long)) == TITLE_SOURCE_MAX


def test_clean_generated_title_unwraps_quotes() -> None:
    assert clean_generated_title('  "季度销售" \n') == "季度销售"
    assert clean_generated_title("") == ""


def _processor(stored: dict[str, str | None]) -> tuple[GlobalProcessor, MagicMock]:
    def get_thread(_thread_id: str) -> SimpleNamespace:
        return SimpleNamespace(title=stored["title"], agent_id="agent-1")

    def set_title(_thread_id: str, title: str) -> None:
        if not stored["title"]:
            stored["title"] = title

    def replace_title(_thread_id: str, title: str) -> None:
        stored["title"] = title

    thread_registry = MagicMock()
    thread_registry.get_thread.side_effect = get_thread
    thread_registry.set_title_if_null.side_effect = set_title
    thread_registry.update_title.side_effect = replace_title
    thread_registry.touch_last_active = MagicMock()
    gateway = MagicMock()
    gateway.ws_hub.push_to_thread = AsyncMock()
    processor = GlobalProcessor(
        agent_manager=MagicMock(),
        thread_registry=thread_registry,
        audit_repo=MagicMock(),
        agent_repo=MagicMock(),
        user_repo=MagicMock(),
        connector_repo=MagicMock(),
        dispatcher=SlashDispatcher(),
        usage_repo=None,
        gateway=gateway,
    )
    return processor, gateway


@pytest.mark.asyncio
async def test_generate_thread_title_uses_model_text() -> None:
    stored: dict[str, str | None] = {"title": None}
    processor, gateway = _processor(stored)
    with patch(
        "octop.infra.text_assist.run_text_assist",
        new=AsyncMock(return_value="季度销售"),
    ):
        await processor._generate_thread_title("thr", "请总结上季度销售数据", user_id=3)
    assert stored["title"] == "季度销售"
    gateway.ws_hub.push_to_thread.assert_awaited_once()
    frame = gateway.ws_hub.push_to_thread.await_args.args[1]
    assert frame["type"] == "thread_title"
    assert frame["title"] == "季度销售"
    assert frame["agent_id"] == "agent-1"


@pytest.mark.asyncio
async def test_generate_thread_title_falls_back_to_the_question() -> None:
    stored: dict[str, str | None] = {"title": None}
    processor, _gateway = _processor(stored)
    with patch(
        "octop.infra.text_assist.run_text_assist",
        new=AsyncMock(side_effect=RuntimeError("down")),
    ):
        await processor._generate_thread_title("thr", "原始问题", user_id=3)
    assert stored["title"] == "原始问题"


@pytest.mark.asyncio
async def test_schedule_keeps_the_question_visible_before_the_model_returns() -> None:
    stored: dict[str, str | None] = {"title": None}
    processor, _gateway = _processor(stored)
    release = asyncio.Event()

    async def _hold(_models: object, **_kwargs: object) -> str:
        await release.wait()
        return "季度销售"

    with patch("octop.infra.text_assist.run_text_assist", new=_hold):
        processor._schedule_auto_thread_title("thr", "Hello", user_id=1)
        assert stored["title"] == "Hello"
        release.set()
        await asyncio.sleep(0)


def test_touch_does_not_stamp_the_raw_question_while_title_generates() -> None:
    stored: dict[str, str | None] = {"title": None}
    processor, _gateway = _processor(stored)
    processor._title_inflight.add("thr")
    processor._touch_thread_after_turn("thr", "原始问题")
    assert stored["title"] is None


@pytest.mark.asyncio
async def test_schedule_skips_a_thread_that_already_has_a_title() -> None:
    stored: dict[str, str | None] = {"title": "已有"}
    processor, _gateway = _processor(stored)
    processor._schedule_auto_thread_title("thr", "新的问题", user_id=1)
    await asyncio.sleep(0)
    assert "thr" not in processor._title_inflight
    assert stored["title"] == "已有"
