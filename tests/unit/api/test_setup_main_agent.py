"""Regression: bootstrap ``main`` agent must not use workspace-scoped virtual backend."""

from __future__ import annotations

import os
import tempfile

import pytest
from harness_agent.backends import resolve_backend
from harness_agent.backends.workspace import BackendWorkspace

from octop.infra.agents.experts.catalog import ExpertCatalog, default_library_root


def test_bootstrap_main_spec_has_no_custom_backend() -> None:
    """setup._bootstrap_default_agent must not pin virtual_mode without root_dir='/'."""
    from octop.infra.agents.experts.catalog import (
        build_create_spec_from_expert,
    )

    catalog = ExpertCatalog(default_library_root())
    catalog.refresh()
    expert = catalog.get("general-assistant")
    assert expert is not None
    spec = build_create_spec_from_expert(
        expert_id="general-assistant",
        expert=expert,
        user_id=1,
        agent_id="main",
        locale="zh",
    )
    assert "backend" not in spec.config
    assert spec.config.get("expert_id") == "general-assistant"


def test_bootstrap_main_spec_en_locale_uses_english_label() -> None:
    from octop.infra.agents.experts.catalog import (
        build_create_spec_from_expert,
    )

    catalog = ExpertCatalog(default_library_root())
    catalog.refresh()
    expert = catalog.get("general-assistant")
    assert expert is not None
    spec = build_create_spec_from_expert(
        expert_id="general-assistant",
        expert=expert,
        user_id=1,
        agent_id="main",
        locale="en",
    )
    expected_name = expert.summary.label_en or expert.summary.label_zh
    assert spec.name == expected_name
    if expert.summary.description_en:
        assert spec.description == expert.summary.description_en


@pytest.mark.asyncio
@pytest.mark.skipif(os.name != "posix", reason="POSIX virtual_mode without root_dir behavior")
async def test_workspace_scoped_virtual_backend_creates_nested_paths() -> None:
    """Broken layout when backend is {local_shell, virtual_mode} without root_dir='/'."""
    with tempfile.TemporaryDirectory() as ws_dir:
        backend = resolve_backend(
            {"type": "local_shell", "virtual_mode": True},
            workspace_dir=ws_dir,
        )
        ws = BackendWorkspace(backend, ws_dir)
        await ws.aupload_bytes("SOUL.md", b"# soul")
        assert not os.path.isfile(os.path.join(ws_dir, "SOUL.md"))
        # virtual_mode must not write to the workspace root; the file lands
        # nested under a child directory instead.
        nested = any(
            os.path.isfile(os.path.join(root, "SOUL.md")) for root, _dirs, _files in os.walk(ws_dir)
        )
        assert nested
