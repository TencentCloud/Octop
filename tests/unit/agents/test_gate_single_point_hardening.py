"""T-68 hardening — ≥2 independent guards for the two single-point gates.

Why this file exists: mutation probes showed that neutering ``owner_violation``
(R1 artifact ownership / G14) or ``validate_task_graph`` (G6) turned exactly **one**
test red each. A gate whose only guard is one test function can be silently
disarmed by a single edit — the cheapest possible way to lose a security-relevant
rule.

So each gate gets an extra guard whose **shape differs** from the incumbent:

* R1 — the incumbent asserts the deny for ``STATE.json`` as ``pm`` (the runtime-only
  ``owners == ()`` branch). Here the *same branch* is reached through a **different
  file and a different role** (``ROSTER.json`` as ``lead``), and its **allow side**
  (the ``exists=False`` creation branch) is asserted separately — the incumbent only
  ever asserts the deny for that branch.
* G6 — the incumbent goes through ``create_task``. Here the gate is reached through
  the **other two public write entries**, ``create_repair`` and
  ``create_quality_task``, which the service docstring promises also run G6
  ("G6 runs on **every** task write"). A refactor that moved the call out of the
  shared path would slip past the incumbent guard.

This file is self-contained on purpose: an "independent guard" that imported the
incumbent's harness would share its failure modes.

Mutation evidence that these are real guards (both re-run after adding this file):
* ``owner_violation`` -> fail-open: **3** tests red (was 1).
* ``validate_task_graph`` -> no-op: **3** tests red (was 1).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from octop.config import OctopConfig
from octop.infra.agents.teams.run_service import TeamRunService, run_directory
from octop.infra.agents.teams.service import TeamService
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.services import build_shared_services
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.gateway.threads import ThreadRegistry
from octop.infra.utils.paths import PathLayout

TEAM_ID = "ag-team"
MANIFEST = ".octop/manifest.json"
MEMBERS = [(TEAM_ID, "lead"), ("ag-be", "backend"), ("ag-qa", "qa")]


class Actor:
    """The slice of a user row ``ProjectActor`` needs."""

    def __init__(self, user_id: int) -> None:
        self.id = user_id
        self.permissions = ["projects", "knowledge_bases"]

    @property
    def is_admin(self) -> bool:
        return False


class FakeWorkspace:
    def __init__(self, files: dict[str, str] | None = None) -> None:
        self.files: dict[str, str] = dict(files or {})

    def read_text(self, path: str, *, limit: int = 10_000_000) -> str | None:
        return self.files.get(str(path))

    def write_text(self, path: str, content: str, *, force: bool = False) -> None:
        self.files[str(path)] = content

    def exists(self, path: str) -> bool:
        return str(path) in self.files

    def list_dir(self, path: str = ".") -> list[Any]:
        """**Same shape as the harness**: workspace-relative ``{"path", "is_dir"}``.

        T-72: the real ``BackendWorkspace.list_dir`` is documented as "Always
        workspace-relative (``skills/demo``), never basename-only" — a basename-only
        fake is precisely what hid the ``present_artifacts`` shape bug.
        """
        prefix = "" if str(path) in {"", "."} else str(path).rstrip("/") + "/"
        entries: list[Any] = []
        for name in sorted(self.files):
            if not name.startswith(prefix):
                continue
            rest = name[len(prefix) :]
            if "/" not in rest:
                entries.append({"path": name, "is_dir": False})
        return entries


class _StubGateway:
    def __init__(self, services: Any) -> None:
        self.thread_registry = ThreadRegistry(
            session_repo=services.session_repo,
            thread_repo=services.thread_repo,
        )


def _manifest() -> str:
    payload: dict[str, Any] = {
        "members": [{"agent_id": a, "role": r} for a, r in MEMBERS],
        "lead_agent_id": TEAM_ID,
    }
    return json.dumps(payload)


@dataclass
class Harness:
    services: Any
    service: TeamRunService
    workspace: FakeWorkspace
    user: Actor

    def create_run(self, **fields: Any) -> Any:
        fields.setdefault("goal", "hardening")
        fields.setdefault("tier", "quick")
        return self.service.create(team_agent_id=TEAM_ID, user=self.user, **fields)

    def write(self, run: Any, name: str, content: str) -> None:
        self.workspace.write_text(f"{run_directory(run)}/{name}", content)

    def stored(self, run: Any, name: str) -> str | None:
        return self.workspace.files.get(f"{run_directory(run)}/{name}")


@pytest.fixture
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Harness]:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path / "home"))
    paths = PathLayout(tmp_path / ".octop")
    paths.ensure_root()
    db = SqlitePool(paths.db)
    run_migrations(db)
    services = build_shared_services(db=db, paths=paths, config=OctopConfig())
    user_id = services.user_repo.create(username="owner", password_hash="h", role="user")
    services.agent_repo.create(agent_id=TEAM_ID, user_id=user_id, name="Team", kind="team")
    workspace = FakeWorkspace({MANIFEST: _manifest(), "other.txt": "x"})
    service = TeamRunService(
        services=services,
        gateway=_StubGateway(services),  # type: ignore[arg-type]
        workspace_for=lambda agent_id: workspace if agent_id == TEAM_ID else None,
        team_service=TeamService(
            services.repos,
            workspace_for=lambda agent_id: workspace if agent_id == TEAM_ID else None,
        ),
    )
    yield Harness(services=services, service=service, workspace=workspace, user=Actor(user_id))


# ─────────────────────────────────────────────────────────────────────────────
# R1 / G14 — artifact ownership. Extra guard #1 (deny) and #2 (allow).
# ─────────────────────────────────────────────────────────────────────────────


def test_roster_json_is_runtime_exclusive_for_a_different_role(
    harness: Harness,
) -> None:
    """Deny side, different file **and** different role from the incumbent guard.

    ``ROSTER.json`` is the second ``owners == ()`` entry. The incumbent asserts
    ``STATE.json`` denied for ``pm``; this asserts the other entry denied for
    ``qa`` — a *recognised* role that is simply not an owner, so the refusal comes
    from the "not one of its owners" arm rather than the fail-open arm.

    Note ``role="lead"`` would **not** work here — see
    ``test_an_unrecognised_role_fails_open_past_the_ownership_gate`` below, which
    pins that gap explicitly.
    """
    run = harness.create_run()
    harness.write(run, "ROSTER.json", '{"members": []}')

    with pytest.raises(OctopError) as err:
        harness.service.write_artifact(
            run.run_id,
            name="ROSTER.json",
            content='{"members": ["hijacked"]}',
            revision="",
            role="qa",
            user=harness.user,
        )

    assert err.value.code is ErrorCode.TEAM_ARTIFACT_OWNERSHIP_DENIED
    assert err.value.status == 409
    assert harness.stored(run, "ROSTER.json") == '{"members": []}', "被拒后内容不得变化"


def test_an_unrecognised_role_is_refused_on_an_existing_artifact(
    harness: Harness,
) -> None:
    """★ **已翻转**（原 `test_an_unrecognised_role_fails_open_past_the_ownership_gate`，T-69/task-103）。

    原用例逐字写着：**"If the team rules that an unrecognised role must be refused,
    flip this to ``pytest.raises`` — that is what makes it a tripwire rather than a
    rubber stamp."** ⇒ 团队裁定 **(a)** 就是那条：**未认出的 `role` + 目标工件存在 ⇒ 拒绝**
    （`400 TEAM_ROLE_UNKNOWN`），而**创建**（`exists=False`）照旧放行。

    它钉住的缺口（原文保留，便于追溯）：`owner_violation` 对认不出的角色 **fail-open**
    （`artifacts.py` 规则 2，上游一致），但**HTTP 面的 `role` 是调用方声明**
    （`api/routers/team_runs.py` 把 `role=body.role` 直接传下来，而 `_require_owned_run`
    只查 run 归属）⇒ 任何能写该 run 工件的人，传一个未认出的角色（`"lead"` / `"bogus"`）
    就能覆写**运行时专属**的 `STATE.json` / `ROSTER.json` / `TASKS.json`。

    **为什么这道门加在服务层而不是纯函数里**：`owner_violation` 是**工具通道**共用的判定，
    那条通道的 `role` 来自**运行时的角色指派**（不是调用方声明）⇒ 它的 fail-open 语义是**对的**，
    不能改（工具通道的对照见 `tests/unit/agents/test_role_unknown_gate.py`）。
    """
    run = harness.create_run()
    harness.write(run, "STATE.json", '{"phase": "design"}')
    # Supply the *current* revision so the revision CAS passes and the only
    # variable left is the role string — that isolates the ownership gate.
    _, revision = harness.service.read_artifact(run.run_id, "STATE.json")
    assert revision, "前提：文件已存在且有 revision（否则只会撞到 CAS）"

    with pytest.raises(OctopError) as err:
        harness.service.write_artifact(
            run.run_id,
            name="STATE.json",
            content='{"phase": "deliver"}',
            revision=revision,
            role="lead",  # not in pipeline.ROLES / artifacts.TEAM_ROLES
            user=harness.user,
        )

    assert err.value.code is ErrorCode.TEAM_ROLE_UNKNOWN
    assert err.value.status == 400
    assert harness.stored(run, "STATE.json") == '{"phase": "design"}', "被拒后内容不得变化"


def test_runtime_exclusive_creation_is_allowed_for_any_role(harness: Harness) -> None:
    """Allow side of the *same* branch — ``exists=False`` must stay permissive.

    The run skeleton is laid down by the first member, who owns almost none of the
    13 files; if creation were refused the run could never be created. The
    incumbent guard only ever pins the deny here, so this is the half that a
    "tighten the gate" edit would break without anything going red.
    """
    run = harness.create_run()
    assert harness.stored(run, "STATE.json") is None

    created = harness.service.write_artifact(
        run.run_id, name="STATE.json", content="{}", revision="", role="qa", user=harness.user
    )

    assert created["revision"]
    assert harness.stored(run, "STATE.json") == "{}"


def test_a_listed_artifact_is_writable_by_one_of_its_owners(harness: Harness) -> None:
    """Third shape: the ``normalized in owners`` pass branch, at the service entry."""
    run = harness.create_run()
    first = harness.service.write_artifact(
        run.run_id, name="SPEC.md", content="# v1", revision="", role="pm", user=harness.user
    )
    second = harness.service.write_artifact(
        run.run_id,
        name="SPEC.md",
        content="# v2",
        revision=first["revision"],
        role="pm",
        user=harness.user,
    )
    assert second["revision"] != first["revision"]


# ─────────────────────────────────────────────────────────────────────────────
# G6 — task graph. Guards through the *other* two public write entries.
# ─────────────────────────────────────────────────────────────────────────────


def test_create_repair_also_runs_the_graph_gate(harness: Harness) -> None:
    """G6 through ``create_repair`` (incumbent only covers ``create_task``)."""
    run = harness.create_run()

    with pytest.raises(OctopError) as err:
        harness.service.create_repair(
            run.run_id, title="修复", role="backend", depends_on=["ghost-task"]
        )

    assert err.value.code is ErrorCode.TEAM_TASK_GRAPH_INVALID
    assert err.value.status == 409
    assert err.value.details["code"] == "missing-id"
    assert harness.service.list_tasks(run.run_id) == [], "被拒时不得落盘"


def test_create_quality_task_also_runs_the_graph_gate(harness: Harness) -> None:
    """G6 through ``create_quality_task`` — the third and last write entry."""
    run = harness.create_run()

    with pytest.raises(OctopError) as err:
        harness.service.create_quality_task(
            run.run_id, title="质检", role="qa", depends_on=["ghost-task"]
        )

    assert err.value.code is ErrorCode.TEAM_TASK_GRAPH_INVALID
    assert err.value.details["code"] == "missing-id"
    assert harness.service.list_tasks(run.run_id) == []


def test_a_dependency_on_an_existing_task_is_accepted(harness: Harness) -> None:
    """Allow side for the same entries: a real dependency must still be accepted.

    Without this, the two refusals above could pass even if ``create_repair``
    refused *everything*.
    """
    run = harness.create_run()
    first = harness.service.create_task(run.run_id, title="上游", role="backend", user=harness.user)

    repair = harness.service.create_repair(
        run.run_id, title="修复", role="backend", depends_on=[first.id]
    )

    assert repair.id != first.id
    assert len(harness.service.list_tasks(run.run_id)) == 2
