"""Integration tests for GET /api/agents/{id}/subagents and the catalog."""

from __future__ import annotations

from typing import Any

import pytest

CUSTOM_SUBAGENT = """---
name: Code Reviewer
id: code-reviewer
description: Review code changes for bugs and style issues
---

# Code Reviewer

Review the assigned code and return actionable feedback.
"""


@pytest.fixture
async def env(env_with_agent):
    yield env_with_agent


async def test_list_seeded_subagent(env: Any) -> None:
    """Harness init_workspace seeds general-purpose subagent by default."""
    c, _srv, auth, aid = env

    r = await c.get(f"/api/agents/{aid}/subagents", headers=auth)
    assert r.status_code == 200, r.text
    rows = r.json()
    assert isinstance(rows, list)
    assert len(rows) >= 1
    slugs = {row["slug"] for row in rows}
    assert "general-purpose" in slugs
    gp = next(row for row in rows if row["slug"] == "general-purpose")
    assert gp["name"] == "General Purpose"
    assert "description" in gp
    assert gp["path"].endswith("general-purpose.md")


async def test_list_includes_workspace_subagent(env: Any) -> None:
    c, srv, auth, aid = env
    agent = srv.app_runtime.agent_registry.get_agent(aid)
    await agent.workspace.aupload_bytes(
        "agents/code-reviewer.md",
        CUSTOM_SUBAGENT.encode("utf-8"),
    )
    await srv.app_runtime.agent_registry.reload(aid)

    r = await c.get(f"/api/agents/{aid}/subagents", headers=auth)
    assert r.status_code == 200, r.text
    slugs = {row["slug"] for row in r.json()}
    assert "code-reviewer" in slugs


async def test_list_requires_auth(env: Any) -> None:
    _c, _srv, _auth, aid = env

    r = await _c.get(f"/api/agents/{aid}/subagents")
    assert r.status_code == 401


async def test_catalog_list_non_empty(env: Any) -> None:
    c, _srv, auth, _aid = env

    r = await c.get("/api/subagent-catalog", headers=auth)
    assert r.status_code == 200, r.text
    rows = r.json()
    assert isinstance(rows, list)
    assert len(rows) > 50
    assert rows[0]["slug"]
    assert rows[0]["division"]
    assert "available_locales" in rows[0]


async def test_catalog_list_localized(env: Any) -> None:
    c, _srv, auth, _aid = env

    r = await c.get(
        "/api/subagent-catalog",
        params={"locale": "en"},
        headers=auth,
    )
    assert r.status_code == 200, r.text
    rows = r.json()
    assert isinstance(rows, list)
    for row in rows:
        assert isinstance(row["name"], dict)
        assert isinstance(row["description"], dict)
        assert row["name"].get("en") or row["name"].get("zh")
        assert row["description"].get("en") or row["description"].get("zh")


async def test_catalog_divisions(env: Any) -> None:
    c, _srv, auth, _aid = env

    r = await c.get("/api/subagent-catalog/divisions", headers=auth)
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) == 16
    assert any(row["id"] == "engineering" and row["count"] > 0 for row in rows)


async def test_catalog_divisions_localized(env: Any) -> None:
    c, _srv, auth, _aid = env

    r = await c.get(
        "/api/subagent-catalog/divisions",
        params={"locale": "zh"},
        headers=auth,
    )
    assert r.status_code == 200, r.text
    rows = r.json()
    engineering = next(d for d in rows if d["id"] == "engineering")
    assert engineering["labels"]["zh"] == "工程"
    assert engineering["labels"]["en"] == "Engineering"
    r_default = await c.get("/api/subagent-catalog/divisions", headers=auth)
    rows_default = r_default.json()
    engineering_default = next(d for d in rows_default if d["id"] == "engineering")
    assert engineering_default["labels"]["zh"] == "工程"


async def test_catalog_divisions_accept_language_header(env: Any) -> None:
    c, _srv, auth, _aid = env

    headers = {**auth, "Accept-Language": "en"}
    r = await c.get("/api/subagent-catalog/divisions", headers=headers)
    assert r.status_code == 200, r.text
    engineering = next(d for d in r.json() if d["id"] == "engineering")
    assert engineering["labels"]["zh"] == "工程"
    assert engineering["labels"]["en"] == "Engineering"


async def test_catalog_detail(env: Any) -> None:
    c, _srv, auth, _aid = env

    r = await c.get("/api/subagent-catalog/engineering-software-architect", headers=auth)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["slug"] == "engineering-software-architect"
    assert isinstance(body["name"], dict)
    assert isinstance(body["content"], dict)
    zh_content = body["content"].get("zh") or ""
    en_content = body["content"].get("en") or ""
    assert zh_content.startswith("---") or en_content.startswith("---")


async def test_catalog_detail_accept_language(env: Any) -> None:
    c, _srv, auth, _aid = env

    headers = {**auth, "Accept-Language": "en"}
    r = await c.get("/api/subagent-catalog/engineering-software-architect", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body["content"], dict)
    assert body["content"].get("en") or body["content"].get("zh")


async def test_install_catalog_subagent(env: Any) -> None:
    c, srv, auth, aid = env

    r = await c.post(
        f"/api/agents/{aid}/subagents/install",
        headers=auth,
        json={"slug": "engineering-software-architect"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["installed"] is True
    assert body["slug"] == "engineering-software-architect"
    assert body["path"] == "agents/engineering-software-architect.md"
    assert body["locale"] in ("zh", "en")
    assert body["requested_locale"] in ("zh", "en")

    r_file = await c.get(
        f"/api/agents/{aid}/workspace/file",
        params={
            "path": "/agents/engineering-software-architect.md",
            "from_workspace": "true",
        },
        headers=auth,
    )
    assert r_file.status_code == 200, r_file.text
    # Content has frontmatter regardless of installed locale.
    assert r_file.json()["content"].startswith("---")

    r2 = await c.get(f"/api/agents/{aid}/subagents", headers=auth)
    assert r2.status_code == 200, r.text
    slugs = {row["slug"] for row in r2.json()}
    assert "engineering-software-architect" in slugs


async def test_install_catalog_subagent_locale_override(env: Any) -> None:
    c, srv, auth, aid = env

    r = await c.post(
        f"/api/agents/{aid}/subagents/install",
        headers=auth,
        json={"slug": "engineering-software-architect", "locale": "en"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["locale"] == "en"
    assert body["requested_locale"] == "en"

    r_file = await c.get(
        f"/api/agents/{aid}/workspace/file",
        params={
            "path": "/agents/engineering-software-architect.md",
            "from_workspace": "true",
        },
        headers=auth,
    )
    assert r_file.status_code == 200, r_file.text
    assert "Software Architect" in r_file.json()["content"]
