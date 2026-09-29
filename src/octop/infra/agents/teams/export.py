"""只读投影导出：`TASKS.json` / `任务看板.md` / `STATE.json` / `ROSTER.json`（T-14）。

**单向投影（PLAN §工件表 · 分层原则）**：状态源**唯一是 DB**（`team_runs` /
`team_run_phases` / `team_run_members` / `project_tasks` / `project_task_findings`），
本模块把 DB 读成四份**只读工件**。**导出器从不读回这四份工件** —— 否则投影会形成环
（读自己的产物当成状态），本仓的「一个事实多份拷贝」就是这么长出来的。

**身份区分（★ 本模块存在的意义，`sec` 在 T-12 抓到的提权面就是这条被写反）**：

* `teams/artifacts.py` 把 ``"STATE.json"`` / ``"ROSTER.json"`` / ``"TASKS.json"`` 登记为
  ``owners = ()`` —— 语义是「**runtime only (no role may overwrite)**」，**不是**「必须
  放行」。任何**业务角色**经 :meth:`TeamRunService.write_artifact` 覆盖已存在的这三份，
  都会被 `artifacts.owner_violation` 拒成 ``TEAM_ARTIFACT_OWNERSHIP_DENIED``（创建仍
  放行，那是建 run 落骨架的路径）。
* 写这三份的**唯一合法身份是运行时**：本模块就是那个运行时写者。因此
  **本模块不得被任何角色化写路径调用**（没有 `role=` 入参、不接受业务角色的调用栈），
  它只接受从 DB 读出的状态。
* `任务看板.md` 不在归属表内（`owners_of(...) is None` ⇒ 不限制），但**同样只由本模块
  生成** —— 「不在表里」不等于「谁都可以覆写」，两个通道的严格度刻意不同。

**可重复（同状态 ⇒ 逐字节相同）**：键序由 ``sort_keys=True`` + 固定 indent 钉死；
**时间字段一律取行里的既有值**（``run.created_at`` / ``run.updated_at`` /
``member.joined_at`` / ``task.created_at``），**不调 ``now()``**。**例外清单：无** ——
若将来要加"导出时刻"这类字段，必须在此处显式登记，并说明它破坏了哪条可重复性。

**写路径**：全部经 ``BackendWorkspace.write_text``（`AGENTS.md §7`：工作区内容不得用
裸 ``Path.write_text``）。本模块不 import `api/`、不碰 DB 连接（只吃行对象）。
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

# -- 工件名（与 artifacts.ARTIFACT_OWNERS 的键逐字一致） ------------------------------

TASKS_JSON = "TASKS.json"
KANBAN_MD = "任务看板.md"
STATE_JSON = "STATE.json"
ROSTER_JSON = "ROSTER.json"

#: 本模块负责的四份投影，顺序即落盘顺序（稳定，便于 diff）。
PROJECTION_FILES: tuple[str, ...] = (TASKS_JSON, KANBAN_MD, STATE_JSON, ROSTER_JSON)

#: `TASKS.json` 的来源标记（PLAN API 面：`{"authority":"db","tasks":[…]}`）。
#:
#: **恒为 `"db"`，不是可配项**：状态源唯一是 DB（PLAN §工件表 · 分层原则）。它存在的
#: 意义是让产物**自带**"我不是权威、不可回灌"这个事实 —— 任何人想把它当状态源读回去
#: 时，先撞上这行标记。
AUTHORITY_DB = "db"

# -- 上游协议 token ↔ Octop 存储值（PLAN §词表冻结 · 状态词表，逐行照抄） ---------------
#
#   | 上游 token     | Octop 存储  | 判据                                                    |
#   | `pending`      | `todo`     | `assignee_id IS NULL`                                    |
#   | `claimed`      | `todo`     | `assignee_id IS NOT NULL AND claimed_at IS NOT NULL ...`  |
#   | `in_progress`  | `doing`    | —                                                        |
#   | `completed`    | `done`     | —                                                        |
#   | `failed`       | `blocked`  | `verdict IN ('needs_revision','reject')`                  |
#   | `cancelled`    | `cancelled`| —                                                        |
#   | `rework`       | `doing`    | 由 `review→doing` 回边产生，`round` 已递增                  |
#
# **投影只朝一个方向**：这里把存储值翻成上游 token；**禁止**把上游 token 写回 DB
# （PLAN §词表冻结明列）。API 入参一律用存储值。
_TOKEN_BY_STATUS: Mapping[str, str] = {
    "todo": "pending",
    "doing": "in_progress",
    "review": "in_progress",
    "blocked": "failed",
    "done": "completed",
    "cancelled": "cancelled",
    "planning": "pending",
}

#: 任务状态词表（存储值）—— 与 `project_tasks.TASK_STATUSES` 同集合；此处只用于校验，
#: 不在本模块重造状态机。
STORAGE_TASK_STATUSES: frozenset[str] = frozenset(_TOKEN_BY_STATUS)


def task_token(task: Mapping[str, Any]) -> str:
    """存储值 ⇒ 上游 token（PLAN §词表冻结，含 `claimed` / `rework` 的判据）。

    `todo` 分三态：未认领 ⇒ `pending`；已认领未开工 ⇒ `claimed`；`doing` 里若
    `round > 1` ⇒ `rework`（`review→doing` 回边的产物）。判据全部来自**行里的字段**，
    不看任何外部时钟。
    """
    status = str(task.get("status") or "")
    token = _TOKEN_BY_STATUS.get(status)
    if token is None:
        # 不在词表里的状态**不猜**：原样回显，让人一眼看见异常值（fail-visible）。
        return status or "unknown"
    if status == "todo":
        if not task.get("assignee_id") and not task.get("claimed_by"):
            return "pending"
        if task.get("started_at") is None:
            return "claimed"
        return "in_progress"
    if status == "doing" and int(task.get("round") or 1) > 1:
        return "rework"
    if status == "blocked":
        verdict = str(task.get("verdict") or "")
        if verdict in {"needs_revision", "reject"}:
            return "failed"
        return "failed"
    return token


def _dump(payload: Mapping[str, Any]) -> str:
    """稳定的 JSON 文本：键序固定 + 固定缩进 + 尾换行（两次导出逐字节相同）。"""
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _task_row(task: Mapping[str, Any]) -> dict[str, Any]:
    """`TASKS.json` 的单条 —— 与既有 `team/<run>/TASKS.json` 的键**同构**。

    既有那份的键：`id/title/kind/owner/spec/acceptance/inScope/verify/dependsOn/
    status/attempt/round`（人可读投影，不是新格式）。
    """
    return {
        "id": str(task.get("id") or ""),
        "title": str(task.get("title") or ""),
        "kind": str(task.get("kind") or "work"),
        "owner": str(task.get("owner") or task.get("role") or ""),
        "spec": str(task.get("spec") or task.get("description") or ""),
        "acceptance": [str(item) for item in task.get("acceptance") or ()],
        "inScope": [str(item) for item in task.get("in_scope") or task.get("inScope") or ()],
        "verify": [str(item) for item in task.get("verify") or ()],
        "dependsOn": [str(item) for item in task.get("deps") or task.get("dependsOn") or ()],
        "status": task_token(task),
        "attempt": int(task.get("attempt") or 0),
        "round": int(task.get("round") or 1),
    }


def render_tasks_json(*, tasks: Sequence[Mapping[str, Any]]) -> str:
    """`TASKS.json` —— **只读投影**（PLAN §工件表：角色一律不得覆写）。

    `"authority": "db"` 是**机器可读的来源标记**（PLAN API 面同一行）：它把
    「状态源唯一是 DB」写在产物里，读的人（或下一个工具）不必回头查文档就知道
    **这份文件不是权威、不可回灌** —— 与模块 docstring 的"单向不可回灌"是同一条。
    """
    return _dump({"authority": AUTHORITY_DB, "tasks": [_task_row(task) for task in tasks]})


def render_kanban(
    *,
    run: Mapping[str, Any],
    phases: Sequence[Mapping[str, Any]],
    members: Sequence[Mapping[str, Any]],
    tasks: Sequence[Mapping[str, Any]],
) -> str:
    """`任务看板.md` —— 阶段 / 覆盖率矩阵 / 任务表（三段，全部来自 DB 行）。"""
    lines: list[str] = [f"# 任务看板 · {run.get('run_id')}", ""]
    lines += [
        f"- 目标：{run.get('goal')}",
        f"- 阶段：`{run.get('phase')}` ｜ 状态：`{run.get('status')}` ｜ 档位：`{run.get('tier')}`",
        "",
        "## 阶段",
        "",
        "| # | 阶段 | 状态 | gate_detail |",
        "|---|---|---|---|",
    ]
    for row in phases:
        detail = row.get("gate_detail") or {}
        lines.append(
            f"| {row.get('seq')} | `{row.get('phase')}` | `{row.get('status')}` | "
            f"{json.dumps(detail, ensure_ascii=False, sort_keys=True) if detail else '—'} |"
        )
    lines += ["", "## 覆盖率矩阵", "", "| 角色 | 成员 | 任务数 | 已完成 |", "|---|---|---|---|"]
    counts: dict[str, list[int]] = {}
    for task in tasks:
        owner = str(task.get("owner") or task.get("role") or "")
        bucket = counts.setdefault(owner, [0, 0])
        bucket[0] += 1
        if task_token(task) == "completed":
            bucket[1] += 1
    for member in members:
        role = str(member.get("role") or "")
        total, done = counts.get(role, [0, 0])
        lines.append(f"| `{role}` | `{member.get('agent_id')}` | {total} | {done} |")
    lines += [
        "",
        "## 任务",
        "",
        "| 任务 | 标题 | 角色 | 状态 | attempt | round | 依赖 |",
        "|---|---|---|---|---|---|---|",
    ]
    for task in tasks:
        lines.append(
            f"| {task.get('id')} | {task.get('title')} | `{task.get('owner') or task.get('role') or ''}` | "
            f"`{task_token(task)}` | {int(task.get('attempt') or 0)} | {int(task.get('round') or 1)} | "
            f"{', '.join(str(item) for item in task.get('deps') or ()) or '—'} |"
        )
    return "\n".join(lines) + "\n"


def render_state_json(
    *,
    run: Mapping[str, Any],
    members: Sequence[Mapping[str, Any]],
) -> str:
    """`STATE.json` —— **运行时专属**（`owners == ()`）；字段取自 run 行，时间取 `updated_at`。"""
    return _dump(
        {
            "runId": str(run.get("run_id") or ""),
            "phase": str(run.get("phase") or ""),
            "status": str(run.get("status") or ""),
            "mode": str(run.get("mode") or ""),
            "deliverable": str(run.get("deliverable") or ""),
            "tier": str(run.get("tier") or ""),
            "coverage": [],
            "members": [f"{m.get('agent_id')}:{m.get('role')}" for m in members],
            "updatedAt": int(run.get("updated_at") or 0),
        }
    )


def render_roster_json(
    *,
    run: Mapping[str, Any],
    members: Sequence[Mapping[str, Any]],
) -> str:
    """`ROSTER.json` —— **运行时专属**（`owners == ()`）；`createdAt` 取 run 行。"""
    return _dump(
        {
            "runId": str(run.get("run_id") or ""),
            "roles": sorted({str(m.get("role") or "") for m in members}),
            "members": [
                {
                    "agent_id": str(m.get("agent_id") or ""),
                    "role": str(m.get("role") or ""),
                    "is_lead": bool(m.get("is_lead")),
                }
                for m in members
            ],
            "createdAt": int(run.get("created_at") or 0),
        }
    )


def project(
    *,
    run: Mapping[str, Any],
    phases: Sequence[Mapping[str, Any]],
    members: Sequence[Mapping[str, Any]],
    tasks: Sequence[Mapping[str, Any]],
) -> dict[str, str]:
    """四份投影的**纯函数**版本（无 IO、无时钟）—— 返回 `{basename: content}`。

    这是"同状态 ⇒ 逐字节相同"的判定面：同样的输入调两次，返回的 dict 逐字节相同。
    """
    return {
        TASKS_JSON: render_tasks_json(tasks=tasks),
        KANBAN_MD: render_kanban(run=run, phases=phases, members=members, tasks=tasks),
        STATE_JSON: render_state_json(run=run, members=members),
        ROSTER_JSON: render_roster_json(run=run, members=members),
    }


def _as_mapping(row: Any) -> dict[str, Any]:
    """行对象 ⇒ dict（dataclass 行；**只读**，不做任何补字段）。"""
    if isinstance(row, Mapping):
        return dict(row)
    fields = getattr(row, "__dataclass_fields__", None)
    if fields:
        return {name: getattr(row, name) for name in fields}
    raise TypeError(f"projection needs dataclass or mapping rows, got {type(row).__name__}")


async def export_run(service: Any, run_id: str, *, directory: str | None = None) -> dict[str, str]:
    """把 *run_id* 的当前状态导出成四份工件（**经 `BackendWorkspace` 写**）。

    :param service: `TeamRunService`（本模块**只读**它：`get_run` / `list_tasks` /
        `snapshot` / 三表 repo 的 list 方法）。
    :param directory: run 目录（默认 `run_directory(run)`）。
    :returns: `{basename: content}`（写下去的就是这些字节，便于逐字节 diff）。

    **不回灌**：本函数从不调用 `workspace.read_text` 读这四份工件 —— 状态只来自 DB。
    """
    from octop.infra.agents.teams.run_service import run_directory

    row = service.require_run(run_id)
    run = _as_mapping(row)
    runs_repo = service._runs  # noqa: SLF001 — 导出器属运行时身份，见模块 docstring
    phases = [_as_mapping(item) for item in runs_repo.list_phases(run_id)]
    members = [_as_mapping(item) for item in runs_repo.list_members(run_id)]
    tasks = [_as_mapping(item) for item in service.list_tasks(run_id)]
    target_dir = directory or run_directory(row)
    payload = project(run=run, phases=phases, members=members, tasks=tasks)

    workspace = service._workspace(row)  # noqa: SLF001 — 同上
    if workspace is None:
        raise RuntimeError(f"run {run_id!r} has no bound workspace to export into")
    for name in PROJECTION_FILES:
        content = payload[name]
        path = f"{target_dir}/{name}"
        try:
            workspace.write_text(path, content, force=True)
        except TypeError:
            workspace.write_text(path, content)
    return payload
