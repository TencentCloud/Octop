"""T-23 · 记忆契约：两侧一致，任一侧回退即变红（`T-18.verify` 指向本文件）。

`T-18` 的验收里有几条**天生是"两处事实必须互相成立"**的契约 —— 单看任一侧都绿，
只有把两侧放进**同一条断言**里，回退才会暴露：

* **措辞 ↔ 白名单**：`template/MEMORY.md` 向团队主持人承诺「写工具不在 host 白名单里」；
  这句话必须与 `service.HOST_TOOLS_ALLOWED` 的**实际内容**同时成立。
  只测"模板里没有『读写』"或只测"白名单里没有 write_file"，**任一侧单独回退都能溜过去**。
* **注入头 ↔ 长度上限**：`INJECTION_HEADER` 是逐字契约（不得改写/本地化），
  而 `render_injection` 承诺「只取要点（有长度上限）」⇒ 两者必须同时成立。
* **三层顺序 ↔ 去重归属**：顺序是 项目 → 团队 → agent 私有，而跨层去重必须
  保留**先出现**的那层 ⇒ 顺序错了、或去重保留了后一层，都必须红。

**与 `backend-2` 的口径对账**：他当时因"不越界创建他人落点"把自测放在
`tests/unit/agents/test_team_learnings.py`（43 例），并明确说"T-23 落地后它的 4 条契约
断言应与我这边一致"。本文件就是那 4 条的**独立版本**：期望值逐条对齐
（`write_file`/`edit_file` 不在白名单、`memory_search`/`memory_get` 在；
注入头逐字；模板无『读写』且有『交付蒸馏』；四层去重规则 1/4 的语义）。
**两侧同跑**：`uv run pytest tests/unit/agents/test_team_learnings.py \
tests/unit/agents/test_team_memory_contract.py -q` —— 若本文件红而他的绿（或反之），
就是"同一事实两处定义"的 finding，报 lead，**不自行统一口径**。
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest

from octop.infra.agents.settings.tool_catalog import BUILTIN_TOOL_CATALOG
from octop.infra.agents.teams import learnings as L
from octop.infra.agents.teams.service import HOST_TOOLS_ALLOWED, TEMPLATE_DIR

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MEMORY_TEMPLATE = TEMPLATE_DIR / "MEMORY.md"
_LEARNINGS_SRC = _REPO_ROOT / "src" / "octop" / "infra" / "agents" / "teams" / "learnings.py"

#: T-18 acc.7 逐字点名的两个写工具；两侧判据都锚在它们身上。
_WRITE_TOOLS = ("write_file", "edit_file")


def _point(text: str, layer: str, source_id: str = "") -> L.LearningPoint:
    return L.LearningPoint(text=text, source_layer=layer, source_id=source_id)  # type: ignore[arg-type]


# ─────────────────────────────────────────────────────────────────────────────
# 契约①：模板措辞 ↔ host 白名单（两侧必须同时成立）
# ─────────────────────────────────────────────────────────────────────────────


def test_the_template_read_only_promise_is_true_of_the_actual_allowlist() -> None:
    """**两侧合一的断言** —— 任一侧回退都会让这条红。

    * A 侧（措辞）：模板不得再出现『读写』，且必须写明写侧由交付蒸馏完成。
    * B 侧（事实）：模板那句承诺必须**真的是真的** —— 写工具不在白名单里。
    * 非空防护：两个写工具必须**仍存在于工具目录**，否则改个名字就能让 B 侧变得空洞。
    """
    text = _MEMORY_TEMPLATE.read_text(encoding="utf-8")

    # ── A 侧：措辞 ──────────────────────────────────────────────────────────
    assert "读写" not in text, "B25 收口：模板不得再写『读写』"
    assert "交付蒸馏" in text, "写侧必须指向交付蒸馏（代码，deliver 阶段）"
    assert "主持人用记忆工具**读**" in text
    assert "写工具不在 host 白名单里" in text, "模板的这句承诺是下面 B 侧的被测对象"

    # ── 非空防护：先证明这两个名字确实在目录里（否则 B 侧恒真） ─────────────
    catalog_names = {entry.name for entry in BUILTIN_TOOL_CATALOG}
    for tool in _WRITE_TOOLS:
        assert tool in catalog_names, f"{tool} 不在工具目录里 ⇒ 下面的白名单断言会变空洞"

    # ── B 侧：事实 ──────────────────────────────────────────────────────────
    allowed_write_tools = sorted(set(_WRITE_TOOLS) & set(HOST_TOOLS_ALLOWED))
    assert allowed_write_tools == [], (
        f"模板承诺『写工具不在 host 白名单里』，但 {allowed_write_tools} 在白名单里 ⇒ 措辞与事实相反"
    )

    # 承诺的另一半：只读记忆工具必须**在**白名单里（否则主持人读不到记忆）
    assert {"memory_search", "memory_get"} <= set(HOST_TOOLS_ALLOWED)


def test_the_shipped_template_is_the_one_this_contract_reads() -> None:
    """防止本文件读错文件：契约必须落在**真正发给团队主持人**那一份上。"""
    assert _MEMORY_TEMPLATE.is_file()
    assert TEMPLATE_DIR.name == "template"
    assert _MEMORY_TEMPLATE.name == "MEMORY.md"


def test_no_tool_whose_name_implies_writing_is_allowed() -> None:
    """比点名两个工具更宽的一层：**凡是名字带"写/改/建/删"的，都不该在白名单里**。

    这不是替代上一条（T-18 逐字点名 `write_file`/`edit_file`），而是防止
    "有人新加一个 `patch_file` 到目录并顺手放进白名单"这种漂移。
    """
    suspicious = {
        entry.name
        for entry in BUILTIN_TOOL_CATALOG
        if any(k in entry.name for k in ("write", "edit", "patch", "delete", "remove", "move"))
    }
    leaked = sorted(suspicious & set(HOST_TOOLS_ALLOWED))
    assert leaked == [], f"名字含写/改/删的工具被放进了 host 白名单：{leaked}"


# ─────────────────────────────────────────────────────────────────────────────
# 契约②：注入头（逐字）↔ 长度上限
# ─────────────────────────────────────────────────────────────────────────────


def _authoritative_header() -> str:
    """权威落点由 ``TEAM_DIR_PARTS`` 推导 —— 不复制今天的字符串。

    ★ 这样绑定的是"**哪条路径是权威**"这件事本身：改了载体（``TEAM_DIR_PARTS``）而忘了
    header ⇒ 本断言红；而不是把新路径又硬编码一遍（那只是把旧串换成新串）。
    """
    workspace = Path("/ws")
    rel = L.team_learnings_path(workspace).relative_to(workspace).as_posix()
    return f"【既往经验（仅要点；完整版见 {rel}，相关时才读）】"


def test_the_injection_header_is_the_verbatim_protocol_string() -> None:
    assert "既往经验" in L.INJECTION_HEADER
    assert "仅要点" in L.INJECTION_HEADER
    assert L.INJECTION_HEADER.startswith("【") and L.INJECTION_HEADER.endswith("】")
    # 不得本地化 / 不得改写：英文夹带或改标点都应红
    # 原断言（逐字 `team/LEARNINGS.md`）已由本 run 的 SPEC B-19（甲）取代 —— 权威落点是 `.octop/team/LEARNINGS.md`（见 learnings.py 的 TEAM_DIR_PARTS）；翻转而不删除。
    assert _authoritative_header() == L.INJECTION_HEADER


def test_rendered_block_starts_with_the_header_and_respects_the_cap() -> None:
    """头与上限**同时**成立：只测头会被"无限长"绕过，只测上限会被"无头"绕过。"""
    points = [_point("甲" * 80, "project"), _point("乙" * 80, "team")]
    block = L.render_injection(points, max_chars=120)

    assert block.startswith(L.INJECTION_HEADER)
    assert len(block) <= 120, f"注入块超过上限：{len(block)}"
    assert "仅要点" in block


def test_no_points_renders_no_block() -> None:
    """空输入不得产出"只有头"的空块（那会把一句没有内容的提示塞进 system prompt）。"""
    assert L.render_injection([]) == ""
    assert L.render_injection([], max_chars=600) == ""


# ─────────────────────────────────────────────────────────────────────────────
# 契约③：三层顺序 ↔ 跨层去重归属
# ─────────────────────────────────────────────────────────────────────────────


def test_layers_are_ordered_project_then_team_then_agent(tmp_path: Path) -> None:
    """顺序 + 来源层标注同时断言；项目层经**服务层直读入口**而非 host 工具面。"""
    team_path = L.team_learnings_path(tmp_path)
    team_path.parent.mkdir(parents=True, exist_ok=True)
    team_path.write_text("# LEARNINGS\n\n## 2026-01-01\n\n- 团队经验\n", encoding="utf-8")

    points = L.read_memory_layers(
        host_workspace=tmp_path,
        project_id="P1",
        project_points=lambda: [_point("项目经验", "project")],
        host_points=[_point("私有经验", "agent")],
    )

    assert [p.source_layer for p in points] == ["project", "team", "agent"]
    assert [p.text for p in points] == ["项目经验", "团队经验", "私有经验"]


def test_a_duplicate_across_layers_keeps_the_earlier_layer(tmp_path: Path) -> None:
    """同一句话出现在项目层与团队层 ⇒ **保留项目层**（顺序即继承，先出现者胜）。"""
    team_path = L.team_learnings_path(tmp_path)
    team_path.parent.mkdir(parents=True, exist_ok=True)
    team_path.write_text("# LEARNINGS\n\n## 2026-01-01\n\n- 同一句话\n", encoding="utf-8")

    points = L.read_memory_layers(
        host_workspace=tmp_path,
        project_id="P1",
        project_points=lambda: [_point("同一句话", "project")],
        host_points=[_point("同一句话", "agent")],
    )

    assert [(p.source_layer, p.text) for p in points] == [("project", "同一句话")]


def test_without_project_context_the_project_layer_is_never_guessed(tmp_path: Path) -> None:
    """不猜项目：无 `project_id` 时连入口都不调用。"""
    called: list[int] = []

    def _recall() -> list[L.LearningPoint]:
        called.append(1)
        return [_point("不该被取到", "project")]

    points = L.read_memory_layers(host_workspace=tmp_path, project_points=_recall)

    assert called == [], "无项目上下文却调用了项目层读入口"
    assert points == ()


# ─────────────────────────────────────────────────────────────────────────────
# 契约④：写侧 ns = project_{id}（行为断言，不看文档话术）
# ─────────────────────────────────────────────────────────────────────────────


class _SpyMemory:
    def add_raw(self, text: str, **kwargs: Any) -> Any:
        return type("Ev", (), {"id": f"raw-{text[:4]}"})()


class _SpyRecall:
    """记录 `memory_for` 的层与参数 —— 写侧 ns 的**行为**证据。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def memory_for(self, layer: str, **kwargs: Any) -> Any:
        self.calls.append((layer, kwargs))
        return _SpyMemory()


