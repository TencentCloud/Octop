"""Embedded CLI runtime does not start IM channel connections."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from octop.cli.repl import embedded_session


@pytest.mark.asyncio
async def test_embedded_runtime_disables_im_channels(monkeypatch: pytest.MonkeyPatch) -> None:
    server = MagicMock()
    server.start = AsyncMock()
    server.stop = AsyncMock()
    factory = MagicMock(return_value=server)
    monkeypatch.setattr(embedded_session, "OctopServer", factory)

    async with embedded_session.embedded_runtime() as started:
        assert started is server

    factory.assert_called_once_with(register_im_channels=False)
    server.start.assert_awaited_once()
    server.stop.assert_awaited_once()
