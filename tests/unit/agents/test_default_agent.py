"""Unit tests for default-agent bootstrap helper."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from octop.infra.agents.default_agent import (
    DEFAULT_EXPERT_ID,
    SETUP_DEFAULT_AGENT_ID,
    bootstrap_default_agent,
)
from octop.infra.agents.experts.catalog import ExpertCatalog, default_library_root
from octop.infra.errors import OctopError


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
    assert registry.create.await_args.kwargs["defer_bootstrap"] is True


async def test_bootstrap_requires_catalog() -> None:
    registry = MagicMock()
    registry.get_row.return_value = None
    registry.list_agents.return_value = []
    with pytest.raises(OctopError):
        await bootstrap_default_agent(registry, None, user_id=1, locale="zh")
