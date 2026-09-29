"""T-35 — namespace isolation acceptance over real ``octop_memory`` stores.

``open_memory_kwargs`` is the single place that decides which namespace a
``Memory`` is built with. These tests construct real ``Memory`` instances over a
real SQLite file (no LLM, no harness) and prove that the namespace it returns is
what keeps two namespaces apart: project A's sentinel is invisible to *every*
query issued on project B, and the other way round.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("octop_memory.core")

from octop.config import OctopConfig
from octop.infra.agents.memory.backend import (
    agent_memory_namespace,
    open_memory_kwargs,
    resolve_project_namespace,
)
from octop.infra.utils.ulid import new_ulid

AGENT_ID = "a1"

# "任意查询（含最普通的查询）": the sentinel itself is probed separately; these
# are the generic ones — a shared prefix, a generic word, a single letter, the
# empty string.
_GENERIC_QUERIES = ("SENTINEL", "记忆", "user", "a", "")


def _now() -> datetime:
    return datetime.now(UTC)


def _cfg(db_path: Path) -> dict[str, Any]:
    return {"memory": {"backend": {"type": "sqlite", "db_path": str(db_path)}}}


def _open(namespace: str | None, *, db_path: Path, workspace: Path) -> tuple[str, Any]:
    """Build ``Memory`` the way production does — entirely from ``open_memory_kwargs``."""
    from octop_memory.core import Memory

    ns, backend, backend_config = open_memory_kwargs(
        agent_id=AGENT_ID,
        cfg=_cfg(db_path),
        octop_config=OctopConfig(),
        workspace_dir=workspace,
        namespace=namespace,
    )
    return ns, Memory(namespace=ns, backend=backend, backend_config=backend_config)


def _atom(memory: Any, sentinel: str) -> None:
    from octop_memory.types import AtomCard

    memory.add_atom(
        AtomCard(
            id=f"atom-{sentinel}",
            entity_id=f"ent-{sentinel}",
            candidate_id=f"cand-{sentinel}",
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


def _candidate(memory: Any, sentinel: str) -> None:
    from octop_memory.types import Candidate

    memory.add_candidate(
        Candidate(
            id=f"cand-{sentinel}",
            raw_event_ids=[],
            candidate_type="Preference",
            status="promoted",
            title=sentinel,
            assertion=sentinel,
            verbatim_quote=sentinel,
            quote_event_id="",
            subject_name="user",
            subject_entity_type="User",
            target_entity_id=f"ent-{sentinel}",
            confidence="high",
            importance="high",
            recommended_action="promote",
            promotion_reason="seed",
            extractor_version="test",
            created_at=_now(),
        )
    )


def _seed(memory: Any, sentinel: str) -> None:
    """Write one entity + atom + raw event + candidate carrying ``sentinel``."""
    from octop_memory.types import Entity

    memory.add_entity(
        Entity(
            id=f"ent-{sentinel}",
            entity_type="User",
            canonical_name=sentinel,
            aliases=[],
            atom_count=0,
            created_at=_now(),
        )
    )
    _atom(memory, sentinel)
    memory.add_raw(sentinel, event_type="user_message", host="octop")
    _candidate(memory, sentinel)


def _leaks(memory: Any, sentinel: str) -> list[str]:
    """Return the probes on which ``sentinel`` became visible in ``memory``."""
    leaked: list[str] = []
    for query in (sentinel, *_GENERIC_QUERIES):
        if any(
            sentinel in f"{a.assertion}{a.verbatim_quote}"
            for a in memory.search_atoms(query, limit=50)
        ):
            leaked.append(f"search_atoms({query!r})")
        if any(sentinel in f"{n.content}{n.topic}" for n in memory.recall(query, limit=5)):
            leaked.append(f"recall({query!r})")
        if any(sentinel in (e.content or "") for e in memory.search_raw(query, limit=50)):
            leaked.append(f"search_raw({query!r})")
    if any(sentinel in a.assertion for a in memory.list_atoms(limit=200)):
        leaked.append("list_atoms")
    if any(sentinel in (e.content or "") for e in memory.list_raw(limit=200)):
        leaked.append("list_raw")
    if any(sentinel in c.assertion for c in memory.list_candidates(limit=200)):
        leaked.append("list_candidates")
    if any(sentinel in f"{e.canonical_name}{e.entity_type}" for e in memory.list_entities()):
        leaked.append("list_entities")
    return leaked


def test_project_namespaces_do_not_leak_into_each_other(tmp_path: Path) -> None:
    """T-35 acc.3 — sentinel A/B: A's sentinel has 0 hits on B, and vice versa."""
    db_path = tmp_path / "memory.sqlite"
    sentinel_a = f"SENTINEL-A-{new_ulid()}"
    sentinel_b = f"SENTINEL-B-{new_ulid()}"

    ns_a, memory_a = _open("project_P1", db_path=db_path, workspace=tmp_path)
    ns_b, memory_b = _open("project_P2", db_path=db_path, workspace=tmp_path)
    assert ns_a == "project_P1"
    assert ns_b == "project_P2"

    _seed(memory_a, sentinel_a)
    _seed(memory_b, sentinel_b)

    # Positive control: each namespace does see its own sentinel, so "0 hits"
    # below is isolation rather than an empty store.
    assert [a.assertion for a in memory_a.search_atoms(sentinel_a)] == [sentinel_a]
    assert [a.assertion for a in memory_b.search_atoms(sentinel_b)] == [sentinel_b]

    assert _leaks(memory_b, sentinel_a) == []
    assert _leaks(memory_a, sentinel_b) == []


