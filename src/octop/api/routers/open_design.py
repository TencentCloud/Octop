"""Authenticated OpenDesign task views and live updates."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from octop.api.deps import current_user, get_server
from octop.infra.connectors.open_design_tasks import OpenDesignTasks

router = APIRouter()
_SCOPE = "/agents/{agent_id}/threads/{thread_id}/open-design"


class DesignTask(BaseModel):
    task_id: str
    instance_id: str
    project: str
    run_id: str | None
    status: str
    last_error: str | None
    result: dict[str, Any] = Field(
        description="Result summary; never launch credentials or source files."
    )
    revision: int
    created_at: int
    updated_at: int
    anchor_message_ids: list[str] = Field(
        default_factory=list,
        description="Assistant messages from the original submission turn, newest first.",
    )


def _tasks(server: Any) -> OpenDesignTasks:
    tasks: OpenDesignTasks = server.app_runtime.agent_registry.open_design.tasks
    return tasks


@router.get(
    _SCOPE + "/tasks",
    summary="List the caller's OpenDesign tasks in a conversation",
    response_model=list[DesignTask],
)
async def list_tasks(
    agent_id: str,
    thread_id: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> list[dict[str, Any]]:
    return await _tasks(server).list_authorized(user.id, agent_id, thread_id)


@router.post(
    _SCOPE + "/tasks/{task_id}/refresh",
    summary="Refresh an owned design task without invoking a model",
    response_model=list[DesignTask],
)
async def refresh_task(
    agent_id: str,
    thread_id: str,
    task_id: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> list[dict[str, Any]]:
    await _tasks(server).refresh_authorized(user.id, agent_id, thread_id, task_id)
    return await _tasks(server).list_authorized(user.id, agent_id, thread_id)


@router.get(
    _SCOPE + "/events",
    summary="Stream durable OpenDesign task snapshots (SSE)",
    description="Initial/reconnected clients receive the persisted task list. Updates do not invoke an LLM.",
)
async def task_events(
    agent_id: str,
    thread_id: str,
    request: Request,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> StreamingResponse:
    tasks = _tasks(server)
    await tasks.list_authorized(user.id, agent_id, thread_id)

    async def stream() -> Any:
        async with tasks.watch(user.id, agent_id, thread_id) as queue:
            while not await request.is_disconnected():
                rows = await tasks.list_authorized(user.id, agent_id, thread_id)
                yield "data: " + json.dumps(rows, ensure_ascii=False) + "\n\n"
                try:
                    await asyncio.wait_for(queue.get(), 20)
                except TimeoutError:
                    yield ": keepalive\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class DesignSelection(BaseModel):
    agent: str | None = Field(default=None, max_length=256)
    model: str | None = Field(default=None, max_length=256)
    skills: list[str] = Field(default_factory=list, max_length=20)
    designSystem: str | None = Field(
        default=None, max_length=256, description="Applied when creating a new project."
    )


class DesignCatalog(BaseModel):
    resources: list[dict[str, Any]]
    next_cursor: str | None
    agents: list[dict[str, Any]]
    selection: DesignSelection


class HealthLevel(BaseModel):
    level: str
    ok: bool
    count: int | None = None


class DesignHealth(BaseModel):
    levels: list[HealthLevel]
    agents: list[dict[str, Any]]
    generation_verified: bool


class ResourceText(BaseModel):
    uri: str
    text: str
    truncated: bool


class DesignFile(BaseModel):
    path: str
    content: str
    digest: str
    truncated: bool
    previewUrl: str | None = None


class EditFile(BaseModel):
    path: str = Field(min_length=1, max_length=1024)
    digest: str = Field(
        pattern=r"^[a-f0-9]{64}$", description="SHA-256 of the last complete file read."
    )
    content: str = Field(max_length=512_000)


def _console(server: Any) -> Any:
    return server.app_runtime.agent_registry.open_design.console


@router.get(
    "/connector-instances/{instance_id}/open-design/health",
    summary="Check launch, protocol, daemon, runtime and resources without generating",
    response_model=DesignHealth,
)
async def health(
    instance_id: str, user: Any = Depends(current_user), server: Any = Depends(get_server)
) -> Any:
    return await _console(server).health(user.id, instance_id)


_INSTANCE = _SCOPE + "/instances/{instance_id}"


@router.get(
    _INSTANCE + "/catalog",
    summary="Discover available runtimes and paginated materials",
    response_model=DesignCatalog,
)
async def catalog(
    agent_id: str,
    thread_id: str,
    instance_id: str,
    cursor: str | None = Query(default=None, max_length=4096),
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> Any:
    return await _console(server).catalog(user.id, instance_id, agent_id, thread_id, cursor)


@router.put(
    _INSTANCE + "/selection",
    summary="Save validated material and runtime choices for this conversation",
    response_model=DesignSelection,
)
async def selection(
    agent_id: str,
    thread_id: str,
    instance_id: str,
    body: DesignSelection,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> DesignSelection:
    await _console(server).save_selection(
        user.id, instance_id, agent_id, thread_id, body.model_dump(exclude_none=True)
    )
    return body


@router.get(
    _INSTANCE + "/resource",
    summary="Read selected material as bounded plain text",
    response_model=ResourceText,
)
async def resource(
    agent_id: str,
    thread_id: str,
    instance_id: str,
    uri: str = Query(min_length=1, max_length=4096),
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> Any:
    return await _console(server).resource(user.id, instance_id, agent_id, thread_id, uri)


@router.get(
    _INSTANCE + "/projects/{project}/search",
    summary="Search source files in a project used by this conversation",
    response_model=dict[str, Any],
)
async def search(
    agent_id: str,
    thread_id: str,
    instance_id: str,
    project: str,
    query: str = Query(min_length=1, max_length=512),
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> Any:
    return await _console(server).search(user.id, instance_id, agent_id, thread_id, project, query)


@router.get(
    _INSTANCE + "/projects/{project}/file",
    summary="Read a bounded source file and its digest",
    response_model=DesignFile,
)
async def read_file(
    agent_id: str,
    thread_id: str,
    instance_id: str,
    project: str,
    path: str = Query(min_length=1, max_length=1024),
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> Any:
    return await _console(server).file(user.id, instance_id, agent_id, thread_id, project, path)


@router.put(
    _INSTANCE + "/projects/{project}/file",
    summary="Recheck, write and verify a source edit",
    description="Rejects changed/truncated files and known running tasks. Read-compare-write is not an atomic upstream version check.",
    response_model=DesignFile,
)
async def edit_file(
    agent_id: str,
    thread_id: str,
    instance_id: str,
    project: str,
    body: EditFile,
    request: Request,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> Any:
    from octop.infra.utils.locale import resolve_request_locale

    return await _console(server).edit(
        user.id,
        instance_id,
        agent_id,
        thread_id,
        project,
        body.path,
        body.digest,
        body.content,
        resolve_request_locale(request),
    )


@router.post(
    _SCOPE + "/tasks/{task_id}/cancel",
    summary="Explicitly cancel a generation task owned by this conversation",
    response_model=list[DesignTask],
)
async def cancel_task(
    agent_id: str,
    thread_id: str,
    task_id: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> Any:
    await _console(server).cancel(user.id, agent_id, thread_id, task_id)
    return await _tasks(server).list_authorized(user.id, agent_id, thread_id)


@router.get(
    "/connector-instances/{instance_id}/open-design/catalog",
    summary="Discover materials and the caller's connector defaults",
    response_model=DesignCatalog,
)
async def default_catalog(
    instance_id: str,
    cursor: str | None = Query(default=None, max_length=4096),
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> Any:
    return await _console(server).catalog(user.id, instance_id, "", "", cursor)


@router.put(
    "/connector-instances/{instance_id}/open-design/selection",
    summary="Save the caller's default runtime and materials for this connector",
    response_model=DesignSelection,
)
async def default_selection(
    instance_id: str,
    body: DesignSelection,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> DesignSelection:
    await _console(server).save_selection(
        user.id, instance_id, "", "", body.model_dump(exclude_none=True)
    )
    return body


@router.get(
    "/connector-instances/{instance_id}/open-design/resource",
    summary="Preview a material from an accessible connector as plain text",
    response_model=ResourceText,
)
async def default_resource(
    instance_id: str, uri: str, user: Any = Depends(current_user), server: Any = Depends(get_server)
) -> Any:
    return await _console(server).resource(user.id, instance_id, "", "", uri)
