"""Terminal review authenticated with the external Codex Memory credential."""

from __future__ import annotations

import asyncio
from typing import Annotated, Any
from weakref import WeakValueDictionary

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field

from octop.api.deps import extract_raw_token, get_server
from octop.infra.agents.codex_memory_review import review_turn
from octop.infra.errors import ErrorCode, OctopError

router = APIRouter()
_locks: WeakValueDictionary[tuple[str, str], asyncio.Lock] = WeakValueDictionary()


class ReviewTurn(BaseModel):
    session_id: str = Field(min_length=7, max_length=256, pattern="^codex:")
    turn_id: str = Field(min_length=1, max_length=256)
    event_ids: list[Annotated[str, Field(pattern=r"^evt_[a-f0-9]{12}$")]] = Field(
        min_length=1, max_length=4
    )


@router.post(
    "/memory-mcp/codex-review",
    summary="Review a captured Codex turn using the selected Octop model",
)
async def review(
    body: ReviewTurn, authorization: str = Header(default=""), server: Any = Depends(get_server)
) -> dict[str, Any]:
    token = extract_raw_token(authorization=authorization)
    if not token or not token.startswith("omcp_"):
        raise OctopError(ErrorCode.AUTH_FAILED, "A Memory space token is required")
    lock = _locks.setdefault((body.session_id, body.turn_id), asyncio.Lock())
    async with lock:
        return await asyncio.to_thread(
            review_turn, server, token, body.session_id, body.turn_id, body.event_ids
        )