def test_agent_private_namespace_is_isolated_from_the_project_namespace(tmp_path: Path) -> None:
    """The default path (no override) stays the private ``agent_{id}`` store."""
    db_path = tmp_path / "memory.sqlite"
    sentinel_agent = f"SENTINEL-AGENT-{new_ulid()}"
    sentinel_project = f"SENTINEL-PROJECT-{new_ulid()}"

    ns_agent, agent_memory = _open(None, db_path=db_path, workspace=tmp_path)
    ns_project, project_memory = _open("project_P1", db_path=db_path, workspace=tmp_path)
    assert ns_agent == agent_memory_namespace(AGENT_ID) == "agent_a1"
    assert ns_project == "project_P1"

    _seed(agent_memory, sentinel_agent)
    _seed(project_memory, sentinel_project)

    assert [a.assertion for a in agent_memory.search_atoms(sentinel_agent)] == [sentinel_agent]
    assert [a.assertion for a in project_memory.search_atoms(sentinel_project)] == [
        sentinel_project
    ]
    assert _leaks(project_memory, sentinel_agent) == []
    assert _leaks(agent_memory, sentinel_project) == []


def test_write_and_read_resolve_the_same_namespace(tmp_path: Path) -> None:
    """T-35 acc.2 — what a write resolves, a fresh read resolves too."""
    db_path = tmp_path / "memory.sqlite"
    sentinel = f"SENTINEL-A-{new_ulid()}"

    ns_writer, writer = _open("project_P1", db_path=db_path, workspace=tmp_path)
    _seed(writer, sentinel)

    # A second, independent resolution + a second Memory instance = the read side.
    ns_reader, reader = _open("project_P1", db_path=db_path, workspace=tmp_path)
    assert ns_reader == ns_writer == "project_P1"
    assert [a.assertion for a in reader.search_atoms(sentinel)] == [sentinel]
    assert [c.assertion for c in reader.list_candidates(limit=50)] == [sentinel]
    assert [e.content for e in reader.list_raw(limit=50)] == [sentinel]


def test_namespace_resolved_from_the_projects_column_is_the_one_written(tmp_path: Path) -> None:
    """``projects.memory_namespace`` is the authority: a renamed ns takes effect."""
    db_path = tmp_path / "memory.sqlite"
    sentinel = f"SENTINEL-A-{new_ulid()}"
    column_value = "project_RENAMED"

    ns = resolve_project_namespace(memory_namespace=column_value, project_id="P1")
    assert ns == column_value
    ns_written, writer = _open(ns, db_path=db_path, workspace=tmp_path)
    assert ns_written == column_value
    _seed(writer, sentinel)

    # The convention-derived namespace must NOT be where the row's data landed.
    _, convention_memory = _open(
        resolve_project_namespace(memory_namespace=None, project_id="P1"),
        db_path=db_path,
        workspace=tmp_path,
    )
    assert _leaks(convention_memory, sentinel) == []
    _, reader = _open(column_value, db_path=db_path, workspace=tmp_path)
    assert [a.assertion for a in reader.search_atoms(sentinel)] == [sentinel]


def test_auto_extracted_candidates_land_in_the_agent_namespace_only(tmp_path: Path) -> None:
    """T-35 acc.4 — extraction candidates go to ``agent_{id}``, never ``project_{id}``.

    Auto-extraction is bound to the session, so its namespace is the default one
    (and the harness gets the same value through ``HarnessAgentConfig(name=…)``,
    which T-35 does not touch).
    """
    from octop.infra.agents.manager import _memory_namespace as harness_convention

    db_path = tmp_path / "memory.sqlite"
    sentinel = f"SENTINEL-CAND-{new_ulid()}"

    ns_agent, agent_memory = _open(None, db_path=db_path, workspace=tmp_path)
    assert ns_agent == harness_convention(AGENT_ID) == "agent_a1"
    _candidate(agent_memory, sentinel)

    _, project_memory = _open("project_P1", db_path=db_path, workspace=tmp_path)
    assert [c.assertion for c in agent_memory.list_candidates(limit=100)] == [sentinel]
    assert project_memory.list_candidates(limit=100) == []
    assert project_memory.search_candidates(sentinel, limit=50) == []
    assert _leaks(project_memory, sentinel) == []
