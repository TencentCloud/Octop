"""R1 工件归属硬门禁的纯函数内核（`teams/artifacts.py`）。

本文件是 **G1 门禁**的契约测试，同时被两个任务共用：

* **T-11** —— 本文件当前的全部内容：`artifacts.py` 的纯函数（归属表 / 模板清单 / 路径作用域）。
* **T-12** —— 中间件 `TeamArtifactOwnershipMiddleware` 的用例，**追加在文件末尾**，
  **不要改动本节已有的断言**（T-11/T-12 写区重叠，已在任务书写明）。

★ **角色词表的冻结约定（task-44）**：角色词表的**唯一权威 = `pipeline.py · ROLES`**，
`artifacts.TEAM_ROLES` 只是它的 `frozenset` 投影。**`pipeline.ROLES` 的名字与内容自 task-44
起冻结** —— 任何人要改它，**必须同时显式更新本文件顶部的 `EXPECTED_ROLES`**。
为什么：`owner_violation` 对「认不出的角色」是 **fail-open**，两表分叉会让多出的那个角色
**可以覆写任何人的工件**（权限绕过）；而收口之后「两边相等」是结构上恒真的，
只有 `EXPECTED_ROLES` 这个**独立真值**才能让护栏继续变异得红。
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import ToolMessage

from octop.infra.agents.middleware.team_artifact_ownership import (
    EVENT_OWNERSHIP_DEGRADED,
    EVENT_OWNERSHIP_DENIED,
    OwnershipGateDeps,
    TeamArtifactOwnershipMiddleware,
)
from octop.infra.agents.teams import artifacts as art
from octop.infra.db.repos.project_artifacts import ATTACHMENT_KIND

# ─────────────────────────────────────────────────────────────────────────────
# T-11 · artifacts.py（纯函数：归属表 / 模板清单 / 路径作用域）
#   ↓ 以下为 T-11 的用例；T-12 的中间件用例请追加在本节之后。
# ─────────────────────────────────────────────────────────────────────────────

RUN_ID = "2026-09-28-145847"


def _run_root(tmp_path: Path) -> Path:
    """团队 host 工作区下的 run 根（`team_runs.run_root` 解析出的那个根，不是 run 目录）。"""
    return tmp_path / "team"


# ── 归属表本身 ───────────────────────────────────────────────────────────────


def test_artifact_owners_is_immutable() -> None:
    """归属表是门禁的真源 ⇒ 运行时不得被改写。"""
    with pytest.raises(TypeError):
        art.ARTIFACT_OWNERS["SPEC.md"] = ("backend",)  # type: ignore[index]


def test_artifact_owners_values_are_known_roles() -> None:
    """表里出现的每个角色都必须是真的角色 —— 否则门禁会静默失配。"""
    listed = {role for owners in art.ARTIFACT_OWNERS.values() for role in owners}
    assert listed <= art.TEAM_ROLES
    assert art.KNOWN_ROLES == art.TEAM_ROLES


#: **测试侧的独立真值** —— 12 个固定角色的第三份拷贝，但它**故意不 import 任何被测模块**。
#:
#: 为什么必须有它：收口（task-44）之后 `artifacts.TEAM_ROLES` 变成 `pipeline.ROLES` 的**转发**，
#: 此时「两边相等」是**结构上恒真**的 ⇒ 只写相等的护栏**再也无法变异成红**，而 task-44 的验收②
#: 恰恰要求「给 pipeline 词表加一个角色 ⇒ 护栏必须红」。有了本真值，加角色会让
#: `pipeline.ROLES != EXPECTED_ROLES` ⇒ **收口后仍然能红**。
EXPECTED_ROLES: frozenset[str] = frozenset(
    {
        "pm",
        "architect",
        "researcher",
        "ui",
        "backend",
        "frontend",
        "dba",
        "sec",
        "reviewer",
        "qa",
        "devops",
        "docs",
    }
)


def test_team_roles_is_exactly_the_twelve_fixed_roles() -> None:
    assert len(art.TEAM_ROLES) == 12
    assert art.TEAM_ROLES == EXPECTED_ROLES


def _assert_role_vocabulary_has_one_authority() -> None:
    """护栏主体：三方对账（独立真值 / `pipeline.ROLES` / `artifacts.TEAM_ROLES`）。

    `pipeline` 在**函数内**导入，保证 `monkeypatch` 变异能真的作用到判定上
    （写成模块级导入的话，变异证据就是假的）。
    """
    from octop.infra.agents.teams import pipeline

    assert set(pipeline.ROLES) == EXPECTED_ROLES, (
        "pipeline.ROLES 与固定 12 角色不符"
        f"：多={sorted(set(pipeline.ROLES) - EXPECTED_ROLES)}"
        f" 少={sorted(EXPECTED_ROLES - set(pipeline.ROLES))}"
    )
    assert art.TEAM_ROLES == EXPECTED_ROLES, (
        "artifacts.TEAM_ROLES 与固定 12 角色不符"
        f"：多={sorted(art.TEAM_ROLES - EXPECTED_ROLES)}"
        f" 少={sorted(EXPECTED_ROLES - art.TEAM_ROLES)}"
    )
    assert set(pipeline.ROLES) == art.TEAM_ROLES


def test_role_vocabulary_has_one_authority() -> None:
    """**漂移护栏**（安全相关，不是风格检查）。

    12 个角色的词表当前存在**两处**：`pipeline.py · ROLES`（T-10）与本模块的 `TEAM_ROLES`（T-11）。
    `owner_violation` 对「认不出的角色」是 **fail-open**：若 `pipeline.ROLES` 新增了第 13 个角色
    而 artifacts 侧没跟上，那个角色在归属门禁里就变成「认不出」⇒ **可以覆写任何人的工件**。
    ⇒ 一旦分叉，本用例必须变红。

    根治办法（task-44，lead 已定方向）：artifacts 侧**转发** `pipeline.ROLES`，只留一份。
    护栏刻意**不**只靠「两边相等」—— 收口之后那条是结构上恒真的，见
    :func:`test_role_vocabulary_drift_is_mutation_detectable`。
    """
    _assert_role_vocabulary_has_one_authority()


def test_role_vocabulary_drift_is_mutation_detectable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**变异证据**（task-44 验收②要求）：给 `pipeline.ROLES` 加第 13 个角色 ⇒ 护栏必须红。

    这条同时是护栏的**判别力证明**：它先确认未变异时是绿的，再把 `pipeline.ROLES` 换成 13 个角色，
    断言护栏确实抛 `AssertionError`。若护栏退化回「只比较两边相等」，收口后本用例会红 —— 这正是
    想要的（那种护栏在收口后失去判别力）。
    """
    from octop.infra.agents.teams import pipeline

    # 先确认未变异时是绿的 —— 否则下面的 `pytest.raises` 是假阳性。
    _assert_role_vocabulary_has_one_authority()
    monkeypatch.setattr(pipeline, "ROLES", (*pipeline.ROLES, "auditor"))
    with pytest.raises(AssertionError):
        _assert_role_vocabulary_has_one_authority()


