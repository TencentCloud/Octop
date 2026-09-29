"""AM-4 (T-33): the host's duties live in **roster data**, not in template prose.

The team host's job used to be defined twice — once in ``template/SOUL.md`` and once in
``template/AGENTS.md`` — which is the "one fact, two copies" failure this repo keeps
paying for. These cases pin the pointer form: both templates *reference* the roster data
(``manifest.json · members[].role`` / ``lead_agent_id`` and the run snapshot
``team_run_members.is_lead``) instead of restating a duty list, while the pure
style/tone guidance ("how you talk") stays where it was.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from octop.infra.agents.teams.service import (
    MANIFEST_LEAD_KEY,
    seed_team_template,
)

TEMPLATE_DIR = Path(__file__).resolve().parents[3] / "src/octop/infra/agents/teams/template"
SOUL = TEMPLATE_DIR / "SOUL.md"
AGENTS = TEMPLATE_DIR / "AGENTS.md"
MANIFEST = TEMPLATE_DIR / "manifest.json"

#: 模板里必须出现的**指针键名**（指向编制数据，而不是重述职责）。
ROSTER_KEYS = ("lead_agent_id", "members[].role", "team_run_members.is_lead")

#: 纯风格/语气内容 —— 不属于「谁指挥谁」的数据事实，必须保留。
STYLE_MARKERS = {
    "SOUL.md": ("你怎么说话", "不要复述", "红线"),
    "AGENTS.md": ("调度", "红线", "不要用成员的口吻冒充发言"),
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize("path", [SOUL, AGENTS])
def test_templates_define_no_duty_list_and_point_at_roster_data(path: Path) -> None:
    """① 两个模板里不再出现「唯一职责」式职责定义，改为指向编制数据的指针。"""
    text = _read(path)
    assert "你的唯一职责" not in text
    # 旧的四条职责清单标题/条目不得复现（听清/拆分/派工/收口 作为**定义列表**）。
    assert "## 你的唯一职责" not in text
    # 指针：必须点名编制数据的键，而不是再写一份职责定义。
    for key in ROSTER_KEYS:
        assert key in text, f"{path.name} missing roster pointer {key}"
    assert ".octop/manifest.json" in text


def test_duty_pointer_is_not_duplicated_as_a_second_definition() -> None:
    """指针可以两处出现；**定义**不行 —— 两个模板都不得再列「1./2./3.」职责条目。"""
    for path in (SOUL, AGENTS):
        text = _read(path)
        for bullet in ("1. **听清**", "2. **拆分**", "3. **派工**", "4. **收口**"):
            assert bullet not in text, f"{path.name} still defines duties: {bullet}"


def test_manifest_template_carries_lead_agent_id_null() -> None:
    """② 模板 manifest 含 `lead_agent_id` 且默认 `null`（= 团队 host 自己主持）。"""
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert data["kind"] == "team"
    assert MANIFEST_LEAD_KEY in data
    assert data[MANIFEST_LEAD_KEY] is None
    assert data["members"] == []


@pytest.mark.parametrize("path", [SOUL, AGENTS])
def test_style_and_tone_content_survives(path: Path) -> None:
    """③ 风格/语气类内容未被误删（不是「谁指挥谁」的数据事实）。"""
    text = _read(path)
    for marker in STYLE_MARKERS[path.name]:
        assert marker in text, f"{path.name} lost style marker {marker!r}"
    assert "原样转发" in text


def test_duties_never_reach_any_memory_layer() -> None:
    """★ 硬约束（SPEC B31）：职责是编制数据，**不得**进任何记忆层。"""
    memory = TEMPLATE_DIR / "MEMORY.md"
    assert memory.is_file()
    text = _read(memory)
    assert "职责" not in text
    assert "负责" not in text


@pytest.mark.asyncio
async def test_seeded_workspace_exposes_the_pointer_target(tmp_path: Path) -> None:
    """④ 模板渲染进工作区后，host 仍能读到指针指向的数据路径。"""
    uploaded: dict[str, bytes] = {}

    class _Workspace:
        async def aupload_many(self, pairs: list[tuple[str, bytes]]) -> None:
            uploaded.update(pairs)

        async def aread_text(self, rel: str) -> str | None:
            raw = uploaded.get(rel)
            return raw.decode("utf-8") if raw is not None else None

    await seed_team_template(_Workspace(), member_ids=["a", "b"])
    # 指针指向的路径确实存在，且带的就是模板里点名的键。
    assert ".octop/manifest.json" in uploaded
    manifest = json.loads(uploaded[".octop/manifest.json"].decode("utf-8"))
    assert MANIFEST_LEAD_KEY in manifest
    assert manifest[MANIFEST_LEAD_KEY] is None
    assert [m["agent_id"] for m in manifest["members"]] == ["a", "b"]
    # 模板里点名的两个 manifest 键，在播种产物里都能找到（指针可解析）。
    for key in ("lead_agent_id", "members"):
        assert key in manifest
