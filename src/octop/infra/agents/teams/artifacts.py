"""团队 run 工件的归属表、模板清单与路径作用域 —— 纯函数，零 IO。

本模块是三层门禁共用的**唯一**机读真源（对齐上游 ``lib/artifact-ownership.js``）：

* **归属表** —— ``ARTIFACT_OWNERS`` / :func:`owners_of` / :func:`owner_violation`
* **模板清单** —— ``RUN_TEMPLATE_NAMES`` / ``RUN_TEMPLATE_DIR``（14 份骨架）
* **路径作用域** —— :func:`run_scoped_target`
* **流程工件取值域** —— ``WORKFLOW_ARTIFACT_KINDS``

── 诚实边界（不得删除，不得改写成「不可绕过」）─────────────────────────────────

本模块只服务 **``write_file`` / ``edit_file`` 工具通道**的归属硬门禁。持有
``execute_shell_command``（bash）的角色可以用 ``cat > SPEC.md`` 这类重定向绕过它；首版
**刻意**不对 bash 参数做启发式检查（写目标可以是重定向 / 变量 / 子命令，静态判断不可靠）。
因此对外表述恒为「**``write``/``edit`` 通道的硬门禁**」，不是「不可能违反」。上游同款边界
见 ``lib/artifact-ownership.js`` 文件头的「诚实边界」段。

── 为什么判据是「创建放行、覆写才拦」────────────────────────────────────────

建 run 时**首个成员**要按模板一次性把 14 份骨架落到 ``<run_root>/<runId>/``，其中大多数
**不属于它**。若判据写成「角色 ≠ 负责人 ⇒ 拦」，会**直接打死建 run**。因此判据是：
**目标不存在（创建）⇒ 放行；已存在且写者不是它的负责人 ⇒ 拒绝。** 这条判据只需一次
存在性查询、**不读内容**，所以能放在写盘**之前**。
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePath
from types import MappingProxyType
from typing import Final

from octop.infra.agents.teams.pipeline import ROLES

#: 12 个固定角色 —— **转发** ``pipeline.ROLES``，本模块**不再自己列一遍**（task-44 收口）。
#:
#: 为什么必须是单一权威（**安全相关，不是风格检查**）：本模块的 :func:`owner_violation` 对
#: 「认不出的角色」是 **fail-open**（对齐上游，见该函数 docstring 第 2 条）。若这里留第二份
#: 拷贝，``pipeline.ROLES`` 新增第 13 个角色而本表没跟上，那个角色在归属门禁里就变成「认不出」
#: ⇒ **可以覆写任何人的工件**（权限绕过）。转发之后，这类漂移在结构上不可能发生。
#:
#: **★ 冻结约定**：``pipeline.ROLES`` 的名字与内容**自 task-44 起冻结**。任何人要改它，
#: **必须同时显式更新** ``tests/unit/agents/test_team_ownership_gate.py`` 顶部的
#: ``EXPECTED_ROLES``（测试侧的独立真值）—— 三方对账护栏靠它才能在收口之后**仍然变异得红**。
#:
#: **不能**从下面的归属表反推：``backend`` / ``frontend`` 不拥有任何工件，但它们**是**可识别
#: 的角色。反推会把它们当成「认不出」而放行，等于让它们任意覆写别人的工件 —— 这是上游冒烟
#: 测试抓到的真实反例（见 ``lib/artifact-ownership.js · KNOWN_ROLES @ 75`` 的注释）。
#:
#: 取 ``frozenset`` 投影而非直接别名（``from … import ROLES as TEAM_ROLES``）：``KNOWN_ROLES``
#: 要做集合运算、成员判定在热路径上，且 ``frozenset[str]`` 是 T-11 已交付的公开类型（改成
#: ``tuple`` 会波及 T-12 的中间件与 T-13 的服务层）。转发语义不变 —— 值仍只有 ``pipeline.ROLES``
#: 一处定义，本行只是类型投影。
TEAM_ROLES: Final[frozenset[str]] = frozenset(ROLES)

#: 工件文件名 → 允许**覆写**它的角色；``()`` = 运行时专属，**角色一律不得覆写**。
#:
#: * 键是 ``run_scoped_target().base`` 的**精确**文件名（不带目录），**未列入的键 = 不限制**
#:   （用 :func:`owners_of` 取，得到 ``None``）。
#: * 多负责人取**宽松**：宁可漏拦，不可误伤（上游 ``PLAN.md`` 是 pm 骨架 → architect 设计段 →
#:   dba 数据段 ⇒ 列 3 个 owner）。
#: * ``TASKS.json`` 在本仓是**只读投影**（写者已从角色变成代码）⇒ 比上游的
#:   ``['pm', 'architect']`` **更严**，取 ``()``（`PLAN.md` 风险 R6）。
#: * 表里没有的文件名（``TASK.md`` / ``任务看板.md`` / ``SUMMARY.md`` / ``RETRO.md`` /
#:   ``RUN.log.md`` / ``METRICS.md`` / ``DECISIONS.md``）**故意不列入** ⇒ 不限制。``RUN.log.md``
#:   的 append-only 语义由**服务层**（``PUT …/artifacts/{name}``）承担，工具通道仍按本表放行
#:   （`PLAN.md` FIND-31 收口：两个通道的严格度**刻意不同**，不得合并）。
ARTIFACT_OWNERS: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        # ── 单一负责人 ──────────────────────────────────────────────────────
        "SPEC.md": ("pm",),
        "RESEARCH.md": ("researcher",),
        "REVIEW.md": ("reviewer",),
        "REVIEW-SPEC.md": ("reviewer",),
        "TEST.md": ("qa",),
        "UI.md": ("ui",),
        "DATA.md": ("dba",),
        "SECURITY.md": ("sec",),
        "RELEASE.md": ("devops",),
        "DOCS.md": ("docs",),
        "AUTHORITY.md": ("architect",),
        # ── 多负责人（真源就是多段 / 多角色 ⇒ 取宽松）──────────────────────
        "PLAN.md": ("pm", "architect", "dba"),
        # ── 运行时专属：角色不得覆写 ────────────────────────────────────────
        "STATE.json": (),
        "ROSTER.json": (),
        "TASKS.json": (),
    }
)

#: **认得出的角色**（用于区分「角色认不出 ⇒ 放行」与「角色认得但没权限 ⇒ 拦」）。
#: 与上游同构：12 固定角色 ∪ 归属表里出现过的角色（后者让表格笔误不至于静默失配 ——
#: 单测另有一条断言把归属表的值域钉回 :data:`TEAM_ROLES`）。
KNOWN_ROLES: Final[frozenset[str]] = frozenset(
    TEAM_ROLES | {role for owners in ARTIFACT_OWNERS.values() for role in owners}
)

#: 14 份 run 骨架模板的文件名：其中 13 份对齐上游
#: ``lib/command.js · ARTIFACT_TEMPLATES @ 42``（``RESEARCH-UPSTREAM.md §5.2`` 的 ``ls``
#: 输出同为这 13 个），外加本仓新增 ``REVIEW-SPEC.md``（``B1`` 沉默清单载体，
#: ``pipeline.py`` 的 ``spec-review`` 阶段要求该工件存在）。
#:
#: ⚠️ **与「必需 11 项」不是同一个清单**：``PLAN.md §run 目录结构`` 的必需 11 项含
#: ``RUN.log.md``，而它**不在**这份清单里 —— 它由 ``/team`` 建 run 时直接创建
#: （``PLAN.md`` 工件表：`RUN.log.md` 的写者是「``/team`` 建；事件由产出角色落盘」）。
#: 本模块**只**回答「模板有哪 14 份」，不回答「骨架必须落哪 11 项」。
RUN_TEMPLATE_NAMES: Final[tuple[str, ...]] = (
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

#: 模板所在目录。``pathlib`` 拼接 ⇒ 跨平台（Windows 与 POSIX 同语义，不手写分隔符）。
#: 刻意**不**调用 ``.resolve()``：那会触发文件系统查询，破坏本模块「零 IO」的纪律。
RUN_TEMPLATE_DIR: Final[Path] = Path(__file__).parent / "templates" / "run"

#: ``project_artifacts.kind`` 的流程工件取值域（`PLAN.md · WORKFLOW_ARTIFACT_KINDS`；**只此一份**，
#: 不得在别处另列该取值域）。
#:
#: 第一个值 ``"attachment"`` 的既有拼写真源是
#: `src/octop/infra/db/repos/project_artifacts.py · ATTACHMENT_KIND @ 16`。本模块**不** import
#: ``infra/db``（纯函数纪律，见 `PLAN.md §模块边界①` 对本文件「允许 import」的限定），
#: 改由单测把两者绑在一起防漂移。
WORKFLOW_ARTIFACT_KIND: Final[str] = "workflow"
WORKFLOW_ARTIFACT_KINDS: Final[tuple[str, ...]] = ("attachment", WORKFLOW_ARTIFACT_KIND)


@dataclass(frozen=True, slots=True)
class RunScopedTarget:
    """``<run_root>/<runId>/<文件名>`` 的解析结果 —— 归属门禁的全部判据来源。"""

    run_id: str
    """run 目录名（同时也是 run 的公开 id，形如 ``2026-09-28-145847``）。"""

    base: str
    """run 目录内的文件名，直接喂给 :func:`owners_of`。"""

    path: str
    """规范化后的绝对（或原样给出的）目标路径，供日志与留痕使用。"""


def owners_of(base: str | None) -> tuple[str, ...] | None:
    """查 *base* 的负责人。

    :returns: 负责人元组；``()`` = 运行时专属（角色一律不得覆写）；
        ``None`` = **不在表里 ⇒ 不限制**。
    """
    return ARTIFACT_OWNERS.get(str(base or ""))


def normalize_owner_role(role: str | None) -> str:
    """把编制里解出的角色串归一成角色表里的 id。

    成员表允许带后缀（``frontend-F4`` / ``reviewer-R1``）⇒ 取基名再查表；**认不出的角色
    返回空串**，调用方据此 **fail-open**（放行），而不是把它当成「没有权限」。

    :returns: 归一后的角色 id；认不出则为 ``""``。
    """
    raw = str(role or "").strip()
    if not raw:
        return ""
    if raw in KNOWN_ROLES:
        return raw
    base = raw.split("-", 1)[0]
    return base if base in KNOWN_ROLES else ""


def owner_violation(*, role: str, base: str, exists: bool) -> str | None:
    """判定一次写入是否违反 R1 工件归属（纯函数，可单测）。

    判据（与上游 ``ownerViolation @ 110`` 同序，逐条都是 fail-open）：

    1. ``exists=False`` ⇒ 放行（**创建放行**；建 run 的骨架落盘依赖这条）。
    2. 角色认不出（``normalize_owner_role`` 后为空）⇒ 放行（fail-open，宁可漏拦）。
    3. ``owners_of(base) is None``（不在表里）⇒ 放行（不限制）。
    4. 角色是负责人之一 ⇒ 放行。
    5. 否则 ⇒ 返回拒绝理由。

    :param role: 写者角色（**建议先过** :func:`normalize_owner_role`；本函数内部会再归一一次，
        因此直接传裸角色串也是安全的）。
    :param base: 目标文件名（run 目录内的基名）。
    :param exists: 目标是否**已存在**。
    :returns: 拒绝理由；合规返回 ``None``。
    """
    if not exists:
        return None
    normalized = normalize_owner_role(role)
    if not normalized:
        return None
    owners = owners_of(base)
    if owners is None:
        return None
    if normalized in owners:
        return None
    who = " / ".join(owners) if owners else "runtime only (no role may overwrite)"
    return (
        f"R1 artifact ownership: `{base}` already exists and role `{normalized}` is not one of "
        f"its owners ({who}) — the protocol says you must not overwrite it. "
        "Return your result (path + summary + verdict) to the lead instead, so the owning role "
        "can write it. Creating new files is not restricted by this rule."
    )


def run_scoped_target(
    path: str | os.PathLike[str],
    run_root: str | os.PathLike[str],
) -> RunScopedTarget | None:
    """把 *path* 解析成 ``<run_root>/<runId>/<文件名>`` 作用域内的目标。

    **只认正好两段**（runId + 文件名）—— 更深（run 目录里的子目录）或更浅（直接落在
    ``run_root`` 下）一律返回 ``None``（**不拦**），避免误伤 run 内的其它同名文件。

    ⚠️ **边界（不得省略）**：路径归一化是**纯词法**的（``os.path.normpath`` + ``relpath``），
    **不查文件系统、不跟随符号链接** —— 跟随就要查盘，破坏本模块「零 IO」的纪律。因此本函数
    提供的是「这次的写目标是不是 ``<run_root>/<runId>/<文件名>`` 这个**形状**」，**不是**
    「路径包含关系」的安全保证；路径逃逸由另一条门禁（``TEAM_ARTIFACT_PATH_INVALID``）负责。

    :param path: 本次写入的目标路径（工具通道给出的 ``file_path``，最好是绝对路径）。
    :param run_root: ``<run_root>``（``team_runs.run_root`` 解析出的那个根，**不是** run 目录本身）。
    :returns: :class:`RunScopedTarget`；不匹配（含空值、越出根、段数不为 2、Windows 不同盘符）返回 ``None``。
    """
    target = _normalized(path)
    root = _normalized(run_root)
    if not target or not root:
        return None
    try:
        relative = os.path.relpath(target, root)
    except ValueError:
        # Windows：target 与 root 不在同一个盘符上 ⇒ 不可能在作用域内。
        return None
    parts = [part for part in PurePath(relative).parts if part not in ("", os.curdir)]
    if len(parts) != 2 or os.pardir in parts:
        return None
    run_id, base = parts
    if not run_id or not base:
        return None
    return RunScopedTarget(run_id=run_id, base=base, path=target)


def _normalized(value: str | os.PathLike[str]) -> str:
    """``os.fspath`` + ``normpath``；非法 / 空输入返回空串（纯词法操作，不查文件系统）。"""
    try:
        raw = os.fspath(value)
    except TypeError:
        return ""
    if not isinstance(raw, str) or not raw.strip():
        return ""
    return os.path.normpath(raw.strip())


__all__ = [
    "ARTIFACT_OWNERS",
    "KNOWN_ROLES",
    "RUN_TEMPLATE_DIR",
    "RUN_TEMPLATE_NAMES",
    "TEAM_ROLES",
    "WORKFLOW_ARTIFACT_KINDS",
    "WORKFLOW_ARTIFACT_KIND",
    "RunScopedTarget",
    "normalize_owner_role",
    "owner_violation",
    "owners_of",
    "run_scoped_target",
]
