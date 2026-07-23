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


async def test_hub_search_returns_list(env: Any) -> None:
    """Authenticated GET → 200 and response body is a list.

    The skillhub CLI may not be installed in CI, in which case the server
    returns a 5xx.  Both outcomes are acceptable; what we must never see
    is a non-list 200 or an auth error.
    """
    c, _srv, auth, aid = env
    r = await c.get(f"/api/agents/{aid}/skills/hub/search", headers=auth)
    if r.status_code == 200:
        assert isinstance(r.json(), list), "200 response body must be a list"
    else:
        # 502/504 when skillhub CLI is absent — that is fine
        assert r.status_code in (502, 504), f"Unexpected status {r.status_code}: {r.text}"


async def test_hub_search_with_query(env: Any) -> None:
    """Authenticated GET with q=file-reader → 200 (list) or 5xx if CLI absent."""
    c, _srv, auth, aid = env
    r = await c.get(
        f"/api/agents/{aid}/skills/hub/search",
        headers=auth,
        params={"q": "file-reader"},
    )
    if r.status_code == 200:
        assert isinstance(r.json(), list), "200 response body must be a list"
    else:
        assert r.status_code in (502, 504), f"Unexpected status {r.status_code}: {r.text}"


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
    from tests.support.auth import create_agent, seed_openai_provider

    async def fake_ensure_cli(*, require_rankings: bool = False) -> str:
        assert not require_rankings
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
        install_dir = Path(args[1]) / args[-1]
        install_dir.mkdir(parents=True)
        (install_dir / "SKILL.md").write_text(
            "---\n"
            "name: english-package-name\n"
            "description: English description\n"
            "metadata:\n"
            "  openclaw:\n"
            "    emoji: '📦'\n"
            "---\n\n"
            "# Body\n",
            encoding="utf-8",
        )
        return 0, "", ""

    monkeypatch.setattr(skills_router, "_ensure_skillhub_cli", fake_ensure_cli)
    monkeypatch.setattr(skills_router, "_upgrade_skillhub_cli", fake_upgrade)
    monkeypatch.setattr(skills_router, "_run_skillhub_cmd", fake_run)

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
