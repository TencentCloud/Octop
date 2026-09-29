"""T-39 — memory ↔ document bridge: the ``kb`` recall source (references only).

Two layers of evidence:

* the reference path is driven through a **real knowledge base** (real SQLite
  control plane, real files, the public ``KnowledgeService.preview_document``),
  so "fetch by ``kb_document_id``" is proven against the KB as it ships;
* the merge path is driven through a **real ``octop_memory`` store** plus the
  real ``MultiNsRecall``, so "one hit, correct order" is proven against the same
  dedup/rank discipline the memory layers use.

The negative half of every dedup assertion is a positive control: the same text
really is present in both places, otherwise an empty store would pass for the
wrong reason (PLAN ``R17``).
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from octop.infra.agents.memory.kb_source import (
    KB_LAYER,
    KB_SOURCE_LAYER,
    KbDocument,
    KbRecallBridge,
    KbRecallSource,
    KbReference,
    KnowledgeServiceReader,
    merge_recall_hits,
)
from octop.infra.agents.memory.multi_ns import MemoryScope, MultiNsRecall, RecallHit

pytest.importorskip("octop_memory.core")

from octop.config import OctopConfig
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.knowledge import KnowledgeRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.knowledge.service import KnowledgeService
from octop.infra.utils.paths import PathLayout

_KB_SOURCE_PATH = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "octop"
    / "infra"
    / "agents"
    / "memory"
    / "kb_source.py"
)

PROJECT_ID = "P1"
AGENT_ID = "a1"

#: Short enough to come back whole (no window), so it can be duplicated verbatim
#: by a memory atom in the merge tests.
KB_TEXT = "KBBRIDGE 口径：对账以 RUN.log.md 的实测时刻为准，不用 [now]。"
KB_QUERY = "KBBRIDGE 口径"


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass
class _KbEnv:
    service: KnowledgeService
    owner_id: int
    kb_id: str
    document_id: str = ""

    def add_document(self, content: str, *, name: str = "notes") -> str:
        row = self.service.create_text_document(
            self.kb_id,
            actor_user_id=self.owner_id,
            name=name,
            format="md",
            content=content,
        )
        self.document_id = row.id
        return row.id

    def reference(self, document_id: str | None = None) -> KbReference:
        return KbReference(
            kb_id=self.kb_id,
            document_id=document_id or self.document_id,
            project_id=PROJECT_ID,
            artifact_id="art-1",
            name="notes.md",
        )

    def source(self, **kwargs: Any) -> KbRecallSource:
        reader = KnowledgeServiceReader(self.service, actor_user_id=self.owner_id)
        return KbRecallSource(reader, **kwargs)


@pytest.fixture
def kb(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _KbEnv:
    """A real KB on a real SQLite control plane, with one archived document."""
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path / ".octop"))
    paths = PathLayout.from_env()
    paths.ensure_root()
    db = SqlitePool(paths.db)
    run_migrations(db)
    owner_id = UserRepo(db).create(username="owner", password_hash="h", role="user")
    settings = MagicMock()
    settings.get.side_effect = lambda key, default=None: {
        "knowledge_feature_enabled": "1",
        "knowledge_embedding_backend": "onnx",
        "knowledge_embedding_model": "tiny",
    }.get(key, default)
    services = SimpleNamespace(
        knowledge_repo=KnowledgeRepo(db),
        settings_repo=settings,
        provider_repo=None,
        owner_id=owner_id,
    )
    monkeypatch.setattr(
        "octop.infra.knowledge.service.assert_knowledge_usable",
        lambda *_args, **_kwargs: None,
    )
    service = KnowledgeService(services)
    base = service.create_base(owner_user_id=owner_id, name="Docs")
    env = _KbEnv(service=service, owner_id=owner_id, kb_id=base.id)
    env.add_document(KB_TEXT)
    return env


# ─────────────────────────────────────────────────────────────────────────────
# ① the kb source fetches content by ``kb_document_id`` (real KB, public surface)
# ─────────────────────────────────────────────────────────────────────────────


def test_kb_source_returns_a_hit_fetched_by_document_reference(kb: _KbEnv) -> None:
    reference = kb.reference()
    hits = kb.source().gather(KB_QUERY, [reference])

    assert len(hits) == 1
    hit = hits[0]
    assert hit.source_id == f"kb:{kb.kb_id}:{kb.document_id}"
    assert hit.layer == KB_LAYER == "kb"
    assert hit.source_layer == KB_SOURCE_LAYER == "project"
    assert "KBBRIDGE" in hit.text, "the body must come back through the KB's own parser"


def test_kb_reference_is_built_from_the_kb_document_id_column(kb: _KbEnv) -> None:
    """The FK column is the bridge: ``kb_document_id`` in, reference out."""
    row = {
        "artifact_id": "art-1",
        "project_id": PROJECT_ID,
        "name": "notes.md",
        "kb_document_id": kb.document_id,
        "created_at": 1_700_000_000,
    }
    reference = KbReference.from_artifact_row(row, kb_id=kb.kb_id)

    assert reference is not None
    assert (reference.kb_id, reference.document_id) == (kb.kb_id, kb.document_id)
    assert reference.project_id == PROJECT_ID
    assert reference.artifact_id == "art-1"
    assert reference.created_at == datetime.fromtimestamp(1_700_000_000, UTC)
    assert reference.source_id == f"kb:{kb.kb_id}:{kb.document_id}"


def test_artifact_without_a_kb_document_id_is_not_a_reference(kb: _KbEnv) -> None:
    """An artifact never archived into the KB has nothing to recall."""
    for row in ({"kb_document_id": None}, {"kb_document_id": ""}, {}):
        assert KbReference.from_artifact_row(row, kb_id=kb.kb_id) is None


def test_kb_source_skips_documents_that_do_not_match_the_query(kb: _KbEnv) -> None:
    assert kb.source().gather("完全无关的词", [kb.reference()]) == []


def test_kb_source_returns_a_bounded_snippet_not_the_whole_body(kb: _KbEnv) -> None:
    long_text = "KBBRIDGE " + ("对账口径以实测时刻为准。" * 200)
    document_id = kb.add_document(long_text, name="long")
    hits = kb.source(snippet_chars=120).gather(KB_QUERY, [kb.reference(document_id)])

    assert len(hits) == 1
    assert "KBBRIDGE" in hits[0].text
    assert len(hits[0].text) <= 120 + 2, "the snippet (with its ellipses) must stay bounded"


def test_kb_source_is_advisory_when_the_reader_fails() -> None:
    """Missing rows *and* parser explosions both mean "zero hits", never "raise"."""

    class _Broken:
        def read_document(self, *, kb_id: str, document_id: str) -> KbDocument | None:
            raise LookupError("knowledge document not found")

    class _Unparsable:
        def read_document(self, *, kb_id: str, document_id: str) -> KbDocument | None:
            raise RuntimeError("knowledge OCR is not enabled")

    reference = KbReference(kb_id="KB1", document_id="doc-1", project_id=PROJECT_ID)
    assert KbRecallSource(_Broken()).gather(KB_QUERY, [reference]) == []
    assert KbRecallSource(_Unparsable()).gather(KB_QUERY, [reference]) == []
    assert KbRecallSource(_Broken()).gather(KB_QUERY, []) == []


def test_reader_uses_only_the_public_preview_method() -> None:
    calls: list[tuple[str, str]] = []

    class _Service:
        def preview_document(
            self, kb_id: str, doc_id: str, *, actor_user_id: int, is_admin: bool = False
        ) -> dict[str, str]:
            calls.append((kb_id, doc_id))
            return {"id": doc_id, "filename": "notes.md", "text": "hello"}

    reader = KnowledgeServiceReader(_Service(), actor_user_id=7)
    document = reader.read_document(kb_id="KB1", document_id="doc-1")

    assert calls == [("KB1", "doc-1")]
    assert document == KbDocument(
        kb_id="KB1", document_id="doc-1", filename="notes.md", text="hello"
    )
    assert reader.read_document(kb_id="KB2", document_id="doc-2") is not None


def test_reader_swallows_kb_lookup_failures() -> None:
    class _Missing:
        def preview_document(
            self, kb_id: str, doc_id: str, *, actor_user_id: int, is_admin: bool = False
        ) -> dict[str, str]:
            raise LookupError("knowledge document not found")

    reader = KnowledgeServiceReader(_Missing(), actor_user_id=7)
    assert reader.read_document(kb_id="KB1", document_id="doc-1") is None


# ─────────────────────────────────────────────────────────────────────────────
# ② the memory side stores references, never document bodies
# ─────────────────────────────────────────────────────────────────────────────


def test_kb_reference_carries_ids_only_and_no_document_body() -> None:
    """What may sit next to a memory: ids + metadata. Body fields are a hard no."""
    names = {field.name for field in dataclasses.fields(KbReference)}

    assert names == {"kb_id", "document_id", "project_id", "artifact_id", "name", "created_at"}
    assert not [name for name in names if "text" in name or "body" in name or "content" in name]


def test_kb_source_module_has_no_memory_write_path() -> None:
    """Static assertion: nothing here can write into a memory store."""
    source = _KB_SOURCE_PATH.read_text(encoding="utf-8")

    for forbidden in (
        "add_atom",
        "add_raw",
        "add_entity",
        "add_candidate",
        "replace_atom",
        "supersede_atom",
        "append_journal",
        "upsert_digest",
        "octop_memory.core",
        "Memory(",
    ):
        assert forbidden not in source, (
            f"kb_source must not reach the memory write surface: {forbidden}"
        )


def test_gather_only_reads_and_returns_bounded_text(kb: _KbEnv) -> None:
    """Behavioural half of ②: one read call, and the caller never sees the body."""
    reads: list[str] = []

    class _SpyReader:
        def read_document(self, *, kb_id: str, document_id: str) -> KbDocument | None:
            reads.append(document_id)
            return KbDocument(
                kb_id=kb_id, document_id=document_id, filename="notes.md", text=KB_TEXT * 50
            )

    source = KbRecallSource(_SpyReader(), snippet_chars=64)
    hits = source.gather(KB_QUERY, [KbReference(kb_id="KB1", document_id="doc-1")])

    assert reads == ["doc-1"], "the KB is read once per reference and written nowhere"
    assert len(hits) == 1
    assert len(hits[0].text) <= 66 < len(KB_TEXT * 50)


# ─────────────────────────────────────────────────────────────────────────────
# ③ kb hits enter the merge layer: same dedup rule, same ordering rule
# ─────────────────────────────────────────────────────────────────────────────


def _hit(
    source_id: str,
    text: str,
    *,
    layer: str,
    source_layer: str,
    importance: str,
    occurred_at: datetime | None = None,
) -> RecallHit:
    return RecallHit(
        source_id=source_id,
        text=text,
        source_layer=source_layer,  # type: ignore[arg-type]
        layer=layer,
        occurred_at=occurred_at or _now(),
        importance=importance,  # type: ignore[arg-type]
        confidence="medium",
    )


def test_merge_drops_a_kb_snippet_that_repeats_a_memory_hit() -> None:
    """The memory layers are merged first, so the memory keeps the fact, once."""
    atom = _hit("atom-1", KB_TEXT, layer="atom", source_layer="project", importance="high")
    kb_duplicate = _hit(
        "kb:KB1:doc-1", KB_TEXT, layer="kb", source_layer="project", importance="medium"
    )
    kb_new = _hit(
        "kb:KB1:doc-2", "另一份文档的内容", layer="kb", source_layer="project", importance="medium"
    )

    merged = merge_recall_hits([atom], [kb_duplicate, kb_new])

    assert [hit.source_id for hit in merged] == ["atom-1", "kb:KB1:doc-2"], "duplicate shown once"
    assert kb_duplicate not in merged


def test_merge_orders_by_the_shared_rank_key_not_by_source() -> None:
    """Importance first, then freshness, then layer — the memory layers' own rule."""
    now = _now()
    high_old = _hit(
        "atom-high",
        "高优先",
        layer="atom",
        source_layer="agent",
        importance="high",
        occurred_at=now - timedelta(days=30),
    )
    kb_medium = _hit(
        "kb:KB1:doc-1", "文档中优先", layer="kb", source_layer="project", importance="medium"
    )
    low_fresh = _hit(
        "atom-low", "低优先", layer="raw", source_layer="project", importance="low", occurred_at=now
    )

    merged = merge_recall_hits([low_fresh, high_old], [kb_medium])

    assert [hit.source_id for hit in merged] == ["atom-high", "kb:KB1:doc-1", "atom-low"]


