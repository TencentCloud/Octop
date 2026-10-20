"""End-to-end tests for ``CandidateExtractor`` (with ``MockLLMClient``)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from octop_memory.pipeline.extractor import (
    CandidateExtractor,
    ExtractionResult,
)
from octop_memory.ports.llm import DEFAULT_EXTRACT_MAX_TOKENS, MockLLMClient, NoopLLMClient
from octop_memory.types import RawEvent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(UTC)


def _make_event(
    event_id: str,
    content: str,
    *,
    event_type: str = "user_message",
    session_id: str | None = "sess-1",
) -> RawEvent:
    return RawEvent(
        id=event_id,
        host="manual",
        session_id=session_id,
        thread_id=None,
        user=None,
        timestamp=_now(),
        event_type=event_type,  # type: ignore[arg-type]
        content=content,
        payload={},
    )


def _candidate_payload(**overrides: object) -> str:
    base: dict[str, object] = {
        "candidate_id": "",
        "candidate_type": "Decision",
        "status": "pending",
        "title": "test",
        "assertion": "decided to use Augment first, NOT replace",
        "verbatim_quote": "decided to use Augment first, NOT replace",
        "quote_event_id": "raw-1",
        "subject": {"name": "Project X", "entity_type": "Project", "entity_id_hint": ""},
        "target_entities": [],
        "source_refs": ["raw-1"],
        "confidence": "high",
        "importance": "high",
        "recommended_action": "promote",
        "promotion_reason": "explicit",
    }
    base.update(overrides)
    return json.dumps({"candidates": [base]})


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestExtractHappyPath:
    def test_basic_extraction(self) -> None:
        events = [_make_event("raw-1", "decided to use Augment first, NOT replace")]
        mock = MockLLMClient(default_response=_candidate_payload())
        extractor = CandidateExtractor(llm=mock)

        result = extractor.extract(events)

        assert isinstance(result, ExtractionResult)
        assert len(result.candidates) == 1
        assert result.failure_reason is None
        assert result.llm_calls == 1
        c = result.candidates[0]
        assert c.id  # worker-assigned uuid
        assert c.session_id == "sess-1"  # auto-detected from events
        assert c.assertion == c.verbatim_quote  # high importance preserved

    def test_empty_event_list_short_circuits(self) -> None:
        # Should not call the LLM at all.
        mock = MockLLMClient(raise_on_call=True)
        extractor = CandidateExtractor(llm=mock)

        result = extractor.extract([])

        assert result.candidates == []
        assert result.llm_calls == 0
        assert mock.calls == []

    def test_default_output_budget_passed_to_llm(self) -> None:
        # A bounded completion budget travels with every call so a
        # reasoning-heavy model cannot run past the client read timeout.
        events = [_make_event("raw-1", "decided to use Augment first, NOT replace")]
        mock = MockLLMClient(default_response=_candidate_payload())
        extractor = CandidateExtractor(llm=mock)

        extractor.extract(events)

        assert len(mock.calls) == 1
        assert mock.calls[0].max_tokens == DEFAULT_EXTRACT_MAX_TOKENS

    def test_explicit_output_budget_override(self) -> None:
        events = [_make_event("raw-1", "decided to use Augment first, NOT replace")]
        mock = MockLLMClient(default_response=_candidate_payload())
        extractor = CandidateExtractor(llm=mock, max_tokens=512)

        extractor.extract(events)

        assert mock.calls[0].max_tokens == 512

    def test_explicit_none_falls_back_to_default_budget(self) -> None:
        # A config layer that resolves "unset" to None must not erase the
        # built-in budget by threading it down as an explicit argument.
        events = [_make_event("raw-1", "decided to use Augment first, NOT replace")]
        mock = MockLLMClient(default_response=_candidate_payload())
        extractor = CandidateExtractor(llm=mock, max_tokens=None)

        extractor.extract(events)

        assert mock.calls[0].max_tokens == DEFAULT_EXTRACT_MAX_TOKENS

    def test_explicit_session_id_overrides_event_session(self) -> None:
        events = [_make_event("raw-1", "x", session_id="auto-detected")]
        mock = MockLLMClient(default_response=_candidate_payload())
        extractor = CandidateExtractor(llm=mock)

        result = extractor.extract(events, session_id="explicit-sess")

        assert result.candidates[0].session_id == "explicit-sess"

    def test_session_id_left_none_when_events_span_sessions(self) -> None:
        events = [
            _make_event("raw-1", "x", session_id="s1"),
            _make_event("raw-2", "y", session_id="s2"),
        ]
        # Use 2 candidates so both source_refs are valid; quote stays raw-1.
        payload = _candidate_payload(source_refs=["raw-1", "raw-2"])
        mock = MockLLMClient(default_response=payload)
        extractor = CandidateExtractor(llm=mock)

        result = extractor.extract(events)

        assert result.candidates[0].session_id is None  # cross-session => no auto

    def test_prompt_includes_event_payload(self) -> None:
        events = [_make_event("raw-1", "memorable thing happened")]
        mock = MockLLMClient(default_response=_candidate_payload())
        extractor = CandidateExtractor(llm=mock)

        extractor.extract(events)

        # The mock recorded the prompt — check our event made it through.
        assert "raw-1" in mock.calls[0].prompt
        assert "memorable thing happened" in mock.calls[0].prompt
        assert mock.calls[0].response_format == "json"
        assert mock.calls[0].tier == "light"


# ---------------------------------------------------------------------------
# Retry logic
# ---------------------------------------------------------------------------


class TestRetry:
    def test_first_response_unparseable_retries_and_succeeds(self) -> None:
        events = [_make_event("raw-1", "x")]
        # Use a key_fn that returns a constant; queue both responses against it
        # via call sequence — easier: use a counter side-effect.

        responses_iter = iter(
            [
                "I cannot comply with that request.",  # bad: not JSON
                _candidate_payload(),  # good
            ]
        )

        class StubLLM:
            calls = 0

            def call_llm(self, prompt: str, **_: object) -> str:
                self.calls += 1
                return next(responses_iter)

        stub = StubLLM()
        extractor = CandidateExtractor(llm=stub)  # type: ignore[arg-type]

        result = extractor.extract(events)

        assert len(result.candidates) == 1
        assert result.llm_calls == 2
        assert any("attempt 1" in w and "parse failed" in w for w in result.warnings)

    def test_retry_exhaustion_returns_failure(self) -> None:
        events = [_make_event("raw-1", "x")]
        mock = MockLLMClient(default_response="completely garbage non-json {{{ ")
        extractor = CandidateExtractor(llm=mock, max_retries=1)

        result = extractor.extract(events)

        assert result.candidates == []
        assert result.failure_reason is not None
        assert "parse failed after 2 attempts" in result.failure_reason
        assert result.llm_calls == 2

    def test_max_retries_zero_means_one_attempt(self) -> None:
        events = [_make_event("raw-1", "x")]
        mock = MockLLMClient(default_response="garbage")
        extractor = CandidateExtractor(llm=mock, max_retries=0)

        result = extractor.extract(events)

        assert result.llm_calls == 1
        assert result.failure_reason is not None


# ---------------------------------------------------------------------------
# LLM unavailability
# ---------------------------------------------------------------------------


class TestLLMUnavailable:
    def test_noop_llm_returns_failure_no_raise(self) -> None:
        events = [_make_event("raw-1", "x")]
        extractor = CandidateExtractor(llm=NoopLLMClient())

        result = extractor.extract(events)

        # Must NOT raise — main reply path should never be aborted.
        assert result.candidates == []
        assert result.failure_reason is not None
        assert "no LLM backend" in result.failure_reason
        assert result.llm_calls == 1

    def test_raise_on_call_mock_caught_gracefully(self) -> None:
        events = [_make_event("raw-1", "x")]
        mock = MockLLMClient(raise_on_call=True)
        extractor = CandidateExtractor(llm=mock)

        result = extractor.extract(events)

        assert result.candidates == []
        assert result.failure_reason is not None

    def test_unexpected_provider_error_degrades(self) -> None:
        class _Expired:
            def call_llm(self, prompt: str, **_: object) -> str:
                raise OSError("InvalidSubscription")

        result = CandidateExtractor(llm=_Expired()).extract([_make_event("raw-1", "x")])  # type: ignore[arg-type]
        assert result.candidates == []
        assert result.failure_reason is not None
        assert "InvalidSubscription" in result.failure_reason


# ---------------------------------------------------------------------------
# Cap warning passthrough
# ---------------------------------------------------------------------------


class TestCapWarningPassthrough:
    def test_cap_warning_surfaced_in_extraction_result(self) -> None:
        events = [_make_event("raw-1", "x")]
        cap_payload = json.dumps(
            {
                "candidates": [
                    json.loads(_candidate_payload())["candidates"][0],
                    {
                        "candidate_id": "",
                        "candidate_type": "Fact",
                        "status": "pending",
                        "title": "__cap_warning__",
                        "assertion": "batch truncated, 99 original candidates",
                        "verbatim_quote": "__cap_warning__",
                        "quote_event_id": "raw-1",
                        "subject": {"name": "n", "entity_type": "Fact", "entity_id_hint": ""},
                        "source_refs": ["raw-1"],
                        "confidence": "low",
                        "importance": "low",
                        "recommended_action": "reject",
                        "promotion_reason": "cap",
                    },
                ]
            }
        )
        mock = MockLLMClient(default_response=cap_payload)
        extractor = CandidateExtractor(llm=mock)

        result = extractor.extract(events)

        assert len(result.candidates) == 1
        assert result.cap_warning is not None
        assert "99" in result.cap_warning


# ---------------------------------------------------------------------------
# Anti-dilution warnings propagate
# ---------------------------------------------------------------------------


class TestAntiDilutionPropagation:
    def test_paraphrased_high_importance_warns(self) -> None:
        events = [_make_event("raw-1", "decided to use Augment, NOT replace")]
        # LLM paraphrased the assertion; should warn but still emit.
        payload = _candidate_payload(
            importance="high",
            assertion="decided to use Augment mode",  # lost negation + paraphrased
            verbatim_quote="decided to use Augment, NOT replace",
        )
        mock = MockLLMClient(default_response=payload)
        extractor = CandidateExtractor(llm=mock)

        result = extractor.extract(events)

        assert len(result.candidates) == 1
        assert any("paraphrased" in w or "negation" in w.lower() for w in result.warnings)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class TestExtractorConfig:
    def test_extractor_version_property(self) -> None:
        extractor = CandidateExtractor(llm=MockLLMClient(), extractor_version="v3.x")
        assert extractor.extractor_version == "v3.x"

    def test_max_candidates_propagated_to_prompt(self) -> None:
        events = [_make_event("raw-1", "x")]
        mock = MockLLMClient(default_response='{"candidates": []}')
        extractor = CandidateExtractor(llm=mock, max_candidates=7)

        extractor.extract(events)

        assert "at most 7 candidates" in mock.calls[0].prompt
