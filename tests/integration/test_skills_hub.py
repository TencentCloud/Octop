"""Integration tests for GET /api/agents/{id}/skills/hub/search
and POST /api/agents/{id}/skills/hub/install."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
async def env(env_with_main_agent):
    yield env_with_main_agent


# --- auth guard tests -------------------------------------------------------


async def test_hub_search_requires_auth(env: Any) -> None:
    c, _srv, _auth, aid = env
    r = await c.get(f"/api/agents/{aid}/skills/hub/search")
    assert r.status_code not in (200,), f"Expected auth failure, got {r.status_code}"


async def test_hub_install_requires_auth(env: Any) -> None:
    c, _srv, _auth, aid = env
    r = await c.post(
        f"/api/agents/{aid}/skills/hub/install",
        json={"skill_name": "file-reader", "enable": True},
    )
    assert r.status_code not in (200, 201), f"Expected auth failure, got {r.status_code}"


# --- authenticated search tests ---------------------------------------------


async def test_hub_search_returns_list(
    env: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Authenticated GET returns direct HTTP search results."""
    from octop.infra.agents import skillhub_market

    async def fake_search(
        query: str,
        *,
        limit: int = 50,
        host: str | None = None,
        timeout: float = 10.0,
    ) -> list[dict[str, Any]]:
        assert query == "a"
        assert limit == 50
        assert host is None
        assert timeout == 10.0
        return []

    monkeypatch.setattr(skillhub_market, "search_skillhub", fake_search)

    c, _srv, auth, aid = env
    r = await c.get(f"/api/agents/{aid}/skills/hub/search", headers=auth)
    assert r.status_code == 200
    assert r.json() == []