def test_merge_prefers_the_higher_layer_on_a_tie() -> None:
    now = _now()
    agent_hit = _hit(
        "atom-agent",
        "同一时刻同权重",
        layer="atom",
        source_layer="agent",
        importance="medium",
        occurred_at=now,
    )
    kb_hit = _hit(
        "kb:KB1:doc-1",
        "另一条同样权重",
        layer="kb",
        source_layer="project",
        importance="medium",
        occurred_at=now,
    )

    merged = merge_recall_hits([agent_hit], [kb_hit])

    assert [hit.source_layer for hit in merged] == ["project", "agent"], "project > team > agent"


def _memory_scope(db_path: Path, workspace: Path) -> MemoryScope:
    return MemoryScope(
        agent_id=AGENT_ID,
        cfg={"memory": {"backend": {"type": "sqlite", "db_path": str(db_path)}}},
        octop_config=OctopConfig(),
        workspace_dir=workspace,
        team_agent_id=None,
    )


def _seed_project_atom(
    db_path: Path,
    workspace: Path,
    assertion: str,
    *,
    search_terms: tuple[str, ...] = ("kbbridge",),
) -> None:
    """Write one atom into the project namespace the bridge recalls from."""
    from octop_memory.core import Memory
    from octop_memory.types import AtomCard

    memory = Memory(
        namespace="project_P1", backend="sqlite", backend_config={"db_path": str(db_path)}
    )
    now = _now()
    memory.add_atom(
        AtomCard(
            id="atom-kb-bridge",
            entity_id="ent-1",
            candidate_id="cand-1",
            raw_event_ids=[],
            assertion=assertion,
            verbatim_quote=assertion,
            quote_event_id="",
            search_terms=list(search_terms),
            occurred_at=now,
            confidence="high",
            importance="high",
            created_at=now,
        )
    )


