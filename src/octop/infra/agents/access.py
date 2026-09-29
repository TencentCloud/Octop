"""Agent 归属 / 可访问性判定 —— **唯一真源**（§5 允许 infra 侧入口直接使用）。

── 这条规则原本住哪、为什么搬到这里 ─────────────────────────────────────────

它原本**只**住在 ``api/common/agent.py``（``assert_agent_owner`` 等，HTTP 层）。而
``AGENTS.md §5`` 硬禁 ``infra/`` → ``api/`` ⇒ **infra 侧的任何入口都拿不到它**，于是每个
新入口只剩两条路：**复制一份**（= 第二套权限模型，而且往往更宽）或**注入一个 callable**。

这不是假想的代价 —— ``researcher`` 在 T-19（``/team`` slash 面）逐条取证到一条真实的
**提权路径**：

* HTTP 面建 run 的授权**只有** ``api/routers/team_runs.py · assert_agent_owner(_team_row(…), user)``
  （同文件模块 docstring 逐字：「admin bypass included, **no second authorisation**」），
  它住在 api 层，共 4 处调用（``@377`` / ``@498`` / ``@531`` / ``@537``）；
* 而 ``TeamRunService.create``（``infra/agents/teams/run_service.py @435``）**不校验
  user↔agent 归属** —— 它只用 ``owner_user=user`` 把调用者**记成** owner；服务内唯一的用户
  判定是**项目级**的（``_RunActor @172-178`` 逐字：「are authorized as the **run's creator**
  … No admin bypass, no second permission model」）；
* ⇒ **任何 IM 会话用户，只要会话绑的是团队 host（或共享 / 他人的 team agent），就能经
  ``/team <goal>`` 建 run，而 HTTP 同一动作会 403。**

把谓词落到 infra 之后，「复制 or 注入」的困境**永久消失**：``infra/`` 侧任何入口直接
``from octop.infra.agents.access import assert_agent_owner`` 即可。
``api/common/agent.py`` 现在只是**转调 + 再导出**，行为逐字不变（转调前后逐情形对照见
``tests/unit/agents/test_agent_access_source.py``）。

为什么放在 ``infra/agents/``：§5 把 agent 注册表 / 生命周期 / 安全归 ``infra/agents/``，
而这条规则问的正是「**这个 agent 行归谁**」—— 它既不是用户域（``infra/users/`` 管的是
账号、角色、口令），也不是 HTTP 适配层的事。

── 谁都不能再实现第二份（**本节是重点**）──────────────────────────────────────

* **归属**（admin 旁路 + 本人）**只有** :func:`user_owns_agent` / :func:`assert_agent_owner`；
* **可访问**（admin | 本人 | 共享）**只有** :func:`user_may_access_agent` /
  :func:`assert_agent_access_row`；
* 另有一条**更宽**的规则曾被当成等价物使用：``teams/service.py`` 的 ``_user_may_use_member``
  （admin | 本人 | ``is_shared``）。它与 :func:`user_may_access_agent` **恰好同语义**，
  因此现在直接**转调**它，而不是各留一份 —— 但注意它与 :func:`assert_agent_owner`
  **不同**（多了 shared 旁路）：两者用途不同，「能不能用这个专家当团队成员」
  ≠「能不能改这个 agent」。

⚠️ **不得**把 shared 旁路加进 :func:`assert_agent_owner`：那是**放宽写权限** ——
任何能看到某个共享 agent 的用户都将能改它。变宽即回归，用例会红（见
``tests/unit/agents/test_agent_access_source.py`` 的变异用例）。

── 入参形态（为什么按 ``User`` 而不是 ``UserRow``）─────────────────────────────

``UserRow``（``infra/db/repos/users.py``）**没有** ``is_admin`` —— 它只有 ``role``；
``is_admin`` 是 ``infra/users/identity.py · User.is_admin @29-31`` 的**派生属性**
（``role == Role.ADMIN``）。所以谓词按**结构**接收「有 ``id`` 与 ``is_admin`` 的对象」
（:class:`AgentOwnerSubject`）；调用方用 ``UserManager.get_by_id``（返回 ``identity.User``）
取得即可。``api`` 侧已有这个对象，因此转调不需要任何适配。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from octop.infra.db.repos.agents import AgentRow
from octop.infra.errors import ErrorCode, OctopError


@runtime_checkable
class AgentOwnerSubject(Protocol):
    """判定所需的**最小**用户面。

    ``infra/users/identity.py · User`` 天然满足（``id`` 是字段，``is_admin`` 是派生属性）。
    ``UserRow`` **不**满足 —— 它没有 ``is_admin``，这正是本模块不接收它的原因。
    """

    @property
    def id(self) -> int: ...

    @property
    def is_admin(self) -> bool: ...


def agent_is_shared(row: AgentRow) -> bool:
    """该 agent 行是否被显式共享给其他用户（``is_shared = 1``）。"""
    return int(getattr(row, "is_shared", 0) or 0) == 1


def user_owns_agent(row: AgentRow, user: AgentOwnerSubject) -> bool:
    """``user`` 是不是这个行的属主。

    **不含 admin 旁路** —— 这是"是不是我的"这个原始问题，用在不能被软化的地方。
    """
    return row.user_id is not None and row.user_id == user.id


def assert_agent_owner(row: AgentRow, user: AgentOwnerSubject) -> None:
    """用户无权**改动**这个 agent 行时抛 ``FORBIDDEN``（**admin 旁路保留**）。

    **这是该规则唯一的实现。** 它原本住在 ``api/common/agent.py``；搬迁原因与它顺带
    关掉的那条提权路径见模块 docstring。

    它**刻意比** :func:`user_may_access_agent` **窄**：**不**认 ``is_shared``。
    放宽它 = 让所有能看见某个共享 agent 的用户都能改它 —— 不要这么做。
    """
    if user.is_admin:
        return
    if row.user_id is None or row.user_id != user.id:
        raise OctopError(ErrorCode.FORBIDDEN, "agent not owned by user")


def user_may_access_agent(row: AgentRow, user: AgentOwnerSubject) -> bool:
    """用户能否**接触到**该 agent：admin ｜ 本人 ｜ 已共享。"""
    if user.is_admin:
        return True
    if row.user_id is not None and row.user_id == user.id:
        return True
    return agent_is_shared(row)


def assert_agent_access_row(row: AgentRow, user: AgentOwnerSubject) -> None:
    """用户接触不到该 agent 行时抛 ``FORBIDDEN``。"""
    if not user_may_access_agent(row, user):
        raise OctopError(ErrorCode.FORBIDDEN, "agent not accessible to user")


__all__ = [
    "AgentOwnerSubject",
    "agent_is_shared",
    "assert_agent_access_row",
    "assert_agent_owner",
    "user_may_access_agent",
    "user_owns_agent",
]
