"""Tests for SkillHub skillset normalization into expert templates."""

from __future__ import annotations

import io
import json
import re
import zipfile


def _zip_bytes(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def _has_cjk(text: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", text))


def test_skillhub_manifest_generates_bilingual_quick_prompts() -> None:
    from octop.infra.agents.experts.skillhub_market import (
        SkillHubSkillset,
        _expert_manifest,
    )

    item = SkillHubSkillset(
        slug="tech-test-automation",
        display_name="技术测试自动化",
        display_name_en="Tech Test Automation",
        summary="自动生成测试方案",
        summary_en="Generate test plans",
        scene="tech",
    )

    manifest = _expert_manifest(item, ["playwright", "pytest"])

    assert manifest["id"] == "skillhub-skillset-tech-test-automation"
    assert manifest["prompt_files"] == ["SOUL.md"]
    assert manifest["label"]["zh"] == "技术测试自动化专家"
    assert manifest["label"]["en"] == "Tech Test Automation Expert"
    assert manifest["quick_prompts"][0]["title"]["zh"]
    assert manifest["quick_prompts"][0]["title"]["en"]
    assert "playwright" in manifest["skillhub"]["skill_slugs"]


def test_skillhub_manifest_generates_workflow_quick_prompts() -> None:
    from octop.infra.agents.experts.skillhub_market import (
        SkillHubSkillset,
        _expert_manifest,
    )

    item = SkillHubSkillset(
        slug="media-storyboard-design",
        display_name="分镜设计",
        scene="media",
        content="""# 分镜设计工作流

## 步骤 1：剧本到分镜表格转换（获取层）
- 将剧本文本解析为结构化分镜表格

输出标准分镜表格和拍摄计划。

## 步骤 2：电影感镜头运动设计（获取层）
- 为每个分镜设计镜头运动方案

输出镜头运动设计方案和机位规划。
""",
    )

    manifest = _expert_manifest(item, ["script-to-storyboard"])

    assert [p["title"]["zh"] for p in manifest["quick_prompts"]] == [
        "剧本到分镜表格转换",
        "电影感镜头运动设计",
    ]
    assert manifest["quick_prompts"][0]["description"]["zh"] == "生成标准分镜表格和拍摄计划"
    prompt = manifest["quick_prompts"][0]["prompt"]["zh"]
    assert "请作为「分镜设计专家」，按以下方式引导我" in prompt
    assert "将剧本文本解析为结构化分镜表格" in prompt
    assert "请输出：标准分镜表格和拍摄计划。" in prompt
    assert "请基于以下目标和材料推进" not in prompt
    assert manifest["quick_prompts"][0]["icon_name"] == "video"
    first = manifest["quick_prompts"][0]
    assert first["title"]["en"] == "Workflow step 1"
    assert first["description"]["en"] == "Run this step and produce the requested deliverable"
    assert not _has_cjk(first["title"]["en"])
    assert not _has_cjk(first["description"]["en"])
    assert not _has_cjk(first["prompt"]["en"])
    assert first["prompt"]["en"].endswith("My context, goals, or materials are:\n")


def test_skillhub_manifest_keeps_up_to_nine_workflow_quick_prompts() -> None:
    from octop.infra.agents.experts.skillhub_market import (
        SkillHubSkillset,
        _expert_manifest,
    )

    workflow = "# 工作流\n\n" + "\n\n".join(
        f"## 步骤 {idx}：步骤标题 {idx}（处理层）\n- 执行动作 {idx}\n\n输出交付物 {idx}。"
        for idx in range(1, 11)
    )
    item = SkillHubSkillset(
        slug="demo",
        display_name="演示专家",
        scene="tech",
        content=workflow,
    )

    manifest = _expert_manifest(item, ["demo"])

    assert len(manifest["quick_prompts"]) == 9
    assert manifest["quick_prompts"][0]["title"]["zh"] == "步骤标题 1"
    assert manifest["quick_prompts"][-1]["title"]["zh"] == "步骤标题 9"


def test_fetch_skillsets_uses_skillhub_pagination(monkeypatch) -> None:
    from octop.infra.agents.experts import skillhub_market

    calls: list[str] = []

    def fake_json_get(url: str) -> dict[str, object]:
        calls.append(url)
        if "page=1" in url:
            return {
                "skillSets": [
                    {"slug": "one", "displayName": "One"},
                    {"slug": "two", "displayName": "Two"},
                ],
                "total": 3,
            }
        return {
            "skillSets": [{"slug": "three", "displayName": "Three"}],
            "total": 3,
        }

    monkeypatch.setattr(skillhub_market, "_SKILLSET_PAGE_SIZE", 2)
    monkeypatch.setattr(skillhub_market, "_http_json_get", fake_json_get)

    items = skillhub_market.fetch_skillsets()

    assert [item.slug for item in items] == ["one", "two", "three"]
    assert "page=1" in calls[0]
    assert "pageSize=2" in calls[0]
    assert "page=2" in calls[1]


def test_skillhub_manifest_skill_slugs_are_deduped() -> None:
    from octop.infra.agents.experts.skillhub_market import _manifest_skill_slugs

    manifest = {
        "skillSets": [
            {"skillSlugs": ["alpha", "beta"]},
            {"skillSlugs": ["beta", "gamma"]},
        ]
    }

    assert _manifest_skill_slugs(manifest) == ["alpha", "beta", "gamma"]


def test_parse_skillset_package_prefers_matching_skillsets_prompt() -> None:
    from octop.infra.agents.experts.skillhub_market import _parse_skillset_package

    manifest = {"skillSets": [{"slug": "target", "skillSlugs": ["alpha"]}]}
    package = _zip_bytes(
        {
            "manifest.json": json.dumps(manifest),
            "identify.md": "# Wrong prompt\n",
            "skillsets/other.md": "# Other prompt\n",
            "skillsets/target.md": "# Target workflow\n",
        }
    )

    parsed_manifest, prompt = _parse_skillset_package(
        package,
        skillset_slug="target",
        fallback_content="# Fallback\n",
    )

    assert parsed_manifest == manifest
    assert prompt == "# Target workflow\n"


def test_parse_skillset_package_uses_identify_for_single_skillset() -> None:
    from octop.infra.agents.experts.skillhub_market import _parse_skillset_package

    manifest = {"skillSlugs": ["alpha"]}
    package = _zip_bytes(
        {
            "manifest.json": json.dumps(manifest),
            "identify.md": "# Single skillset workflow\n",
        }
    )

    _parsed_manifest, prompt = _parse_skillset_package(
        package,
        skillset_slug="target",
        fallback_content="# Fallback\n",
    )

    assert prompt == "# Single skillset workflow\n"


def test_skillhub_dedupes_repeated_frontmatter() -> None:
    from octop.infra.agents.experts.skillhub_market import _dedupe_frontmatter

    text = "---\ntitle: Demo\n---\n---\ntitle: Demo\n---\n# Body\n"

    assert _dedupe_frontmatter(text) == "---\ntitle: Demo\n---\n\n# Body\n"
