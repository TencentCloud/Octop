"""T-69 —— `role` 未认出这道**门**的位置与分层（机检）。

裁定 (a) 的实现落在 **服务层**（`TeamRunService.write_artifact`），不是纯函数
`artifacts.owner_violation` 里 —— 因为后者是**工具通道**共用的判定：那条通道的 `role` 来自
**运行时的角色指派**（不是调用方声明），给它 fail-open 的语义是对的（模块 docstring 逐字：
"认不出请返回 None / 空串 ⇒ fail-open 放行"）。**HTTP 面的 `role` 是调用方声明**（AM-31）
⇒ 门必须加在**服务层**、且加在 `role` 的**全部分叉点之前**：

* `owner_violation(role=…)` —— 判归属；
* `_owner_role_for(name, role)` —— 写索引行的 `owner_role`（T-45）。

本文件把这两件事钉住：① 门在两者**之前**（机器判序）；② 纯函数仍然 fail-open（分层不变）。
"""

from __future__ import annotations

import ast
from pathlib import Path

_SRC = Path(__file__).resolve().parents[3] / "src" / "octop"
_RUN_SERVICE = "infra/agents/teams/run_service.py"
_GATE_CODE = "TEAM_ROLE_UNKNOWN"
_CONSUMERS = ("owner_violation", "_owner_role_for")


def _write_artifact_body(tree: ast.AST) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "write_artifact":
            return node
    raise AssertionError(f"{_RUN_SERVICE} 里找不到 write_artifact")


def _first_line_of(body: ast.AST, predicate) -> int | None:
    lines = [node.lineno for node in ast.walk(body) if predicate(node)]
    return min(lines) if lines else None


def _gate_line(body: ast.AST) -> int | None:
    return _first_line_of(
        body,
        lambda n: (
            isinstance(n, ast.Attribute)
            and n.attr == _GATE_CODE
            and isinstance(n.value, ast.Name)
            and n.value.id == "ErrorCode"
        ),
    )


def _consumer_line(body: ast.AST, name: str) -> int | None:
    return _first_line_of(
        body,
        lambda n: (
            isinstance(n, ast.Call)
            and (
                (isinstance(n.func, ast.Name) and n.func.id == name)
                or (isinstance(n.func, ast.Attribute) and n.func.attr == name)
            )
        ),
    )


def _order_violations(source: str) -> list[str]:
    """哪几个消费点跑在门**之前**（空 = 合规）。"""
    body = _write_artifact_body(ast.parse(source))
    gate = _gate_line(body)
    if gate is None:
        return [f"{_GATE_CODE} 门不见了"]
    bad = []
    for name in _CONSUMERS:
        line = _consumer_line(body, name)
        if line is not None and line < gate:
            bad.append(f"{name}@{line} 早于门@{gate}")
    return bad


def test_detector_discriminates() -> None:
    """判据先自证：把门挪到消费点**之后**，它必须报出来。"""
    after = """
def write_artifact(self, run_id, *, role):
    violation = owner_violation(role=role, base="SPEC.md", exists=True)
    if violation is None:
        if exists and not normalize_owner_role(role):
            raise OctopError(ErrorCode.TEAM_ROLE_UNKNOWN, "x")
    owner_role = _owner_role_for("SPEC.md", role)
"""
    before = """
def write_artifact(self, run_id, *, role):
    if exists and not normalize_owner_role(role):
        raise OctopError(ErrorCode.TEAM_ROLE_UNKNOWN, "x")
    violation = owner_violation(role=role, base="SPEC.md", exists=True)
    owner_role = _owner_role_for("SPEC.md", role)
"""

    bad = _order_violations(after)
    assert len(bad) == 1 and bad[0].startswith("owner_violation@"), (
        f"检测器认不出'门排错了'，那它就是绿而不生效：{bad}"
    )
    assert _order_violations(before) == []


def test_the_gate_sits_before_every_consumer_of_role() -> None:
    """★ 核心：`TEAM_ROLE_UNKNOWN` 门必须在 `owner_violation` 与 `_owner_role_for` **之前**。"""
    source = (_SRC / _RUN_SERVICE).read_text(encoding="utf-8")

    assert _order_violations(source) == [], (
        "同一个 `role` 有多个消费点 ⇒ 门要加在**分叉之前**（否则未认出的角色会从另一个口子漏出去）"
    )
    body = _write_artifact_body(ast.parse(source))
    assert _gate_line(body) is not None, "门没了：HTTP 面又能用未认出的角色覆写运行时工件"


def test_owner_violation_keeps_its_fail_open_contract() -> None:
    """分层不变：**纯函数**仍按文档 fail-open（工具通道的 `role` 不是调用方声明）。

    ⇒ 修的是**服务层**那一跳；若哪天这里改成拒绝，说明有人把两层的语义混了
    （那会打到工具通道——那里的角色来自运行时指派）。
    """
    from octop.infra.agents.teams.artifacts import owner_violation

    assert owner_violation(role="ghost", base="SPEC.md", exists=True) is None
    assert owner_violation(role="", base="STATE.json", exists=True) is None
