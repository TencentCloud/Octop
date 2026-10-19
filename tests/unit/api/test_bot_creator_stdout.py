"""Bot creator polling joins pending bytes with the final stdout drain."""

from __future__ import annotations

import asyncio
import io
import json
from types import SimpleNamespace

import pytest

from octop.api.routers import channels
from octop.infra.utils import subprocess_io


@pytest.mark.parametrize("kind", ["feishu", "yuanbao"])
async def test_bot_creator_poll_preserves_split_final_event(
    monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    event = {
        "action": "finish",
        "level": "success",
        "data": {"app_id": "cli_test", "app_key": "test_key", "app_secret": "test_secret"},
    }
    raw = json.dumps(event).encode()
    cut = len(raw) // 2
    chunks = iter([raw[:cut], b""])
    statuses = iter([None, 0])
    proc = SimpleNamespace(stdout=io.BytesIO(raw[cut:]), poll=lambda: next(statuses))
    state = {"proc": proc, "lines": [], "lock": asyncio.Lock()}
    monkeypatch.setattr(subprocess_io, "read_available_bytes", lambda _stream: next(chunks))
    monkeypatch.setattr(channels, "_require_agent_access", lambda *args, **kwargs: None)
    monkeypatch.setattr(channels, f"_get_{kind}_state", lambda _agent_id: state)
    poll = getattr(channels, f"{kind}_bot_creator_poll")

    running = await poll("test-agent", as_user=None, user=None, server=None)
    assert running["status"] == "running"
    assert running["events"] == []
    finished = await poll("test-agent", as_user=None, user=None, server=None)
    assert finished["status"] == "finished"
    assert finished["events"] == [event]
    assert finished["app_secret"] == "test_secret"
    assert state["lines"] == [event]
