"""``GET /media/preview`` must read a stopped agent's workspace like download does."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from octop.api.routers.workspace import preview_media
from octop.infra.errors import ErrorCode, OctopError

SOURCE = "/api/agents/A1/workspace/download?path=/outbound/shot.png"
PNG = b"\x89PNG\r\n\x1a\n"


def _server(*, last_state: str, owner_id: int, is_shared: int = 0) -> SimpleNamespace:
    """Registry whose agent has no live harness handle — only a row + workspace."""
    workspace = MagicMock()
    workspace.workspace_dir = SimpleNamespace(expanduser=lambda: SimpleNamespace())
    workspace.adownload_bytes = AsyncMock(return_value=PNG)
    registry = MagicMock()
    registry.get_row.return_value = SimpleNamespace(
        agent_id="A1",
        user_id=owner_id,
        is_shared=is_shared,
        enabled=True,
        last_state=last_state,
    )
    registry.get_agent.side_effect = OctopError(
        ErrorCode.AGENT_NOT_RUNNING, "agent 'A1' not running"
    )
    registry.workspace_for_agent.return_value = workspace
    return SimpleNamespace(app_runtime=SimpleNamespace(agent_registry=registry))


async def test_preview_media_reads_a_stopped_agent() -> None:
    server = _server(last_state="stopped", owner_id=1)
    user = SimpleNamespace(id=1, is_admin=False)

    response = await preview_media(
        "A1",
        source=SOURCE,
        mime_type=None,
        as_user=None,
        user=user,
        server=server,
    )

    assert response.status_code == 200
    assert response.media_type == "image/png"


async def test_preview_media_still_rejects_an_inaccessible_agent() -> None:
    server = _server(last_state="stopped", owner_id=1)
    stranger = SimpleNamespace(id=2, is_admin=False)

    with pytest.raises(OctopError) as excinfo:
        await preview_media(
            "A1",
            source=SOURCE,
            mime_type=None,
            as_user=None,
            user=stranger,
            server=server,
        )

    assert excinfo.value.code is ErrorCode.FORBIDDEN
    server.app_runtime.agent_registry.workspace_for_agent.assert_not_called()
