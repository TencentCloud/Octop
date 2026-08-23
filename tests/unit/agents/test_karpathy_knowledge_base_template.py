"""Regression tests for the bundled Karpathy-style knowledge-base expert."""

from __future__ import annotations

import json

from octop.infra.agents.experts.catalog import ExpertCatalog, default_library_root

_ROOT = default_library_root() / "karpathy-knowledge-base"


def test_template_is_discoverable_and_has_initialized_workspace() -> None:
    catalog = ExpertCatalog(default_library_root())
    catalog.refresh()

    expert = catalog.get("karpathy-knowledge-base")
    assert expert is not None
    assert expert.summary.label_zh == "卡帕西知识库专家"

    expected = {
        "SOUL.md",
        "AGENTS.md",
        "BOOTSTRAP.md",
        "MEMORY.md",
        "knowledge-base/raw/README.md",
        "knowledge-base/wiki/index.md",
        "knowledge-base/wiki/overview.md",
        "knowledge-base/wiki/log.md",
        "skills/llm-wiki/SKILL.md",
    }
    assert expected <= set(expert.files)


def test_manifest_exposes_knowledge_workflows() -> None:
    manifest = json.loads((_ROOT / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["id"] == "karpathy-knowledge-base"
    assert {"SOUL.md", "AGENTS.md", "BOOTSTRAP.md"} <= set(manifest["prompt_files"])
    titles = {item["title"]["zh"] for item in manifest["quick_prompts"]}
    assert {"初始化知识主题", "摄取新资料", "查询知识库", "运行知识库体检"} <= titles


def test_memory_is_a_bounded_index_and_raw_is_immutable() -> None:
    memory = (_ROOT / "MEMORY.md").read_text(encoding="utf-8")
    agents = (_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    skill = (_ROOT / "skills" / "llm-wiki" / "SKILL.md").read_text(encoding="utf-8")

    assert len(memory.splitlines()) <= 200
    assert "knowledge-base/wiki/index.md" in memory
    assert "不是事实证据" in memory
    assert "已摄取来源不可改写" in agents
    assert "Ingest" in skill
    assert "Query" in skill
    assert "Lint" in skill
    assert "maximum 200 lines" in skill
