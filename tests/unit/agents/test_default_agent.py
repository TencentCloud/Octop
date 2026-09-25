"""Unit tests for default-agent bootstrap helper."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from octop.infra.agents.experts.catalog import ExpertCatalog, default_library_root
from octop.infra.agents.experts.default_agent import (
    DEFAULT_EXPERT_ID,
    SETUP_DEFAULT_AGENT_ID,
    bootstrap_default_agent,
    default_home_local_backend,
)
from octop.infra.errors import OctopError
from octop.infra.utils.host_dirs import host_fs_tree_root


@pytest.fixture(scope="module")
def catalog() -> ExpertCatalog:
    cat = ExpertCatalog(default_library_root())
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


async def test_bootstrap_requires_catalog() -> None:
    registry = MagicMock()
    registry.get_row.return_value = None
    registry.list_agents.return_value = []
    with pytest.raises(OctopError):
        await bootstrap_default_agent(registry, None, user_id=1, locale="zh")
