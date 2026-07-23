"""tests/integration/test_skills_api.py — per-agent skill library.

Requires a running harness agent; skills are read/written via
``agent.workspace`` (``local_shell`` on the agent workspace dir).
"""

from __future__ import annotations

from typing import Any

import pytest

SAMPLE_SKILL = """---
name: file-reader
description: Read and summarize text files
metadata:
  octop:
    emoji: 📄
---
# File Reader

Use this skill when the user asks to read text files.
"""

BUILTIN_SKILL = """---
name: web-search
description: Search the web for information
metadata:
  octop:
    emoji: 🔍
---
# Web Search

Use this skill when the user needs up-to-date information from the web.
"""

WORKSPACE_OVERRIDE_SKILL = """---
name: web-search
description: Custom workspace override
---
# Custom Web Search
"""


async def _seed_builtin_skill(
    env: Any, name: str = "web-search", content: str = BUILTIN_SKILL
) -> None:
    _c, srv, _auth, aid = env
    agent = srv.app_runtime.agent_registry.get_agent(aid)
    await agent.workspace.aupload_many(
        [(f"_builtin_skills/{name}/SKILL.md", content.encode("utf-8"))]
    )


@pytest.fixture
async def env(env_with_agent):
    yield env_with_agent


# --- create + list ---------------------------------------------------------


