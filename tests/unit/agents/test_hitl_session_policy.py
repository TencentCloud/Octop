"""Thread-scoped HITL bypass policy."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from harness_agent.security.models import SecurityPolicy

from octop.config import OctopConfig
from octop.infra.agents.manager import AgentManager
from octop.infra.agents.security.hitl_session import (
    HitlSessionPolicy,
    HitlSessionPolicyStore,
    apply_session_bypass,
    current_hitl_thread_id,
    hitl_thread_scope,
    parse_hitl_session_policy,
    thread_id_from_request,
)


@pytest.fixture
def manager(tmp_path: Path) -> AgentManager:
    from octop.infra.db.migrate import run_migrations
    from octop.infra.db.pool import SqlitePool
    from octop.infra.db.services import build_shared_services
    from octop.infra.utils.paths import PathLayout

    paths = PathLayout(tmp_path / ".octop")
    paths.ensure_root()
    db = SqlitePool(paths.db)
    run_migrations(db)
    services = build_shared_services(db=db, paths=paths, config=OctopConfig())
    return AgentManager(repos=services.repos, paths=services.paths)


def test_parse_modes() -> None:
    assert parse_hitl_session_policy(None).mode == "ask"
    assert parse_hitl_session_policy('{"mode":"allow_all"}').mode == "allow_all"
    policy = parse_hitl_session_policy({"mode": "allow_tools", "tools": ["execute"]})
    assert policy == HitlSessionPolicy(mode="allow_tools", tools=("execute",))
    assert parse_hitl_session_policy({"mode": "allow_tools", "tools": []}).mode == "ask"


def test_allows_never_skips_ask_user() -> None:
    policy = HitlSessionPolicy(mode="allow_all")
    assert policy.allows("execute")
    assert not policy.allows("ask_user_question")
    tools = HitlSessionPolicy(mode="allow_tools", tools=("execute",))
    assert tools.allows("execute")
    assert not tools.allows("write_file")


def test_without_tools_returns_ask_when_empty() -> None:
    policy = HitlSessionPolicy(mode="allow_tools", tools=("execute", "write_file"))
    assert policy.without_tools(["write_file"]).tools == ("execute",)
    assert policy.without_tools(["execute", "write_file"]).mode == "ask"


def test_thread_id_from_request() -> None:
    assert thread_id_from_request({"thread_id": " thr_1 "}) == "thr_1"
    assert thread_id_from_request({"configurable": {"thread_id": "thr_2"}}) == "thr_2"
    assert thread_id_from_request({}) is None


def test_current_thread_id_is_unbound_outside_scope() -> None:
    assert current_hitl_thread_id() is None
    with hitl_thread_scope("thr_1"):
        assert current_hitl_thread_id() == "thr_1"
    assert current_hitl_thread_id() is None


def test_wrap_skips_when_thread_allows_all() -> None:
    store = HitlSessionPolicyStore()
    store.set("thr_1", HitlSessionPolicy(mode="allow_all"))
    wrapped = apply_session_bypass({"execute": {}, "ask_user_question": {}}, store)
    assert wrapped is not None
    assert "when" not in wrapped["ask_user_question"]
    with hitl_thread_scope("thr_1"):
        assert wrapped["execute"]["when"](None) is False
    with hitl_thread_scope("other"):
        assert wrapped["execute"]["when"](None) is True


def test_wrap_respects_original_when() -> None:
    store = HitlSessionPolicyStore()
    store.set("thr_1", HitlSessionPolicy(mode="ask"))
    wrapped = apply_session_bypass(
        {"write_file": {"when": lambda _req: False}},
        store,
    )
    assert wrapped is not None
    with hitl_thread_scope("thr_1"):
        assert wrapped["write_file"]["when"](None) is False


def test_store_set_persists_once() -> None:
    repo = MagicMock()
    store = HitlSessionPolicyStore(repo)
    store.set("thr_1", {"mode": "allow_tools", "tools": ["bash"]})
    repo.update_composer.assert_called_once_with(
        "thr_1", hitl_policy='{"mode": "allow_tools", "tools": ["bash"]}'
    )
    assert store.get("thr_1").allows("bash")
    repo.get.assert_not_called()


@pytest.mark.asyncio
async def test_resume_hitl_binds_thread_scope() -> None:
    seen: list[str | None] = []

    async def fake_resume(agent_id: str, thread_id: str, decisions: list[dict[str, Any]]) -> Any:
        seen.append(current_hitl_thread_id())
        if False:
            yield {}

    manager = AgentManager.__new__(AgentManager)
    manager._harness_manager = SimpleNamespace(resume_hitl=fake_resume)
    manager._history_backfills = {}
    manager._invocation_waiters = {}
    manager._active_invocations = {}
    manager._thread_execution_locks = {}
    manager._bootstrap_graph_refresh_pending = set()

    chunks = [item async for item in manager.resume_hitl("agt", "thr_live", [{"type": "approve"}])]
    assert chunks == []
    assert seen == ["thr_live"]
    assert current_hitl_thread_id() is None


def test_build_harness_config_skips_interrupt_for_allowed_thread(
    manager: AgentManager,
) -> None:
    from tests.unit.agents.test_agent_manager import _row, _seed_test_provider

    _seed_test_provider(manager)
    manager._security.save(
        SecurityPolicy.from_dict({"hitl": {"enabled": True, "tools": ["write_file"]}})
    )
    store = HitlSessionPolicyStore()
    store.set("thr_1", HitlSessionPolicy(mode="allow_all"))
    manager.set_hitl_session_store(store)
    cfg = manager._build_harness_config(_row())
    assert cfg.interrupt_on is not None
    write_cfg = cfg.interrupt_on["write_file"]
    assert callable(write_cfg.get("when"))
    with hitl_thread_scope("thr_1"):
        assert write_cfg["when"](None) is False
    with hitl_thread_scope("other"):
        assert write_cfg["when"](None) is True