async def test_hub_search_with_query(
    env: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Authenticated GET passes its query to the HTTP client."""
    from octop.infra.agents import skillhub_market

    async def fake_search(
        query: str,
        *,
        limit: int = 50,
        host: str | None = None,
        timeout: float = 10.0,
    ) -> list[dict[str, Any]]:
        assert query == "file-reader"
        return [
            {
                "slug": "file-reader",
                "name": "文件读取",
                "description": "读取文件",
                "version": "1.0.0",
            }
        ]

    monkeypatch.setattr(skillhub_market, "search_skillhub", fake_search)

    c, _srv, auth, aid = env
    r = await c.get(
        f"/api/agents/{aid}/skills/hub/search",
        headers=auth,
        params={"q": "file-reader"},
    )
    assert r.status_code == 200
    assert r.json()[0]["name"] == "文件读取"


async def test_hub_rankings_returns_dict(
    env: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Authenticated GET rankings returns the direct HTTP client payload."""
    from octop.infra.agents import skillhub_market

    async def fake_fetch_rankings(
        ranking_type: str,
        *,
        host: str | None = None,
        timeout: float = 10.0,
    ) -> dict[str, Any]:
        assert ranking_type == "hot"
        assert host is None
        assert timeout == 10.0
        return {"section": "hot_downloads", "skills": [], "total": 0}

    monkeypatch.setattr(
        skillhub_market,
        "fetch_skillhub_rankings",
        fake_fetch_rankings,
    )

    c, _srv, auth, aid = env
    r = await c.get(
        f"/api/agents/{aid}/skills/hub/rankings",
        headers=auth,
        params={"type": "hot"},
    )
    assert r.status_code == 200
    assert r.json() == {"section": "hot_downloads", "skills": [], "total": 0}


# --- authenticated install tests --------------------------------------------


async def test_hub_install_unknown_skill(env: Any) -> None:
    """POST with a nonexistent skill → 4xx (400/404) or 5xx if CLI absent."""
    c, _srv, auth, aid = env
    r = await c.post(
        f"/api/agents/{aid}/skills/hub/install",
        headers=auth,
        json={"skill_name": "nonexistent-xyz-skill-abc123", "enable": True},
    )
    # 400 for bad name validation, 404 if skillhub says not found,
    # 502/504 if skillhub CLI is absent or network unavailable
    assert r.status_code != 200, f"Expected non-200, got {r.status_code}"
    assert r.status_code in (400, 404, 502, 504), f"Unexpected status {r.status_code}: {r.text}"


async def test_hub_install_persists_market_name_and_icon(
    env: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from octop.api.routers import skills as skills_router
    from octop.infra.agents import skillhub_market
    from tests.support.auth import create_agent, seed_openai_provider

    async def fake_download(
        slug: str,
        *,
        host: str | None = None,
        timeout: float = 30.0,
    ) -> list[tuple[str, bytes]]:
        assert slug == "stable-english-slug"
        return [
            (
                "SKILL.md",
                (
                    "---\n"
                    "name: english-package-name\n"
                    "description: English description\n"
                    "metadata:\n"
                    "  openclaw:\n"
                    "    emoji: '📦'\n"
                    "---\n\n"
                    "# Body\n"
                ).encode(),
            )
        ]

    async def unexpected_cli() -> str:
        raise AssertionError("HTTP success must not initialize the SkillHub CLI")

    monkeypatch.setattr(skillhub_market, "download_skillhub_package", fake_download)
    monkeypatch.setattr(skills_router, "_ensure_skillhub_cli", unexpected_cli)

    c, _srv, auth, _main_aid = env
    await seed_openai_provider(c, auth)
    aid = await create_agent(c, auth)
    icon_url = "https://cdn.example.com/skill.png"
    r = await c.post(
        f"/api/agents/{aid}/skills/hub/install",
        headers=auth,
        json={
            "skill_name": "stable-english-slug",
            "enable": True,
            "display_name": "中文展示名称",
            "icon_url": icon_url,
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["transport"] == "http"

    detail = await c.get(
        f"/api/agents/{aid}/skills/stable-english-slug",
        headers=auth,
    )
    assert detail.status_code == 200, detail.text
    payload = detail.json()
    assert payload["slug"] == "stable-english-slug"
    assert payload["name"] == "中文展示名称"
    assert payload["icon_url"] == icon_url
    assert payload["emoji"] == "📦"
    assert payload["frontmatter"]["name"] == "english-package-name"
    assert payload["frontmatter"]["metadata"]["octop"] == {
        "source": "skillhub",
        "display_name": "中文展示名称",
        "icon_url": icon_url,
    }


async def test_hub_install_falls_back_to_cli_on_http_failure(
    env: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from octop.api.routers import skills as skills_router
    from octop.infra.agents import skillhub_market
    from tests.support.auth import create_agent, seed_openai_provider

    async def failed_download(
        _slug: str,
        *,
        host: str | None = None,
        timeout: float = 30.0,
    ) -> list[tuple[str, bytes]]:
        raise skillhub_market.SkillHubMarketError("upstream unavailable")

    async def fake_ensure_cli() -> str:
        return "/fake/skillhub"

    async def fake_upgrade(_skillhub_bin: str) -> bool:
        return False

    async def fake_run(
        _skillhub_bin: str,
        args: list[str],
        *,
        timeout: float,
    ) -> tuple[int, str, str]:
        assert timeout == 120
        assert args[-1] == "fallback-skill"
        install_dir = Path(args[1]) / "cli-output"
        install_dir.mkdir(parents=True)
        (install_dir / "SKILL.md").write_text(
            "---\nname: fallback-skill\n---\n\n# Body\n",
            encoding="utf-8",
        )
        return 0, "", ""

    monkeypatch.setattr(skillhub_market, "download_skillhub_package", failed_download)
    monkeypatch.setattr(skills_router, "_ensure_skillhub_cli", fake_ensure_cli)
    monkeypatch.setattr(skills_router, "_upgrade_skillhub_cli", fake_upgrade)
    monkeypatch.setattr(skills_router, "_run_skillhub_cmd", fake_run)

    c, _srv, auth, _main_aid = env
    await seed_openai_provider(c, auth)
    aid = await create_agent(c, auth)
    r = await c.post(
        f"/api/agents/{aid}/skills/hub/install",
        headers=auth,
        json={"skill_name": "fallback-skill", "enable": True},
    )

    assert r.status_code == 201, r.text
    assert r.json()["transport"] == "cli"


async def test_hub_install_does_not_fallback_after_package_validation_failure(
    env: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from octop.api.routers import skills as skills_router
    from octop.infra.agents import skillhub_market
    from tests.support.auth import create_agent, seed_openai_provider

    async def invalid_download(
        _slug: str,
        *,
        host: str | None = None,
        timeout: float = 30.0,
    ) -> list[tuple[str, bytes]]:
        raise skillhub_market.SkillHubPackageError("unsafe zip path entry")

    async def unexpected_cli() -> str:
        raise AssertionError("Invalid packages must not bypass validation through the CLI")

    monkeypatch.setattr(skillhub_market, "download_skillhub_package", invalid_download)
    monkeypatch.setattr(skills_router, "_ensure_skillhub_cli", unexpected_cli)

    c, _srv, auth, _main_aid = env
    await seed_openai_provider(c, auth)
    aid = await create_agent(c, auth)
    r = await c.post(
        f"/api/agents/{aid}/skills/hub/install",
        headers=auth,
        json={"skill_name": "unsafe-package", "enable": True},
    )

    assert r.status_code == 502
    assert r.json()["detail"] == "unsafe zip path entry"
