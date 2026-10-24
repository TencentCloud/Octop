"""Safe Octop extension draft, validation, and packaging tests."""

from __future__ import annotations

import io
import json
import zipfile

import pytest
from tests.support.fakes import FakeHarnessAgent

from octop.infra.agents.extensions.catalog import ExtensionCatalog
from octop.infra.agents.extensions.service import (
    ExtensionBuilderError,
    ExtensionBuilderService,
)
from octop.infra.agents.extensions.tools import build_extension_builder_tools


@pytest.fixture
def workspace(tmp_path):
    return FakeHarnessAgent(workspace_dir=tmp_path, virtual_mode=False).workspace


@pytest.mark.asyncio
async def test_skill_draft_must_be_finished_before_package(workspace) -> None:
    service = ExtensionBuilderService(workspace)
    created = await service.scaffold(
        artifact_type="skill",
        slug="release-helper",
        goal="Prepare a release checklist for an Octop repository.",
    )

    initial = await service.validate(created["project_id"])
    assert initial["valid"] is False
    assert initial["errors"][0]["code"] == "unfinished_placeholder"

    skill_path = f"{created['source_root']}/SKILL.md"
    await workspace.awrite_text(
        skill_path,
        """---
name: release-helper
description: Prepare and verify an Octop release checklist.
---

# Release Helper

Check the version, change log, tests, and release branch before publishing.
""",
    )
    report = await service.validate(created["project_id"])
    assert report["valid"] is True
    assert report["errors"] == []

    with pytest.raises(ExtensionBuilderError, match="source revision changed"):
        await service.package(created["project_id"], expected_revision="stale")

    packaged = await service.package(
        created["project_id"],
        expected_revision=report["revision"],
    )
    packaged_again = await service.package(
        created["project_id"],
        expected_revision=report["revision"],
    )
    assert packaged["installed"] is False
    assert packaged_again["sha256"] == packaged["sha256"]
    assert packaged_again["artifact_path"] == packaged["artifact_path"]
    payload = await workspace.adownload_bytes(packaged["artifact_path"])
    assert payload is not None
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        assert archive.namelist() == ["release-helper/SKILL.md"]


@pytest.mark.asyncio
async def test_package_publishes_skill_to_private_catalog(workspace, tmp_path) -> None:
    catalog = ExtensionCatalog(tmp_path / "catalog")
    service = ExtensionBuilderService(workspace, catalog=catalog, owner_user_id=7)
    created = await service.scaffold(
        artifact_type="skill",
        slug="visible-skill",
        goal="Show a generated skill in the private catalog.",
    )
    await workspace.awrite_text(
        f"{created['source_root']}/SKILL.md",
        """---
name: visible-skill
description: Show a generated skill in the private catalog.
---

# Visible Skill

Use this skill to verify catalog publication.
""",
    )
    report = await service.validate(created["project_id"])

    packaged = await service.package(
        created["project_id"],
        expected_revision=report["revision"],
    )

    assert packaged["catalog_entries"][0]["kind"] == "skill"
    assert [item["slug"] for item in catalog.list_skills(7)] == ["visible-skill"]
    assert catalog.list_skills(8) == []
    published = catalog.resolve_skill_dir(7, "visible-skill")
    assert published is not None
    assert (published / "SKILL.md").is_file()


@pytest.mark.asyncio
async def test_plugin_validation_parses_but_does_not_execute_source(workspace) -> None:
    service = ExtensionBuilderService(workspace)
    created = await service.scaffold(
        artifact_type="plugin",
        slug="safe-probe",
        goal="Expose a safe probe tool.",
    )
    entry_path = f"{created['source_root']}/main.py"
    await workspace.awrite_text(
        entry_path,
        """from octop_harness.plugins import PluginContext
import subprocess

raise RuntimeError("validation must not execute this module")

async def safe_probe(value: str) -> str:
    return value

def setup(ctx: PluginContext) -> None:
    ctx.tool("safe_probe", safe_probe, description="Return the supplied value.")
""",
    )

    report = await service.validate(created["project_id"])

    assert report["valid"] is True
    assert [warning["code"] for warning in report["warnings"]] == ["sensitive_plugin_code"]
    assert "subprocess" in report["warnings"][0]["message"]


@pytest.mark.asyncio
async def test_skill_validation_requires_frontmatter_description(workspace) -> None:
    service = ExtensionBuilderService(workspace)
    created = await service.scaffold(
        artifact_type="skill",
        slug="brief-skill",
        goal="Create concise briefs.",
    )
    await workspace.awrite_text(
        f"{created['source_root']}/SKILL.md",
        "---\nname: brief-skill\n---\n\n# Brief Skill\n",
    )

    report = await service.validate(created["project_id"])

    assert report["valid"] is False
    assert any(error["code"] == "invalid_skill_manifest" for error in report["errors"])