def test_the_project_writer_asks_for_the_project_layer_explicitly() -> None:
    """写侧必须显式要 `project` 层 —— ns 解析交给 T-36 的唯一真源，本模块不自己拼。"""
    recall = _SpyRecall()
    writer = L.ProjectMemoryWriter(recall)  # type: ignore[arg-type]

    writer.write_summary(project_id="P1", run_id="r1", text="摘要")

    assert recall.calls == [("project", {"project_id": "P1"})]


def test_learnings_never_constructs_a_harness_agent_config() -> None:
    """静态侧：`T-18` 的 N1 互斥红线 —— 本模块**不得构造** `HarnessAgentConfig`。

    只查"构造"形态（`HarnessAgentConfig(`），不看 docstring：该模块的文档里**故意**
    提到这个名字来解释"绝不碰它"，所以纯 grep 名字会误报。
    """
    source = _LEARNINGS_SRC.read_text(encoding="utf-8")
    code_lines = [
        line
        for line in source.splitlines()
        if "HarnessAgentConfig(" in line and not line.lstrip().startswith(("#", "*", '"""', "``"))
    ]
    assert code_lines == [], f"learnings.py 在代码里构造了 HarnessAgentConfig：{code_lines}"

    # 同时：不得出现"用 agent 私有 ns 写项目记忆"的拼法
    assert "agent_memory_namespace" not in source.replace("agent_memory_namespace``", "")


