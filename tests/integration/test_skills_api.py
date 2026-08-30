"""tests/integration/test_skills_api.py — per-agent skill library.

Requires a running harness agent; skills are read/written via
``agent.workspace`` (``local_shell`` on the agent workspace dir).
"""

from __future__ import annotations

import base64
from typing import Any

import pytest


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


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


async def test_list_localizes_octop_presentation_metadata(env: Any) -> None:
    c, _srv, auth, aid = env
    content = """---
name: pdf-reader
description: Agent trigger description
metadata:
  octop:
    label:
      zh: PDF 阅读
      en: PDF Reader
    summary:
      zh: 阅读和处理 PDF
      en: Read and process PDFs
    emoji: 📄
---
"""
    created = await c.post(
        f"/api/agents/{aid}/skills",
        headers=auth,
        json={"name": "pdf-reader", "content": content},
    )
    assert created.status_code == 201, created.text

    zh_rows = (
        await c.get(
            f"/api/agents/{aid}/skills",
            headers={**auth, "Accept-Language": "zh-CN"},
        )
    ).json()
    en_rows = (
        await c.get(
            f"/api/agents/{aid}/skills",
            headers={**auth, "Accept-Language": "en-US"},
        )
    ).json()

    zh = next(row for row in zh_rows if row["slug"] == "pdf-reader")
    en = next(row for row in en_rows if row["slug"] == "pdf-reader")
    assert (zh["name"], zh["description"]) == ("PDF 阅读", "阅读和处理 PDF")
    assert (en["name"], en["description"]) == ("PDF Reader", "Read and process PDFs")


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

    manager = next(row for row in builtin if row["slug"] == "skill-manager")
    assert manager["enabled"] is True
    assert manager["name"] in {"技能管理", "Skill Manager"}
    assert manager["description"]


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


