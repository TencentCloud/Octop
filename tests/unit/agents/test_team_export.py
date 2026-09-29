"""只读投影导出（T-14）—— 单向性、身份区分、可重复、形状同构。

这四条**各自都有会失败的用例**（不是只跑一遍看它没抛异常）：

1. **单向不可回灌**：AST 证明 `export.py` 里**没有任何读调用**；再用"工件已被污染"
   的现场证明导出结果只来自 DB 行（污染值不会出现在产物里）。
2. **身份区分**：`STATE.json`/`ROSTER.json`/`TASKS.json` 的 `owners == ()` ⇒
   **runtime only（任何业务角色不得覆写）**；静态证明业务侧**没有第二条写路径**。
3. **可重复**：同一状态导出两次 ⇒ **逐字节相同**（用 `==` 逐字节比对，并列出
   任何差异）；时间只来自行、不来自时钟（AST 禁 `now()/time()/uuid()/random()`）。
4. **形状同构**：`TASKS.json` 的键集与既有 `team/<run>/TASKS.json` **逐字相同**。
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest

from octop.infra.agents.teams import export
from octop.infra.agents.teams.artifacts import ARTIFACT_OWNERS, owner_violation

REPO_ROOT = Path(__file__).resolve().parents[3]
EXPORT_PY = REPO_ROOT / "src/octop/infra/agents/teams/export.py"

#: 既有 `team/2026-09-28-145847/TASKS.json` 的单条键集（**独立 oracle**，逐字抄自
#: 该工件；导出器必须与它同构，而不是另造格式）。
_EXISTING_TASKS_KEYS = {
    "id",
    "title",
    "kind",
    "owner",
    "spec",
    "acceptance",
    "inScope",
    "verify",
    "dependsOn",
    "status",
    "attempt",
    "round",
}


def _run_row(**over: Any) -> dict[str, Any]:
    row = {
        "run_id": "2026-09-28-145847",
        "goal": "只读投影导出",
        "phase": "implement",
        "status": "running",
        "mode": "persist",
        "deliverable": "code+artifacts",
        "tier": "strict",
        "ownerSession": "session-x",
        "created_at": 1_756_000_000,
        "updated_at": 1_756_000_500,
    }
    row.update(over)
    return row


def _members() -> list[dict[str, Any]]:
    return [
        {"agent_id": "a1", "role": "pm", "is_lead": True},
        {"agent_id": "a2", "role": "backend", "is_lead": False},
    ]


def _phases() -> list[dict[str, Any]]:
    return [
        {"phase": "clarify", "seq": 0, "status": "passed", "gate_detail": {}},
        {
            "phase": "implement",
            "seq": 5,
            "status": "active",
            "gate_detail": {"skipped_roles": ["docs"]},
        },
    ]


def _tasks() -> list[dict[str, Any]]:
    return [
        {
            "id": "T-01",
            "title": "任务一",
            "kind": "implementation",
            "owner": "backend",
            "spec": "做一件事",
            "acceptance": ["能跑"],
            "inScope": ["a.py"],
            "verify": ["uv run pytest -q"],
            "dependsOn": ["T-00"],
            "status": "doing",
            "attempt": 2,
            "round": 3,
        }
    ]


# ---------------------------------------------------------------- ① 单向不可回灌


def _calls_in(path: Path) -> list[ast.Call]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [node for node in ast.walk(tree) if isinstance(node, ast.Call)]


def _call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def test_export_module_has_no_read_call() -> None:
    """① AST：`export.py` 里**没有任何读调用**（read_text / read_bytes / open / read）。"""
    banned = {"read_text", "read_bytes", "readlines", "open", "read"}
    offenders = sorted({_call_name(call) for call in _calls_in(EXPORT_PY)} & banned)
    assert offenders == [], f"导出器必须单向：不得读回（{offenders}）"


@pytest.mark.anyio
async def test_export_ignores_polluted_artifacts(tmp_path: Path) -> None:
    """① 行为：工件已被污染/删除，导出结果依然只反映 DB 行（证明没读回）。"""
    polluted = {
        "TASKS.json": '{"tasks":[{"id":"HACKED"}]}',
        "STATE.json": '{"status":"HACKED"}',
        "ROSTER.json": '{"roles":["HACKED"]}',
        "任务看板.md": "# HACKED",
    }

    class _Workspace:
        def __init__(self) -> None:
            self.files: dict[str, str] = dict(polluted)

        def read_text(self, path: str, *, limit: int = 10_000_000) -> str | None:
            return self.files.get(path)

        def write_text(self, path: str, content: str, *, force: bool = False) -> None:
            self.files[path] = content

    class _Service:
        def __init__(self, ws: _Workspace) -> None:
            self._ws = ws
            self._runs = type(
                "R", (), {"list_phases": lambda _s, _r: [], "list_members": lambda _s, _r: []}
            )()

        def require_run(self, run_id: str) -> dict[str, Any]:
            return _run_row()

        def list_tasks(self, run_id: str) -> list[dict[str, Any]]:
            return _tasks()

        def _workspace(self, run: Any) -> _Workspace:
            return self._ws

    workspace = _Workspace()
    payload = await export.export_run(_Service(workspace), "2026-09-28-145847", directory="runs/x")
    assert "HACKED" not in payload["TASKS.json"]
    assert "HACKED" not in payload["STATE.json"]
    assert "HACKED" not in payload["ROSTER.json"]
    assert "HACKED" not in payload["任务看板.md"]
    # 写下去的就是返回值（逐字节），四份齐备。
    for name in export.PROJECTION_FILES:
        assert workspace.files[f"runs/x/{name}"] == payload[name]


# ---------------------------------------------------------------- ② 身份区分


def test_projection_targets_are_runtime_only_in_the_ownership_table() -> None:
    """② 归属表：三份 JSON 的 `owners == ()` ⇒ runtime only（不是"必须放行"）。"""
    for name in ("STATE.json", "ROSTER.json", "TASKS.json"):
        assert ARTIFACT_OWNERS[name] == (), name
        # 任何**已识别**的业务角色覆盖已存在的这三份 ⇒ 拒绝（创建仍放行）。
        for role in ("pm", "architect", "backend", "reviewer"):
            reason = owner_violation(role=role, base=name, exists=True)
            assert reason is not None, f"{role} 不该能覆盖 {name}"
            assert "runtime only" in reason
        assert owner_violation(role="pm", base="STATE.json", exists=False) is None


def test_no_second_write_path_for_the_projections() -> None:
    """② 静态：除 `export.py` 外，`src/` 内**没有任何写调用**指向这四份工件。

    判据是**写调用**（`write_text`/`write_bytes`/`aupload*`/`write_artifact`/`write`）的
    源码片段里出现投影文件名 —— **不是**"谁提到过这个名字"：归属表（`artifacts.py`）、
    门的必需工件表（`pipeline.py`）与 T-16 的 HTTP 只读端点都会**提到**它们，那都是合法
    的**非写**引用。把它写成"只许两个文件提到"会误报（本用例的第一版就误报过）。
    """
    write_calls = {
        "write_text",
        "write_bytes",
        "aupload",
        "aupload_many",
        "write_artifact",
        "write",
    }
    hits: list[str] = []
    for path in (REPO_ROOT / "src").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or _call_name(node) not in write_calls:
                continue
            segment = ast.get_source_segment(text, node) or ""
            if any(name in segment for name in export.PROJECTION_FILES):
                hits.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}")
    assert hits == [], f"出现第二个写路径：{hits}"


def test_docstring_states_the_identity_distinction() -> None:
    """② docstring 必须把身份区分写清（否则下一个人会把 `owners == ()` 读成"放行"）。"""
    doc = export.__doc__ or ""
    assert "runtime only" in doc
    assert "不得被任何角色化写路径调用" in doc
    assert "从不读回" in doc


# ---------------------------------------------------------------- ③ 可重复


def test_projection_is_byte_identical_across_two_calls() -> None:
    """③ 同状态 ⇒ 逐字节相同（不是"断言相等"，是**字节**比对）。"""
    kwargs = {"run": _run_row(), "phases": _phases(), "members": _members(), "tasks": _tasks()}
    first = export.project(**kwargs)
    second = export.project(**kwargs)
    for name in export.PROJECTION_FILES:
        assert first[name].encode("utf-8") == second[name].encode("utf-8"), name


def test_projection_uses_state_time_not_the_clock() -> None:
    """③ AST：导出器不得调时钟/随机（时间字段只来自行）。"""
    banned = {"now", "utcnow", "time", "today", "uuid1", "uuid4", "random"}
    offenders = sorted({_call_name(call) for call in _calls_in(EXPORT_PY)} & banned)
    assert offenders == [], f"时间/随机必须来自状态：{offenders}"
    state = json.loads(export.render_state_json(run=_run_row(), members=_members()))
    assert state["updatedAt"] == 1_756_000_500
    roster = json.loads(export.render_roster_json(run=_run_row(), members=_members()))
    assert roster["createdAt"] == 1_756_000_000


# ---------------------------------------------------------------- ④ 形状同构


def test_tasks_json_is_isomorphic_to_the_existing_artifact() -> None:
    """④ `TASKS.json` 的**任务行**键集与既有 run 工件逐字相同（人可读投影，不是新格式）。

    顶层另有 `"authority": "db"`（PLAN API 面要求的来源标记）—— 既有工件没有这一行，
    所以**顶层键集刻意不同构**，同构的是**行**。本用例第一版把顶层钉成 `{"tasks"}`，
    补标记时按实修正（**只改断言值，意图不变**）。
    """
    payload = json.loads(export.render_tasks_json(tasks=_tasks()))
    assert set(payload) == {"authority", "tasks"}
    assert set(payload["tasks"][0]) == _EXISTING_TASKS_KEYS


def test_tasks_json_authority_marker_is_always_db() -> None:
    """`authority` 恒为 `"db"` —— 状态源唯一是 DB（与"单向不可回灌"同一条）。

    标记不是可配项、也不随输入变化：空任务、脏状态、任何调用路径都是同一个值。
    """
    assert export.AUTHORITY_DB == "db"
    for tasks in ([], _tasks(), [{"id": "X", "status": "weird"}]):
        payload = json.loads(export.render_tasks_json(tasks=tasks))
        assert payload["authority"] == "db", tasks
    # 键序稳定（`sort_keys`）⇒ 标记恒在最前，diff 时一眼可见。
    assert (
        export.render_tasks_json(tasks=_tasks()).splitlines()[1].strip().startswith('"authority"')
    )


# ---------------------------------------------------------------- token 映射


def test_token_mapping_matches_plan_status_table_row_by_row() -> None:
    """PLAN §词表冻结 · 状态词表：七行逐行验证（含 `claimed` / `rework` 判据）。"""
    cases: list[tuple[dict[str, Any], str]] = [
        ({"status": "todo", "assignee_id": None, "claimed_by": None}, "pending"),
        (
            {"status": "todo", "assignee_id": "a2", "claimed_by": "backend", "started_at": None},
            "claimed",
        ),
        (
            {"status": "todo", "assignee_id": "a2", "claimed_by": "backend", "started_at": 5},
            "in_progress",
        ),
        ({"status": "doing"}, "in_progress"),
        ({"status": "doing", "round": 2}, "rework"),
        ({"status": "done"}, "completed"),
        ({"status": "blocked", "verdict": "needs_revision"}, "failed"),
        ({"status": "blocked", "verdict": "reject"}, "failed"),
        ({"status": "cancelled"}, "cancelled"),
    ]
    for task, expected in cases:
        assert export.task_token(task) == expected, task
    # 不在词表里的状态**不猜**：原样回显（fail-visible），不静默映射成 pending。
    assert export.task_token({"status": "weird"}) == "weird"
