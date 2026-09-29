"""T-36 — cross-namespace recall merge (project → team → agent private).

These tests build real ``octop_memory`` stores over one real SQLite file (no LLM,
no harness) and drive the merge layer through it. Every "only one hit" assertion
is paired with a positive control proving the fact really is in *both*
namespaces — otherwise a silently empty store would pass the dedup test for the
wrong reason (PLAN ``R17``).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("octop_memory.core")

from octop.config import OctopConfig
from octop.infra.agents.memory.multi_ns import (
    LAYER_ORDER,
    MemoryScope,
    MultiNsRecall,
    ProjectInjectVersion,
    normalize_memory_text,
    team_memory_namespace,
)
from octop.infra.utils.ulid import new_ulid

AGENT_ID = "a1"
TEAM_ID = "T1"
PROJECT_ID = "P1"


def _now() -> datetime:
    return datetime.now(UTC)


def _cfg(db_path: Path) -> dict[str, Any]:
    return {"memory": {"backend": {"type": "sqlite", "db_path": str(db_path)}}}


def _scope(db_path: Path, workspace: Path, *, team_agent_id: str | None = TEAM_ID) -> MemoryScope:
    return MemoryScope(
        agent_id=AGENT_ID,
        cfg=_cfg(db_path),
        octop_config=OctopConfig(),
        workspace_dir=workspace,
        team_agent_id=team_agent_id,
    )


def _seed(memory: Any, sentinel: str) -> None:
    """Write one atom whose assertion is ``sentinel`` (what recall returns)."""
    from octop_memory.types import AtomCard

    memory.add_atom(
        AtomCard(
            id=f"atom-{new_ulid()}",
            entity_id=f"ent-{new_ulid()}",
            candidate_id=f"cand-{new_ulid()}",
            raw_event_ids=[],
            assertion=sentinel,
            verbatim_quote=sentinel,
            quote_event_id="",
            search_terms=[sentinel],
            occurred_at=_now(),
            confidence="high",
            importance="high",
            created_at=_now(),
        )
    )


def _contains(memory: Any, sentinel: str) -> bool:
    """Positive control: the fact really is stored in this namespace."""
    return any(sentinel in a.assertion for a in memory.search_atoms(sentinel, limit=50))


# ---------------------------------------------------------------------------
# Layer order and namespaces
# ---------------------------------------------------------------------------


def test_recall_order_is_project_then_team_then_agent() -> None:
    """The fixed order from PLAN「记忆分层」— earlier layers win a duplicate."""
    assert LAYER_ORDER == ("project", "team", "agent")


def test_team_namespace_helper() -> None:
    assert team_memory_namespace(TEAM_ID) == "team_T1"


def test_layers_present_depend_on_context(tmp_path: Path) -> None:
    recall = MultiNsRecall(_scope(tmp_path / "m.sqlite", tmp_path))
    assert recall.layers(project_id=PROJECT_ID) == ("project", "team", "agent")
    assert recall.layers(project_id=None) == ("team", "agent")

    no_team = MultiNsRecall(_scope(tmp_path / "m.sqlite", tmp_path, team_agent_id=None))
    assert no_team.layers(project_id=PROJECT_ID) == ("project", "agent")
    assert no_team.layers(project_id=None) == ("agent",)
    recall.close()
    no_team.close()


# ---------------------------------------------------------------------------
# R17 — one memory hit in several layers must appear once
# ---------------------------------------------------------------------------


def test_duplicate_across_project_and_agent_appears_once_as_project(tmp_path: Path) -> None:
    """R17: the same fact in two namespaces ⇒ one hit, tagged project (> agent).

    The two namespaces are separate stores, so the duplicate carries two atom
    ids — the id key alone cannot catch it. Both positives are asserted first,
    so "one hit" is dedup and not an empty store.
    """
    db_path = tmp_path / "memory.sqlite"
    sentinel = f"multinsdup{new_ulid()}"
    recall = MultiNsRecall(_scope(db_path, tmp_path))

    project_memory = recall.memory_for("project", project_id=PROJECT_ID)
    agent_memory = recall.memory_for("agent")
    _seed(project_memory, sentinel)
    _seed(agent_memory, sentinel)
    assert _contains(project_memory, sentinel)
    assert _contains(agent_memory, sentinel)

    hits = [h for h in recall.recall(sentinel, project_id=PROJECT_ID) if sentinel in h.text]
    assert len(hits) == 1, [h.text for h in hits]
    assert hits[0].source_layer == "project"
    recall.close()


def test_duplicate_across_team_and_agent_resolves_to_team(tmp_path: Path) -> None:
    """Team sits between project and agent, so team wins over agent."""
    db_path = tmp_path / "memory.sqlite"
    sentinel = f"multinsdup{new_ulid()}"
    recall = MultiNsRecall(_scope(db_path, tmp_path))

    team_memory = recall.memory_for("team")
    agent_memory = recall.memory_for("agent")
    _seed(team_memory, sentinel)
    _seed(agent_memory, sentinel)
    assert _contains(team_memory, sentinel)
    assert _contains(agent_memory, sentinel)

    hits = [h for h in recall.recall(sentinel, project_id=PROJECT_ID) if sentinel in h.text]
    assert len(hits) == 1, [h.text for h in hits]
    assert hits[0].source_layer == "team"
    recall.close()


def test_duplicate_across_all_three_layers_resolves_to_project(tmp_path: Path) -> None:
    """All three layers hold the fact ⇒ still exactly one hit, from project."""
    db_path = tmp_path / "memory.sqlite"
    sentinel = f"multinsdup{new_ulid()}"
    recall = MultiNsRecall(_scope(db_path, tmp_path))

    for layer in LAYER_ORDER:
        _seed(recall.memory_for(layer, project_id=PROJECT_ID), sentinel)
    for layer in LAYER_ORDER:
        assert _contains(recall.memory_for(layer, project_id=PROJECT_ID), sentinel)

    hits = [h for h in recall.recall(sentinel, project_id=PROJECT_ID) if sentinel in h.text]
    assert len(hits) == 1, [h.text for h in hits]
    assert hits[0].source_layer == "project"
    recall.close()


def test_duplicate_matches_after_whitespace_is_normalized(tmp_path: Path) -> None:
    """The content key is normalized, so formatting drift does not double-report."""
    db_path = tmp_path / "memory.sqlite"
    token = f"multinsdup{new_ulid()}"
    recall = MultiNsRecall(_scope(db_path, tmp_path))

    project_memory = recall.memory_for("project", project_id=PROJECT_ID)
    agent_memory = recall.memory_for("agent")
    _seed(project_memory, f"{token}   spaced   out")
    _seed(agent_memory, f"{token} spaced out")
    assert _contains(project_memory, token)
    assert _contains(agent_memory, token)

    hits = [h for h in recall.recall(token, project_id=PROJECT_ID) if token in h.text]
    assert len(hits) == 1, [h.text for h in hits]
    assert hits[0].source_layer == "project"
    recall.close()


def test_distinct_memories_from_every_layer_all_survive(tmp_path: Path) -> None:
    """Dedup must not over-collapse: three different facts stay three hits."""
    db_path = tmp_path / "memory.sqlite"
    token = f"multinskeep{new_ulid()}"
    recall = MultiNsRecall(_scope(db_path, tmp_path))

    for layer in LAYER_ORDER:
        _seed(recall.memory_for(layer, project_id=PROJECT_ID), f"{token} from {layer}")

    hits = [h for h in recall.recall(token, project_id=PROJECT_ID) if token in h.text]
    assert len(hits) == 3, [h.text for h in hits]
    assert {h.source_layer for h in hits} == {"project", "team", "agent"}
    recall.close()


# ---------------------------------------------------------------------------
# No project context ⇒ never guess a project
# ---------------------------------------------------------------------------


def test_without_project_context_the_project_layer_is_not_recalled(tmp_path: Path) -> None:
    """Differential: the same project fact is invisible until ``project_id`` is given."""
    db_path = tmp_path / "memory.sqlite"
    token = f"multinsnoproj{new_ulid()}"
    recall = MultiNsRecall(_scope(db_path, tmp_path))

    project_memory = recall.memory_for("project", project_id=PROJECT_ID)
    _seed(project_memory, f"{token} project only")
    _seed(recall.memory_for("team"), f"{token} team only")
    _seed(recall.memory_for("agent"), f"{token} agent only")
    assert _contains(project_memory, token)

    without = [h for h in recall.recall(token) if token in h.text]
    assert {h.source_layer for h in without} == {"team", "agent"}, [h.text for h in without]

    # Positive control: supplying project_id reaches the very same project store.
    with_project = [h for h in recall.recall(token, project_id=PROJECT_ID) if token in h.text]
    assert {h.source_layer for h in with_project} == {"project", "team", "agent"}
    recall.close()


def test_agent_without_a_team_recalls_only_itself(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.sqlite"
    token = f"multinsnoteam{new_ulid()}"
    recall = MultiNsRecall(_scope(db_path, tmp_path, team_agent_id=None))
    _seed(recall.memory_for("agent"), f"{token} agent only")

    hits = [h for h in recall.recall(token) if token in h.text]
    assert [h.source_layer for h in hits] == ["agent"]
    recall.close()


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


def test_every_hit_carries_its_source_layer(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.sqlite"
    token = f"multinslayer{new_ulid()}"
    recall = MultiNsRecall(_scope(db_path, tmp_path))
    for layer in LAYER_ORDER:
        _seed(recall.memory_for(layer, project_id=PROJECT_ID), f"{token} from {layer}")

    hits = [h for h in recall.recall(token, project_id=PROJECT_ID) if token in h.text]
    assert hits
    for hit in hits:
        assert hit.source_layer in LAYER_ORDER
        assert hit.source_id
        assert hit.layer == "atom"
    recall.close()


def test_normalize_memory_text_folds_whitespace_and_case() -> None:
    assert normalize_memory_text("  A\t b\n\nC ") == "a b c"
    assert normalize_memory_text("x   y") == normalize_memory_text("X Y")


# ---------------------------------------------------------------------------
# Per-namespace timeout discipline
# ---------------------------------------------------------------------------


def test_one_layer_timing_out_leaves_the_other_layers_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each namespace is treated as one source: a timeout drops only that layer."""
    import octop_memory.pipeline.recall.multi_source as multi_source
    from octop_memory.pipeline.recall.timeout import TimeoutExceededError

    db_path = tmp_path / "memory.sqlite"
    token = f"multinstimeout{new_ulid()}"
    recall = MultiNsRecall(_scope(db_path, tmp_path))
    for layer in LAYER_ORDER:
        _seed(recall.memory_for(layer, project_id=PROJECT_ID), f"{token} from {layer}")

    real_gather = multi_source.gather_candidates

    def _timeout_on_project(memory: Any, parsed: Any, **kwargs: Any) -> Any:
        if str(memory.namespace).startswith("project_"):
            raise TimeoutExceededError(stage="ns:project", budget_ms=1)
        return real_gather(memory, parsed, **kwargs)

    monkeypatch.setattr(multi_source, "gather_candidates", _timeout_on_project)

    hits = [h for h in recall.recall(token, project_id=PROJECT_ID) if token in h.text]
    assert {h.source_layer for h in hits} == {"team", "agent"}, [h.text for h in hits]
    recall.close()