async def test_octop_skill_manager_detail_and_delete_protection(env: Any) -> None:
    c, _srv, auth, aid = env

    r = await c.get(f"/api/agents/{aid}/skills/skill-manager", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "builtin"
    assert body["frontmatter"]["name"] == "skill-manager"
    assert "manage_skills.py" in body["body"]

    r = await c.delete(f"/api/agents/{aid}/skills/skill-manager", headers=auth)
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


# --- update (PUT) ----------------------------------------------------------


UPDATED_SKILL = """---
name: file-reader
description: Updated description
metadata:
  octop:
    emoji: 📘
---
# File Reader Updated

Edited body content.
"""


async def test_put_updates_workspace_skill(env: Any) -> None:
    c, srv, auth, aid = env
    await c.post(
        f"/api/agents/{aid}/skills",
        headers=auth,
        json={"name": "file-reader", "content": SAMPLE_SKILL},
    )

    r = await c.put(
        f"/api/agents/{aid}/skills/file-reader",
        headers=auth,
        json={"content": UPDATED_SKILL},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "file-reader"
    assert body["kind"] == "workspace"
    assert body["description"] == "Updated description"
    assert body["emoji"] == "📘"

    detail = (await c.get(f"/api/agents/{aid}/skills/file-reader", headers=auth)).json()
    assert detail["raw"] == UPDATED_SKILL
    assert "Edited body content" in detail["body"]

    agent = srv.app_runtime.agent_registry.get_agent(aid)
    raw = await agent.workspace.aread_text("skills/file-reader/SKILL.md")
    assert raw == UPDATED_SKILL


async def test_put_content_only_keeps_sibling_files_and_dirs(env: Any) -> None:
    """Editing SKILL.md via the dashboard must not wipe the skill's other files."""
    c, srv, auth, aid = env
    skill_md = "---\nname: zip-demo\ndescription: from zip\n---\n\n# Zip Demo\n"
    r = await c.post(
        f"/api/agents/{aid}/skills",
        headers=auth,
        json={
            "name": "zip-demo",
            "files": [
                {"path": "SKILL.md", "content_base64": _b64(skill_md)},
                {"path": "README.md", "content_base64": _b64("# readme")},
                {"path": "references/", "content_base64": ""},
                {"path": "references/doc.md", "content_base64": _b64("# doc")},
            ],
        },
    )
    assert r.status_code == 201, r.text

    updated_md = "---\nname: zip-demo\ndescription: edited\n---\n\n# Edited\n"
    r = await c.put(
        f"/api/agents/{aid}/skills/zip-demo",
        headers=auth,
        json={"content": updated_md},
    )
    assert r.status_code == 200, r.text

    agent = srv.app_runtime.agent_registry.get_agent(aid)
    assert await agent.workspace.aread_text("skills/zip-demo/SKILL.md") == updated_md
    assert await agent.workspace.aread_text("skills/zip-demo/README.md") == "# readme"
    assert await agent.workspace.aread_text("skills/zip-demo/references/doc.md") == "# doc"


async def test_put_files_payload_replaces_directory(env: Any) -> None:
    """A full ``files`` payload on PUT replaces the skill directory wholesale."""
    c, srv, auth, aid = env
    skill_md = "---\nname: zip-demo\ndescription: from zip\n---\n\n# Zip Demo\n"
    r = await c.post(
        f"/api/agents/{aid}/skills",
        headers=auth,
        json={
            "name": "zip-demo",
            "files": [
                {"path": "SKILL.md", "content_base64": _b64(skill_md)},
                {"path": "stale.txt", "content_base64": _b64("old")},
            ],
        },
    )
    assert r.status_code == 201, r.text

    updated_md = "---\nname: zip-demo\ndescription: replaced\n---\n\n# New\n"
    r = await c.put(
        f"/api/agents/{aid}/skills/zip-demo",
        headers=auth,
        json={
            "files": [
                {"path": "SKILL.md", "content_base64": _b64(updated_md)},
                {"path": "fresh.txt", "content_base64": _b64("new")},
            ],
        },
    )
    assert r.status_code == 200, r.text

    agent = srv.app_runtime.agent_registry.get_agent(aid)
    assert await agent.workspace.aread_text("skills/zip-demo/SKILL.md") == updated_md
    assert await agent.workspace.aread_text("skills/zip-demo/fresh.txt") == "new"
    assert await agent.workspace.aread_text("skills/zip-demo/stale.txt") is None


async def test_put_empty_files_list_falls_back_to_content_only(env: Any) -> None:
    """``files: []`` + ``content`` must not wipe the directory (empty list = content path)."""
    c, srv, auth, aid = env
    skill_md = "---\nname: zip-demo\ndescription: from zip\n---\n\n# Zip Demo\n"
    r = await c.post(
        f"/api/agents/{aid}/skills",
        headers=auth,
        json={
            "name": "zip-demo",
            "files": [
                {"path": "SKILL.md", "content_base64": _b64(skill_md)},
                {"path": "notes.txt", "content_base64": _b64("keep me")},
            ],
        },
    )
    assert r.status_code == 201, r.text

    updated_md = "---\nname: zip-demo\ndescription: edited\n---\n\n# Edited\n"
    r = await c.put(
        f"/api/agents/{aid}/skills/zip-demo",
        headers=auth,
        json={"content": updated_md, "files": []},
    )
    assert r.status_code == 200, r.text

    agent = srv.app_runtime.agent_registry.get_agent(aid)
    assert await agent.workspace.aread_text("skills/zip-demo/SKILL.md") == updated_md
    assert await agent.workspace.aread_text("skills/zip-demo/notes.txt") == "keep me"


async def test_put_rejects_missing_skill(env: Any) -> None:
    c, _srv, auth, aid = env
    r = await c.put(
        f"/api/agents/{aid}/skills/nope",
        headers=auth,
        json={"content": UPDATED_SKILL},
    )
    assert r.status_code == 404


async def test_put_rejects_builtin_only_skill(env: Any) -> None:
    c, _srv, auth, aid = env
    await _seed_builtin_skill(env)
    r = await c.put(
        f"/api/agents/{aid}/skills/web-search",
        headers=auth,
        json={"content": WORKSPACE_OVERRIDE_SKILL},
    )
    assert r.status_code == 404


async def test_put_rejects_removed_skill(env: Any) -> None:
    c, _srv, auth, aid = env
    await c.post(
        f"/api/agents/{aid}/skills",
        headers=auth,
        json={"name": "tmp-skill", "content": SAMPLE_SKILL},
    )
    await c.delete(f"/api/agents/{aid}/skills/tmp-skill", headers=auth)
    r = await c.put(
        f"/api/agents/{aid}/skills/tmp-skill",
        headers=auth,
        json={"content": UPDATED_SKILL},
    )
    assert r.status_code == 404


# --- URL import ------------------------------------------------------------


async def test_import_skill_from_url(env: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    c, srv, auth, aid = env
    from octop.infra.skills import skills_hub

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
    from octop.infra.skills import skills_hub

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


# --- local zip-style files create / overwrite -----------------------------


async def test_create_skill_from_files_payload(env: Any) -> None:
    """Local ZIP import posts ``files`` + base64 content (not just ``content``)."""
    c, srv, auth, aid = env
    skill_md = "---\nname: zip-demo\ndescription: from zip\n---\n\n# Zip Demo\n"
    r = await c.post(
        f"/api/agents/{aid}/skills",
        headers=auth,
        json={
            "name": "zip-demo",
            "files": [
                {"path": "SKILL.md", "content_base64": _b64(skill_md)},
                {"path": "notes.txt", "content_base64": _b64("hello")},
                {"path": "scripts/run.py", "content_base64": _b64("print(1)\n")},
            ],
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["name"] == "zip-demo"
    assert r.json()["description"] == "from zip"

    agent = srv.app_runtime.agent_registry.get_agent(aid)
    notes = await agent.workspace.aread_text("skills/zip-demo/notes.txt")
    script = await agent.workspace.aread_text("skills/zip-demo/scripts/run.py")
    assert notes == "hello"
    assert script == "print(1)\n"


async def test_create_skill_preserves_empty_directories(env: Any) -> None:
    """Empty folders from a local ZIP import are recreated in the workspace."""
    c, srv, auth, aid = env
    skill_md = "---\nname: word-docx\ndescription: from zip\n---\n\n# Word Docx\n"
    r = await c.post(
        f"/api/agents/{aid}/skills",
        headers=auth,
        json={
            "name": "word-docx",
            "files": [
                {"path": "SKILL.md", "content_base64": _b64(skill_md)},
                {"path": "index.html", "content_base64": _b64("<html></html>")},
                {"path": "ai/", "content_base64": ""},
                {"path": "data/", "content_base64": ""},
                {"path": "scripts/", "content_base64": ""},
            ],
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["name"] == "word-docx"

    agent = srv.app_runtime.agent_registry.get_agent(aid)
    index = await agent.workspace.aread_text("skills/word-docx/index.html")
    assert index == "<html></html>"
    for path in (
        "skills/word-docx/ai",
        "skills/word-docx/data",
        "skills/word-docx/scripts",
    ):
        assert await agent.workspace.aexists(path), path


async def test_create_skill_files_conflict_without_overwrite(env: Any) -> None:
    c, _srv, auth, aid = env
    await c.post(
        f"/api/agents/{aid}/skills",
        headers=auth,
        json={"name": "zip-demo", "content": SAMPLE_SKILL},
    )
    r = await c.post(
        f"/api/agents/{aid}/skills",
        headers=auth,
        json={
            "name": "zip-demo",
            "files": [{"path": "SKILL.md", "content_base64": _b64(SAMPLE_SKILL)}],
            "overwrite": False,
        },
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "SKILL_ALREADY_EXISTS"


async def test_create_skill_files_overwrite_replaces_stale_siblings(env: Any) -> None:
    c, srv, auth, aid = env
    first = await c.post(
        f"/api/agents/{aid}/skills",
        headers=auth,
        json={
            "name": "zip-demo",
            "files": [
                {"path": "SKILL.md", "content_base64": _b64(SAMPLE_SKILL)},
                {"path": "stale.txt", "content_base64": _b64("old")},
            ],
        },
    )
    assert first.status_code == 201, first.text

    updated_md = "---\nname: zip-demo\ndescription: replaced\n---\n\n# New\n"
    second = await c.post(
        f"/api/agents/{aid}/skills",
        headers=auth,
        json={
            "name": "zip-demo",
            "files": [
                {"path": "SKILL.md", "content_base64": _b64(updated_md)},
                {"path": "fresh.txt", "content_base64": _b64("new")},
            ],
            "overwrite": True,
        },
    )
    assert second.status_code == 201, second.text
    assert second.json()["description"] == "replaced"

    agent = srv.app_runtime.agent_registry.get_agent(aid)
    assert await agent.workspace.aread_text("skills/zip-demo/fresh.txt") == "new"
    assert await agent.workspace.aread_text("skills/zip-demo/stale.txt") is None


async def test_create_skill_rejects_invalid_base64_files(env: Any) -> None:
    c, _srv, auth, aid = env
    r = await c.post(
        f"/api/agents/{aid}/skills",
        headers=auth,
        json={
            "name": "bad-b64",
            "files": [{"path": "SKILL.md", "content_base64": "%%%not-base64%%%"}],
        },
    )
    assert r.status_code == 400, r.text


async def test_reinstall_after_soft_delete_without_overwrite(env: Any) -> None:
    """Soft-deleted multi-file skills must reinstall even when a sibling is listed first."""
    c, srv, auth, aid = env
    skill_md = "---\nname: zip-demo\ndescription: from zip\n---\n\n# Zip Demo\n"
    first = await c.post(
        f"/api/agents/{aid}/skills",
        headers=auth,
        json={
            "name": "zip-demo",
            "files": [
                {"path": "notes.txt", "content_base64": _b64("hello")},
                {"path": "SKILL.md", "content_base64": _b64(skill_md)},
            ],
        },
    )
    assert first.status_code == 201, first.text

    assert (
        await c.post(f"/api/agents/{aid}/skills/zip-demo/disable", headers=auth)
    ).status_code == 204
    assert (await c.delete(f"/api/agents/{aid}/skills/zip-demo", headers=auth)).status_code == 204

    reinstall = await c.post(
        f"/api/agents/{aid}/skills",
        headers=auth,
        json={
            "name": "zip-demo",
            "files": [
                {"path": "notes.txt", "content_base64": _b64("hello2")},
                {"path": "SKILL.md", "content_base64": _b64(skill_md)},
            ],
            "overwrite": False,
        },
    )
    assert reinstall.status_code == 201, reinstall.text
    assert reinstall.json()["enabled"] is True

    agent = srv.app_runtime.agent_registry.get_agent(aid)
    raw = await agent.workspace.aread_text("skills/zip-demo/SKILL.md")
    assert raw is not None
    assert "removed" not in raw
    assert await agent.workspace.aread_text("skills/zip-demo/notes.txt") == "hello2"

    cfg = srv.app_runtime.agent_registry.get_config(aid)
    assert "zip-demo" not in set(cfg.get("skills_disabled") or [])
    rows = (await c.get(f"/api/agents/{aid}/skills", headers=auth)).json()
    row = next(item for item in rows if item["slug"] == "zip-demo")
    assert row["enabled"] is True


async def test_reinstall_overwrite_clears_skills_disabled(env: Any) -> None:
    """Disable → delete → overwrite reinstall must leave the skill enabled."""
    c, srv, auth, aid = env
    skill_md = "---\nname: zip-demo\ndescription: from zip\n---\n\n# Zip Demo\n"
    first = await c.post(
        f"/api/agents/{aid}/skills",
        headers=auth,
        json={
            "name": "zip-demo",
            "files": [
                {"path": "notes.txt", "content_base64": _b64("hello")},
                {"path": "SKILL.md", "content_base64": _b64(skill_md)},
            ],
        },
    )
    assert first.status_code == 201, first.text

    assert (
        await c.post(f"/api/agents/{aid}/skills/zip-demo/disable", headers=auth)
    ).status_code == 204
    assert (await c.delete(f"/api/agents/{aid}/skills/zip-demo", headers=auth)).status_code == 204

    reinstall = await c.post(
        f"/api/agents/{aid}/skills",
        headers=auth,
        json={
            "name": "zip-demo",
            "files": [
                {"path": "notes.txt", "content_base64": _b64("hello2")},
                {"path": "SKILL.md", "content_base64": _b64(skill_md)},
            ],
            "overwrite": True,
        },
    )
    assert reinstall.status_code == 201, reinstall.text
    assert reinstall.json()["enabled"] is True

    agent = srv.app_runtime.agent_registry.get_agent(aid)
    raw = await agent.workspace.aread_text("skills/zip-demo/SKILL.md")
    assert raw is not None
    assert "removed: true" not in raw

    cfg = srv.app_runtime.agent_registry.get_config(aid)
    assert "zip-demo" not in set(cfg.get("skills_disabled") or [])
    rows = (await c.get(f"/api/agents/{aid}/skills", headers=auth)).json()
    row = next(item for item in rows if item["slug"] == "zip-demo")
    assert row["enabled"] is True
