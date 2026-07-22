"""Unit tests for Gateway runtime channel status."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from octop.config import OctopConfig
from octop.infra.agents.manager import AgentManager
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.services import build_shared_services
from octop.infra.gateway.gateway import Gateway
from octop.infra.utils.paths import PathLayout


def _make_gateway(tmp_path: Path) -> Gateway:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    services = build_shared_services(db=db, paths=PathLayout(tmp_path), config=OctopConfig())
    registry = AgentManager(
        repos=services.repos,
        paths=services.paths,
        config=services.config,
    )
    return Gateway(agent_manager=registry, repos=services.repos)


def _fake_row(channel_id: str = "ch1") -> MagicMock:
    row = MagicMock()
    row.channel_id = channel_id
    row.agent_id = "agent1"
    row.kind = "feishu"
    row.name = "main"
    row.config_json = '{"app_id":"x","app_secret":"y"}'
    row.enabled = 1
    return row


@pytest.mark.asyncio
async def test_register_success_sets_runtime_connected(tmp_path: Path) -> None:
    gw = _make_gateway(tmp_path)
    gw._channel_manager = MagicMock()
    gw._channel_manager.add_channel = AsyncMock()
    gw._channel_manager.get_channel = MagicMock(return_value=MagicMock())
    gw._processor = MagicMock()

    await gw._register_channel(_fake_row())

    status = gw.get_runtime_status("ch1")
    assert status is not None
    assert status.connected is True
    assert status.reason is None


@pytest.mark.asyncio
async def test_register_failure_sets_runtime_error(tmp_path: Path) -> None:
    gw = _make_gateway(tmp_path)
    gw._channel_manager = MagicMock()
    gw._channel_manager.add_channel = AsyncMock(side_effect=RuntimeError("boom"))
    gw._processor = MagicMock()

    await gw._safe_register_channel(_fake_row())

    status = gw.get_runtime_status("ch1")
    assert status is not None
    assert status.connected is False
    assert status.reason == "error"
    assert "boom" in (status.detail or "")
    rendered = gw.runtime_status_to_dict("ch1", locale="zh")
    assert rendered is not None
    assert "boom" in rendered["error"]


@pytest.mark.asyncio
async def test_probe_weixin_without_token_fails_before_start(tmp_path: Path) -> None:
    from harness_gateway.manager import ChannelManager

    gw = _make_gateway(tmp_path)
    gw._channel_manager = ChannelManager()
    row = _fake_row()
    row.kind = "weixin"
    row.config_json = '{"bot_uin":"wx"}'

    result = await gw._probe_row(row, locale="zh")
    assert result["ok"] is False
    assert "Token" in result["error"]
