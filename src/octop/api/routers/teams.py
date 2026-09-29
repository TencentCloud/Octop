"""Expert teams — create, list, update roster."""

from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from octop.api.common.agent import assert_agent_owner
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

router = APIRouter()

#: Sentinel meaning "``lead_agent_id`` was omitted ⇒ leave the stored lead untouched".
_ROSTER_LEAD_UNSET: Any = object()


class TeamCreateBody(BaseModel):
    name: str
    description: str | None = None
    default_model: str | None = None
    color: str | None = None
    icon_name: str | None = None
    icon_url: str | None = None
    welcome_message: str | None = None
    member_ids: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)


class TeamPatchBody(BaseModel):
    name: str | None = None
    description: str | None = None
    default_model: str | None = None
    color: str | None = None
    icon_name: str | None = None
    welcome_message: str | None = None
    member_ids: list[str] | None = None


class RosterMember(BaseModel):
    """One roster row — AM-1 shape (``role`` is one of the twelve fixed ids)."""

    agent_id: str
    role: str | None = None


class TeamRosterBody(BaseModel):
    """``PUT /teams/{team_id}/roster``.

    ``lead_agent_id`` omitted ⇒ leave the stored lead untouched; explicit ``null`` ⇒
    the team host chairs the run itself.
    """

    members: list[RosterMember] = Field(default_factory=list)
    lead_agent_id: str | None = None
    clear_lead: bool = False


def _teams(server: Any) -> Any:
    assert server.app_runtime is not None
    return server.app_runtime.agent_registry.teams


def _require_owned_team(server: Any, user: Any, team_id: str) -> Any:
    assert server.app_runtime is not None
    row = server.app_runtime.agent_registry.get_row(team_id)
    if row is None or not is_team_agent(row):
        raise OctopError(ErrorCode.TEAM_NOT_FOUND, f"team {team_id!r} not found")
    assert_agent_owner(row, user)
    return row


@router.get("/teams", summary="List my expert teams")
async def list_teams(
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], _teams(server).list_for_user(user.id))


@router.post("/teams", summary="Create an expert team")
async def create_team(
    body: TeamCreateBody,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    teams = _teams(server)
    member_ids = teams.validate_member_ids(user, body.member_ids)
    assert server.app_runtime is not None
    spec = AgentCreateSpec(
        name=body.name.strip(),
        user_id=user.id,
        description=body.description,
        default_model=body.default_model,
        color=body.color,
        icon_name=body.icon_name or "users",
        icon_url=team_icon_url(body.icon_url),
        welcome_message=body.welcome_message,
        template_name=TEAM_TEMPLATE_NAME,
        kind=TEAM_KIND,
        config=body.config,
        member_ids=member_ids,
        mcp_servers=[],
    )
    row = await server.app_runtime.agent_registry.create(spec)
    return cast(
        dict[str, Any],
        teams.team_payload(server.app_runtime.agent_registry.get_row(row.agent_id) or row),
    )


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
    row = _require_owned_team(server, user, team_id)
    return cast(dict[str, Any], _teams(server).team_payload(row))


@router.patch("/teams/{team_id}", summary="Update an expert team")
async def patch_team(
    team_id: str,
    body: TeamPatchBody,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    _require_owned_team(server, user, team_id)
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
    if body.welcome_message is not None:
        updates["welcome_message"] = body.welcome_message
    if updates:
        await server.app_runtime.agent_registry.update(team_id, **updates)
    if roster_changed:
        await server.app_runtime.agent_registry.reload(team_id)
    row = server.app_runtime.agent_registry.get_row(team_id)
    if row is None:
        raise OctopError(ErrorCode.TEAM_NOT_FOUND, f"team {team_id!r} not found")
    return cast(dict[str, Any], teams.team_payload(row))


@router.get("/teams/{team_id}/roster", summary="Get the team roster")
async def get_team_roster(
    team_id: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Read the team-level roster from the team host's ``.octop/manifest.json``.

    That file is the **single authority** for "who is in this team" (AM-1); this route
    never reads a second store. Legacy manifests with bare member ids still load
    (their role reads as ``null``).
    """
    _require_owned_team(server, user, team_id)
    return cast(dict[str, Any], _teams(server).roster(team_id))


@router.put("/teams/{team_id}/roster", summary="Replace the team roster")
async def put_team_roster(
    team_id: str,
    body: TeamRosterBody,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Replace the whole roster (not incremental adds) and reload the team.

    An unknown role is ``400 TEAM_ROLE_UNKNOWN``; an unusable member id is
    ``400 TEAM_MEMBER_INVALID``; fewer than ``TEAM_MIN_MEMBERS`` usable experts is
    ``400 TEAM_MEMBERS_TOO_FEW``. In-flight members cannot be dropped
    (``TEAM_MEMBER_BUSY``). No new error codes: every rejection reuses an existing one.
    """
    _require_owned_team(server, user, team_id)
    teams = _teams(server)
    members_payload = [member.model_dump() for member in body.members]
    next_ids = [str(member.agent_id or "").strip() for member in body.members]
    teams.assert_roster_writable(team_id, teams.validate_member_ids(user, next_ids))
    lead: Any = (
        None
        if body.clear_lead
        else (body.lead_agent_id if body.lead_agent_id is not None else _ROSTER_LEAD_UNSET)
    )
    roster = teams.replace_roster(team_id, members_payload, lead_agent_id=lead)
    assert server.app_runtime is not None
    await server.app_runtime.agent_registry.reload(team_id)
    return cast(dict[str, Any], roster)


@router.delete("/teams/{team_id}", status_code=204, summary="Delete an expert team")
async def delete_team(
    team_id: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> None:
    _require_owned_team(server, user, team_id)
    assert server.app_runtime is not None
    await server.app_runtime.agent_registry.delete(team_id)
