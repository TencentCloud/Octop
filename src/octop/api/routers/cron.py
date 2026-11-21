"""Cron router."""

from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from octop.api.common.agent import assert_agent_access, require_agent_row, user_owns_agent
from octop.api.deps import current_user, get_server
from octop.infra.agents.experts.catalog import resolve_agent_display_task_examples
from octop.infra.cron.task_type import normalize_cron_task, require_cron_name
from octop.infra.cron.trigger import build_trigger
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.ulid import new_cron_id

router = APIRouter()


class CronCreateBody(BaseModel):
    name: str | None = None
    trigger: str = Field(
        description="Examples: cron:0 9 * * *, interval:3600, date:2030-01-01T08:00:00, or agently:INSTANCE_ID for new mail events."
    )
    prompt: str
    session_key: str | None = None
    fresh_thread: bool = False
    enabled: bool = True
    model: str | None = None
    task_type: str = "text"
    mcp_servers: list[str] = Field(default_factory=list)
    allow_all: bool = False
    script_lang: str | None = None
    script_source: str | None = None
    script_path: str | None = None


class CronPatchBody(BaseModel):
    name: str | None = None
    trigger: str | None = Field(
        default=None,
        description="Time schedule or agently:INSTANCE_ID for new mail events.",
    )
    prompt: str | None = None
    session_key: str | None = None
    fresh_thread: bool | None = None
    enabled: bool | None = None
    model: str | None = None
    task_type: str | None = None
    mcp_servers: list[str] | None = None
    allow_all: bool | None = None
    script_lang: str | None = None
    script_source: str | None = None
    script_path: str | None = None


class CronExamplesResponse(BaseModel):
    """Compat mirror of welcome ``task_examples`` (workspace → catalog → name)."""

    task_examples: dict[str, list[str]] | None = None


def _get_cron_manager(server: Any) -> Any:
    assert server.app_runtime is not None
    return server.app_runtime.cron_manager


def _user_may_manage_agent_cron(*, agent_row: Any, user: Any) -> bool:
    return user_owns_agent(agent_row, user)


def _assert_cron_manage(
    *, agent_id: str, agent_row: Any, user: Any, row: Any | None = None
) -> None:
    if row is not None and row.agent_id != agent_id:
        raise OctopError(ErrorCode.NOT_FOUND, "cron job not found")
    if not _user_may_manage_agent_cron(agent_row=agent_row, user=user):
        raise OctopError(ErrorCode.FORBIDDEN, "cron job not accessible to user")


@router.get("/cron/settings", summary="Cron server settings")
async def cron_settings(
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, str]:
    """Return process-level cron configuration (compat; prefer ``GET /settings/timezone``)."""
    return {"timezone": server.services.config.default_timezone}