def test_team_roles_is_a_forwarding_projection_not_a_second_definition() -> None:
    """**验收① 的结构化版本**：artifacts 侧那一行必须是**转发表达式**，不是第二份定义。

    task-44 的机检是 `grep -rn "TEAM_ROLES\\s*[:=]\\|^ROLES\\s*[:=]"`，收口后它**必然命中 2 行** ——
    因为 Python 里没有「只 import 不赋值」的转发形态：写 `from … import ROLES as TEAM_ROLES`
    会把公开类型从 `frozenset[str]` 变成 `tuple`（`KNOWN_ROLES` 的 `|` 运算与 T-12/T-13 的既有
    契约都会跟着变），所以只能写一次 `TEAM_ROLES = frozenset(ROLES)`。**那条 grep 数的是「赋值
    语句」，不是「角色定义」** —— 本用例给出能区分二者的判据：

    1. `TEAM_ROLES` 的**右边必须引用 `ROLES`**（是转发）；
    2. 右边**不得出现任何角色字面量**（不是第二份定义）。

    这样「两处定义」与「一处定义 + 一处投影」在机检上就分得开了。
    """
    source = Path(art.__file__).read_text(encoding="utf-8")
    match = re.search(r"^TEAM_ROLES[^=\n]*=\s*(.+)$", source, re.MULTILINE)
    assert match is not None, "artifacts.py 里找不到 TEAM_ROLES 的赋值语句"
    rhs = match.group(1)
    assert "ROLES" in rhs, f"TEAM_ROLES 不是转发表达式（右边未引用 ROLES）：{rhs!r}"
    for role in sorted(EXPECTED_ROLES):
        assert f'"{role}"' not in rhs, f"TEAM_ROLES 的右边出现了角色字面量 {role!r}：{rhs!r}"


def _imported_modules(path: str | Path) -> list[str]:
    """AST 取出一个 Python 文件的**真实 import 语句**所指的模块。

    为什么不用字面 `grep`：**「禁止 X」的检查会被自己的说明文字命中**。本仓已出现两次 ——
    ① `multi_ns`/`backend` 那类「不 import repos」的 docstring 里就写着 `repos`；
    ② 断言 docstring 复现了它要匹配的形态。⇒ 一律查 AST，不查文本。
    """
    import ast

    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.append(node.module)
    assert modules, f"AST 没解析出任何 import —— 检查本身失效了（假绿灯）：{path}"
    return modules


