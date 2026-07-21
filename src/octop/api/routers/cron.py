"""Cron router."""

from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from octop.api.common.agent import require_agent_row
from octop.api.deps import current_user, get_server
from octop.infra.cron.task_type import normalize_cron_task_type, require_cron_prompt
from octop.infra.cron.trigger import build_trigger
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.ulid import new_cron_id

router = APIRouter()


class CronCreateBody(BaseModel):
    trigger: str
    prompt: str
    session_key: str | None = None
    fresh_thread: bool = False
    model: str | None = None
    task_type: str = "text"


class CronPatchBody(BaseModel):
    trigger: str | None = None
    prompt: str | None = None
    session_key: str | None = None
    fresh_thread: bool | None = None
    enabled: bool | None = None
    model: str | None = None
    task_type: str | None = None


def _get_cron_manager(server: Any) -> Any:
    assert server.app_runtime is not None
    return server.app_runtime.cron_manager


@router.get("/cron/settings", summary="Cron server settings")
async def cron_settings(
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, str]:
    """Return process-level cron configuration (compat; prefer ``GET /settings/timezone``)."""
    return {"timezone": server.services.config.default_timezone}


@router.get("/agents/{agent_id}/cron", summary="List cron jobs")
async def list_cron(
    agent_id: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> list[dict[str, Any]]:
    """List scheduled jobs for an agent."""
    require_agent_row(agent_id, user=user, as_user=None, server=server)
    return [
        r.to_public_dict(include_agent=True)
        for r in _get_cron_manager(server).list_by_agent(agent_id)
    ]


@router.post("/agents/{agent_id}/cron", status_code=201, summary="Create cron job")
async def create_cron(
    agent_id: str,
    body: CronCreateBody,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Schedule a recurring prompt. `trigger` uses cron syntax or natural `@every` aliases."""
    from octop.infra.cron.manager import CronCreateSpec  # noqa: PLC0415

    spec = CronCreateSpec(
        cron_id=new_cron_id(),
        agent_id=agent_id,
        user_id=user.id,
        trigger=body.trigger,
        prompt=require_cron_prompt(body.prompt),
        session_key=body.session_key,
        fresh_thread=body.fresh_thread,
        model=(body.model or "").strip() or None,
        task_type=normalize_cron_task_type(body.task_type),
        username=user.username,
    )
    row = await _get_cron_manager(server).create(spec)
    return cast(dict[str, Any], row.to_public_dict(include_agent=True))


@router.get("/agents/{agent_id}/cron/{cron_id}", summary="Get cron job")
async def get_cron(
    agent_id: str,
    cron_id: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Return one scheduled job by id."""
    row = _get_cron_manager(server).get(cron_id)
    if row is None or row.agent_id != agent_id:
        raise OctopError(ErrorCode.NOT_FOUND, "cron job not found")
    return cast(dict[str, Any], row.to_public_dict(include_agent=True))


@router.patch("/agents/{agent_id}/cron/{cron_id}", summary="Update cron job")
async def patch_cron(
    agent_id: str,
    cron_id: str,
    body: CronPatchBody,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Update trigger, prompt, session binding, or enabled flag."""
    mgr = _get_cron_manager(server)
    existing = mgr.get(cron_id)
    if existing is None or existing.agent_id != agent_id:
        raise OctopError(ErrorCode.NOT_FOUND, "cron job not found")
    if body.trigger is not None:
        build_trigger(body.trigger)
    patch_fields = body.model_dump(exclude_unset=True)
    row = await mgr.update(
        cron_id,
        trigger=body.trigger,
        prompt=require_cron_prompt(body.prompt) if body.prompt is not None else None,
        session_key=body.session_key,
        fresh_thread=body.fresh_thread,
        enabled=int(body.enabled) if body.enabled is not None else None,
        task_type=normalize_cron_task_type(body.task_type) if body.task_type is not None else None,
        **({"model": (body.model or "").strip() or None} if "model" in patch_fields else {}),
    )
    return cast(dict[str, Any], row.to_public_dict(include_agent=True))


@router.delete("/agents/{agent_id}/cron/{cron_id}", status_code=204, summary="Delete cron job")
async def delete_cron(
    agent_id: str,
    cron_id: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> None:
    """Remove a scheduled job."""
    mgr = _get_cron_manager(server)
    existing = mgr.get(cron_id)
    if existing is None or existing.agent_id != agent_id:
        raise OctopError(ErrorCode.NOT_FOUND, "cron job not found")
    await mgr.delete(cron_id)


@router.post("/agents/{agent_id}/cron/{cron_id}/run-now", status_code=204, summary="Run cron now")
async def run_now(
    agent_id: str,
    cron_id: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> None:
    """Trigger an immediate one-off run without waiting for the schedule."""
    mgr = _get_cron_manager(server)
    existing = mgr.get(cron_id)
    if existing is None or existing.agent_id != agent_id:
        raise OctopError(ErrorCode.NOT_FOUND, "cron job not found")
    await mgr.run_now(cron_id)