@router.get(
    "/agents/{agent_id}/cron/examples",
    summary="Task page example prompts",
    response_model=CronExamplesResponse,
)
async def cron_examples(
    agent_id: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> CronExamplesResponse:
    """Same resolution as ``GET …/chat/welcome`` ``task_examples`` (API compat)."""
    assert_agent_access(server, agent_id, user)
    assert server.app_runtime is not None
    registry = server.app_runtime.agent_registry
    examples = await resolve_agent_display_task_examples(
        workspace=registry.workspace_for_agent(agent_id),
        row=registry.get_row(agent_id),
        catalog=getattr(server, "expert_catalog", None),
    )
    return CronExamplesResponse(task_examples=examples)


@router.get("/agents/{agent_id}/cron", summary="List cron jobs")
async def list_cron(
    agent_id: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> list[dict[str, Any]]:
    """List scheduled jobs for an agent."""
    agent_row = require_agent_row(agent_id, user=user, as_user=None, server=server)
    if not _user_may_manage_agent_cron(agent_row=agent_row, user=user):
        return []
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
    """Schedule a prompt on a timer or on new mail from a visible Agent Mail instance."""
    from octop.api.common.validators import validate_chat_mcp_servers  # noqa: PLC0415
    from octop.infra.cron.manager import CronCreateSpec  # noqa: PLC0415

    agent_row = require_agent_row(agent_id, user=user, as_user=None, server=server)
    _assert_cron_manage(agent_id=agent_id, agent_row=agent_row, user=user)
    task = normalize_cron_task(
        task_type=body.task_type,
        prompt=body.prompt,
        allow_all=body.allow_all,
        script_lang=body.script_lang,
        script_source=body.script_source,
        script_path=body.script_path,
    )
    cron_id = new_cron_id()
    mcp_servers = (
        await validate_chat_mcp_servers(server, user_id=user.id, names=body.mcp_servers) or []
    )
    spec = CronCreateSpec(
        cron_id=cron_id,
        agent_id=agent_id,
        user_id=user.id,
        name=require_cron_name(body.name, prompt=task.prompt, cron_id=cron_id),
        trigger=body.trigger,
        prompt=task.prompt,
        session_key=body.session_key,
        fresh_thread=body.fresh_thread,
        enabled=body.enabled,
        model=(body.model or "").strip() or None,
        task_type=task.task_type,
        mcp_servers=mcp_servers,
        allow_all=task.allow_all,
        script_lang=task.script_lang,
        script_source=task.script_source,
        script_path=task.script_path,
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
    agent_row = require_agent_row(agent_id, user=user, as_user=None, server=server)
    row = _get_cron_manager(server).get(cron_id)
    if row is None:
        raise OctopError(ErrorCode.NOT_FOUND, "cron job not found")
    _assert_cron_manage(agent_id=agent_id, agent_row=agent_row, user=user, row=row)
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
    from octop.api.common.validators import validate_chat_mcp_servers  # noqa: PLC0415
    from octop.infra.db.repos._base import UNSET  # noqa: PLC0415

    agent_row = require_agent_row(agent_id, user=user, as_user=None, server=server)
    mgr = _get_cron_manager(server)
    existing = mgr.get(cron_id)
    if existing is None:
        raise OctopError(ErrorCode.NOT_FOUND, "cron job not found")
    _assert_cron_manage(agent_id=agent_id, agent_row=agent_row, user=user, row=existing)
    if body.trigger is not None:
        build_trigger(body.trigger)
    patch_fields = body.model_dump(exclude_unset=True)
    task_keys = {
        "task_type",
        "prompt",
        "allow_all",
        "script_lang",
        "script_source",
        "script_path",
    }
    task_kwargs: dict[str, Any] = {}
    prompt_for_name = existing.prompt
    if task_keys & patch_fields.keys():
        task = normalize_cron_task(
            task_type=body.task_type or existing.task_type,
            prompt=body.prompt if isinstance(body.prompt, str) else existing.prompt,
            allow_all=(
                body.allow_all if isinstance(body.allow_all, bool) else bool(existing.allow_all)
            ),
            script_lang=body.script_lang if "script_lang" in patch_fields else existing.script_lang,
            script_source=(
                body.script_source if "script_source" in patch_fields else existing.script_source
            ),
            script_path=body.script_path if "script_path" in patch_fields else existing.script_path,
        )
        prompt_for_name = task.prompt
        task_kwargs = {
            "prompt": task.prompt,
            "task_type": task.task_type,
            "allow_all": task.allow_all,
            "script_lang": task.script_lang,
            "script_source": task.script_source,
            "script_path": task.script_path,
        }
    mcp_arg: object = UNSET
    if "mcp_servers" in patch_fields:
        mcp_arg = await validate_chat_mcp_servers(
            server, user_id=user.id, names=body.mcp_servers or []
        )
    row = await mgr.update(
        cron_id,
        trigger=body.trigger,
        name=(
            require_cron_name(body.name, prompt=prompt_for_name, cron_id=cron_id)
            if "name" in patch_fields
            else None
        ),
        session_key=body.session_key,
        fresh_thread=body.fresh_thread,
        enabled=int(body.enabled) if body.enabled is not None else None,
        **task_kwargs,
        **({"model": (body.model or "").strip() or None} if "model" in patch_fields else {}),
        mcp_servers=mcp_arg,
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
    agent_row = require_agent_row(agent_id, user=user, as_user=None, server=server)
    mgr = _get_cron_manager(server)
    existing = mgr.get(cron_id)
    if existing is None:
        raise OctopError(ErrorCode.NOT_FOUND, "cron job not found")
    _assert_cron_manage(agent_id=agent_id, agent_row=agent_row, user=user, row=existing)
    await mgr.delete(cron_id)


@router.post("/agents/{agent_id}/cron/{cron_id}/run-now", status_code=204, summary="Run cron now")
async def run_now(
    agent_id: str,
    cron_id: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> None:
    """Trigger an immediate one-off run without waiting for the schedule."""
    agent_row = require_agent_row(agent_id, user=user, as_user=None, server=server)
    mgr = _get_cron_manager(server)
    existing = mgr.get(cron_id)
    if existing is None:
        raise OctopError(ErrorCode.NOT_FOUND, "cron job not found")
    _assert_cron_manage(agent_id=agent_id, agent_row=agent_row, user=user, row=existing)
    await mgr.run_now(cron_id)