def test_pipeline_does_not_import_artifacts() -> None:
    """反向依赖必须为 0：`pipeline.py` → `artifacts.py` 会成环（artifacts 已正向 import）。

    **用 AST 而不是字面匹配**：`pipeline.py` 的 `ROLES` 注释里逐字写着
    「This module must therefore never import ``artifacts``」—— 一旦有人把那句写成不带反引号的
    `never import artifacts`，字面断言就会**因为说明文字而假红**（本仓纪律：禁止 X 的检查不得
    被自己的说明命中）。
    """
    from octop.infra.agents.teams import pipeline

    modules = _imported_modules(pipeline.__file__)
    assert "octop.infra.agents.teams.artifacts" not in modules, modules
    assert not [name for name in modules if name.endswith("artifacts")], modules


@pytest.mark.parametrize(
    ("base", "owners"),
    [
        ("SPEC.md", ("pm",)),
        ("RESEARCH.md", ("researcher",)),
        ("REVIEW.md", ("reviewer",)),
        ("REVIEW-SPEC.md", ("reviewer",)),
        ("TEST.md", ("qa",)),
        ("UI.md", ("ui",)),
        ("DATA.md", ("dba",)),
        ("SECURITY.md", ("sec",)),
        ("RELEASE.md", ("devops",)),
        ("DOCS.md", ("docs",)),
        ("AUTHORITY.md", ("architect",)),
        ("PLAN.md", ("pm", "architect", "dba")),
        ("STATE.json", ()),
        ("ROSTER.json", ()),
        ("TASKS.json", ()),
    ],
)
def test_artifact_owners_table(base: str, owners: tuple[str, ...]) -> None:
    assert art.owners_of(base) == owners


@pytest.mark.parametrize(
    "base",
    [
        "TASK.md",
        "任务看板.md",
        "SUMMARY.md",
        "RETRO.md",
        "RUN.log.md",
        "METRICS.md",
        "DECISIONS.md",
    ],
)
def test_unlisted_artifacts_are_unrestricted(base: str) -> None:
    """未列入归属表 ⇒ `None` = 不限制（**不是**空数组那层「运行时专属」语义）。"""
    assert art.owners_of(base) is None


def test_owners_of_is_exact_match_on_base_name() -> None:
    """`owners_of` 只认基名；带目录的路径不算命中 ⇒ 回到「不限制」。"""
    assert art.owners_of("team/2026-09-28-145847/SPEC.md") is None
    assert art.owners_of(None) is None
    assert art.owners_of("") is None


# ── 角色归一（fail-open 的另一半：认得出来才谈权限）─────────────────────────


@pytest.mark.parametrize("role", sorted(art.TEAM_ROLES))
def test_normalize_owner_role_accepts_every_fixed_role(role: str) -> None:
    assert art.normalize_owner_role(role) == role


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("reviewer-R1", "reviewer"),
        ("frontend-F4", "frontend"),
        ("  pm  ", "pm"),
        ("backend-2", "backend"),
        ("unknown", ""),
        ("", ""),
        (None, ""),
        ("-", ""),
    ],
)
def test_normalize_owner_role_strips_member_suffix(raw: str | None, expected: str) -> None:
    assert art.normalize_owner_role(raw) == expected


# ── owner_violation：四类放行 + 一类拒绝 ─────────────────────────────────────


def test_owner_violation_allows_creation() -> None:
    """放行路径 ① 创建放行 —— 建 run 时要一次性落 14 份骨架，收紧它会把建 run 直接打死。"""
    assert art.owner_violation(role="backend", base="SPEC.md", exists=False) is None


def test_owner_violation_allows_unknown_role_fail_open() -> None:
    """放行路径 ② 角色认不出 ⇒ fail-open（宁可漏拦，不可误伤）。"""
    assert art.owner_violation(role="ghost", base="SPEC.md", exists=True) is None
    assert art.owner_violation(role="", base="SPEC.md", exists=True) is None


def test_owner_violation_allows_unlisted_artifact() -> None:
    """放行路径 ③ 不在表里 ⇒ 不限制（含覆写）。"""
    assert art.owner_violation(role="backend", base="TASK.md", exists=True) is None
    assert art.owner_violation(role="backend", base="RUN.log.md", exists=True) is None


def test_owner_violation_allows_the_owner() -> None:
    """放行路径 ④ 写者就是负责人（含多负责人之一与带后缀的成员名）。"""
    assert art.owner_violation(role="pm", base="SPEC.md", exists=True) is None
    assert art.owner_violation(role="architect", base="PLAN.md", exists=True) is None
    assert art.owner_violation(role="dba", base="PLAN.md", exists=True) is None
    assert art.owner_violation(role="reviewer-R1", base="REVIEW.md", exists=True) is None


def test_owner_violation_denies_overwriting_someone_elses_artifact() -> None:
    """拒绝路径：已存在且写者不是负责人。"""
    reason = art.owner_violation(role="backend", base="SPEC.md", exists=True)
    assert reason is not None
    assert "SPEC.md" in reason
    assert "pm" in reason