# ─────────────────────────────────────────────────────────────────────────────
# 契约⑤：LEARNINGS 按项目分文件（两个 project ⇒ 两条物理路径）
# ─────────────────────────────────────────────────────────────────────────────


def test_two_projects_resolve_to_two_distinct_files(tmp_path: Path) -> None:
    p1 = L.project_learnings_path(tmp_path, "P1")
    p2 = L.project_learnings_path(tmp_path, "P2")
    team = L.team_learnings_path(tmp_path)

    assert p1 != p2
    assert p1 != team and p2 != team
    assert p1.relative_to(tmp_path).as_posix() == ".octop/team/projects/P1/LEARNINGS.md"
    assert p2.relative_to(tmp_path).as_posix() == ".octop/team/projects/P2/LEARNINGS.md"
    assert team.relative_to(tmp_path).as_posix() == ".octop/team/LEARNINGS.md"


def test_rule1_skips_a_text_duplicate_inside_the_same_day_block(tmp_path: Path) -> None:
    """去重口径①：当日块内同一 `norm()` ⇒ 跳过（不产生第二行）。"""
    path = tmp_path / "LEARNINGS.md"
    outcome_a = L.append_learnings(path, ["照常落盘的经验"], on_date=date(2026, 1, 1))
    outcome_b = L.append_learnings(path, ["照常落盘的经验。"], on_date=date(2026, 1, 1))

    assert outcome_a.added == ("照常落盘的经验",)
    assert outcome_b.added == ()
    assert outcome_b.skipped == ("照常落盘的经验。",)
    body = path.read_text(encoding="utf-8")
    assert body.count("照常落盘的经验") == 1


