"""T-68 ④ 机检：**判词只有一个入口** —— `api/` 层不得直接写判词。

## 这条判据防的是什么

`op:"report"` 曾经这样落地（T-68 修复前）::

    service.report(run_id, task_id, attempt_id=..., verdict=body.verdict, ...)

而 `report()` 是 ``verdict()`` **内部**用的那个写手（`run_service.py:902` 自己也调它）⇒
路由绕过了外层的两道门 **G12 / G13**，并顺手丢掉了请求里的 `findings`
（`report()` 没有这个形参）⇒ G16 的前提在 HTTP 面上永远建立不起来。

修法是**条件委托**：带 `verdict` 的 report 走 `service.verdict(...)`，不带 verdict 的进度报告
逐字不变。**但"接线正确"这件事不能只靠"我查过了"** —— 本 run 的教训是：结论必须机检。

## 判据

* 扫 ``src/octop/api/**``，任何 ``.report(...)`` **带 ``verdict=`` 关键字** ⇒ 红；
* **不扫** `infra/`：``run_service.py`` 里 ``fail()`` 自己那次
  ``self.report(..., verdict="reject")`` 是**服务自身的失败语义**，不是审阅判词；把它一起禁掉
  等于要求给 `fail` 开私门或重构（T-68 设计答复里已论证：那才是更大的改动面）。

⇒ 于是"**判词只有一个入口**"从"我查过"变成"**忘了就红**"（与 T-62 同源）。
"""

from __future__ import annotations

import ast
from pathlib import Path

_SRC = Path(__file__).resolve().parents[3] / "src" / "octop"
_API = _SRC / "api"
_ROUTE = "api/routers/team_runs.py"
_VERDICT_KEYWORD = "verdict"


def _writes_a_verdict(call: ast.Call) -> bool:
    """这次调用是否**真的写了一个判词**。

    显式 ``verdict=None`` **不算**：它是"本次不写判词"（进度报告分支为了与改动前逐字一致
    仍然显式传 None —— 省略该参数与传 None 在 ``report()`` 里语义不同，前者不动列）。
    """
    for kw in call.keywords:
        if kw.arg != _VERDICT_KEYWORD:
            continue
        # 三个分支都在：① 不是 verdict= ⇒ 继续找；② verdict=None 字面量 ⇒ 不算写判词；
        # ③ verdict=<真值> ⇒ 算。写成 `not <条件>` 而不是 if/return 嵌套（SIM103），语义不变。
        is_none_literal = isinstance(kw.value, ast.Constant) and kw.value.value is None
        return not is_none_literal
    return False


def _direct_verdict_writes(tree: ast.AST) -> list[int]:
    """``<x>.report(..., verdict="pass"|"needs_revision"|...)`` 的行号 —— 直写判词的那条路。"""
    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr != "report":
            continue
        if _writes_a_verdict(node):
            lines.append(node.lineno)
    return lines


def _scan_api() -> dict[str, list[int]]:
    found: dict[str, list[int]] = {}
    for path in sorted(_API.rglob("*.py")):
        lines = _direct_verdict_writes(ast.parse(path.read_text(encoding="utf-8")))
        if lines:
            found[path.relative_to(_SRC).as_posix()] = lines
    return found


def _report_calls(tree: ast.AST) -> int:
    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "report"
    )


# ---------------------------------------------------------------------------
# 用例
# ---------------------------------------------------------------------------


def test_detector_discriminates() -> None:
    """判据先自证：认得出"直写判词"，且不会把合法的两种形态当成它。"""
    direct = ast.parse('service.report(run_id, tid, attempt_id=a, verdict="pass", user=u)\n')
    via_gate = ast.parse('service.verdict(run_id, tid, attempt_id=a, verdict="pass", user=u)\n')
    plain_report = ast.parse(
        "service.report(run_id, tid, attempt_id=a, changed_paths=[], user=u)\n"
    )
    explicit_none = ast.parse("service.report(run_id, tid, attempt_id=a, verdict=None, user=u)\n")
    unrelated = ast.parse("finding_repo.report(x, verdict='pass')\n")

    assert _direct_verdict_writes(direct) == [1]
    assert _direct_verdict_writes(via_gate) == [], "走 verdict() 的是唯一合法形态"
    assert _direct_verdict_writes(plain_report) == [], "不带 verdict 的进度报告不算"
    assert _direct_verdict_writes(explicit_none) == [], "显式 verdict=None 是'不写判词'"
    assert _direct_verdict_writes(unrelated) == [1], "锚在 `.report(...)` 形态上，不看接收者是谁"


def test_the_scan_has_something_to_look_at() -> None:
    """防"检测器扫了个空"：`api/` 里确实有 `.report(...)` 调用，锚点不是摆设。"""
    total = sum(
        _report_calls(ast.parse(p.read_text(encoding="utf-8"))) for p in sorted(_API.rglob("*.py"))
    )

    assert total >= 1, "`api/` 里一个 `.report(` 都没有了？检测器可能已经失效"
    assert _report_calls(ast.parse((_SRC / _ROUTE).read_text(encoding="utf-8"))) >= 1


def test_no_direct_verdict_write_in_the_api_layer() -> None:
    """★ 核心：`api/` 层不得出现直写判词的调用（新增一处 ⇒ 红）。"""
    offenders = _scan_api()

    assert offenders == {}, (
        "这些地方在 `api/` 层直接写判词，绕过了 G12/G13 并会丢掉 findings："
        f"{offenders}。判词必须经 `service.verdict(...)`（唯一实现）—— "
        '带 verdict 的 report 走条件委托，见 `op == "report"` 分支。'
    )


def test_the_route_reaches_that_single_writer() -> None:
    """反向：路由必须真的**够得到**那个唯一写手（否则门又回到不可达）。"""
    tree = ast.parse((_SRC / _ROUTE).read_text(encoding="utf-8"))
    verdict_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "verdict"
    ]

    assert verdict_calls, f"{_ROUTE} 不再调用 `verdict()` ⇒ G12/G13 又不可达了"
    assert all(any(kw.arg == _VERDICT_KEYWORD for kw in call.keywords) for call in verdict_calls), (
        "调用 verdict() 却不传 verdict？"
    )
