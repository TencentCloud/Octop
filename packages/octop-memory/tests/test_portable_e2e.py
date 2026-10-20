"""End-to-end tests: the portable pack -> adopt flow (requirements 2, 3, 7, 9).

Covers:
- Scenario A: pack -> adopt -> target db row counts match the manifest
- Scenario C: idempotent re-run (skip policy, two consecutive adopts leave row counts unchanged)
- host-rewrite=target mode
- dry-run mode
- basic doctor checks
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from octop_memory.core import Memory
from octop_memory.operations.migration.portable import (
    AdoptSummary,
    DoctorReport,
    PackSummary,
    SourceInfo,
    adopt,
    doctor,
    pack,
    read_manifest,
)
from octop_memory.types import AtomCard, Candidate, Entity, RawEvent


def _now() -> datetime:
    return datetime.now(UTC)


def _seed_memory(memory: Memory) -> None:
    """Write basic test data into memory."""
    raw_id = "raw-portable-1"
    entity_id = "ent-portable-1"
    cand_id = "cand-portable-1"
    atom_id = "atom-portable-1"
    when = _now()

    memory.add_raw_batch(
        [
            RawEvent(
                id=raw_id,
                host="octop",
                session_id="s1",
                thread_id=None,
                user="alice",
                timestamp=when,
                event_type="user_message",
                content="上次咖啡话题",
                payload={},
            )
        ]
    )
    memory.add_entity(
        Entity(
            id=entity_id,
            entity_type="Person",
            canonical_name="Alice",
            aliases=[],
            atom_count=0,
            last_promoted_at=None,
            created_at=when,
        )
    )
    memory.add_candidate(
        Candidate(
            id=cand_id,
            raw_event_ids=[raw_id],
            candidate_type="Fact",
            status="promoted",
            title="咖啡话题",
            assertion="Alice 喜欢咖啡",
            verbatim_quote="上次咖啡话题",
            quote_event_id=raw_id,
            subject_name="Alice",
            subject_entity_type="Person",
            target_entity_id=entity_id,
            confidence="high",
            importance="medium",
            recommended_action="promote",
            promotion_reason="",
            extractor_version="test",
            created_at=when,
            decided_at=when,
            decided_by="auto",
            session_id="s1",
            payload={},
        )
    )
    memory.add_atom(
        AtomCard(
            id=atom_id,
            entity_id=entity_id,
            candidate_id=cand_id,
            raw_event_ids=[raw_id],
            assertion="Alice 喜欢咖啡",
            verbatim_quote="上次咖啡话题",
            quote_event_id=raw_id,
            search_terms=["咖啡", "Alice"],
            occurred_at=when,
            confidence="high",
            importance="medium",
            created_at=when,
            superseded_by=None,
            deprecated_at=None,
        )
    )


@pytest.fixture()
def src_memory(tmp_path: Path) -> Memory:
    """Create and populate the source Memory instance."""
    db_path = tmp_path / "src" / "memory.sqlite"
    db_path.parent.mkdir(parents=True)
    mem = Memory(
        namespace="agent_test_",
        backend="sqlite",
        backend_config={"db_path": str(db_path)},
    )
    _seed_memory(mem)
    return mem


@pytest.fixture()
def src_info(src_memory: Memory, tmp_path: Path) -> SourceInfo:
    """Build the SourceInfo corresponding to src_memory."""
    db_path = tmp_path / "src" / "memory.sqlite"
    return SourceInfo(
        host_kind="agent",
        db_path=str(db_path),
        namespace="agent_test_",
        raw_event_count=1,
        atom_count=1,
        entity_count=1,
        journal_count=0,
        schema_version=1,
        agent_name="test",
    )


# ---------------------------------------------------------------------------
# Scenario A: pack -> adopt end-to-end
# ---------------------------------------------------------------------------


def test_pack_creates_hmpkg(src_info: SourceInfo, tmp_path: Path) -> None:
    """pack should produce a valid .hmpkg file with a complete manifest."""
    out_path = tmp_path / "test.hmpkg"
    summary = pack(src_info, out=out_path)

    assert isinstance(summary, PackSummary)
    assert out_path.exists()
    assert summary.total_rows > 0
    assert summary.file_size_bytes > 0
    assert summary.source_namespace == "agent_test_"

    # Verify the manifest.
    manifest = read_manifest(out_path)
    assert manifest["pkg_version"] == 1
    assert manifest["export_version"] >= 1
    assert manifest["source_host_kind"] == "agent"
    assert manifest["source_namespace"] == "agent_test_"
    assert "packed_at" in manifest
    assert "row_counts" in manifest
    assert manifest["row_counts"]["raw_events"] >= 1


def test_adopt_imports_to_target(src_info: SourceInfo, tmp_path: Path) -> None:
    """adopt should import the .hmpkg into the target db, with row counts matching the manifest."""
    pkg_path = tmp_path / "test.hmpkg"
    pack(src_info, out=pkg_path)

    # Target db path.
    target_db = tmp_path / "target" / "memory.sqlite"
    target_db.parent.mkdir(parents=True)

    summary = adopt(
        pkg_path,
        "openclaw:openclaw__test",
        on_conflict="skip",
        target_db_path=target_db,
    )

    assert isinstance(summary, AdoptSummary)
    assert summary.applied > 0
    assert not summary.dry_run
    assert not summary.already_adopted

    # Verify the target db has data.
    manifest = read_manifest(pkg_path)
    target_ns = summary.target_namespace
    target_db_path = summary.target_db_path

    conn = sqlite3.connect(target_db_path)
    raw_count = conn.execute(f"SELECT COUNT(*) FROM {target_ns}_raw_events").fetchone()[0]
    conn.close()
    assert raw_count == manifest["row_counts"]["raw_events"]


# ---------------------------------------------------------------------------
# Scenario C: idempotent re-run
# ---------------------------------------------------------------------------


def test_adopt_idempotent_skip(src_info: SourceInfo, tmp_path: Path) -> None:
    """Adopting the same .hmpkg twice in a row (skip policy) should return already_adopted the second time."""
    pkg_path = tmp_path / "test.hmpkg"
    pack(src_info, out=pkg_path)

    target_db = tmp_path / "idem_target" / "memory.sqlite"
    target_db.parent.mkdir(parents=True)

    # First adopt.
    result1 = adopt(pkg_path, "openclaw:openclaw__test_idem", on_conflict="skip", target_db_path=target_db)
    assert result1.applied > 0
    assert not result1.already_adopted

    # Second adopt.
    result2 = adopt(pkg_path, "openclaw:openclaw__test_idem", on_conflict="skip", target_db_path=target_db)
    assert result2.already_adopted
    assert result2.applied == 0

    # Verify the target db row count is unchanged.
    conn = sqlite3.connect(result1.target_db_path)
    count_after_2nd = conn.execute(f"SELECT COUNT(*) FROM {result1.target_namespace}_raw_events").fetchone()[0]
    conn.close()
    assert count_after_2nd == result1.applied_by_table.get("raw_events", result1.applied)


# ---------------------------------------------------------------------------
# dry-run mode
# ---------------------------------------------------------------------------


def test_adopt_dry_run(src_info: SourceInfo, tmp_path: Path) -> None:
    """dry-run mode should not write to the target db."""
    pkg_path = tmp_path / "test.hmpkg"
    pack(src_info, out=pkg_path)

    target_db = tmp_path / "dryrun_target" / "memory.sqlite"
    target_db.parent.mkdir(parents=True)
    Memory("openclaw__test_dry", backend_config={"db_path": str(target_db)})
    with sqlite3.connect(str(target_db)) as conn:
        before = list(conn.iterdump())

    summary = adopt(
        pkg_path,
        "openclaw:openclaw__test_dry",
        dry_run=True,
        target_db_path=target_db,
    )

    assert summary.dry_run
    assert summary.applied > 0  # Estimated row count.

    assert summary.target_db_path == str(target_db)
    with sqlite3.connect(str(target_db)) as conn:
        assert list(conn.iterdump()) == before


# ---------------------------------------------------------------------------
# host-rewrite mode
# ---------------------------------------------------------------------------


def test_adopt_host_rewrite_target(src_info: SourceInfo, tmp_path: Path) -> None:
    """host-rewrite=target should rewrite RawEvent.host to the target host."""
    pkg_path = tmp_path / "test.hmpkg"
    pack(src_info, out=pkg_path)

    target_db = tmp_path / "rewrite_target" / "memory.sqlite"
    target_db.parent.mkdir(parents=True)

    summary = adopt(
        pkg_path,
        "openclaw:openclaw__test_rewrite",
        host_rewrite="target",
        on_conflict="skip",
        target_db_path=target_db,
    )

    assert summary.applied > 0

    # Verify the host field has been rewritten.
    conn = sqlite3.connect(summary.target_db_path)
    rows = conn.execute(f"SELECT host FROM {summary.target_namespace}_raw_events").fetchall()
    conn.close()

    for row in rows:
        assert row[0] == "openclaw", f"expected host='openclaw', got host='{row[0]}'"


# ---------------------------------------------------------------------------
# basic doctor checks
# ---------------------------------------------------------------------------


def test_doctor_after_adopt(src_info: SourceInfo, tmp_path: Path) -> None:
    """After adopt, doctor should pass the db_accessible check."""
    pkg_path = tmp_path / "test.hmpkg"
    pack(src_info, out=pkg_path)

    target_db = tmp_path / "doctor_target" / "memory.sqlite"
    target_db.parent.mkdir(parents=True)

    summary = adopt(pkg_path, "openclaw:openclaw__test_doctor", on_conflict="skip", target_db_path=target_db)

    report = doctor(
        "openclaw:openclaw__test_doctor",
        db_path=summary.target_db_path,
        compare_with=pkg_path,
    )

    assert isinstance(report, DoctorReport)
    # A freshly adopted store is healthy end to end: every check passes,
    # including schema_version (stamped by the backend on open since 0.9.2).
    assert report.all_passed, [c.to_dict() for c in report.checks if not c.passed]
    schema = next(c for c in report.checks if c.name == "schema_version")
    assert "schema_version = " in schema.detail


def test_doctor_passes_on_legacy_store_without_schema_version(src_info: SourceInfo, tmp_path: Path) -> None:
    """Stores created before 0.9.2 have no schema_version row in meta —
    doctor must treat that as an older store, not corruption."""
    import sqlite3

    pkg_path = tmp_path / "legacy.hmpkg"
    pack(src_info, out=pkg_path)
    target_db = tmp_path / "legacy_target" / "memory.sqlite"
    target_db.parent.mkdir(parents=True)
    adopt(pkg_path, "openclaw:openclaw__legacy", on_conflict="skip", target_db_path=target_db)

    # Simulate a legacy store: strip the stamp the backend just wrote.
    conn = sqlite3.connect(target_db)
    conn.execute("DELETE FROM openclaw__legacy_meta WHERE key = 'schema_version'")
    conn.commit()
    conn.close()

    report = doctor("openclaw:openclaw__legacy", db_path=str(target_db))
    schema = next(c for c in report.checks if c.name == "schema_version")
    assert schema.passed
    assert "not recorded" in schema.detail


# ---------------------------------------------------------------------------
# empty namespace rejects packing
# ---------------------------------------------------------------------------


def test_pack_rejects_empty_namespace(tmp_path: Path) -> None:
    """An empty namespace (0 raw_events) should reject packing."""
    db_path = tmp_path / "empty" / "memory.sqlite"
    db_path.parent.mkdir(parents=True)
    # Create an empty Memory (no data written).
    Memory(
        namespace="agent_empty_",
        backend="sqlite",
        backend_config={"db_path": str(db_path)},
    )

    src = SourceInfo(
        host_kind="agent",
        db_path=str(db_path),
        namespace="agent_empty_",
        raw_event_count=0,
        agent_name="empty",
    )

    with pytest.raises(ValueError, match="nothing to migrate"):
        pack(src, out=tmp_path / "empty.hmpkg")


# ---------------------------------------------------------------------------
# progress callback
# ---------------------------------------------------------------------------


def test_pack_progress_callback(src_info: SourceInfo, tmp_path: Path) -> None:
    """pack should report progress via the progress callback."""
    phases: list[str] = []

    def _cb(done: int, total: int, phase: str) -> None:
        phases.append(phase)

    pack(src_info, out=tmp_path / "test_progress.hmpkg", progress=_cb)
    assert len(phases) > 0
    assert "done" in phases


def test_adopt_progress_callback(src_info: SourceInfo, tmp_path: Path) -> None:
    """adopt should report progress via the progress callback."""
    pkg_path = tmp_path / "test_adopt_progress.hmpkg"
    pack(src_info, out=pkg_path)

    target_db = tmp_path / "progress_target" / "memory.sqlite"
    target_db.parent.mkdir(parents=True)

    phases: list[str] = []

    def _cb(done: int, total: int, phase: str) -> None:
        phases.append(phase)

    adopt(pkg_path, "openclaw:openclaw__test_progress_cb", target_db_path=target_db, progress=_cb)
    assert len(phases) > 0
    assert "done" in phases


# ---------------------------------------------------------------------------
# OpenClaw configured-namespace default (openclaw.json)
# ---------------------------------------------------------------------------


def _write_openclaw_config(tmp_path: Path, namespace: str | None, db_path: str | None = None) -> Path:
    import json

    cfg_path = tmp_path / "openclaw.json"
    entry: dict = {"enabled": True}
    config: dict = {}
    if namespace is not None:
        config["namespace"] = namespace
    if db_path is not None:
        config["db_path"] = db_path
    if config:
        entry["config"] = config
    cfg_path.write_text(
        json.dumps({"plugins": {"entries": {"octopmemory": entry}}}),
        encoding="utf-8",
    )
    return cfg_path


def test_configured_openclaw_namespace_parses_config(tmp_path: Path) -> None:
    from octop_memory.operations.migration.portable import configured_openclaw_namespace

    cfg_path = _write_openclaw_config(tmp_path, "openclaw__live")
    assert configured_openclaw_namespace(cfg_path) == "openclaw__live"
    # Missing namespace key / missing file both fall back to None.
    assert configured_openclaw_namespace(_write_openclaw_config(tmp_path, None)) is None
    assert configured_openclaw_namespace(tmp_path / "missing.json") is None


def test_adopt_defaults_to_configured_openclaw_namespace(
    src_info: SourceInfo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """adopt(..., "openclaw") without a namespace must target the namespace the
    installed plugin actually reads, not a generated openclaw__<source-name>."""
    from octop_memory.operations.migration.portable import sources as portable_sources

    monkeypatch.setattr(portable_sources, "DEFAULT_OPENCLAW_CONFIG", _write_openclaw_config(tmp_path, "openclaw__live"))
    pkg_path = tmp_path / "cfg_ns.hmpkg"
    pack(src_info, out=pkg_path)
    target_db = tmp_path / "cfg_ns_target" / "memory.sqlite"
    target_db.parent.mkdir(parents=True)

    summary = adopt(pkg_path, "openclaw", target_db_path=target_db)
    assert summary.target_namespace == "openclaw__live"
    assert summary.applied > 0


def test_adopt_explicit_namespace_beats_configured(
    src_info: SourceInfo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from octop_memory.operations.migration.portable import sources as portable_sources

    monkeypatch.setattr(portable_sources, "DEFAULT_OPENCLAW_CONFIG", _write_openclaw_config(tmp_path, "openclaw__live"))
    pkg_path = tmp_path / "explicit_ns.hmpkg"
    pack(src_info, out=pkg_path)
    target_db = tmp_path / "explicit_ns_target" / "memory.sqlite"
    target_db.parent.mkdir(parents=True)

    summary = adopt(pkg_path, "openclaw:openclaw__explicit", target_db_path=target_db)
    assert summary.target_namespace == "openclaw__explicit"


def test_adopt_falls_back_to_generated_namespace_without_config(
    src_info: SourceInfo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from octop_memory.operations.migration.portable import sources as portable_sources

    monkeypatch.setattr(portable_sources, "DEFAULT_OPENCLAW_CONFIG", tmp_path / "missing.json")
    pkg_path = tmp_path / "fallback_ns.hmpkg"
    pack(src_info, out=pkg_path)
    target_db = tmp_path / "fallback_ns_target" / "memory.sqlite"
    target_db.parent.mkdir(parents=True)

    summary = adopt(pkg_path, "openclaw", target_db_path=target_db)
    # Generated from the source agent name ("test"), the pre-existing behaviour.
    assert summary.target_namespace == "openclaw__test"


def test_doctor_defaults_to_configured_openclaw_namespace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from octop_memory.operations.migration.portable import sources as portable_sources

    monkeypatch.setattr(portable_sources, "DEFAULT_OPENCLAW_CONFIG", _write_openclaw_config(tmp_path, "openclaw__live"))
    report = doctor("openclaw", db_path=str(tmp_path / "nonexistent.sqlite"))
    assert report.namespace == "openclaw__live"


def test_adopt_uses_configured_db_path_for_matching_namespace(
    src_info: SourceInfo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When adopting into the plugin's own namespace, the plugin's configured
    db_path (e.g. relocated under ~/.openclaw for sandboxed hosts) wins over
    the ~/.octopmemory default."""
    from octop_memory.operations.migration.portable import sources as portable_sources

    configured_db = tmp_path / "openclaw_home" / "octopmemory" / "openclaw__live" / "memory.sqlite"
    monkeypatch.setattr(
        portable_sources,
        "DEFAULT_OPENCLAW_CONFIG",
        _write_openclaw_config(tmp_path, "openclaw__live", str(configured_db)),
    )
    pkg_path = tmp_path / "cfg_db.hmpkg"
    pack(src_info, out=pkg_path)

    summary = adopt(pkg_path, "openclaw")
    assert summary.target_namespace == "openclaw__live"
    assert summary.target_db_path == str(configured_db)
    assert configured_db.exists()


