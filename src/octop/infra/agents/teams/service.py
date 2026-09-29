"""Team roster rules and host-expert helpers."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from octop.infra.agents.access import user_may_access_agent
from octop.infra.agents.settings.tool_catalog import BUILTIN_TOOL_CATALOG
from octop.infra.agents.teams.jobs import TeamJobTracker
from octop.infra.agents.teams.pipeline import DEFAULT_TIER, RosterTrim, trim_roster
from octop.infra.agents.teams.pipeline import ROLES as _PIPELINE_ROLES
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

#: The twelve fixed role ids — forwarded from ``pipeline.ROLES`` (its docstring declares
#: that tuple the single authority for the role vocabulary; never re-list it here).
TEAM_ROLES: frozenset[str] = frozenset(_PIPELINE_ROLES)

#: ``manifest.json · lead_agent_id`` — ``None`` means the team host chairs the run itself.
MANIFEST_LEAD_KEY = "lead_agent_id"

#: Sentinel for "leave ``lead_agent_id`` untouched" (a caller may legitimately set ``None``).
_UNSET: Any = object()

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


#: 「这个专家能不能被编进团队」的判定 = **admin ｜ 本人 ｜ 已共享**。
#:
#: 这是 ``infra/agents/access.py`` 那条**可访问**规则（:func:`user_may_access_agent`）的
#: **转发**，不是第二份实现 —— 原先这里有一份逐字相同的拷贝（``admin | 本人 | is_shared``），
#: 而 ``api/common/agent.py`` 里还有另一份；两处同名不同命，正是"同一事实两份定义"的形状。
#:
#: ⚠️ 它与 :func:`octop.infra.agents.access.assert_agent_owner` **不同**（后者**不认**
#: ``is_shared``）：**能不能用这个专家当成员** ≠ **能不能改这个 agent**。不要为了"统一"
#: 把这条换成更窄的归属判定（会打死共享专家编队），也不要把共享旁路加到写权限上。
_user_may_use_member = user_may_access_agent


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


def _normalize_roster(raw: Any) -> list[dict[str, Any]]:
    """Normalize ``manifest.json · members`` into AM-1's ``[{"agent_id", "role"}]``.

    **Both shapes are accepted** (T-32 ②：必须兼容读旧形状):
    a bare agent id (legacy ``["a", "b"]``) reads as ``role=None``; the AM-1 object
    shape carries the role. Duplicates and blank ids are dropped, order is kept.
    """
    if not isinstance(raw, list):
        return []
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in raw:
        role: str | None = None
        if isinstance(item, Mapping):
            member_id = str(item.get("agent_id") or "").strip()
            raw_role = item.get("role")
            if raw_role is not None:
                role = str(raw_role).strip() or None
        else:
            member_id = str(item or "").strip()
        if not member_id or member_id in seen:
            continue
        seen.add(member_id)
        out.append({"agent_id": member_id, "role": role})
    return out


def _roster_from_manifest(data: dict[str, Any]) -> list[dict[str, Any]]:
    return _normalize_roster(data.get("members") or data.get("member"))


def _member_ids_from_manifest(data: dict[str, Any]) -> list[str]:
    return [member["agent_id"] for member in _roster_from_manifest(data)]


def _lead_from_manifest(data: dict[str, Any]) -> str | None:
    raw = data.get(MANIFEST_LEAD_KEY)
    lead = str(raw).strip() if raw is not None else ""
    return lead or None


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

    def _write_manifest(
        self,
        team_agent_id: str,
        members: list[Any],
        *,
        lead_agent_id: Any = _UNSET,
    ) -> None:
        """**The only writer** of ``.octop/manifest.json`` (T-32 ②: no second writer).

        ``members`` may be bare agent ids (legacy call sites: ``replace_members`` /
        ``drop_member``) or ``{"agent_id", "role"}`` objects. Bare ids **keep the role
        already recorded** for that member, so a rename-only PATCH cannot silently
        downgrade the roster back to the legacy shape. ``lead_agent_id`` is only
        written when explicitly passed (``None`` = host chairs, which is a real value).
        """
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
        known_roles = {m["agent_id"]: m["role"] for m in _roster_from_manifest(data)}
        roster: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in members:
            if isinstance(item, Mapping):
                member_id = str(item.get("agent_id") or "").strip()
                raw_role = item.get("role")
                role = None
                if raw_role is not None:
                    role = str(raw_role).strip() or None
                if role is None:
                    role = known_roles.get(member_id)
            else:
                member_id = str(item or "").strip()
                role = known_roles.get(member_id)
            if not member_id or member_id in seen:
                continue
            seen.add(member_id)
            roster.append({"agent_id": member_id, "role": role})
        data["members"] = roster
        if lead_agent_id is not _UNSET:
            lead_text = str(lead_agent_id or "").strip()
            data[MANIFEST_LEAD_KEY] = lead_text or None
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

    def roster(self, team_agent_id: str) -> dict[str, Any]:
        """Team-level roster = ``manifest.json`` (AM-1 唯一权威). Reads **both** shapes."""
        data = self._read_manifest(team_agent_id)
        return {
            MANIFEST_LEAD_KEY: _lead_from_manifest(data),
            "members": _roster_from_manifest(data),
        }

    def replace_roster(
        self,
        team_agent_id: str,
        members: list[Any],
        *,
        lead_agent_id: Any = _UNSET,
    ) -> dict[str, Any]:
        """Validate then persist a whole roster through the single writer.

        ``members`` items are ``{"agent_id", "role"}`` (or bare ids). Roles must be in
        the twelve-role closed set — anything else is ``TEAM_ROLE_UNKNOWN`` (400, reused
        code: **no new ErrorCode**, T-32). Member ids go through
        :meth:`validate_member_ids` (``TEAM_MEMBER_INVALID`` / ``TEAM_MEMBERS_TOO_FEW``).
        """
        normalized = _normalize_roster(members)
        unknown = sorted(
            {m["role"] for m in normalized if m["role"] and m["role"] not in TEAM_ROLES}
        )
        if unknown:
            raise OctopError(
                ErrorCode.TEAM_ROLE_UNKNOWN,
                "one or more roles are not in the fixed role table",
                details={"roles": unknown, "allowed": sorted(TEAM_ROLES)},
            )
        next_members = [{"agent_id": m["agent_id"], "role": m["role"]} for m in normalized]
        member_ids = [m["agent_id"] for m in next_members]
        if lead_agent_id is not _UNSET and lead_agent_id is not None:
            lead = str(lead_agent_id).strip()
            if lead and lead not in set(member_ids):
                raise OctopError(
                    ErrorCode.TEAM_MEMBER_INVALID,
                    "lead_agent_id must be one of the team members",
                    details={"lead_agent_id": lead},
                )
        self._write_manifest(team_agent_id, next_members, lead_agent_id=lead_agent_id)
        return self.roster(team_agent_id)

    def trimmed_roster(
        self,
        team_agent_id: str,
        tier: object = DEFAULT_TIER,
        *,
        host_agent_id: str | None = None,
    ) -> RosterTrim:
        """Apply the tier cap to the manifest roster (AM-1 ③).

        Delegates to ``pipeline.trim_roster`` — the single implementation of the four
        priority rules — so the cut roles stay visible via
        :attr:`RosterTrim.skipped_roles` and callers can persist them into
        ``gate_detail.skipped_roles``. **Cutting is the default behaviour and is not an
        error** (only an explicit over-cap ``roles?`` request is).
        """
        current = self.roster(team_agent_id)
        return trim_roster(
            current["members"],
            tier,
            lead_agent_id=current[MANIFEST_LEAD_KEY],
            host_agent_id=host_agent_id,
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
                data["members"] = [{"agent_id": member_id, "role": None} for member_id in roster]
            else:
                data["members"] = _roster_from_manifest(data)
            data.setdefault(MANIFEST_LEAD_KEY, None)
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
