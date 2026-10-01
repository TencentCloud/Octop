"""Team roster validation and in-flight locks."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from octop.infra.agents.teams import (
    TEAM_AVATAR_URL,
    TEAM_MIN_MEMBERS,
    TeamJobTracker,
    TeamService,
    team_icon_url,
)
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.db.services import RepoBundle
from octop.infra.errors import ErrorCode, OctopError


class _PathWorkspace:
    """Duck-typed BackendWorkspace for roster tests (sync read/write)."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def read_text(self, path: str, *, limit: int = 10_000_000) -> str | None:
        target = self.root / path
        if not target.is_file():
            return None
        return target.read_text(encoding="utf-8")

    def write_text(self, path: str, content: str, *, force: bool = False) -> None:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


@pytest.fixture
def team_env(tmp_path: Path) -> dict[str, object]:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    users = UserRepo(db)
    users.create(username="owner", password_hash="h", role="user")
    agents = AgentRepo(db)
    agents.create(agent_id="host", user_id=1, name="Host", kind="team")
    agents.create(agent_id="a", user_id=1, name="Alpha")
    agents.create(agent_id="b", user_id=1, name="Beta")
    agents.create(agent_id="c", user_id=1, name="Gamma")
    agents.create(agent_id="other-team", user_id=1, name="Nested", kind="team")
    repos = RepoBundle.from_pool(db)
    jobs = TeamJobTracker()
    workspaces = tmp_path / "workspaces"

    def workspace_for(agent_id: str) -> _PathWorkspace:
        return _PathWorkspace(workspaces / agent_id)

    return {
        "db": db,
        "repos": repos,
        "teams": TeamService(repos, jobs, workspace_for=workspace_for),
        "jobs": jobs,
        "user": SimpleNamespace(id=1, is_admin=False),
        "agents": agents,
        "workspace_for": workspace_for,
    }


def test_validate_members_requires_two(team_env: dict[str, object]) -> None:
    teams = team_env["teams"]
    user = team_env["user"]
    assert isinstance(teams, TeamService)
    with pytest.raises(OctopError) as exc:
        teams.validate_member_ids(user, ["a"])
    assert exc.value.code is ErrorCode.TEAM_MEMBERS_TOO_FEW
    assert TEAM_MIN_MEMBERS == 2
    assert teams.validate_member_ids(user, ["a", "b"]) == ["a", "b"]


def test_validate_members_rejects_unusable(team_env: dict[str, object]) -> None:
    teams = team_env["teams"]
    user = team_env["user"]
    assert isinstance(teams, TeamService)
    with pytest.raises(OctopError) as exc:
        teams.validate_member_ids(user, ["a", "other-team", "b", "missing"])
    assert exc.value.code is ErrorCode.TEAM_MEMBER_INVALID
    assert exc.value.details == {"member_agent_ids": ["other-team", "missing"]}
    with pytest.raises(OctopError) as exc:
        teams.validate_member_ids(user, ["a"])
    assert exc.value.code is ErrorCode.TEAM_MEMBERS_TOO_FEW
    assert teams.validate_member_ids(user, ["a", "b"]) == ["a", "b"]


def test_roster_lock_blocks_remove_and_delete(team_env: dict[str, object]) -> None:
    teams = team_env["teams"]
    jobs = team_env["jobs"]
    assert isinstance(teams, TeamService)
    assert isinstance(jobs, TeamJobTracker)
    teams.replace_members("host", ["a", "b"])
    jobs.begin("host", "a")
    with pytest.raises(OctopError) as exc:
        teams.assert_roster_writable("host", ["b", "c"])
    assert exc.value.code is ErrorCode.TEAM_MEMBER_BUSY
    with pytest.raises(OctopError) as exc:
        teams.assert_can_delete_agent("a")
    assert exc.value.code is ErrorCode.TEAM_MEMBER_BUSY
    jobs.end("host", "a")
    teams.assert_roster_writable("host", ["b", "c"])
    teams.assert_can_delete_agent("a")


def test_job_id_begin_end_is_idempotent(team_env: dict[str, object]) -> None:
    jobs = team_env["jobs"]
    assert isinstance(jobs, TeamJobTracker)
    jobs.begin("host", "a", job_id="job-1")
    jobs.begin("host", "a", job_id="job-1")
    assert jobs.is_busy("host", "a")
    jobs.end("host", "a", job_id="job-1")
    jobs.end("host", "a", job_id="job-1")
    assert not jobs.is_busy("host", "a")
    assert not jobs.is_member_busy("a")


def test_drop_member_rewrites_every_team_roster(team_env: dict[str, object]) -> None:
    teams = team_env["teams"]
    workspace_for = team_env["workspace_for"]
    assert isinstance(teams, TeamService)
    workspace_for("other-team")
    teams.replace_members("host", ["a", "b", "c"])
    teams.replace_members("other-team", ["a", "c"])
    assert teams.drop_member("a") == ["host", "other-team"]
    assert teams.member_ids("host") == ["b", "c"]
    assert teams.member_ids("other-team") == ["c"]
    assert teams.drop_member("missing") == []


def test_roster_lives_in_workspace_manifest(team_env: dict[str, object]) -> None:
    teams = team_env["teams"]
    workspace_for = team_env["workspace_for"]
    assert isinstance(teams, TeamService)
    teams.replace_members("host", ["a", "b"])
    assert teams.member_ids("host") == ["a", "b"]
    raw = workspace_for("host").read_text(".octop/manifest.json")
    assert raw is not None
    manifest = json.loads(raw)
    assert manifest["kind"] == "team"
    assert manifest["members"] == ["a", "b"]
    listed = teams.list_for_user(1)
    assert [item["agent_id"] for item in listed] == ["host", "other-team"]
    assert listed[0]["member_ids"] == ["a", "b"]
    assert [item["agent_id"] for item in listed[0]["members"]] == ["a", "b"]
    teams.replace_members("host", ["a", "missing", "other-team", "b"])
    assert teams.member_ids("host") == ["a", "missing", "other-team", "b"]
    assert teams.visible_member_ids("host") == ["a", "b"]
    host = team_env["agents"].get("host")
    assert host is not None
    assert teams.team_payload(host)["member_ids"] == ["a", "b"]
    assert teams.team_payload(host)["icon_url"] == TEAM_AVATAR_URL


def test_team_icon_url_falls_back_to_cartoon() -> None:
    assert team_icon_url(None) == TEAM_AVATAR_URL
    assert team_icon_url("  ") == TEAM_AVATAR_URL
    assert team_icon_url("/experts/avatars/multi-agent-orchestrator.svg") == TEAM_AVATAR_URL
    assert team_icon_url("/custom.png") == "/custom.png"


@pytest.mark.asyncio
async def test_seed_team_template_writes_octop_manifest() -> None:
    from octop.infra.agents.teams.service import seed_team_template

    uploaded: dict[str, bytes] = {}

    class _Workspace:
        async def aupload_many(self, pairs: list[tuple[str, bytes]]) -> None:
            uploaded.update(pairs)

        async def aread_text(self, rel: str) -> str | None:
            raw = uploaded.get(rel)
            return raw.decode("utf-8") if raw is not None else None

    await seed_team_template(_Workspace(), member_ids=["a", "b"])
    assert "AGENTS.md" in uploaded
    raw = uploaded[".octop/manifest.json"]
    data = json.loads(raw.decode("utf-8"))
    assert data["kind"] == "team"
    assert data["members"] == ["a", "b"]