@pytest.mark.parametrize("role", ["backend", "frontend"])
def test_owner_violation_denies_roles_that_own_no_artifact(role: str) -> None:
    """**上游冒烟测试抓到的真实反例**：`backend`/`frontend` 不拥有任何工件，
    但它们**是**可识别角色 ⇒ 必须能认出并**拦下**，绝不能因「认不出」而放行。
    若 `TEAM_ROLES` 被改成从归属表反推，本用例会红。"""
    reason = art.owner_violation(role=role, base="SPEC.md", exists=True)
    assert reason is not None
    assert f"`{role}`" in reason


@pytest.mark.parametrize("base", ["STATE.json", "ROSTER.json", "TASKS.json"])
@pytest.mark.parametrize("role", sorted(art.TEAM_ROLES))
def test_runtime_exclusive_artifacts_reject_every_role(base: str, role: str) -> None:
    """`owners == []` = 运行时专属 ⇒ **任何角色**覆写都被拒（含创建之外的一切写）。"""
    reason = art.owner_violation(role=role, base=base, exists=True)
    assert reason is not None
    assert "runtime only" in reason


def test_tasks_json_owners_is_empty_and_stricter_than_upstream() -> None:
    """`TASKS.json` 在本仓是**只读投影**（写者从角色变成代码）⇒ 比上游的
    `['pm', 'architect']` 更严，取 `()`。"""
    assert art.ARTIFACT_OWNERS["TASKS.json"] == ()
    for role in ("pm", "architect", "backend", "reviewer", "qa"):
        assert art.owner_violation(role=role, base="TASKS.json", exists=True) is not None


def test_runtime_exclusive_still_allows_creation() -> None:
    """创建放行 对 `[]` 同样成立 —— 骨架落盘依赖它（否则建 run 立刻死）。"""
    assert art.owner_violation(role="backend", base="STATE.json", exists=False) is None


# ── run_scoped_target：只认正好两段 ─────────────────────────────────────────


def test_run_scoped_target_accepts_exactly_two_segments(tmp_path: Path) -> None:
    root = _run_root(tmp_path)
    target = art.run_scoped_target(root / RUN_ID / "SPEC.md", root)
    assert target is not None
    assert target.run_id == RUN_ID
    assert target.base == "SPEC.md"
    assert Path(target.path) == root / RUN_ID / "SPEC.md"


@pytest.mark.parametrize(
    "relative",
    [
        "SPEC.md",  # 直接落在 run_root 下（缺 runId 段）
        f"{RUN_ID}/nested/SPEC.md",  # 更深一层（run 目录里的子目录）
        f"{RUN_ID}/a/b/SPEC.md",
        f"{RUN_ID}/",  # 只有 runId 段
        "",
    ],
)
def test_run_scoped_target_rejects_other_shapes(tmp_path: Path, relative: str) -> None:
    root = _run_root(tmp_path)
    assert art.run_scoped_target(root / relative, root) is None


def test_run_scoped_target_rejects_paths_outside_the_root(tmp_path: Path) -> None:
    root = _run_root(tmp_path)
    outside = tmp_path / "elsewhere" / RUN_ID / "SPEC.md"
    assert art.run_scoped_target(outside, root) is None
    # `..` 上跳到**根之外**的兄弟目录，同样不算命中
    assert art.run_scoped_target(root / ".." / "other" / RUN_ID / "SPEC.md", root) is None


def test_run_scoped_target_normalizes_dotdot_lexically(tmp_path: Path) -> None:
    """`..` 是**纯词法**折叠（`os.path.normpath`），不查文件系统。

    ⇒ 从根内上跳再回到根内的同名结构，**仍然命中**（这是对的：它真的落在 run 目录里）。
    边界要说清：本函数**不**跟随符号链接（跟随就要查盘，破坏「零 IO」纪律），
    因此「路径包含关系」不是它提供的保证 —— 它只提供「这次的写目标是不是
    `<run_root>/<runId>/<文件名>` 这个形状」。
    """
    root = _run_root(tmp_path)
    target = art.run_scoped_target(root / ".." / root.name / RUN_ID / "SPEC.md", root)
    assert target is not None
    assert target.base == "SPEC.md"
    assert Path(target.path).parent.parent == root


def test_run_scoped_target_rejects_run_root_itself(tmp_path: Path) -> None:
    root = _run_root(tmp_path)
    assert art.run_scoped_target(root, root) is None


def test_run_scoped_target_rejects_empty_inputs(tmp_path: Path) -> None:
    root = _run_root(tmp_path)
    assert art.run_scoped_target("", root) is None
    assert art.run_scoped_target(root / RUN_ID / "SPEC.md", "") is None
    assert art.run_scoped_target("   ", root) is None


def test_run_scoped_target_uses_os_sep_not_a_hardcoded_slash(tmp_path: Path) -> None:
    """跨平台：路径由 `pathlib` 拼，断言不依赖 `/` 或 `\\` 字面量。"""
    root = _run_root(tmp_path)
    target = art.run_scoped_target(Path(os.fspath(root), RUN_ID, "SPEC.md"), root)
    assert target is not None
    assert target.base == "SPEC.md"
    assert target.run_id == RUN_ID