def test_adopt_ignores_configured_db_path_for_other_namespace(
    src_info: SourceInfo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An explicit different namespace must not inherit the plugin's db_path."""
    from octop_memory.operations.migration.portable import sources as portable_sources

    configured_db = tmp_path / "openclaw_home" / "live.sqlite"
    monkeypatch.setattr(
        portable_sources,
        "DEFAULT_OPENCLAW_CONFIG",
        _write_openclaw_config(tmp_path, "openclaw__live", str(configured_db)),
    )
    pkg_path = tmp_path / "other_ns.hmpkg"
    pack(src_info, out=pkg_path)
    target_db = tmp_path / "other_target" / "memory.sqlite"
    target_db.parent.mkdir(parents=True)

    summary = adopt(pkg_path, "openclaw:openclaw__other", target_db_path=target_db)
    assert summary.target_db_path == str(target_db)
    assert not configured_db.exists()


def test_doctor_uses_configured_db_path_for_matching_namespace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from octop_memory.operations.migration.portable import sources as portable_sources

    configured_db = tmp_path / "openclaw_home" / "memory.sqlite"
    monkeypatch.setattr(
        portable_sources,
        "DEFAULT_OPENCLAW_CONFIG",
        _write_openclaw_config(tmp_path, "openclaw__live", str(configured_db)),
    )
    report = doctor("openclaw")
    assert report.namespace == "openclaw__live"
    assert report.db_path == str(configured_db)
