"""T-75 · `details` 的准入面（SEC-4 / SPEC A6）—— 黑名单的**机检** + 判别性对照。

判据面（谁会被看到）：`api/app.py` 的 app handler 走 `to_envelope(locale=…)` ⇒ i18n 把
raise-site 的 message **整条替换**，**只有 `details` 幸存**。所以 `details` 是 5xx 的
**唯一**定位通道 ⇒ 它同时是**唯一会被最终用户看到的结构化字段** ⇒ 它必须干净。

两条机检（★ 都配**负样本对照**：静态断言若只写"真源码 0 命中"，可能是**空断言**）：

1. `code` 键**不得**再炸：`details={"code": …}` 走 `to_envelope(locale=…)` 必须**不抛**
   （`infra/errors.py · interpolation_kwargs` 会把与 i18n 形参同名的键从**插值**里剔除；
   ★ 注意：`code` **不是**禁用键 —— 它是既有的机器可读类别，见 `teams/pipeline.py`）。
2. 黑名单**值**（异常原文 = `str(exc)` / 裸异常对象）：报出 `路径:行号`；
   已知既有站点走**双向绑定**的清单（新出现 ⇒ 红；清单里的修好了没删 ⇒ 也红）。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from octop.infra.errors import ErrorCode, OctopError

_SRC = Path(__file__).resolve().parents[3] / "src" / "octop"

#: ★ `T-88` 已把 15 处（机检清单 14 处 ＋ 机检**看不见**的第 15 处 = `manager.py` ·
#: `install_url` 的 `URLError` 分支）**全部处置**（承重 8 处换值不删键 / 不承重 7 处换值）
#: ⇒ 清单**收敛为空**。**双向绑定**仍然生效：清单里的条目修好了没删 ⇒
#: `test_known_blacklist_entries_are_still_present` 红；新出现的命中 ⇒
#: `test_no_unknown_blacklist_hits` 红。
#: ★★ 硬判据 = `len(_KNOWN_BLACKLIST_VIOLATIONS) == 0`
#: （见 `test_known_blacklist_violations_is_empty` —— 只跑上面两条集合差用例在 14 条未处置时
#: **已为 True** ⇒ 那是假绿）。
_KNOWN_BLACKLIST_VIOLATIONS: dict[str, str] = {}

#: 黑名单**值**的形态（A6）：异常原文不得进 `details`。
_BLACKLISTED_VALUE_MARKERS = (
    "str(exc",
    "str(err",
    # ★ `T-88`：补上第 15 处的**原始形态**（`manager.py` · `URLError` 分支 ·
    # `details={"reason": str(reason)}`）—— 旧标记表不含 `str(reason` ⇒ `scan_blacklist`
    # 对那一处**两头都看不见**（`SEC-14` 的机检盲区）。
    "str(reason",
    "{exc}",
    "{err}",
    "traceback",
    "Traceback",
    # ★ `T-98` · `PLAN §5.1 @ 276-283` 逐字新增 4 个（追加到同一 tuple 末尾；
    # 匹配仍是 `ast.unparse(value)` **子串** `in` ⇒ 顺序无关、只增不减）。
    # 每条都对应 `RESEARCH-T98-T99.md §3` 的一个**现表抓不到**的形态：
    #   `"str(e"`  ⇒ `details={"reason": str(e)}`（现表三条标记都含变量名 ⇒ 变量叫 `e` 即漏）
    #   `"repr("`  ⇒ `details={"reason": repr(exc)}`（现表无 `repr`；`{x!r}` 渲染为 `!r` 不是 `repr(`）
    #   `".args"` / `"str(exc.args"` ⇒ `details={"reason": exc.args}` 系列
    "str(e",
    "repr(",
    ".args",
    "str(exc.args",
)


def _is_octop_error(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and (
        (getattr(node.func, "id", None) or getattr(node.func, "attr", None)) == "OctopError"
    )


def scan_blacklist(source: str, path: str = "<synthetic>") -> list[str]:
    """返回 `路径:行号` 形式的黑名单命中（`details` 的值里出现异常原文）。"""
    hits: list[str] = []
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not _is_octop_error(node):
            continue
        for kw in node.keywords:
            if kw.arg != "details" or not isinstance(kw.value, ast.Dict):
                continue
            for value in kw.value.values:
                rendered = ast.unparse(value)
                if any(marker in rendered for marker in _BLACKLISTED_VALUE_MARKERS):
                    hits.append(f"{path}:{node.lineno}")
    return hits


def _scan_tree() -> list[str]:
    hits: list[str] = []
    for path in sorted(_SRC.rglob("*.py")):
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):  # pragma: no cover
            continue
        try:
            hits += scan_blacklist(source, path.relative_to(_SRC.parents[1]).as_posix())
        except SyntaxError:  # pragma: no cover - 3.12 语法下不应出现
            continue
    return hits


# ── ① `code` 键不得再炸（本卡 ⑥ 的显式要求）────────────────────────────────────


@pytest.mark.parametrize("locale", ["zh", "en"])
def test_details_with_a_code_key_passes_through_to_envelope(locale: str) -> None:
    """`details={"code": …}` 走 `to_envelope(locale=…)` **不抛**（本 run 曾在此炸过 `TypeError`）。"""
    err = OctopError(
        ErrorCode.INTERNAL_ERROR,
        "boom",
        details={"code": "missing-id", "task_id": "t1"},
    )

    envelope = err.to_envelope(locale=locale)["error"]

    # 不抛 + details 原样 survives（它就是 5xx 唯一的定位通道）。
    assert envelope["details"] == {"code": "missing-id", "task_id": "t1"}
    # ★ message 被 i18n 替换（这正是"定位只能靠 details"的机制本身）——
    # 断言它**不是** raise-site 原文，把这个前提钉住。
    assert envelope["message"] != "boom"


# ── ② 黑名单值 + 判别性对照 ──────────────────────────────────────────────────


def test_the_blacklist_scanner_catches_a_synthetic_violation() -> None:
    """★ 判别性对照：合成的违规源码必须被**同一套**规则抓到（否则下面的"0 命中"是空断言）。"""
    bad = (
        "def f(exc):\n"
        "    raise OctopError(ErrorCode.INTERNAL_ERROR, 'x', details={'detail': str(exc)})\n"
    )
    good = "def f(exc):\n    raise OctopError(ErrorCode.INTERNAL_ERROR, f'x: {exc}')\n"

    assert scan_blacklist(bad) == ["<synthetic>:2"], "黑名单值必须被抓到"
    assert scan_blacklist(good) == [], "异常原文留在 message 里**不是**违规"


def test_no_unknown_blacklist_hits() -> None:
    """全仓扫：除既有清单外，**不得**有新的 `details` 含异常原文。"""
    unknown = [hit for hit in _scan_tree() if hit not in _KNOWN_BLACKLIST_VIOLATIONS]
    assert unknown == [], f"新增的 details 黑名单命中（须改）: {unknown}"


def test_known_blacklist_entries_are_still_present() -> None:
    """★ 双向绑定：清单里的条目修好之后必须**删条目**（否则"已知例外"变永久豁免）。"""
    hits = set(_scan_tree())
    stale = [entry for entry in _KNOWN_BLACKLIST_VIOLATIONS if entry not in hits]
    assert stale == [], f"这些已知项已经修好了，请把条目删掉：{stale}"


#: `T-88` 处置过的四个文件（承重 8 处 ＋ 不承重 7 处）。
_REMEDIATED_FILES = (
    "api/routers/connectors.py",
    "api/routers/plugins.py",
    "infra/agents/plugins/manager.py",
    "infra/connectors/custom_mcp.py",
)


def test_known_blacklist_violations_is_empty() -> None:
    """★ `T-88` 硬判据（可机判）：清单为空 **且** 全仓扫描零命中。

    ★ 判别性：上面两条集合差用例在 14 条**未处置**时**已为 True** ⇒ 只跑它们 = 假绿。
    """
    assert len(_KNOWN_BLACKLIST_VIOLATIONS) == 0, _KNOWN_BLACKLIST_VIOLATIONS
    assert _KNOWN_BLACKLIST_VIOLATIONS == {}
    assert _scan_tree() == []


def _details_dicts_in(rel: str) -> list[tuple[set[str], list[str]]]:
    """某文件里每个 `details={...}` 字面量的（键集合, 值源码列表）—— 用于正对照。"""
    out: list[tuple[set[str], list[str]]] = []
    tree = ast.parse((_SRC / rel).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if _is_octop_error(node):
            for kw in node.keywords:
                if kw.arg == "details" and isinstance(kw.value, ast.Dict):
                    keys = {k.value for k in kw.value.keys if isinstance(k, ast.Constant)}
                    out.append((keys, [ast.unparse(v) for v in kw.value.values]))
    return out


def test_remediated_details_still_carry_a_machine_readable_category() -> None:
    """★ 正对照（`T-88`）：**换值 ≠ 删键** ⇒ 定位能力没有归零。

    ① 四个文件里带 `reason` 键的 `details` 字面量共 **19** 处（= 15 处处置后**仍留键**
       ＋ 3 处既有公开字面量 `custom_mcp.py` ＋ 1 处 `B-19-15` 允许留痕的 `HTTP {code}`）；
       少一处就说明有人为了过扫描**删了键**。
    ② 承重两码仍能插值：值换成类别串后 `message` 仍填得上 `{reason}`，**不会**印出字面量。
    """
    kept = sum(
        1 for rel in _REMEDIATED_FILES for keys, _ in _details_dicts_in(rel) if "reason" in keys
    )
    assert kept == 19, f"`reason` 键被删掉了（应保留 19 处，实测 {kept}）"
    for rel in _REMEDIATED_FILES:
        for keys, values in _details_dicts_in(rel):
            if "reason" in keys:
                # ★ `T-98` · `PLAN §5.3 @ 322` 承重性裁定：这条断言在 **AST 字面量层恒真**
                # （`ast.Dict` 的 `keys`/`values` 等长 ⇒ `values` 非空；`ast.unparse` 对任意
                # expr 节点恒返回非空串 —— 实证见 `RESEARCH-T98-T99.md §2⑤`）
                # ⇒ **不得**把它当值面护栏、**不得**写进验收理由。
                # 值面保护**只**由下面的 B/C/D 三条（`value_fingerprint` / `install_url_reason_forms`
                # / `install_url_urlopen_failure`）承担。
                assert values and all(values), f"{rel}: `reason` 键的值为空"

    for code in (ErrorCode.PLUGIN_INSTALL_FAILED, ErrorCode.CONNECTOR_MCP_URL_INVALID):
        for locale in ("zh", "en"):
            err = OctopError(code, "raise-site", details={"reason": type(ValueError()).__name__})
            message = err.to_envelope(locale=locale)["error"]["message"]
            assert "{reason}" not in message, message
            assert "ValueError" in message, message


def _details_keys_in(rel: str) -> set[str]:
    """某文件里所有 `OctopError(..., details={...})` 字面量的**键**集合。"""
    keys: set[str] = set()
    tree = ast.parse((_SRC / rel).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if _is_octop_error(node):
            for kw in node.keywords:
                if kw.arg == "details" and isinstance(kw.value, ast.Dict):
                    keys |= {k.value for k in kw.value.keys if isinstance(k, ast.Constant)}
    return keys


def test_the_new_t75_details_are_whitelist_clean() -> None:
    """T-75 本轮新增的 details：键必须落在 A6 白名单内（调用者给出的值 / 资源标识）。

    ★ 三个文件各钉一条：**键 ⊆ 白名单**（防将来有人塞 `str(exc)`/凭据/主机路径）＋
    **期望键必须真的在**（防断言空洞化 —— 若扫描写错、返回空集，这条会红）。
    """
    assert _details_keys_in("api/common/memory_client.py") == {"method"}
    assert "operation" in _details_keys_in("api/routers/workspace.py")
    assert _details_keys_in("api/routers/browser/harness.py") == {"profile"}
    # 白名单之外的一律不许出现（这三个文件在本轮由 T-75 定过 details 面）
    for rel in (
        "api/common/memory_client.py",
        "api/routers/workspace.py",
        "api/routers/browser/harness.py",
    ):
        assert _details_keys_in(rel) <= {"method", "operation", "profile"}, rel


# ── ③ `T-98`：标记表新增 4 个形态（`PLAN §5.1` 逐字）────────────────────────────

#: 新增字面量 ⇒ 对应形态（`RESEARCH-T98-T99.md §3` 探针逐行）。
_T98_NEW_MARKER_FORMS = {
    "str(e": "details={'reason': str(e)}",
    "repr(": "details={'reason': repr(exc)}",
    ".args": "details={'reason': exc.args}",
    "str(exc.args": "details={'reason': str(exc.args)}",
}


def test_t98_new_markers_catch_their_forms() -> None:
    """★ 判别性对照（`SEC-15a/b/c`）：4 个新增标记**各自**必须能抓到对应形态。

    删掉任一条新增标记 ⇒ 本条**必红**（`SEC-15` 三形态在改前实测全为 `[]`）。
    """
    assert set(_T98_NEW_MARKER_FORMS) <= set(_BLACKLISTED_VALUE_MARKERS), (
        "新增标记被删（`PLAN §5.1` 只许增不许删）"
    )
    for marker, expr in _T98_NEW_MARKER_FORMS.items():
        src = f"def f(exc, e):\n    raise OctopError(ErrorCode.INTERNAL_ERROR, 'x', {expr})\n"
        assert scan_blacklist(src) == ["<synthetic>:2"], f"标记 {marker!r} 未命中 {expr}"


# ── ④ `SEC-17a`：裸异常对象（AST 值面 —— **不是**子串面）──────────────────────

#: 值节点为 `ast.Name`/`ast.Attribute` ⇒ 该值是**可能是异常对象**的裸标识符 ⇒ 命中。
#: ★ **根标识符**口径（非「凡非字面量即命中」，`PLAN §5.1 @ 290` 逐字禁止粗口径）：
#: 只认异常载荷名；`type(exc).__name__` 是**类别串**（根是内建 `type`，不是载荷名）⇒ 不命中；
#: `run_id` / `kind` / `code` 等普通标识符（全仓 121 个 `ast.Name`/`ast.Attribute` 值）⇒ 不命中。
_BARE_PAYLOAD_ROOTS = ("reason", "exc", "err", "error", "cause", "exception", "exc_info")


def _root_identifier(node: ast.expr) -> str | None:
    """`ast.Name`/`ast.Attribute` 链的最左标识符；根不是名字（如 `type(exc).__name__`）⇒ `None`。"""
    cur: ast.expr = node
    while True:
        if isinstance(cur, ast.Name):
            return cur.id
        if isinstance(cur, ast.Attribute):
            cur = cur.value
            continue
        return None


def _is_bare_exception_value(node: ast.expr) -> bool:
    return isinstance(node, (ast.Name, ast.Attribute)) and (
        _root_identifier(node) in _BARE_PAYLOAD_ROOTS
    )


def scan_bare_exceptions(source: str, path: str = "<synthetic>") -> list[tuple[str, str]]:
    """返回 `details` 字面量里**裸异常对象**值的 `(路径, 值 ast.unparse)` 对（**含重复**）。"""
    hits: list[tuple[str, str]] = []
    for node in ast.walk(ast.parse(source)):
        if not _is_octop_error(node):
            continue
        for kw in node.keywords:
            if kw.arg != "details" or not isinstance(kw.value, ast.Dict):
                continue
            hits += [(path, ast.unparse(v)) for v in kw.value.values if _is_bare_exception_value(v)]
    return hits


def test_sec17a_bare_exception_value_is_flagged() -> None:
    """★ 判别性对照（`SEC-17a`）：`details={'reason': exc}` 必须命中（改前实测 = `[]`）。

    同时钉住**不得收窄成粗口径的反面**：类别串 `type(exc).__name__`（现行修法）**不**命中。
    """
    bad = "def f(exc):\n    raise OctopError(ErrorCode.INTERNAL_ERROR, 'x', details={'reason': exc})\n"
    attr = "def f(exc):\n    raise OctopError(ErrorCode.INTERNAL_ERROR, 'x', details={'reason': exc.reason})\n"
    good = (
        "def f(exc):\n"
        "    raise OctopError(ErrorCode.INTERNAL_ERROR, 'x', details={'reason': type(exc).__name__})\n"
    )
    plain = "def f(run_id):\n    raise OctopError(ErrorCode.INTERNAL_ERROR, 'x', details={'id': run_id})\n"

    assert scan_bare_exceptions(bad) == [("<synthetic>", "exc")]
    assert scan_bare_exceptions(attr) == [("<synthetic>", "exc.reason")]
    assert scan_bare_exceptions(good) == [], "类别串 `type(exc).__name__` 是修法本身，不得命中"
    assert scan_bare_exceptions(plain) == [], "普通标识符值不是异常对象，不得命中"


#: ★ 豁免面 = **唯一**减面，逐字 3 元组（`PLAN §5.1 @ 296-298` · `SPEC · A9`）。
#: 三条都是**活体安全站点**：`experts.py` / `skill_packages.py` 的值来自
#: `_SAFE_*_REASONS.get(...)` 枚举→安全串映射；`inbound_store.py` 的值是上一行赋的安全 f-string。
_EXEMPT = (
    ("api/routers/experts.py", "reason"),
    ("api/routers/skill_packages.py", "reason"),
    ("infra/gateway/media/inbound_store.py", "reason"),
)


def _scan_bare_tree() -> list[tuple[str, str]]:
    """全仓扫描（★ 不是 `_REMEDIATED_FILES` 四文件 —— `PLAN §5.1 @ 299` 逐字要求）。"""
    hits: list[tuple[str, str]] = []
    for path in sorted(_SRC.rglob("*.py")):
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):  # pragma: no cover
            continue
        try:
            hits += scan_bare_exceptions(source, path.relative_to(_SRC).as_posix())
        except SyntaxError:  # pragma: no cover
            continue
    return hits


def test_sec17a_exemption_surface_cannot_widen() -> None:
    """★★ `FIND-9`：豁免面**不得扩大**的全局可机判断言（`PLAN §5.1 @ 293-304`）。

    ★ **为什么「只管 `manager.py` 单文件」不够**：`test_b19_15_…` 第 3 条只约束
    `plugins/manager.py` **一个文件内**的站点数，**不覆盖豁免表的全局基数**；而豁免面是
    `SEC-17a` 判据**唯一的减面** ⇒ 只要把第 4 个文件写进 `_EXEMPT`，新的裸异常对象站点
    即可**静默通过**。⇒ 必须有一条「全仓扫描 ＋ 集合**逐字相等** ＋ **基数 = 3**」的断言
    把减面钉死（与单文件那条各自独立：前者钉全局减面，后者钉单文件内部）。
    """
    hits = _scan_bare_tree()
    # ① 集合**逐字相等**（`⊆` 不够）⇒ 加第 4 个文件 / 改一个字面量即红
    assert tuple(sorted(set(hits))) == _EXEMPT, f"豁免面被改动：{sorted(set(hits))}"
    # ② **基数 = 3** ⇒ 同一站点重复出现（减面的另一种写法）亦红
    assert len(hits) == len(_EXEMPT), f"豁免面基数变了：{hits}"


# ── ⑤ 值面钉桩 B + C + D（`PLAN §5.3` 选定组合；A 已弃）──────────────────────

_MANAGER_REL = "infra/agents/plugins/manager.py"

#: ★ B（四文件多重集指纹）：`(键, ast.unparse(值))` **排序元组**，逐项写死（**不哈希** ⇒
#: 红灯直接指出变动项）。★ 代价（卡面已写明）：任何**合法**的 `details` 变更都要同步本常量，
#: 否则维护噪声会变成"静默改常量"。
_EXPECTED_DETAILS_FINGERPRINT: tuple[tuple[str, str], ...] = (
    ("id", "manifest.id"),
    ("reason", "'url is required'"),
    ("reason", "'url missing hostname'"),
    ("reason", "'url must be http or https'"),
    ("reason", "f'HTTP {exc.code}'"),
    ("reason", "type(cause).__name__"),
    ("reason", "type(exc).__name__"),
    ("reason", "type(exc).__name__"),
    ("reason", "type(exc).__name__"),
    ("reason", "type(exc).__name__"),
    ("reason", "type(exc).__name__"),
    ("reason", "type(exc).__name__"),
    ("reason", "type(exc).__name__"),
    ("reason", "type(exc).__name__"),
    ("reason", "type(exc).__name__"),
    ("reason", "type(exc).__name__"),
    ("reason", "type(exc).__name__"),
    ("reason", "type(exc).__name__"),
    ("reason", "type(exc).__name__"),
    ("reason", "type(exc).__name__"),
)


def _details_pairs_in(rel: str) -> list[tuple[str, str]]:
    """该文件所有 `details={...}` 字面量的 `(键, ast.unparse(值))`（`**x` 键记 `<splat>`）。"""
    out: list[tuple[str, str]] = []
    tree = ast.parse((_SRC / rel).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if _is_octop_error(node):
            for kw in node.keywords:
                if kw.arg == "details" and isinstance(kw.value, ast.Dict):
                    for key, value in zip(kw.value.keys, kw.value.values, strict=True):
                        name = key.value if isinstance(key, ast.Constant) else "<splat>"
                        out.append((name, ast.unparse(value)))
    return out


def test_remediated_details_value_fingerprint_is_pinned() -> None:
    """★ B（广谱防退化）：四个受治文件的 `(键, unparse(值))` 排序元组逐项相等。

    替代被 `PLAN §5.3 @ 322` 判为**恒真、不承重**的 `assert values and all(values)`。
    """
    pairs: list[tuple[str, str]] = []
    for rel in _REMEDIATED_FILES:
        pairs += _details_pairs_in(rel)
    assert tuple(sorted(pairs)) == _EXPECTED_DETAILS_FINGERPRINT


def _find_func(tree: ast.Module, name: str) -> ast.FunctionDef | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def _reason_values_in(func: ast.AST) -> list[str]:
    out: list[str] = []
    for node in ast.walk(func):
        if _is_octop_error(node):
            for kw in node.keywords:
                if kw.arg == "details" and isinstance(kw.value, ast.Dict):
                    for key, value in zip(kw.value.keys, kw.value.values, strict=True):
                        if isinstance(key, ast.Constant) and key.value == "reason":
                            out.append(ast.unparse(value))
    return out


#: ★ C 的权威白集（`RESEARCH-T98-T99.md §5 @ 175` 逐字 3 元；`type(reason).__name__` 是
#: `PLAN.md` 的抄写漂移，**已作废** ⇒ 不得写进来，否则 `ANCHOR-MISSING`）。
_INSTALL_URL_ALLOWED_REASONS = {
    "type(exc).__name__",
    "type(cause).__name__",
    "f'HTTP {exc.code}'",
}


def test_install_url_reason_forms_are_pinned() -> None:
    """★ C（站点级锚定 · 主钉第 15 处）：锚 = `install_url` 的 **`FunctionDef`**，**不依赖行号**。

    把 `URLError` 分支改回 `details={"reason": str(reason)}` ⇒ `str(reason)` ∉ 白集 ⇒ **必红**
    （标记 `"str(reason"` 亦命中 ⇒ 双重红）。
    """
    tree = ast.parse((_SRC / _MANAGER_REL).read_text(encoding="utf-8"))
    func = _find_func(tree, "install_url")
    assert func is not None, "锚点 `install_url` 消失（改名/搬迁）⇒ 必须红，不得静默放过"
    forms = _reason_values_in(func)
    assert forms, "`install_url` 内没有 `reason` 的 details 字面量 ⇒ 锚点空洞化"
    assert set(forms) <= _INSTALL_URL_ALLOWED_REASONS, forms


def test_install_url_urlopen_failure_is_serializable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """★ D（运行时行为钉桩）：`urllib.request.urlopen` 抛 `URLError` 驱动 `install_url`。

    唯一**同时**覆盖「值不是异常原文」＋「`json.dumps(to_envelope)` 不抛」两面，且对
    helper 间接取值免疫（`SEC-17②` 的序列化面变成回归网）。
    """
    import json
    import urllib.error
    import urllib.request

    from octop.infra.agents.plugins.manager import PluginManager

    def _boom(*args: object, **kwargs: object) -> object:
        raise urllib.error.URLError(ValueError("raw secret /etc/passwd"))

    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    manager = PluginManager(plugins_dir=tmp_path / "plugins", config_path=tmp_path / "plugins.json")
    with pytest.raises(OctopError) as caught:
        manager.install_url("https://example.com/plugin.zip")

    details = caught.value.details
    assert details["reason"] == "ValueError", details  # 类别串，不是异常原文
    envelope = caught.value.to_envelope(locale="zh")
    rendered = json.dumps(envelope)  # ★ 不抛 = SEC-17 的序列化面
    assert "raw secret" not in rendered


# ── ⑥ `B-19-15` 显式断言（`PLAN §5.4` · `SPEC · A8` / `B13`）──────────────────

#: 允许 · 留痕的站点：`infra/agents/plugins/manager.py` 的唯一「以 `HTTP ` 起头的 f-string」。
_B19_15_HTTP_PREFIX = "f'HTTP "


def _is_exempt_reason_form(rendered: str) -> bool:
    """`B-19-15` 第 3 条的**豁免形态集**：f-string 形态 / `str(...)` / `repr(...)` / `.args` / 裸标识符。"""
    return (
        rendered.startswith(_B19_15_HTTP_PREFIX)
        or any(marker in rendered for marker in ("str(", "repr(", ".args"))
        or rendered in _BARE_PAYLOAD_ROOTS
    )


def test_b19_15_allowlisted_reason_is_human_readable() -> None:
    """★ `B-19-15` 的三条显式断言（**全不依赖行号**；锚 = 字面前缀 `HTTP ` ＋ 属性 `exc.code`）。

    ① **基数**（防删 · 防误改）：`manager.py` 内 `reason` 值为「以 `HTTP ` 起头的 f-string」的
       `details` 站点**恰好 1 处**；
    ② **值形态**（钉形状）：该值 `ast.unparse(v)` **逐字等于** `f'HTTP {exc.code}'`；
    ③ **豁免面（本文件内）**：同文件其它 `reason` 值**不落**豁免集，且本文件被豁免站点数 == 1。
    ★ 第 3 条**只钉本文件基数** ⇒ 全局减面由 `test_sec17a_exemption_surface_cannot_widen` 独立承担。
    """
    values = _reason_values_in(ast.parse((_SRC / _MANAGER_REL).read_text(encoding="utf-8")))

    http_sites = [value for value in values if value.startswith(_B19_15_HTTP_PREFIX)]
    assert len(http_sites) == 1, f"`HTTP ` 起头站点必须恰好 1 处：{http_sites}"  # ① 基数
    assert http_sites == ["f'HTTP {exc.code}'"], http_sites  # ② 逐字形态

    exempt = [value for value in values if _is_exempt_reason_form(value)]
    assert exempt == http_sites, f"本文件被豁免的站点数必须 == 1：{exempt}"  # ③ 豁免面
    others = [value for value in values if value not in http_sites]
    assert [value for value in others if _is_exempt_reason_form(value)] == [], others


# ── ⑦ `SEC-9`：禁止 skip / xfail（防「用例被跳过 ⇒ 差集假绿」）────────────────

#: 承重用例清单（任一条被 `skip`/`xfail` ⇒ 本文件的"绿"就不再是证据）。
_KEY_CASES = (
    "test_details_with_a_code_key_passes_through_to_envelope",
    "test_no_unknown_blacklist_hits",
    "test_known_blacklist_entries_are_still_present",
    "test_known_blacklist_violations_is_empty",
    "test_remediated_details_still_carry_a_machine_readable_category",
    "test_t98_new_markers_catch_their_forms",
    "test_sec17a_bare_exception_value_is_flagged",
    "test_sec17a_exemption_surface_cannot_widen",
    "test_remediated_details_value_fingerprint_is_pinned",
    "test_install_url_reason_forms_are_pinned",
    "test_install_url_urlopen_failure_is_serializable",
    "test_b19_15_allowlisted_reason_is_human_readable",
)


def test_key_cases_are_not_skipped_or_xfailed() -> None:
    """★ `SEC-9` 护栏：本文件的关键用例**没有被** `skip`/`skipif`/`xfail`（含 `pytestmark`）。"""
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    defined = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
    assert set(_KEY_CASES) <= defined, f"承重用例消失：{sorted(set(_KEY_CASES) - defined)}"

    banned: list[tuple[str, str]] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            for decorator in node.decorator_list:
                text = ast.unparse(decorator)
                if "skip" in text or "xfail" in text:
                    banned.append((node.name, text))
        if isinstance(node, ast.Assign):
            for target in node.targets:
                assert getattr(target, "id", None) != "pytestmark", "`pytestmark` 会批量跳过模块"
    assert banned == [], f"承重用例被 skip/xfail：{banned}"
