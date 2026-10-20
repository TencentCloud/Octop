"""Unit tests for :mod:`octop_memory.application.path_projection`.

These are pure-Python tests; no SQLite, no I/O.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from octop_memory.application.path_projection import (
    PathError,
    atom_to_path,
    excerpt_metadata,
    page_to_path,
    parse_path,
    raw_to_path,
    render_atom_md,
    render_page_md,
    render_raw_md,
    slice_lines,
)
from octop_memory.types import AtomCard, EntityPage, RawEvent

# ---------------------------------------------------------------------------
# parse_path
# ---------------------------------------------------------------------------


class TestParsePath:
    def test_parse_atom(self) -> None:
        ref = parse_path("atom/atm_a3f2c891.md")
        assert ref.kind == "atom"
        assert ref.id == "atm_a3f2c891"

    def test_parse_page(self) -> None:
        ref = parse_path("page/Hermes-Adapter.md")
        assert ref.kind == "page"
        assert ref.id == "Hermes-Adapter"

    def test_parse_raw(self) -> None:
        ref = parse_path("raw/2026-06-04/evt_x9k.md")
        assert ref.kind == "raw"
        assert ref.date == "2026-06-04"
        assert ref.id == "evt_x9k"

    def test_parse_host_root(self) -> None:
        assert parse_path("MEMORY.md").kind == "host_root"
        assert parse_path("USER.md").kind == "host_root"

    def test_parse_host_dreams(self) -> None:
        assert parse_path("DREAMS.md").kind == "host_dreams"

    def test_parse_host_daily_plain(self) -> None:
        ref = parse_path("memory/2026-06-04.md")
        assert ref.kind == "host_daily"
        assert ref.date == "2026-06-04"
        assert ref.slug is None

    def test_parse_host_daily_slugged(self) -> None:
        ref = parse_path("memory/2026-06-04-design-review.md")
        assert ref.kind == "host_daily"
        assert ref.date == "2026-06-04"
        assert ref.slug == "design-review"

    def test_parse_host_topic_file(self) -> None:
        ref = parse_path("topics/billing.md")
        assert ref.kind == "host_file"
        assert ref.filename == "topics/billing.md"

    def test_parse_rejects_empty(self) -> None:
        with pytest.raises(PathError):
            parse_path("")

    def test_parse_rejects_whitespace(self) -> None:
        with pytest.raises(PathError):
            parse_path(" atom/x.md")

    def test_parse_rejects_unknown_prefix(self) -> None:
        with pytest.raises(PathError):
            parse_path("garbage/whatever.txt")

    def test_parse_rejects_unsafe_host_path(self) -> None:
        for path in ("../secret.md", "/tmp/secret.md", "topics/../secret.md", ".secret/file.md"):
            with pytest.raises(PathError):
                parse_path(path)

    def test_parse_rejects_no_extension(self) -> None:
        with pytest.raises(PathError):
            parse_path("atom/atm_x")


# ---------------------------------------------------------------------------
# Round-trip: row → path → parse → ref.id matches row.id
# ---------------------------------------------------------------------------


class TestRoundtrip:
    def test_atom_path_roundtrips(self) -> None:
        atom = _make_atom(atom_id="atm_xyz")
        path = atom_to_path(atom)
        ref = parse_path(path)
        assert ref.id == "atm_xyz"

    def test_page_path_roundtrips(self) -> None:
        page = _make_page(entity_id="ent_abc")
        path = page_to_path(page)
        ref = parse_path(path)
        assert ref.id == "ent_abc"

    def test_raw_path_includes_event_date(self) -> None:
        event = _make_event(event_id="evt_1", ts=datetime(2026, 6, 4, 10, 30, tzinfo=UTC))
        path = raw_to_path(event)
        ref = parse_path(path)
        assert ref.date == "2026-06-04"
        assert ref.id == "evt_1"


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------


class TestRenderers:
    def test_render_atom_includes_front_matter_and_assertion(self) -> None:
        atom = _make_atom(atom_id="atm_1", assertion="Hermes adapter uses MemoryProvider ABC")
        body = render_atom_md(atom)
        assert "id: atm_1" in body
        assert "importance: high" in body
        assert "Hermes adapter uses MemoryProvider ABC" in body

    def test_render_atom_omits_quote_when_equal_to_assertion(self) -> None:
        atom = _make_atom(atom_id="atm_1", assertion="X", quote="X")
        body = render_atom_md(atom)
        # Quote line should NOT appear when quote == assertion (D25 anti-dilution
        # already keeps them equal for high-importance atoms).
        assert body.count("> X") == 0

    def test_render_atom_includes_quote_when_distinct(self) -> None:
        atom = _make_atom(atom_id="atm_1", assertion="X paraphrased", quote="X verbatim")
        body = render_atom_md(atom)
        assert "> X verbatim" in body

    def test_render_page_with_summary(self) -> None:
        page = _make_page(entity_id="ent_1", summary="Body text.\n\nMore.")
        body = render_page_md(page)
        assert "entity_id: ent_1" in body
        assert "version: 3" in body
        assert "Body text." in body

    def test_render_empty_page_has_placeholder(self) -> None:
        page = _make_page(entity_id="ent_1", summary="")
        body = render_page_md(page)
        assert "_(empty page" in body

    def test_render_raw_uses_payload_role(self) -> None:
        event = _make_event(event_id="evt_1", payload={"role": "assistant"})
        body = render_raw_md(event)
        assert "role: assistant" in body

    def test_render_raw_falls_back_to_event_type(self) -> None:
        event = _make_event(event_id="evt_1", payload={})
        body = render_raw_md(event)
        # event_type defaults to "user_message" in the helper
        assert "role: user_message" in body


# ---------------------------------------------------------------------------
# slice_lines
# ---------------------------------------------------------------------------


class TestSliceLines:
    def test_full_text_when_no_args(self) -> None:
        text = "a\nb\nc"
        assert slice_lines(text) == "a\nb\nc"

    def test_from_only(self) -> None:
        assert slice_lines("a\nb\nc\nd", from_line=2) == "b\nc\nd"

    def test_lines_only(self) -> None:
        assert slice_lines("a\nb\nc\nd", lines=2) == "a\nb"

    def test_from_and_lines(self) -> None:
        assert slice_lines("a\nb\nc\nd", from_line=2, lines=2) == "b\nc"

    def test_from_past_end_returns_empty(self) -> None:
        assert slice_lines("a\nb", from_line=5) == ""

    def test_lines_past_end_clamps(self) -> None:
        # asking for 99 lines of a 3-line doc → returns all 3
        assert slice_lines("a\nb\nc", lines=99) == "a\nb\nc"

    def test_rejects_zero_from(self) -> None:
        with pytest.raises(ValueError, match="from_line must be >= 1"):
            slice_lines("a", from_line=0)

    def test_rejects_zero_lines(self) -> None:
        with pytest.raises(ValueError, match="lines must be >= 1"):
            slice_lines("a", lines=0)


# ---------------------------------------------------------------------------
# excerpt_metadata
# ---------------------------------------------------------------------------


class TestExcerptMetadata:
    def test_full_doc_not_truncated(self) -> None:
        meta = excerpt_metadata(full_text="a\nb\nc", from_line=1, lines=10)
        assert meta["total_lines"] == 3
        assert meta["truncated"] is False
        assert "continuation" not in meta

    def test_partial_returns_continuation(self) -> None:
        meta = excerpt_metadata(full_text="a\nb\nc\nd\ne", from_line=1, lines=2)
        assert meta["truncated"] is True
        assert meta["continuation"] == {"from": 3}

    def test_default_values(self) -> None:
        meta = excerpt_metadata(full_text="a\nb\nc", from_line=None, lines=None)
        assert meta["from_line"] == 1
        assert meta["to_line"] == 3
        assert meta["truncated"] is False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_atom(
    *,
    atom_id: str = "atm_x",
    assertion: str = "test assertion",
    quote: str | None = None,
) -> AtomCard:
    return AtomCard(
        id=atom_id,
        entity_id="ent_x",
        candidate_id="cand_x",
        raw_event_ids=["evt_x"],
        assertion=assertion,
        verbatim_quote=quote if quote is not None else assertion,
        quote_event_id="evt_x",
        search_terms=["test"],
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        confidence="high",
        importance="high",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _make_page(
    *,
    entity_id: str = "ent_x",
    summary: str = "Summary body.",
    headline: str = "Headline",
) -> EntityPage:
    return EntityPage(
        id=f"pg_{entity_id}",
        entity_id=entity_id,
        summary_markdown=summary,
        headline=headline,
        topics=["topic1"],
        dirty=False,
        regen_attempt_count=0,
        summary_version=3,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=datetime(2026, 6, 4, tzinfo=UTC),
    )


def _make_event(
    *,
    event_id: str = "evt_x",
    ts: datetime | None = None,
    payload: dict | None = None,
) -> RawEvent:
    return RawEvent(
        id=event_id,
        host="openclaw",
        session_id="sess_1",
        thread_id="thread_1",
        user="alice",
        timestamp=ts or datetime(2026, 6, 4, tzinfo=UTC),
        event_type="user_message",
        content="hello world",
        payload=payload or {},
    )
