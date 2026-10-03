"""Regression tests for the graph-state fallback slice in ``embedded_ops``.

``messages[-limit:]`` cannot express "no messages": for ``limit == 0`` Python
evaluates ``messages[-0:]`` as ``messages[0:]``, i.e. the *entire* history. The
sibling web path already guards this in
``api/routers/chat/serialize.py::_slice_message_page``; the CLI fallback did
not, so ``octop chats get --limit 0`` returned everything while
``octop chats list --limit 0`` (SQL ``LIMIT 0``) returned nothing.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any

import pytest

from octop.cli.support import embedded_ops
from octop.infra.errors import ErrorCode, OctopError

_MESSAGES = [{"role": "user", "content": f"m{i}"} for i in range(10)]


class _FakeGraph:
    def __init__(self, messages: list[Any]) -> None:
        self._messages = messages

    async def aget_state(self, _config: dict[str, Any]) -> SimpleNamespace:
        return SimpleNamespace(values={"messages": self._messages})


class _FakeHarness:
    """Harness without ``aget_history``, so the graph fallback is exercised."""

    def __init__(self, messages: list[Any]) -> None:
        self.graph = _FakeGraph(messages)


def _install_runtime(
    monkeypatch: pytest.MonkeyPatch,
    harness: _FakeHarness,
    *,
    thread_agent_id: str = "a1",
) -> list[int]:
    """Patch ``embedded_runtime`` and return the captured ``aget_state`` calls."""
    seen: list[int] = []

    class _ThreadRegistry:
        def get_thread(self, thread_id: str) -> Any:
            return SimpleNamespace(agent_id=thread_agent_id, id=thread_id)

    class _AgentRegistry:
        def get_agent(self, agent_id: str) -> Any:
            return harness

        async def start(self, agent_id: str) -> None:
            return None

    @asynccontextmanager
    async def fake_runtime():
        yield SimpleNamespace(
            app_runtime=SimpleNamespace(
                gateway=SimpleNamespace(thread_registry=_ThreadRegistry()),
                agent_registry=_AgentRegistry(),
            )
        )

    class _GraphSpy(_FakeGraph):
        async def aget_state(self, config: dict[str, Any]) -> SimpleNamespace:
            seen.append(1)
            return await super().aget_state(config)

    harness.graph = _GraphSpy(_MESSAGES)  # type: ignore[assignment]
    monkeypatch.setattr(embedded_ops, "embedded_runtime", fake_runtime)
    return seen


def _fetch(limit: int) -> Any:
    return asyncio.run(embedded_ops.fetch_thread_history_async("a1", "t1", limit=limit))


def test_zero_limit_returns_nothing_not_the_whole_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The bug: ``messages[-0:]`` is ``messages[0:]`` -- all 10 messages."""
    _install_runtime(monkeypatch, _FakeHarness(_MESSAGES))
    assert _fetch(0) == []


@pytest.mark.parametrize("limit", [-1, -5, -100])
def test_negative_limit_returns_nothing(monkeypatch: pytest.MonkeyPatch, limit: int) -> None:
    _install_runtime(monkeypatch, _FakeHarness(_MESSAGES))
    assert _fetch(limit) == []


def test_positive_limit_still_takes_the_tail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_runtime(monkeypatch, _FakeHarness(_MESSAGES))
    assert _fetch(3) == _MESSAGES[-3:]
    assert len(_fetch(50)) == 10


def test_aget_history_path_still_delegates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the harness *does* expose ``aget_history`` the fallback is skipped."""
    calls: list[int] = []

    class _HarnessWithHistory(_FakeHarness):
        async def aget_history(self, thread_id: str, *, limit: int) -> list[Any]:
            calls.append(limit)
            return _MESSAGES[-limit:] if limit > 0 else _MESSAGES

    _install_runtime(monkeypatch, _HarnessWithHistory(_MESSAGES))
    _fetch(4)
    assert calls == [4]


def test_missing_thread_still_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_runtime(monkeypatch, _FakeHarness(_MESSAGES), thread_agent_id="other")
    with pytest.raises(OctopError) as exc:
        _fetch(10)
    assert exc.value.code == ErrorCode.AGENT_NOT_FOUND
