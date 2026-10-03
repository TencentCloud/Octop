"""Cross-process HITL bypass policy: ``threads.hitl_policy`` is the only state.

``octop run --workers N`` gives every worker its own :class:`HitlSessionPolicyStore`,
and a CLI run beside a live server opens the same database. A store that answers a
bypass decision from process-local memory therefore disagrees with the row: another
process revoking the bypass kept auto-approving tool calls, and another process
granting one stayed invisible.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from octop.infra.agents.security.hitl_session import (
    HitlSessionPolicy,
    HitlSessionPolicyStore,
)
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.threads import ThreadRepo
from octop.infra.db.repos.users import UserRepo


@pytest.fixture
def thread_repo(tmp_path: Path) -> ThreadRepo:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    UserRepo(db).create(username="u", password_hash="h", role="user")
    AgentRepo(db).create(agent_id="a1", user_id=1, name="Agent 1")
    repo = ThreadRepo(db)
    repo.insert(
        thread_id="thr_1",
        agent_id="a1",
        user_id=1,
        channel_type="dashboard",
        session_key="k",
    )
    return repo


def test_revoked_bypass_stops_in_the_other_worker(thread_repo: ThreadRepo) -> None:
    serving_api = HitlSessionPolicyStore(thread_repo)
    running_turn = HitlSessionPolicyStore(thread_repo)

    serving_api.set("thr_1", HitlSessionPolicy(mode="allow_all"))
    assert running_turn.allows("thr_1", "execute")

    serving_api.set("thr_1", HitlSessionPolicy())
    assert thread_repo.get("thr_1").hitl_policy is None
    assert not running_turn.allows("thr_1", "execute")


def test_granted_bypass_reaches_the_other_worker(thread_repo: ThreadRepo) -> None:
    serving_api = HitlSessionPolicyStore(thread_repo)
    running_turn = HitlSessionPolicyStore(thread_repo)

    assert running_turn.get("thr_1").mode == "ask"
    serving_api.set("thr_1", HitlSessionPolicy(mode="allow_tools", tools=("execute",)))
    assert running_turn.allows("thr_1", "execute")


def test_bypass_is_not_active_when_persisting_failed(
    thread_repo: ThreadRepo,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed row write must not leave a bypass that no reader can see."""

    def _locked(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("database is locked")

    monkeypatch.setattr(thread_repo, "update_composer", _locked)
    store = HitlSessionPolicyStore(thread_repo)
    with pytest.raises(RuntimeError):
        store.set("thr_1", HitlSessionPolicy(mode="allow_all"))
    assert not store.allows("thr_1", "execute")


def test_store_without_repo_keeps_turn_local_state() -> None:
    """An unwired store has nothing to read back from, so it keeps its own value."""
    store = HitlSessionPolicyStore()
    assert store.get("thr_1").mode == "ask"
    store.set("thr_1", HitlSessionPolicy(mode="allow_all"))
    assert store.allows("thr_1", "execute")

    store.replace_repo(None)
    assert not store.allows("thr_1", "execute")
