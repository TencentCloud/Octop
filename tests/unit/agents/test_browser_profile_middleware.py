from unittest.mock import AsyncMock

import pytest
from langgraph.prebuilt.tool_node import ToolCallRequest

from octop.infra.agents.middleware import browser_profile


def _request(name: str, args: dict[str, object]) -> ToolCallRequest:
    return ToolCallRequest(
        tool_call={"name": name, "args": args, "id": "call-1"},
        tool=None,
        state={},
        runtime=None,  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_browser_profile_is_forced_from_current_user(monkeypatch) -> None:
    monkeypatch.setattr(
        browser_profile,
        "get_config",
        lambda: {"configurable": {"user": "42"}},
    )
    handler = AsyncMock(return_value=object())
    request = _request("browser_use", {"action": "navigate", "profile": "default"})

    await browser_profile.BrowserProfileMiddleware().awrap_tool_call(request, handler)

    forwarded = handler.await_args.args[0]
    assert forwarded.tool_call["args"] == {
        "action": "navigate",
        "profile": "user-42",
    }


@pytest.mark.asyncio
async def test_non_browser_tool_is_unchanged(monkeypatch) -> None:
    monkeypatch.setattr(
        browser_profile,
        "get_config",
        lambda: {"configurable": {"user": "42"}},
    )
    handler = AsyncMock(return_value=object())
    request = _request("read_file", {"path": "notes.txt"})

    await browser_profile.BrowserProfileMiddleware().awrap_tool_call(request, handler)

    assert handler.await_args.args[0] is request


@pytest.mark.asyncio
async def test_browser_profile_blocks_when_user_missing(monkeypatch) -> None:
    monkeypatch.setattr(browser_profile, "get_config", lambda: {"configurable": {}})
    handler = AsyncMock(return_value=object())
    request = _request("browser_use", {"action": "navigate", "profile": "default"})

    result = await browser_profile.BrowserProfileMiddleware().awrap_tool_call(request, handler)

    handler.assert_not_awaited()
    assert getattr(result, "status", None) == "error"
    assert "no Octop user id" in str(result.content)


@pytest.mark.asyncio
async def test_browser_profile_blocks_placeholder_user_zero(monkeypatch) -> None:
    monkeypatch.setattr(
        browser_profile,
        "get_config",
        lambda: {"configurable": {"user": "0"}},
    )
    handler = AsyncMock(return_value=object())
    request = _request("browser_use", {"action": "navigate"})

    result = await browser_profile.BrowserProfileMiddleware().awrap_tool_call(request, handler)

    handler.assert_not_awaited()
    assert getattr(result, "status", None) == "error"


class _ThreadRow:
    def __init__(self, user_id: int) -> None:
        self.user_id = user_id


class _ThreadStore:
    def __init__(self, owners: dict[str, int]) -> None:
        self._owners = owners

    def get(self, thread_id: str) -> _ThreadRow | None:
        owner = self._owners.get(thread_id)
        return None if owner is None else _ThreadRow(owner)


class _FailingThreadStore:
    def get(self, thread_id: str) -> _ThreadRow | None:
        raise RuntimeError("database is locked")


@pytest.mark.asyncio
async def test_hitl_resume_uses_thread_owner_as_profile(monkeypatch) -> None:
    # A resumed HITL turn carries thread_id only, so no ``user`` key is present.
    monkeypatch.setattr(
        browser_profile,
        "get_config",
        lambda: {"configurable": {"thread_id": "thr-1"}},
    )
    handler = AsyncMock(return_value=object())
    request = _request("browser_use", {"action": "navigate"})

    await browser_profile.BrowserProfileMiddleware(
        thread_repo=_ThreadStore({"thr-1": 7})
    ).awrap_tool_call(request, handler)

    assert handler.await_args.args[0].tool_call["args"] == {
        "action": "navigate",
        "profile": "user-7",
    }


@pytest.mark.asyncio
async def test_explicit_user_wins_over_thread_owner(monkeypatch) -> None:
    monkeypatch.setattr(
        browser_profile,
        "get_config",
        lambda: {"configurable": {"user": "42", "thread_id": "thr-1"}},
    )
    handler = AsyncMock(return_value=object())
    request = _request("browser_use", {"action": "navigate"})

    await browser_profile.BrowserProfileMiddleware(
        thread_repo=_ThreadStore({"thr-1": 7})
    ).awrap_tool_call(request, handler)

    assert handler.await_args.args[0].tool_call["args"] == {
        "action": "navigate",
        "profile": "user-42",
    }


@pytest.mark.asyncio
async def test_unknown_thread_still_blocks(monkeypatch) -> None:
    monkeypatch.setattr(
        browser_profile,
        "get_config",
        lambda: {"configurable": {"thread_id": "thr-9"}},
    )
    handler = AsyncMock(return_value=object())
    request = _request("browser_use", {"action": "navigate"})

    result = await browser_profile.BrowserProfileMiddleware(
        thread_repo=_ThreadStore({"thr-1": 7})
    ).awrap_tool_call(request, handler)

    handler.assert_not_awaited()
    assert getattr(result, "status", None) == "error"
    assert "no Octop user id" in str(result.content)


@pytest.mark.asyncio
async def test_missing_thread_id_still_blocks(monkeypatch) -> None:
    monkeypatch.setattr(browser_profile, "get_config", lambda: {"configurable": {}})
    handler = AsyncMock(return_value=object())
    request = _request("browser_use", {"action": "navigate"})

    result = await browser_profile.BrowserProfileMiddleware(
        thread_repo=_ThreadStore({"thr-1": 7})
    ).awrap_tool_call(request, handler)

    handler.assert_not_awaited()
    assert getattr(result, "status", None) == "error"


@pytest.mark.asyncio
async def test_thread_lookup_failure_keeps_blocking(monkeypatch) -> None:
    # A failing store must not turn the guard into a silent pass-through.
    monkeypatch.setattr(
        browser_profile,
        "get_config",
        lambda: {"configurable": {"thread_id": "thr-1"}},
    )
    handler = AsyncMock(return_value=object())
    request = _request("browser_use", {"action": "navigate"})

    result = await browser_profile.BrowserProfileMiddleware(
        thread_repo=_FailingThreadStore()
    ).awrap_tool_call(request, handler)

    handler.assert_not_awaited()
    assert getattr(result, "status", None) == "error"


@pytest.mark.asyncio
async def test_invalid_user_is_not_replaced_by_thread_owner(monkeypatch) -> None:
    monkeypatch.setattr(
        browser_profile,
        "get_config",
        lambda: {"configurable": {"user": "0", "thread_id": "thr-1"}},
    )
    handler = AsyncMock(return_value=object())
    request = _request("browser_use", {"action": "navigate"})

    result = await browser_profile.BrowserProfileMiddleware(
        thread_repo=_ThreadStore({"thr-1": 7})
    ).awrap_tool_call(request, handler)

    handler.assert_not_awaited()
    assert getattr(result, "status", None) == "error"
