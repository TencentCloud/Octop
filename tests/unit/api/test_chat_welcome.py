"""Unit tests for agent chat welcome (workspace / catalog / default)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from deepagents.backends.local_shell import LocalShellBackend
from harness_agent.backends.workspace import BackendWorkspace

from octop.infra.agents.experts.catalog import (
    ExpertCatalog,
    default_welcome_payload,
    read_workspace_manifest_welcome,
    seed_expert_directory,
    welcome_payload_has_content,
)


def _workspace(root: str) -> BackendWorkspace:
    backend = LocalShellBackend(root_dir=root, virtual_mode=False)
    return BackendWorkspace(backend, root)


@pytest.mark.asyncio
async def test_read_workspace_manifest_welcome() -> None:
    with tempfile.TemporaryDirectory() as ws_dir:
        workspace = _workspace(ws_dir)
        await workspace.awrite_text(
            ".octop/manifest.json",
            json.dumps(
                {
                    "id": "demo",
                    "welcome_message": {"zh": "你好", "en": "Hi"},
                    "quick_prompts": [
                        {
                            "title": {"zh": "标题", "en": "Title"},
                            "description": {"zh": "描述", "en": "Desc"},
                            "prompt": {"zh": "提示", "en": "Prompt"},
                            "color": "#eee",
                            "icon_name": "zap",
                        }
                    ],
                }
            ),
            force=True,
        )
        payload = await read_workspace_manifest_welcome(workspace)
        assert payload is not None
        assert payload["welcome_message"]["zh"] == "你好"
        assert len(payload["quick_prompts"]) == 1
        assert payload["quick_prompts"][0]["title"]["en"] == "Title"


@pytest.mark.asyncio
async def test_read_workspace_manifest_welcome_falls_back_to_root() -> None:
    with tempfile.TemporaryDirectory() as ws_dir:
        workspace = _workspace(ws_dir)
        await workspace.awrite_text(
            "manifest.json",
            json.dumps({"welcome_message": {"zh": "旧路径", "en": "Legacy"}}),
            force=True,
        )
        payload = await read_workspace_manifest_welcome(workspace)
        assert payload is not None
        assert payload["welcome_message"]["zh"] == "旧路径"


@pytest.mark.asyncio
async def test_seed_expert_directory_includes_manifest() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        expert_dir = Path(tmp) / "demo"
        expert_dir.mkdir()
        (expert_dir / "SOUL.md").write_text("# Soul", encoding="utf-8")
        (expert_dir / "manifest.json").write_text(
            json.dumps({"id": "demo", "welcome_message": {"zh": "x", "en": "y"}}),
            encoding="utf-8",
        )
        ws_dir = Path(tmp) / "ws"
        ws_dir.mkdir()
        workspace = _workspace(str(ws_dir))
        count = await seed_expert_directory(
            expert_dir=expert_dir,
            workspace=workspace,
            seed_paths=["SOUL.md"],
        )
        assert count == 2
        text = await workspace.aread_text(".octop/manifest.json")
        assert text is not None
        assert json.loads(text)["id"] == "demo"
        soul = await workspace.aread_text("SOUL.md")
        assert soul == "# Soul"


def test_welcome_payload_has_content() -> None:
    assert (
        welcome_payload_has_content({"welcome_message": {"zh": "", "en": ""}, "quick_prompts": []})
        is False
    )
    assert (
        welcome_payload_has_content(
            {"welcome_message": {"zh": "hi", "en": ""}, "quick_prompts": []}
        )
        is True
    )


def test_default_welcome_uses_general_assistant_when_catalog_present() -> None:
    catalog = ExpertCatalog.__new__(ExpertCatalog)
    # Use real library if available
    from octop.infra.agents.experts.catalog import default_library_root

    catalog = ExpertCatalog(default_library_root())
    catalog.refresh()
    payload = default_welcome_payload(catalog)
    assert welcome_payload_has_content(payload)
    assert len(payload["quick_prompts"]) > 0


def test_default_welcome_builtin_without_catalog() -> None:
    payload = default_welcome_payload(None)
    assert welcome_payload_has_content(payload)
    assert len(payload["quick_prompts"]) >= 1
