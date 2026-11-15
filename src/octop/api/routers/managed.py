"""Create a managed agent bound to one ACP runner."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from octop.api.common.agent import apply_agent_audience
from octop.api.deps import current_user, get_server
from octop.api.routers.agents import _row_dict
from octop.infra.agents.experts.composer_files import (
    apply_composer_workspace_patch,
    composer_patch_from_payload,
)
from octop.infra.agents.managed import (
    MANAGED_KIND,
    apply_managed_backend,
    managed_template_payload,
    pin_managed_runtime,
    seed_managed_workspace,
)
from octop.infra.agents.manager import AgentCreateSpec
from octop.infra.agents.workspace.dir import apply_explicit_workspace_dir
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.history.trajectory.settings import apply_enable_trajectory
from octop.infra.users.groups import GroupAccess

router = APIRouter()


class _LocalizedText(BaseModel):
    zh: str = ""
    en: str = ""


class _QuickPromptBody(BaseModel):
    title: _LocalizedText
    description: _LocalizedText = Field(default_factory=_LocalizedText)
    prompt: _LocalizedText
    color: str = "#e8f4ff"
    icon_name: str | None = None


class _FileOverrideBody(BaseModel):
    name: str
    content: str = ""


class ManagedCreateBody(BaseModel):
    name: str
    runner: str = Field(description="Enabled ACP runner id")
    workspace_dir: str = Field(description="Working directory passed to the ACP session")
    description: str | None = None
    welcome_message: str | None = None
    agent_id: str | None = Field(
        default=None,
        max_length=64,
        description="Optional public id; generated when omitted",
    )
    color: str | None = None
    icon_url: str | None = None
    enable_trajectory: bool = True
    visibility: Literal["owner", "all", "groups"] | None = None
    group_ids: list[str] | None = None
    quick_prompts: list[_QuickPromptBody] | None = None
    file_overrides: list[_FileOverrideBody] | None = None


def _prompt_dict(prompt: _QuickPromptBody) -> dict[str, Any]:
    return {
        "title": {"zh": prompt.title.zh, "en": prompt.title.en},
        "description": {"zh": prompt.description.zh, "en": prompt.description.en},
        "prompt": {"zh": prompt.prompt.zh, "en": prompt.prompt.en},
        "color": prompt.color,
        "icon_name": prompt.icon_name,
    }


def _workspace_initializer(body: ManagedCreateBody) -> Any:
    prompts = (
        [_prompt_dict(item) for item in body.quick_prompts]
        if body.quick_prompts is not None
        else None
    )
    overrides = (
        [{"name": item.name, "content": item.content} for item in body.file_overrides]
        if body.file_overrides
        else None
    )

    async def _apply(_row: Any, workspace: Any) -> None:
        agents_md = None
        if overrides:
            for item in overrides:
                if item["name"].strip() == "AGENTS.md":
                    agents_md = item["content"]
        await seed_managed_workspace(workspace, agents_md=agents_md, quick_prompts=prompts)
        extra = [item for item in (overrides or []) if item["name"].strip() != "AGENTS.md"]
        if extra:
            patch = composer_patch_from_payload(
                file_overrides=extra,
                omit_files=None,
                hub_skills=None,
            )
            await apply_composer_workspace_patch(workspace, patch)

    return _apply


def _enabled_runner(server: Any, user_id: int, runner: str) -> None:
    registry = server.app_runtime.agent_registry
    runners = registry.acp_settings.load_runners(user_id)
    spec = runners.get(runner)
    if not isinstance(spec, dict) or not spec.get("enabled"):
        raise OctopError(ErrorCode.NOT_FOUND, f"ACP runner {runner!r} is not enabled", status=404)


@router.get("/managed-agents/template", summary="Default managed workspace files")
async def managed_agent_template(
    _user: Any = Depends(current_user),
) -> dict[str, Any]:
    """Programming welcome cards and ``AGENTS.md`` copied into a new workspace."""
    return managed_template_payload()


@router.post("/managed-agents", summary="Create a managed ACP agent")
async def create_managed_agent(
    body: ManagedCreateBody,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Create an agent that forwards each turn to one connected ACP runner.

    The backend is the local filesystem rooted at ``/``. ``workspace_dir`` is
    the working directory for both the agent workspace and the ACP session.
    """
    runner = body.runner.strip()
    _enabled_runner(server, user.id, runner)
    config: dict[str, Any] = {"managed_runner": runner}
    apply_enable_trajectory(config, body.enable_trajectory)
    apply_managed_backend(config)
    pin_managed_runtime(config)
    apply_explicit_workspace_dir(config, body.workspace_dir)
    if body.visibility is not None:
        GroupAccess(server.services.repos).validate_visibility(body.visibility, body.group_ids)
    spec = AgentCreateSpec(
        name=body.name.strip(),
        agent_id=(body.agent_id or "").strip() or None,
        user_id=user.id,
        description=body.description,
        welcome_message=body.welcome_message,
        color=body.color,
        icon_url=(body.icon_url or "").strip() or None,
        kind=MANAGED_KIND,
        config=config,
        mcp_servers=[],
    )
    assert server.app_runtime is not None
    row = await server.app_runtime.agent_registry.create(
        spec,
        workspace_initializer=_workspace_initializer(body),
    )
    if body.visibility is not None:
        row = await apply_agent_audience(
            server,
            row.agent_id,
            visibility=body.visibility,
            group_ids=body.group_ids,
            shared=body.visibility != "owner",
        )
    return _row_dict(row, viewer_user_id=user.id, server=server)
