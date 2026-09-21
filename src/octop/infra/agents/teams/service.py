"""Team roster rules and host-expert helpers."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from octop.infra.agents.teams.jobs import TeamJobTracker
from octop.infra.agents.tool_catalog import BUILTIN_TOOL_CATALOG
from octop.infra.db.repos.agents import AgentRow
from octop.infra.db.services import RepoBundle
from octop.infra.errors import ErrorCode, OctopError

TEAM_KIND = "team"
EXPERT_KIND = "expert"
TEAM_TEMPLATE_NAME = "team-host"
TEAM_MIN_MEMBERS = 2
TEAM_AVATAR_URL = "/experts/avatars/team-host.svg"
TEMPLATE_DIR = Path(__file__).resolve().parent / "template"
TEAM_MANIFEST_WORKSPACE = ".octop/manifest.json"

# Hosts only dispatch and keep light memory/time — members do the work.
HOST_TOOLS_ALLOWED: frozenset[str] = frozenset(
    {
        "agent_list",
        "ask_agent",
        "memory_search",
        "memory_get",
        "current_time",
    }
)

HOST_TOOLS_DISABLED: frozenset[str] = frozenset(
    entry.name for entry in BUILTIN_TOOL_CATALOG if entry.name not in HOST_TOOLS_ALLOWED
)


def host_tools_disabled(extra: frozenset[str] | set[str] | tuple[str, ...] = ()) -> frozenset[str]:
    """Denylist for a team host: catalog minus the dispatch allowlist."""
    return frozenset(extra) | HOST_TOOLS_DISABLED


def agent_kind(row: AgentRow | None) -> str:
    if row is None:
        return EXPERT_KIND
    kind = getattr(row, "kind", None) or EXPERT_KIND
    return TEAM_KIND if kind == TEAM_KIND else EXPERT_KIND


def is_team_agent(row: AgentRow | None) -> bool:
    return agent_kind(row) == TEAM_KIND


_LEGACY_TEAM_AVATARS = frozenset(
    {
        "/experts/avatars/multi-agent-orchestrator.svg",
    }
)


def team_icon_url(stored: str | None) -> str:
    """Public team portrait; bundled cartoon when none is stored."""
    text = str(stored or "").strip()
    if not text or text in _LEGACY_TEAM_AVATARS:
        return TEAM_AVATAR_URL
    return text


def _user_may_use_member(row: AgentRow, user: Any) -> bool:
    if getattr(user, "is_admin", False):
        return True
    if row.user_id is not None and row.user_id == getattr(user, "id", None):
        return True
    return int(getattr(row, "is_shared", 0) or 0) == 1


def _normalize_member_ids(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for item in raw:
        member_id = str(item or "").strip()
        if not member_id or member_id in seen:
            continue
        seen.add(member_id)
        out.append(member_id)
    return out


def _member_ids_from_manifest(data: dict[str, Any]) -> list[str]:
    return _normalize_member_ids(data.get("members") or data.get("member"))


async def _read_workspace_manifest(workspace: Any) -> dict[str, Any]:
    reader = getattr(workspace, "aread_text", None)
    if reader is None:
        return {}
    try:
        text = await reader(TEAM_MANIFEST_WORKSPACE)
    except Exception:
        return {}
    if not text or not str(text).strip():
        return {}
    try:
        data = json.loads(str(text))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


class TeamService:
    def __init__(
        self,
        repos: RepoBundle,
        jobs: TeamJobTracker | None = None,
        workspace_for: Callable[[str], Any] | None = None,
    ) -> None:
        self._repos = repos
        self.jobs = jobs or TeamJobTracker()
        self._workspace_for = workspace_for

    def _workspace(self, team_agent_id: str) -> Any | None:
        if self._workspace_for is None:
            return None
        try:
            return self._workspace_for(team_agent_id)
        except (OSError, TypeError, ValueError):
            return None

    def _read_manifest(self, team_agent_id: str) -> dict[str, Any]:
        workspace = self._workspace(team_agent_id)
        if workspace is None:
            return {}
        reader = getattr(workspace, "read_text", None)
        if reader is None:
            return {}
        try:
            text = reader(TEAM_MANIFEST_WORKSPACE)
        except Exception:
            return {}
        if not text or not str(text).strip():
            return {}
        try:
            data = json.loads(str(text))
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def _write_manifest(self, team_agent_id: str, member_ids: list[str]) -> None:
        workspace = self._workspace(team_agent_id)
        writer = getattr(workspace, "write_text", None) if workspace is not None else None
        if workspace is None or writer is None:
            raise OctopError(
                ErrorCode.AGENT_NOT_FOUND,
                f"workspace missing for team {team_agent_id!r}",
                details={"team_agent_id": team_agent_id},
            )
        data = dict(self._read_manifest(team_agent_id))
        data["kind"] = TEAM_KIND
        data["members"] = list(member_ids)
        content = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        try:
            writer(TEAM_MANIFEST_WORKSPACE, content, force=True)
        except TypeError:
            writer(TEAM_MANIFEST_WORKSPACE, content)

    def member_ids(self, team_agent_id: str) -> list[str]:
        return _member_ids_from_manifest(self._read_manifest(team_agent_id))

    def visible_member_ids(self, team_agent_id: str) -> list[str]:
        """Persisted roster minus deleted / team-host ids. Does not rewrite disk."""
        out: list[str] = []
        for member_id in self.member_ids(team_agent_id):
            row = self._repos.agent_repo.get(member_id)
            if row is None or is_team_agent(row):
                continue
            out.append(member_id)
        return out

    def validate_member_ids(self, user: Any, member_ids: list[str]) -> list[str]:
        """Treat *member_ids* as the complete next roster, not incremental adds.

        Missing, unusable, or team-host ids raise ``TEAM_MEMBER_INVALID``.
        Fewer than ``TEAM_MIN_MEMBERS`` usable experts is ``TEAM_MEMBERS_TOO_FEW``.
        """
        seen: set[str] = set()
        out: list[str] = []
        invalid: list[str] = []
        for raw in member_ids:
            member_id = str(raw or "").strip()
            if not member_id or member_id in seen:
                continue
            seen.add(member_id)
            row = self._repos.agent_repo.get(member_id)
            if row is None or is_team_agent(row) or not _user_may_use_member(row, user):
                invalid.append(member_id)
                continue
            out.append(member_id)
        if invalid:
            raise OctopError(
                ErrorCode.TEAM_MEMBER_INVALID,
                "one or more team members cannot be used",
                details={"member_agent_ids": invalid},
            )
        if len(out) < TEAM_MIN_MEMBERS:
            raise OctopError(
                ErrorCode.TEAM_MEMBERS_TOO_FEW,
                f"a team needs at least {TEAM_MIN_MEMBERS} members",
                details={"min_members": TEAM_MIN_MEMBERS},
            )
        return out

    def assert_roster_writable(
        self,
        team_agent_id: str,
        next_member_ids: list[str],
    ) -> None:
        current = set(self.member_ids(team_agent_id))
        removed = current - set(next_member_ids)
        busy = self.jobs.busy_member_ids(team_agent_id)
        blocked = sorted(removed & busy)
        if blocked:
            raise OctopError(
                ErrorCode.TEAM_MEMBER_BUSY,
                "cannot remove a member with an in-flight team job",
                details={"member_agent_ids": blocked},
            )

    def assert_can_delete_agent(self, agent_id: str) -> None:
        row = self._repos.agent_repo.get(agent_id)
        if row is None:
            raise OctopError(ErrorCode.AGENT_NOT_FOUND, f"agent {agent_id!r} not found")
        if is_team_agent(row):
            busy = self.jobs.busy_member_ids(agent_id)
            if busy:
                raise OctopError(
                    ErrorCode.TEAM_MEMBER_BUSY,
                    "cannot delete a team while members have in-flight jobs",
                    details={"member_agent_ids": sorted(busy)},
                )
            return
        if self.jobs.is_member_busy(agent_id):
            raise OctopError(
                ErrorCode.TEAM_MEMBER_BUSY,
                "cannot delete an expert with an in-flight team job",
                details={"member_agent_id": agent_id},
            )

    def replace_members(self, team_agent_id: str, member_ids: list[str]) -> None:
        self._write_manifest(team_agent_id, list(member_ids))

    def drop_member(self, member_id: str) -> list[str]:
        """Remove an expert from every team roster. Returns changed team ids."""
        target = str(member_id or "").strip()
        if not target:
            return []
        changed: list[str] = []
        for row in self._repos.agent_repo.list_all():
            if not is_team_agent(row):
                continue
            current = self.member_ids(row.agent_id)
            if target not in current:
                continue
            self.replace_members(row.agent_id, [item for item in current if item != target])
            changed.append(row.agent_id)
        return changed

    def team_payload(self, row: AgentRow) -> dict[str, Any]:
        ids = self.visible_member_ids(row.agent_id)
        member_rows = [self._repos.agent_repo.get(member_id) for member_id in ids]
        return {
            "team_id": row.agent_id,
            "agent_id": row.agent_id,
            "name": row.name,
            "description": row.description,
            "default_model": row.default_model,
            "color": row.color,
            "icon_name": row.icon_name,
            "icon_url": team_icon_url(row.icon_url),
            "welcome_message": row.welcome_message,
            "state": row.last_state or "unknown",
            "kind": TEAM_KIND,
            "member_ids": ids,
            "members": [
                {
                    "agent_id": member.agent_id,
                    "name": member.name,
                    "color": member.color,
                    "icon_name": member.icon_name,
                    "icon_url": member.icon_url,
                    "state": member.last_state or "unknown",
                    "is_shared": bool(int(member.is_shared or 0)),
                    "user_id": member.user_id,
                }
                for member in member_rows
                if member is not None
            ],
        }

    def list_for_user(self, user_id: int) -> list[dict[str, Any]]:
        return [
            self.team_payload(row)
            for row in self._repos.agent_repo.list_by_user(user_id)
            if is_team_agent(row)
        ]


async def seed_team_template(
    workspace: Any,
    *,
    member_ids: list[str] | None = None,
) -> None:
    pairs: list[tuple[str, bytes]] = []
    if not TEMPLATE_DIR.is_dir():
        return
    roster = _normalize_member_ids(member_ids) if member_ids is not None else None
    if roster is None:
        existing = await _read_workspace_manifest(workspace)
        if existing:
            roster = _member_ids_from_manifest(existing)
    for path in sorted(TEMPLATE_DIR.iterdir()):
        if not path.is_file() or path.name.startswith("."):
            continue
        if path.name == "manifest.json":
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                data = {}
            if not isinstance(data, dict):
                data = {}
            data["kind"] = TEAM_KIND
            if roster is not None:
                data["members"] = roster
            else:
                data.setdefault("members", [])
            pairs.append(
                (
                    TEAM_MANIFEST_WORKSPACE,
                    (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
                )
            )
            continue
        pairs.append((path.name, path.read_bytes()))
    if pairs:
        await workspace.aupload_many(pairs)
