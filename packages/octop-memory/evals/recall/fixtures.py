"""Synthetic recall evaluation fixture builder.

Generates entity, topical, time-bounded and co-reference queries from a
small synthetic corpus. Names and assertions are test data, not claims
about real people, projects or product versions. Dates default to the
current time and ids are generated per run; this is a regression aid,
not a comprehensive or strictly deterministic quality benchmark.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from octop_memory.core import Memory
from octop_memory.types import AtomCard, Entity, RawEvent

# A small but diverse corpus. Each entry is one entity + a handful of
# atoms; the query generator below builds entity_lookup, time_bounded,
# topical, and co-reference queries from this seed.
_SEED_CORPUS: list[dict[str, Any]] = [
    {
        "name": "Hermes",
        "type": "Project",
        "atoms": [
            ("我们决定 Hermes 用 Postgres 16 作为主存储", "high"),
            ("Hermes 的部署目标是 2026-Q3 上线", "medium"),
            ("Hermes 后端语言锁定为 Python 3.13", "medium"),
        ],
    },
    {
        "name": "OpenClaw",
        "type": "Project",
        "atoms": [
            ("OpenClaw 插件 SDK 通过 npm 分发", "high"),
            ("OpenClaw 默认 memory adapter 是 memory-core", "high"),
            ("OpenClaw 的 hook API 在 v2.4 之后稳定", "medium"),
        ],
    },
    {
        "name": "Alice",
        "type": "Person",
        "atoms": [
            ("Alice 主要负责 Hermes 的后端", "high"),
            ("Alice 喜欢用 vim", "medium"),
        ],
    },
    {
        "name": "Bob",
        "type": "Person",
        "atoms": [
            ("Bob 在做 OpenClaw 的插件 SDK", "high"),
            ("Bob 用 IntelliJ", "low"),
        ],
    },
    {
        "name": "Postgres",
        "type": "Tech",
        "atoms": [
            ("Postgres 16 引入了逻辑复制改进", "medium"),
            ("Postgres 不要用 ON DELETE CASCADE 来管理生命周期", "high"),
        ],
    },
    {
        "name": "Python",
        "type": "Tech",
        "atoms": [
            ("Python 3.13 默认开启了 free-threaded 模式", "medium"),
            ("Python 项目首选 uv 做包管理", "high"),
        ],
    },
]


@dataclass
class EvalQuery:
    """One synthetic query with its known positive source ids.

    ``expected_source_ids`` is the union of the atom ids that should
    match AND the raw event ids backing them. This lets us evaluate
    raw-only baselines fairly (their snippets carry raw_event ids,
    not atom ids). Atom and raw ids are both accepted as relevant.
    """

    qid: str
    query: str
    expected_source_ids: tuple[str, ...]
    klass: str  # "entity_lookup" / "time_bounded" / "topical" / "coref"
    thread_id: str | None = None


@dataclass
class EvalCorpus:
    """Seeded :class:`Memory` plus the labeled query set."""

    memory: Memory
    queries: list[EvalQuery] = field(default_factory=list)
    entity_id_by_name: dict[str, str] = field(default_factory=dict)


def seed_memory(memory: Memory, *, base_time: datetime | None = None) -> EvalCorpus:
    """Insert the synthetic corpus into ``memory`` and label queries.

    All atoms get ``occurred_at`` distributed in a 60-day window
    ending at ``base_time`` so the time-bounded queries land
    deterministically.
    """
    when = base_time or datetime.now(UTC)
    corpus = EvalCorpus(memory=memory)
    raw_id_for_atom: dict[str, str] = {}

    for c_idx, project in enumerate(_SEED_CORPUS):
        entity_id = str(uuid.uuid4())
        memory.add_entity(
            Entity(
                id=entity_id,
                entity_type=project["type"],
                canonical_name=project["name"],
                aliases=[],
                atom_count=len(project["atoms"]),
                created_at=when,
            )
        )
        corpus.entity_id_by_name[project["name"]] = entity_id

        for a_idx, (assertion, importance) in enumerate(project["atoms"]):
            occurred = when - timedelta(days=(c_idx * 10) + a_idx)  # spread out
            raw_id = str(uuid.uuid4())
            memory.add_raw_batch(
                [
                    RawEvent(
                        id=raw_id,
                        host="evals",
                        session_id=f"sess-{c_idx}",
                        thread_id=None,
                        user=None,
                        timestamp=occurred,
                        event_type="user_message",
                        content=assertion,
                        payload={},
                    )
                ]
            )
            atom_id = str(uuid.uuid4())
            raw_id_for_atom[atom_id] = raw_id
            memory.add_atom(
                AtomCard(
                    id=atom_id,
                    entity_id=entity_id,
                    candidate_id=str(uuid.uuid4()),
                    raw_event_ids=[raw_id],
                    assertion=assertion,
                    verbatim_quote=assertion,
                    quote_event_id=raw_id,
                    search_terms=[project["name"]],
                    occurred_at=occurred,
                    confidence="high",
                    importance=importance,  # type: ignore[arg-type]
                    created_at=occurred,
                )
            )

    def _expected(predicate: Callable[[AtomCard], bool]) -> tuple[str, ...]:
        ids: list[str] = []
        for atom in memory.list_atoms():
            if predicate(atom):
                ids.append(atom.id)
                rid = raw_id_for_atom.get(atom.id)
                if rid:
                    ids.append(rid)
        return tuple(ids)

    # ---- query generation -------------------------------------------
    # 1) entity_lookup — query directly names an entity.
    for name, eid in corpus.entity_id_by_name.items():
        positives = _expected(lambda a, eid=eid: a.entity_id == eid)
        corpus.queries.append(
            EvalQuery(
                qid=f"entity_{name.lower()}",
                query=f"{name} 现在怎么样？",
                expected_source_ids=positives,
                klass="entity_lookup",
            )
        )

    # 2) topical — query topic word that should match multiple atoms.
    for topic in ("Postgres", "Python", "vim", "IntelliJ", "Hermes 后端"):
        positives = _expected(lambda a, t=topic: t.lower() in a.assertion.lower())
        if positives:
            corpus.queries.append(
                EvalQuery(
                    qid=f"topical_{topic.lower().replace(' ', '_')}",
                    query=f"我们以前是怎么用 {topic} 的？",
                    expected_source_ids=positives,
                    klass="topical",
                )
            )

    # 3) time_bounded — last week.
    last_week_positives = _expected(lambda a, cutoff=when - timedelta(days=7): a.occurred_at >= cutoff)
    if last_week_positives:
        corpus.queries.append(
            EvalQuery(
                qid="time_last_week",
                query="上周我们聊过什么？",
                expected_source_ids=last_week_positives,
                klass="time_bounded",
            )
        )

    # 4) co-reference — needs thread_id with a primed active entity.
    coref_thread = f"thr-{uuid.uuid4().hex[:8]}"
    primary_entity = corpus.entity_id_by_name["Hermes"]
    memory.upsert_active_entity(coref_thread, primary_entity, source="manual", when=when)
    coref_positives = _expected(lambda a, eid=primary_entity: a.entity_id == eid)
    corpus.queries.append(
        EvalQuery(
            qid="coref_those",
            query="那个项目最近怎么样？",
            expected_source_ids=coref_positives,
            klass="coref",
            thread_id=coref_thread,
        )
    )

    # Keep the query set small to avoid duplicating nearly identical cases.

    return corpus


def write_fixture(corpus: EvalCorpus, dest: Path) -> None:
    """Persist the labeled query set so eval runs are reproducible."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "queries": [
            {
                "qid": q.qid,
                "query": q.query,
                "expected_source_ids": list(q.expected_source_ids),
                "klass": q.klass,
                "thread_id": q.thread_id,
            }
            for q in corpus.queries
        ],
        "entity_id_by_name": corpus.entity_id_by_name,
    }
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


__all__ = ["EvalCorpus", "EvalQuery", "seed_memory", "write_fixture"]
