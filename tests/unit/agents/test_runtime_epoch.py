"""The process generation (C-2) and its carrier, ``runtime_epoch`` (T4).

``runtime_epoch`` is new in this batch — ``grep -rn "runtime_epoch" src/octop``
found nothing before it — so this file pins the three things that make it a
*process identity* rather than a decoration:

* it is minted **once per bound process** by ``bind_runtime``, and two separately
  bound services do not share it;
* every attempt token this process hands out carries it as a ``<epoch>.`` prefix,
  on the existing free-``TEXT`` ``attempt_id`` column (zero migration);
* an unbound service passes ``epoch=None`` and therefore **does not judge C-2 at
  all** — it never fabricates a generation to manufacture a mismatch (``D-4``).

The last one is the load-bearing one: "cannot judge" must not decay into "guesses".
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from octop.config import OctopConfig
from octop.infra.agents.teams.pipeline import epoch_of
from octop.infra.agents.teams.run_service import TeamRunService
from octop.infra.agents.teams.service import TeamService
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.services import build_shared_services
from octop.infra.gateway.threads import ThreadRegistry
from octop.infra.utils.paths import PathLayout

TEAM_ID = "ag-team"
MANIFEST = ".octop/manifest.json"
SCOPE = "src/octop/infra/agents/teams/run_service.py"


class Actor:
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
        """Direct entries under *path*, in the dict shape the harness returns."""
        prefix = "" if str(path) in {"", "."} else f"{str(path).rstrip('/')}/"
        entries: list[Any] = []
        for name in sorted(self.files):
            if not name.startswith(prefix):
                continue
            if "/" not in name[len(prefix) :]:
                entries.append({"path": name, "is_dir": False})
        return entries


class _StubGateway:
    def __init__(self, services: Any) -> None:
        self.thread_registry = ThreadRegistry(
            session_repo=services.session_repo,
            thread_repo=services.thread_repo,
        )


@dataclass
class Runtime:
    services: Any
    service: TeamRunService
    workspace: FakeWorkspace
    user: Actor

    def spawn(self) -> TeamRunService:
        """A second service over the same control plane — i.e. the next boot."""
        return TeamRunService(
            services=self.services,
            gateway=_StubGateway(self.services),  # type: ignore[arg-type]
            workspace_for=lambda agent_id: self.workspace if agent_id == TEAM_ID else None,
            team_service=TeamService(
                self.services.repos,
                workspace_for=lambda agent_id: self.workspace if agent_id == TEAM_ID else None,
            ),
        )

    def create_run(self) -> Any:
        return self.service.create(
            team_agent_id=TEAM_ID, user=self.user, goal="代际", tier="standard"
        )

    def add_task(self, run: Any) -> Any:
        return self.service.create_task(
            run.run_id, user=self.user, title="占位", role="backend", in_scope=[SCOPE]
        )

    def move_to_doing(self, task_id: str, token: str) -> None:
        """Stamp *token* on the row and move it to ``doing`` — a task held by a peer."""
        claimed = self.service._tasks.claim(
            task_id, claimed_by="backend", expected_attempt_id=None, attempt_id=token
        )
        assert claimed is not None
        self.service._tasks.update(task_id, status="doing")


@pytest.fixture
def runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Runtime]:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path / "home"))
    paths = PathLayout(tmp_path / ".octop")
    paths.ensure_root()
    db = SqlitePool(paths.db)
    run_migrations(db)
    services = build_shared_services(db=db, paths=paths, config=OctopConfig())
    user = services.user_repo.create(username="owner", password_hash="h", role="user")
    services.agent_repo.create(agent_id=TEAM_ID, user_id=user, name="Team", kind="team")
    workspace = FakeWorkspace(
        {
            MANIFEST: json.dumps(
                {
                    "members": [
                        {"agent_id": TEAM_ID, "role": "lead"},
                        {"agent_id": "ag-arch", "role": "architect"},
                        {"agent_id": "ag-be", "role": "backend"},
                        {"agent_id": "ag-qa", "role": "qa"},
                    ],
                    "lead_agent_id": TEAM_ID,
                }
            )
        }
    )
    service = TeamRunService(
        services=services,
        gateway=_StubGateway(services),  # type: ignore[arg-type]
        workspace_for=lambda agent_id: workspace if agent_id == TEAM_ID else None,
        team_service=TeamService(
            services.repos,
            workspace_for=lambda agent_id: workspace if agent_id == TEAM_ID else None,
        ),
    )
    yield Runtime(services=services, service=service, workspace=workspace, user=Actor(user))


def test_epoch_of_reads_the_prefix_and_nothing_else() -> None:
    assert epoch_of(None) is None
    assert epoch_of("") is None
    assert epoch_of("boot") == "boot"
    assert epoch_of("boot.0001") == "boot"
    assert epoch_of("boot.0001.tail") == "boot"


def test_an_unbound_service_has_no_generation_and_mints_bare_tokens(
    runtime: Runtime,
) -> None:
    assert runtime.service._runtime_epoch is None
    run = runtime.create_run()
    task = runtime.add_task(run)

    runtime.service.claim(run.run_id, task.id, role="backend", user=runtime.user)

    row = runtime.service._tasks.get(task.id)
    assert row is not None
    assert row.attempt_id and "." not in row.attempt_id
    # a token without a separator is its own generation, so it can never be
    # mistaken for a stale foreign one
    assert epoch_of(row.attempt_id) == row.attempt_id


def test_bind_runtime_mints_one_generation_and_every_token_carries_it(
    runtime: Runtime,
) -> None:
    runtime.service.bind_runtime()
    first = runtime.service._runtime_epoch
    assert isinstance(first, str) and first
    # idempotent: binding again does not roll this process's generation
    runtime.service.bind_runtime()
    assert runtime.service._runtime_epoch == first

    run = runtime.create_run()
    task = runtime.add_task(run)
    runtime.service.claim(run.run_id, task.id, role="backend", user=runtime.user)

    row = runtime.service._tasks.get(task.id)
    assert row is not None
    assert row.attempt_id.startswith(f"{first}.")
    assert epoch_of(row.attempt_id) == first


def test_a_fresh_boot_gets_a_different_generation(runtime: Runtime) -> None:
    runtime.service.bind_runtime()
    other = runtime.spawn()
    other.bind_runtime()

    assert other._runtime_epoch
    assert other._runtime_epoch != runtime.service._runtime_epoch


def test_a_token_from_another_generation_is_reported_then_rearmed(
    runtime: Runtime,
) -> None:
    runtime.service.bind_runtime()
    generation = runtime.service._runtime_epoch
    run = runtime.create_run()
    task = runtime.add_task(run)
    runtime.move_to_doing(task.id, "previousboot.0001")
    before = runtime.service._tasks.get(task.id)
    assert before is not None

    (item,) = runtime.service.stranded(run.run_id)

    assert item.id == task.id
    assert item.reason == "epoch"
    assert item.epochMismatch is True
    assert item.status == "doing"
    # reporting wrote nothing: the foreign token is still on the row
    assert runtime.service._tasks.get(task.id).attempt_id == "previousboot.0001"

    assert runtime.service.settle(run.run_id) == [task.id]

    rearmed = runtime.service._tasks.get(task.id)
    assert rearmed.status == "todo"
    assert rearmed.attempt == before.attempt + 1
    assert epoch_of(rearmed.attempt_id) == generation
    # G8: the previous holder's token is now stale, and the row is no longer stranded
    assert runtime.service._tasks.report(task.id, attempt_id="previousboot.0001") is None
    assert runtime.service.stranded(run.run_id) == ()


def test_an_unbound_service_never_judges_c2(runtime: Runtime) -> None:
    run = runtime.create_run()
    task = runtime.add_task(run)
    runtime.move_to_doing(task.id, "someoneelse.0002")

    assert runtime.service._runtime_epoch is None
    # C-1 alone: the row was just touched, so nothing is reported and nothing is
    # settled — no fabricated epoch, no false positive
    assert runtime.service.stranded(run.run_id) == ()
    assert runtime.service.settle(run.run_id) == []
    row = runtime.service._tasks.get(task.id)
    assert (row.status, row.attempt_id) == ("doing", "someoneelse.0002")


def test_settle_uses_the_same_clock_as_the_report(runtime: Runtime) -> None:
    """``I5``: ``settle`` re-judges through ``stranded()``, so a hypothetical report
    — one produced by moving the clock — settles nothing."""
    run = runtime.create_run()
    task = runtime.add_task(run)
    runtime.move_to_doing(task.id, "someoneelse.0002")
    before = runtime.service._tasks.get(task.id)
    assert before is not None

    items = runtime.service.stranded(run.run_id, now=before.updated_at + 10_000)
    assert [item.reason for item in items] == ["idle"]

    assert runtime.service.settle(run.run_id) == []
    row = runtime.service._tasks.get(task.id)
    assert (row.status, row.attempt_id) == ("doing", "someoneelse.0002")
