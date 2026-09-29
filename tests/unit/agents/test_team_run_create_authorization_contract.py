"""T-62 ② — 把"每个新入口都要记得注入授权"变成"**忘了就红**"。

风险原文（`sec`，T-27-4）：``TeamRunService.create`` 自身**不校验** agent 归属
（``infra/agents/teams/run_service.py`` 的 ``create`` 全文没有属主检查）⇒ 建 run 的授权
**完全**取决于每个入口是否记得注入谓词。本 run 已经在 ``/team`` slash 面实测到过这条
路径的代价：T-48 的 docstring 逐字记录了"HTTP 面 403、而 ``/team`` 能建"的提权差。

**本用例的判据**：凡在 ``src/octop/infra/`` 里调用 ``TeamRunService.create(...)`` 的模块，
必须引用 ``infra/agents/access`` 的谓词（``octop.infra.agents.access`` 出现在其 import 里）。
不满足的模块**必须在**下面的 ``_GRANDFATHERED`` 里**逐条写明理由** ——
⇒ **新调用点若不引用、又没登记 ⇒ 红**（登记本身是一次显式、可被 review 的动作）。

**范围**：实现模块 ``infra/agents/teams/run_service.py`` 自身不算"调用方"（它内部的
``self._runs.create(...)`` 是仓储写）；**仓储直插**（绕开 service 建 run 行）是另一条更低层的
路径，本用例不覆盖 —— 见模块末尾的"已知边界"。

⚠️ **诚实标注**：``_GRANDFATHERED`` **不是**"这些模块是合规的"，它是"当前已知的例外"。
条目必须**仍然存在调用点**（调用点被删 ⇒ 条目也要删，否则红），所以豁免不会烂在原地。
本条不实现 `sec` 建议的"同时接受两种授权形态" —— 那属于 **task-95 / T-61**（`backend` 的卡）。

**已知边界（本用例不覆盖，别读成"已覆盖"）**

1. **仓储直插**：``services.team_run_repo.create(...)`` 能绕过 ``TeamRunService`` 直接建 run 行。
   本判据锚在 ``TeamRunService.create`` 上，看不到这条更低层的路径 ⇒ 将来若有人从仓储建 run，
   **这里不会红**（要覆盖它得另立一条判据）。
2. **splat + 接收者认不出**：``x.create(**payload)`` 的关键字不在 AST 上，只能靠"接收者文本像
   service"兜（通道 ②）⇒ 接收者名字也与 service 无关时**漏**。
3. **动态派发**：``getattr(service, "create")(...)`` 之类 ⇒ 漏（AST 判据的固有边界）。

**变异证据（两类，别混读）**

判据对**被测对象**有信号：

* ``M-A`` 新增一个 infra 调用点、**不**引用 access（接收者从参数传入）⇒ **2 红**；
* ``M-B`` 别处再写一个前缀字面量 ⇒ **1 红**（在 ``test_memory_namespace_authority.py``，同一批加固）；
* ``M-C`` §5 被迫那份漂移（``project_`` → ``projects_``）⇒ **2 红**。

判据对**自己失效**也有信号（★ 这一类与上面不同，读者别把它当成同一种证据）：

* ``M-D`` 把检测器改坏（让它永远扫不到调用点）⇒ **4 红** —— 验的是"判据失灵时会不会静默变绿"。
  它存在的理由：``M-A`` **第一次做时恰恰没红**（当时的检测器锚在接收者变量名上，认不出参数传入的
  service）⇒ **判据自己绿而不生效**。换锚点到 ``create()`` 的必填关键字 ``team_agent_id=`` 后才红。
  配合 ``test_the_matcher_is_anchored_on_the_signature_not_the_variable_name``（锚点自己也会腐坏，
  所以给它配一条会先红的用例）。
"""

from __future__ import annotations

import ast
from pathlib import Path

_SRC = Path(__file__).resolve().parents[3] / "src" / "octop"
_INFRA = _SRC / "infra"

#: 谓词的唯一真源（`api/common/agent.py` 只是转调 + 再导出）。
_ACCESS_MODULE = "octop.infra.agents.access"

#: 锚点：``TeamRunService.create`` 的**必填关键字参数**（见 run_service.py 的签名）。
_CREATE_KEYWORD = "team_agent_id"

#: 实现模块**不是调用方**：它内部的 ``self._runs.create(team_agent_id=…)`` 是**仓储**写
#: （``self._runs = services.team_run_repo``），不是入口 ⇒ 从"调用点清单"里排除。
_IMPLEMENTATION = "infra/agents/teams/run_service.py"

