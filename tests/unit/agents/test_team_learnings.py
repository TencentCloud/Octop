"""T-18 —— 团队记忆接线：LEARNINGS 蒸馏 / 三层召回 / 注入 / 失败语义。

八条验收逐条有可失败用例；三处"接线"另有独立断言（``ProjectInjectVersion`` 的写入侧
由本模块接上、结构化记忆落 ``project_{project_id}``、agent 的
``HarnessAgentConfig(name=…)`` 一个字节都没被碰）。

端到端部分用**真 sqlite 记忆库**（真 ``MultiNsRecall``）＋**真工作区文件**，
不 mock 被测链本身；只把"能力缺失/失败"这两种外部条件用替身造出来。
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from octop.infra.agents.teams import learnings as L
from octop.infra.agents.teams.service import HOST_TOOLS_ALLOWED

pytest.importorskip("octop_memory.core")

from octop.config import OctopConfig
from octop.infra.agents.memory.multi_ns import (
    MemoryScope,
    MultiNsRecall,
    ProjectInjectVersion,
)

AGENT_ID = "a1"
PROJECT_ID = "P1"
RUN_ID = "R1"
DAY = date(2026, 9, 29)

_TEMPLATE = Path(__file__).resolve().parents[3] / "src" / "octop" / "infra" / "agents" / "teams"
_MEMORY_TEMPLATE_PATH = _TEMPLATE / "template" / "MEMORY.md"
_LEARNINGS_SOURCE_PATH = _TEMPLATE / "learnings.py"


class _FakeProjectRepo:
    """``ProjectInjectVersion`` 的既有协议（``bump_inject_version``）的替身。"""

    def __init__(self) -> None:
        self.bumps: list[str] = []

    def bump_inject_version(self, project_id: str) -> int:
        self.bumps.append(project_id)
        return len(self.bumps)


class _EventLog:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, event: str, payload: dict[str, Any]) -> None:
        self.events.append((event, payload))

    @property
    def reasons(self) -> list[str]:
        return [
            str(payload.get("reason")) for name, payload in self.events if name == L.DEGRADED_EVENT
        ]


def _recall(tmp_path: Path, *, team_agent_id: str | None = None) -> MultiNsRecall:
    return MultiNsRecall(
        MemoryScope(
            agent_id=AGENT_ID,
            cfg={
                "memory": {
                    "backend": {"type": "sqlite", "db_path": str(tmp_path / "memory.sqlite")}
                }
            },
            octop_config=OctopConfig(),
            workspace_dir=tmp_path,
            team_agent_id=team_agent_id,
        )
    )


def _distill(
    workspace: Path,
    *,
    candidates: list[L.LearningCandidate] | None = None,
    project_id: str = PROJECT_ID,
    **kwargs: Any,
) -> L.DistillResult:
    return L.distill_and_append(
        host_workspace=workspace,
        project_id=project_id,
        run_id=RUN_ID,
        candidates=candidates or [],
        on_date=DAY,
        **kwargs,
    )


# ─────────────────────────────────────────────────────────────────────────────
# ① 注入：注入头逐字 + 只取要点 + 长度上限
# ─────────────────────────────────────────────────────────────────────────────


def _authoritative_header() -> str:
    """权威落点由 ``TEAM_DIR_PARTS`` 推导 —— 不复制今天的字符串。

    ★ 这样绑定的是"**哪条路径是权威**"这件事本身：改了载体（``TEAM_DIR_PARTS``）而忘了
    header ⇒ 本断言红；而不是把新路径又硬编码一遍（那只是把旧串换成新串）。
    """
    workspace = Path("/ws")
    rel = L.team_learnings_path(workspace).relative_to(workspace).as_posix()
    return f"【既往经验（仅要点；完整版见 {rel}，相关时才读）】"


def test_injection_block_starts_with_the_verbatim_header() -> None:
    block = L.render_injection(
        [
            L.LearningPoint("先跑 ruff 再收工", "project"),
            L.LearningPoint("派工要改写任务书", "team"),
        ]
    )

    assert (
        block.splitlines()[0]
        == L.INJECTION_HEADER
        # 原断言（逐字 `team/LEARNINGS.md`）已由本 run 的 SPEC B-19（甲）取代 —— 权威落点是 `.octop/team/LEARNINGS.md`（见 learnings.py 的 TEAM_DIR_PARTS）；翻转而不删除。
        == _authoritative_header()
    )
    assert block.splitlines()[1:] == ["- 先跑 ruff 再收工", "- 派工要改写任务书"]
    assert "完整版" in block, "只给要点，完整版指向文件"


def test_injection_block_has_no_length_escape() -> None:
    points = [L.LearningPoint("很长的经验" * 40, "project") for _ in range(20)]

    block = L.render_injection(points, max_chars=200)

    assert len(block) <= 200
    assert all(line.startswith("- ") for line in block.splitlines()[1:])


def test_no_points_means_no_block() -> None:
    assert L.render_injection([]) == ""
    assert L.build_host_memory_block(host_workspace=Path("/nonexistent")) == ""


# ─────────────────────────────────────────────────────────────────────────────
# ② 三层召回：顺序 = 项目 → 团队 → agent 私有；①② 层不经 host 工具
# ─────────────────────────────────────────────────────────────────────────────


def test_layers_come_back_in_the_fixed_order(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    L.append_learnings(L.team_learnings_path(workspace), ["团队层经验"], on_date=DAY)
    calls: list[str] = []

    def project_reader() -> tuple[L.LearningPoint, ...]:
        calls.append("project")
        return (L.LearningPoint("项目层经验", "project"),)

    points = L.read_memory_layers(
        host_workspace=workspace,
        project_id=PROJECT_ID,
        project_points=project_reader,
        host_points=[L.LearningPoint("私有层经验", "agent")],
    )

    assert [point.source_layer for point in points] == ["project", "team", "agent"]
    assert [point.text for point in points] == ["项目层经验", "团队层经验", "私有层经验"]
    assert calls == ["project"], "项目层由服务层直读入口取（host 工具面读不到它）"


def test_team_layer_is_read_by_this_module_not_by_a_host_tool(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    L.append_learnings(L.team_learnings_path(workspace), ["只存在于团队文件里的经验"], on_date=DAY)

    points = L.read_memory_layers(host_workspace=workspace, host_points=[])

    assert [point.text for point in points] == ["只存在于团队文件里的经验"]


def test_project_layer_is_not_guessed_without_context(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    calls: list[str] = []

    points = L.read_memory_layers(
        host_workspace=workspace,
        project_id=None,
        project_points=lambda: calls.append("project") or (),  # type: ignore[func-returns-value]
        host_points=[L.LearningPoint("私有", "agent")],
    )

    assert calls == [], "没有项目上下文就不许打开项目层"
    assert [point.source_layer for point in points] == ["agent"]


def test_a_project_layer_never_reads_another_project_file(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    L.append_learnings(L.project_learnings_path(workspace, "P2"), ["P2 专属经验"], on_date=DAY)

    points = L.read_memory_layers(
        host_workspace=workspace,
        project_id=PROJECT_ID,
        project_points=lambda: (),
    )

    assert points == (), "项目层文件按 project_id 物理隔离"


def test_cross_layer_duplicate_keeps_the_earlier_layer(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    L.append_learnings(L.team_learnings_path(workspace), ["同一句话"], on_date=DAY)

    points = L.read_memory_layers(
        host_workspace=workspace,
        project_id=PROJECT_ID,
        project_points=lambda: (L.LearningPoint("同一句话", "project"),),
        host_points=[L.LearningPoint("  同一句话。 ", "agent")],
    )

    assert [(point.source_layer, point.text) for point in points] == [("project", "同一句话")]


def test_build_host_memory_block_feeds_the_documented_injection_point(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    L.append_learnings(L.team_learnings_path(workspace), ["注入要点"], on_date=DAY)

    block = L.build_host_memory_block(host_workspace=workspace)

    assert block.startswith(L.INJECTION_HEADER)
    assert "- 注入要点" in block


# ─────────────────────────────────────────────────────────────────────────────
# ③ 结构化记忆落 project_{project_id}，agent 私有层与 HarnessAgentConfig 不动
# ─────────────────────────────────────────────────────────────────────────────


def test_structured_memory_lands_in_the_project_namespace_only(tmp_path: Path) -> None:
    from octop_memory.core import Memory

    workspace = tmp_path / "ws"
    recall = _recall(tmp_path)
    result = _distill(
        workspace,
        candidates=[L.LearningCandidate("流程红线：不写 Hindsight")],
        memory_writer=L.ProjectMemoryWriter(recall),
    )

    assert result.structured_memory_id is not None
    config = {"db_path": str(tmp_path / "memory.sqlite")}
    project = Memory(namespace=f"project_{PROJECT_ID}", backend="sqlite", backend_config=config)
    agent = Memory(namespace=f"agent_{AGENT_ID}", backend="sqlite", backend_config=config)

    assert [event.content for event in project.list_raw(limit=10)] == ["流程红线：不写 Hindsight"]
    assert agent.list_raw(limit=10) == [], "agent 私有层不得被交付蒸馏写入"


def test_learnings_never_touches_the_agent_harness_config() -> None:
    """硬约束（T-35/N1）：只改写入 ns，绝不改 ``HarnessAgentConfig(name=…)``。

    用 AST 只看**代码**引用（docstring 里提到这个名字是说明，不是触碰）：
    不 import manager、不出现该名字、不自己拼 ns。
    """
    import ast

    tree = ast.parse(_LEARNINGS_SOURCE_PATH.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.add(str(node.module))
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    code_names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    code_names |= {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}

    assert "octop.infra.agents.manager" not in imported
    assert "HarnessAgentConfig" not in code_names
    assert "agent_memory_namespace" not in code_names, "前缀拼法只有 memory/backend.py 一处"
    assert "open_memory_kwargs" not in code_names, "ns 解析复用 multi_ns，不在这里重写"

    from octop.infra.agents.manager import _memory_namespace

    assert _memory_namespace(AGENT_ID) == f"agent_{AGENT_ID}"


def test_structured_memory_writer_reuses_the_multi_ns_writer_path() -> None:
    """写侧走的正是 T-36 为 writer 预留的那条（``memory_for('project')``）。"""
    calls: list[tuple[str, dict[str, Any]]] = []

    class _SpyRecall:
        def memory_for(self, layer: str, **kwargs: Any) -> Any:
            calls.append((layer, kwargs))
            raise RuntimeError("stop here")

    writer = L.ProjectMemoryWriter(_SpyRecall())  # type: ignore[arg-type]
    with pytest.raises(RuntimeError):
        writer.write_summary(project_id=PROJECT_ID, run_id=RUN_ID, text="x")

    assert calls == [("project", {"project_id": PROJECT_ID})]


# ─────────────────────────────────────────────────────────────────────────────
# ④ LEARNINGS 按项目分文件
# ─────────────────────────────────────────────────────────────────────────────


def test_two_projects_write_two_physically_separate_files(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    _distill(workspace, candidates=[L.LearningCandidate("P1 的经验")], project_id="P1")
    _distill(workspace, candidates=[L.LearningCandidate("P2 的经验")], project_id="P2")

    p1 = L.project_learnings_path(workspace, "P1")
    p2 = L.project_learnings_path(workspace, "P2")

    assert p1 != p2
    assert p1.is_file() and p2.is_file()
    assert "P1 的经验" in p1.read_text(encoding="utf-8")
    assert "P2 的经验" not in p1.read_text(encoding="utf-8")
    assert "P1 的经验" not in p2.read_text(encoding="utf-8")


def test_project_file_path_shape_matches_the_plan() -> None:
    workspace = Path("/ws")

    assert L.project_learnings_path(workspace, "P1") == Path(
        "/ws/.octop/team/projects/P1/LEARNINGS.md"
    )
    assert L.team_learnings_path(workspace) == Path("/ws/.octop/team/LEARNINGS.md")


# ─────────────────────────────────────────────────────────────────────────────
# ⑤ 上浮：项目 → 团队（代码判、打印理由、单向）
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "reusable", "recurrence", "expected"),
    [
        ("随便一条", True, 0, (True, "explicit")),
        ("随便一条", False, 2, (True, "seen-in-2-projects")),
        ("随便一条", False, 5, (True, "seen-in-5-projects")),
        ("流程红线：禁写仓库", False, 0, (True, "general-marker")),
        ("所有项目都必须先跑回归", False, 0, (True, "general-marker")),
        ("这条只对本项目有意义", False, 0, (False, "project-specific")),
        ("这条只对本项目有意义", False, 1, (False, "project-specific")),
    ],
)
def test_promotion_rules_and_reasons(
    text: str, reusable: bool, recurrence: int, expected: tuple[bool, str]
) -> None:
    assert L.should_promote_to_team(text, reusable=reusable, recurrence=recurrence) == expected


def test_general_practice_is_promoted_into_the_team_file(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    result = _distill(
        workspace,
        candidates=[
            L.LearningCandidate("流程红线：不写 Hindsight"),
            L.LearningCandidate("这条只对本项目有意义"),
        ],
    )

    team_file = L.team_learnings_path(workspace)
    assert result.team_promoted == ("流程红线：不写 Hindsight",)
    assert dict(result.promotion_reasons)["这条只对本项目有意义"] == "project-specific"
    content = team_file.read_text(encoding="utf-8")
    assert "流程红线：不写 Hindsight" in content
    assert "这条只对本项目有意义" not in content, "项目专属经验不得进团队级"


def test_recurrence_across_projects_promotes_without_any_flag(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    text = "先跑 ruff 再收工"
    for other in ("PA", "PB"):
        L.append_learnings(L.project_learnings_path(workspace, other), [text], on_date=DAY)

    result = _distill(workspace, candidates=[L.LearningCandidate(text)], project_id="PC")

    assert result.team_promoted == (text,)
    assert dict(result.promotion_reasons)[text] == "seen-in-2-projects"


def test_promotion_is_one_way_and_keeps_the_project_copy(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    text = "流程红线：不写 Hindsight"
    _distill(workspace, candidates=[L.LearningCandidate(text)])

    assert text in L.project_learnings_path(workspace, PROJECT_ID).read_text(encoding="utf-8")
    assert text in L.team_learnings_path(workspace).read_text(encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# ⑥ 去重四层（①文本 ②哈希 ③语义不做 ④冲突追加）
# ─────────────────────────────────────────────────────────────────────────────


def test_rule1_text_level_duplicate_in_the_same_day_block_is_skipped(tmp_path: Path) -> None:
    path = tmp_path / "LEARNINGS.md"
    first = L.append_learnings(path, ["先跑 ruff 再收工。"], on_date=DAY)
    second = L.append_learnings(path, ["  先跑   ruff 再收工  "], on_date=DAY)

    assert first.added == ("先跑 ruff 再收工。",)
    assert second.added == ()
    assert second.skipped == ("先跑   ruff 再收工",)
    assert path.read_text(encoding="utf-8").count("先跑") == 1


def test_rule1_does_not_swallow_a_genuinely_new_line(tmp_path: Path) -> None:
    path = tmp_path / "LEARNINGS.md"
    L.append_learnings(path, ["第一条经验"], on_date=DAY)

    assert L.append_learnings(path, ["第二条经验"], on_date=DAY).added == ("第二条经验",)


def test_rule2_hash_level_duplicate_against_the_kb_is_skipped() -> None:
    text = "已经在 KB 里的经验"
    kept, skipped = L.dedupe_by_digest([text, "新的经验"], [L.learning_digest(text)])

    assert kept == ("新的经验",)
    assert skipped == (text,)
    assert len(L.learning_digest(text)) == 16


def test_rule2_duplicate_document_is_not_archived_twice(tmp_path: Path) -> None:
    written: list[str] = []

    class _Archiver:
        def existing_digests(self, *, project_id: str) -> list[str]:
            return [L.learning_digest("流程红线：不写 Hindsight")]

        def write_document(self, *, project_id: str, text: str, digest: str) -> str:
            written.append(digest)
            return "doc-should-not-exist"

    events = _EventLog()
    result = _distill(
        workspace=tmp_path / "ws",
        candidates=[L.LearningCandidate("流程红线：不写 Hindsight")],
        kb_archiver=_Archiver(),
        event_sink=events,
    )

    assert written == [], "摘要命中既有 KB 文档 ⇒ 跳过，不重复落库"
    assert result.kb_document_id is None
    assert "kb:duplicate" in result.degraded
    assert "kb:duplicate" in events.reasons


def test_rule3_semantic_dedup_is_explicitly_not_done(tmp_path: Path) -> None:
    """口径③：不引向量/语义去重 —— 文本不同就是两条（本模块也不 import 任何向量栈）。"""
    path = tmp_path / "LEARNINGS.md"
    outcome = L.append_learnings(path, ["先跑 ruff 再收工", "收工前必须先跑 ruff"], on_date=DAY)

    assert outcome.added == ("先跑 ruff 再收工", "收工前必须先跑 ruff")
    source = _LEARNINGS_SOURCE_PATH.read_text(encoding="utf-8")
    for forbidden in ("embedding", "vector", "octop_memory.pipeline.recall"):
        assert forbidden not in source


def test_rule4_same_key_different_text_appends_an_update_line(tmp_path: Path) -> None:
    path = tmp_path / "LEARNINGS.md"
    L.append_learnings(path, ["不要 覆盖历史"], on_date=date(2026, 9, 28))

    outcome = L.append_learnings(path, ["不要覆盖历史。"], on_date=DAY)

    content = path.read_text(encoding="utf-8")
    assert outcome.updated == ("不要覆盖历史。",)
    assert outcome.added == ()
    assert "- 不要 覆盖历史" in content, "旧行保留（经验是审计面，不静默改写）"
    assert f"- 不要覆盖历史。{L._UPDATE_TEMPLATE.format(day=DAY.isoformat())}" in content


def test_other_day_blocks_are_left_byte_for_byte(tmp_path: Path) -> None:
    path = tmp_path / "LEARNINGS.md"
    L.append_learnings(path, ["第一天"], on_date=date(2026, 9, 28))
    before = path.read_text(encoding="utf-8")

    L.append_learnings(path, ["第二天"], on_date=DAY)

    after = path.read_text(encoding="utf-8")
    assert after.startswith(before.rstrip("\n")), "整文件不重写：既有块逐字节不动"


def test_read_learnings_points_returns_the_latest() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as raw:
        path = Path(raw) / "LEARNINGS.md"
        L.append_learnings(path, ["一", "二", "三"], on_date=DAY)

        assert L.read_learnings_points(path, limit=2) == ("二", "三")
        assert L.read_learnings_points(Path(raw) / "absent.md") == ()


# ─────────────────────────────────────────────────────────────────────────────
# ⑦ 契约两侧一致：模板措辞 ↔ host 工具白名单
# ─────────────────────────────────────────────────────────────────────────────


def test_memory_template_says_read_only_and_names_the_deliver_distillation() -> None:
    text = _MEMORY_TEMPLATE_PATH.read_text(encoding="utf-8")

    assert "读写" not in text, "B25 收口：模板不得再写『读写』"
    assert "交付蒸馏" in text, "写侧必须指向交付蒸馏（代码）"
    assert "主持人用记忆工具**读**" in text


def test_host_allowlist_has_no_write_tools() -> None:
    assert "write_file" not in HOST_TOOLS_ALLOWED
    assert "edit_file" not in HOST_TOOLS_ALLOWED
    assert "memory_search" in HOST_TOOLS_ALLOWED and "memory_get" in HOST_TOOLS_ALLOWED


def test_the_template_file_is_the_one_shipped_to_team_hosts() -> None:
    from octop.infra.agents.teams.service import TEMPLATE_DIR

    assert TEMPLATE_DIR / "MEMORY.md" == _MEMORY_TEMPLATE_PATH


# ─────────────────────────────────────────────────────────────────────────────
# ⑧ 失败语义：第 1 条阻塞，第 2/3 条降级不阻塞
# ─────────────────────────────────────────────────────────────────────────────


def test_structured_memory_failure_degrades_and_keeps_delivering(tmp_path: Path) -> None:
    class _Broken:
        def write_summary(self, *, project_id: str, run_id: str, text: str) -> str:
            raise RuntimeError("memory backend down")

    events = _EventLog()
    result = _distill(
        workspace=tmp_path / "ws",
        candidates=[L.LearningCandidate("照常落盘的经验")],
        memory_writer=_Broken(),
        event_sink=events,
    )

    assert result.structured_memory_id is None
    assert "structured-memory:failed" in result.degraded
    assert result.project_added == ("照常落盘的经验",)
    assert (L.DEGRADED_EVENT, {"reason": "structured-memory:failed"}) in events.events


def test_kb_failure_degrades_and_keeps_delivering(tmp_path: Path) -> None:
    class _Broken:
        def existing_digests(self, *, project_id: str) -> list[str]:
            raise RuntimeError("kb index unreadable")

        def write_document(self, *, project_id: str, text: str, digest: str) -> str:
            raise RuntimeError("unreachable")

    events = _EventLog()
    result = _distill(
        workspace=tmp_path / "ws",
        candidates=[L.LearningCandidate("照常落盘的经验")],
        kb_archiver=_Broken(),
        event_sink=events,
    )

    assert "kb:failed" in result.degraded
    assert result.project_added == ("照常落盘的经验",)
    assert L.DEGRADED_EVENT in [name for name, _ in events.events]


def test_missing_capabilities_are_reported_as_degraded(tmp_path: Path) -> None:
    result = _distill(workspace=tmp_path / "ws", candidates=[L.LearningCandidate("只有主写入")])

    assert "structured-memory:unavailable" in result.degraded
    assert "kb:unavailable" in result.degraded
    assert result.project_added == ("只有主写入",)


def test_inject_version_failure_degrades_but_memory_is_still_written(tmp_path: Path) -> None:
    class _BrokenRepo:
        def bump_inject_version(self, project_id: str) -> int:
            raise RuntimeError("projects row gone")

    result = _distill(
        workspace=tmp_path / "ws",
        candidates=[L.LearningCandidate("经验")],
        memory_writer=L.ProjectMemoryWriter(_recall(tmp_path)),
        inject_version=ProjectInjectVersion(_BrokenRepo()),  # type: ignore[arg-type]
        event_sink=_EventLog(),
    )

    assert result.structured_memory_id is not None
    assert result.inject_version is None
    assert "inject-version:failed" in result.degraded


def test_primary_learnings_write_failure_blocks_the_delivery(tmp_path: Path) -> None:
    """第 1 条是协议要求的最低经验面 ⇒ 失败必须向上抛，不许静默降级。"""
    workspace = tmp_path / "ws"
    blocked = L.project_learnings_path(workspace, PROJECT_ID)
    blocked.parent.mkdir(parents=True, exist_ok=True)
    blocked.mkdir()

    with pytest.raises(OSError):
        _distill(workspace, candidates=[L.LearningCandidate("写不进去")])


def test_degraded_event_name_is_the_one_in_the_event_table() -> None:
    assert L.DEGRADED_EVENT == "learnings.degraded"


# ─────────────────────────────────────────────────────────────────────────────
# 接线事实：ProjectInjectVersion 的写入侧由本模块接上
# ─────────────────────────────────────────────────────────────────────────────


def test_distill_bumps_the_existing_inject_version_watermark(tmp_path: Path) -> None:
    repo = _FakeProjectRepo()
    watermark = ProjectInjectVersion(repo)

    result = _distill(
        workspace=tmp_path / "ws",
        candidates=[L.LearningCandidate("经验")],
        memory_writer=L.ProjectMemoryWriter(_recall(tmp_path)),
        inject_version=watermark,
    )

    assert repo.bumps == [PROJECT_ID], "项目层写入后必须 bump 水位（既有类，本模块消费）"
    assert result.inject_version == 1
    assert watermark.should_inject(PROJECT_ID, 1) is True, "首次注入判据生效"
    watermark.mark_injected(PROJECT_ID, 1)
    assert watermark.should_inject(PROJECT_ID, 1) is False


def test_distill_result_is_json_serialisable_for_the_timeline(tmp_path: Path) -> None:
    result = _distill(
        workspace=tmp_path / "ws",
        candidates=[L.LearningCandidate("可序列化的经验")],
        memory_writer=L.ProjectMemoryWriter(_recall(tmp_path)),
    )

    payload = {
        "project_added": list(result.project_added),
        "team_promoted": list(result.team_promoted),
        "degraded": list(result.degraded),
    }
    assert json.loads(json.dumps(payload))["project_added"] == ["可序列化的经验"]
