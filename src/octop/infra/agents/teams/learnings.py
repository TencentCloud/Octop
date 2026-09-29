"""团队记忆接线（T-18）—— LEARNINGS 蒸馏 / 注入 / 失败语义。

唯一权威 = ``PLAN.md``「记忆接线」全节（四来源写入表 · 三层召回 · 4 条去重口径 ·
失败语义 · host 记忆自相矛盾的收口方向）。本模块是那条链的**代码侧**：

**读（run 开始前，只读）** —— :func:`read_memory_layers` 按固定顺序取三层，
:func:`build_host_memory_block` 渲染注入块（上游注入头逐字）：

1. **项目层** ``project_{project_id}`` —— 经**服务层直读**（host 的工具面读不到它）；
2. **团队层** —— ``{host_workspace}/.octop/team/LEARNINGS.md`` 的要点；
3. **agent 私有层** —— host 自己的 ``memory_search`` / ``memory_get`` 结果（白名单既有，零改动）。

**写（deliver 时，代码写、非 LLM 写）** —— :func:`distill_and_append` 三条写入路径：

1. **主写入（阻塞）**：项目级 LEARNINGS ``{host_workspace}/.octop/team/projects/{project_id}/
   LEARNINGS.md``，**按项目分文件**、**当日块原地替换**（不整文件重写）；
2. **结构化记忆（降级）**：一条 run 摘要进 ``project_{project_id}`` 命名空间 —— 复用
   ``multi_ns.MultiNsRecall.memory_for("project")``（它 docstring 里写明 writer 走这条），
   **绝不动 agent 的 ``HarnessAgentConfig(name=…)``**（那是 N1 单值互斥、会让成员丢私有记忆）；
   写成功后 ``bump`` 既有 ``ProjectInjectVersion`` 水位；
3. **跨项目知识（降级）**：交给调用方注入的 :class:`KnowledgeArchiver`（KB 侧 public 面），
   本模块**不碰** ``project_artifacts.kb_document_id``（那是 T-43 的落点）。

**上浮（项目 → 团队）**：:func:`should_promote_to_team` 由**代码判定**并打印理由
（``explicit`` / ``seen-in-n-projects`` / ``general-marker``），不靠人工搬；单向，不复制数据。

**去重四层**（PLAN「去重口径」逐条落地）：① 文本级 :func:`norm_learning` 当日块内比对 ⇒ 跳过；
② 哈希级 :func:`learning_digest` 对 KB 既有文档 ⇒ 跳过；③ 语义级**明确不做**（不引向量去重）；
④ 冲突口径：同一 ``norm()`` 键而原始文本不同 ⇒ **不覆盖**，追加 ``（更新 YYYY-MM-DD）`` 保留旧行。

**失败语义**：第 1 条失败 ⇒ 阻塞交付（向上抛）；第 2/3 条失败（含"能力缺失"）⇒ 记事件
``learnings.degraded`` 并继续交付。

**接线现状（照 T-13 的样式分开陈述）**：本模块是**库**——两个生产调用点：
① **用户记忆块注入（已接线）** = ``infra/agents/manager.py · _apply_team_host_config`` 内的就地拼接
``prompt = prompt + build_host_memory_block(host_workspace=…)``（**本轮实测 ``manager.py @3460``**）；
★ 其**定义处**是 ``teams/team_manager.py · host_system_prompt``（**本轮实测 ``@87`` 是 ``def`` —— 定义，不是接线**）
—— 原写「``team_manager.py · host_system_prompt @87`` 的注入」**把定义处当成了接线处**（``T-87`` 实测定正）；
② ``run_service`` deliver 阶段的蒸馏（:func:`distill_and_append`）**尚未接线**（本轮 ``grep`` 生产侧 0 命中）
⇒ 需由持有该文件的卡接一行；``ProjectInjectVersion`` 的**写入侧已被本模块接上**
（见 :func:`distill_and_append`），其注入侧比较由 ``ProjectInjectVersion.should_inject``
（``infra/agents/memory/multi_ns.py``）提供 —— ★ **本轮实测：该判据在生产侧【尚无调用者】**
（``grep`` 只命中用例），接线随注入点一并落地。
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from octop.infra.agents.memory.multi_ns import (
    MemoryLayer,
    MultiNsRecall,
    ProjectInjectVersion,
    normalize_memory_text,
)

if TYPE_CHECKING:
    from octop_memory.types import RawEvent

logger = logging.getLogger(__name__)

# ── 路径（唯一拼法；PLAN「可执行落点」表）──────────────────────────────────────

TEAM_DIR_PARTS: tuple[str, ...] = (".octop", "team")
"""``{host_workspace}/.octop/team`` —— 团队记忆与项目级经验文件的唯一根。"""

TEAM_LEARNINGS_NAME = "LEARNINGS.md"
PROJECTS_DIRNAME = "projects"
DEFAULT_TITLE = "# LEARNINGS"

#: 注入头。★ **与上游原文有一处不同**：上游写 ``team/LEARNINGS.md``，而本仓的权威落点是
#: ``{host_workspace}/.octop/team/LEARNINGS.md``（见本模块 ``TEAM_DIR_PARTS``），host 的内容根是
#: ``{host_workspace}``（``.octop`` 是系统树）⇒ 照抄上游会指向一个**从未被写入的位置**。
#: 该差异已由本 run 的 ``SPEC.md``（B-19）与 ``AUTHORITY.md`` 裁定：旧行（``PLAN@1218``）被取代，
#: 此处保留指向说明 —— **请勿"为了与上游一致"改回去**；本行由
#: ``tests/unit/agents/test_learnings_injection_header_pointer.py`` 机检。
INJECTION_HEADER = "【既往经验（仅要点；完整版见 .octop/team/LEARNINGS.md，相关时才读）】"

#: 非 ``ErrorCode`` 的可观测事件（PLAN「事件名词表」；进 METRICS/日志）。
DEGRADED_EVENT = "learnings.degraded"

_BULLET_RE = re.compile(r"^\s*[-*]\s+(?P<text>.+?)\s*$")
_DAY_HEADING_RE = re.compile(r"^##\s+(?P<day>\d{4}-\d{2}-\d{2})\s*$")
_TRAILING_PUNCT = "。．.,，;；:：!！?？、"

_UPDATE_TEMPLATE = "（更新 {day}）"

_GENERAL_MARKERS: tuple[str, ...] = ("通用", "所有项目", "跨项目", "流程红线")


def team_learnings_path(host_workspace: Path) -> Path:
    """``{host_workspace}/.octop/team/LEARNINGS.md`` —— 团队级（跨项目复用）。"""
    return host_workspace.joinpath(*TEAM_DIR_PARTS, TEAM_LEARNINGS_NAME)


def project_learnings_path(host_workspace: Path, project_id: str) -> Path:
    """``{host_workspace}/.octop/team/projects/{project_id}/LEARNINGS.md`` —— 每项目一份。"""
    return host_workspace.joinpath(
        *TEAM_DIR_PARTS, PROJECTS_DIRNAME, str(project_id), TEAM_LEARNINGS_NAME
    )


def projects_dir(host_workspace: Path) -> Path:
    """``…/team/projects`` —— 上浮判定要扫的目录。"""
    return host_workspace.joinpath(*TEAM_DIR_PARTS, PROJECTS_DIRNAME)


# ── 去重（口径 ①②③④）────────────────────────────────────────────────────────


def norm_learning(text: str) -> str:
    """口径①的 ``norm()``：**去**空白 + 小写 + 去尾部标点。

    大小写与"空白折叠"复用 ``multi_ns.normalize_memory_text``（记忆侧同一件事，不另写一份），
    再把折叠后的空格**去掉** —— PLAN 对 LEARNINGS 行的要求是"去空白"而不是"折叠空白"，
    两者不等价（``不要 覆盖`` 折叠后仍带空格，去空白后与 ``不要覆盖`` 同键）。
    """
    return normalize_memory_text(text).replace(" ", "").rstrip(_TRAILING_PUNCT).strip()


def learning_digest(text: str) -> str:
    """口径②的 ``sha256(norm(text))[:16]``（与 KB 既有文档比对用）。"""
    return hashlib.sha256(norm_learning(text).encode("utf-8")).hexdigest()[:16]


def dedupe_by_digest(
    texts: Iterable[str], known_digests: Collection[str]
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """口径②：按摘要与既有 KB 文档比对，返回 ``(保留, 跳过)``。

    口径③（语义级）**明确不做** —— 文本不同即视为不同条目，不调用任何向量去重。
    """
    known = {str(item) for item in known_digests}
    kept: list[str] = []
    skipped: list[str] = []
    for text in texts:
        (skipped if learning_digest(text) in known else kept).append(text)
    return tuple(kept), tuple(skipped)


# ── LEARNINGS.md：读要点 / 追加（口径①④ + 当日块原地替换）─────────────────────


@dataclass(frozen=True, slots=True)
class AppendOutcome:
    """一次 LEARNINGS 追加的可审计结果。"""

    added: tuple[str, ...] = ()
    skipped: tuple[str, ...] = ()
    updated: tuple[str, ...] = ()


def read_learnings_points(path: Path, *, limit: int = 5) -> tuple[str, ...]:
    """取文件里最后 ``limit`` 条要点（最新在后 ⇒ 取尾部），文件不存在返回空。"""
    if not path.is_file():
        return ()
    texts: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _BULLET_RE.match(line)
        if match is not None:
            texts.append(match.group("text"))
    return tuple(texts[-limit:]) if limit >= 0 else ()


def append_learnings(
    path: Path,
    texts: Sequence[str],
    *,
    on_date: date | None = None,
) -> AppendOutcome:
    """把候选经验追加进 ``path`` 的**当日块**，返回本次的增/跳/更新三组。

    口径①：当日块内出现同一 ``norm()`` ⇒ **跳过**。
    口径④：文件**任意位置**已有同一 ``norm()`` 键而原始文本不同 ⇒ **不覆盖**，
    在当日块追加 ``（更新 YYYY-MM-DD）`` 新行，旧行原样保留（经验是审计面）。
    其余 ⇒ 当日块追加普通行；当日块不存在时在文件尾新建（**其余块逐字节不动**）。
    """
    day = (on_date or date.today()).isoformat()
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []

    today_start, today_end = _locate_day_block(lines, day)
    today_norms = {
        norm_learning(match.group("text"))
        for line in lines[today_start:today_end]
        if (match := _BULLET_RE.match(line)) is not None
    }
    seen_norms: dict[str, str] = {}
    for line in lines:
        match = _BULLET_RE.match(line)
        if match is not None:
            seen_norms.setdefault(norm_learning(match.group("text")), match.group("text"))

    added: list[str] = []
    skipped: list[str] = []
    updated: list[str] = []
    new_lines: list[str] = []
    for text in texts:
        cleaned = str(text).strip()
        if not cleaned:
            continue
        key = norm_learning(cleaned)
        if not key or key in today_norms:
            skipped.append(cleaned)
            continue
        previous = seen_norms.get(key)
        if previous is not None and previous.strip() != cleaned:
            row = f"- {cleaned}{_UPDATE_TEMPLATE.format(day=day)}"
            updated.append(cleaned)
        else:
            row = f"- {cleaned}"
            added.append(cleaned)
        new_lines.append(row)
        today_norms.add(key)

    if not new_lines:
        return AppendOutcome(skipped=tuple(skipped))

    if today_start >= 0:
        merged = [*lines[:today_end], *new_lines, *lines[today_end:]]
    else:
        merged = [
            *lines,
            *([""] if lines and lines[-1].strip() else []),
            f"## {day}",
            "",
            *new_lines,
        ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(merged).rstrip("\n") + "\n", encoding="utf-8")
    return AppendOutcome(added=tuple(added), skipped=tuple(skipped), updated=tuple(updated))


def _locate_day_block(lines: Sequence[str], day: str) -> tuple[int, int]:
    """当日块的内容区间 ``[start, end)``（不含标题行）；没有则 ``(-1, -1)``。"""
    start = -1
    for index, line in enumerate(lines):
        heading = _DAY_HEADING_RE.match(line)
        if heading is None:
            continue
        if start >= 0:
            return start, index
        if heading.group("day") == day:
            start = index + 1
    if start >= 0:
        return start, len(lines)
    return -1, -1


def count_project_occurrences(
    host_workspace: Path, text: str, *, exclude: str | None = None
) -> int:
    """该要点在多少个**不同项目**的 LEARNINGS 里已出现（上浮判据的输入）。"""
    key = norm_learning(text)
    if not key:
        return 0
    root = projects_dir(host_workspace)
    if not root.is_dir():
        return 0
    count = 0
    for candidate in sorted(root.iterdir()):
        if not candidate.is_dir() or candidate.name == exclude:
            continue
        if key in {norm_learning(item) for item in read_learnings_points(_project_file(candidate))}:
            count += 1
    return count


def _project_file(directory: Path) -> Path:
    return directory / TEAM_LEARNINGS_NAME


# ── 三层召回 + 注入（读侧）───────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class LearningPoint:
    """一条要点 + 它来自哪一层（``source_layer`` 与 T-36 同词表）。"""

    text: str
    source_layer: MemoryLayer
    source_id: str = ""


RecallPoints = Callable[[], Sequence[LearningPoint]]
"""服务层直读某一层的要点（项目层用它；host 工具面读不到 ``project_{id}``）。"""

EventSink = Callable[[str, Mapping[str, Any]], None]
"""非 ``ErrorCode`` 事件的观测端：``(event_name, payload)``，默认只写日志。"""


def _log_event(event: str, payload: Mapping[str, Any]) -> None:
    """默认观测端：结构化日志（调用方可注入真实指标端）。"""
    logger.warning("%s %s", event, dict(payload))


def _dedupe_points(points: Iterable[LearningPoint]) -> tuple[LearningPoint, ...]:
    """跨层去重：同一归一文本只保留**先出现**的那层（项目 > 团队 > agent）。

    用 LEARNINGS 行的 ``norm_learning``（它本身由 ``normalize_memory_text`` 组合而来）：
    注入块里的"同一句话"可能来自文件与记忆两侧，空白/标点差异不该让它出现两遍。
    """
    out: list[LearningPoint] = []
    seen: set[str] = set()
    for point in points:
        key = norm_learning(point.text)
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        out.append(point)
    return tuple(out)


def read_memory_layers(
    *,
    host_workspace: Path,
    project_id: str | None = None,
    project_points: RecallPoints | None = None,
    host_points: Sequence[LearningPoint] = (),
    per_layer_limit: int = 5,
) -> tuple[LearningPoint, ...]:
    """按 **项目 → 团队 → agent 私有** 取三层要点并跨层去重（顺序即继承次序）。

    项目层只在**有 ``project_id`` 且调用方给了服务层直读入口**时取（不猜项目）；
    团队层读工作区文件；私有层是调用方用 host 自己的 ``memory_search``/``memory_get``
    取好后传进来的（白名单既有，本模块不碰工具面）。
    """
    collected: list[LearningPoint] = []
    if project_id is not None and project_points is not None:
        collected.extend(
            LearningPoint(text=point.text, source_layer="project", source_id=point.source_id)
            for point in tuple(project_points())[: max(0, per_layer_limit)]
            if str(point.text).strip()
        )
    team = read_learnings_points(team_learnings_path(host_workspace), limit=per_layer_limit)
    collected.extend(LearningPoint(text=text, source_layer="team", source_id="") for text in team)
    collected.extend(
        LearningPoint(text=point.text, source_layer="agent", source_id=point.source_id)
        for point in tuple(host_points)[: max(0, per_layer_limit)]
        if str(point.text).strip()
    )
    return _dedupe_points(collected)


def render_injection(points: Sequence[LearningPoint], *, max_chars: int = 600) -> str:
    """渲染注入块（含逐字注入头）；无要点返回空串（**不注入空块**）。"""
    if not points:
        return ""
    lines = [INJECTION_HEADER]
    budget = max(0, max_chars - len(INJECTION_HEADER) - 1)
    for point in points:
        row = f"- {point.text.strip()}"
        if len(row) > budget:
            if budget <= 2:
                break
            row = row[: budget - 1] + "…"
        lines.append(row)
        budget -= len(row) + 1
        if budget <= 0:
            break
    return "\n".join(lines)


def build_host_memory_block(
    *,
    host_workspace: Path,
    project_id: str | None = None,
    project_points: RecallPoints | None = None,
    host_points: Sequence[LearningPoint] = (),
    per_layer_limit: int = 5,
    max_chars: int = 600,
) -> str:
    """注入侧的**唯一入口**：三层召回 + 渲染（调用方把它追加到 host system prompt）。

    生产接线点 = ``infra/agents/manager.py · _apply_team_host_config`` 内的就地拼接
    （``prompt = prompt + build_host_memory_block(host_workspace=…)``，**本轮实测 ``manager.py @3460``**）；
    ★ **定义处（不是接线）** = ``teams/team_manager.py · host_system_prompt``（**本轮实测 ``@87`` 是 ``def``**）
    —— 原写「生产接线点 = ``teams/team_manager.py · host_system_prompt @87``」**把定义处当接线处**（``T-87`` 实测定正）。
    接线已在 ``manager.py`` 落地；本模块仍是库。
    """
    points = read_memory_layers(
        host_workspace=host_workspace,
        project_id=project_id,
        project_points=project_points,
        host_points=host_points,
        per_layer_limit=per_layer_limit,
    )
    return render_injection(points, max_chars=max_chars)


# ── 上浮判定（项目 → 团队，代码判、打印理由）───────────────────────────────────


def should_promote_to_team(
    text: str,
    *,
    reusable: bool = False,
    recurrence: int = 0,
) -> tuple[bool, str]:
    """判定一条经验是否**跨项目可复用**，返回 ``(是否上浮, 理由)``。

    规则（自上而下，第一条命中即返回；理由可打印、可断言）：

    1. 调用方显式标记 ``reusable=True`` ⇒ ``"explicit"``；
    2. 已在 **≥2 个其它项目**的 LEARNINGS 里出现 ⇒ ``"seen-in-{n}-projects"``；
    3. 文本带通用做法标记（通用 / 所有项目 / 跨项目 / 流程红线）⇒ ``"general-marker"``；
    4. 否则 ``(False, "project-specific")`` —— 留在项目级，不上浮。
    """
    if reusable:
        return True, "explicit"
    if recurrence >= 2:
        return True, f"seen-in-{recurrence}-projects"
    if any(marker in text for marker in _GENERAL_MARKERS):
        return True, "general-marker"
    return False, "project-specific"


# ── deliver 蒸馏（写侧）───────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class LearningCandidate:
    """一条待蒸馏的经验（``reusable`` 由蒸馏/复盘侧标注）。"""

    text: str
    reusable: bool = False


class StructuredMemoryWriter(Protocol):
    """服务层直写 ``project_{project_id}`` 的写入面（由调用方注入）。"""

    def write_summary(self, *, project_id: str, run_id: str, text: str) -> str | None: ...


class KnowledgeArchiver(Protocol):
    """第 3 条写入（KB 落库）的 public 面。

    协议本身**不含** ``kb_document_id`` 的回写（那是 :class:`ProjectKbArchiver` 在实现侧
    做的最后一跳）—— T-18 的调用点与签名因此一字未动。
    """

    def existing_digests(self, *, project_id: str) -> Collection[str]: ...

    def write_document(self, *, project_id: str, text: str, digest: str) -> str | None: ...


class KbDocumentCreator(Protocol):
    """KB 侧 public 写/查面（生产实现 = :class:`KnowledgeServiceDocuments`）。"""

    def create_text_document(self, *, kb_id: str, name: str, text: str) -> str: ...

    def existing_document_names(self, *, kb_id: str) -> Collection[str]: ...


class KbDocumentIdWriter(Protocol):
    """``project_artifacts.kb_document_id`` 的**唯一写者**（`ProjectArtifactRepo` 满足）。"""

    def set_kb_document_id(self, artifact_id: str, kb_document_id: str) -> bool: ...


class KnowledgeServiceDocuments:
    """把既有 ``KnowledgeService`` 的 public 面适配成归档用的两个方法（**KB 侧零改动**）。

    文件名里带回内容摘要（``LEARNINGS-{digest}.md``），因此"同一份蒸馏重跑一次"能被
    :meth:`existing_document_names` 认出来 ⇒ 去重口径②在 KB 这一侧也真实生效，
    而不需要 KB 再长一个 content-hash 列。
    """

    DOCUMENT_PREFIX = "LEARNINGS-"

    def __init__(self, service: Any, *, actor_user_id: int, is_admin: bool = False) -> None:
        self._service = service
        self._actor_user_id = actor_user_id
        self._is_admin = is_admin

    def create_text_document(self, *, kb_id: str, name: str, text: str) -> str:
        row = self._service.create_text_document(
            kb_id,
            actor_user_id=self._actor_user_id,
            is_admin=self._is_admin,
            name=name,
            format="md",
            content=text,
        )
        return str(row.id)

    def existing_document_names(self, *, kb_id: str) -> Collection[str]:
        rows = self._service.list_documents(
            kb_id, actor_user_id=self._actor_user_id, is_admin=self._is_admin
        )
        return tuple(str(getattr(row, "filename", "") or "") for row in rows)


class ProjectKbArchiver:
    """T-18 ``KnowledgeArchiver`` 的默认实现：归档一段蒸馏文本，并把引用绑回工件行。

    构造即绑定上下文（``kb_id`` + ``artifact_id``）⇒ **per-(项目, 归档行) 一个实例**，
    这样 T-18 已交付的协议与调用点（``distill_and_append``）**一字未动**。

    最后一跳（``set_kb_document_id``）是 ``project_artifacts.kb_document_id`` 的**唯一写者**：
    本类不写 SQL、不建行、不改 KB —— 它只把"引用"从 KB 那侧搬到工件行，
    让 `kb_source.KbReference.from_artifact_row` 读得回来（**记忆只存引用，不复制正文**）。
    """

    def __init__(
        self,
        *,
        documents: KbDocumentCreator,
        artifacts: KbDocumentIdWriter,
        kb_id: str,
        artifact_id: str,
    ) -> None:
        self._documents = documents
        self._artifacts = artifacts
        self._kb_id = kb_id
        self._artifact_id = artifact_id

    def document_name(self, digest: str) -> str:
        """KB 文档名 = 前缀 + 摘要（去重口径②靠它认出"同一份蒸馏"）。"""
        return f"{KnowledgeServiceDocuments.DOCUMENT_PREFIX}{digest}.md"

    def existing_digests(self, *, project_id: str) -> Collection[str]:
        """KB 里已归档的摘要集合（由文档名反解，见 :class:`KnowledgeServiceDocuments`）。"""
        prefix = KnowledgeServiceDocuments.DOCUMENT_PREFIX
        names = self._documents.existing_document_names(kb_id=self._kb_id)
        return tuple(
            name[len(prefix) : -3]
            for name in names
            if name.startswith(prefix) and name.endswith(".md")
        )

    def write_document(self, *, project_id: str, text: str, digest: str) -> str | None:
        """建 KB 文档 ⇒ **绑引用**（唯一写者）⇒ 返回文档 id。"""
        document_id = self._documents.create_text_document(
            kb_id=self._kb_id, name=self.document_name(digest), text=text
        )
        self._artifacts.set_kb_document_id(self._artifact_id, document_id)
        return document_id


class ProjectMemoryWriter:
    """把一条 run 摘要写进 ``project_{project_id}`` 的默认实现。

    复用 T-36 的 :meth:`MultiNsRecall.memory_for`（它的 docstring 已写明 writer 走这条），
    因此命名空间解析、缓存与后端选择都不在本模块重写；**agent 的
    ``HarnessAgentConfig(name=…)`` 一个字节都不碰**（N1 单值互斥会让成员丢私有记忆）。
    """

    def __init__(self, recall: MultiNsRecall) -> None:
        self._recall = recall

    def write_summary(self, *, project_id: str, run_id: str, text: str) -> str | None:
        memory = self._recall.memory_for("project", project_id=project_id)
        event: RawEvent = memory.add_raw(
            text,
            event_type="host_memory_write",
            host="octop",
            session_id=f"team-run:{run_id}",
        )
        return str(event.id)


@dataclass(frozen=True, slots=True)
class DistillResult:
    """``distill_and_append`` 的可审计结果（含降级理由）。"""

    project_added: tuple[str, ...] = ()
    project_skipped: tuple[str, ...] = ()
    project_updated: tuple[str, ...] = ()
    team_promoted: tuple[str, ...] = ()
    promotion_reasons: tuple[tuple[str, str], ...] = ()
    structured_memory_id: str | None = None
    inject_version: int | None = None
    kb_document_id: str | None = None
    degraded: tuple[str, ...] = field(default_factory=tuple)


def _record_degraded(reason: str, sink: EventSink) -> None:
    """记事件 ``learnings.degraded`` 并继续交付（第 2/3 条失败不阻塞）。

    观测端是可注入的 :data:`EventSink`（默认只写日志）—— 与 T-12 归属门禁的
    ``_noop_event`` 同款：``METRICS`` 目前没有通用计数器（它是 dataclass 固定字段），
    本卡不新增计数器，也不给自己造第二个事件通道。
    """
    logger.warning("%s reason=%s", DEGRADED_EVENT, reason)
    sink(DEGRADED_EVENT, {"reason": reason})


def distill_and_append(
    *,
    host_workspace: Path,
    project_id: str,
    run_id: str,
    candidates: Sequence[LearningCandidate],
    on_date: date | None = None,
    summary: str | None = None,
    memory_writer: StructuredMemoryWriter | None = None,
    inject_version: ProjectInjectVersion | None = None,
    kb_archiver: KnowledgeArchiver | None = None,
    event_sink: EventSink | None = None,
) -> DistillResult:
    """deliver 时的交付蒸馏：主写入 + 结构化记忆 + 跨项目知识 + 上浮。

    * **主写入**（项目级 LEARNINGS）失败 ⇒ **向上抛**（协议要求的最低经验面，阻塞交付）；
    * 结构化记忆 / KB / 上浮任一失败或能力缺失 ⇒ 记 ``learnings.degraded`` 并继续；
    * 结构化记忆写成功后调用既有的 ``inject_version.note_write(project_id)``（水位 bump）。
    """
    texts = [candidate.text for candidate in candidates if str(candidate.text).strip()]
    outcome = append_learnings(
        project_learnings_path(host_workspace, project_id), texts, on_date=on_date
    )

    degraded: list[str] = []
    structured_id: str | None = None
    version: int | None = None
    kb_document_id: str | None = None

    payload = summary if summary is not None else "\n".join(outcome.added)
    if not payload.strip():
        degraded.append("structured-memory:empty-summary")
    elif memory_writer is None:
        degraded.append("structured-memory:unavailable")
    else:
        try:
            structured_id = memory_writer.write_summary(
                project_id=project_id, run_id=run_id, text=payload
            )
        except Exception:  # noqa: BLE001 - 第 2 条失败只降级，不阻塞交付
            logger.warning("learnings structured memory write failed", exc_info=True)
            degraded.append("structured-memory:failed")

    if structured_id is not None and inject_version is not None:
        try:
            version = int(inject_version.note_write(project_id))
        except Exception:  # noqa: BLE001 - 水位失守不影响记忆写入本身
            logger.warning("learnings inject_version bump failed", exc_info=True)
            degraded.append("inject-version:failed")

    document_text = "\n".join([*outcome.added, *outcome.updated])
    if not document_text.strip():
        degraded.append("kb:empty-document")
    elif kb_archiver is None:
        degraded.append("kb:unavailable")
    else:
        try:
            digest = learning_digest(document_text)
            if digest in {
                str(item) for item in kb_archiver.existing_digests(project_id=project_id)
            }:
                degraded.append("kb:duplicate")
            else:
                kb_document_id = kb_archiver.write_document(
                    project_id=project_id, text=document_text, digest=digest
                )
        except Exception:  # noqa: BLE001 - 第 3 条失败只降级，不阻塞交付
            logger.warning("learnings kb archive failed", exc_info=True)
            degraded.append("kb:failed")

    promoted: list[str] = []
    reasons: list[tuple[str, str]] = []
    for candidate in candidates:
        text = str(candidate.text).strip()
        if not text:
            continue
        recurrence = count_project_occurrences(host_workspace, text, exclude=project_id)
        promote, reason = should_promote_to_team(
            text, reusable=candidate.reusable, recurrence=recurrence
        )
        reasons.append((text, reason))
        if promote:
            promoted.append(text)

    if promoted:
        try:
            append_learnings(team_learnings_path(host_workspace), promoted, on_date=on_date)
        except OSError:
            logger.warning("learnings team-level promotion failed", exc_info=True)
            degraded.append("team-learnings:failed")
            promoted = []

    sink = event_sink or _log_event
    for reason in degraded:
        _record_degraded(reason, sink)

    return DistillResult(
        project_added=outcome.added,
        project_skipped=outcome.skipped,
        project_updated=outcome.updated,
        team_promoted=tuple(promoted),
        promotion_reasons=tuple(reasons),
        structured_memory_id=structured_id,
        inject_version=version,
        kb_document_id=kb_document_id,
        degraded=tuple(degraded),
    )


__all__ = [
    "DEFAULT_TITLE",
    "DEGRADED_EVENT",
    "INJECTION_HEADER",
    "PROJECTS_DIRNAME",
    "TEAM_DIR_PARTS",
    "TEAM_LEARNINGS_NAME",
    "AppendOutcome",
    "DistillResult",
    "EventSink",
    "KnowledgeArchiver",
    "KnowledgeServiceDocuments",
    "KbDocumentCreator",
    "KbDocumentIdWriter",
    "ProjectKbArchiver",
    "LearningCandidate",
    "LearningPoint",
    "ProjectMemoryWriter",
    "RecallPoints",
    "StructuredMemoryWriter",
    "append_learnings",
    "build_host_memory_block",
    "count_project_occurrences",
    "dedupe_by_digest",
    "distill_and_append",
    "learning_digest",
    "norm_learning",
    "project_learnings_path",
    "projects_dir",
    "read_learnings_points",
    "read_memory_layers",
    "render_injection",
    "should_promote_to_team",
    "team_learnings_path",
]