#: 调用 `TeamRunService.create` 但**不**直接引用 access 的模块：逐条写理由。
_GRANDFATHERED: dict[str, str] = {
    "infra/gateway/slash/handlers/team.py": (
        "授权经**注入的** `ctx.authorize_agent_action`（T-19 的接线形态：注入面为 None 时"
        "直接 `authorizer_unwired` 失败关闭），本文件不直接 import access —— "
        "两形态的收口见 task-95 / T-61。"
    ),
}


# ---------------------------------------------------------------------------
# 检测器（它自己也要被测：见 test_detector_discriminates）
# ---------------------------------------------------------------------------


def _mentions_service(node: ast.AST | None) -> bool:
    if node is None:
        return False
    text = ast.unparse(node)
    return "team_run_service" in text or "TeamRunService" in text


def _service_names(tree: ast.AST) -> set[str]:
    """模块内"绑定到 team run service"的名字（含返回它的本地 helper 名）。

    覆盖本仓的实际形态：``service = ctx.team_run_service``（slash）、
    ``def _service(server): return server.services.team_run_service()``（HTTP），
    以及直接写全名的调用。
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and _mentions_service(node.value):
            names |= {t.id for t in node.targets if isinstance(t, ast.Name)}
        elif isinstance(node, ast.AnnAssign) and _mentions_service(node.value):
            if isinstance(node.target, ast.Name):
                names.add(node.target.id)
        elif isinstance(node, ast.FunctionDef) and any(
            _mentions_service(ret.value) for ret in ast.walk(node) if isinstance(ret, ast.Return)
        ):
            names.add(node.name)
    return names


def _create_call_lines(tree: ast.AST) -> list[int]:
    """``TeamRunService.create(...)`` 的行号 —— **两条互补的通道取并集**。

    通道 ①：调用点上出现 ``team_agent_id=`` 关键字。``create`` 的 ``team_agent_id`` 是
      **必填关键字参数**（``run_service.py`` 的签名），所以无论接收者叫什么 —— ``service``、
      ``ctx.team_run_service``、别名、**甚至从参数传进来的未知名字** —— 这个关键字都在调用点上。
      别的 ``.create(...)`` 不会传它 ⇒ **无假阳**。
      （第一版只认接收者名字，实测漏掉了"接收者从参数传入"的形态：临时加一个
      ``def build(service, …): return service.create(team_agent_id=…)`` 时用例**没红** ——
      这正是"判据自己被证明会红"要抓的东西，故改成锚形参名。）
    通道 ②：接收者的文本提到 ``team_run_service`` / ``TeamRunService``。它兜住通道 ① 看不见的
      ``service.create(**payload)``（splat 时关键字不在 AST 里）。
    """
    names = _service_names(tree)
    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr != "create":
            continue
        receiver = ast.unparse(func.value)
        # 通道 ①（锚形参名）与通道 ②（锚接收者文本）取并集。
        keyword_anchor = any(kw.arg == _CREATE_KEYWORD for kw in node.keywords)
        receiver_anchor = (
            _mentions_service(func.value)
            or receiver in names
            or any(receiver.startswith(f"{name}(") for name in names)
        )
        if keyword_anchor or receiver_anchor:
            lines.append(node.lineno)
    return lines


def _references_access(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == _ACCESS_MODULE:
            return True
        if isinstance(node, ast.Import) and any(a.name == _ACCESS_MODULE for a in node.names):
            return True
    return False


def _scan_all_callers(root: Path = _INFRA) -> dict[str, int]:
    """``{相对路径: 调用点数}`` —— infra 里所有真的建 run 的模块（排除实现自身）。"""
    found: dict[str, int] = {}
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(_SRC).as_posix()
        if rel == _IMPLEMENTATION:
            continue
        lines = _create_call_lines(ast.parse(path.read_text(encoding="utf-8")))
        if lines:
            found[rel] = len(lines)
    return found


def _scan(root: Path = _INFRA) -> dict[str, int]:
    """上面那份里，**没有**引用 access 谓词的那些（= 必须登记理由的）。"""
    found: dict[str, int] = {}
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(_SRC).as_posix()
        if rel == _IMPLEMENTATION:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        lines = _create_call_lines(tree)
        if lines and not _references_access(tree):
            found[rel] = len(lines)
    return found


# ---------------------------------------------------------------------------
# 用例
# ---------------------------------------------------------------------------


def test_detector_discriminates() -> None:
    """判据先自证：认得出该认的，且**不会**把随便一个 ``.create()`` 当调用点。"""
    slash_like = ast.parse(
        "service = ctx.team_run_service\nservice.create(team_agent_id=t, user=u, goal=g)\n"
    )
    http_like = ast.parse(
        "def _service(server):\n    return server.services.team_run_service()\n"
        "run = _service(server).create(a=1)\n"
    )
    # ★ 接收者的名字**认不出来**（从参数传进来）⇒ 靠 `team_agent_id=` 关键字仍要抓到。
    passed_in = ast.parse(
        "def build(service, team_agent_id, user, goal):\n"
        "    return service.create(team_agent_id=team_agent_id, user=user, goal=goal)\n"
    )
    # splat：关键字在 AST 里看不见 ⇒ 靠接收者像是 service 来兜。
    splat = ast.parse("svc = ctx.team_run_service\nsvc.create(**payload)\n")
    unrelated = ast.parse("repo = ProjectRepo(db)\nrepo.create(name='x')\n")

    assert _create_call_lines(slash_like) == [2]
    assert _create_call_lines(http_like) == [3]
    assert _create_call_lines(passed_in) == [2], "接收者从参数传入的形态漏了"
    assert _create_call_lines(splat) == [2], "splat 形态漏了"
    assert _create_call_lines(unrelated) == [], "别把无关的 .create() 当成建 run"


def test_matcher_still_sees_a_call_site() -> None:
    """防"检测器悄悄坏掉 ⇒ 一切皆绿"：当前确实存在调用点，且数量被钉住。"""
    callers = _scan_all_callers()

    assert callers, "一个调用点都没扫到 —— 检测器坏了（这本身就是红）"
    assert callers == {"infra/gateway/slash/handlers/team.py": 1}, (
        f"infra 里的 create 调用点变了：{callers}。"
        "新增调用点要一并登记到 _GRANDFATHERED（或让它引用 access）"
    )


def test_every_infra_caller_references_the_access_predicate_or_is_grandfathered() -> None:
    """★ 本卡的核心：新增的不引用调用点 ⇒ 红。"""
    non_compliant = _scan()

    assert set(non_compliant) <= set(_GRANDFATHERED), (
        "这些 infra 模块调用了 TeamRunService.create 却没有引用 "
        f"{_ACCESS_MODULE}，也没登记理由："
        f"{sorted(set(non_compliant) - set(_GRANDFATHERED))}。"
        "建 run 的授权必须显式注入（create 自己不校验归属）。"
    )


def test_grandfathered_entries_are_still_real_and_carry_a_reason() -> None:
    """豁免不许烂在原地：调用点没了要删条目；理由不许空。"""
    callers = set(_scan_all_callers())

    stale = sorted(entry for entry in _GRANDFATHERED if entry not in callers)
    assert stale == [], f"这些豁免已经没有对应调用点了，请删掉：{stale}"
    for entry, reason in _GRANDFATHERED.items():
        assert reason.strip(), f"{entry} 的豁免理由不能为空"
        assert len(reason) > 20, f"{entry} 的豁免理由太短，写清'授权从哪来'"


def test_the_matcher_is_anchored_on_the_signature_not_the_variable_name() -> None:
    """判据的来源：``team_agent_id`` 是 ``create`` 的**必填关键字参数**。

    这条把"锚点"本身钉在签名上 —— 若 ``create`` 改了参数名，这里先红，而不是让检测器
    悄悄失效（"绿而不生效"）。
    """
    source = (_SRC / "infra/agents/teams/run_service.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    create = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "create"
    )

    keyword_only = [arg.arg for arg in create.args.kwonlyargs]
    assert _CREATE_KEYWORD in keyword_only, (
        f"create() 的关键字参数变了（{keyword_only}）：检测器的锚点要同步改"
    )
    assert create.args.kw_defaults[keyword_only.index(_CREATE_KEYWORD)] is None, (
        f"{_CREATE_KEYWORD} 变成可选了：锚点会开始漏掉不传它的调用点"
    )


def test_the_http_surface_references_the_predicate_too() -> None:
    """HTTP 面（唯一被 T-48 认定合规的入口）在同一个检测器下必须是"引用了 access"。

    这条不是新增义务，而是**把已有事实钉住**：``api/routers/team_runs.py`` 的建 run
    授权经 ``api/common/agent.py``（转调 ``infra/agents/access``）。
    """
    tree = ast.parse((_SRC / "api/routers/team_runs.py").read_text(encoding="utf-8"))
    assert _create_call_lines(tree), "HTTP 面的 create 调用点没了？"
    source = (SRC_TEAM_RUNS := _SRC / "api/routers/team_runs.py").read_text(encoding="utf-8")
    assert "assert_agent_owner" in source, (
        f"{SRC_TEAM_RUNS.as_posix()} 不再引用 assert_agent_owner ⇒ HTTP 面的授权没了"
    )
