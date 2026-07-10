"""Tests for model-generated SkillHub expert manifest metadata."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest


class FakeLLM:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.messages: list[Any] = []

    async def ainvoke(self, messages: list[Any]) -> SimpleNamespace:
        self.messages = messages
        return SimpleNamespace(
            content=f"```json\n{json.dumps(self.payload, ensure_ascii=False)}\n```"
        )


def _generated_payload() -> dict[str, Any]:
    prompts: list[dict[str, Any]] = []
    for idx, title in enumerate(["启动任务", "规划路径", "分析材料", "生成方案"], start=1):
        prompts.append(
            {
                "title": {"zh": title, "en": f"Card {idx}"},
                "description": {
                    "zh": f"第 {idx} 个专家入口",
                    "en": f"Expert entry {idx}",
                },
                "prompt": {
                    "zh": f"请按专家工作流处理第 {idx} 个任务：\n\n",
                    "en": f"Use the expert workflow for task {idx}:\n\n",
                },
                "color": "#123456",
                "icon_name": "sparkles",
            }
        )
    return {
        "label": {
            "zh": "测试工作流专家",
            "en": "Test Workflow Expert",
        },
        "description": {
            "zh": "按测试工作流组织任务和交付物。",
            "en": "Organizes tasks and deliverables through the test workflow.",
        },
        "welcome_message": {
            "zh": "我是测试专家，可以按工作流推进。",
            "en": "I am the test expert and can follow the workflow.",
        },
        "quick_prompts": prompts,
    }


@pytest.mark.asyncio
async def test_generate_and_apply_skillhub_manifest_assets(tmp_path) -> None:
    from octop.infra.agents.experts.catalog import ExpertCatalog
    from octop.infra.agents.experts.manifest_generator import (
        generate_and_apply_skillhub_manifest_assets,
    )

    expert_dir = tmp_path / "skillhub-skillset-demo"
    (expert_dir / "skills" / "demo").mkdir(parents=True)
    (expert_dir / "skills" / "demo" / "SKILL.md").write_text(
        "---\nname: Demo Workflow\ndescription: Demo workflow description\n---\n# Demo\nDo work.",
        encoding="utf-8",
    )
    (expert_dir / "skills" / "helper").mkdir(parents=True)
    (expert_dir / "skills" / "helper" / "SKILL.md").write_text(
        "---\nname: Helper\ndescription: Helper skill\n---\n# Helper\nAssist.",
        encoding="utf-8",
    )
    (expert_dir / "manifest.json").write_text(
        json.dumps(
            {
                "id": "skillhub-skillset-demo",
                "label": {"zh": "测试专家", "en": "Test Expert"},
                "description": {"zh": "测试描述", "en": "Test description"},
                "welcome_message": {"zh": "fallback", "en": "fallback"},
                "prompt_files": ["SOUL.md"],
                "quick_prompts": [],
                "skillhub": {"skill_slugs": ["helper"]},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    item = SimpleNamespace(
        slug="demo",
        display_name="测试专家",
        display_name_en="Test Expert",
        summary="测试描述",
        summary_en="Test description",
        scene="tech",
        sub_scene="automation",
    )
    ok = await generate_and_apply_skillhub_manifest_assets(
        llm=FakeLLM(_generated_payload()),
        item=item,
        expert_dir=expert_dir,
        model_ref="p/model",
    )

    assert ok is True
    data = json.loads((expert_dir / "manifest.json").read_text(encoding="utf-8"))
    assert data["label"]["zh"] == "测试工作流专家"
    assert data["label"]["en"] == "Test Workflow Expert"
    assert (
        data["description"]["en"] == "Organizes tasks and deliverables through the test workflow."
    )
    assert data["welcome_message"]["zh"] == "我是测试专家，可以按工作流推进。"
    assert len(data["quick_prompts"]) == 4
    assert data["quick_prompts"][0]["title"]["en"] == "Card 1"
    assert data["skillhub"]["manifest_generated"]["model"] == "p/model"
    assert data["skillhub"]["welcome_generated"]["model"] == "p/model"

    catalog = ExpertCatalog(tmp_path)
    catalog.refresh()
    expert = catalog.get("skillhub-skillset-demo")
    assert expert is not None
    assert expert.quick_prompts[0].title_zh == "启动任务"


def test_normalize_manifest_assets_rejects_empty_quick_prompts() -> None:
    from octop.infra.agents.experts.manifest_generator import (
        ExpertManifestGenerationError,
        normalize_manifest_assets,
    )

    with pytest.raises(ExpertManifestGenerationError):
        normalize_manifest_assets(
            {"welcome_message": {"zh": "hi", "en": "hi"}, "quick_prompts": []},
            fallback_name_zh="专家",
            fallback_name_en="Expert",
        )


def test_normalize_manifest_assets_roleizes_fallback_label() -> None:
    from octop.infra.agents.experts.manifest_generator import normalize_manifest_assets

    payload = _generated_payload()
    payload.pop("label")
    payload.pop("description")

    assets = normalize_manifest_assets(
        payload,
        fallback_name_zh="自动化测试",
        fallback_name_en="Test Automation",
        fallback_summary_zh="自动生成测试方案",
        fallback_summary_en="Generate test plans",
    )

    assert assets["label"] == {"zh": "自动化测试专家", "en": "Test Automation Expert"}
    assert assets["description"] == {"zh": "自动生成测试方案", "en": "Generate test plans"}


def test_normalize_manifest_assets_keeps_at_most_nine_quick_prompts() -> None:
    from octop.infra.agents.experts.manifest_generator import normalize_manifest_assets

    payload = _generated_payload()
    payload["quick_prompts"] = [
        {
            "title": {"zh": f"卡片 {idx}", "en": f"Card {idx}"},
            "description": {"zh": f"描述 {idx}", "en": f"Description {idx}"},
            "prompt": {"zh": f"处理任务 {idx}：\n\n", "en": f"Handle task {idx}:\n\n"},
            "color": "#123456",
            "icon_name": "sparkles",
        }
        for idx in range(1, 11)
    ]

    assets = normalize_manifest_assets(
        payload,
        fallback_name_zh="专家",
        fallback_name_en="Expert",
    )

    assert len(assets["quick_prompts"]) == 9
    assert assets["quick_prompts"][-1]["title"]["zh"] == "卡片 9"
