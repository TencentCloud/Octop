"""Tests for ``octop_memory.pipeline.extractor.prompts``."""

from __future__ import annotations

from octop_memory.pipeline.extractor.prompts import (
    EXTRACTOR_VERSION,
    NEGATION_TOKENS,
    render_prompt,
    render_retry_prompt,
)


def test_extractor_version_is_versioned_string() -> None:
    assert isinstance(EXTRACTOR_VERSION, str)
    assert EXTRACTOR_VERSION.startswith("v")


def test_render_prompt_embeds_events_and_max_cap() -> None:
    events_json = '[{"event_id": "raw-1", "content": "hello"}]'
    prompt = render_prompt(events_json, max_candidates=15)

    assert "raw-1" in prompt
    assert "hello" in prompt
    assert "at most 15 candidates" in prompt
    # Must include critical anti-dilution wording
    assert "Anti-dilution rules" in prompt
    assert "verbatim_quote" in prompt
    assert "negation" in prompt or "NOT" in prompt


def test_render_prompt_includes_few_shot_examples() -> None:
    prompt = render_prompt("[]", max_candidates=20)
    assert "Example 1" in prompt
    assert "Example 2" in prompt
    assert "Example 3" in prompt
    # Few-shot must demonstrate the high-importance verbatim rule
    assert "记住" in prompt or "remember" in prompt.lower()


def test_render_prompt_lists_six_entity_types() -> None:
    prompt = render_prompt("[]", max_candidates=20)
    for et in ("User", "Person", "Project", "Decision", "Task", "Fact"):
        assert et in prompt


def test_render_prompt_contains_output_schema_keys() -> None:
    prompt = render_prompt("[]", max_candidates=20)
    for key in (
        "candidate_type",
        "candidate_id",
        "verbatim_quote",
        "quote_event_id",
        "source_refs",
        "confidence",
        "importance",
        "recommended_action",
    ):
        assert key in prompt


def test_render_retry_prompt_keeps_original_context() -> None:
    original = render_prompt('[{"event_id":"r1"}]', max_candidates=20)
    retry = render_retry_prompt(original, "broken {{{ output")

    assert original in retry
    assert "previous response was not valid JSON" in retry
    assert "broken" in retry  # malformed snippet preserved
    assert "JSON only" in retry


def test_render_retry_prompt_truncates_long_malformed_output() -> None:
    very_long = "x" * 10_000
    retry = render_retry_prompt("base prompt", very_long)
    # Should truncate to 1000 chars per the parser implementation
    assert retry.count("x") <= 1000


def test_negation_tokens_cover_required_languages() -> None:
    """Anti-dilution requires negation token coverage in user-facing languages."""
    assert "不" in NEGATION_TOKENS
    assert "not" in NEGATION_TOKENS
    assert "won't" in NEGATION_TOKENS
    assert "先" in NEGATION_TOKENS  # Chinese qualifier
