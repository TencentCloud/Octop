"""Unit tests for default-agent bootstrap helper."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from octop.infra.agents.experts.catalog import ExpertCatalog
from octop.infra.agents.experts.default_agent import (
    DEFAULT_EXPERT_ID,
    SETUP_DEFAULT_AGENT_ID,
    bootstrap_default_agent,
    default_home_local_backend,
    materialize_market_expert,
)
from octop.infra.errors import OctopError
from octop.infra.utils.host_dirs import host_fs_tree_root


def _write_expert(root: Path, expert_id: str) -> None:
    directory = root / expert_id
    directory.mkdir()
    (directory / "SOUL.md").write_text("# soul\n", encoding="utf-8")
    (directory / "manifest.json").write_text(
        json.dumps(
            {
                "id": expert_id,
                "label": {"zh": expert_id, "en": expert_id},
                "description": {"zh": "", "en": ""},
                "prompt_files": ["SOUL.md"],
            }
        ),
        encoding="utf-8",
    )


@pytest.fixture
def catalog(tmp_path: Path) -> ExpertCatalog:
    _write_expert(tmp_path, "general-assistant")
    _write_expert(tmp_path, "ops-engineer")
    cat = ExpertCatalog(tmp_path)
    cat.refresh()
    return cat


async def test_bootstrap_skips_when_user_has_agents(catalog: ExpertCatalog) -> None:
    registry = MagicMock()
    registry.list_agents.return_value = [object()]
    registry.get_row.return_value = None
    registry.create = AsyncMock()
    result = await bootstrap_default_agent(registry, catalog, user_id=2, locale="zh", agent_id=None)
    assert result is None
    registry.create.assert_not_called()


async def test_bootstrap_skips_when_main_exists(catalog: ExpertCatalog) -> None:
    registry = MagicMock()
    registry.get_row.return_value = object()
    registry.list_agents.return_value = []
    registry.create = AsyncMock()
    result = await bootstrap_default_agent(
        registry,
        catalog,
        user_id=1,
        locale="zh",
        agent_id=SETUP_DEFAULT_AGENT_ID,
    )
    assert result is None
    registry.create.assert_not_called()


async def test_bootstrap_creates_general_assistant(catalog: ExpertCatalog) -> None:
    registry = MagicMock()
    registry.get_row.return_value = None
    registry.list_agents.return_value = []
    created = object()
    registry.create = AsyncMock(return_value=created)
    result = await bootstrap_default_agent(registry, catalog, user_id=3, locale="en", agent_id=None)
    assert result is created
    registry.create.assert_awaited_once()
    spec = registry.create.await_args.args[0]
    assert spec.user_id == 3
    assert spec.agent_id is None
    assert spec.template_name == DEFAULT_EXPERT_ID
    assert spec.config["backend"] == default_home_local_backend()
    assert spec.config["backend"]["root_dir"] == host_fs_tree_root()
    assert registry.create.await_args.kwargs["defer_bootstrap"] is True


async def test_bootstrap_main_uses_fs_root_backend(catalog: ExpertCatalog) -> None:
    registry = MagicMock()
    registry.get_row.return_value = None
    registry.list_agents.return_value = []
    registry.create = AsyncMock(return_value=object())

    await bootstrap_default_agent(
        registry,
        catalog,
        user_id=1,
        agent_id=SETUP_DEFAULT_AGENT_ID,
    )

    spec = registry.create.await_args.args[0]
    assert spec.config["backend"] == default_home_local_backend()
    assert spec.config["backend"]["root_dir"] == host_fs_tree_root()


async def test_bootstrap_respects_policy_root_dir(catalog: ExpertCatalog, tmp_path: Path) -> None:
    registry = MagicMock()
    registry.get_row.return_value = None
    registry.list_agents.return_value = []
    registry.create = AsyncMock(return_value=object())
    jail = (tmp_path / "jail").resolve().as_posix()

    await bootstrap_default_agent(
        registry,
        catalog,
        user_id=1,
        agent_id=None,
        root_dir=jail,
    )

    spec = registry.create.await_args.args[0]
    assert spec.config["backend"] == default_home_local_backend(root_dir=jail)
    assert spec.config["backend"]["root_dir"] == jail


async def test_bootstrap_uses_selected_template(catalog: ExpertCatalog) -> None:
    other = next(item.id for item in catalog.list_summaries() if item.id != DEFAULT_EXPERT_ID)
    registry = MagicMock()
    registry.get_row.return_value = None
    registry.list_agents.return_value = []
    registry.create = AsyncMock(return_value=object())
    await bootstrap_default_agent(
        registry,
        catalog,
        user_id=4,
        locale="zh",
        expert_id=other,
    )
    spec = registry.create.await_args.args[0]
    assert spec.template_name == other


async def test_bootstrap_rejects_unknown_template(catalog: ExpertCatalog) -> None:
    registry = MagicMock()
    registry.get_row.return_value = None
    registry.list_agents.return_value = []
    with pytest.raises(OctopError) as exc:
        await bootstrap_default_agent(registry, catalog, user_id=4, expert_id="missing-template")
    assert exc.value.code.value == "EXPERT_TEMPLATE_NOT_FOUND"


async def test_materialize_returns_false_when_market_disabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OCTOP_PORTAL_ORIGIN", "")
    catalog = ExpertCatalog(tmp_path)
    catalog.refresh()
    server = MagicMock()
    server.expert_catalog = catalog
    server.paths.expert_market_dir = tmp_path / "cache"
    assert await materialize_market_expert(server, "missing-template") is False


async def test_materialize_uses_catalog_without_network(catalog: ExpertCatalog) -> None:
    server = MagicMock()
    server.expert_catalog = catalog
    assert await materialize_market_expert(server, DEFAULT_EXPERT_ID) is True


async def test_bootstrap_requires_catalog() -> None:
    registry = MagicMock()
    registry.get_row.return_value = None
    registry.list_agents.return_value = []
    with pytest.raises(OctopError):
        await bootstrap_default_agent(registry, None, user_id=1, locale="zh")
