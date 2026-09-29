"""``project_artifacts`` rows — the single writer for project file metadata.

The table predates this feature (migration 019); migration 020 added ``size`` and
``mime``. Project attachments reuse it with ``kind='attachment'``: ``task_id``
NULL means *pending* (uploaded from the create-task dialog before the task
exists), a non-NULL ``task_id`` means bound. No new table, no status column.

── 列的血缘（**别把它当成"025 加了三列"**）────────────────────────────────────

* ``owner_role`` / ``phase`` —— 由 **025** 加（`025_team_runs.sql @103-104`、`.pg.sql @100-101`）。
* ``version`` —— **019 既有**（`019_projects.sql @149` ：``version INTEGER NOT NULL DEFAULT 1``）。
  本模块此前只把它硬编码成 ``1``、且不往 :class:`ArtifactRow` 上映射 ⇒ 它一直是**仅有写入位**
  （一个恒为 1、无人读的常量）。本次把它**读出来**并允许调用方写值。

── ``owner_role`` / ``phase`` 的语义（**索引，不是第二套定义**）──────────────

* ``owner_role`` = 该工件的**归属角色**，真源是 `PLAN.md · 项目工件加列` 的第 360 行
  「归属角色（由 ``ARTIFACT_OWNERS`` 落库，**仅作索引**）」；语义权威 =
  `src/octop/infra/agents/teams/artifacts.py · ARTIFACT_OWNERS`（``()`` = 运行时专属、
  未列入 = 不限制、多负责人 = 多个角色 —— **那些判定一概不在这里做**）。
* ``phase`` = 「**该工件由哪个阶段产出**」（`PLAN.md` 同表第 361 行）；阶段词表权威 =
  `src/octop/infra/agents/teams/pipeline.py · PHASES`。
* ⚠️ **本层不得校验、不得归一、不得反推**这两个值：`AGENTS.md §5` 的硬禁令是
  「``infra/db/repos/`` → any non-DB ``infra`` package」⇒ 本模块**不能** import
  ``teams.artifacts`` / ``teams.pipeline``。因此这里**只存字符串**，派生与校验由
  写入方（run 工件的索引行写入者）负责。谁在这里另写一套归属/阶段判定，就是在制造
  「同一事实两份定义」。

── ``version`` **不是** ``revision``（两者都叫"版本"，但是两件事）─────────────

| | ``revision`` | ``version``（本列） |
|---|---|---|
| 平面 | **工作区文件正文**（``<run_root>/<runId>/<文件名>``） | **``project_artifacts`` 元数据行** |
| 取值 | ``sha256(content)[:16]`` | ``INTEGER NOT NULL DEFAULT 1`` |
| 用途 | 乐观并发 CAS：``PUT``/``GET …/artifacts/{name}`` 比对"我读到的是不是还是这份字节" | 行的版本号（019 既有列），出现在 ``GET …/artifacts`` 的清单里 |
| 权威 | `src/octop/infra/agents/teams/run_service.py · revision_of @136` | 本列本身 |
| 写者 | 服务层写文件时算（不落库） | 本 :meth:`ProjectArtifactRepo.insert`（默认 ``1``） |

`run_service.py · revision_of @136-143` 的 docstring 逐字说明了为什么**故意**用内容哈希而不是
计数列：「a content hash makes "same revision" mean "same bytes" **without a second counter
column that could drift from the file**」。
⇒ **结论：``revision`` 是文件正文的 CAS 令牌，``version`` 是元数据行的版本号；
两者不是同一件事，也不得互相赋值。** 接口面同理：`GET …/artifacts` 用 ``version``，
`GET|PUT …/artifacts/{name}` 用 ``revision``（`PLAN.md` API 面表）。

── 消费方（交付时点名，避免造出新的"仅有写入位"）────────────────────────────

* ``owner_role`` / ``version`` / ``phase`` —— **`GET /api/team/runs/{run_id}/artifacts`**
  （`PLAN.md` API 面：``{items:[{name, owner_role, version, hash, phase, created_at}]}``）。
* ⚠️ **值仍可能是 NULL / 1**：索引行的写入方是 :meth:`ProjectArtifactRepo.upsert_workflow`
  （``kind='workflow'``）；``owner_role`` / ``phase`` 由调用方派生后**逐字落库**（本层不推导、
  不归一），``version`` 计**行重写次数**（首写 1，之后每次 +1），**不是**正文的 ``revision``。
  读取侧已接：``GET /api/team/runs/{run_id}/artifacts`` 查这些列并如实回填，从未写过索引行的
  工件仍返回 ``null``（写侧 T-45 · 读侧 T-16，两侧都在代码里）。
* ``kb_document_id`` —— **两端都点名**：写者 = :meth:`ProjectArtifactRepo.set_kb_document_id`
  （调用方 `agents/teams/learnings.py · ProjectKbArchiver`）；读者 =
  `agents/memory/kb_source.py · KbReference.from_artifact_row` → `KbRecallSource`（T-39 的
  ``kb`` recall source）。⇒ 它**不再是**「仅有读取位」的字段；两个消费方都在代码里（T-43 收口）。
* 其余列（``comment_id`` / ``hash`` / ``size`` / ``mime`` / ``uri``）—— 附件面既有消费方
  （`infra/projects/attachments.py`、`api/routers/projects.py`）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import DbRow, map_rows, now_ts, sql_in_placeholders
from octop.infra.utils.ulid import new_short_id

ATTACHMENT_KIND = "attachment"

#: ``kind`` of a team-run workflow artifact. The **tuple** authority (which kinds a
#: workflow artifact may take) is ``teams/artifacts.py · WORKFLOW_ARTIFACT_KINDS``;
#: this constant is the spelling this layer needs and a unit test binds the two.
WORKFLOW_KIND = "workflow"


@dataclass(frozen=True)
class ArtifactRow:
    pk: int
    artifact_id: str
    project_id: str
    task_id: str | None
    kind: str
    name: str
    uri: str
    size: int
    mime: str
    hash: str
    created_by: str
    created_at: int
    comment_id: str | None
    #: 归属角色的**索引**（真源 `teams/artifacts.py · ARTIFACT_OWNERS`）；附件行恒为 ``None``。
    owner_role: str | None
    #: 产出阶段的**索引**（真源 `teams/pipeline.py · PHASES`）；附件行恒为 ``None``。
    phase: str | None
    #: 行的版本号（019 既有列）；**不是** `revision`（内容哈希 CAS），见模块 docstring。
    version: int
    #: 归档文档的**引用**（019 既有列；T-43 起可读可写）—— 指向该工件在项目 KB 里的文档。
    #: 唯一写者 = :meth:`ProjectArtifactRepo.set_kb_document_id`；读取方 =
    #: `agents/memory/kb_source.py · KbReference.from_artifact_row`。
    #: **记忆侧只存引用、不复制正文**（正文留在 KB）。
    kb_document_id: str | None = None

    @classmethod
    def from_row(cls, r: DbRow) -> ArtifactRow:
        return cls(
            pk=int(r["id"]),
            artifact_id=str(r["artifact_id"]),
            project_id=str(r["project_id"]),
            task_id=(str(r["task_id"]) if r["task_id"] is not None else None),
            kind=str(r["kind"]),
            name=str(r["name"]),
            uri=str(r["uri"]),
            size=int(r["size"]),
            mime=str(r["mime"]),
            hash=str(r["hash"]),
            created_by=str(r["created_by"]),
            created_at=int(r["created_at"]),
            comment_id=r["comment_id"],
            # 025 加的两列可空（既有行 = NULL）⇒ 必须按 None 传，不能 str(None) 成 "None"。
            owner_role=(str(r["owner_role"]) if r["owner_role"] is not None else None),
            phase=(str(r["phase"]) if r["phase"] is not None else None),
            version=int(r["version"]),
            # 019 既有列、可空；未归档的行 = NULL（**不是** "None" 字符串）。
            kb_document_id=(str(r["kb_document_id"]) if r["kb_document_id"] is not None else None),
        )


class ProjectArtifactRepo:
    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    def artifact_id_exists(self, artifact_id: str) -> bool:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM project_artifacts WHERE artifact_id = ?", (artifact_id,)
            ).fetchone()
        return row is not None

    def insert(
        self,
        *,
        artifact_id: str,
        project_id: str,
        task_id: str | None,
        name: str,
        uri: str,
        size: int,
        mime: str,
        file_hash: str,
        created_by: str,
        kind: str = ATTACHMENT_KIND,
        owner_role: str | None = None,
        phase: str | None = None,
        version: int = 1,
    ) -> ArtifactRow:
        """Insert one metadata row.

        ``owner_role`` / ``phase`` give the row its owning role and producing phase
        (025 columns). They are stored **verbatim** — this layer must not validate or
        derive them (see the module docstring: ``AGENTS.md §5`` forbids repos →
        domain imports, so the authority stays in ``teams/artifacts.py`` /
        ``teams/pipeline.py``). Attachments leave both ``None``.

        ``version`` is the row's version number (019 column), **not** the artifact
        body's ``revision`` (a content-hash CAS token — see the module docstring).
        """
        ts = now_ts()
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO project_artifacts("
                "artifact_id, project_id, task_id, thread_id, kind, name, uri, agent_id,"
                " kb_document_id, commit_ref, version, hash, size, mime, created_by, created_at,"
                " owner_role, phase"
                ") VALUES (?, ?, ?, NULL, ?, ?, ?, NULL, NULL, NULL, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    artifact_id,
                    project_id,
                    task_id,
                    kind,
                    name,
                    uri,
                    version,
                    file_hash,
                    size,
                    mime,
                    created_by,
                    ts,
                    owner_role,
                    phase,
                ),
            )
        row = self.get(artifact_id)
        if row is None:
            raise RuntimeError(f"artifact insert failed: {artifact_id}")
        return row

    def set_kb_document_id(self, artifact_id: str, kb_document_id: str) -> bool:
        """Bind the archived KB document to this artifact row — **the only writer**.

        Idempotent: re-binding the same value touches zero rows and reports ``False``;
        the ``WHERE`` clause also keeps the statement from rewriting unchanged rows.
        Re-binding to a *different* document is allowed (re-archive), and every other
        column is left alone.

        Like ``owner_role`` / ``phase``, the value is stored **verbatim** — this layer
        does not validate or interpret it (``AGENTS.md §5``: repos must not import the
        ``teams`` domain). The reader is
        :func:`octop.infra.agents.memory.kb_source.KbReference.from_artifact_row`, and
        memory stores the **reference only** — never the document body.

        :returns: ``True`` when a row was actually updated (missing row or same value
            ⇒ ``False``).
        """
        with self._db.transaction() as conn:
            cur = conn.execute(
                "UPDATE project_artifacts SET kb_document_id = ? "
                "WHERE artifact_id = ? AND (kb_document_id IS NULL OR kb_document_id <> ?)",
                (kb_document_id, artifact_id, kb_document_id),
            )
        return bool(cur.rowcount)

    def get(self, artifact_id: str) -> ArtifactRow | None:
        with self._db.connect() as conn:
            r = conn.execute(
                "SELECT * FROM project_artifacts WHERE artifact_id = ?", (artifact_id,)
            ).fetchone()
        return ArtifactRow.from_row(r) if r else None

    def list_by_task(self, *, project_id: str, task_id: str) -> list[ArtifactRow]:
        """Bound attachments of one task, oldest first (display order)."""
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM project_artifacts "
                "WHERE project_id = ? AND task_id = ? AND kind = ? "
                "ORDER BY created_at, id",
                (project_id, task_id, ATTACHMENT_KIND),
            ).fetchall()
        return map_rows(rows, ArtifactRow)

    def list_by_tasks(
        self, *, project_id: str, task_ids: list[str]
    ) -> dict[str, list[ArtifactRow]]:
        """Resolve attachments for many tasks at once — one ``IN`` query.

        The board renders every task in one pass; a query per task would be N+1.
        """
        if not task_ids:
            return {}
        placeholders = sql_in_placeholders(len(task_ids))
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM project_artifacts "
                f"WHERE project_id = ? AND kind = ? AND task_id IN ({placeholders}) "
                "ORDER BY created_at, id",
                [project_id, ATTACHMENT_KIND, *task_ids],
            ).fetchall()
        grouped: dict[str, list[ArtifactRow]] = {task_id: [] for task_id in task_ids}
        for row in map_rows(rows, ArtifactRow):
            grouped.setdefault(row.task_id or "", []).append(row)
        return grouped

    def list_pending(self, project_id: str) -> list[ArtifactRow]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM project_artifacts "
                "WHERE project_id = ? AND kind = ? AND task_id IS NULL "
                "ORDER BY created_at, id",
                (project_id, ATTACHMENT_KIND),
            ).fetchall()
        return map_rows(rows, ArtifactRow)

    def sum_size_for_task(self, task_id: str) -> int:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(size), 0) AS total FROM project_artifacts "
                "WHERE kind = ? AND task_id = ?",
                (ATTACHMENT_KIND, task_id),
            ).fetchone()
        return int(row["total"]) if row else 0

    def sum_pending_size(self, project_id: str) -> int:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(size), 0) AS total FROM project_artifacts "
                "WHERE kind = ? AND project_id = ? AND task_id IS NULL",
                (ATTACHMENT_KIND, project_id),
            ).fetchone()
        return int(row["total"]) if row else 0

    def bind(self, artifact_id: str, *, task_id: str) -> bool:
        """Bind a **pending** row; an already-bound row is left untouched."""
        with self._db.transaction() as conn:
            cur = conn.execute(
                "UPDATE project_artifacts SET task_id = ? WHERE artifact_id = ? AND task_id IS NULL",
                (task_id, artifact_id),
            )
        return bool(cur.rowcount)

    def unbind(self, artifact_id: str, *, task_id: str) -> bool:
        """Compensating unbind — idempotent, and never touches other tasks' rows."""
        with self._db.transaction() as conn:
            cur = conn.execute(
                "UPDATE project_artifacts SET task_id = NULL WHERE artifact_id = ? AND task_id = ?",
                (artifact_id, task_id),
            )
        return bool(cur.rowcount)

    def bind_comment(self, artifact_id: str, *, comment_id: str) -> bool:
        """Attach an artifact to the comment that introduced it (v23 column).

        Mirrors :meth:`bind` for ``task_id``: the file is inserted first (uploads
        do not know the comment yet) and bound afterwards.
        """
        with self._db.transaction() as conn:
            cur = conn.execute(
                "UPDATE project_artifacts SET comment_id = ? WHERE artifact_id = ?",
                (comment_id, artifact_id),
            )
        return bool(cur.rowcount > 0)

    def list_by_comment(self, *, project_id: str, comment_id: str) -> list[ArtifactRow]:
        """The files one comment owns, oldest first."""
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM project_artifacts WHERE project_id = ? AND comment_id = ? "
                "ORDER BY created_at, artifact_id",
                (project_id, comment_id),
            ).fetchall()
        return map_rows(rows, ArtifactRow)

    def delete_by_comment(self, comment_id: str, *, conn: Any = None) -> int:
        """Delete every artifact bound to a comment; returns how many rows went.

        Takes the caller's transaction (``conn``) because deleting a comment is one
        unit of work: comment row + its attachments + the audit row commit together
        or not at all (PLAN §4).
        """
        statement = "DELETE FROM project_artifacts WHERE comment_id = ?"
        if conn is not None:
            return int(conn.execute(statement, (comment_id,)).rowcount)
        with self._db.transaction() as own:
            return int(own.execute(statement, (comment_id,)).rowcount)

    def delete(self, artifact_id: str) -> bool:
        with self._db.transaction() as conn:
            cur = conn.execute(
                "DELETE FROM project_artifacts WHERE artifact_id = ?", (artifact_id,)
            )
        return bool(cur.rowcount)

    # ── workflow artifacts (kind='workflow') ─────────────────────────────────
    #
    # The name ``workflow`` and the ownership rules behind ``owner_role`` live in
    # ``teams/artifacts.py`` (this layer must not import it — AGENTS.md section 5);
    # a unit test binds the two spellings so they cannot drift apart.

    def get_workflow(self, *, project_id: str, name: str) -> ArtifactRow | None:
        """The ``kind='workflow'`` index row for one artifact name, or ``None``."""
        with self._db.connect() as conn:
            r = conn.execute(
                "SELECT * FROM project_artifacts "
                "WHERE project_id = ? AND kind = ? AND name = ? "
                "ORDER BY id DESC LIMIT 1",
                (project_id, WORKFLOW_KIND, name),
            ).fetchone()
        return ArtifactRow.from_row(r) if r is not None else None

    def list_workflow(self, *, project_id: str) -> list[ArtifactRow]:
        """Every workflow index row of one project, oldest first."""
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM project_artifacts WHERE project_id = ? AND kind = ? ORDER BY id ASC",
                (project_id, WORKFLOW_KIND),
            ).fetchall()
        return map_rows(rows, ArtifactRow)

    def upsert_workflow(
        self,
        *,
        project_id: str,
        name: str,
        uri: str,
        size: int,
        mime: str,
        file_hash: str,
        owner_role: str | None,
        phase: str | None,
        created_by: str = "runtime",
        artifact_id: str | None = None,
    ) -> ArtifactRow:
        """Insert or refresh the workflow index row of ``name``.

        ``version`` counts **row rewrites** (019 column, default 1): the first write
        stores 1, every later write of the same name bumps it by one. It is *not* the
        body's ``revision`` — the revision is a content hash used as a CAS token and is
        deliberately never stored here (module docstring).

        ``owner_role`` / ``phase`` are stored verbatim; deriving them is the caller's
        job (the authority is ``teams/artifacts.py``, which this layer cannot import).
        Returns the row as it stands after the write.
        """
        existing = self.get_workflow(project_id=project_id, name=name)
        if existing is None:
            return self.insert(
                artifact_id=artifact_id or new_short_id(),
                project_id=project_id,
                task_id=None,
                name=name,
                uri=uri,
                size=size,
                mime=mime,
                file_hash=file_hash,
                created_by=created_by,
                kind=WORKFLOW_KIND,
                owner_role=owner_role,
                phase=phase,
                version=1,
            )
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE project_artifacts SET uri = ?, size = ?, mime = ?, hash = ?, "
                "version = version + 1, owner_role = ?, phase = ? WHERE artifact_id = ?",
                (uri, size, mime, file_hash, owner_role, phase, existing.artifact_id),
            )
        row = self.get(existing.artifact_id)
        if row is None:  # pragma: no cover - the row was just updated
            raise RuntimeError(f"workflow artifact update failed: {existing.artifact_id}")
        return row
