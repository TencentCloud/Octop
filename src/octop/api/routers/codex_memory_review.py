"""Terminal review authenticated with the external Codex Memory credential."""

from __future__ import annotations

import asyncio
from typing import Annotated, Any
from weakref import WeakValueDictionary

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field

from octop.api.deps import extract_raw_token, get_server
from octop.infra.agents.codex_memory_review import review_turn, sync_terminal
from octop.infra.errors import ErrorCode, OctopError

router = APIRouter()
_locks: WeakValueDictionary[tuple[str, str], asyncio.Lock] = WeakValueDictionary()


class ReviewTurn(BaseModel):
    session_id: str = Field(min_length=7, max_length=256, pattern="^codex:")
    turn_id: str = Field(min_length=1, max_length=256)
    event_ids: list[Annotated[str, Field(pattern=r"^evt_[a-f0-9]{12}$")]] = Field(
        min_length=1, max_length=4
    )


class TerminalSync(BaseModel):
    applied_revision: str | None = Field(default=None, max_length=64)


def _memory_token(authorization: str = Header(default="")) -> str:
    token = extract_raw_token(authorization=authorization)
    if not token or not token.startswith("omcp_"):
        raise OctopError(ErrorCode.AUTH_FAILED, "A Memory space token is required")
    return token


@router.post(
    "/memory-mcp/codex-config", summary="Pull or acknowledge this terminal's published mode"
)
def terminal_config(
    body: TerminalSync, token: str = Depends(_memory_token), server: Any = Depends(get_server)
) -> dict[str, Any]:
    return sync_terminal(server, token, body.applied_revision)


@router.post(
    "/memory-mcp/codex-review",
    summary="Review a captured Codex turn using the selected Octop model",
)
async def review(
    body: ReviewTurn, token: str = Depends(_memory_token), server: Any = Depends(get_server)
) -> dict[str, Any]:
    lock = _locks.setdefault((body.session_id, body.turn_id), asyncio.Lock())
    async with lock:
        return await asyncio.to_thread(
            review_turn, server, token, body.session_id, body.turn_id, body.event_ids
        )
