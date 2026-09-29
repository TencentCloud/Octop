"""T-56 · 门禁的「前提证明」——**形状判别力**，而不只是"拒绝发生了"。

## 这张卡在查什么（`REVIEW.md §6 S1` 的落点）
`reviewer` 自陈：**G3–G16 里除决策门外的 15 个门，它没逐条审"前提证明"**。
一条拒绝用例可以是**绿的、码也对**，而它其实**没有建立那个前提** —— 例如
`test_team_runs_api.py` 里"没有待决决策 ⇒ 409 `TEAM_DECISION_NOT_PENDING`"：
断言是真的，**但那个 run 从不可能有待决决策**（没绑 gateway）⇒ 它证明的是"从未挂起过"。

## 这里的判据（比"断言了具体码"更强一层）
断言了具体码只能证明**是哪条门**在拒；要证明用例**建立了前提**，得证明它**分得清形状**：

* 同一份输入字段，**两种不同形状**必须落到**两条不同的门**上
  （依赖指向"存在但未 done 的任务" ⇒ G5；指向"不存在的 id" ⇒ G6）——
  若实现把两者混成一条门，或某条门根本不可达，这条就会红。
* 一侧"前提成立 ⇒ 会发生"，一侧"前提不成立 ⇒ 不发生"，**同一用例内成对**。

⇒ 本文件**不重复**生产者的用例，只补**形状判别**与**跨层可达性**这两类。
`backend-2`/`backend` 的服务层用例仍是主证据；本文件是第二把尺子。
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from octop.config import OctopConfig
from octop.infra.agents.teams.run_service import TeamRunService, run_directory
from octop.infra.agents.teams.service import TeamService
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.services import build_shared_services
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.gateway.threads import ThreadRegistry
from octop.infra.utils.paths import PathLayout

TEAM_ID = "ag-team"
MANIFEST = ".octop/manifest.json"
MEMBERS = [(TEAM_ID, "lead"), ("ag-be", "backend"), ("ag-qa", "qa")]
FILLED_SPEC = (
    "# SPEC\n\n## 边界与禁止项\n\n| 边界 | 处置 |\n| --- | --- |\n| 不新增错误码 | 复用 |\n"
)


class Actor:
    def __init__(self, user_id: int) -> None:
        self.id = user_id
        self.permissions = ["projects", "knowledge_bases"]

    @property
    def is_admin(self) -> bool:
        return False


class FakeWorkspace:
    def __init__(self, files: dict[str, str] | None = None) -> None:
        self.files: dict[str, str] = dict(files or {})

    def read_text(self, path: str, *, limit: int = 10_000_000) -> str | None:
        return self.files.get(str(path))

    def write_text(self, path: str, content: str, *, force: bool = False) -> None:
        self.files[str(path)] = content

    def exists(self, path: str) -> bool:
        return str(path) in self.files

    def list_dir(self, path: str = ".") -> list[Any]:
        """**Same shape as the harness**: workspace-relative ``{"path", "is_dir"}`` (T-72)."""
        prefix = "" if str(path) in {"", "."} else str(path).rstrip("/") + "/"
        return [
            {"path": n, "is_dir": False}
            for n in sorted(self.files)
            if n.startswith(prefix) and "/" not in n[len(prefix) :]
        ]


class _StubGateway:
    def __init__(self, services: Any) -> None:
        self.thread_registry = ThreadRegistry(
            session_repo=services.session_repo, thread_repo=services.thread_repo
        )


@dataclass
class Harness:
    services: Any
    service: TeamRunService
    workspace: FakeWorkspace
    user: Actor

    def create_run(self, **fields: Any) -> Any:
        fields.setdefault("goal", "premises")
        fields.setdefault("tier", "quick")
        return self.service.create(team_agent_id=TEAM_ID, user=self.user, **fields)

    def write(self, run: Any, name: str, content: str) -> None:
        self.workspace.write_text(f"{run_directory(run)}/{name}", content)

    def add_task(self, run: Any, **fields: Any) -> Any:
        return self.service.create_task(run.run_id, user=self.user, **fields)


@pytest.fixture
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Harness]:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path / "home"))
    paths = PathLayout(tmp_path / ".octop")
    paths.ensure_root()
    db = SqlitePool(paths.db)
    run_migrations(db)
    services = build_shared_services(db=db, paths=paths, config=OctopConfig())
    uid = services.user_repo.create(username="owner", password_hash="h", role="user")
    services.agent_repo.create(agent_id=TEAM_ID, user_id=uid, name="Team", kind="team")
    workspace = FakeWorkspace(
        {
            MANIFEST: json.dumps(
                {
                    "members": [{"agent_id": a, "role": r} for a, r in MEMBERS],
                    "lead_agent_id": TEAM_ID,
                }
            ),
            "other.txt": "x",
        }
    )
    service = TeamRunService(
        services=services,
        gateway=_StubGateway(services),  # type: ignore[arg-type]
        workspace_for=lambda agent_id: workspace if agent_id == TEAM_ID else None,
        team_service=TeamService(
            services.repos,
            workspace_for=lambda agent_id: workspace if agent_id == TEAM_ID else None,
        ),
    )
    yield Harness(services=services, service=service, workspace=workspace, user=Actor(uid))


def _code(fn: Any, *args: Any, **kwargs: Any) -> ErrorCode:
    with pytest.raises(OctopError) as err:
        fn(*args, **kwargs)
    return err.value.code


# ─────────────────────────────────────────────────────────────────────────────
# 形状判别 ①：同一个 dependsOn 字段，两种形状 ⇒ 两条不同的门（G5 vs G6）
# ─────────────────────────────────────────────────────────────────────────────


def test_the_dependency_field_falls_into_two_different_gates(harness: Harness) -> None:
    """**前提证明**：G5 的前提是"上游**存在**但未 done"；G6 的前提是"上游**不存在**"。

    两条门共用一个输入字段。只断言"有一个 409"分不清它们 ⇒ 必须证明**分得清**：

    * 指向**已存在但未 done** 的任务 ⇒ `TEAM_TASK_DEPS_UNMET`（G5，前提**成立**）
    * 指向**不存在的 id** ⇒ `TEAM_TASK_GRAPH_INVALID`（G6，前提是**图不合法**）

    若实现把"不存在"也算成"依赖未满足"，或 G5 因为拿不到 `todo` 任务而走了别的分支，
    这条会红 —— 这是"断言真、理由不对"的直接探测。
    """
    run = harness.create_run()
    upstream = harness.add_task(run, title="upstream", role="backend")

    # G5：上游存在、未 done
    downstream = harness.add_task(run, title="downstream", depends_on=[upstream.id])
    assert (
        _code(harness.service.claim, run.run_id, downstream.id, role="backend", user=harness.user)
        is ErrorCode.TEAM_TASK_DEPS_UNMET
    )

    # G6：上游不存在 —— 同一字段、不同形状、不同的门
    assert (
        _code(harness.add_task, run, title="ghost-dep", depends_on=["no-such-task"])
        is ErrorCode.TEAM_TASK_GRAPH_INVALID
    )


def test_g5_premise_passes_the_moment_the_upstream_is_done(harness: Harness) -> None:
    """**前提不成立 ⇒ 不发生**：上游真的 `done` 之后，同一个 claim 必须放行。

    ★ 这条是"前提证明"的活教材 —— 我第一版用 `complete()` 想把上游弄成 done，
    **结果仍然 `TEAM_TASK_DEPS_UNMET`**。回源后发现：`complete()` 把任务落进 **`review`**
    （"Finishing lands the task in ``review``（a verdict closes it）"），**`review` 不是 `done`**
    ⇒ 我**没有建立那个前提**，而用例红着把这个错误告诉了我。
    ⇒ 这正是本卡要抓的形态：**"我调用了收尾接口" ≠ "任务已 done"**。
    """
    run = harness.create_run()
    upstream = harness.add_task(run, title="upstream", role="backend")
    downstream = harness.add_task(run, title="downstream", depends_on=[upstream.id])

    # 前提的形状之一：complete() 只到 review，**不足以**解锁下游
    up_claim = harness.service.claim(run.run_id, upstream.id, role="backend", user=harness.user)
    harness.service.complete(
        run.run_id,
        upstream.id,
        role="backend",
        attempt_id=up_claim.attempt_id or "",
        changed_paths=[],
        user=harness.user,
    )
    assert harness.services.project_task_repo.get(upstream.id).status == "review"
    assert (
        _code(harness.service.claim, run.run_id, downstream.id, role="backend", user=harness.user)
        is ErrorCode.TEAM_TASK_DEPS_UNMET
    ), "review 不是 done ⇒ 下游不得解锁"

    # 前提成立：任务真的 done（生产者用例用的同一原语）
    harness.services.project_task_repo.update(upstream.id, status="done")
    claimed = harness.service.claim(run.run_id, downstream.id, role="backend", user=harness.user)
    assert claimed.attempt_id, "上游 done 后必须放行（否则 G5 的门永远关着）"


# ─────────────────────────────────────────────────────────────────────────────
# 形状判别 ②：阶段迁移的两种形状（G2 非法迁移 vs G4 迁移合法但门未过）
# ─────────────────────────────────────────────────────────────────────────────


def test_an_illegal_transition_and_an_unmet_gate_are_different_gates(
    harness: Harness,
) -> None:
    """G2 的前提是"目标阶段**不在允许集**里"；G4 的前提是"迁移合法、但边界表空"。

    两者都是 advance 的 409 ⇒ 只断言"409"永远分不清。这里要求**分得清**，
    并且用**同一个 run**先证 G2、再证 G4，排除"是两个不同环境导致的差别"。
    """
    run = harness.create_run(tier="quick")

    # G2：跳到不允许的阶段（quick 档 clarify 的允许集只有 implement）
    assert (
        _code(harness.service.advance, run.run_id, to_phase="deliver", user=harness.user)
        is ErrorCode.TEAM_RUN_PHASE_INVALID
    )

    # G4：迁移本身**合法**（quick 档 clarify → implement 是允许的下一个），但边界表为空。
    # 实测确认：G4 守的是 **implement** 这一跳，不是任意跳
    # （先前把 to_phase 写成 "research" 时拿到的是 TEAM_PHASE_GATE_FAILED ⇒ 那是 G2/G3 的门，
    #  不是 G4 —— 这条用例本身就是"前提写错会拿到别的门"的实证）。
    assert (
        _code(harness.service.advance, run.run_id, to_phase="implement", user=harness.user)
        is ErrorCode.TEAM_SPEC_BOUNDARY_EMPTY
    )


def test_the_spec_boundary_gate_distinguishes_missing_from_empty(harness: Harness) -> None:
    """G4 的两种前提形状：SPEC.md **不存在** vs **存在但边界表空**（都该拒，且可分辨）。

    只测一种会把"文件缺失"当成"表没填" ⇒ 填了表仍然进不去时，用例不会红。
    """
    run = harness.create_run(tier="quick")

    # 形状 a：SPEC.md 根本不存在
    assert (
        _code(harness.service.advance, run.run_id, to_phase="implement", user=harness.user)
        is ErrorCode.TEAM_SPEC_BOUNDARY_EMPTY
    )

    # 形状 b：SPEC.md 存在，但边界表是空行
    harness.write(run, "SPEC.md", "# SPEC\n\n## 边界与禁止项\n\n| 边界 | 处置 |\n| --- | --- |\n")
    assert (
        _code(harness.service.advance, run.run_id, to_phase="implement", user=harness.user)
        is ErrorCode.TEAM_SPEC_BOUNDARY_EMPTY
    )

    # 前提成立（表填实）⇒ 不再被 G4 拦
    harness.write(run, "SPEC.md", FILLED_SPEC)
    harness.service.advance(run.run_id, to_phase="implement", user=harness.user)
    assert harness.service.require_run(run.run_id).phase == "implement"


# ─────────────────────────────────────────────────────────────────────────────
# 形状判别 ③：工件归属的三态（G14：创建放行 / 非负责人拒绝 / 版本过期）
# ─────────────────────────────────────────────────────────────────────────────


def test_artifact_ownership_has_three_distinguishable_shapes(harness: Harness) -> None:
    """G14 的前提是"目标**已存在**"；G14 的 CAS 前提是"给的 revision **不是**盘上的"。

    三态必须落成三种**不同**结果，否则"用旧 revision 覆写"会被误当成"越权"。
    """
    run = harness.create_run()

    # 态 1：不存在 ⇒ 创建放行（前提不成立 ⇒ 不发生）
    created = harness.service.write_artifact(
        run.run_id, name="SPEC.md", content="# v1", revision="", role="pm", user=harness.user
    )
    assert created["revision"]

    # 态 2：已存在 + 非负责人 ⇒ 归属拒绝
    assert (
        _code(
            harness.service.write_artifact,
            run.run_id,
            name="SPEC.md",
            content="# hijack",
            revision=created["revision"],
            role="backend",
            user=harness.user,
        )
        is ErrorCode.TEAM_ARTIFACT_OWNERSHIP_DENIED
    )

    # 态 3：已存在 + 负责人 + 旧 revision ⇒ CAS 拒绝（**不是**归属拒绝）
    assert (
        _code(
            harness.service.write_artifact,
            run.run_id,
            name="SPEC.md",
            content="# v2",
            revision="deadbeefdeadbeef",
            role="pm",
            user=harness.user,
        )
        is ErrorCode.TEAM_ARTIFACT_STALE
    )


# ─────────────────────────────────────────────────────────────────────────────
# 形状判别 ④：审查独立性（G13：同一 attempt ⇒ 拒；换人换 attempt ⇒ 放）
# ─────────────────────────────────────────────────────────────────────────────


def test_review_independence_denies_only_the_same_claimer(harness: Harness) -> None:
    """G13 的前提是"审查者与最近一次实现的 `claimed_by` **相同**"。

    只测"自审被拒"证明不了前提 —— 必须证明**换人之后放行**，否则可能整条门恒拒。
    """
    run = harness.create_run()
    work = harness.add_task(run, title="实现", role="backend")
    harness.service.claim(run.run_id, work.id, role="backend", user=harness.user)

    review = harness.add_task(run, title="审", role="backend", kind="review")
    claimed = harness.service.claim(run.run_id, review.id, role="backend", user=harness.user)

    assert (
        _code(
            harness.service.verdict,
            run.run_id,
            review.id,
            role="backend",
            attempt_id=claimed.attempt_id or "",
            verdict="pass",
            user=harness.user,
        )
        is ErrorCode.TEAM_REVIEW_SELF_AUDIT
    )

    # 换人（并换 attempt）⇒ 前提不成立 ⇒ 放行
    transferred = harness.services.project_task_repo.claim(
        review.id, claimed_by="reviewer", expected_attempt_id=claimed.attempt_id
    )
    assert transferred is not None
    passed = harness.service.verdict(
        run.run_id,
        review.id,
        role="reviewer",
        attempt_id=transferred.attempt_id or "",
        verdict="pass",
        user=harness.user,
    )
    assert passed.verdict == "pass"


# ─────────────────────────────────────────────────────────────────────────────
# ★ 跨层可达性：门"拒成了"，但生产路径收不到 —— G6 的现症（task-86 的目标）
# ─────────────────────────────────────────────────────────────────────────────


def test_a_graph_refusal_can_be_serialised_after_the_fix() -> None:
    """**T-65 落地后的翻转**（旧名：`test_a_graph_refusal_cannot_be_serialised_today`）。

    旧用例断言的是"**今天会炸**"（`details["code"]` 与 `error_message` 的形参 `code` 撞名
    ⇒ `to_envelope` 抛 `TypeError`）。**T-65 已修** ⇒ 现在断言：**序列化必须成功**，
    且 `code` / `details.code` / 本地化消息三样都对，并**保留服务层的形状**
    （异常对象本身仍带 `details["code"]`，那是 G6 契约的一部分）。
    """
    from octop.infra.agents.teams.pipeline import validate_task_graph

    with pytest.raises(OctopError) as err:
        validate_task_graph([{"id": "a", "dependsOn": ["ghost"]}])
    graph_error = err.value

    # 服务层形状不变（这是 G6 的对外契约）
    assert graph_error.code is ErrorCode.TEAM_TASK_GRAPH_INVALID
    assert graph_error.details.get("code") == "missing-id"

    # 序列化层：修好之后必须成功，且三样都对
    envelope = graph_error.to_envelope(locale="zh")
    assert envelope["error"]["code"] == "TEAM_TASK_GRAPH_INVALID"
    assert envelope["error"]["details"]["code"] == "missing-id"
    assert "任务依赖图" in envelope["error"]["message"], envelope["error"]["message"]
