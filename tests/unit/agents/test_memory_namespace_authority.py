"""T-62 — ``agent_`` / ``project_`` / ``team_`` 命名空间**前缀**只有一个权威。

背景（`sec` 在 T-27-3 逐处核过"构造 vs 比较"）：前缀字面量曾在 4 处重复，其中
**3 处不是 §5 被迫**（`manager.py` / `api/common/memory_client.py` / `memory_portable.py`
都能引权威），只有 ``db/repos/projects.py`` 是**真被迫** —— ``AGENTS.md §5`` 硬禁
``infra/db/repos/`` → 非 DB 的 ``infra`` 包，而 ``infra/agents/memory/backend.py`` 正是
域侧模块。于是它按 ``project_artifacts.py · WORKFLOW_KIND`` 的先例处理：
**两份 + 机检绑定**（而**不是**把词表下沉到 repos 让 import 合法 —— `SECURITY §8.1` 的反向禁令）。

本文件就是那道"机检绑定"：
① 精确前缀字面量**只允许出现在两个地方**（权威 + 那处 §5 被迫）；
② 两份的值必须**相等**；
③ ``def agent_memory_namespace`` 全仓**只有一处**（重复在字面量层，不是两套实现）；
④ 那处"被迫"是真的：repos 模块确实没有 import 域侧（否则它就该改成引用权威）。
"""

from __future__ import annotations

import ast
from pathlib import Path

_SRC = Path(__file__).resolve().parents[3] / "src" / "octop"

#: 前缀的**唯一权威**。
_AUTHORITY = "infra/agents/memory/backend.py"
#: §5 被迫的第二份（``infra/db/repos/`` 不得 import 域侧）。
_S5_FORCED = "infra/db/repos/projects.py"
#: 精确等于这些字符串的**字面量**只准出现在上面两个文件里。
_PREFIXES = frozenset({"agent_", "project_", "team_"})


def _rel(path: Path) -> str:
    return path.relative_to(_SRC).as_posix()


def _prefix_literals(tree: ast.AST) -> list[str]:
    """精确等于前缀的字符串常量（``f"agent_{x}"`` 的 JoinedStr 不算 —— 那是拼接）。"""
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and node.value in _PREFIXES
    ]


def _literals_by_file() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for path in sorted(_SRC.rglob("*.py")):
        values = _prefix_literals(ast.parse(path.read_text(encoding="utf-8")))
        if values:
            found[_rel(path)] = values
    return found


def _module_prefix_constant(node: ast.stmt) -> tuple[str, str] | None:
    """``NAME = "prefix"`` ⇒ ``(NAME, value)``；任何其它节点 ⇒ ``None``。

    （拆成两条平铺的 ``if`` 而不是嵌套：SIM102，且比一条四段的 ``and`` 好读。）
    """
    if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Constant):
        return None
    if node.value.value not in _PREFIXES or not isinstance(node.targets[0], ast.Name):
        return None
    return node.targets[0].id, str(node.value.value)


def _module_constants(rel: str) -> dict[str, str]:
    """模块级 ``NAME = "literal"`` 的映射（只看前缀常量）。"""
    tree = ast.parse((_SRC / rel).read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for node in tree.body:
        found = _module_prefix_constant(node)
        if found is not None:
            out[found[0]] = found[1]
    return out


def _imports(rel: str) -> set[str]:
    tree = ast.parse((_SRC / rel).read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_prefix_literals_live_in_exactly_two_places() -> None:
    """① 新增第三份前缀字面量 ⇒ 红（不管它在哪个层）。"""
    assert set(_literals_by_file()) == {_AUTHORITY, _S5_FORCED}, (
        "命名空间前缀的字面量只允许出现在权威与 §5 被迫的那处；"
        "其余位置请 `from octop.infra.agents.memory.backend import agent_memory_namespace`。"
    )


def test_the_s5_forced_copy_is_equal_to_the_authority() -> None:
    """② 两份必须相等（机检绑定）—— 任意一份被改而另一份没跟上 ⇒ 红。"""
    authority = _module_constants(_AUTHORITY)
    forced = _module_constants(_S5_FORCED)

    assert authority == {
        "_AGENT_NS_PREFIX": "agent_",
        "_PROJECT_NS_PREFIX": "project_",
        "_TEAM_NS_PREFIX": "team_",
    }, "权威的三条前缀是这三条；改它们要同步改本用例与 §5 被迫的那份"
    # 被迫的那份只写 project_（它唯一的职责是 projects.memory_namespace 的写入值），
    # 而且当前是**直接拼**的（没有模块级常量），所以这里允许它为空。
    assert not forced or forced == {"_PROJECT_NS_PREFIX": "project_"}, (
        f"{_S5_FORCED} 的模块级前缀常量变了：{forced}"
    )
    repo_value = _repo_prefix_from_function()
    assert repo_value == authority["_PROJECT_NS_PREFIX"], (
        "repos 的 project_ 前缀与权威不一致 —— 两份已经漂移"
    )


def _repo_prefix_from_function() -> str:
    """从 ``projects.py · project_memory_namespace`` 的返回字面量里取前缀。

    这个函数**不**依赖模块级常量名（那份实现用的是 ``f"project_{project_id}"``
    直接拼），所以从返回语句的 JoinedStr 里取第一个常量段 —— 它才是真正写进
    ``projects.memory_namespace`` 的那个值。
    """
    tree = ast.parse((_SRC / _S5_FORCED).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "project_memory_namespace":
            for sub in ast.walk(node):
                if isinstance(sub, ast.JoinedStr):
                    for part in sub.values:
                        if isinstance(part, ast.Constant) and part.value in _PREFIXES:
                            return str(part.value)
    raise AssertionError(f"{_S5_FORCED} 里找不到 project_memory_namespace 的前缀字面量")


def test_agent_memory_namespace_is_defined_exactly_once() -> None:
    """③ 全仓只有一个构造函数 —— 重复只在字面量层，不是两套实现。"""
    definitions: list[str] = []
    for path in sorted(_SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        definitions += [
            _rel(path)
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "agent_memory_namespace"
        ]

    assert definitions == [_AUTHORITY], f"权威只准一处，实得 {definitions}"


def test_the_s5_forced_copy_really_is_forced() -> None:
    """④ "被迫"必须是**真的**：repos 没 import 域侧；否则它就该引用权威而不是抄一份。"""
    imports = _imports(_S5_FORCED)

    forbidden = sorted(name for name in imports if name.startswith("octop.infra.agents"))
    assert forbidden == [], (
        f"{_S5_FORCED} 现在能 import 域侧了（{forbidden}）⇒ 它不再是 §5 被迫，"
        "请改成 `from octop.infra.agents.memory.backend import project_memory_namespace` "
        "并把本用例的豁免一起删掉。"
    )


def test_the_three_former_duplicates_now_reference_the_authority() -> None:
    """①' 改过的三处：构造/比较都走权威（行为等价另有用例）。"""
    from octop.api.common.memory_client import memory_namespace
    from octop.api.routers.memory_portable import _agent_id_of_namespace
    from octop.infra.agents.manager import _memory_namespace
    from octop.infra.agents.memory.backend import agent_memory_namespace

    assert memory_namespace("A1") == agent_memory_namespace("A1") == _memory_namespace("A1")
    assert _agent_id_of_namespace(agent_memory_namespace("A1")) == "A1"
    # 比较方向的边界：空 id 与别的层都不是 agent 命名空间。
    assert _agent_id_of_namespace(agent_memory_namespace("")) is None
    assert _agent_id_of_namespace("project_P1") is None