def test_bridge_merges_real_memory_layers_with_the_real_kb(kb: _KbEnv, tmp_path: Path) -> None:
    """End to end: a real atom + a real KB document ⇒ one hit, memory wins."""
    db_path = tmp_path / "memory.sqlite"
    _seed_project_atom(db_path, tmp_path, KB_TEXT)
    recall = MultiNsRecall(_memory_scope(db_path, tmp_path))

    bridge = KbRecallBridge(recall, kb.source())
    hits = bridge.recall(KB_QUERY, project_id=PROJECT_ID, references=[kb.reference()])

    # Positive control: the memory layer did return the fact.
    assert [hit.source_id for hit in hits] == ["atom-kb-bridge"]
    assert hits[0].layer == "atom"
    assert all(hit.layer != KB_LAYER for hit in hits), "the duplicate document hit is dropped"


def test_bridge_adds_a_kb_hit_the_memory_layers_do_not_have(kb: _KbEnv, tmp_path: Path) -> None:
    db_path = tmp_path / "memory.sqlite"
    _seed_project_atom(db_path, tmp_path, "只有记忆里才有的一条事实", search_terms=("unrelated",))
    recall = MultiNsRecall(_memory_scope(db_path, tmp_path))

    bridge = KbRecallBridge(recall, kb.source())
    hits = bridge.recall(KB_QUERY, project_id=PROJECT_ID, references=[kb.reference()])

    assert [hit.layer for hit in hits] == [KB_LAYER], "memory has nothing matching the query"
    assert hits[0].source_layer == "project"
    assert hits[0].source_id == f"kb:{kb.kb_id}:{kb.document_id}"


def test_bridge_ignores_references_without_project_context(tmp_path: Path) -> None:
    """No project context ⇒ no references resolved, nothing guessed."""
    calls: list[str] = []

    class _SpyKb:
        def gather(self, query: str, references: Any, *, limit: int = 10) -> list[RecallHit]:
            calls.append(query)
            return []

    recall = MultiNsRecall(_memory_scope(tmp_path / "memory.sqlite", tmp_path))
    bridge = KbRecallBridge(recall, _SpyKb())  # type: ignore[arg-type]
    reference = KbReference(kb_id="KB1", document_id="doc-1", project_id=PROJECT_ID)

    assert bridge.recall(KB_QUERY, references=[reference]) == []
    assert calls == [], "the kb source must not run without a project"
