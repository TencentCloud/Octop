"""T-48 —— agent 归属判定收口成 infra 唯一真源的**等价性证明**。

这条重构的唯一可接受结果是「**行为零变化**」，所以本文件不是"再测一遍旧断言"，而是：

① **差分对照**：把搬迁**之前**的实现（``api/common/agent.py`` 的旧函数体）逐字留成本文件的
   oracle，对**同一张输入矩阵**逐一比较新实现与旧实现的**结论**（抛错与否、错误码、返回值）；
② **转调证明**：``api/common/agent`` 暴露的那些谓词必须是 ``infra/agents/access`` 里的
   **同一个对象**（``is``）—— 是转发，不是又抄了一份；
③ **变异证明**：把 infra 侧谓词**改宽**（加上 ``is_shared`` 旁路）⇒ 上面的差分必须变红
   —— 证明它真的在把守，而不是"碰巧两边一样"；
④ **§5 结构护栏**：``infra/`` 不得 import ``api/``（AST 查真实 import 语句）。
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from octop.api.common import agent as api_agent
from octop.infra.agents import access
from octop.infra.agents.teams import service as team_service
from octop.infra.errors import ErrorCode, OctopError

# ── ① 搬迁前的实现（**逐字**留作 oracle，不要"顺手更新"它）────────────────────


def _old_agent_is_shared(row: Any) -> bool:
    return int(getattr(row, "is_shared", 0) or 0) == 1


def _old_user_owns_agent(row: Any, user: Any) -> bool:
    return row.user_id is not None and row.user_id == user.id


def _old_assert_agent_owner(row: Any, user: Any) -> None:
    if user.is_admin:
        return
    if row.user_id is None or row.user_id != user.id:
        raise OctopError(ErrorCode.FORBIDDEN, "agent not owned by user")


def _old_user_may_access(row: Any, user: Any) -> bool:
    if user.is_admin:
        return True
    if row.user_id is not None and row.user_id == user.id:
        return True
    return bool(_old_agent_is_shared(row))


def _old_assert_agent_access_row(row: Any, user: Any) -> None:
    if not _old_user_may_access(row, user):
        raise OctopError(ErrorCode.FORBIDDEN, "agent not accessible to user")


def _outcome(fn: Any, *args: Any) -> tuple[Any, ...]:
    """把"抛错 / 返回值"归一成一个可比较的元组。"""
    try:
        value = fn(*args)
    except OctopError as exc:
        return ("raise", exc.code, exc.message)
    return ("return", value)


# 差分骨架统一按 ``(row, user)`` 调用；``agent_is_shared`` 只吃 ``row``，故套一层适配
# （适配器只丢参数，不改语义）。
def _new_is_shared(row: Any, _user: Any) -> bool:
    return access.agent_is_shared(row)


def _old_is_shared(row: Any, _user: Any) -> bool:
    return _old_agent_is_shared(row)


# 输入矩阵：owner / 非 owner / admin（本人与非本人）/ 未知属主(NULL) / 已共享 / 未共享 /
# 缺 is_shared 属性。
ROWS: dict[str, Any] = {
    "本人所有": SimpleNamespace(user_id=1),
    "他人所有": SimpleNamespace(user_id=1),
    "无属主(NULL)": SimpleNamespace(user_id=None),
    "本人所有·已共享": SimpleNamespace(user_id=1, is_shared=1),
    "他人所有·已共享": SimpleNamespace(user_id=1, is_shared=1),
    "无属主·已共享": SimpleNamespace(user_id=None, is_shared=1),
    "他人所有·显式未共享": SimpleNamespace(user_id=1, is_shared=0),
    "缺 is_shared 属性": SimpleNamespace(user_id=1),
}
USERS: dict[str, Any] = {
    "本人": SimpleNamespace(id=1, is_admin=False),
    "他人": SimpleNamespace(id=2, is_admin=False),
    "admin(本人)": SimpleNamespace(id=1, is_admin=True),
    "admin(他人)": SimpleNamespace(id=99, is_admin=True),
}

CASES = [(rk, uk) for rk in ROWS for uk in USERS]


def _diff(name: str, new: Any, old: Any) -> None:
    """对整张矩阵比较新旧两条路径；任一格不同即失败并指出是哪一格。"""
    for rk, uk in CASES:
        row, user = ROWS[rk], USERS[uk]
        got, want = _outcome(new, row, user), _outcome(old, row, user)
        assert got == want, f"{name} 在 [{rk} × {uk}] 上分叉：新={got!r} 旧={want!r}"


@pytest.mark.parametrize(
    ("name", "new", "old"),
    [
        ("agent_is_shared", _new_is_shared, _old_is_shared),
        ("user_owns_agent", access.user_owns_agent, _old_user_owns_agent),
        ("assert_agent_owner", access.assert_agent_owner, _old_assert_agent_owner),
        (
            "user_may_access_agent",
            access.user_may_access_agent,
            _old_user_may_access,
        ),
        (
            "assert_agent_access_row",
            access.assert_agent_access_row,
            _old_assert_agent_access_row,
        ),
    ],
)
def test_new_predicate_agrees_with_the_pre_move_implementation(
    name: str, new: Any, old: Any
) -> None:
    """① 逐情形对照：owner / 非 owner / admin / NULL 属主 / 共享 —— 结论必须逐一相同。"""
    _diff(name, new, old)


# ── ② 转调证明：api 侧是**同一个对象**，不是第二份实现 ──────────────────────


@pytest.mark.parametrize(
    "name",
    [
        "agent_is_shared",
        "user_owns_agent",
        "assert_agent_owner",
        "user_may_access_agent",
        "assert_agent_access_row",
    ],
)
def test_api_module_reexports_the_infra_objects(name: str) -> None:
    """② ``api/common/agent`` 只是转发 ⇒ 必须是同一个函数对象。"""
    assert getattr(api_agent, name) is getattr(access, name), (
        f"{name} 在 api 侧不是同一个对象 —— 说明又抄了一份实现"
    )


def test_team_service_member_rule_forwards_to_the_same_predicate() -> None:
    """② 团队编制那条**更宽**的规则（admin|本人|is_shared）也只剩一份实现。

    它曾被误当成 :func:`assert_agent_owner` 的等价物使用；实际它与
    :func:`user_may_access_agent` 同语义、与 ``assert_agent_owner`` **不同**
    （多了 shared 旁路）。这里用对象同一性钉死"没有第二份"。
    """
    assert team_service._user_may_use_member is access.user_may_access_agent


def test_owner_rule_is_strictly_narrower_than_access_rule() -> None:
    """两条规则的关系必须保持：**共享**只影响"可访问"，不影响"可改写"。"""
    shared_other = SimpleNamespace(user_id=1, is_shared=1)
    other = SimpleNamespace(id=2, is_admin=False)

    assert access.user_may_access_agent(shared_other, other) is True
    with pytest.raises(OctopError):
        access.assert_agent_owner(shared_other, other)


# ── ③ 变异证明：改宽 ⇒ 差分必须红 ───────────────────────────────────────────


def _widened_assert_agent_owner(row: Any, user: Any) -> None:
    """变异体：给归属判定加上 ``is_shared`` 旁路（= 放宽写权限）。"""
    if user.is_admin:
        return
    if row.user_id is not None and row.user_id == user.id:
        return
    if _old_agent_is_shared(row):  # ← 变异：共享 agent 也允许改写
        return
    raise OctopError(ErrorCode.FORBIDDEN, "agent not owned by user")


def test_mutation_widening_the_owner_rule_is_caught(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """③ 把 infra 侧谓词改宽 ⇒ ① 的差分必须立刻变红（否则那条差分没有判别力）。

    先确认**未变异**时差分是绿的 —— 否则下面的 ``pytest.raises`` 是假阳性。
    """
    _diff("assert_agent_owner", access.assert_agent_owner, _old_assert_agent_owner)

    monkeypatch.setattr(access, "assert_agent_owner", _widened_assert_agent_owner)
    with pytest.raises(AssertionError, match="分叉"):
        _diff("assert_agent_owner", access.assert_agent_owner, _old_assert_agent_owner)


def test_widened_rule_would_actually_grant_write_access() -> None:
    """变异体确实是"更宽"的那个方向 —— 不是换个写法而已。"""
    shared_other = SimpleNamespace(user_id=1, is_shared=1)
    other = SimpleNamespace(id=2, is_admin=False)

    with pytest.raises(OctopError):
        access.assert_agent_owner(shared_other, other)
    _widened_assert_agent_owner(shared_other, other)  # 不抛 —— 这就是被放宽的那一格


# ── ④ §5 结构护栏 + 装载器分支（未知 agent / agent 不存在 / as_user）─────────


def test_infra_module_does_not_import_the_api_layer() -> None:
    """④ ``AGENTS.md §5``：``infra/`` 不得 import ``api/``。

    用 **AST** 查真实 import 语句（不去源码里找 ``api`` 这个词：docstring 里就写着
    ``api/common/agent.py``，字面匹配会假红）。
    """
    tree = ast.parse(Path(access.__file__).read_text(encoding="utf-8"))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.append(node.module)

    assert modules, "AST 没解析出 import —— 检查本身失效了（假绿灯）"
    offenders = [m for m in modules if m.startswith("octop.api") or ".api." in m]
    assert offenders == [], f"infra 侧不得依赖 api 层：{offenders}"


def _server(*, row: Any, target_user: Any = None) -> Any:
    return SimpleNamespace(
        app_runtime=SimpleNamespace(agent_registry=SimpleNamespace(get_row=lambda _aid: row)),
        user_manager=SimpleNamespace(get_by_id=lambda _uid: target_user),
    )


def test_unknown_agent_is_agent_not_found() -> None:
    """未知 agent / agent 不存在 ⇒ 仍是 ``AGENT_NOT_FOUND``（装载器路径，行为不变）。"""
    user = SimpleNamespace(id=1, is_admin=False)
    with pytest.raises(OctopError) as ei:
        api_agent.require_agent_row("missing", user=user, as_user=None, server=_server(row=None))
    assert ei.value.code is ErrorCode.AGENT_NOT_FOUND


def test_loader_owner_branch_and_as_user_branches() -> None:
    owner = SimpleNamespace(id=1, is_admin=False)
    other = SimpleNamespace(id=2, is_admin=False)
    admin = SimpleNamespace(id=99, is_admin=True)
    row = SimpleNamespace(user_id=1, is_shared=0)

    # 本人 ⇒ 通过
    api_agent.require_agent_row("a", user=owner, as_user=None, server=_server(row=row))
    # 非本人 ⇒ FORBIDDEN
    with pytest.raises(OctopError) as ei:
        api_agent.require_agent_row("a", user=other, as_user=None, server=_server(row=row))
    assert ei.value.code is ErrorCode.FORBIDDEN
    # as_user 需要 admin（非 admin 传 as_user ⇒ FORBIDDEN）
    with pytest.raises(OctopError) as ei:
        api_agent.require_agent_row(
            "a", user=other, as_user=1, server=_server(row=row, target_user=owner)
        )
    assert ei.value.code is ErrorCode.FORBIDDEN
    # admin + as_user 指向该 agent 的属主 ⇒ 通过
    api_agent.require_agent_row(
        "a", user=admin, as_user=1, server=_server(row=row, target_user=owner)
    )
    # admin + as_user 指向别人的 agent ⇒ FORBIDDEN
    with pytest.raises(OctopError) as ei:
        api_agent.require_agent_row(
            "a", user=admin, as_user=2, server=_server(row=row, target_user=other)
        )
    assert ei.value.code is ErrorCode.FORBIDDEN
    # as_user 指向不存在的用户 ⇒ NOT_FOUND
    with pytest.raises(OctopError) as ei:
        api_agent.require_agent_row(
            "a", user=admin, as_user=7, server=_server(row=row, target_user=None)
        )
    assert ei.value.code is ErrorCode.NOT_FOUND