def test_run_scoped_target_result_is_frozen(tmp_path: Path) -> None:
    root = _run_root(tmp_path)
    target = art.run_scoped_target(root / RUN_ID / "SPEC.md", root)
    assert target is not None
    with pytest.raises(FrozenInstanceError):
        target.base = "OTHER.md"  # type: ignore[misc]


# ── 模板清单：14 份齐备 ─────────────────────────────────────────────────────


def test_run_template_names_are_exactly_fourteen() -> None:
    assert len(art.RUN_TEMPLATE_NAMES) == 14
    assert len(set(art.RUN_TEMPLATE_NAMES)) == 14
    assert art.RUN_TEMPLATE_NAMES == (
        "TASK.md",
        "ROSTER.json",
        "STATE.json",
        "任务看板.md",
        "SPEC.md",
        "PLAN.md",
        "RESEARCH.md",
        "TASKS.json",
        "REVIEW-SPEC.md",
        "REVIEW.md",
        "TEST.md",
        "SUMMARY.md",
        "RETRO.md",
        "AUTHORITY.md",
    )


def test_run_template_dir_is_built_with_pathlib() -> None:
    """目录由 `pathlib` 拼（不手写分隔符），且不调用 `.resolve()`（那会破坏「零 IO」）。"""
    assert isinstance(art.RUN_TEMPLATE_DIR, Path)
    assert Path(art.__file__).parent / "templates" / "run" == art.RUN_TEMPLATE_DIR
    assert art.RUN_TEMPLATE_DIR.is_dir()


def test_all_fourteen_templates_exist_and_are_non_empty() -> None:
    on_disk = sorted(p.name for p in art.RUN_TEMPLATE_DIR.iterdir() if p.is_file())
    assert on_disk == sorted(art.RUN_TEMPLATE_NAMES)
    for name in art.RUN_TEMPLATE_NAMES:
        assert (art.RUN_TEMPLATE_DIR / name).read_text(encoding="utf-8").strip(), name


@pytest.mark.parametrize("name", ["ROSTER.json", "STATE.json", "TASKS.json"])
def test_json_templates_parse_and_carry_expected_keys(name: str) -> None:
    data = json.loads((art.RUN_TEMPLATE_DIR / name).read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    if name == "TASKS.json":
        # 只读投影的权威标记（PLAN 风险 R6 ②）：写者不是角色，是代码。
        assert data["authority"] == "db"
        assert data["tasks"] == []
    else:
        assert data["runId"] == ""


def test_templates_dir_does_not_shadow_the_team_host_template_dir() -> None:
    """`templates/run/`（run 骨架）与既有 `template/`（团队 host 工作区种子）是**两个**目录。"""
    from octop.infra.agents.teams.service import TEMPLATE_DIR

    assert TEMPLATE_DIR != art.RUN_TEMPLATE_DIR
    assert TEMPLATE_DIR.name == "template"
    assert art.RUN_TEMPLATE_DIR.name == "run"


# ── 流程工件取值域（只此一份）────────────────────────────────────────────────


def test_workflow_artifact_kinds_bind_to_the_existing_attachment_constant() -> None:
    """取值域只此一份；`attachment` 的既有拼写真源在 repo 层，本模块不 import 它，
    由本用例把两者绑在一起（改了任一处都会红）。"""
    assert art.WORKFLOW_ARTIFACT_KINDS == ("attachment", "workflow")
    assert ATTACHMENT_KIND in art.WORKFLOW_ARTIFACT_KINDS
    assert art.WORKFLOW_ARTIFACT_KIND == "workflow"


def test_workflow_kind_literal_in_the_repo_layer_is_bound_to_the_authority() -> None:
    """**补一条被"声称存在"但并不存在的护栏。**

    repo 层（`infra/db/repos/`）**不能** import `teams/artifacts.py`（`AGENTS.md §5` 硬禁令，
    本文件另有一条 AST 用例钉着），所以它只能自己写一份 `WORKFLOW_KIND = "workflow"` 字面量。
    那里的注释逐字写着「this constant is the spelling this layer needs and **a unit test binds
    the two**」—— 但**那个用例当时并不存在**（`grep WORKFLOW_KIND tests/` 零命中）⇒ 两处字面量
    可以**静默分叉**。本用例把这句话变成真的。

    为什么放在这里而不是 repo 的测试里：本文件是 `WORKFLOW_ARTIFACT_KINDS` 的 owner 所在，
    「只此一份」的断言应该和权威常量住在一起（FIND-19 的口径）。
    """
    from octop.infra.db.repos.project_artifacts import WORKFLOW_KIND

    assert WORKFLOW_KIND == art.WORKFLOW_ARTIFACT_KIND, (
        "repo 层的 workflow kind 字面量与 teams/artifacts.py 的权威值分叉了"
    )
    assert WORKFLOW_KIND in art.WORKFLOW_ARTIFACT_KINDS


# ── 诚实边界：不得被「顺手改写成不可绕过」────────────────────────────────────


def test_module_docstring_keeps_the_honest_bash_bypass_boundary() -> None:
    """`execute_shell_command` 重定向可绕过本门禁 —— 这条边界必须留在模块文档里。
    任何人把它删掉或改成「不可绕过」，本用例变红。"""
    doc = art.__doc__ or ""
    assert "execute_shell_command" in doc
    assert "write_file" in doc


# ─────────────────────────────────────────────────────────────────────────────
# T-12 · TeamArtifactOwnershipMiddleware（工具通道硬门禁，写盘之前拦）
# ─────────────────────────────────────────────────────────────────────────────


class _Req:
    """最小 `ToolCallRequest` 替身 —— 中间件只读 `tool_call`。"""

    def __init__(self, name: str, args: dict[str, Any], call_id: str = "tc1") -> None:
        self.tool_call = {"name": name, "args": args, "id": call_id}


class _Handler:
    """记录**是否被调用**的 handler 替身 —— 「拒绝时不调用 handler」是 G1 的核心断言。"""

    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self, request: Any) -> ToolMessage:
        self.calls += 1
        return ToolMessage(content="WROTE", tool_call_id="tc1")


