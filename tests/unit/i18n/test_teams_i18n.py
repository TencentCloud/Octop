"""T-23 · 团队拒绝码的 i18n 契约（**三处一致 + zh/en 逐键**）。

## 三处是哪三处
| # | 位置 | 命名空间 |
|---|---|---|
| ① | `src/octop/infra/errors.py` · `ErrorCode` | 码的**定义源**（`TEAM_*`） |
| ② | `src/octop/i18n/{zh,en}.json` | `errors.<CODE>`（后端 `error_message()` 用） |
| ③ | `dashboard/src/locales/{zh,en}.json` | `apiErrors.<CODE>`（前端 `apiError.ts` 用） |

`AGENTS.md` 已把 ②↔③ 定为硬约束（"tests require backend and frontend keys to match"），
本文件把它**收窄到团队那一组码**并**逐键钉住 zh 值**，因为团队拒绝码是**用户唯一的
可操作提示来源** —— 文案漂移不会让任何测试变红，只会让用户看到一句话说不清的拒绝。

## 两条独立命令（**不得合并成一条**）
```bash
uv run pytest tests/unit/i18n/test_teams_i18n.py -q -k zh    # 中文面
uv run pytest tests/unit/i18n/test_teams_i18n.py -q -k en    # 英文面
```
## ★ 为什么**禁用 for 循环守卫**
写成 `for locale in ("zh", "en"): assert ...` 会有两个后果：① **哪一面坏了只看得到
第一条**（循环在第一次失败处中断，第二面根本没跑）；② **无法单独跑一面** ——
"zh/en 各一条独立命令"这个要求本身就是"两面必须能分别判定"。
所以本文件**一个 for 循环都没有**：每个 locale 有自己的用例，每个码有自己的 `assert`。
（集合级的一致性用**集合相等**表达，那是在"码的集合"上比较，不是在 locale 上循环。）

**登记**：`backend-2` 的 `test_team_learnings.py` 与本文无关（那是记忆契约）；
本文件的 41 个 `TEAM_*` 码是 `ErrorCode` 的**团队子集**。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from octop.infra.errors import ErrorCode

_REPO = Path(__file__).resolve().parents[3]


def _load(rel: str) -> dict[str, Any]:
    return json.loads((_REPO / rel).read_text(encoding="utf-8"))


def _team_codes() -> set[str]:
    return {c.value for c in ErrorCode if c.value.startswith("TEAM_")}


_BACKEND_ZH = _load("src/octop/i18n/zh.json")["errors"]
_BACKEND_EN = _load("src/octop/i18n/en.json")["errors"]
_DASH_ZH = _load("dashboard/src/locales/zh.json")["apiErrors"]
_DASH_EN = _load("dashboard/src/locales/en.json")["apiErrors"]


# ─────────────────────────────────────────────────────────────────────────────
# 三处一致（集合级；不在 locale 上循环）
# ─────────────────────────────────────────────────────────────────────────────


def test_the_team_codes_are_present_in_all_four_files() -> None:
    codes = _team_codes()
    assert codes, "ErrorCode 里一个 TEAM_* 都没有 —— 本文件会变成空断言"

    backend_zh = codes & set(_BACKEND_ZH)
    backend_en = codes & set(_BACKEND_EN)
    dash_zh = codes & set(_DASH_ZH)
    dash_en = codes & set(_DASH_EN)

    assert backend_zh == codes, f"后端 zh 缺：{sorted(codes - backend_zh)}"
    assert backend_en == codes, f"后端 en 缺：{sorted(codes - backend_en)}"
    assert dash_zh == codes, f"dashboard zh 缺：{sorted(codes - dash_zh)}"
    assert dash_en == codes, f"dashboard en 缺：{sorted(codes - dash_en)}"


def test_backend_zh_and_en_carry_the_same_team_codes() -> None:
    """zh/en 的团队码集合必须相等（缺席一面 = 该面用户看到 fallback 或原文码）。"""
    assert sorted(_team_codes() & set(_BACKEND_ZH)) == sorted(_team_codes() & set(_BACKEND_EN))


def test_dashboard_zh_and_en_carry_the_same_team_codes() -> None:
    assert sorted(_team_codes() & set(_DASH_ZH)) == sorted(_team_codes() & set(_DASH_EN))


def test_nothing_outside_the_team_prefix_is_asserted_here() -> None:
    """防止本文件被"顺手扩到全部 36/41 码"而掩盖团队面 —— 团队面就是 TEAM_*。"""
    assert all(c.startswith("TEAM_") for c in _team_codes())


# ─────────────────────────────────────────────────────────────────────────────
# zh 逐键断言（每码一行；无循环）
# ─────────────────────────────────────────────────────────────────────────────


def test_zh_gate_refusals_are_the_frozen_text() -> None:
    assert _BACKEND_ZH["TEAM_PHASE_GATE_FAILED"] == "当前阶段门禁未通过。"
    assert _BACKEND_ZH["TEAM_DECISION_PENDING"] == "存在待拍板决策，须先处理。"
    assert (
        _BACKEND_ZH["TEAM_SPEC_BOUNDARY_EMPTY"] == "规格的「边界与禁止项」为空，不得进入实现阶段。"
    )
    assert _BACKEND_ZH["TEAM_TASK_DEPS_UNMET"] == "上游任务尚未完成。"
    assert _BACKEND_ZH["TEAM_TASK_GRAPH_INVALID"] == "任务依赖图不合法。"
    assert _BACKEND_ZH["TEAM_SCOPE_VIOLATION"] == "变更文件超出任务范围。"


def test_zh_artifact_and_review_refusals_are_the_frozen_text() -> None:
    assert _BACKEND_ZH["TEAM_ARTIFACT_STALE"] == "工件已被他人修改，请重新加载后重试。"
    assert _BACKEND_ZH["TEAM_ARTIFACT_OWNERSHIP_DENIED"] == "你不是该工件的归属写者。"
    assert _BACKEND_ZH["TEAM_REVIEW_SELF_AUDIT"] == "审查者不得审查自己的产出。"
    assert _BACKEND_ZH["TEAM_FINDING_REOPENED"] == "同一问题连续两轮未闭环，须升级用户裁决。"


def test_zh_capacity_and_tier_refusals_are_the_frozen_text() -> None:
    assert _BACKEND_ZH["TEAM_RUN_MEMBER_LIMIT"] == "本次运行的成员数已达上限。"
    assert _BACKEND_ZH["TEAM_TIER_INVALID"] == "档位无法识别，不做猜测也不静默回退默认值。"
    assert _BACKEND_ZH["TEAM_ROLE_UNKNOWN"] == "该角色不在固定角色表内。"


def test_zh_dashboard_mirrors_every_asserted_backend_value() -> None:
    """逐键核对 dashboard 的 zh 与后端 zh **同字** —— 不是"存在即可"。"""
    assert _DASH_ZH["TEAM_PHASE_GATE_FAILED"] == _BACKEND_ZH["TEAM_PHASE_GATE_FAILED"]
    assert _DASH_ZH["TEAM_DECISION_PENDING"] == _BACKEND_ZH["TEAM_DECISION_PENDING"]
    assert _DASH_ZH["TEAM_SPEC_BOUNDARY_EMPTY"] == _BACKEND_ZH["TEAM_SPEC_BOUNDARY_EMPTY"]
    assert _DASH_ZH["TEAM_TASK_DEPS_UNMET"] == _BACKEND_ZH["TEAM_TASK_DEPS_UNMET"]
    assert _DASH_ZH["TEAM_TASK_GRAPH_INVALID"] == _BACKEND_ZH["TEAM_TASK_GRAPH_INVALID"]
    assert _DASH_ZH["TEAM_SCOPE_VIOLATION"] == _BACKEND_ZH["TEAM_SCOPE_VIOLATION"]
    assert _DASH_ZH["TEAM_ARTIFACT_STALE"] == _BACKEND_ZH["TEAM_ARTIFACT_STALE"]
    assert (
        _DASH_ZH["TEAM_ARTIFACT_OWNERSHIP_DENIED"] == _BACKEND_ZH["TEAM_ARTIFACT_OWNERSHIP_DENIED"]
    )
    assert _DASH_ZH["TEAM_REVIEW_SELF_AUDIT"] == _BACKEND_ZH["TEAM_REVIEW_SELF_AUDIT"]
    assert _DASH_ZH["TEAM_FINDING_REOPENED"] == _BACKEND_ZH["TEAM_FINDING_REOPENED"]
    assert _DASH_ZH["TEAM_RUN_MEMBER_LIMIT"] == _BACKEND_ZH["TEAM_RUN_MEMBER_LIMIT"]
    assert _DASH_ZH["TEAM_TIER_INVALID"] == _BACKEND_ZH["TEAM_TIER_INVALID"]
    assert _DASH_ZH["TEAM_ROLE_UNKNOWN"] == _BACKEND_ZH["TEAM_ROLE_UNKNOWN"]


# ─────────────────────────────────────────────────────────────────────────────
# en 逐键断言（每码一行；无循环）
# ─────────────────────────────────────────────────────────────────────────────


def test_en_gate_refusals_are_the_frozen_text() -> None:
    assert _BACKEND_EN["TEAM_PHASE_GATE_FAILED"] == "The current phase gate is not satisfied."
    assert _BACKEND_EN["TEAM_DECISION_PENDING"] == "A pending decision must be resolved first."
    assert (
        _BACKEND_EN["TEAM_SPEC_BOUNDARY_EMPTY"]
        == "The spec boundary table is empty; implementation cannot start."
    )
    assert _BACKEND_EN["TEAM_TASK_DEPS_UNMET"] == "Upstream tasks are not done yet."
    assert _BACKEND_EN["TEAM_TASK_GRAPH_INVALID"] == "The task graph is invalid."
    assert _BACKEND_EN["TEAM_SCOPE_VIOLATION"] == "Changed paths fall outside the task scope."


def test_en_artifact_and_review_refusals_are_the_frozen_text() -> None:
    assert (
        _BACKEND_EN["TEAM_ARTIFACT_STALE"]
        == "The artifact was changed by someone else; reload and retry."
    )
    assert (
        _BACKEND_EN["TEAM_ARTIFACT_OWNERSHIP_DENIED"] == "You are not the owner of this artifact."
    )
    assert _BACKEND_EN["TEAM_REVIEW_SELF_AUDIT"] == "A reviewer cannot audit their own output."
    assert (
        _BACKEND_EN["TEAM_FINDING_REOPENED"]
        == "The same finding is still open across two rounds; escalate to the user."
    )


def test_en_capacity_and_tier_refusals_are_the_frozen_text() -> None:
    assert _BACKEND_EN["TEAM_RUN_MEMBER_LIMIT"] == "The run member limit has been reached."
    assert (
        _BACKEND_EN["TEAM_TIER_INVALID"] == "Unknown tier; it is not guessed or silently defaulted."
    )
    assert _BACKEND_EN["TEAM_ROLE_UNKNOWN"] == "The role is not in the fixed role table."


def test_en_dashboard_mirrors_every_asserted_backend_value() -> None:
    assert _DASH_EN["TEAM_PHASE_GATE_FAILED"] == _BACKEND_EN["TEAM_PHASE_GATE_FAILED"]
    assert _DASH_EN["TEAM_DECISION_PENDING"] == _BACKEND_EN["TEAM_DECISION_PENDING"]
    assert _DASH_EN["TEAM_SPEC_BOUNDARY_EMPTY"] == _BACKEND_EN["TEAM_SPEC_BOUNDARY_EMPTY"]
    assert _DASH_EN["TEAM_TASK_DEPS_UNMET"] == _BACKEND_EN["TEAM_TASK_DEPS_UNMET"]
    assert _DASH_EN["TEAM_TASK_GRAPH_INVALID"] == _BACKEND_EN["TEAM_TASK_GRAPH_INVALID"]
    assert _DASH_EN["TEAM_SCOPE_VIOLATION"] == _BACKEND_EN["TEAM_SCOPE_VIOLATION"]
    assert _DASH_EN["TEAM_ARTIFACT_STALE"] == _BACKEND_EN["TEAM_ARTIFACT_STALE"]
    assert (
        _DASH_EN["TEAM_ARTIFACT_OWNERSHIP_DENIED"] == _BACKEND_EN["TEAM_ARTIFACT_OWNERSHIP_DENIED"]
    )
    assert _DASH_EN["TEAM_REVIEW_SELF_AUDIT"] == _BACKEND_EN["TEAM_REVIEW_SELF_AUDIT"]
    assert _DASH_EN["TEAM_FINDING_REOPENED"] == _BACKEND_EN["TEAM_FINDING_REOPENED"]
    assert _DASH_EN["TEAM_RUN_MEMBER_LIMIT"] == _BACKEND_EN["TEAM_RUN_MEMBER_LIMIT"]
    assert _DASH_EN["TEAM_TIER_INVALID"] == _BACKEND_EN["TEAM_TIER_INVALID"]
    assert _DASH_EN["TEAM_ROLE_UNKNOWN"] == _BACKEND_EN["TEAM_ROLE_UNKNOWN"]


# ─────────────────────────────────────────────────────────────────────────────
# 两面确实不同（防止"en 抄 zh"这类静默缺陷）
# ─────────────────────────────────────────────────────────────────────────────


def test_zh_and_en_are_not_the_same_text_for_the_asserted_codes() -> None:
    """若某次改动把 en 直接写成 zh（或反之），上面两组逐键断言会**双双通过** ——
    因为它们各自比对的是"自己那一面"，只要两面**同时**被写成同一个值就都不报错。
    这条补上那个盲区：两面必须**确实不同**。
    """
    assert _BACKEND_ZH["TEAM_PHASE_GATE_FAILED"] != _BACKEND_EN["TEAM_PHASE_GATE_FAILED"]
    assert _BACKEND_ZH["TEAM_DECISION_PENDING"] != _BACKEND_EN["TEAM_DECISION_PENDING"]
    assert _BACKEND_ZH["TEAM_SPEC_BOUNDARY_EMPTY"] != _BACKEND_EN["TEAM_SPEC_BOUNDARY_EMPTY"]
    assert _BACKEND_ZH["TEAM_ARTIFACT_STALE"] != _BACKEND_EN["TEAM_ARTIFACT_STALE"]
    assert (
        _BACKEND_ZH["TEAM_ARTIFACT_OWNERSHIP_DENIED"]
        != _BACKEND_EN["TEAM_ARTIFACT_OWNERSHIP_DENIED"]
    )
    assert _BACKEND_ZH["TEAM_REVIEW_SELF_AUDIT"] != _BACKEND_EN["TEAM_REVIEW_SELF_AUDIT"]


def test_the_zh_values_are_not_left_as_the_bare_code() -> None:
    """缺键时 i18n 会回退成原文码；值等于码本身就是"没翻译"的形态。"""
    assert _BACKEND_ZH["TEAM_PHASE_GATE_FAILED"] != "TEAM_PHASE_GATE_FAILED"
    assert _BACKEND_ZH["TEAM_ROLE_UNKNOWN"] != "TEAM_ROLE_UNKNOWN"
    assert _BACKEND_EN["TEAM_PHASE_GATE_FAILED"] != "TEAM_PHASE_GATE_FAILED"
    assert _BACKEND_EN["TEAM_ROLE_UNKNOWN"] != "TEAM_ROLE_UNKNOWN"
