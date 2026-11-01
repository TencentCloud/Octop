"""Contract tests for bundled business-operations expert."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from deepagents.backends.local_shell import LocalShellBackend
from octop_harness.backends.workspace import BackendWorkspace
from octop_harness.middleware.bootstrap import bootstrap_marker_exists

from octop.infra.agents.experts.catalog import (
    WORKSPACE_MANIFEST_PATH,
    ExpertCatalog,
    default_library_root,
    discover_seed_paths,
    preview_file_paths,
    seed_expert_directory,
)

EXPERT_DIR = default_library_root() / "business-operations"
EXPECTED_SKILLS = {
    "bo-process-doc",
    "bo-runbook",
    "bo-process-optimization",
    "bo-risk-assessment",
    "bo-vendor-review",
    "bo-status-report",
}


def test_business_operations_catalog_and_manifest() -> None:
    catalog = ExpertCatalog(default_library_root())
    catalog.refresh()
    expert = catalog.get("business-operations")
    assert expert is not None
    assert expert.summary.label_zh == "业务流程专家"
    manifest = json.loads((EXPERT_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["id"] == "business-operations"
    assert set(manifest["prompt_files"]) == {"SOUL.md", "AGENTS.md", "IDENTITY.md", "BOOTSTRAP.md"}
    assert "BOOTSTRAP.md" in preview_file_paths(expert)
    assert len(manifest["quick_prompts"]) == 6
    assert len(manifest["task_examples"]["zh"]) == len(manifest["task_examples"]["en"]) == 6
    assert all(
        q["title"]["zh"] and q["title"]["en"] and q["prompt"]["zh"] and q["prompt"]["en"]
        for q in manifest["quick_prompts"]
    )


def test_business_operations_skill_files_and_attribution() -> None:
    dirs = {p.name for p in (EXPERT_DIR / "skills").iterdir() if p.is_dir()}
    assert dirs == EXPECTED_SKILLS
    files = discover_seed_paths(EXPERT_DIR)
    for name in EXPECTED_SKILLS:
        rel = f"skills/{name}/SKILL.md"
        assert rel in files
        raw = (EXPERT_DIR / rel).read_text(encoding="utf-8")
        assert raw.startswith(f"---\nname: {name}\n")
        assert "\ndescription:" in raw.split("---", 2)[1]
        # Modified upstream files must carry their own notice, not only a directory notice.
        notice = raw.split("---", 2)[2].strip().split("\n\n", 1)[0]
        assert "已为 Octop 改编" in notice
    for name in EXPECTED_SKILLS:
        assert name in (EXPERT_DIR / "SOUL.md").read_text(encoding="utf-8")
    # The shared README and its complete upstream license must ship with the expert.
    assert "README.md" in files
    readme = (EXPERT_DIR / "README.md").read_text(encoding="utf-8")
    license_bytes = readme.split("```text\n", 1)[1].split("```", 1)[0].encode("utf-8")
    assert hashlib.sha256(license_bytes).hexdigest() == (
        "a6946284993aeec75c7d75906064b66210c46051e562077efb30eb6dcfe72e26"
    )
    assert "02ffa99ff00ce4d3046ccebabb8357cb39f3ab06" in readme


def test_business_operations_marks_unknowns_without_claiming_nonexistence() -> None:
    soul = (EXPERT_DIR / "SOUL.md").read_text(encoding="utf-8")
    assert "尚未提供或现有证据尚未核实" in soul
    assert "不得据此断言事实不存在、没有负责人、无人掌握或从未发生" in soul
    assert "必须标为建议/提议" in soul
    assert "不要从步骤顺序推定缺件何时发现" in soul
    assert "标题也按事实核验" in soul

    guidance = (EXPERT_DIR / "AGENTS.md").read_text(encoding="utf-8")
    assert "已知审批延迟但未说明约束哪一步时" in guidance
    assert "“材料未提供”只表示当前材料没有这项信息" in guidance
    assert "同一事实结论、控制措施或总结清单只在一处完整列出" in guidance
    assert "不得为去重删掉执行条件" in guidance
    assert "跨来源或按人去重的指标，分别标明分子、分母对应的事件记录" in guidance
    assert "只在一个环节补标识，不能据此声称另一来源的人数分母可识别" in guidance
    assert "不同业务事件（如核销与到场）不得默认视为同一口径" in guidance
    assert "只有材料明确给出口径时才能互相替代" in guidance
    assert "不得把相邻事件的发生点当作该端点" in guidance
    assert "超出每人一次的事件数，不是发生重复事件的人数" in guidance
    assert "只补齐分母或仅有代理事件，不足以声称指标可算" in guidance
    assert "指标核算或状态报告用 `bo-status-report`" in soul
    assert "若指标任务还要求改进建议或衡量/记录方案，另读 `bo-process-optimization`" in soul
    assert "同一请求兼有两者时两项都读" in soul

    runbook = (EXPERT_DIR / "skills/bo-runbook/SKILL.md").read_text(encoding="utf-8")
    assert "每步仍须就地写明执行所必需的前置条件、判断门槛和保护点" in runbook
    assert "不能为避免重复而删掉执行门槛" in runbook
    assert "例如，“仅在行数一致时保存”应写在保存步骤中" in runbook

    process_doc = (EXPERT_DIR / "skills/bo-process-doc/SKILL.md").read_text(encoding="utf-8")
    assert "不得把延迟并入最近的核对、分派等已知步骤" in process_doc
    assert "不再把“谁分派”列为未知" in process_doc

    optimization = (EXPERT_DIR / "skills/bo-process-optimization/SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "流程先后本身不能证明问题最早何时被发现" in optimization

    status_report = (EXPERT_DIR / "skills/bo-status-report/SKILL.md").read_text(encoding="utf-8")
    assert "材料未提供后续安排，只能写“安排未提供”" in status_report


@pytest.mark.parametrize("language", ["zh", "en"])
async def test_seeded_business_bootstrap_survives_workspace_init(
    tmp_path: Path, language: str
) -> None:
    """Exercise real seeding and harness init without creating a model or completion marker."""
    workspace = BackendWorkspace(
        LocalShellBackend(root_dir=str(tmp_path), virtual_mode=False), tmp_path
    )
    paths = discover_seed_paths(EXPERT_DIR)
    assert "BOOTSTRAP.md" in paths
    copied = await seed_expert_directory(expert_dir=EXPERT_DIR, workspace=workspace)
    assert copied == len(paths) + 1
    assert {workspace.resolve_path(name) for name in ("SOUL.md", "AGENTS.md")} <= set(
        workspace.memory_paths()
    )
    assert not bootstrap_marker_exists(workspace)
    manifest = json.loads((EXPERT_DIR / "manifest.json").read_text(encoding="utf-8"))

    result = workspace.init_workspace(
        language=language,
        include_md_files=True,
        include_skills=False,
        include_agents=False,
        overwrite=False,
    )

    assert workspace.resolve_path("BOOTSTRAP.md") in result.templates_skipped
    for rel in manifest["prompt_files"]:
        assert await workspace.adownload_bytes(rel) == (EXPERT_DIR / rel).read_bytes()
    for name in EXPECTED_SKILLS:
        rel = f"skills/{name}/SKILL.md"
        assert await workspace.adownload_bytes(rel) == (EXPERT_DIR / rel).read_bytes()
    assert (
        await workspace.adownload_bytes(WORKSPACE_MANIFEST_PATH)
        == (EXPERT_DIR / "manifest.json").read_bytes()
    )
    assert "{{BOOTSTRAP_MARKER}}" not in (workspace.read_text("BOOTSTRAP.md") or "")
    assert not bootstrap_marker_exists(workspace)
    assert not workspace.exists(workspace.system_rel(".bootstrapped"))