def _gate(
    *,
    team_root: str | None,
    exists: bool | None = True,
    status: str | None = "running",
    role: str | None = "pm",
    exists_raises: bool = False,
    role_raises: bool = False,
    on_event_raises: bool = False,
    events: list[tuple[str, dict[str, Any]]] | None = None,
) -> TeamArtifactOwnershipMiddleware:
    """装配一个可完全操控的门禁（四个查询都是测试替身 ⇒ 不需要数据库）。"""

    def _on_event(event: str, payload: dict[str, Any]) -> None:
        if events is not None:
            events.append((event, dict(payload)))
        if on_event_raises:
            raise RuntimeError("observer down")

    def _exists_for(_path: str) -> bool | None:
        if exists_raises:
            raise RuntimeError("existence backend down")
        return exists

    def _role_for(_run_id: str) -> str | None:
        if role_raises:
            raise RuntimeError("role backend down")
        return role

    return TeamArtifactOwnershipMiddleware(
        deps=OwnershipGateDeps(
            team_root_for=lambda _raw: team_root,
            run_status_for=lambda _run_id: status,
            role_for=_role_for,
            exists_for=_exists_for,
            on_event=_on_event,
        )
    )


def _spec_path(tmp_path: Path) -> str:
    return str(_run_root(tmp_path) / RUN_ID / "SPEC.md")


# ── 拒绝路径（G1 的主断言）───────────────────────────────────────────────────


async def test_denies_overwrite_and_never_calls_handler(tmp_path: Path) -> None:
    """以 `backend` 写**已存在**的 `SPEC.md` ⇒ 拒绝，且 **handler 未被调用**（写盘之前拦）。"""
    events: list[tuple[str, dict[str, Any]]] = []
    mw = _gate(team_root=str(_run_root(tmp_path)), role="backend", events=events)
    handler = _Handler()

    out = await mw.awrap_tool_call(_Req("write_file", {"file_path": _spec_path(tmp_path)}), handler)

    assert isinstance(out, ToolMessage)
    assert out.status == "error"
    assert "SPEC.md" in str(out.content)
    assert handler.calls == 0, "门禁必须在写盘之前拦 —— handler 一次都不能被调用"
    assert out.tool_call_id == "tc1"
    assert [e for e, _ in events] == [EVENT_OWNERSHIP_DENIED]
    assert events[0][1]["base"] == "SPEC.md"
    assert events[0][1]["role"] == "backend"
    assert events[0][1]["runId"] == RUN_ID


@pytest.mark.parametrize("base", ["STATE.json", "ROSTER.json", "TASKS.json"])
async def test_runtime_exclusive_artifacts_are_denied_in_the_tool_channel(
    tmp_path: Path, base: str
) -> None:
    """`owners == []`（运行时专属）**在本通道也拒绝** —— SPEC B13 逐字要求工具通道出
    `ToolMessage(status="error")`；PLAN 的 `L1 工具通道硬门禁` 行同口径（「任何角色不得覆写」）。
    ⇒ 角色写 run 状态/编制就等于篡改门禁的判据来源。"""
    mw = _gate(team_root=str(_run_root(tmp_path)), role="pm")
    handler = _Handler()

    out = await mw.awrap_tool_call(
        _Req("write_file", {"file_path": str(_run_root(tmp_path) / RUN_ID / base)}), handler
    )

    assert isinstance(out, ToolMessage)
    assert out.status == "error"
    assert handler.calls == 0


# ── 四类 fail-open（T-12 验收逐条）──────────────────────────────────────────


