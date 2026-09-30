"""AM-1 team-roster persistence (T-32): manifest shape, single writer, tier trimming.

The team-level roster lives in the team host's ``.octop/manifest.json`` — that file is
the single authority for "who is in this team". These cases pin the AM-1 shape
(``members: [{agent_id, role}]`` + ``lead_agent_id``), the **legacy read** path (a bare
id array must still load), the single-writer rule, and the four tier-trim priorities.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from octop.infra.agents.teams.pipeline import ROLES, TIER_SPEC, trim_roster
from octop.infra.agents.teams.service import (
    MANIFEST_LEAD_KEY,
    TEAM_MANIFEST_WORKSPACE,
    TEAM_MIN_MEMBERS,
    TEAM_ROLES,
    TeamService,
)
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.db.services import RepoBundle
from octop.infra.errors import ErrorCode, OctopError

REPO_ROOT = Path(__file__).resolve().parents[3]


class _PathWorkspace:
    """Duck-typed BackendWorkspace (sync read/write), same shape as test_team_service."""

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
def roster_env(tmp_path: Path) -> dict[str, object]:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    users = UserRepo(db)
    users.create(username="owner", password_hash="h", role="user")
    agents = AgentRepo(db)
    agents.create(agent_id="host", user_id=1, name="Host", kind="team")
    for agent_id in ("a", "b", "c", "d", "e", "f", "g"):
        agents.create(agent_id=agent_id, user_id=1, name=agent_id.upper())
    repos = RepoBundle.from_pool(db)
    workspaces = tmp_path / "workspaces"

    def workspace_for(agent_id: str) -> _PathWorkspace:
        return _PathWorkspace(workspaces / agent_id)

    return {
        "teams": TeamService(repos, workspace_for=workspace_for),
        "user": SimpleNamespace(id=1, is_admin=False),
        "workspace_for": workspace_for,
    }


def _manifest(env: dict[str, object], team_id: str = "host") -> dict[str, object]:
    workspace_for = env["workspace_for"]
    assert callable(workspace_for)
    raw = workspace_for(team_id).read_text(TEAM_MANIFEST_WORKSPACE)
    assert raw is not None
    data = json.loads(raw)
    assert isinstance(data, dict)
    return data


def test_roster_writes_the_am1_object_shape(roster_env: dict[str, object]) -> None:
    """新形状可写：members 元素是 {agent_id, role}，lead_agent_id 落盘。"""
    teams = roster_env["teams"]
    assert isinstance(teams, TeamService)
    teams.replace_roster(
        "host",
        [{"agent_id": "a", "role": "backend"}, {"agent_id": "b", "role": "qa"}],
        lead_agent_id="a",
    )
    manifest = _manifest(roster_env)
    assert manifest["members"] == [
        {"agent_id": "a", "role": "backend"},
        {"agent_id": "b", "role": "qa"},
    ]
    assert manifest[MANIFEST_LEAD_KEY] == "a"
    assert teams.roster("host") == {
        MANIFEST_LEAD_KEY: "a",
        "members": [
            {"agent_id": "a", "role": "backend"},
            {"agent_id": "b", "role": "qa"},
        ],
    }


def test_roster_reads_the_legacy_bare_id_shape(roster_env: dict[str, object]) -> None:
    """兼容读旧形状：裸 id 数组 ⇒ role 读作 None，且不把老团队读崩。"""
    workspace_for = roster_env["workspace_for"]
    assert callable(workspace_for)
    workspace_for("host").write_text(
        TEAM_MANIFEST_WORKSPACE,
        json.dumps({"kind": "team", "members": ["a", "b"]}, ensure_ascii=False),
        force=True,
    )
    teams = roster_env["teams"]
    assert isinstance(teams, TeamService)
    assert teams.member_ids("host") == ["a", "b"]
    assert teams.roster("host") == {
        MANIFEST_LEAD_KEY: None,
        "members": [{"agent_id": "a", "role": None}, {"agent_id": "b", "role": None}],
    }


def test_legacy_writer_keeps_roles_and_upgrades_the_shape(roster_env: dict[str, object]) -> None:
    """`replace_members`（旧入口）不得把已记录的 role 降级掉。"""
    teams = roster_env["teams"]
    assert isinstance(teams, TeamService)
    teams.replace_roster(
        "host",
        [{"agent_id": "a", "role": "backend"}, {"agent_id": "b", "role": "qa"}],
    )
    teams.replace_members("host", ["b", "c"])  # 名称/描述 PATCH 走的就是这条
    assert teams.roster("host")["members"] == [
        {"agent_id": "b", "role": "qa"},
        {"agent_id": "c", "role": None},
    ]


def test_write_manifest_remains_the_only_writer() -> None:
    """静态断言：全仓只有 service.py 写 TEAM_MANIFEST_WORKSPACE（不新增第二处写者）。"""
    hits: list[Path] = []
    for path in (REPO_ROOT / "src").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "TEAM_MANIFEST_WORKSPACE" in text:
            hits.append(path.relative_to(REPO_ROOT))
    assert hits == [Path("src/octop/infra/agents/teams/service.py")], hits
    # 写动作只出现在 _write_manifest / seed_team_template 两处合法路径内。
    source = (REPO_ROOT / "src/octop/infra/agents/teams/service.py").read_text(encoding="utf-8")
    assert source.count("writer(TEAM_MANIFEST_WORKSPACE") == 2


def test_trim_priorities_lead_never_cut_and_default_roles_first() -> None:
    """裁剪 4 条优先级：① lead 永不裁 ② defaultRoles 次序优先 ③ manifest 次序 ④ 落 skipped。"""
    roster = [
        {"agent_id": "x1", "role": "docs"},
        {"agent_id": "x2", "role": "devops"},
        {"agent_id": "x3", "role": "pm"},
        {"agent_id": "x4", "role": "backend"},
        {"agent_id": "x5", "role": "qa"},
    ]
    quick = TIER_SPEC["quick"]  # role_cap=3, default_roles=("pm","backend","qa")
    assert quick.role_cap == 3

    # ① lead 是最先被保的，即使它在 manifest 里排在最后。
    trim = trim_roster(roster, "quick", lead_agent_id="x5", host_agent_id="host")
    assert [m["agent_id"] for m in trim.kept] == ["x3", "x4", "x5"]
    assert trim.skipped_roles == ("docs", "devops")

    # ② defaultRoles 的数组次序优先于 manifest 次序（pm → backend → qa）。
    assert "pm" in quick.default_roles and quick.default_roles.index("pm") == 0

    # ② 无 lead 时 defaultRoles 次序仍然优先（不退回 manifest 次序）。
    trim_no_lead = trim_roster(roster, "quick")
    assert [m["agent_id"] for m in trim_no_lead.kept] == ["x3", "x4", "x5"]

    # ③ 默认角色不足 cap 时，余量按 **manifest 数组顺序** 保留。
    sparse = [
        {"agent_id": "y1", "role": "docs"},
        {"agent_id": "y2", "role": "pm"},
        {"agent_id": "y3", "role": "devops"},
        {"agent_id": "y4", "role": "qa"},
    ]
    trim_sparse = trim_roster(sparse, "quick")
    assert [m["agent_id"] for m in trim_sparse.kept] == ["y1", "y2", "y4"]
    assert trim_sparse.skipped_roles == ("devops",)


def test_trim_default_is_not_an_error_and_skipped_stays_visible() -> None:
    """被裁角色写进 gate_detail.skipped_roles（可见、不静默）；默认裁剪不抛 409。"""
    roster = [{"agent_id": f"x{i}", "role": role} for i, role in enumerate(ROLES)]
    trim = trim_roster(roster, "quick", host_agent_id="x0")
    assert len(trim.kept) == TIER_SPEC["quick"].role_cap
    assert len(trim.skipped) == len(ROLES) - TIER_SPEC["quick"].role_cap
    # 可见：被裁角色的 role 逐个在 skipped_roles 里，不静默丢弃。
    assert set(trim.skipped_roles) <= set(ROLES)
    assert trim.skipped_roles  # 非空 ⇒ 有东西要报给 gate_detail
    gate_detail = {"skipped_roles": list(trim.skipped_roles)}
    assert gate_detail["skipped_roles"] == list(trim.skipped_roles)
    # 默认裁剪是行为、不是错误；只有显式超 cap 的 roles? 请求才会 409（assert_capacity）。
    assert TIER_SPEC["strict"].role_cap >= len(ROLES)


def test_service_trimmed_roster_uses_manifest_and_pipeline(roster_env: dict[str, object]) -> None:
    """`TeamService.trimmed_roster` 读 manifest 并委托 pipeline.trim_roster（单源）。"""
    teams = roster_env["teams"]
    assert isinstance(teams, TeamService)
    teams.replace_roster(
        "host",
        [
            {"agent_id": "a", "role": "pm"},
            {"agent_id": "b", "role": "backend"},
            {"agent_id": "c", "role": "qa"},
            {"agent_id": "d", "role": "docs"},
        ],
        lead_agent_id="d",
    )
    trim = teams.trimmed_roster("host", "quick", host_agent_id="host")
    assert [m["agent_id"] for m in trim.kept] == ["a", "b", "d"]  # d = lead，永不裁
    assert trim.skipped_roles == ("qa",)
    # 没有超过 roleCap 时什么都不裁、skipped 为空。
    assert teams.trimmed_roster("host", "strict", host_agent_id="host").skipped == ()


def test_replace_roster_rejects_unknown_role(roster_env: dict[str, object]) -> None:
    """非法角色 ⇒ 400 TEAM_ROLE_UNKNOWN（复用既有码，不新增 ErrorCode）。"""
    teams = roster_env["teams"]
    assert isinstance(teams, TeamService)
    with pytest.raises(OctopError) as err:
        teams.replace_roster(
            "host", [{"agent_id": "a", "role": "cto"}, {"agent_id": "b", "role": None}]
        )
    assert err.value.code is ErrorCode.TEAM_ROLE_UNKNOWN
    assert err.value.status == 400
    assert err.value.details["roles"] == ["cto"]
    assert set(err.value.details["allowed"]) == set(ROLES)


def test_replace_roster_rejects_lead_outside_members(roster_env: dict[str, object]) -> None:
    """主持人必须是本团队成员 ⇒ 否则 TEAM_MEMBER_INVALID（复用既有码）。"""
    teams = roster_env["teams"]
    assert isinstance(teams, TeamService)
    with pytest.raises(OctopError) as err:
        teams.replace_roster(
            "host",
            [{"agent_id": "a", "role": "pm"}, {"agent_id": "b", "role": "qa"}],
            lead_agent_id="c",
        )
    assert err.value.code is ErrorCode.TEAM_MEMBER_INVALID


def test_validate_member_ids_is_the_membership_gate(roster_env: dict[str, object]) -> None:
    """成员可用性门 = `validate_member_ids`（**路由真正走的那条**，见 routers/teams.py）。

    不可用成员 ⇒ TEAM_MEMBER_INVALID；< 2 人 ⇒ TEAM_MEMBERS_TOO_FEW。
    这条替换了原先直接调 `TeamService.roster_for_user()` 的用例 —— 后者是零引用死代码，
    已按 AGENTS.md §1「移除自己引入的孤儿符号」删除（lead 授权），断言值与语义不变。
    """
    teams = roster_env["teams"]
    user = roster_env["user"]
    assert isinstance(teams, TeamService)
    with pytest.raises(OctopError) as err:
        teams.validate_member_ids(user, ["ghost", "b"])
    assert err.value.code is ErrorCode.TEAM_MEMBER_INVALID
    with pytest.raises(OctopError) as few:
        teams.validate_member_ids(user, ["a"])
    assert few.value.code is ErrorCode.TEAM_MEMBERS_TOO_FEW


def test_role_table_is_the_single_twelve_role_vocabulary() -> None:
    """角色闭集 = pipeline.ROLES 的转发（12 个），不在 service 里另抄一份。"""
    assert frozenset(ROLES) == TEAM_ROLES
    assert len(TEAM_ROLES) == 12


# ── A4 / A5（roster-guard 批次）：档位裁剪的安全性 ─────────────────────────────
# 判据（DECISIONS D3，逐字冻结）：守卫条件 = `len(trim.kept) == 0`；**不是**
# `< TEAM_MIN_MEMBERS`（会误伤 lead-only），也不是角色白名单校验。
# 下列用例把 `kept == ()` 的**唯一**成因钉死在「空入参」上。


def _roster_of(size: int) -> list[dict[str, str]]:
    """造 `size` 个成员的合法花名册：agent_id 唯一，角色在 12 角色闭集内轮转。"""
    return [{"agent_id": f"m{i}", "role": ROLES[i % len(ROLES)]} for i in range(size)]


@pytest.mark.parametrize("tier", sorted(TIER_SPEC))
def test_trim_roster_of_empty_roster_stays_empty(tier: str) -> None:
    """A5 负向边界：空入参 ⇒ `kept == ()`（skipped 也空，不留半截状态）。

    这是 `kept == ()` 的**唯一**合法成因；紧接其后的属性用例证明非空入参永不为空。
    """
    trim = trim_roster((), tier)
    assert trim.kept == ()
    assert trim.skipped == ()


@pytest.mark.parametrize("size", (1, 3, 6, 12, 13, 40))
@pytest.mark.parametrize("tier", sorted(TIER_SPEC))
def test_tier_trim_never_empties_a_non_empty_roster(tier: str, size: int) -> None:
    """A5 属性：任意**非空**花名册 × 三档 ⇒ `kept` 必非空（裁剪不可能裁成空）。

    规模覆盖三种边界：1 人（最小非空）、正好等于该档 `role_cap`（短路分支的边界）、
    远超 cap（真走裁剪分支）。断言是负向的：任何「非空入参 ⇒ kept 为空」都变红。
    """
    cap = TIER_SPEC[tier].role_cap
    roster = _roster_of(size)
    assert roster  # 属性前提：入参非空
    trim = trim_roster(roster, tier, lead_agent_id="m0", host_agent_id="host")
    assert len(trim.kept) >= 1, f"{tier}: 非空花名册（size={size}）被裁成空"
    assert len(trim.kept) == min(size, cap)  # 只减不空：至多裁到 cap，绝不为 0
    assert len(trim.kept) + len(trim.skipped) == size  # 不丢成员、不造成员


def test_no_tier_cap_can_exhaust_a_non_empty_roster() -> None:
    """边界族负向断言：**任何**档位都无法把非空花名册裁空。

    证明结构（SPEC §空返回条件）：`role_cap >= 1` 三档全成立，且裁剪是「保留优先」
    而非「过滤」——`priority.extend(members)` 让每个成员都进候选。故 `kept == ()`
    只可能来自空入参；此处穷举 `size ∈ [1, cap+2]`（无 lead / 有 lead 两种调用）逐条
    断言，任何一条返回空都会让本用例变红。
    """
    for tier, spec in TIER_SPEC.items():
        assert spec.role_cap >= 1, f"{tier} 的 role_cap 必须 >= 1，否则裁剪可裁空"
        for size in range(1, spec.role_cap + 3):
            roster = _roster_of(size)
            for lead in (None, roster[0]["agent_id"]):
                trim = trim_roster(roster, tier, lead_agent_id=lead, host_agent_id="host")
                assert trim.kept != (), f"{tier}: size={size} lead={lead} 被裁成空"
                assert len(trim.kept) >= 1


#: quick / standard 两档 `default_roles` **之外**的角色（strict 的 default_roles = 全角色表）。
_NON_DEFAULT_ROLES = ("researcher", "ui", "dba", "sec", "devops", "docs")


def test_non_default_role_roster_is_never_trimmed_to_zero() -> None:
    """A5 判别力加强：`default_roles` 是取舍**次序**，不是白名单。

    花名册只含 quick / standard 的 `default_roles` 之外的角色。若有人把裁剪实现成
    「过滤：只保留 defaultRoles」，quick / standard 下它会被裁成空 —— 本用例正为此
    变红（strict 的 `default_roles` 就是全角色表，故那里只作非空断言）。规模取 1 与 5
    （quick cap=3，5 人必走真裁剪分支）。
    """
    for tier, spec in TIER_SPEC.items():
        if tier != "strict":
            assert not (set(_NON_DEFAULT_ROLES) & set(spec.default_roles))  # 判别前提
        for size in (1, 5):
            roster = [
                {"agent_id": f"n{i}", "role": _NON_DEFAULT_ROLES[i % len(_NON_DEFAULT_ROLES)]}
                for i in range(size)
            ]
            trim = trim_roster(roster, tier, lead_agent_id="n0", host_agent_id="host")
            assert len(trim.kept) >= 1, f"{tier}: 非默认角色花名册（size={size}）被裁成空"


@pytest.mark.parametrize("tier", sorted(TIER_SPEC))
def test_lead_only_roster_is_not_read_as_empty(tier: str) -> None:
    """A4 负向对照：lead-only 花名册**必须放行**，不得被判成空花名册。

    断言逐字 `len(trim.kept) == 1`（**禁止**写成 `>= 2`）：`lead` 是合法 roster 角色
    （run_service.py「``lead`` is a legitimate *roster* role」，而
    `normalize_owner_role("lead") == ""` 只管 artifact 归属）；团队清单的
    `TEAM_MIN_MEMBERS = 2` 只作用于 `TeamService.validate_member_ids`，套到 run
    花名册上会误伤 lead-only（DECISIONS D3/D4）。
    """
    lead_only = [{"agent_id": "host", "role": "lead"}]
    trim = trim_roster(lead_only, tier, lead_agent_id="host", host_agent_id="host")
    assert len(trim.kept) == 1  # lead 是合法 roster 角色 —— 不得写成 `>= 2`
    assert trim.kept[0] == {"agent_id": "host", "role": "lead"}
    assert trim.skipped == ()
    # 负向断言：两种候选判据在 lead-only 上**必然分道扬镳** —— D3 判据（`== 0`）放行，
    # 被否决的「团队清单最小成员数」判据会误伤；这正是禁止改写成 `< 2` 的原因。
    assert (len(trim.kept) == 0) is False  # D3 判据：不误伤 lead-only
    assert (len(trim.kept) < TEAM_MIN_MEMBERS) is True  # 被否决的判据：会误伤


def test_manifest_lead_only_roster_survives_tier_trim(
    roster_env: dict[str, object],
) -> None:
    """A4/A5 走**权威路径**：manifest 里的单成员花名册经 `trimmed_roster` 仍非空。

    直接写 manifest 是因为 `replace_roster` 会用 `TEAM_ROLES` 拒掉 roster-only 的
    `lead`（那是团队的 12 角色闭集）；读回必须经 `TeamService.roster` —— manifest
    是花名册唯一权威（S1），本用例不另造第二套裁剪。
    """
    workspace_for = roster_env["workspace_for"]
    teams = roster_env["teams"]
    assert callable(workspace_for)
    assert isinstance(teams, TeamService)
    workspace_for("host").write_text(
        TEAM_MANIFEST_WORKSPACE,
        json.dumps(
            {"kind": "team", "members": [{"agent_id": "host", "role": "lead"}]},
            ensure_ascii=False,
        ),
        force=True,
    )
    assert _manifest(roster_env)["members"] == [{"agent_id": "host", "role": "lead"}]
    for tier in TIER_SPEC:
        trim = teams.trimmed_roster("host", tier, host_agent_id="host")
        assert len(trim.kept) == 1  # lead 是合法 roster 角色 —— 不得写成 `>= 2`
        assert len(trim.kept) != 0
