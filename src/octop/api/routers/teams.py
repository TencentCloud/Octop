"""Expert teams — create, list, update roster."""

from __future__ import annotations

from typing import Any, Literal, cast

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from octop.api.common.agent import (
    apply_agent_audience,
    assert_agent_access_row,
    assert_agent_owner,
)
from octop.api.deps import current_user, get_server
from octop.infra.agents.manager import AgentCreateSpec
from octop.infra.agents.teams import (
    TEAM_KIND,
    TEAM_TEMPLATE_NAME,
    TEMPLATE_DIR,
    is_team_agent,
    team_icon_url,
)
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.users.groups import GroupAccess

router = APIRouter()


class TeamCreateBody(BaseModel):
    name: str
    description: str | None = None
    default_model: str | None = None
    color: str | None = None
    icon_name: str | None = None
    icon_url: str | None = None
    welcome_message: str | None = None
    member_ids: list[str] = Field(default_factory=list)
    agent_id: str | None = Field(
        default=None,
        max_length=64,
        description="Optional custom agent id; auto-generated when omitted",
    )
    config: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Harness config. ``workspace_dir`` is kept only when ``backend`` is "
            "local_shell or filesystem rooted at the filesystem root."
        ),
    )
    is_shared: bool = False
    visibility: Literal["owner", "all", "groups"] | None = Field(
        default=None,
        description="Who may chat with this team. Overrides is_shared when set.",
    )
    group_ids: list[str] = Field(
        default_factory=list,
        description="User group ids when visibility is groups",
    )


class TeamPatchBody(BaseModel):
    name: str | None = None
    description: str | None = None
    default_model: str | None = None
    color: str | None = None
    icon_name: str | None = None
    icon_url: str | None = None
    welcome_message: str | None = None
    member_ids: list[str] | None = None
    is_shared: bool | None = None
    visibility: Literal["owner", "all", "groups"] | None = Field(
        default=None,
        description="Who may chat with this team. Overrides is_shared when set.",
    )
    group_ids: list[str] | None = Field(
        default=None,
        description="User group ids when visibility is groups",
    )


def _teams(server: Any) -> Any:
    assert server.app_runtime is not None
    return server.app_runtime.agent_registry.teams


def _load_team_row(server: Any, team_id: str) -> Any:
    assert server.app_runtime is not None
    row = server.app_runtime.agent_registry.get_row(team_id)
    if row is None or not is_team_agent(row):
        raise OctopError(ErrorCode.TEAM_NOT_FOUND, f"team {team_id!r} not found")
    return row


def _require_visible_team(server: Any, user: Any, team_id: str) -> Any:
    row = _load_team_row(server, team_id)
    assert_agent_access_row(row, user, repos=server.services.repos)
    return row


def _require_owned_team(server: Any, user: Any, team_id: str) -> Any:
    row = _require_visible_team(server, user, team_id)
    assert_agent_owner(row, user)
    return row


def _validate_team_audience(server: Any, body: TeamCreateBody | TeamPatchBody) -> None:
    if body.visibility is None:
        return
    GroupAccess(server.services.repos).validate_visibility(body.visibility, body.group_ids)