async def test_allows_creation_and_calls_handler(tmp_path: Path) -> None:
    """fail-open ① 目标**不存在**（创建）⇒ 放行。建 run 时首个成员要一次性落 14 份骨架，
    收紧这条会把建 run 直接打死。"""
    mw = _gate(team_root=str(_run_root(tmp_path)), role="backend", exists=False)
    handler = _Handler()

    out = await mw.awrap_tool_call(_Req("write_file", {"file_path": _spec_path(tmp_path)}), handler)

    assert handler.calls == 1
    assert isinstance(out, ToolMessage)
    assert out.status != "error"


async def test_allows_unknown_role_and_calls_handler(tmp_path: Path) -> None:
    """fail-open ② 角色认不出 ⇒ 放行（宁可漏拦，不可误伤）。"""
    mw = _gate(team_root=str(_run_root(tmp_path)), role="ghost")
    handler = _Handler()

    await mw.awrap_tool_call(_Req("write_file", {"file_path": _spec_path(tmp_path)}), handler)

    assert handler.calls == 1


async def test_allows_artifact_absent_from_the_owners_table(tmp_path: Path) -> None:
    """fail-open ③ `owners is None`（未列入归属表，如 `RUN.log.md` / `TASK.md`）⇒ 不限制。"""
    mw = _gate(team_root=str(_run_root(tmp_path)), role="backend")
    handler = _Handler()
    target = str(_run_root(tmp_path) / RUN_ID / "RUN.log.md")

    await mw.awrap_tool_call(_Req("write_file", {"file_path": target}), handler)

    assert handler.calls == 1


async def test_allows_when_existence_query_returns_none(tmp_path: Path) -> None:
    """fail-open ④-a 存在性**查不到**（`None`）⇒ 放行 **+ 留痕**（门禁降级必须可见）。"""
    events: list[tuple[str, dict[str, Any]]] = []
    mw = _gate(team_root=str(_run_root(tmp_path)), exists=None, events=events)
    handler = _Handler()

    await mw.awrap_tool_call(_Req("write_file", {"file_path": _spec_path(tmp_path)}), handler)

    assert handler.calls == 1
    assert [e for e, _ in events] == [EVENT_OWNERSHIP_DEGRADED]
    assert events[0][1]["why"] == "existence-unknown"
    assert events[0][1]["base"] == "SPEC.md"


async def test_allows_when_existence_query_raises(tmp_path: Path) -> None:
    """fail-open ④-b 存在性**查询抛异常** ⇒ 放行 + 留痕，**异常不得外泄**。"""
    events: list[tuple[str, dict[str, Any]]] = []
    mw = _gate(team_root=str(_run_root(tmp_path)), exists_raises=True, events=events)
    handler = _Handler()

    await mw.awrap_tool_call(_Req("write_file", {"file_path": _spec_path(tmp_path)}), handler)

    assert handler.calls == 1
    assert [e for e, _ in events] == [EVENT_OWNERSHIP_DEGRADED]
    assert events[0][1]["why"] == "gate-error"


# ── 门禁自身绝不允许成为工具故障源 ───────────────────────────────────────────


async def test_gate_internal_error_does_not_block_the_tool(tmp_path: Path) -> None:
    """任何内部异常一律放行 + 留痕（上游真实事故：post-execute 签名写错曾让全工具瘫痪）。"""
    events: list[tuple[str, dict[str, Any]]] = []
    mw = _gate(team_root=str(_run_root(tmp_path)), role_raises=True, events=events)
    handler = _Handler()

    await mw.awrap_tool_call(_Req("write_file", {"file_path": _spec_path(tmp_path)}), handler)

    assert handler.calls == 1
    assert events and events[0][0] == EVENT_OWNERSHIP_DEGRADED
    assert events[0][1]["why"] == "gate-error"


async def test_on_event_failure_does_not_flip_a_deny_into_an_allow(tmp_path: Path) -> None:
    """**观测端炸了也必须仍然是拒绝** —— 否则「打挂观测」就成了绕过门禁的手法。"""
    mw = _gate(team_root=str(_run_root(tmp_path)), role="backend", on_event_raises=True)
    handler = _Handler()

    out = await mw.awrap_tool_call(_Req("write_file", {"file_path": _spec_path(tmp_path)}), handler)

    assert isinstance(out, ToolMessage)
    assert out.status == "error"
    assert handler.calls == 0


# ── 放行的其余正常路径 ───────────────────────────────────────────────────────


async def test_allows_terminal_run(tmp_path: Path) -> None:
    """终态 run 放行：冻结的历史工件不该在写侧拦（上游同一理由）。"""
    mw = _gate(team_root=str(_run_root(tmp_path)), role="backend", status="complete")
    handler = _Handler()

    await mw.awrap_tool_call(_Req("write_file", {"file_path": _spec_path(tmp_path)}), handler)

    assert handler.calls == 1


