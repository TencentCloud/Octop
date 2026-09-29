"""``project_artifacts`` repo —— 025 的 ``owner_role``/``phase`` 与既有的 ``version`` 列。

覆盖本卡的三个要求：

1. **可读可写**：三列真 DB 往返（含 NULL / 既有行的容错）；
2. **``version`` ≠ ``revision``**：把"两件事"钉成断言（类型空间不相交 ⇒ 不可能被互相赋值）；
3. **不另定一套语义**：``owner_role``/``phase`` 逐字存储、**不校验不归一**，
   且本模块**不得** import ``teams`` 域（`AGENTS.md §5` 硬禁令）。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.project_artifacts import (
    ATTACHMENT_KIND,
    ArtifactRow,
    ProjectArtifactRepo,
)
from octop.infra.db.repos.projects import ProjectRepo
from octop.infra.db.repos.users import UserRepo


@pytest.fixture
def db(tmp_path: Path) -> SqlitePool:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    return pool


@pytest.fixture
def project_id(db: SqlitePool) -> str:
    owner = UserRepo(db).create(username="owner", password_hash="h", role="user")
    return str(ProjectRepo(db).create(owner_user_id=owner, name="Alpha").id)


def _insert(
    db: SqlitePool,
    project_id: str,
    *,
    artifact_id: str = "ART1",
    kind: str = ATTACHMENT_KIND,
    task_id: str | None = None,
    **extra: object,
) -> ArtifactRow:
    return ProjectArtifactRepo(db).insert(
        artifact_id=artifact_id,
        project_id=project_id,
        task_id=task_id,
        name="SPEC.md",
        uri="team/2026-09-28-145847/SPEC.md",
        size=10,
        mime="text/markdown",
        file_hash="deadbeef",
        created_by="pm",
        kind=kind,
        **extra,  # type: ignore[arg-type]
    )


# ── ① 三列可读可写 ───────────────────────────────────────────────────────────


def test_insert_round_trips_owner_role_and_phase(db: SqlitePool, project_id: str) -> None:
    row = _insert(
        db, project_id, kind="workflow", owner_role="architect", phase="方案确认", version=7
    )
    assert row.owner_role == "architect"
    assert row.phase == "方案确认"
    assert row.version == 7

    again = ProjectArtifactRepo(db).get("ART1")
    assert again is not None
    assert (again.owner_role, again.phase, again.version) == ("architect", "方案确认", 7)


def test_attachment_path_is_unchanged_by_default(db: SqlitePool, project_id: str) -> None:
    """附件行不给新参数 ⇒ ``owner_role``/``phase`` 为 NULL、``version`` = 列默认 1。

    这条同时是**回归护栏**：唯一的既有 :meth:`insert` 调用者
    （`src/octop/infra/projects/attachments.py`）不传新参数，行为必须逐字不变。
    """
    row = _insert(db, project_id)
    assert row.kind == ATTACHMENT_KIND
    assert row.owner_role is None
    assert row.phase is None
    assert row.version == 1


def test_rows_written_before_025_read_back_as_none(db: SqlitePool, project_id: str) -> None:
    """**既有行的容错**：025 之前的行这两列是 NULL，读出来必须是 ``None``。

    用裸 SQL 插一行（不写这两列）来模拟历史行 —— 走 :meth:`insert` 反而模拟不到，
    因为 ``insert`` 总会显式写它们（``None`` 也是写）。
    """
    from octop.infra.db.repos._base import now_ts

    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO project_artifacts("
            "artifact_id, project_id, task_id, kind, name, uri, hash, size, mime,"
            " created_by, created_at"
            ") VALUES (?, ?, NULL, ?, ?, ?, ?, 0, '', ?, ?)",
            ("LEGACY1", project_id, ATTACHMENT_KIND, "old.txt", "old.txt", "h", "u", now_ts()),
        )

    row = ProjectArtifactRepo(db).get("LEGACY1")
    assert row is not None
    assert row.owner_role is None, "NULL 不得被 str() 成 'None'"
    assert row.phase is None, "NULL 不得被 str() 成 'None'"
    assert row.version == 1, "019 的 NOT NULL DEFAULT 1 必须仍然成立"


def test_list_readers_carry_the_new_columns(db: SqlitePool, project_id: str) -> None:
    """列必须能被**既有读取路径**取到 —— 否则只是把写入位换成"另一半的仅有写入位"。"""
    repo = ProjectArtifactRepo(db)
    _insert(db, project_id, task_id="T1", owner_role="qa", phase="test")
    rows = repo.list_by_task(project_id=project_id, task_id="T1")
    assert len(rows) == 1
    assert (rows[0].owner_role, rows[0].phase) == ("qa", "test")


# ── ② version 与 revision 是两件事 ──────────────────────────────────────────


def test_version_is_an_int_row_counter_not_the_content_hash(
    db: SqlitePool, project_id: str
) -> None:
    """**本卡要求②的断言形态。**

    ``version`` = 元数据行的版本号（``INTEGER``）；``revision`` = 工件正文的 sha256 前 16 位
    （``str``）。两者**类型空间不相交** ⇒ 结构上不可能被互相赋值；若将来有人把
    ``version`` 换成 ``revision``（或反之），本用例会红。
    """
    from octop.infra.agents.teams.run_service import revision_of

    row = _insert(db, project_id, kind="workflow", version=3)
    assert isinstance(row.version, int)
    assert not isinstance(row.version, str)

    revision = revision_of("hello")
    assert isinstance(revision, str)
    assert re.fullmatch(r"[0-9a-f]{16}", revision), revision
    assert revision != str(row.version)


def test_repo_module_does_not_import_the_teams_domain() -> None:
    """`AGENTS.md §5` 硬禁令：``infra/db/repos/`` 不得 import 非 DB 的 ``infra`` 包。

    ⇒ ``owner_role``/``phase`` 的**派生与校验只能在写入方**，本层只存字符串。
    任何人若想在这里 import ``teams.artifacts`` 来"顺手校验一下归属"，本用例变红 ——
    同时模块 docstring 也写明了这条。

    用 **AST** 查真实 import 语句（不去源码里找 ``teams`` 这个词：docstring 里就写着
    ``teams/artifacts.py``，字面匹配会假红）。
    """
    from octop.infra.db.repos import project_artifacts as mod

    tree = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.append(node.module)

    assert modules, "AST 没解析出 import —— 检查本身失效了（假绿灯）"
    offenders = [m for m in modules if "agents" in m or m.startswith("octop.infra.projects")]
    assert offenders == [], f"repo 层不得依赖域层：{offenders}"


# ── ③ 不另定一套语义：逐字存储 ──────────────────────────────────────────────


@pytest.mark.parametrize(
    ("owner_role", "phase"),
    [
        ("reviewer-R1", "spec-review"),  # 带成员后缀：本层**不得**归一（归一在 artifacts.py）
        ("dba", "design"),
        (None, None),
    ],
)
def test_owner_role_and_phase_are_stored_verbatim(
    db: SqlitePool, project_id: str, owner_role: str | None, phase: str | None
) -> None:
    """逐字往返：本层不归一、不校验、不反推（语义权威在 ``teams/artifacts.py``）。"""
    row = _insert(db, project_id, kind="workflow", owner_role=owner_role, phase=phase)
    assert row.owner_role == owner_role
    assert row.phase == phase


def test_from_row_is_the_only_mapping_point() -> None:
    """``ArtifactRow`` 暴露的列集合必须包含本卡的三列 —— 防止有人只改 SQL 不改映射。"""
    fields = set(ArtifactRow.__dataclass_fields__)
    assert {"owner_role", "phase", "version"} <= fields