async def test_create_then_list(env: Any) -> None:
    c, _srv, auth, aid = env

    r = await c.post(
        f"/api/agents/{aid}/skills",
        headers=auth,
        json={"name": "file-reader", "content": SAMPLE_SKILL},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "file-reader"
    assert body["enabled"] is True
    assert body["kind"] == "workspace"
    assert body["description"] == "Read and summarize text files"
    assert body["emoji"] == "📄"

    r = await c.get(f"/api/agents/{aid}/skills", headers=auth)
    assert r.status_code == 200
    rows = r.json()
    names = {row["name"] for row in rows}
    assert "file-reader" in names


async def test_list_empty_when_no_workspace_skills(env: Any) -> None:
    c, _srv, auth, aid = env
    r = await c.get(f"/api/agents/{aid}/skills", headers=auth)
    assert r.status_code == 200
    rows = r.json()
    workspace = [row for row in rows if row.get("kind") == "workspace"]
    assert workspace == []


async def test_list_includes_builtin_skills(env: Any) -> None:
    c, _srv, auth, aid = env
    await _seed_builtin_skill(env)

    r = await c.get(f"/api/agents/{aid}/skills", headers=auth)
    assert r.status_code == 200
    rows = r.json()
    builtin = [row for row in rows if row.get("kind") == "builtin"]
    assert len(builtin) >= 1
    ws = next(row for row in builtin if row["name"] == "web-search")
    assert ws["enabled"] is True
    assert ws["emoji"] == "🔍"


async def test_get_builtin_skill_detail(env: Any) -> None:
    c, _srv, auth, aid = env
    await _seed_builtin_skill(env)

    r = await c.get(f"/api/agents/{aid}/skills/web-search", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "builtin"
    assert "Web Search" in body["body"]


async def test_disable_builtin_skill(env: Any) -> None:
    c, _srv, auth, aid = env
    await _seed_builtin_skill(env)

    r = await c.post(f"/api/agents/{aid}/skills/web-search/disable", headers=auth)
    assert r.status_code == 204

    rows = (await c.get(f"/api/agents/{aid}/skills", headers=auth)).json()
    ws = next(row for row in rows if row["name"] == "web-search")
    assert ws["enabled"] is False


async def test_delete_builtin_skill_rejected(env: Any) -> None:
    c, _srv, auth, aid = env
    await _seed_builtin_skill(env)

    r = await c.delete(f"/api/agents/{aid}/skills/web-search", headers=auth)
    assert r.status_code == 404


async def test_workspace_skill_overrides_builtin_name(env: Any) -> None:
    c, _srv, auth, aid = env
    await _seed_builtin_skill(env)
    await c.post(
        f"/api/agents/{aid}/skills",
        headers=auth,
        json={"name": "web-search", "content": WORKSPACE_OVERRIDE_SKILL},
    )

    rows = (await c.get(f"/api/agents/{aid}/skills", headers=auth)).json()
    names = [row["name"] for row in rows]
    assert names.count("web-search") == 1
    ws = next(row for row in rows if row["name"] == "web-search")
    assert ws["kind"] == "workspace"


# --- detail ---------------------------------------------------------------


async def test_get_skill_detail(env: Any) -> None:
    c, _srv, auth, aid = env
    await c.post(
        f"/api/agents/{aid}/skills",
        headers=auth,
        json={"name": "file-reader", "content": SAMPLE_SKILL},
    )

    r = await c.get(f"/api/agents/{aid}/skills/file-reader", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["frontmatter"]["name"] == "file-reader"
    assert "Use this skill" in body["body"]
    assert body["raw"] == SAMPLE_SKILL


async def test_get_unknown_skill_404(env: Any) -> None:
    c, _srv, auth, aid = env
    r = await c.get(f"/api/agents/{aid}/skills/nope", headers=auth)
    assert r.status_code == 404


# --- create rejects ---------------------------------------------------------


async def test_create_rejects_duplicate(env: Any) -> None:
    c, _srv, auth, aid = env
    payload = {"name": "file-reader", "content": SAMPLE_SKILL}
    r1 = await c.post(f"/api/agents/{aid}/skills", headers=auth, json=payload)
    assert r1.status_code == 201
    r2 = await c.post(f"/api/agents/{aid}/skills", headers=auth, json=payload)
    assert r2.status_code == 409


async def test_create_rejects_invalid_name(env: Any) -> None:
    c, _srv, auth, aid = env
    for bad in ["", "  ", ".hidden", "with/slash"]:
        r = await c.post(
            f"/api/agents/{aid}/skills",
            headers=auth,
            json={"name": bad, "content": SAMPLE_SKILL},
        )
        assert r.status_code == 404, f"name={bad!r} should have been rejected"


# --- enable / disable ------------------------------------------------------


async def test_disable_then_enable_toggles_listing(env: Any) -> None:
    c, _srv, auth, aid = env
    await c.post(
        f"/api/agents/{aid}/skills",
        headers=auth,
        json={"name": "file-reader", "content": SAMPLE_SKILL},
    )

    r = await c.post(f"/api/agents/{aid}/skills/file-reader/disable", headers=auth)
    assert r.status_code == 204

    rows = (await c.get(f"/api/agents/{aid}/skills", headers=auth)).json()
    fr = next(row for row in rows if row["name"] == "file-reader")
    assert fr["enabled"] is False

    r = await c.post(f"/api/agents/{aid}/skills/file-reader/enable", headers=auth)
    assert r.status_code == 204
    rows = (await c.get(f"/api/agents/{aid}/skills", headers=auth)).json()
    fr = next(row for row in rows if row["name"] == "file-reader")
    assert fr["enabled"] is True


# --- soft delete -----------------------------------------------------------


async def test_delete_hides_skill_from_listing(env: Any) -> None:
    c, _srv, auth, aid = env
    await c.post(
        f"/api/agents/{aid}/skills",
        headers=auth,
        json={"name": "tmp-skill", "content": SAMPLE_SKILL},
    )

    r = await c.delete(f"/api/agents/{aid}/skills/tmp-skill", headers=auth)
    assert r.status_code == 204

    rows = (await c.get(f"/api/agents/{aid}/skills", headers=auth)).json()
    assert all(row["name"] != "tmp-skill" for row in rows)

    # detail also 404s
    r = await c.get(f"/api/agents/{aid}/skills/tmp-skill", headers=auth)
    assert r.status_code == 404


async def test_delete_unknown_skill_404(env: Any) -> None:
    c, _srv, auth, aid = env
    r = await c.delete(f"/api/agents/{aid}/skills/nope", headers=auth)
    assert r.status_code == 404


# --- URL import ------------------------------------------------------------


async def test_import_skill_from_url(env: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    c, srv, auth, aid = env
    from octop.infra.agents import skills_hub

    uploads = [
        (
            "skills/imported-skill/SKILL.md",
            SAMPLE_SKILL.encode("utf-8"),
        ),
        (
            "skills/imported-skill/references/doc.md",
            b"# doc",
        ),
    ]

    def _fake_resolve(**_kwargs: object) -> skills_hub.BundleResolveResult:
        return skills_hub.BundleResolveResult(
            name="imported-skill",
            uploads=uploads,
            source_url="https://github.com/example/repo",
        )

    monkeypatch.setattr(skills_hub, "resolve_bundle_from_url", _fake_resolve)

    srv.app_runtime.agent_registry.sync_skills_disabled = lambda *_a, **_k: None  # type: ignore[method-assign]

    r = await c.post(
        f"/api/agents/{aid}/skills/import",
        headers=auth,
        json={
            "bundle_url": "https://github.com/example/repo/tree/main/skills/imported-skill",
            "enable": True,
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["slug"] == "imported-skill"
    assert body["name"] == "file-reader"
    assert body["enabled"] is True
    assert body["kind"] == "workspace"

    agent = srv.app_runtime.agent_registry.get_agent(aid)
    raw = await agent.workspace.aread_text("skills/imported-skill/SKILL.md")
    assert raw is not None
    assert "file-reader" in raw
    ref = await agent.workspace.aread_text("skills/imported-skill/references/doc.md")
    assert ref == "# doc"

    cfg = srv.app_runtime.agent_registry.get_config(aid)
    assert "imported-skill" not in set(cfg.get("skills_disabled") or [])


async def test_import_rejects_unsupported_url(env: Any) -> None:
    c, _srv, auth, aid = env
    r = await c.post(
        f"/api/agents/{aid}/skills/import",
        headers=auth,
        json={"bundle_url": "https://example.com/skill"},
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "SKILL_IMPORT_UNSUPPORTED_URL"


async def test_import_rejects_adapter_upload_outside_skill_root(
    env: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c, _srv, auth, aid = env
    from octop.infra.agents import skills_hub

    def _fake_resolve(**_kwargs: object) -> skills_hub.BundleResolveResult:
        return skills_hub.BundleResolveResult(
            name="imported-skill",
            uploads=[
                ("skills/imported-skill/SKILL.md", SAMPLE_SKILL.encode()),
                ("skills/other/escape.md", b"unsafe"),
            ],
            source_url="https://github.com/example/repo",
        )

    monkeypatch.setattr(skills_hub, "resolve_bundle_from_url", _fake_resolve)

    r = await c.post(
        f"/api/agents/{aid}/skills/import",
        headers=auth,
        json={"bundle_url": "https://github.com/example/repo"},
    )

    assert r.status_code == 502
    assert r.json()["error"]["code"] == "SKILL_IMPORT_FAILED"
