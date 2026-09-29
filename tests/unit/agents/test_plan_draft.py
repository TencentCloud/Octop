"""Unit tests for the plan-draft and stranded-settle pure functions (T3).

Covers ``PLAN.md §2.2``/``§2.4``/``§2.5`` (A1 draft normalisation) and
``§4.2``/``§4.3`` (A2 C-1 / C-2). Every refusal row carries a negative
assertion, and the two contrasts PLAN ``AC-A2-1``/``B15`` demand are pinned:
``normalize_draft`` must **reject** an owner outside the roster instead of
silently downgrading it, and ``stranded_tasks`` must **report without writing**
— it neither mutates its inputs nor settles anything.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

import pytest

from octop.infra.agents.teams import pipeline
from octop.infra.agents.teams.pipeline import (
    STRANDED_IDLE_SECONDS,
    OctopError,
    StrandedItem,
    epoch_of,
    normalize_draft,
    settle_tasks,
    stranded_tasks,
)
from octop.infra.errors import ErrorCode

ROLES = ("pm", "architect", "backend")

#: ``TEAM_PLAN_DRAFT_INVALID`` — PLAN ``§2.4``, owned by ``T2``. Pinned at import
#: time so a missing code is a collection error, not a silently skipped row.
DRAFT_INVALID = ErrorCode.TEAM_PLAN_DRAFT_INVALID


def _draft_task(task_id: str = "T1", **overrides: Any) -> dict[str, Any]:
    """One valid ``TaskDraft`` (PLAN ``§2.5`` keys verbatim)."""
    task: dict[str, Any] = {
        "id": task_id,
        "owner": "backend",
        "title": f"do {task_id}",
        "kind": "work",
        "spec": "…",
        "acceptance": ["…"],
        "inScope": ["src/octop/infra/agents/teams/pipeline.py"],
        "verify": "uv run --no-sync pytest tests/unit/agents/test_plan_draft.py -q",
        "dependsOn": [],
        "status": "pending",
        "attempt": 7,
        "round": 9,
        "verdict": "pass",
    }
    task.update(overrides)
    return task


def _draft(*tasks: dict[str, Any], roles: tuple[str, ...] = ROLES) -> dict[str, Any]:
    return {"roles": list(roles), "tasks": list(tasks)}


def _row(task_id: str = "T1", **overrides: Any) -> dict[str, Any]:
    """One ``project_tasks`` row snapshot as the repo hands it to the service."""
    row: dict[str, Any] = {
        "id": task_id,
        "owner": "backend",
        "status": "doing",
        "attempt": 0,
        "attempt_id": None,
        "updated_at": 1_000_000,
        "started_at": 1_000_000,
    }
    row.update(overrides)
    return row


def _failure_code(excinfo: pytest.ExceptionInfo[OctopError]) -> object:
    return excinfo.value.details.get("code")


# ─────────────────────────────────────────────────────────────────────────────
# normalize_draft — real validation, no silent downgrade
# ─────────────────────────────────────────────────────────────────────────────


def test_normalize_draft_defaults_to_todo_storage_status() -> None:
    """★ A1 normalisation target is ``todo`` — Octop has no ``pending`` storage state."""
    result = normalize_draft(_draft(_draft_task()), roles=ROLES, run={"run_id": "r1"})
    task = result["tasks"][0]
    assert task["status"] == "todo"
    assert task["status"] != "pending"
    assert (task["attempt"], task["round"], task["verdict"]) == (0, 1, None)
    assert task["dependsOn"] == []
    assert result["roles"] == list(ROLES)


def test_normalize_draft_is_idempotent() -> None:
    once = normalize_draft(_draft(_draft_task()), roles=ROLES, run={})
    twice = normalize_draft(once, roles=ROLES, run={})
    assert once == twice


def test_normalize_draft_rejects_empty_task_list() -> None:
    with pytest.raises(OctopError) as excinfo:
        normalize_draft(_draft(), roles=ROLES, run={})
    assert _failure_code(excinfo) == "empty-tasks"


def test_normalize_draft_refuses_the_run_id_as_an_owner() -> None:
    """★ B1 is fail-closed: the run id / project id are **not** roles.

    ``normalize_draft`` used to carry a ``known`` fallback over those two values, so
    ``owner == run_id`` was accepted — the refusal was open for exactly the ids a
    caller is most likely to pass by mistake. Any owner outside ``roles`` is now
    refused, and the offending owner is never rewritten to ``roles[0]``.
    """
    draft = _draft(_draft_task("T0", owner="run-1"))
    with pytest.raises(OctopError) as excinfo:
        normalize_draft(draft, roles=ROLES, run={"run_id": "run-1", "project_id": "prj-1"})
    assert _failure_code(excinfo) == "owner-not-in-roles"
    assert (excinfo.value.details or {})["path"] == ["tasks[0].owner"]
    assert draft["tasks"][0]["owner"] == "run-1", "owner must never be rewritten to roles[0]"


@pytest.mark.parametrize(
    ("task", "code", "path"),
    [
        pytest.param(_draft_task(""), "missing-id", ["0"], id="missing-id"),
        pytest.param(
            _draft_task("T0", owner="ghost"),
            "owner-not-in-roles",
            ["tasks[0].owner"],
            id="owner-outside-roster",
        ),
        pytest.param(
            _draft_task("T0", owner=""), "owner-not-in-roles", ["tasks[0].owner"], id="owner-empty"
        ),
        pytest.param(
            _draft_task("T0", inScope=[]), "scope-empty", ["T0", "inScope"], id="scope-empty"
        ),
        pytest.param(
            _draft_task("T0", dependsOn=["T0"]),
            "self-dependency",
            ["T0", "T0"],
            id="self-dependency",
        ),
        pytest.param(
            _draft_task("T0", dependsOn=["T9"]), "missing-id", ["T0", "T9"], id="dangling-dep"
        ),
    ],
)
def test_normalize_draft_refusals(task: dict[str, Any], code: str, path: list[str]) -> None:
    """★ Every illegal draft is refused with a PLAN ``§2.4`` ``details.code``.

    The owner row is the anti-downgrade guard: an owner outside the roster must
    raise, never be rewritten to a default role.
    """
    with pytest.raises(OctopError) as excinfo:
        normalize_draft(_draft(task), roles=ROLES, run={})
    assert excinfo.value.code is DRAFT_INVALID
    assert _failure_code(excinfo) == code
    assert excinfo.value.details.get("path") == path
    assert excinfo.value.status == 422


def test_normalize_draft_rejects_duplicate_id() -> None:
    with pytest.raises(OctopError) as excinfo:
        normalize_draft(_draft(_draft_task("T1"), _draft_task("T1")), roles=ROLES, run={})
    assert _failure_code(excinfo) == "duplicate-id"


def test_normalize_draft_rejects_cycle() -> None:
    with pytest.raises(OctopError) as excinfo:
        normalize_draft(
            _draft(
                _draft_task("T1", dependsOn=["T2"]),
                _draft_task("T2", dependsOn=["T1"]),
            ),
            roles=ROLES,
            run={},
        )
    assert _failure_code(excinfo) == "cycle"


def test_normalize_draft_strips_blank_padded_ids() -> None:
    result = normalize_draft(
        _draft(
            _draft_task("  T1  "),
            _draft_task("T2", dependsOn=[" T1 "]),
        ),
        roles=ROLES,
        run={},
    )
    first, second = result["tasks"]
    assert first["id"] == "T1"
    assert second["id"] == "T2"
    assert second["dependsOn"] == ["T1"]


def test_normalize_draft_does_not_mutate_input() -> None:
    source = _draft(_draft_task())
    before = deepcopy(source)
    normalize_draft(source, roles=ROLES, run={})
    assert source == before


# ─────────────────────────────────────────────────────────────────────────────
# stranded_tasks — report only, never a write
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("rows", "epoch", "now", "expected"),
    [
        pytest.param(
            [_row("T1", status="doing", attempt_id="old.abc")],
            "new",
            1_000_000,
            [("T1", True, "epoch")],
            id="doing-old-epoch",
        ),
        pytest.param(
            [_row("T1", status="doing", attempt_id="new.abc")],
            "new",
            1_000_000,
            [],
            id="doing-current-epoch",
        ),
        pytest.param(
            [_row("T1", status="todo", attempt_id="old.abc")],
            "new",
            1_000_000,
            [("T1", True, "epoch")],
            id="todo-claimed-old-epoch",
        ),
        pytest.param(
            [_row("T1", status="todo", attempt_id=None)],
            "new",
            1_000_000,
            [],
            id="todo-unclaimed",
        ),
        pytest.param(
            [_row("T1", status="done", attempt_id="old.abc")],
            "new",
            9_999_999,
            [],
            id="done-never-reported",
        ),
        pytest.param(
            [_row("T1", status="blocked", attempt_id="old.abc")],
            "new",
            9_999_999,
            [],
            id="blocked-never-reported",
        ),
        pytest.param(
            [_row("T1", status="doing", attempt_id="new.abc", updated_at=1_000_000)],
            "new",
            1_000_000 + STRANDED_IDLE_SECONDS + 1,
            [("T1", False, "idle")],
            id="idle-above-threshold",
        ),
        pytest.param(
            [_row("T1", status="doing", attempt_id="new.abc", updated_at=1_000_000)],
            "new",
            1_000_000 + STRANDED_IDLE_SECONDS,
            [],
            id="idle-at-threshold-not-stranded",
        ),
        pytest.param(
            [_row("T1", status="doing", attempt_id="old.abc", updated_at=1_000_000)],
            "new",
            1_000_000 + STRANDED_IDLE_SECONDS + 5,
            [("T1", True, "epoch")],
            id="epoch-wins-over-idle",
        ),
        pytest.param(
            [_row("T1", status="doing", attempt_id="old.abc")],
            None,
            9_999_999,
            [("T1", False, "idle")],
            id="epoch-unavailable-only-c1",
        ),
    ],
)
def test_stranded_tasks_table(
    rows: list[dict[str, Any]],
    epoch: str | None,
    now: float,
    expected: list[tuple[str, bool, str]],
) -> None:
    """★ C-2 epoch first, C-1 timestamp fallback, and "cannot tell ⇒ do not judge"."""
    items = stranded_tasks({"run_id": "r1"}, rows, epoch=epoch, now=now)
    assert [(item.id, item.epochMismatch, item.reason) for item in items] == expected


def test_stranded_tasks_empty_candidate_set_reports_nothing() -> None:
    """★ ``AC-A2-1``: an empty input must return ``()`` — no false report."""
    assert stranded_tasks({"run_id": "r1"}, [], epoch="new", now=9_999_999) == ()
    assert (
        stranded_tasks(
            {"run_id": "r1"}, [_row("T1", status="planning")], epoch="new", now=9_999_999
        )
        == ()
    )


def test_stranded_tasks_epoch_none_uses_timestamp_fallback() -> None:
    """``epoch is None`` ⇒ C-2 is not judged, C-1 still fires."""
    rows = [_row("T1", status="doing", attempt_id="old.abc", updated_at=1_000_000)]
    items = stranded_tasks(
        {"run_id": "r1"}, rows, epoch=None, now=1_000_000 + STRANDED_IDLE_SECONDS + 1
    )
    assert [(item.id, item.epochMismatch, item.reason) for item in items] == [("T1", False, "idle")]


def test_stranded_tasks_epoch_mismatch_without_timestamps() -> None:
    """No timestamps ⇒ ``idleSeconds = 0``; C-2 alone still reports the task."""
    rows = [
        {"id": "T1", "owner": "backend", "status": "doing", "attempt": 2, "attempt_id": "old.abc"}
    ]
    items = stranded_tasks({"run_id": "r1"}, rows, epoch="new", now=9_999_999)
    assert len(items) == 1
    assert items[0].idleSeconds == 0
    assert items[0].attempt == 2
    assert items[0].reason == "epoch"


def test_stranded_tasks_uses_max_of_updated_and_started() -> None:
    rows = [
        _row(
            "T1",
            status="doing",
            attempt_id="new.abc",
            updated_at=1_000_000,
            started_at=1_000_000 + STRANDED_IDLE_SECONDS + 1,
        )
    ]
    items = stranded_tasks(
        {"run_id": "r1"}, rows, epoch="new", now=1_000_000 + STRANDED_IDLE_SECONDS + 1
    )
    assert items == ()


def test_stranded_tasks_tolerates_missing_owner() -> None:
    """PLAN ``§4.3`` ③: a task without an owner is reported with ``owner=""``."""
    rows = [{"id": "T1", "status": "doing", "attempt_id": "old.abc", "updated_at": 0}]
    items = stranded_tasks({"run_id": "r1"}, rows, epoch="new", now=0)
    assert [(item.id, item.owner) for item in items] == [("T1", "")]


def test_stranded_tasks_reports_do_not_change_anything() -> None:
    """★ ``PLAN`` ``I7``: the judgement function reports and does not act.

    Nothing it returns is a mutation: the row snapshot comes back verbatim, no
    status is touched, and no ``StrandedItem`` carries a target state.
    """
    rows = [_row("T1", status="doing", attempt_id="old.abc")]
    before = deepcopy(rows)
    items = stranded_tasks({"run_id": "r1"}, rows, epoch="new", now=9_999_999)
    assert rows == before
    assert rows[0]["status"] == "doing"
    assert rows[0]["attempt"] == 0
    assert isinstance(items[0], StrandedItem)
    assert not hasattr(items[0], "status_after")


def test_stranded_tasks_is_observably_read_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """★ Contrast ② guard: a judge that *acts* instead of reporting cannot pass.

    The whole settle contract rests on ``stranded_tasks`` only looking, so this
    test pins the difference between looking and acting: the same input, once
    through a write-capable judge, is no longer the input it was handed.
    """
    rows = [_row("T1", status="doing", attempt_id="old.abc")]
    before = deepcopy(rows)

    def _acting_judge(
        run: Mapping[str, Any],
        tasks: Sequence[Mapping[str, Any]],
        *,
        epoch: str | None,
        now: float,
    ) -> tuple[StrandedItem, ...]:
        items = stranded_tasks(run, tasks, epoch=epoch, now=now)
        for task in tasks:  # the bad behaviour this guard exists to catch
            if any(item.id == task.get("id") for item in items):
                task["status"] = "todo"
                task["attempt"] = int(task.get("attempt") or 0) + 1
        return items

    monkeypatch.setattr(pipeline, "stranded_tasks", _acting_judge)
    _acting_judge({"run_id": "r1"}, rows, epoch="new", now=9_999_999)
    assert rows != before, "an acting judge is detectable — the guard has teeth"

    rows_again = [_row("T1", status="doing", attempt_id="old.abc")]
    stranded_tasks({"run_id": "r1"}, rows_again, epoch="new", now=9_999_999)
    assert rows_again == before, "the real stranded_tasks must leave the board verbatim"


def test_epoch_of_shape() -> None:
    """``epoch_of`` is the C-2 reader: ``<epoch>.<token>``, no ``.`` ⇒ own epoch."""
    assert epoch_of("new.abc") == "new"
    assert epoch_of("new") == "new"
    assert epoch_of(None) is None
    assert epoch_of("") is None


# ─────────────────────────────────────────────────────────────────────────────
# settle_tasks — clears back to a re-dispatchable state
# ─────────────────────────────────────────────────────────────────────────────


def test_settle_tasks_clears_back_to_todo_and_bumps_attempt() -> None:
    """★ ``doing → todo`` is legal (repo ``update`` @362 applies no transition
    table) and ``attempt + 1`` makes the task re-dispatchable."""
    rows = [_row("T1", status="doing", attempt=3, attempt_id="old.abc")]
    items = stranded_tasks({"run_id": "r1"}, rows, epoch="new", now=9_999_999)
    drafts, settled = settle_tasks(rows, items, at=1_700_000_000, reason="epoch mismatch")
    assert settled == ["T1"]
    assert drafts == [
        {
            "id": "T1",
            "status": "todo",
            "attempt": 4,
            "strandedAt": 1_700_000_000,
            "strandedFrom": "doing",
            "note": "epoch mismatch",
        }
    ]


def test_settle_tasks_is_empty_without_stranded_items() -> None:
    """★ PLAN ``R10``: nothing stranded ⇒ ``([], [])`` so the caller writes nothing."""
    rows = [_row("T1", status="doing", attempt_id="new.abc")]
    assert settle_tasks(rows, (), at=1) == ([], [])


@pytest.mark.parametrize("status", ["done", "cancelled"])
def test_settle_tasks_leaves_terminal_tasks_verbatim(status: str) -> None:
    """★ Terminal tasks are never rewritten, never re-dispatched, never settled.

    The :class:`StrandedItem` is built **directly**, not routed through
    :func:`stranded_tasks`: the reporter already refuses terminal rows
    (``_STRANDED_CANDIDATE_STATUSES``), so reporting first would pre-filter the item
    and leave the guard inside :func:`settle_tasks` unexecuted — the case passed even
    with that guard broken (FIND-4). Handing the settle step an item it has to refuse
    is the only shape that can go red.
    """
    rows = [_row("T1", status=status, attempt=2, attempt_id="old.abc")]
    before = deepcopy(rows)
    items = (
        StrandedItem(
            id="T1",
            owner="backend",
            status=status,
            attempt=2,
            epochMismatch=True,
            idleSeconds=9_999,
            reason="epoch",
        ),
    )
    drafts, settled = settle_tasks(rows, items, at=1)
    assert (drafts, settled) == ([], [])
    assert rows == before


def test_settle_tasks_idempotent_second_pass_settles_nothing() -> None:
    """★ ``AC-A2-3``: a second settle returns an empty ``settled``."""
    rows = [_row("T1", status="doing", attempt=0, attempt_id="old.abc")]
    items = stranded_tasks({"run_id": "r1"}, rows, epoch="new", now=9_999_999)
    _, settled = settle_tasks(rows, items, at=1_700_000_000)
    assert settled == ["T1"]

    after = [_row("T1", status="todo", attempt=1, attempt_id=None)]
    assert stranded_tasks({"run_id": "r1"}, after, epoch="new", now=9_999_999) == ()
    assert settle_tasks(after, (), at=1_700_000_001) == ([], [])


def test_settle_tasks_output_is_a_valid_draft_source() -> None:
    """The normalisation target of a settled task is the same ``todo`` storage
    value :func:`normalize_draft` produces for a fresh draft."""
    rows = [_row("T1", status="doing", attempt=1, attempt_id="old.abc")]
    items = stranded_tasks({"run_id": "r1"}, rows, epoch="new", now=9_999_999)
    drafts, _ = settle_tasks(rows, items, at=5)
    assert (
        drafts[0]["status"]
        == normalize_draft(_draft(_draft_task()), roles=ROLES, run={})["tasks"][0]["status"]
    )
