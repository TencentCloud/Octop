"""R1 工件归属的**工具通道硬门禁** —— 在 ``write_file`` / ``edit_file`` 写盘**之前**拦。

对齐上游 ``lib/artifact-ownership.js · createOwnershipGate @ 138``：本模块只负责**取上下文**
（目标路径 / run / 角色 / 存在性），判定委托给纯函数
:func:`octop.infra.agents.teams.artifacts.owner_violation`。所有上下文一律经**依赖注入**
取得 ⇒ 本模块**不 import repos、不需要数据库**即可单测。

── 门禁语义（为什么是「创建放行、覆写才拦」）────────────────────────────────

建 run 时**首个成员**要按模板一次性把 13 份骨架落到 ``<run_root>/<runId>/``，其中大多数
**不属于它**。「角色 ≠ 负责人 ⇒ 拦」会**直接打死建 run**。因此判据是：**目标不存在（创建）
⇒ 放行；已存在且写者不是它的负责人 ⇒ 拒绝**。这条判据只查一次存在性、**不读内容**，所以
能放在写盘之前（`PLAN.md · 门禁落点④ G1` / `L1 工具通道硬门禁`）。

``owners == []``（``STATE.json`` / ``ROSTER.json``）在**本通道也拒绝** —— 运行时专属，
任何角色不得覆写（`PLAN.md` 工件表的 `ROSTER.json` / `STATE.json` 两行 + `L1` 行；
`SPEC.md · B13` 逐字：「工具通道 ⇒ ``ToolMessage(status="error")`` + 事件
``team.artifact.ownership_denied``」）。

── ★ 诚实边界（不得删除，不得改写成「不可绕过」）─────────────────────────────

本门禁只覆盖 **``write_file`` / ``edit_file`` 工具通道 ＋ 服务层**
（``PUT /api/team/runs/{run_id}/artifacts/{name}``）。持有 ``execute_shell_command``（bash）
的角色可以用 ``cat > SPEC.md`` 这类**重定向绕过**它；首版**刻意**不对 bash 参数做启发式
检查（写目标可以是重定向 / 变量 / 子命令，静态判断不可靠）。这是**有意的取舍，不是缺陷**。
⇒ 对外表述恒为「**``write``/``edit`` 通道的硬门禁**」，**不是**「不可能违反」。
（bash 那一路的补救在**服务层** —— 那是唯一绕不过的一层。）

**同步路径不会静默放行**：本类只实现 ``awrap_tool_call``（与同目录 ``binary_read_guard``
一致）。LangGraph 的默认 ``wrap_tool_call`` 会**显式抛** ``NotImplementedError``
（``langchain/agents/middleware/types.py``，逐字：「Synchronous implementation of
wrap_tool_call is not available…」），因此不存在「同步上下文悄悄绕过门禁」的缺口 ——
它是**响亮地失败**，不是安静地放过。

── 与上游的两处**刻意不同**（不得照抄上游）──────────────────────────────────

1. **判定顺序**：上游 ``createOwnershipGate`` 的第①步是「先让下游表态：``next()`` 已 deny
   就不插嘴」。那个 ``next()`` 在 DSH 宿主里是**决策链**；而 LangGraph 交给中间件的
   ``handler`` 是**执行器**（调用它 = 真的写盘）⇒ **不能**照搬该顺序。本实现改为
   **先判定、后委托**：只有放行时才调用 ``handler``，拒绝时**根本不调用**。
   「更严格者优先」仍然成立 —— 本门禁的拒绝是短路，内层中间件的拒绝发生在我们委托之后，
   两者只会叠加、不会互相覆盖。
2. **工具名要剥命名空间**：Octop 的插件工具名形如 ``<prefix>/<tool>``
   （``src/octop/infra/agents/plugins/manager.py · return f"{prefix}/{cleaned}"``），而
   harness 自带的同类判定一律先剥前缀（`.venv/.../octop_harness/middleware/filesystem_guard.py
   · _tool_base_name @ 51`、`conversation_mode.py @ 118`、`skill_filter.py @ 47`）。
   若这里用精确匹配，插件暴露的 ``<prefix>/write_file`` 会**绕过归属门禁却照样写盘**。
   故取 harness 同款口径：先剥前缀再查表。
"""

