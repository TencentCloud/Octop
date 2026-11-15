"""Cron turns must carry the owner's personal provider key, like gateway turns."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from octop.infra.cron.delivery import CronDeliveryCommand, CronDeliveryService
from octop.infra.gateway.threads import ThreadRegistry


def _session() -> MagicMock:
    session = MagicMock()
    session.channel_type = ThreadRegistry.CHANNEL_DASHBOARD
    session.thread_id = "thr1"
    session.user_id = 1
    session.agent_id = "a1"
    session.session_key = "a1:dashboard:1:dm"
    session.channel_id = None
    return session


async def _run_locked(_agent_id: str, _session_key: str, operation: Any) -> None:
    await operation()


def _command(**overrides: object) -> CronDeliveryCommand:
    values: dict[str, object] = {
        "cron_id": "j1",
        "cron_name": "nightly",
        "agent_id": "a1",
        "user_id": 1,
        "session_key": "a1:dashboard:1:dm",
        "prompt": "cron prompt",
        "fresh_thread": False,
        "task_type": "agent",
        "model": None,
        "mcp_servers": (),
    }
    values.update(overrides)
    return CronDeliveryCommand(**values)  # type: ignore[arg-type]


def _service(
    seen: list[dict[str, Any]], *, default_ref: str | None, key: str | None
) -> CronDeliveryService:
    async def _stream(_agent_id: str, request: dict[str, Any]) -> Any:
        seen.append(dict(request.get("configurable") or {}))
        yield {"type": "token", "content": "ok"}

    agent_row = MagicMock()
    agent_row.default_model = None
    agent_row.kind = "expert"

    agent_manager = MagicMock()
    agent_manager.merge_turn_mcp_servers = MagicMock(return_value=[])
    agent_manager.prepare_chat_mcp = AsyncMock(return_value=[])
    agent_manager.stream = _stream
    agent_manager.get_row = MagicMock(return_value=agent_row)
    agent_manager.get_config = MagicMock(return_value={})
    agent_manager.providers.resolve_explicit_default_model = MagicMock(return_value=None)
    agent_manager.resolve_fallback_model_ref = MagicMock(return_value=default_ref)
    agent_manager.resolve_api_key_override = MagicMock(return_value=key)

    gateway = MagicMock()
    gateway.run_in_session = _run_locked
    gateway.require_session = MagicMock(return_value=_session())
    gateway.push_session_text = AsyncMock()
    gateway.notify_dashboard_push = AsyncMock()
    return CronDeliveryService(gateway=gateway, agent_manager=agent_manager, repos=MagicMock())


@pytest.mark.asyncio
async def test_pinned_model_carries_personal_key_and_provider() -> None:
    seen: list[dict[str, Any]] = []
    service = _service(seen, default_ref=None, key="sk-user")

    await service.deliver(_command(model="p/pinned"))

    assert seen[0]["api_key_override"] == "sk-user"
    assert seen[0]["api_key_override_provider"] == "p"


@pytest.mark.asyncio
async def test_auto_job_resolves_the_default_ref_for_the_key() -> None:
    seen: list[dict[str, Any]] = []
    service = _service(seen, default_ref="p/auto", key="sk-user")

    await service.deliver(_command(model=None))

    assert seen[0]["api_key_override"] == "sk-user"
    assert seen[0]["api_key_override_provider"] == "p"


@pytest.mark.asyncio
async def test_no_personal_key_adds_nothing() -> None:
    seen: list[dict[str, Any]] = []
    service = _service(seen, default_ref="p/auto", key=None)

    await service.deliver(_command(model=None))

    assert "api_key_override" not in seen[0]
    assert "api_key_override_provider" not in seen[0]
