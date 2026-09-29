"""项目定向写入面（T-50）—— 把记忆**显式**写进 ``project_{project_id}``。

PLAN「写入路径」表的第 2 行（采纳时选归属）与第 4 行（显式「记到项目」）在服务端的落点。
本模块坐在既有件之上，**不重写**它们：

* 命名空间解析 / 句柄缓存 = ``multi_ns.MultiNsRecall.memory_for``（T-36）—— 项目层的 ns
  来自**授权行的** ``projects.memory_namespace``（经 ``resolve_project_namespace``）；
* 候选采纳语义 = ``octop_memory.application.dashboard_data.promote_candidate``（**既有公共
  函数**，与 agent 侧走的是同一套 5 检查 / human-override 逻辑）；
* agent 私有层照旧：默认路径一个字节都不改（不带目标时根本不会走到这里）。

**只搬记忆内容，不搬文档正文**（T-39 铁律）：复制的是 ``Candidate`` / ``AtomCard`` 本身，
文档正文留在 KB，记忆里只有引用。

**权限不在本模块**（SPEC B38）：读写两门分别判定，且**不得**由"读得出"推导"写得进" ——
由 HTTP 适配层用既有的 ``ProjectService.assert_project_role`` 判（写门 = ``PROJECT_WRITE``）。
本模块只接收一个**已经授权过**的 ``project_id`` + ``project_namespace``。
"""

from __future__ import annotations

from typing import Any

from octop.infra.agents.memory.multi_ns import MultiNsRecall
from octop.infra.errors import ErrorCode, OctopError


def _project_memory(
    recall: MultiNsRecall, *, project_id: str, project_namespace: str | None
) -> Any:
    """项目层句柄 —— ns 由 ``projects.memory_namespace`` 授权，绝不在这里拼字符串。"""
    return recall.memory_for("project", project_id=project_id, project_namespace=project_namespace)


def promote_candidate_into_project(
    *,
    recall: MultiNsRecall,
    project_id: str,
    project_namespace: str | None,
    candidate_id: str,
) -> dict[str, Any]:
    """把 agent 层的一条候选**复制进项目层并采纳**，返回与 agent 侧同形的结果。

    复制是必要的：候选表按命名空间物理隔离，项目层里原本没有这一行。复制的是候选
    （记忆内容），**不是**任何文档正文。同 id 再跑一次不会再插一行（先查后写）。
    """
    from octop_memory.application.dashboard_data import (
        promote_candidate,  # noqa: PLC0415 - optional dep
    )

    agent_memory = recall.memory_for("agent")
    candidate = agent_memory.get_candidate(candidate_id)
    if candidate is None:
        raise OctopError(ErrorCode.NOT_FOUND, f"candidate {candidate_id!r} not found")

    project_memory = _project_memory(
        recall, project_id=project_id, project_namespace=project_namespace
    )
    if project_memory.get_candidate(candidate_id) is None:
        project_memory.add_candidate(candidate)

    result: dict[str, Any] = promote_candidate(project_memory, {"candidate_id": candidate_id})
    return {**result, "namespace": project_id, "target_layer": "project"}


def record_atom_into_project(
    *,
    recall: MultiNsRecall,
    project_id: str,
    project_namespace: str | None,
    atom_id: str,
) -> dict[str, Any]:
    """把 agent 层的一条**已有记忆**显式记进项目层（PLAN 写入路径第 4 行）。

    幂等：项目层已有同 id 的原子 ⇒ 不再写入（``recorded=False``）。与上一条一样，
    搬的是记忆内容本身，不是文档正文。
    """
    agent_memory = recall.memory_for("agent")
    atom = agent_memory.get_atom(atom_id)
    if atom is None:
        raise OctopError(ErrorCode.NOT_FOUND, f"atom {atom_id!r} not found")

    project_memory = _project_memory(
        recall, project_id=project_id, project_namespace=project_namespace
    )
    already_there = project_memory.get_atom(atom_id) is not None
    if not already_there:
        project_memory.add_atom(atom)
    return {"recorded": not already_there, "atom_id": atom_id, "target_layer": "project"}


__all__ = ["promote_candidate_into_project", "record_atom_into_project"]