@router.get("/teams", summary="List expert teams I can use")
async def list_teams(
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> list[dict[str, Any]]:
    """Owned teams, plus teams other users have shared with the caller."""
    return cast(list[dict[str, Any]], _teams(server).list_visible(user))


@router.post("/teams", summary="Create an expert team")
async def create_team(
    body: TeamCreateBody,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    teams = _teams(server)
    _validate_team_audience(server, body)
    member_ids = teams.validate_member_ids(user, body.member_ids)
    assert server.app_runtime is not None
    from octop.infra.agents.workspace.dir import apply_explicit_workspace_dir  # noqa: PLC0415

    config = dict(body.config)
    raw_workspace = config.pop("workspace_dir", None)
    apply_explicit_workspace_dir(
        config,
        raw_workspace if isinstance(raw_workspace, str) else None,
    )
    spec = AgentCreateSpec(
        name=body.name.strip(),
        agent_id=(body.agent_id or "").strip() or None,
        user_id=user.id,
        description=body.description,
        default_model=body.default_model,
        color=body.color,
        icon_name=body.icon_name or "users",
        icon_url=team_icon_url(body.icon_url),
        welcome_message=body.welcome_message,
        template_name=TEAM_TEMPLATE_NAME,
        kind=TEAM_KIND,
        config=config,
        member_ids=member_ids,
        mcp_servers=[],
    )
    row = await server.app_runtime.agent_registry.create(spec)
    if body.visibility is not None or body.is_shared:
        row = await apply_agent_audience(
            server,
            row.agent_id,
            visibility=body.visibility,
            group_ids=body.group_ids,
            shared=body.is_shared,
        )
    saved = server.app_runtime.agent_registry.get_row(row.agent_id) or row
    return cast(dict[str, Any], teams.team_payload(saved, viewer_user_id=user.id))


@router.get("/teams/template", summary="Preview default team workspace files")
async def team_template_files(
    _user: Any = Depends(current_user),
) -> list[dict[str, str]]:
    files: list[dict[str, str]] = []
    if TEMPLATE_DIR.is_dir():
        for path in sorted(TEMPLATE_DIR.iterdir()):
            if path.is_file() and path.suffix.lower() == ".md" and not path.name.startswith("."):
                files.append(
                    {
                        "name": path.name,
                        "content": path.read_text(encoding="utf-8"),
                    }
                )
    return files


@router.get("/teams/{team_id}", summary="Get an expert team")
async def get_team(
    team_id: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    row = _require_visible_team(server, user, team_id)
    return cast(dict[str, Any], _teams(server).team_payload(row, viewer_user_id=user.id))


@router.patch("/teams/{team_id}", summary="Update an expert team")
async def patch_team(
    team_id: str,
    body: TeamPatchBody,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    _require_owned_team(server, user, team_id)
    _validate_team_audience(server, body)
    teams = _teams(server)
    assert server.app_runtime is not None
    roster_changed = False
    if body.member_ids is not None:
        next_ids = teams.validate_member_ids(user, body.member_ids)
        teams.assert_roster_writable(team_id, next_ids)
        teams.replace_members(team_id, next_ids)
        roster_changed = True
    updates: dict[str, Any] = {}
    if body.name is not None:
        updates["name"] = body.name.strip()
    if body.description is not None:
        updates["description"] = body.description
    if body.default_model is not None:
        updates["default_model"] = body.default_model
    if body.color is not None:
        updates["color"] = body.color
    if body.icon_name is not None:
        updates["icon_name"] = body.icon_name
    if "icon_url" in body.model_fields_set:
        updates["icon_url"] = team_icon_url(body.icon_url)
    if body.welcome_message is not None:
        updates["welcome_message"] = body.welcome_message
    if updates:
        await server.app_runtime.agent_registry.update(team_id, **updates)
    if roster_changed:
        await server.app_runtime.agent_registry.reload(team_id)
    if "visibility" in body.model_fields_set or "is_shared" in body.model_fields_set:
        await apply_agent_audience(
            server,
            team_id,
            visibility=body.visibility,
            group_ids=body.group_ids,
            shared=body.is_shared,
        )
    row = server.app_runtime.agent_registry.get_row(team_id)
    if row is None:
        raise OctopError(ErrorCode.TEAM_NOT_FOUND, f"team {team_id!r} not found")
    return cast(dict[str, Any], teams.team_payload(row, viewer_user_id=user.id))


@router.delete("/teams/{team_id}", status_code=204, summary="Delete an expert team")
async def delete_team(
    team_id: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> None:
    _require_owned_team(server, user, team_id)
    assert server.app_runtime is not None
    await server.app_runtime.agent_registry.delete(team_id)