from __future__ import annotations

import logging
import os
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

from octop.infra.agents.teams.artifacts import (
    normalize_owner_role,
    owner_violation,
    run_scoped_target,
)
from octop.infra.agents.teams.pipeline import TERMINAL_RUN_STATUSES

logger = logging.getLogger(__name__)

#: 本门禁只认这两个工具的 ``file_path``；其余工具（**含 ``execute_shell_command``**）一律放行
#: —— 见模块 docstring 的「诚实边界」。与上游 ``lib/interception.js · WRITE_TOOLS @ 24``
#: （``new Set(['write', 'edit'])``）同口径，工具名按 Octop 命名。
#:
#: ``append_file`` 曾在 harness 的 ``bootstrap.py · _WRITE_TOOLS`` 里出现，但**实测它不是已
#: 注册工具**（`src/octop/infra/agents/settings/tool_catalog.py` 里没有它）⇒ 不列入；
#: 若将来注册，必须同步扩这张表，否则它成为绕过面。
_WRITE_TOOLS: frozenset[str] = frozenset({"write_file", "edit_file"})

#: 事件名 —— **只此一份**（`PLAN.md · 事件名词表`），不得另造同义事件名。
#: 注意它们**不是** ``ErrorCode``：工具通道的拒绝产出 ``ToolMessage(status="error")``，
#: **不产** ``TEAM_ARTIFACT_OWNERSHIP_DENIED``（那个码归 HTTP 服务层）。
EVENT_OWNERSHIP_DENIED = "team.artifact.ownership_denied"
EVENT_OWNERSHIP_DEGRADED = "team.artifact.ownership_degraded"


def _noop_event(_event: str, _payload: Mapping[str, Any]) -> None:
    """默认观测端：什么都不做（门禁在无观测接线时也必须可用）。"""


@dataclass(frozen=True, slots=True)
class OwnershipGateDeps:
    """门禁的**注入依赖**（上游 ``createOwnershipGate(deps)`` 的 Octop 形态）。

    四个查询全是 callable ⇒ 本模块不 import repos、可无 DB 单测；接线方（T-20 的中间件装配）
    负责把它们接到 run 仓储 / 角色查询 / 工作区存在性上。
    """

    team_root_for: Callable[[str], str | None]
    """``(raw_path) -> <run_root>``。返回 ``None`` = 该目标不在团队 run 目录里 ⇒ 放行。"""

    run_status_for: Callable[[str], str | None]
    """``(run_id) -> status``。``None`` = 查不到 ⇒ 按**非终态**处理，继续判定。"""

    role_for: Callable[[str], str | None]
    """``(run_id) -> 写者角色``。认不出请返回 ``None`` / 空串 ⇒ **fail-open 放行**。"""

    exists_for: Callable[[str], bool | None]
    """``(abs_path) -> 是否存在``。``None`` = 查不到 ⇒ **放行 + 留痕**（门禁降级必须可见）。"""

    on_event: Callable[[str, Mapping[str, Any]], None] = _noop_event
    """``(event_name, payload)``。观测失败**绝不影响**工具调用（内部已包 try/except）。"""


def _tool_base_name(name: str) -> str:
    """剥掉插件命名空间前缀（``<prefix>/write_file`` → ``write_file``）。

    与 `.venv/.../octop_harness/middleware/filesystem_guard.py · _tool_base_name @ 51` 逐字同构。
    """
    trimmed = name.strip()
    slash = trimmed.rfind("/")
    return trimmed[slash + 1 :] if slash >= 0 else trimmed


def _file_path_from_args(params: Mapping[str, Any]) -> str:
    """取写目标路径；与 harness ``_path_from_tool_args`` 同口径（``file_path`` 优先）。"""
    for key in ("file_path", "path"):
        raw = params.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return ""


