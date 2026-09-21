"""Tests for ExpertCatalog workspace discovery and lazy file reads."""

from __future__ import annotations

import json
from pathlib import Path


def _write_manifest(expert_dir: Path, *, extra: dict | None = None) -> None:
    payload: dict = {
        "id": expert_dir.name,
        "label": {"zh": "测试", "en": "Test"},
        "description": {"zh": "desc", "en": "desc"},
    }
    if extra:
        payload.update(extra)
    (expert_dir / "manifest.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )


def test_expert_discovers_seed_paths(tmp_path: Path) -> None:
    from octop.infra.agents.experts.catalog import ExpertCatalog

    expert_dir = tmp_path / "my-expert"
    expert_dir.mkdir()
    _write_manifest(expert_dir)
    (expert_dir / "SOUL.md").write_text("# Soul\nhello", encoding="utf-8")
    skill = expert_dir / "skills" / "my-skill" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("# Skill", encoding="utf-8")

    catalog = ExpertCatalog(tmp_path)
    catalog.refresh()

    expert = catalog.get("my-expert")
    assert expert is not None
    assert "SOUL.md" in expert.files
    assert "skills/my-skill/SKILL.md" in expert.files
    assert expert.prompt_files == []


def test_resolve_expert_icon_url_uses_scene_for_skillhub() -> None:
    from octop.infra.agents.experts.catalog import resolve_expert_icon_url

    assert (
        resolve_expert_icon_url(
            "skillhub-skillset-healthcare-nursing-plan",
            None,
            scene="healthcare",
        )
        == "/experts/avatars/scene-healthcare.svg"
    )
    # Do not invent missing per-skillset SVG paths.
    assert (
        resolve_expert_icon_url(
            "skillhub-skillset-healthcare-nursing-plan",
            "/experts/avatars/skillhub-skillset-healthcare-nursing-plan.svg",
            scene="healthcare",
        )
        == "/experts/avatars/scene-healthcare.svg"
    )
    assert resolve_expert_icon_url("stock-assistant", None) == (
        "/experts/avatars/stock-assistant.svg"
    )
    assert resolve_expert_icon_url(
        "external",
        "https://cdn.example.com/a.png",
    ) == ("https://cdn.example.com/a.png")


def test_bundled_avatar_ids_discovered_from_public_dir() -> None:
    from octop.infra.agents.experts.catalog import (
        _BUNDLED_AVATAR_IDS,
        bundled_avatars_dir,
        discover_bundled_avatar_ids,
    )

    avatars = bundled_avatars_dir()
    assert avatars is not None
    discovered = discover_bundled_avatar_ids(avatars)
    assert "stock-assistant" in discovered
    assert "scene-healthcare" in discovered
    assert discovered == _BUNDLED_AVATAR_IDS
    # Empty / missing dir falls back without crashing.
    assert "scene-default" in discover_bundled_avatar_ids(avatars / "missing")


def test_skillhub_market_manifest_gets_scene_icon_url(tmp_path: Path) -> None:
    from octop.infra.agents.experts.catalog import ExpertCatalog

    market_root = tmp_path / "market"
    expert_dir = market_root / "skillhub-skillset-healthcare-nursing-plan"
    expert_dir.mkdir(parents=True)
    _write_manifest(
        expert_dir,
        extra={
            "id": "skillhub-skillset-healthcare-nursing-plan",
            "icon_name": "heart",
            "source": {"type": "skillhub", "scene": "healthcare"},
        },
    )

    catalog = ExpertCatalog(tmp_path / "bundled", extra_roots=[market_root])
    (tmp_path / "bundled").mkdir()
    catalog.refresh()

    expert = catalog.get("skillhub-skillset-healthcare-nursing-plan")
    assert expert is not None
    assert expert.summary.icon_url == "/experts/avatars/scene-healthcare.svg"


def test_expert_catalog_reads_extra_roots(tmp_path: Path) -> None:
    from octop.infra.agents.experts.catalog import ExpertCatalog

    bundled_root = tmp_path / "bundled"
    market_root = tmp_path / "market"
    bundled_dir = bundled_root / "bundled-expert"
    market_dir = market_root / "market-expert"
    bundled_dir.mkdir(parents=True)
    market_dir.mkdir(parents=True)
    _write_manifest(bundled_dir)
    _write_manifest(market_dir)
    (market_dir / "SOUL.md").write_text("# Market soul", encoding="utf-8")

    catalog = ExpertCatalog(bundled_root, extra_roots=[market_root])
    catalog.refresh()

    assert catalog.get("bundled-expert") is not None
    assert catalog.get("market-expert") is not None
    # Library UI lists only bundled templates; market cache stays resolvable via get().
    assert [s.id for s in catalog.list_summaries()] == ["bundled-expert"]
    assert [s.id for s in catalog.list_summaries(include_market_cache=True)] == [
        "bundled-expert",
        "market-expert",
    ]
    market = catalog.get("market-expert")
    assert market is not None
    assert catalog.expert_dir("market-expert") == market_dir
    assert "SOUL.md" in market.files


def test_expert_lazy_read_file_contents(tmp_path: Path) -> None:
    from octop.infra.agents.experts.catalog import ExpertCatalog

    expert_dir = tmp_path / "my-expert"
    expert_dir.mkdir()
    _write_manifest(expert_dir, extra={"prompt_files": ["SOUL.md"]})
    (expert_dir / "SOUL.md").write_text("# Soul\nhello", encoding="utf-8")
    (expert_dir / "extra.md").write_text("also copied", encoding="utf-8")

    catalog = ExpertCatalog(tmp_path)
    catalog.refresh()

    expert = catalog.get("my-expert")
    assert expert is not None
    assert expert.prompt_files == ["SOUL.md"]
    contents = {item["name"]: item["content"] for item in catalog.read_file_contents("my-expert")}
    assert contents["SOUL.md"] == "# Soul\nhello"
    assert contents["extra.md"] == "also copied"
    assert "manifest.json" not in expert.files


def test_preview_file_paths_limits_dashboard_preview(tmp_path: Path) -> None:
    from octop.infra.agents.experts.catalog import ExpertCatalog, preview_file_paths

    expert_dir = tmp_path / "my-expert"
    expert_dir.mkdir()
    _write_manifest(expert_dir, extra={"prompt_files": ["SOUL.md"]})
    (expert_dir / "SOUL.md").write_text("# Soul\nhello", encoding="utf-8")
    (expert_dir / "BOOTSTRAP.md").write_text("bootstrap", encoding="utf-8")
    (expert_dir / "references" / "cron-presets.json").parent.mkdir(parents=True)
    (expert_dir / "references" / "cron-presets.json").write_text("{}", encoding="utf-8")
    skill = expert_dir / "skills" / "my-skill" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("# Skill", encoding="utf-8")
    agents_dir = expert_dir / "agents"
    agents_dir.mkdir()
    (agents_dir / "reviewer.md").write_text(
        "---\nname: Reviewer\ndescription: Code review\n---\n\n# Reviewer\n",
        encoding="utf-8",
    )

    catalog = ExpertCatalog(tmp_path)
    catalog.refresh()

    expert = catalog.get("my-expert")
    assert expert is not None
    preview = preview_file_paths(expert)
    assert preview == [
        "SOUL.md",
        "skills/my-skill/SKILL.md",
        "agents/reviewer.md",
    ]
    names = {item["name"] for item in catalog.read_file_contents("my-expert", paths=preview)}
    assert names == {"SOUL.md", "skills/my-skill/SKILL.md", "agents/reviewer.md"}


def test_preview_paths_skip_manifest_json_in_prompt_files(tmp_path: Path) -> None:
    from octop.infra.agents.experts.catalog import preview_paths_from_inventory

    paths = preview_paths_from_inventory(
        ["SOUL.md", "manifest.json"],
        ["skills/demo/SKILL.md"],
    )
    assert paths == ["SOUL.md", "skills/demo/SKILL.md"]


def test_expert_prompt_files_metadata_only(tmp_path: Path) -> None:
    from octop.infra.agents.experts.catalog import ExpertCatalog

    expert_dir = tmp_path / "my-expert"
    expert_dir.mkdir()
    _write_manifest(expert_dir, extra={"prompt_files": ["SOUL.md"]})
    (expert_dir / "SOUL.md").write_text("# Soul\nhello", encoding="utf-8")
    skill = expert_dir / "skills" / "my-skill" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("# Skill\n" + ("x" * 5000), encoding="utf-8")

    catalog = ExpertCatalog(tmp_path)
    catalog.refresh()

    expert = catalog.get("my-expert")
    assert expert is not None
    assert expert.prompt_files == ["SOUL.md"]
    skill_body = next(
        item["content"]
        for item in catalog.read_file_contents("my-expert")
        if item["name"] == "skills/my-skill/SKILL.md"
    )
    assert skill_body.startswith("# Skill")


def test_bundled_default_expert_only_has_agents_md() -> None:
    from octop.infra.agents.experts.catalog import ExpertCatalog, default_library_root

    catalog = ExpertCatalog(default_library_root())
    catalog.refresh()
    expert = catalog.get("default")
    assert expert is not None
    assert expert.prompt_files == ["AGENTS.md"]
    assert expert.files == ["AGENTS.md"]
    names = {item["name"] for item in catalog.read_file_contents("default")}
    assert names == {"AGENTS.md"}


def test_bundled_office_automation_discovers_skills() -> None:
    from octop.infra.agents.experts.catalog import ExpertCatalog, default_library_root

    catalog = ExpertCatalog(default_library_root())
    catalog.refresh()
    expert = catalog.get("office-automation")
    assert expert is not None
    assert expert.prompt_files
    assert len(expert.files) > 50
    names = {item["name"] for item in catalog.read_file_contents("office-automation")}
    assert "skills/docx/SKILL.md" in names
    docx_skill = next(
        item["content"]
        for item in catalog.read_file_contents("office-automation")
        if item["name"] == "skills/docx/SKILL.md"
    )
    assert "DOCX" in docx_skill


def test_expert_quick_prompts_from_manifest(tmp_path: Path) -> None:
    from octop.infra.agents.experts.catalog import ExpertCatalog

    expert_dir = tmp_path / "my-expert"
    expert_dir.mkdir()
    _write_manifest(
        expert_dir,
        extra={
            "prompt_files": ["SOUL.md"],
            "quick_prompts": [
                {
                    "title": {"zh": "标题", "en": "Title"},
                    "description": {"zh": "说明", "en": "Desc"},
                    "prompt": {"zh": "你好", "en": "Hello"},
                    "color": "#abcdef",
                    "icon_name": "zap",
                }
            ],
        },
    )
    (expert_dir / "SOUL.md").write_text("soul", encoding="utf-8")

    catalog = ExpertCatalog(tmp_path)
    catalog.refresh()

    expert = catalog.get("my-expert")
    assert expert is not None
    assert len(expert.quick_prompts) == 1
    assert expert.quick_prompts[0].title_zh == "标题"
    assert expert.quick_prompts[0].prompt_en == "Hello"


def test_expert_task_examples_from_manifest(tmp_path: Path) -> None:
    from octop.infra.agents.experts.catalog import ExpertCatalog

    expert_dir = tmp_path / "my-expert"
    expert_dir.mkdir()
    _write_manifest(
        expert_dir,
        extra={
            "task_examples": {
                "zh": ["一", "二", "三", "四", "五"],
                "en": ["a", "b", "c", "d", "e"],
            }
        },
    )

    catalog = ExpertCatalog(tmp_path)
    catalog.refresh()
    expert = catalog.get("my-expert")
    assert expert is not None
    assert expert.summary.task_examples == {
        "zh": ["一", "二", "三"],
        "en": ["a", "b", "c"],
    }
