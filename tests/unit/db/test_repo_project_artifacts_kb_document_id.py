"""T-43 —— ``project_artifacts.kb_document_id`` 的**写入方**（repo 侧）。

本卡收口的是「**仅有读取位**」的字段：列在 `019_projects.sql` 就有，T-39 的 `kb` source 也
已经在读它，但**没人写**（INSERT 恒 NULL，`ArtifactRow` 都没映射）⇒ 读回来永远是空。

这里测 repo 侧的三件事：① 行**暴露**该列（NULL 与有值都读得出）；② 写入方**幂等**且只动这一列；
③ **只有一个写点**（结构化断言，防第二条写入路径"顺手"长出来）。
端到端的正对照（写入后取得回 ↔ 未写入取不回，同用例）见
``tests/unit/agents/test_memory_kb_reference_bridge.py``。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.project_artifacts import ArtifactRow, ProjectArtifactRepo
from octop.infra.db.repos.projects import ProjectRepo
from octop.infra.db.repos.users import UserRepo

_SRC = Path(__file__).resolve().parents[3] / "src" / "octop"
_REPO_SOURCE = _SRC / "infra" / "db" / "repos" / "project_artifacts.py"
_LEARNINGS_SOURCE = _SRC / "infra" / "agents" / "teams" / "learnings.py"


@pytest.fixture
def db(tmp_path: Path) -> SqlitePool:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    return pool


@pytest.fixture
def project_id(db: SqlitePool) -> str:
    owner = UserRepo(db).create(username="owner", password_hash="h", role="user")
    return str(ProjectRepo(db).create(owner_user_id=owner, name="Alpha").id)


@pytest.fixture
def repo(db: SqlitePool, project_id: str) -> ProjectArtifactRepo:
    return ProjectArtifactRepo(db)


def _insert(
    repo: ProjectArtifactRepo, project_id: str, *, artifact_id: str = "art-1"
) -> ArtifactRow:
    return repo.insert(
        artifact_id=artifact_id,
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


def test_row_exposes_kb_document_id_as_null_before_archiving(
    repo: ProjectArtifactRepo, project_id: str
) -> None:
    row = _insert(repo, project_id)

    assert row.kb_document_id is None, "未归档的行必须是 NULL（不是 'None' 字符串）"
    assert repo.get(row.artifact_id).kb_document_id is None  # type: ignore[union-attr]


def test_set_binds_the_document_and_is_readable_back(
    repo: ProjectArtifactRepo, project_id: str
) -> None:
    row = _insert(repo, project_id)

    assert repo.set_kb_document_id(row.artifact_id, "kb-doc-1") is True

    stored = repo.get(row.artifact_id)
    assert stored is not None
    assert stored.kb_document_id == "kb-doc-1"


def test_set_is_idempotent_and_touches_only_that_column(
    repo: ProjectArtifactRepo, project_id: str
) -> None:
    row = _insert(repo, project_id)
    repo.set_kb_document_id(row.artifact_id, "kb-doc-1")
    before = repo.get(row.artifact_id)

    assert repo.set_kb_document_id(row.artifact_id, "kb-doc-1") is False, "同值 ⇒ 不产生写入"

    after = repo.get(row.artifact_id)
    assert after == before, "幂等：除了该列以外一个字段都不许变"


def test_rebinding_to_another_document_is_allowed(
    repo: ProjectArtifactRepo, project_id: str
) -> None:
    row = _insert(repo, project_id)
    repo.set_kb_document_id(row.artifact_id, "kb-doc-1")

    assert repo.set_kb_document_id(row.artifact_id, "kb-doc-2") is True
    stored = repo.get(row.artifact_id)
    assert stored is not None and stored.kb_document_id == "kb-doc-2"


def test_set_on_a_missing_row_reports_no_write(repo: ProjectArtifactRepo) -> None:
    assert repo.set_kb_document_id("nope", "kb-doc-1") is False


def test_other_columns_survive_the_bind(repo: ProjectArtifactRepo, project_id: str) -> None:
    """绑引用不得顺手动 ``task_id``/``comment_id``/``version`` 等既有语义列。"""
    row = _insert(repo, project_id)

    repo.set_kb_document_id(row.artifact_id, "kb-doc-1")

    stored = repo.get(row.artifact_id)
    assert stored is not None
    for field in ("pk", "project_id", "task_id", "kind", "name", "uri", "version", "comment_id"):
        assert getattr(stored, field) == getattr(row, field), field


def test_kb_document_id_has_exactly_one_write_site() -> None:
    """④ 唯一写者：写点只有一处，且域侧不得自己写 SQL。"""
    repo_source = _REPO_SOURCE.read_text(encoding="utf-8")
    learnings_source = _LEARNINGS_SOURCE.read_text(encoding="utf-8")

    assignments = re.findall(r"kb_document_id\s*=\s*\?", repo_source)
    assert assignments == ["kb_document_id = ?"], "只允许 set_kb_document_id 里那一条 UPDATE 赋值"

    tree = ast.parse(repo_source)
    methods = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and "kb_document_id" in node.name
    }
    assert methods == {"set_kb_document_id"}, f"写者只许一个，实得 {methods}"

    assert "set_kb_document_id" in learnings_source, "归档链必须走那个唯一写者"
    assert "UPDATE project_artifacts" not in learnings_source, "域侧不许自己写 SQL"
    assert "INSERT INTO project_artifacts" not in learnings_source, "也不许自己建行"

    writers = sorted(
        path.relative_to(_SRC).as_posix()
        for path in _SRC.rglob("*.py")
        if "kb_document_id = ?" in path.read_text(encoding="utf-8")
    )
    assert writers == ["infra/db/repos/project_artifacts.py"], f"跨文件也只许一处，实得 {writers}"
