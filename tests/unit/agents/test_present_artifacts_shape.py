"""T-72 —— 工件清点（``present_artifacts``）必须读**harness 的形状**，不是读 ``.name``。

**根因（实测）**：``octop_harness.backends.workspace · BackendWorkspace.list_dir`` 返回
``{"path": <workspace-relative>, "is_dir": bool}``，注释逐字写着 "**Always workspace-relative
(``skills/demo``), never basename-only**"。而 ``present_artifacts`` 当时用
``getattr(entry, "name", entry)`` 取名字 ⇒ **dict 没有 ``.name``** ⇒ 退化成整串 dict 文本
（实测：``"{'path': 'team/R1/SPEC.md', 'is_dir': False}"``）⇒ 阶段门的 ``SPEC.md`` 永远匹配不上。

**后果链**（与 `qa` 的现象逐字吻合）：``SPEC.md`` 真落盘 ⇒ **G4 读的是正文**（``spec_text``）
⇒ 通过 ⇒ 紧接着的**阶段工件清点**（``missing_artifacts``）读 ``present_artifacts`` ⇒ 报
``TEAM_PHASE_GATE_FAILED details.missing=["SPEC.md"]`` ⇒ **写侧说"写成了"、门禁侧说"没有"**
⇒ run 永远进不了 ``implement``。

**为什么会藏住**：测试替身返回的是 ``SimpleNamespace(name="SPEC.md")``（basename），
``getattr`` 分支能work ⇒ 端到端用例一直绿，而**生产用的是另一个形状**。
⇒ 判据：**"比'名字'之前，先确认对方返回的是不是名字。"**（形状错在代码里，不在观测里）
"""

from __future__ import annotations

import ast
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from octop.infra.agents.teams.run_service import TeamRunService

_TESTS = Path(__file__).resolve().parents[2]


class _Workspace:
    """只实现 ``list_dir`` —— 被测的只有清点这一跳。"""

    def __init__(self, entries: Any) -> None:
        self._entries = entries

    def list_dir(self, path: str = ".") -> Any:
        return self._entries


def _census(entries: Any) -> tuple[str, ...]:
    service = TeamRunService.__new__(TeamRunService)  # 只测这一个方法，不建整套服务
    service._workspace = lambda run: _Workspace(entries)  # type: ignore[method-assign]
    return TeamRunService.present_artifacts(service, SimpleNamespace(run_id="R1", run_root=None))


def test_reads_the_harness_shape() -> None:
    """★ 真形状：``{"path", "is_dir"}`` ⇒ **basename**（门比的是 ``SPEC.md``）。"""
    entries = [
        {"path": "team/R1/SPEC.md", "is_dir": False},
        {"path": "team/R1/TASKS.json", "is_dir": False},
        {"path": "team/R1/sub", "is_dir": True},
        {"path": "team/R1/sub/PLAN.md", "is_dir": False},
    ]

    assert _census(entries) == ("SPEC.md", "TASKS.json", "PLAN.md")


def test_reads_the_attribute_shape() -> None:
    """旧替身的形状仍然容忍（属性 ``.name`` / 纯字符串 / 目录尾斜杠）。"""
    assert _census([SimpleNamespace(name="SPEC.md"), SimpleNamespace(name="sub/")]) == ("SPEC.md",)
    assert _census(["SPEC.md", "sub/"]) == ("SPEC.md",)


def test_written_is_present_and_unwritten_is_absent() -> None:
    """正对照（两个方向）：**写了就是有、没写就是没有** —— 防"把门改成恒真"。"""
    entries = [{"path": "team/R1/SPEC.md", "is_dir": False}]

    present = _census(entries)
    assert "SPEC.md" in present
    assert "TASKS.json" not in present, "没写的工件不许被报成存在"


def test_no_workspace_is_an_empty_census() -> None:
    """fail closed：没有 workspace ⇒ 清点为空（门据此拒绝，而不是放行）。"""
    service = TeamRunService.__new__(TeamRunService)
    service._workspace = lambda run: None  # type: ignore[method-assign]
    run = SimpleNamespace(run_id="R1", run_root=None)

    assert TeamRunService.present_artifacts(service, run) == ()


#: 已知的 basename-only 替身 —— **带过期判据**：条目与实测列表必须**双向相等**
#: （修好一个就删一条；新增一个则红）。它们**不在 T-72 写区**（`tests/unit/api` · `tests/unit/gateway`）
#: ⇒ 只登记不代改；T-72 报告里已上报给了 lead。
#: 已知的 basename-only 替身 —— 现在是**空的**（T-79 把最后 3 处改成了 harness 形状）。
#: **带过期判据**：与实测列表**双向相等** ⇒ 新出现 ⇒ 红；修好未删条目 ⇒ 也红。
#: 清单为空是**收敛的证据**，不是"没人管"。
_KNOWN_BASENAME_DOUBLES: dict[str, str] = {}


def _repo_rel(path: Path) -> str:
    """``tests/…`` 形式的相对路径 —— basename 会有歧义（T-79：其中两处在 ``tests/integration/``）。"""
    try:
        return path.relative_to(_TESTS.parent).as_posix()
    except ValueError:  # 不在仓内（不应发生）
        return path.as_posix()


