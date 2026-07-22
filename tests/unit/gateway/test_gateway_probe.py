"""Unit tests for Gateway.probe_channel()."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

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
async def test_probe_channel_start_stop_ok(tmp_path: Path) -> None:
    gw = _make_gateway(tmp_path)
    gw._channel_manager = MagicMock()
    gw._channel_manager.probe_channel = AsyncMock()

    with patch.object(gw, "get_channel", return_value=_fake_row()):
        result = await gw.probe_channel("ch1")

    assert result == {"ok": True}
    gw._channel_manager.probe_channel.assert_awaited_once()


@pytest.mark.asyncio
async def test_probe_channel_returns_error_on_start_failure(tmp_path: Path) -> None:
    gw = _make_gateway(tmp_path)
    gw._channel_manager = MagicMock()
    gw._channel_manager.probe_channel = AsyncMock(side_effect=RuntimeError("connect refused"))

    with patch.object(gw, "get_channel", return_value=_fake_row("ch2")):
        result = await gw.probe_channel("ch2")

    assert result["ok"] is False
    assert "connect refused" in result["error"]


@pytest.mark.asyncio
async def test_probe_config_without_persisted_row(tmp_path: Path) -> None:
    gw = _make_gateway(tmp_path)
    gw._channel_manager = MagicMock()
    gw._channel_manager.probe_channel = AsyncMock()

    result = await gw.probe_config(
        agent_id="agent1",
        kind="feishu",
        config={"app_id": "x", "app_secret": "y"},
    )

    assert result == {"ok": True}
    call = gw._channel_manager.probe_channel.await_args
    assert call is not None
    assert call.kwargs["tenant_id"] == "agent1"
    assert call.kwargs["channel_id"] == "__probe__"
    assert call.args[0] == "feishu"