class TeamArtifactOwnershipMiddleware(AgentMiddleware[Any, Any]):
    """R1 工件归属硬门禁（``write``/``edit`` 通道，**写盘之前**拦）。"""

    def __init__(self, *, deps: OwnershipGateDeps) -> None:
        super().__init__()
        self._deps = deps

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        tool_call = request.tool_call
        try:
            reason = self._violation(request)
        except Exception:
            # **门禁绝不允许成为工具故障源**（上游真实事故：post-execute 签名写错曾让全工具
            # 瘫痪）⇒ 任何异常一律放行 + 留痕。
            logger.warning(
                "team artifact ownership gate errored; allowing tool call",
                exc_info=True,
            )
            self._emit(
                EVENT_OWNERSHIP_DEGRADED,
                {"why": "gate-error", "tool": str(tool_call.get("name") or "")},
            )
            return await handler(request)

        if reason is None:
            return await handler(request)

        # 拒绝路径：**不调用 handler** —— 写盘之前拦，因此真拦得住。
        logger.info("team artifact ownership denied: %s", reason)
        return ToolMessage(
            content=reason,
            tool_call_id=str(tool_call.get("id") or ""),
            status="error",
        )

    # ── 内部 ────────────────────────────────────────────────────────────────

    def _violation(self, request: ToolCallRequest) -> str | None:
        """返回拒绝理由；``None`` = 放行。**纯判定，不碰 handler。**"""
        tool_call = request.tool_call
        if _tool_base_name(str(tool_call.get("name") or "")) not in _WRITE_TOOLS:
            return None

        params = tool_call.get("args") or {}
        if not isinstance(params, dict):
            params = {}
        raw_path = _file_path_from_args(params)
        if not raw_path:
            return None

        team_root = self._deps.team_root_for(raw_path)
        if not team_root:
            return None

        # Same-form requirement: ``run_scoped_target`` compares lexically, so a
        # workspace-relative path (the repo's normal form) never matches an absolute
        # root. Resolve it against the root's parent -- for a host run that parent *is*
        # the workspace (``<workspace>/<RUN_DIR_PREFIX>``), and an explicit run's root is
        # absolute, so a relative path could not have resolved to it in the first place.
        resolved = (
            raw_path
            if os.path.isabs(raw_path)
            else os.path.join(os.path.dirname(team_root), raw_path)
        )
        target = run_scoped_target(resolved, team_root)
        if target is None or not target.base:
            return None

        status = str(self._deps.run_status_for(target.run_id) or "")
        if status in TERMINAL_RUN_STATUSES:
            # 已终止的 run 放行：冻结的历史工件不该在写侧拦（与上游同一理由）。
            return None

        exists = self._deps.exists_for(target.path)
        if not isinstance(exists, bool):
            self._emit(
                EVENT_OWNERSHIP_DEGRADED,
                {
                    "why": "existence-unknown",
                    "runId": target.run_id,
                    "base": target.base,
                    "abs": target.path,
                },
            )
            return None

        role = normalize_owner_role(self._deps.role_for(target.run_id))
        if not role:
            if exists:
                self._emit(
                    EVENT_OWNERSHIP_DEGRADED,
                    {"why": "role-unknown", "runId": target.run_id, "base": target.base},
                )
            return None

        reason = owner_violation(role=role, base=target.base, exists=exists)
        if reason is not None:
            self._emit(
                EVENT_OWNERSHIP_DENIED,
                {
                    "runId": target.run_id,
                    "base": target.base,
                    "role": role,
                    "abs": target.path,
                },
            )
        return reason

    def _emit(self, event: str, payload: Mapping[str, Any]) -> None:
        """上报可观测事件；**观测失败不影响工具**。"""
        try:
            self._deps.on_event(event, payload)
        except Exception:
            logger.debug("ownership gate on_event failed", exc_info=True)


__all__ = [
    "EVENT_OWNERSHIP_DEGRADED",
    "EVENT_OWNERSHIP_DENIED",
    "OwnershipGateDeps",
    "TeamArtifactOwnershipMiddleware",
]