def _basename_only_doubles(path: Path) -> list[str]:
    """``def list_dir`` 体内构造的 **basename-only** 目录项（违反 harness 形状）。

    只认两种精确写法：``SimpleNamespace(name=…)`` 与**只有 ``name`` 没有 ``path``** 的 dict。
    （裸字符串列表同样会藏住形状错，但静态识别它假阳太多 —— 这条边界写在用例 docstring 里。）
    """
    offenders: list[str] = []
    tree = ast.parse(path.read_text(encoding="utf-8"))
    # Report the **full** relative path: basenames alone are ambiguous (T-79: two of
    # these doubles live in ``tests/integration/``, not ``tests/unit/api/``).
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name != "list_dir":
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                callee = getattr(sub.func, "id", None) or getattr(sub.func, "attr", None)
                if callee == "SimpleNamespace" and any(kw.arg == "name" for kw in sub.keywords):
                    offenders.append(f"{_repo_rel(path)}:{sub.lineno} SimpleNamespace(name=…)")
            elif isinstance(sub, ast.Dict):
                keys = {k.value for k in sub.keys if isinstance(k, ast.Constant)}
                if "name" in keys and "path" not in keys:
                    offenders.append(f"{_repo_rel(path)}:{sub.lineno} dict(name=…) without path")
    return offenders


def scan_basename_only_doubles(root: Path) -> list[str]:
    """扫 ``root`` 下所有 ``list_dir`` 替身，返回 basename-only 的清单。

    **扫描根是参数**（T-79 收尾）：于是"这个守卫自己会不会红"可以在**调用方给的临时树**里验证
    —— 两个方向都**零写入**共享工作树（此前方向一必须临时新增一个文件）。
    """
    offenders: list[str] = []
    for path in sorted(root.rglob("*.py")):
        offenders += _basename_only_doubles(path)
    return offenders


def unknown_doubles(offenders: Sequence[str], known: Mapping[str, str]) -> list[str]:
    """实测里**不在**已知清单中的（= 必须红的那些）。"""
    return [item for item in offenders if item not in known]


def stale_known_entries(offenders: Sequence[str], known: Mapping[str, str]) -> list[str]:
    """已知清单里**已经不存在**的条目（= 修好没删 ⇒ 必须红）。"""
    return [entry for entry in known if entry not in offenders]


def test_no_test_double_feeds_the_old_basename_shape() -> None:
    """★ 守"下一个人再把 ``.name`` 写回来"：**替身必须与 harness 同形**。

    这条是这次缺陷藏住的直接原因 —— 替身返回 basename 时，``getattr(entry, "name", ...)``
    能work，于是端到端用例在**错误形状**上全绿，而生产用的是 dict（``{"path", "is_dir"}``）。

    **边界（如实标注）**：本机检只覆盖 ``SimpleNamespace(name=…)`` 与"只有 name 的 dict"两种写法
    —— 一个**裸字符串列表**的 ``list_dir`` 替身同样会藏住形状错，但静态识别它的假阳率太高
    （函数体里的 ``""``、``"/"`` 随处可见）⇒ 未覆盖；要收它请把替身改成显式 dict 形状。
    """
    offenders = scan_basename_only_doubles(_TESTS)

    unknown = unknown_doubles(offenders, _KNOWN_BASENAME_DOUBLES)
    assert unknown == [], (
        "这些测试替身的 ``list_dir`` 返回 basename 形状，而 harness 返回 "
        f'{{"path", "is_dir"}}: {unknown} —— 请与 BackendWorkspace.list_dir 同形，'
        "否则下一次「形状错」还会被替身藏住。"
    )
    stale = [item for item in _KNOWN_BASENAME_DOUBLES if item not in offenders]
    assert stale == [], f"这些已知项已经修好了，请把条目删掉：{stale}"


_BASENAME_ONLY_DOUBLE = """from __future__ import annotations

from typing import Any


class W:
    def list_dir(self, path: str = ".") -> list[Any]:
        return [{"name": "SPEC.md"}]
"""

_HARNESS_SHAPE_DOUBLE = """from __future__ import annotations

from typing import Any


class W:
    def list_dir(self, path: str = ".") -> list[Any]:
        return [{"path": "team/R1/SPEC.md", "is_dir": False}]
"""


def test_the_guard_discriminates_in_a_caller_provided_tree(tmp_path: Path) -> None:
    """★ 两个方向都在 ``tmp_path`` 里跑 ⇒ **零写入**共享工作树。

    方向一（**新出现**的 basename-only 替身 ⇒ 红）与方向二（**修好未删**的已知条目 ⇒ 红）
    此前只能靠"临时新增文件 + 记得删掉"来验；扫描根可注入之后，两边都变成进程内的构造
    —— **"记得删"这件事不再存在**。

    ★ 写这条时踩过一次：早先用 pytest 插件 patch 的是 ``tests.unit.agents.*`` 那个**模块对象**，
    而 pytest 按 rootdir 把测试模块加载成**另一个**对象 ⇒ patch 没生效、变异"没红"。
    ⇒ **patch / 断言 / 观察的对象，必须是运行时真正被执行的那一个 —— 同名不等于同一。**
    """
    (tmp_path / "test_bad_double.py").write_text(_BASENAME_ONLY_DOUBLE, encoding="utf-8")
    (tmp_path / "test_ok_double.py").write_text(_HARNESS_SHAPE_DOUBLE, encoding="utf-8")

    offenders = scan_basename_only_doubles(tmp_path)

    # 方向一：坏的被抓、好的不被冤枉
    assert len(offenders) == 1, offenders
    assert "test_bad_double.py" in offenders[0]
    assert unknown_doubles(offenders, {}) == offenders

    # 方向二：清单里多一条（已不存在）⇒ 过期，必须红
    ghost = {"ghost.py:1 dict(name=…) without path": "已经修好了"}
    assert stale_known_entries(offenders, ghost) == list(ghost)
    # 而清单正好等于实测 ⇒ 两侧都空（收敛态）
    assert unknown_doubles(offenders, {offenders[0]: "ok"}) == []
    assert stale_known_entries(offenders, {offenders[0]: "ok"}) == []
