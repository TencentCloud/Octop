"""Runtime failures are diagnostic evidence, never automatic durable knowledge."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from octop_memory import Memory, MemoryService
from octop_memory.application.runtime import MemoryRuntime
from octop_memory.pipeline.episode import EpisodeExtractor
from octop_memory.pipeline.extractor import CandidateExtractor
from octop_memory.pipeline.recall import recall_for_prompt, recall_multi_source
from octop_memory.ports.llm.mock import MockLLMClient
from octop_memory.types import RawEvent

FAILURE = "Model call failed after 3 attempts with AuthenticationError: Error code: 401 - token_expired"


def failure_event(*, marked: bool = False) -> RawEvent:
    return RawEvent(
        id="failure",
        host="octop-harness",
        session_id="s1",
        thread_id="t1",
        user="alice",
        timestamp=datetime.now(UTC),
        event_type="assistant_message",
        content=FAILURE,
        payload={"octop_runtime_error": True} if marked else {},
    )


@pytest.fixture
def memory(tmp_path: Path) -> Iterator[Memory]:
    mem = Memory(namespace="retention", backend_config={"db_path": str(tmp_path / "memory.sqlite")})
    try:
        yield mem
    finally:
        mem.backend.close()


def test_capture_preserves_user_request_and_drops_generated_failure(memory: Memory) -> None:
    runtime = MemoryRuntime(memory, config={"capture": {"min_message_chars": 0}})
    result = runtime.capture(
        {
            "events": [
                {"event_type": "user_message", "content": "401 故障修复后要验证成功请求。"},
                {"event_type": "assistant_message", "content": FAILURE, "payload": {"octop_runtime_error": True}},
            ]
        }
    )
    assert result["accepted"] == 1
    assert [event.event_type for event in memory.list_raw()] == ["user_message"]


@pytest.mark.parametrize("extractor_type", [CandidateExtractor, EpisodeExtractor])
def test_marked_runtime_failure_never_reaches_either_extraction_prompt(extractor_type: type) -> None:
    llm = MockLLMClient(default_response='{"candidates": [], "episodes": []}')
    extractor_type(llm=llm).extract([failure_event(marked=True)])
    assert not llm.calls


def test_marked_raw_failure_cannot_return_via_fallback(memory: Memory) -> None:
    memory.add_raw_batch([failure_event(marked=True)])
    assert not recall_for_prompt(memory, "token_expired", raw_policy="always").snippets
    assert not recall_multi_source(memory, "token_expired", sources=("raw",)).snippets
    assert memory.get_raw("failure") is not None  # Evidence is still inspectable.


@pytest.mark.parametrize("content", [FAILURE, "记住：遇到 401 先刷新凭据，验证请求成功后再继续。"])
def test_user_error_reports_and_explicit_memory_requests_are_kept(memory: Memory, content: str) -> None:
    event = replace(failure_event(), event_type="user_message", content=content)
    memory.add_raw_batch([event])
    assert recall_for_prompt(memory, "401", raw_policy="always").snippets


def test_normal_troubleshooting_lesson_is_not_a_runtime_failure(memory: Memory) -> None:
    lesson = "已验证的排障经验：遇到 401 后刷新凭据，再重试请求，这次验证成功。"
    service = MemoryService(memory, config={"capture": {"min_message_chars": 0}})
    assert service.capture_turn(user="排查一下认证问题", assistant=lesson)["accepted"] == 2
    assert any(event.content == lesson for event in memory.list_raw())


def test_legacy_error_quote_followed_by_verified_fix_is_kept(memory: Memory) -> None:
    lesson = FAILURE + "\n\n已验证的修复方法：刷新凭据后重新请求，验证成功。"
    service = MemoryService(memory, config={"capture": {"min_message_chars": 0}})
    assert service.capture_turn(assistant=lesson)["accepted"] == 1
    assert recall_for_prompt(memory, "token_expired", raw_policy="always").snippets


@pytest.mark.parametrize("store_content", [True, False])
@pytest.mark.parametrize("marked", [True, False])
def test_capture_checks_source_before_privacy_redaction(memory: Memory, store_content: bool, marked: bool) -> None:
    runtime = MemoryRuntime(
        memory,
        config={
            "capture": {"min_message_chars": 0},
            "privacy": {"store_raw_content": store_content},
        },
    )
    event = {
        "event_type": "assistant_message",
        "content": "运行请求失败" if marked else FAILURE,
        "payload": {"octop_runtime_error": True} if marked else {},
    }
    result = runtime.capture({"events": [event]})
    assert result["accepted"] == (0 if marked else 1)
    assert result["skipped_runtime_error"] == (1 if marked else 0)
    # The same text quoted by a user remains an eligible statement.
    event["event_type"] = "user_message"
    assert runtime.capture({"events": [event]})["accepted"] == 1


@pytest.mark.parametrize("content", ["请记住这件事", "remember this", "保留这个偏好", "garder cette préférence"])
def test_explicit_save_needs_no_keyword_or_capture_length_exception(memory: Memory, content: str) -> None:
    service = MemoryService(memory, config={"capture": {"min_message_chars": 200}})
    capture = service.capture_turn(user=content)
    assert capture["accepted"] == 0 and capture["skipped_too_short"] == 1
    saved = service.save(content)
    assert saved.content == content and memory.get_atom(saved.atom_id) is not None


@pytest.mark.parametrize("suffix", ["", "\n已验证、已解决", "\nTry refreshing credentials, then confirm success."])
def test_unmarked_legacy_text_is_retained_without_value_keyword_checks(memory: Memory, suffix: str) -> None:
    content = FAILURE + suffix
    service = MemoryService(memory, config={"capture": {"min_message_chars": 0}})
    assert service.capture_turn(assistant=content)["accepted"] == 1
    assert recall_for_prompt(memory, "token_expired", raw_policy="always").snippets


@pytest.mark.parametrize("extractor_type", [CandidateExtractor, EpisodeExtractor])
def test_unknown_legacy_source_is_left_to_the_extraction_model(extractor_type: type) -> None:
    llm = MockLLMClient(default_response='{"candidates": [], "episodes": []}')
    extractor_type(llm=llm).extract([failure_event()])
    assert llm.calls


@pytest.mark.parametrize("content", [FAILURE, FAILURE + "\n已验证修复", "A structured runtime diagnostic"])
def test_marked_diagnostics_are_excluded_regardless_of_value_words(memory: Memory, content: str) -> None:
    runtime = MemoryRuntime(memory, config={"capture": {"min_message_chars": 0}})
    result = runtime.capture(
        {"events": [{"event_type": "assistant_message", "content": content, "payload": {"octop_runtime_error": True}}]}
    )
    assert result["accepted"] == 0 and result["skipped_runtime_error"] == 1