@pytest.mark.asyncio
async def test_plugin_validation_rejects_invalid_tool_name(workspace) -> None:
    service = ExtensionBuilderService(workspace)
    created = await service.scaffold(
        artifact_type="plugin",
        slug="name-check",
        goal="Check generated tool names.",
    )
    await workspace.awrite_text(
        f"{created['source_root']}/main.py",
        """from octop_harness.plugins import PluginContext

async def run(value: str) -> str:
    return value

def setup(ctx: PluginContext) -> None:
    ctx.tool("无效工具名", run, description="Return the value.")
""",
    )

    report = await service.validate(created["project_id"])

    assert report["valid"] is False
    assert any(error["code"] == "invalid_plugin_tool_name" for error in report["errors"])


@pytest.mark.asyncio
async def test_plugin_validation_checks_python_helper_files(workspace) -> None:
    service = ExtensionBuilderService(workspace)
    created = await service.scaffold(
        artifact_type="plugin",
        slug="helper-check",
        goal="Check every Python source file.",
    )
    await workspace.awrite_text(
        f"{created['source_root']}/main.py",
        """from octop_harness.plugins import PluginContext

async def run(value: str) -> str:
    return value

def setup(ctx: PluginContext) -> None:
    ctx.tool("helper_check", run, description="Return the value.")
""",
    )
    await workspace.awrite_text(
        f"{created['source_root']}/helper.py",
        "def broken(:\n",
    )

    report = await service.validate(created["project_id"])

    assert report["valid"] is False
    assert any(
        error["code"] == "invalid_plugin_python" and error["path"] == "helper.py"
        for error in report["errors"]
    )


@pytest.mark.asyncio
async def test_hybrid_requires_valid_bundled_skill(workspace) -> None:
    service = ExtensionBuilderService(workspace)
    created = await service.scaffold(
        artifact_type="hybrid",
        slug="calendar-helper",
        goal="Create calendar events with clear confirmation rules.",
    )
    await workspace.awrite_text(
        f"{created['source_root']}/main.py",
        """from octop_harness.plugins import PluginContext

async def create_event(title: str) -> str:
    return title

def setup(ctx: PluginContext) -> None:
    ctx.tool("create_event", create_event, description="Create one calendar event.")
""",
    )
    await workspace.awrite_text(
        f"{created['source_root']}/skills/calendar-helper/SKILL.md",
        """---
name: calendar-helper
description: Create calendar events after confirming time and attendees.
---

# Calendar Helper

Confirm the time zone before calling the event tool.
""",
    )

    report = await service.validate(created["project_id"])
    manifest = await workspace.aread_text(f"{created['source_root']}/plugin.yaml")

    assert report["valid"] is True
    assert report["file_count"] == 3
    assert manifest is not None and "skills: skills" in manifest


@pytest.mark.asyncio
async def test_validation_requires_final_newline_in_text_files(workspace) -> None:
    service = ExtensionBuilderService(workspace)
    created = await service.scaffold(
        artifact_type="skill",
        slug="format-check",
        goal="Check generated text file formatting.",
    )
    await workspace.awrite_text(
        f"{created['source_root']}/SKILL.md",
        "---\nname: format-check\ndescription: Check generated text files.\n---\n\n# Format Check",
    )

    report = await service.validate(created["project_id"])

    assert report["valid"] is False
    assert any(error["code"] == "missing_final_newline" for error in report["errors"])


@pytest.mark.asyncio
async def test_hybrid_requires_plugin_skills_declaration(workspace) -> None:
    service = ExtensionBuilderService(workspace)
    created = await service.scaffold(
        artifact_type="hybrid",
        slug="hybrid-check",
        goal="Check the hybrid plugin manifest.",
    )
    manifest_path = f"{created['source_root']}/plugin.yaml"
    manifest = await workspace.aread_text(manifest_path)
    assert manifest is not None
    await workspace.awrite_text(manifest_path, manifest.replace("skills: skills\n", ""))

    report = await service.validate(created["project_id"])

    assert any(error["code"] == "missing_plugin_skills_declaration" for error in report["errors"])


@pytest.mark.asyncio
async def test_project_id_cannot_escape_workspace(workspace) -> None:
    service = ExtensionBuilderService(workspace)

    with pytest.raises(ExtensionBuilderError, match="invalid project_id"):
        await service.validate("../../other-agent")


@pytest.mark.asyncio
async def test_extension_tools_reject_non_owner(workspace) -> None:
    tools = build_extension_builder_tools(
        workspace,
        agent_id="builder-1",
        owner_user_id=7,
    )
    scaffold = next(tool for tool in tools if tool.name == "octop_extension_scaffold")

    result = await scaffold.ainvoke(
        {
            "artifact_type": "skill",
            "slug": "private-skill",
            "goal": "Keep this draft private.",
        },
        config={"configurable": {"agent_id": "builder-1", "user": 9}},
    )

    assert json.loads(result) == {"error": "only the extension builder owner can create artifacts"}


def test_extension_tool_names_are_stable(workspace) -> None:
    tools = build_extension_builder_tools(
        workspace,
        agent_id="builder-1",
        owner_user_id=7,
    )

    assert [tool.name for tool in tools] == [
        "octop_extension_scaffold",
        "octop_extension_validate",
        "octop_extension_package",
    ]