# ---------------------------------------------------------------------------
# projects.inject_version wiring
# ---------------------------------------------------------------------------


class _FakeProjects:
    """Stands in for ``ProjectRepo``'s one used method (structural contract)."""

    def __init__(self) -> None:
        self.versions: dict[str, int] = {}
        self.bump_calls: list[str] = []

    def bump_inject_version(self, project_id: str) -> int:
        self.bump_calls.append(project_id)
        self.versions[project_id] = self.versions.get(project_id, 0) + 1
        return self.versions[project_id]


def test_project_write_bumps_inject_version_and_gates_injection() -> None:
    """A project-layer write advances the watermark; injection follows it."""
    projects = _FakeProjects()
    tracker = ProjectInjectVersion(projects)

    # Nothing injected yet ⇒ the first injection must happen.
    assert tracker.should_inject(PROJECT_ID, 0) is True

    version = tracker.note_write(PROJECT_ID)
    assert version == 1
    assert projects.bump_calls == [PROJECT_ID]
    assert tracker.last_injected(PROJECT_ID) is None
    assert tracker.should_inject(PROJECT_ID, version) is True

    tracker.mark_injected(PROJECT_ID, version)
    assert tracker.last_injected(PROJECT_ID) == 1
    # Unchanged project ⇒ no re-injection.
    assert tracker.should_inject(PROJECT_ID, version) is False

    # Another project-layer write advances the revision ⇒ re-inject.
    assert tracker.note_write(PROJECT_ID) == 2
    assert tracker.should_inject(PROJECT_ID, 2) is True

    # Watermarks are per project.
    assert tracker.last_injected("P2") is None
    assert tracker.should_inject("P2", 0) is True
