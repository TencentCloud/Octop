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

#: ★ 既有（**本卡之前就有**）的黑名单命中：`str(exc)` 进了 `details`。
#: 它们**不在** T-75 的「本轮新增/改动」集合里（`T-75` 只要求**新增/改动**的 details 干净），
#: 且修它们会改这些端点的响应体 ⇒ **只登记不代改**，已上报 lead。
#: **双向绑定**：清单里的条目若已修好 ⇒ 测试红（强迫清单在收敛时变短）；
#: 新出现的命中 ⇒ 测试红。
_KNOWN_BLACKLIST_VIOLATIONS = {
    "src/octop/api/routers/connectors.py:727": "既有：连接器 MCP 错误回传上游原文",
    "src/octop/api/routers/connectors.py:847": "既有",
    "src/octop/api/routers/connectors.py:1011": "既有",
    "src/octop/api/routers/connectors.py:1090": "既有",
    "src/octop/api/routers/connectors.py:1117": "既有",
    "src/octop/api/routers/connectors.py:1143": "既有",
    "src/octop/api/routers/connectors.py:1169": "既有",
    "src/octop/api/routers/plugins.py:147": "既有",
    "src/octop/api/routers/plugins.py:189": "既有",
    "src/octop/api/routers/plugins.py:235": "既有",
    "src/octop/infra/agents/plugins/manager.py:523": "既有",
    "src/octop/infra/agents/plugins/manager.py:626": "既有",
    "src/octop/infra/agents/plugins/manager.py:692": "既有",
    "src/octop/infra/connectors/custom_mcp.py:161": "既有",
}

#: 黑名单**值**的形态（A6）：异常原文不得进 `details`。
_BLACKLISTED_VALUE_MARKERS = ("str(exc", "str(err", "{exc}", "{err}", "traceback", "Traceback")


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