async def test_allows_non_write_tools_including_bash(tmp_path: Path) -> None:
    """本门禁**只**认 write/edit；`execute_shell_command`（bash）**有意**放行 —— 见 docstring
    的诚实边界。它不是缺陷，是首版取舍；bash 那一路的补救在服务层。"""
    mw = _gate(team_root=str(_run_root(tmp_path)), role="backend")
    handler = _Handler()

    await mw.awrap_tool_call(
        _Req("execute_shell_command", {"command": f"cat > {_spec_path(tmp_path)}"}), handler
    )

    assert handler.calls == 1


async def test_gates_namespaced_write_tool(tmp_path: Path) -> None:
    """插件工具名形如 `<prefix>/<tool>` ⇒ 必须**先剥前缀再查表**，否则它绕过归属门禁却照样写盘。"""
    mw = _gate(team_root=str(_run_root(tmp_path)), role="backend")
    handler = _Handler()

    out = await mw.awrap_tool_call(
        _Req("octop_ui/write_file", {"file_path": _spec_path(tmp_path)}), handler
    )

    assert isinstance(out, ToolMessage)
    assert out.status == "error"
    assert handler.calls == 0


@pytest.mark.parametrize("relpath", ["SPEC.md", f"{RUN_ID}/nested/SPEC.md", f"{RUN_ID}/"])
async def test_allows_paths_outside_the_two_segment_run_scope(tmp_path: Path, relpath: str) -> None:
    """只认 `<run_root>/<runId>/<文件名>` 正好两段 —— 更深/更浅一律不拦（避免误伤）。"""
    mw = _gate(team_root=str(_run_root(tmp_path)), role="backend")
    handler = _Handler()

    await mw.awrap_tool_call(
        _Req("write_file", {"file_path": str(_run_root(tmp_path) / relpath)}), handler
    )

    assert handler.calls == 1


async def test_allows_when_the_write_target_is_empty(tmp_path: Path) -> None:
    mw = _gate(team_root=str(_run_root(tmp_path)), role="backend")
    handler = _Handler()

    await mw.awrap_tool_call(_Req("write_file", {}), handler)

    assert handler.calls == 1


async def test_allows_when_run_root_is_unknown(tmp_path: Path) -> None:
    """`team_root_for` 返回 `None` = 目标不在团队 run 目录里 ⇒ 放行。"""
    mw = _gate(team_root=None, role="backend")
    handler = _Handler()

    await mw.awrap_tool_call(_Req("write_file", {"file_path": "/tmp/x/SPEC.md"}), handler)

    assert handler.calls == 1


# ── 结构与契约（防「顺手改坏」）──────────────────────────────────────────────


def test_sync_tool_path_is_not_a_silent_bypass() -> None:
    """只实现 `awrap_tool_call` ⇒ 同步路径**不会静默放行**：LangGraph 的默认
    `wrap_tool_call` 会显式抛 `NotImplementedError`（响亮地失败，不是安静地放过）。"""
    mw = _gate(team_root="/tmp/team", role="backend")
    assert "wrap_tool_call" not in TeamArtifactOwnershipMiddleware.__dict__
    with pytest.raises(NotImplementedError):
        mw.wrap_tool_call(_Req("write_file", {"file_path": "/tmp/team/x/SPEC.md"}), _Handler())


def test_emits_exactly_the_two_plan_event_names() -> None:
    """事件名**只此一份**（`PLAN.md · 事件名词表`）——不得另造同义名。"""
    assert EVENT_OWNERSHIP_DENIED == "team.artifact.ownership_denied"
    assert EVENT_OWNERSHIP_DEGRADED == "team.artifact.ownership_degraded"


def test_module_does_not_import_repos_or_db() -> None:
    """本模块走依赖注入 ⇒ 必须能在**没有数据库**的情况下单测（T-12 验收④）。

    用 AST 查**真实的 import 语句**（见 `_imported_modules`），而不是在源码里找 `repos` 这个词
    —— docstring 里就写着「不 import ``repos``」，字面匹配会假红。
    """
    from octop.infra.agents.middleware import team_artifact_ownership as mod

    imported = _imported_modules(mod.__file__)
    for name in imported:
        assert "infra.db" not in name, f"门禁不得 import 数据库层：{name}"
        assert "repos" not in name, f"门禁不得 import 仓储层：{name}"
    # 依赖面必须只有：stdlib + langchain/langgraph 中间件协议 + 两个纯函数内核。
    assert {name for name in imported if name.startswith("octop.")} == {
        "octop.infra.agents.teams.artifacts",
        "octop.infra.agents.teams.pipeline",
    }, imported


def test_middleware_docstring_keeps_the_honest_bash_bypass_boundary() -> None:
    """与 `artifacts.py` 那条同款：诚实边界不得被删掉，也不得被改写成「不可绕过」。"""
    from octop.infra.agents.middleware import team_artifact_ownership as mod

    doc = mod.__doc__ or ""
    assert "execute_shell_command" in doc
    assert "重定向绕过" in doc
    assert "不是缺陷" in doc
    assert "不可能违反" in doc, "必须显式写出「不是『不可能违反』」这句否认"
