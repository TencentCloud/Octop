"""Tests for in-process desktop session registry."""

from __future__ import annotations

import pytest

from octop.infra.desktop.session import (
    DesktopSessionLimitError,
    acquire_session,
    active_session_count,
    release_session,
)


@pytest.mark.asyncio
async def test_acquire_replaces_same_user_session(monkeypatch) -> None:
    monkeypatch.setattr("octop.infra.desktop.session._MAX_DESKTOP_SESSIONS", 1)

    first = await acquire_session(user_id="u1", display=":99", monitor=0)
    second = await acquire_session(user_id="u1", display=":99", monitor=0)

    assert first is not second
    assert active_session_count() == 1

    await release_session(user_id="u1", session=first)
    assert active_session_count() == 1

    await release_session(user_id="u1", session=second)
    assert active_session_count() == 0


@pytest.mark.asyncio
async def test_supersede_calls_previous_disconnect() -> None:
    from octop.infra.desktop.session import clear_user_stream, supersede_user_stream

    calls: list[str] = []

    async def first() -> None:
        calls.append("first")

    async def second() -> None:
        calls.append("second")

    await supersede_user_stream("u1", first)
    await supersede_user_stream("u1", second)

    assert calls == ["first"]

    await clear_user_stream("u1", second)


@pytest.mark.asyncio
async def test_acquire_raises_when_global_cap_reached(monkeypatch) -> None:
    monkeypatch.setattr("octop.infra.desktop.session._MAX_DESKTOP_SESSIONS", 1)

    s1 = await acquire_session(user_id="u1", display=":99", monitor=0)
    with pytest.raises(DesktopSessionLimitError) as exc:
        await acquire_session(user_id="u2", display=":99", monitor=0)

    assert exc.value.limit == 1
    assert exc.value.active == 1

    await release_session(user_id="u1", session=s1)


@pytest.mark.asyncio
async def test_disconnect_all_streams_closes_sessions(monkeypatch) -> None:
    from octop.infra.desktop.session import disconnect_all_streams, supersede_user_stream

    monkeypatch.setattr("octop.infra.desktop.session._MAX_DESKTOP_SESSIONS", 3)

    called: list[str] = []

    async def handler() -> None:
        called.append("disconnect")

    await supersede_user_stream("u1", handler)
    session = await acquire_session(user_id="u1", display=":99", monitor=0)
    assert active_session_count() == 1

    await disconnect_all_streams()

    assert called == ["disconnect"]
    assert active_session_count() == 0
    await release_session(user_id="u1", session=session)


@pytest.mark.asyncio
async def test_release_ignores_stale_session_after_replace(monkeypatch) -> None:
    monkeypatch.setattr("octop.infra.desktop.session._MAX_DESKTOP_SESSIONS", 2)

    first = await acquire_session(user_id="u1", display=":99", monitor=0)
    second = await acquire_session(user_id="u1", display=":99", monitor=0)

    await release_session(user_id="u1", session=first)
    assert active_session_count() == 1

    await release_session(user_id="u1", session=second)
    assert active_session_count() == 0
