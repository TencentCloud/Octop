"""T2 · 计划门控的 2 个**新**拒绝码：定义源 / 状态映射 / en·zh 文案。

权威 = `team/2026-09-29-234500/PLAN.md` §2.4 拒绝码与状态（本批只新增 2 个）
＋ `SPEC.md` §5 边界表 B1 / B4（逐字中文与英文文案）。

| 码 | HTTP | 语义 | 逐字文案 |
|---|---|---|---|
| `TEAM_PLAN_DRAFT_INVALID` | 422 | 草稿非法（owner 不在 roles / 图非法 / 空 tasks / scope 空…） | zh「计划草稿非法：任务负责人不在角色清单内」/ en「plan draft invalid: task owner is not in the role list」 |
| `TEAM_PLAN_DRAFT_MISSING` | 409 | 无草稿可批 / 可丢（含重复） | zh「没有待批准的计划草稿」/ en「no plan draft awaiting approval」 |

本批**只**允许这 2 个新码（`grep -c TEAM_PLAN_DRAFT src/octop/infra/errors.py` == 2）：
「无可清算」不新增码、`check` 不加违规码 —— 见 PLAN §2.4 尾注 / SPEC §0-D6。

**仅本地可观测**：本文件只读仓库内的 3 个文件（`infra/errors.py` 经 import、
`i18n/{en,zh}.json`），不起服务、不碰 DB。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from octop.i18n import error_message
from octop.infra.errors import _DEFAULT_STATUS, ErrorCode, OctopError

# ── 逐字文案（真源 SPEC.md §5 B1 / B4，不得改写）─────────────────────────────
FROZEN_ZH: dict[str, str] = {
    "TEAM_PLAN_DRAFT_INVALID": "计划草稿非法：任务负责人不在角色清单内",
    "TEAM_PLAN_DRAFT_MISSING": "没有待批准的计划草稿",
}
FROZEN_EN: dict[str, str] = {
    "TEAM_PLAN_DRAFT_INVALID": "plan draft invalid: task owner is not in the role list",
    "TEAM_PLAN_DRAFT_MISSING": "no plan draft awaiting approval",
}
# PLAN §2.4 状态映射：INVALID → 422、MISSING → 409。
FROZEN_STATUS: dict[str, int] = {
    "TEAM_PLAN_DRAFT_INVALID": 422,
    "TEAM_PLAN_DRAFT_MISSING": 409,
}

_REPO = Path(__file__).resolve().parents[3]
_NEW_CODES = ("TEAM_PLAN_DRAFT_INVALID", "TEAM_PLAN_DRAFT_MISSING")


def _load(rel: str) -> dict[str, Any]:
    return json.loads((_REPO / rel).read_text(encoding="utf-8"))


def test_plan_draft_codes_are_error_code_members() -> None:
    """两个码必须是 ``ErrorCode`` 成员（码的唯一定义源 = `infra/errors.py`）。"""
    for code in _NEW_CODES:
        assert code in ErrorCode.__members__, f"ErrorCode 缺少 {code}"
        assert ErrorCode[code].value == code


def test_no_third_plan_draft_code_was_invented() -> None:
    """★ 本批只允许 2 个新码：多造一个（例如 `TEAM_PLAN_DRAFT_CONFLICT`）即红。"""
    found = sorted(c.value for c in ErrorCode if "PLAN_DRAFT" in c.value)
    assert found == sorted(_NEW_CODES), f"PLAN_DRAFT 码集应为 {sorted(_NEW_CODES)}，实际 {found}"


def test_plan_draft_status_mapping_matches_plan() -> None:
    """★ 状态映射逐字按 PLAN §2.4：422 / 409（不是笼统的 400）。"""
    for code, status in FROZEN_STATUS.items():
        member = ErrorCode[code]
        assert _DEFAULT_STATUS[member] == status, f"{code} 应为 {status}"
        assert OctopError(member, "raw detail").status == status, (
            f"{code} 的 OctopError.status 应为 {status}"
        )


def test_plan_draft_codes_are_localized_in_en_and_zh_bundles() -> None:
    """两个码在 en/zh **两本**后端 bundle 里都要有键，且不得为空。"""
    for locale, rel in (("en", "src/octop/i18n/en.json"), ("zh", "src/octop/i18n/zh.json")):
        errors = _load(rel)["errors"]
        for code in _NEW_CODES:
            assert errors.get(code), f"{locale} errors.{code} 缺失或为空"


def test_plan_draft_copy_is_verbatim_zh() -> None:
    """★ 中文逐字（SPEC §5 B1 / B4）—— 漂移即红。"""
    errors = _load("src/octop/i18n/zh.json")["errors"]
    for code, text in FROZEN_ZH.items():
        assert errors[code] == text, code
        assert error_message(code, "zh") == text, code


def test_plan_draft_copy_is_verbatim_en() -> None:
    """★ 英文逐字（SPEC §5 B1 / B4）—— 漂移即红。"""
    errors = _load("src/octop/i18n/en.json")["errors"]
    for code, text in FROZEN_EN.items():
        assert errors[code] == text, code
        assert error_message(code, "en") == text, code


def test_plan_draft_keys_sit_inside_the_errors_namespace() -> None:
    """★ 键必须落在**既有 `errors` 命名空间内部**，不得另起顶层键或落到文件末尾。"""
    for rel in ("src/octop/i18n/en.json", "src/octop/i18n/zh.json"):
        bundle = _load(rel)
        assert "errors" in bundle
        for code in _NEW_CODES:
            assert code in bundle["errors"], f"{rel} 的 {code} 不在 errors 命名空间内"
            assert code not in bundle, f"{rel} 的 {code} 不得作为顶层键重复定义"


def test_backend_en_and_zh_key_trees_stay_identical() -> None:
    """★ en/zh 两侧键树保持一致（新增这 2 个键不得破坏既有对齐）。"""
    en = _load("src/octop/i18n/en.json")
    zh = _load("src/octop/i18n/zh.json")

    def tree(value: object) -> object:
        return {k: tree(v) for k, v in value.items()} if isinstance(value, dict) else True

    assert tree(en) == tree(zh)
    assert set(en["errors"]) == set(zh["errors"])


def test_plan_draft_tokens_carry_no_python_style_braces() -> None:
    """文案里不得出现 ``{name}`` 占位符（这两条文案无插值参数）。"""
    for text in (*FROZEN_ZH.values(), *FROZEN_EN.values()):
        assert "{" not in text and "}" not in text, text


def test_error_envelope_carries_the_localized_message() -> None:
    """``OctopError.localized_message`` 走 ``errors.<CODE>``，两码各回本地化文案。"""
    for code in _NEW_CODES:
        for locale, frozen in (("zh", FROZEN_ZH), ("en", FROZEN_EN)):
            assert (
                OctopError(ErrorCode[code], "raw detail").localized_message(locale)
                == (frozen[code])
            ), (code, locale)
