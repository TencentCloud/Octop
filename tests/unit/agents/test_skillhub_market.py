"""Tests for SkillHub skillset normalization into expert templates."""

from __future__ import annotations

import io
import json
import re
import urllib.error
import zipfile
from typing import Any

import pytest

from octop.infra.agents import skillhub_market


def _zip_bytes(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def _has_cjk(text: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", text))


def test_skillhub_manifest_welcome_summarizes_capability() -> None:
    from octop.infra.agents.experts.skillhub_market import (
        SkillHubSkillset,
        _expert_manifest,
    )

    item = SkillHubSkillset(
        slug="media-longform-outline",
        display_name="长篇大纲设计",
        display_name_en="Long-form Outline Design",
        summary="把灵感扩展成可长期连载的长篇大纲。",
        summary_en="Expand ideas into serialization-ready outlines.",
        scene="media",
    )

    manifest = _expert_manifest(item, ["outline"])

    assert manifest["welcome_message"]["zh"] == "把灵感扩展成可长期连载的长篇大纲"
    assert "选下方卡片" not in manifest["welcome_message"]["zh"]
    assert "…" not in manifest["welcome_message"]["zh"]
    assert manifest["welcome_message"]["en"] == ("Expand ideas into serialization-ready outlines")
    assert "Pick a card" not in manifest["welcome_message"]["en"]


def test_skillhub_manifest_welcome_keeps_chinese_when_summary_is_english() -> None:
    from octop.infra.agents.experts.skillhub_market import (
        SkillHubSkillset,
        _expert_manifest,
    )

    item = SkillHubSkillset(
        slug="tarot-reading",
        display_name="塔罗占卜",
        display_name_en="Tarot Reading",
        summary=(
            "Cover tarot from crypto-random draw engines to Rider-Waite classics "
            "and rich 13-card spreads."
        ),
        summary_en="Practical tarot draws with classic spreads.",
        scene="mysticism",
    )

    manifest = _expert_manifest(item, ["tarot"])

    assert "Cover tarot" not in manifest["welcome_message"]["zh"]
    assert "…" not in manifest["welcome_message"]["zh"]
    assert manifest["welcome_message"]["zh"] == "提供专业、可落地的专家工作流支持"
    assert manifest["welcome_message"]["en"] == "Practical tarot draws with classic spreads"

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
    assert len(manifest["quick_prompts"]) == 6
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

    titles_zh = [p["title"]["zh"] for p in manifest["quick_prompts"]]
    assert len(titles_zh) == 6
    assert titles_zh[:2] == [
        "剧本到分镜表格转换",
        "电影感镜头运动设计",
    ]
    assert titles_zh[2:] == [
        "开始处理任务",
        "先制定计划",
        "分析现状",
        "产出结果",
    ]
    assert manifest["quick_prompts"][0]["description"]["zh"] == "生成标准分镜表格和拍摄计划"
    prompt = manifest["quick_prompts"][0]["prompt"]["zh"]
    assert prompt == (
        "请作为「分镜设计专家」，帮我完成「剧本到分镜表格转换」。\n我的情况/目标/材料是：\n"
    )
    assert "按以下方式引导我" not in prompt
    assert "将剧本文本解析为结构化分镜表格" not in prompt
    assert manifest["quick_prompts"][0]["icon_name"] == "video"
    first = manifest["quick_prompts"][0]
    assert first["title"]["en"] == "Workflow step 1"
    assert first["description"]["en"] == "Share context for a ready result"
    assert not _has_cjk(first["title"]["en"])
    assert not _has_cjk(first["description"]["en"])
    assert not _has_cjk(first["prompt"]["en"])
    assert first["prompt"]["en"] == (
        "As the Media Storyboard Design Expert, help me with: Workflow step 1.\n"
        "My context, goals, or materials are:\n"
    )


def test_skillhub_manifest_keeps_up_to_six_workflow_quick_prompts() -> None:
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

    assert len(manifest["quick_prompts"]) == 6
    assert manifest["quick_prompts"][0]["title"]["zh"] == "步骤标题 1"
    assert manifest["quick_prompts"][-1]["title"]["zh"] == "步骤标题 6"


def test_browse_skillsets_filters_by_scene(monkeypatch) -> None:
    from octop.infra.agents.experts import skillhub_market

    monkeypatch.setattr(
        skillhub_market,
        "_fetch_all_skillsets",
        lambda: [
            skillhub_market.SkillHubSkillset(
                slug="a",
                display_name="A",
                scene="tech",
            ),
            skillhub_market.SkillHubSkillset(
                slug="b",
                display_name="B",
                scene="finance",
            ),
            skillhub_market.SkillHubSkillset(
                slug="c",
                display_name="C",
                scene="tech",
            ),
        ],
    )

    items, scenes = skillhub_market.browse_skillsets(scene="tech")

    assert [item.slug for item in items] == ["a", "c"]
    assert scenes == ["finance", "tech"]


def test_fetch_skillset_uses_detail_endpoint(monkeypatch) -> None:
    from octop.infra.agents.experts import skillhub_market

    calls: list[str] = []

    def fake_json_get(url: str) -> dict[str, object]:
        calls.append(url)
        return {
            "slug": "tech-code-review",
            "displayName": "代码审查",
            "scene": "tech",
            "summary": "review PRs",
        }

    monkeypatch.setattr(skillhub_market, "_http_json_get", fake_json_get)

    item = skillhub_market.fetch_skillset("tech-code-review")

    assert item.slug == "tech-code-review"
    assert item.scene == "tech"
    assert "/api/v1/skillsets/tech-code-review" in calls[0]


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
    monkeypatch.setattr(skillhub_market, "_skillset_list_cache", None)
    monkeypatch.setattr(skillhub_market, "_skillset_list_cache_at", 0.0)
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


def test_skillset_from_raw_tolerates_bad_skill_count() -> None:
    from octop.infra.agents.experts.skillhub_market import _skillset_from_raw

    item = _skillset_from_raw(
        {
            "slug": "demo",
            "displayName": "Demo",
            "skillSlugs": ["a", "b"],
            "skillCount": "not-a-number",
        }
    )

    assert item.skill_count == 2


def test_validate_zip_rejects_path_traversal() -> None:
    import io
    import zipfile

    import pytest

    from octop.infra.agents.experts.skillhub_market import (
        SkillHubMarketError,
        SkillHubMarketErrorKind,
        _validate_zip,
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../evil.txt", "x")
    with (
        zipfile.ZipFile(io.BytesIO(buf.getvalue())) as zf,
        pytest.raises(SkillHubMarketError) as exc,
    ):
        _validate_zip(zf)
    assert exc.value.kind == SkillHubMarketErrorKind.PACKAGE_INVALID


def test_validate_zip_rejects_too_many_entries(monkeypatch) -> None:
    import io
    import zipfile

    import pytest

    from octop.infra.agents.experts import skillhub_market

    monkeypatch.setattr(skillhub_market, "_MAX_ZIP_ENTRIES", 2)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("a.txt", "a")
        zf.writestr("b.txt", "b")
        zf.writestr("c.txt", "c")
    with (
        zipfile.ZipFile(io.BytesIO(buf.getvalue())) as zf,
        pytest.raises(skillhub_market.SkillHubMarketError) as exc,
    ):
        skillhub_market._validate_zip(zf)
    assert exc.value.kind == skillhub_market.SkillHubMarketErrorKind.PACKAGE_TOO_LARGE


def test_fetch_all_skillsets_serves_stale_on_refresh_failure(monkeypatch) -> None:
    from octop.infra.agents.experts import skillhub_market

    cached = [
        skillhub_market.SkillHubSkillset(slug="cached", display_name="Cached"),
    ]
    monkeypatch.setattr(skillhub_market, "_skillset_list_cache", cached)
    monkeypatch.setattr(skillhub_market, "_skillset_list_cache_at", 0.0)
    monkeypatch.setattr(skillhub_market, "_skillset_list_loading", False)

    def boom() -> list[skillhub_market.SkillHubSkillset]:
        raise skillhub_market.SkillHubMarketError(
            "upstream down",
            kind=skillhub_market.SkillHubMarketErrorKind.UPSTREAM_FAILED,
        )

    monkeypatch.setattr(skillhub_market, "_load_all_skillsets_uncached", boom)

    items = skillhub_market._fetch_all_skillsets()
    assert [item.slug for item in items] == ["cached"]


def test_map_skillhub_error_hides_upstream_details() -> None:
    from octop.api.routers.experts import _map_skillhub_error
    from octop.infra.agents.experts.skillhub_market import (
        SkillHubMarketError,
        SkillHubMarketErrorKind,
    )
    from octop.infra.errors import ErrorCode

    err = SkillHubMarketError(
        "SkillHub request failed: https://secret.example/path",
        kind=SkillHubMarketErrorKind.UPSTREAM_FAILED,
    )
    mapped = _map_skillhub_error(err)
    assert mapped.code == ErrorCode.EXPERT_MARKET_FAILED
    assert "secret.example" not in mapped.message
    assert mapped.details["kind"] == "upstream_failed"
    assert "secret.example" not in str(mapped.details.get("reason", ""))


def test_http_get_ssl_urlerror_raises_ssl_kind(monkeypatch) -> None:
    from urllib.error import URLError

    from octop.infra.agents.experts import skillhub_market

    def boom(*_args: object, **_kwargs: object) -> object:
        raise URLError("[SSL: RECORD_LAYER_FAILURE] record layer failure")

    monkeypatch.setattr(skillhub_market, "urlopen", boom)

    with pytest.raises(skillhub_market.SkillHubMarketError) as exc:
        skillhub_market._http_get("https://example.test/x", accept="application/json")
    assert exc.value.kind == skillhub_market.SkillHubMarketErrorKind.SSL_ERROR


def test_map_skillhub_ssl_error() -> None:
    from octop.api.routers.experts import _map_skillhub_error
    from octop.infra.agents.experts.skillhub_market import (
        SkillHubMarketError,
        SkillHubMarketErrorKind,
    )
    from octop.infra.errors import ErrorCode

    mapped = _map_skillhub_error(
        SkillHubMarketError("ssl broken", kind=SkillHubMarketErrorKind.SSL_ERROR)
    )
    assert mapped.code == ErrorCode.SKILLHUB_SSL_FAILED
    assert mapped.details["kind"] == "ssl_error"


def test_map_skillhub_not_found() -> None:
    from octop.api.routers.experts import _map_skillhub_error
    from octop.infra.agents.experts.skillhub_market import (
        SkillHubMarketError,
        SkillHubMarketErrorKind,
    )
    from octop.infra.errors import ErrorCode

    mapped = _map_skillhub_error(
        SkillHubMarketError("missing", kind=SkillHubMarketErrorKind.NOT_FOUND)
    )
    assert mapped.code == ErrorCode.NOT_FOUND


class _Response:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self._payload).encode()


def test_fetch_ranking_json_uses_showcase_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake_urlopen(request: Any, timeout: float) -> _Response:
        seen["url"] = request.full_url
        seen["accept"] = request.headers["Accept"]
        seen["timeout"] = timeout
        return _Response({"section": "hot_downloads", "skills": [], "total": 0})

    monkeypatch.setattr(skillhub_market.urllib.request, "urlopen", fake_urlopen)

    result = skillhub_market._fetch_ranking_json(
        "https://api.example.com",
        "hot",
        timeout=7,
    )

    assert result["section"] == "hot_downloads"
    assert seen == {
        "url": "https://api.example.com/api/v1/showcase/hot",
        "accept": "application/json",
        "timeout": 7,
    }


@pytest.mark.asyncio
async def test_fetch_all_returns_partial_results(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_fetch(
        _host: str,
        ranking_type: str,
        *,
        timeout: float,
    ) -> dict[str, Any]:
        assert timeout == 10
        if ranking_type == "hot":
            raise skillhub_market.SkillHubMarketError("hot unavailable")
        return {"section": ranking_type, "skills": [], "total": 0}

    monkeypatch.setattr(skillhub_market, "_fetch_ranking_json", fake_fetch)

    result = await skillhub_market.fetch_skillhub_rankings("all")

    assert "hot" not in result["rankings"]
    assert result["rankings"]["recommended"]["section"] == "recommended"
    assert result["errors"] == {"hot": "hot unavailable"}


@pytest.mark.asyncio
async def test_fetch_all_raises_timeout_when_every_request_times_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_fetch(
        _host: str,
        ranking_type: str,
        *,
        timeout: float,
    ) -> dict[str, Any]:
        raise skillhub_market.SkillHubMarketTimeout(f"{ranking_type} timed out")

    monkeypatch.setattr(skillhub_market, "_fetch_ranking_json", fake_fetch)

    with pytest.raises(
        skillhub_market.SkillHubMarketTimeout,
        match="All SkillHub ranking requests timed out",
    ):
        await skillhub_market.fetch_skillhub_rankings("all")


def test_fetch_ranking_maps_url_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(_request: Any, timeout: float) -> _Response:
        raise urllib.error.URLError(TimeoutError())

    monkeypatch.setattr(skillhub_market.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(skillhub_market.SkillHubMarketTimeout):
        skillhub_market._fetch_ranking_json(
            "https://api.example.com",
            "recommended",
            timeout=7,
        )