def test_rule4_same_key_different_text_appends_an_update_line(tmp_path: Path) -> None:
    """去重口径④：**同一 ``norm()`` 键**但原文不同、且落在**不同日块** ⇒ 不覆盖，
    在当日块追加『（更新 …）』，旧行原样保留（经验是审计面）。

    注意键是 ``norm_learning``（折空白/标点/大小写）——所以"旧的说法"与"旧的说法。"
    是同一个键；而"旧的说法"与"新的说法"是**两个不同的键**（那是两条经验，不是更新）。
    日块必须不同，否则先命中口径①（同日块重复 ⇒ 跳过）。
    """
    path = tmp_path / "LEARNINGS.md"
    L.append_learnings(path, ["旧的说法"], on_date=date(2026, 1, 1))
    outcome = L.append_learnings(path, ["旧的说法。"], on_date=date(2026, 1, 2))

    assert outcome.updated == ("旧的说法。",), outcome
    body = path.read_text(encoding="utf-8")
    assert body.count("旧的说法") == 2, "旧行必须保留 + 新行是『更新』"
    assert "（更新 2026-01-02）" in body


@pytest.mark.parametrize("missing", ["", "   "])
def test_a_blank_point_is_not_a_point(tmp_path: Path, missing: str) -> None:
    """空白要点不得进注入块（它没有身份，会把"空"渲染成一条经验）。"""
    points = L.read_memory_layers(
        host_workspace=tmp_path,
        project_id="P1",
        project_points=lambda: [_point(missing, "project")],
        host_points=[],
    )
    assert points == ()
