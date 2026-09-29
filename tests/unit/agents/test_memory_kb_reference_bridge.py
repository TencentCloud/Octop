"""T-43 —— 记忆↔文档桥的**写入端到端**：绑定前取不回 ↔ 绑定后取得回（**同一用例**）。

`project_artifacts.kb_document_id` 此前只有读取位：T-39 的 `kb` source 会按引用取正文，
但没人把引用写进去 ⇒ 读回来永远是空。本文件跑**真控制面 + 真 KB + 真归档链 + 真 kb source**。

★ 正对照与断言**同处一个用例**（本 run 铁律）：先用**确实存在**的 KB 文档证明"没绑引用就取不回"
（排除"fixture 压根没有文档"的假通过），再绑引用证明"取得回"。两半共用同一个 KB、同一行工件。
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from octop.infra.agents.memory.kb_source import (
    KbRecallSource,
    KbReference,
    KnowledgeServiceReader,
)
from octop.infra.agents.teams import learnings as L
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.knowledge import KnowledgeRepo
from octop.infra.db.repos.project_artifacts import ProjectArtifactRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.knowledge.service import KnowledgeService
from octop.infra.utils.paths import PathLayout

pytest.importorskip("octop_memory.core")

QUERY = "KBBRIDGE 口径"
BODY = "KBBRIDGE 口径：对账以 RUN.log.md 的实测时刻为准，不用 [now]。"
ARTIFACT_ID = "art-1"


class _Env:
    def __init__(self, **kwargs: object) -> None:
        self.__dict__.update(kwargs)


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Env:
    """真控制面（SQLite + 迁移）＋真 KB（真文件、公共 KnowledgeService）＋一行 workflow 工件。"""
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
        "octop.infra.knowledge.service.assert_knowledge_usable", lambda *_a, **_k: None
    )
    service = KnowledgeService(services)
    base = service.create_base(owner_user_id=owner_id, name="Docs")

    from octop.infra.db.repos.projects import ProjectRepo

    project_id = str(ProjectRepo(db).create(owner_user_id=owner_id, name="Alpha").id)
    repo = ProjectArtifactRepo(db)
    artifact = repo.insert(
        artifact_id=ARTIFACT_ID,
        project_id=project_id,
        task_id=None,
        name="LEARNINGS.md",
        uri="team/R1/LEARNINGS.md",
        size=0,
        mime="text/markdown",
        file_hash="",
        created_by="code",
        kind="workflow",
    )
    documents = L.KnowledgeServiceDocuments(service, actor_user_id=owner_id)
    archiver = L.ProjectKbArchiver(
        documents=documents, artifacts=repo, kb_id=base.id, artifact_id=ARTIFACT_ID
    )
    return _Env(
        db=db,
        service=service,
        owner_id=owner_id,
        project_id=project_id,
        kb_id=base.id,
        repo=repo,
        artifact=artifact,
        documents=documents,
        archiver=archiver,
        source=KbRecallSource(KnowledgeServiceReader(service, actor_user_id=owner_id)),
    )


def _reference_from_row(env: _Env) -> KbReference | None:
    row = env.repo.get(ARTIFACT_ID)
    assert row is not None
    return KbReference.from_artifact_row(row, kb_id=env.kb_id)


def test_kb_reference_is_recallable_only_after_the_id_is_bound(env: _Env) -> None:
    """★ 正对照同用例：未绑定 ⇒ 0 命中（而文档**确实存在**）；绑定后 ⇒ 取回正文。"""
    # ── 正对照的准备：KB 里**真的**有一份内容相同的文档（下面直接读得到）──
    control_id = env.documents.create_text_document(kb_id=env.kb_id, name="control.md", text=BODY)
    preview = env.service.preview_document(env.kb_id, control_id, actor_user_id=env.owner_id)
    assert "KBBRIDGE" in preview["text"], "文档确实存在 —— 所以下面的 0 命中只能是'没绑引用'"

    # ── ① 未绑定：工件行没有引用 ⇒ kb source 一个引用都构造不出 ⇒ 0 命中 ──
    assert env.repo.get(ARTIFACT_ID).kb_document_id is None
    assert _reference_from_row(env) is None
    assert env.source.gather(QUERY, []) == []

    # ── ② 归档链：建文档 + 绑引用（唯一写者）⇒ kb source 取回同一份内容 ──
    digest = L.learning_digest(BODY)
    bound_id = env.archiver.write_document(project_id=env.project_id, text=BODY, digest=digest)
    assert bound_id is not None and bound_id != control_id

    row = env.repo.get(ARTIFACT_ID)
    assert row is not None and row.kb_document_id is not None, "① 该列必须非 NULL"

    reference = _reference_from_row(env)
    assert reference is not None
    assert reference.document_id == row.kb_document_id
    hits = env.source.gather(QUERY, [reference])
    assert [hit.text for hit in hits] == [BODY]
    assert hits[0].source_id == f"kb:{env.kb_id}:{row.kb_document_id}"


def test_archiving_binds_the_reference_and_reports_the_digest(env: _Env) -> None:
    digest = L.learning_digest(BODY)

    assert env.archiver.existing_digests(project_id=env.project_id) == ()
    document_id = env.archiver.write_document(project_id=env.project_id, text=BODY, digest=digest)

    assert document_id is not None
    row = env.repo.get(ARTIFACT_ID)
    assert row is not None and row.kb_document_id == document_id
    assert env.archiver.existing_digests(project_id=env.project_id) == (digest,)


def test_rerunning_the_same_distillation_does_not_archive_a_second_document(
    env: _Env, tmp_path: Path
) -> None:
    """去重口径②在**真 KB**上生效：同一份蒸馏重跑 ⇒ 不再建第二份文档。"""
    workspace = tmp_path / "ws"
    candidates = [
        L.LearningCandidate("KBBRIDGE 口径：对账以 RUN.log.md 的实测时刻为准，不用 [now]。")
    ]

    from datetime import date

    first = L.distill_and_append(
        host_workspace=workspace,
        project_id=env.project_id,
        run_id="R1",
        candidates=candidates,
        on_date=date(2026, 9, 29),
        kb_archiver=env.archiver,
    )
    # 换一天再蒸馏同一份内容：当日块不同 ⇒ 文本级去重**不**命中（口径①只管当日块），
    # 于是真正走到 KB 那一层 ⇒ 由口径②（摘要）拦住，不再建第二份文档。
    second = L.distill_and_append(
        host_workspace=workspace,
        project_id=env.project_id,
        run_id="R1",
        candidates=candidates,
        on_date=date(2026, 9, 30),
        kb_archiver=env.archiver,
    )

    assert first.kb_document_id is not None
    assert "kb:duplicate" in second.degraded, "第二遍应命中既有文档摘要"
    assert second.kb_document_id is None
    documents = env.service.list_documents(env.kb_id, actor_user_id=env.owner_id)
    assert len([row for row in documents if not row.is_dir]) == 1, "KB 里只该有一份"


def test_memory_side_keeps_only_the_reference_never_the_body(env: _Env) -> None:
    """③ T-39 铁律不回退：工件行与记忆引用里都**没有**正文，只有 id。

    ``kb`` 命中里的 ``text`` 是**召回时**从 KB 现取的有界片段（T-39 已证），
    这里证的是**落库/落引用**那一侧不含正文。
    """
    env.archiver.write_document(
        project_id=env.project_id, text=BODY, digest=L.learning_digest(BODY)
    )

    row = env.repo.get(ARTIFACT_ID)
    assert row is not None
    stored = json.dumps(dataclasses.asdict(row), ensure_ascii=False, default=str)
    assert BODY not in stored, "工件行的任何列都不得存正文（只存引用）"
    assert "KBBRIDGE" not in stored

    names = {field.name for field in dataclasses.fields(KbReference)}
    assert not [name for name in names if "text" in name or "body" in name or "content" in name]


def test_binding_is_idempotent_through_the_archive_chain(env: _Env) -> None:
    digest = L.learning_digest(BODY)
    document_id = env.archiver.write_document(project_id=env.project_id, text=BODY, digest=digest)

    assert env.repo.set_kb_document_id(ARTIFACT_ID, str(document_id)) is False, "同值 ⇒ 无写入"
