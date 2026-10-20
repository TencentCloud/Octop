"""Tests for ``octop_memory.pipeline.extractor.parser``."""

from __future__ import annotations

import json

import pytest

from octop_memory.pipeline.extractor.parser import (
    ExtractorParseError,
    extract_json_blob,
    parse_extractor_output,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_candidate_dict(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "candidate_id": "",
        "candidate_type": "Decision",
        "status": "pending",
        "title": "Octop Memory mode",
        "assertion": "decided to use Augment mode first, NOT replace",
        "verbatim_quote": "decided to use Augment mode first, NOT replace",
        "quote_event_id": "raw-1",
        "subject": {"name": "Octop Memory", "entity_type": "Project", "entity_id_hint": ""},
        "target_entities": [],
        "source_refs": ["raw-1"],
        "confidence": "high",
        "importance": "high",
        "recommended_action": "promote",
        "promotion_reason": "explicit decision",
    }
    base.update(overrides)
    return base


def _wrap_payload(*candidates: dict[str, object]) -> str:
    return json.dumps({"candidates": list(candidates)})


# ---------------------------------------------------------------------------
# extract_json_blob
# ---------------------------------------------------------------------------


class TestExtractJsonBlob:
    def test_plain_json_passes_through(self) -> None:
        s = '{"candidates": []}'
        assert extract_json_blob(s) == s

    def test_strips_code_fence(self) -> None:
        wrapped = '```json\n{"candidates": []}\n```'
        assert extract_json_blob(wrapped) == '{"candidates": []}'

    def test_strips_bare_fence(self) -> None:
        wrapped = '```\n{"a": 1}\n```'
        assert extract_json_blob(wrapped) == '{"a": 1}'

    def test_strips_leading_prose(self) -> None:
        s = 'Sure! Here is the JSON:\n{"candidates": []}'
        assert extract_json_blob(s) == '{"candidates": []}'

    def test_strips_trailing_prose(self) -> None:
        s = '{"a": 1}\nLet me know if you need adjustments.'
        assert extract_json_blob(s) == '{"a": 1}'

    def test_handles_braces_in_strings(self) -> None:
        s = '{"foo": "has } brace inside"}'
        assert extract_json_blob(s) == s

    def test_handles_escaped_quotes_in_strings(self) -> None:
        s = '{"foo": "she said \\"hi\\" to me", "bar": 1}'
        assert extract_json_blob(s) == s

    def test_empty_string_raises(self) -> None:
        with pytest.raises(ExtractorParseError, match="empty"):
            extract_json_blob("")

    def test_no_json_object_raises(self) -> None:
        with pytest.raises(ExtractorParseError, match="no JSON object found"):
            extract_json_blob("just some prose, no JSON at all")

    def test_unbalanced_braces_raises(self) -> None:
        with pytest.raises(ExtractorParseError, match="unbalanced"):
            extract_json_blob("{ unbalanced")


# ---------------------------------------------------------------------------
# parse_extractor_output — happy path
# ---------------------------------------------------------------------------


class TestParseHappyPath:
    def test_single_high_importance_candidate_round_trip(self) -> None:
        payload = _wrap_payload(_make_candidate_dict())
        result = parse_extractor_output(
            payload,
            session_id="sess-1",
            raw_event_ids={"raw-1"},
        )

        assert len(result.candidates) == 1
        c = result.candidates[0]
        assert c.candidate_type == "Decision"
        assert c.assertion == c.verbatim_quote  # high importance preserved
        assert c.session_id == "sess-1"
        assert c.id  # worker-assigned id
        assert c.target_entity_id is None  # never from LLM
        assert result.warnings == []
        assert result.cap_warning is None

    def test_multiple_candidates(self) -> None:
        payload = _wrap_payload(
            _make_candidate_dict(quote_event_id="raw-1", source_refs=["raw-1"]),
            _make_candidate_dict(
                title="other fact",
                assertion="alias table 默认大小是 10000",
                verbatim_quote="alias table 默认大小是 10000",
                importance="low",
                quote_event_id="raw-2",
                source_refs=["raw-2"],
            ),
        )
        result = parse_extractor_output(
            payload,
            session_id="sess-1",
            raw_event_ids={"raw-1", "raw-2"},
        )
        assert len(result.candidates) == 2
        assert result.candidates[0].importance == "high"
        assert result.candidates[1].importance == "low"

    def test_empty_candidates_list_is_valid(self) -> None:
        payload = '{"candidates": []}'
        result = parse_extractor_output(payload, session_id=None)
        assert result.candidates == []
        assert result.warnings == []

    def test_session_id_propagates_to_all_candidates(self) -> None:
        payload = _wrap_payload(_make_candidate_dict())
        result = parse_extractor_output(
            payload,
            session_id="my-session",
            raw_event_ids={"raw-1"},
        )
        assert all(c.session_id == "my-session" for c in result.candidates)

    def test_extractor_version_persisted(self) -> None:
        payload = _wrap_payload(_make_candidate_dict())
        result = parse_extractor_output(
            payload,
            session_id="s",
            raw_event_ids={"raw-1"},
            extractor_version="v9.99-test",
        )
        assert result.candidates[0].extractor_version == "v9.99-test"


# ---------------------------------------------------------------------------
# parse_extractor_output — anti-dilution warnings
# ---------------------------------------------------------------------------


class TestAntiDilutionWarnings:
    def test_high_importance_paraphrased_warns(self) -> None:
        # Same negation present so we isolate the "high importance must equal verbatim" rule.
        payload = _wrap_payload(
            _make_candidate_dict(
                importance="high",
                assertion="we decided to use Augment first, NOT replace",  # paraphrased
                verbatim_quote="Octop Memory 这个项目，我决定先做 Augment 模式，不做 Replace",
            )
        )
        result = parse_extractor_output(payload, session_id="s", raw_event_ids={"raw-1"})
        # Candidate is still emitted (warn, not reject) so caller can decide.
        assert len(result.candidates) == 1
        assert any("paraphrased" in w for w in result.warnings)

    def test_lost_negation_warns(self) -> None:
        payload = _wrap_payload(
            _make_candidate_dict(
                importance="medium",  # avoid the assertion==quote rule above
                assertion="decided to use Augment mode",  # negation lost
                verbatim_quote="decided to use Augment mode first, NOT replace",
            )
        )
        result = parse_extractor_output(payload, session_id="s", raw_event_ids={"raw-1"})
        assert len(result.candidates) == 1
        assert any("negation" in w.lower() or "qualifier" in w.lower() for w in result.warnings)

    def test_high_importance_matching_verbatim_no_warning(self) -> None:
        payload = _wrap_payload(_make_candidate_dict(importance="high"))
        result = parse_extractor_output(payload, session_id="s", raw_event_ids={"raw-1"})
        assert result.warnings == []


# ---------------------------------------------------------------------------
# parse_extractor_output — structural errors
# ---------------------------------------------------------------------------


class TestStructuralErrors:
    def test_invalid_json_raises(self) -> None:
        # Input has balanced braces (passes blob extraction) but body is not valid JSON.
        with pytest.raises(ExtractorParseError, match="invalid JSON"):
            parse_extractor_output('{"a": 1, "b": invalid}', session_id=None)

    def test_top_level_array_rejected_at_blob_extraction(self) -> None:
        # extract_json_blob refuses non-object inputs early, with a clear message.
        with pytest.raises(ExtractorParseError, match="no JSON object found"):
            parse_extractor_output("[1, 2]", session_id=None)

    def test_top_level_object_missing_candidates_rejected(self) -> None:
        with pytest.raises(ExtractorParseError, match="candidates"):
            parse_extractor_output('{"foo": 1}', session_id=None)

    def test_candidates_must_be_list(self) -> None:
        with pytest.raises(ExtractorParseError, match="candidates"):
            parse_extractor_output('{"candidates": "oops"}', session_id=None)

    def test_invalid_candidate_type_skipped(self) -> None:
        payload = _wrap_payload(_make_candidate_dict(candidate_type="Garbage"))
        result = parse_extractor_output(payload, session_id="s", raw_event_ids={"raw-1"})
        assert result.candidates == []
        assert any("candidate_type" in w for w in result.warnings)

    def test_missing_verbatim_quote_skipped(self) -> None:
        payload = _wrap_payload(_make_candidate_dict(verbatim_quote=""))
        result = parse_extractor_output(payload, session_id="s", raw_event_ids={"raw-1"})
        assert result.candidates == []
        assert any("verbatim_quote" in w for w in result.warnings)

    def test_verbatim_quote_too_long_truncated(self) -> None:
        payload = _wrap_payload(_make_candidate_dict(verbatim_quote="x" * 211))
        result = parse_extractor_output(payload, session_id="s", raw_event_ids={"raw-1"})
        assert len(result.candidates) == 1
        assert result.candidates[0].verbatim_quote == "x" * 200
        assert any("truncated" in w for w in result.warnings)

    def test_bad_candidate_does_not_discard_siblings(self) -> None:
        payload = _wrap_payload(
            _make_candidate_dict(candidate_type="Garbage"),
            _make_candidate_dict(),
        )
        result = parse_extractor_output(payload, session_id="s", raw_event_ids={"raw-1"})
        assert len(result.candidates) == 1
        assert any("skipped" in w for w in result.warnings)

    def test_source_refs_must_be_non_empty(self) -> None:
        payload = _wrap_payload(_make_candidate_dict(source_refs=[]))
        result = parse_extractor_output(payload, session_id="s", raw_event_ids={"raw-1"})
        assert result.candidates == []
        assert any("at least 1" in w for w in result.warnings)

    def test_fabricated_source_ref_skipped(self) -> None:
        payload = _wrap_payload(_make_candidate_dict(source_refs=["fake-id-99"]))
        result = parse_extractor_output(payload, session_id="s", raw_event_ids={"raw-1"})
        assert result.candidates == []
        assert any("not in input batch" in w for w in result.warnings)

    def test_quote_event_id_not_in_batch_skipped(self) -> None:
        payload = _wrap_payload(_make_candidate_dict(quote_event_id="fake-quote"))
        result = parse_extractor_output(payload, session_id="s", raw_event_ids={"raw-1"})
        assert result.candidates == []
        assert any("not in input batch" in w for w in result.warnings)

    def test_subject_must_be_object(self) -> None:
        payload = _wrap_payload(_make_candidate_dict(subject="oops"))
        result = parse_extractor_output(payload, session_id="s", raw_event_ids={"raw-1"})
        assert result.candidates == []
        assert any("subject" in w for w in result.warnings)

    def test_skip_referential_check_when_universe_empty(self) -> None:
        # Useful for tests where caller wants synthetic ids.
        payload = _wrap_payload(_make_candidate_dict(quote_event_id="anything"))
        result = parse_extractor_output(payload, session_id="s", raw_event_ids=None)
        assert len(result.candidates) == 1


# ---------------------------------------------------------------------------
# parse_extractor_output — cap warning
# ---------------------------------------------------------------------------


class TestCapWarning:
    def test_cap_warning_recognised_and_excluded_from_candidates(self) -> None:
        payload = _wrap_payload(
            _make_candidate_dict(),
            {
                "candidate_id": "",
                "candidate_type": "Fact",
                "status": "pending",
                "title": "__cap_warning__",
                "assertion": "batch truncated, 47 original candidates",
                "verbatim_quote": "__cap_warning__",
                "quote_event_id": "raw-1",
                "subject": {"name": "n", "entity_type": "Fact", "entity_id_hint": ""},
                "source_refs": ["raw-1"],
                "confidence": "low",
                "importance": "low",
                "recommended_action": "reject",
                "promotion_reason": "cap",
            },
        )
        result = parse_extractor_output(payload, session_id="s", raw_event_ids={"raw-1"})
        assert len(result.candidates) == 1  # cap_warning excluded
        assert result.cap_warning is not None
        assert "47" in result.cap_warning
        assert result.raw_count == 2
