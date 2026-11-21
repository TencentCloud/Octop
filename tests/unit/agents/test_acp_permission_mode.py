"""Managed turns read the chat approval switch."""

from __future__ import annotations

from octop.infra.agents.acp.turn import acp_permission_mode


class _Policy:
    def __init__(self, mode: str) -> None:
        self.mode = mode


class _Store:
    def __init__(self, mode: str) -> None:
        self._mode = mode

    def get(self, thread_id: str) -> _Policy:
        assert thread_id == "thr"
        return _Policy(self._mode)


class _Manager:
    def __init__(self, mode: str) -> None:
        self._hitl_session_store = _Store(mode)


def test_allow_all_chat_is_yolo() -> None:
    request = {"thread_id": "thr", "configurable": {}}
    assert acp_permission_mode(_Manager("allow_all"), request) == "yolo"


def test_ask_is_the_default() -> None:
    assert acp_permission_mode(object(), {"thread_id": "thr"}) == "ask"
    request = {"thread_id": "thr", "configurable": {}}
    assert acp_permission_mode(_Manager("ask"), request) == "ask"


def test_explicit_mode_on_the_request_wins() -> None:
    request = {"thread_id": "thr", "configurable": {"acp_permission_mode": "ask"}}
    assert acp_permission_mode(_Manager("allow_all"), request) == "ask"


class _ThreadRow:
    def __init__(self, raw: str | None) -> None:
        self.hitl_policy = raw


class _ThreadRepo:
    def __init__(self, raw: str | None) -> None:
        self._raw = raw

    def get(self, thread_id: str) -> _ThreadRow:
        assert thread_id == "thr"
        return _ThreadRow(self._raw)


class _PersistedStore:
    def __init__(self, raw: str | None) -> None:
        self._repo = _ThreadRepo(raw)


class _AgentRow:
    config_json = '{"managed_permission_mode": "yolo"}'


class _AgentRepo:
    def get(self, agent_id: str) -> _AgentRow:
        assert agent_id == "agt"
        return _AgentRow()


class _Repos:
    agent_repo = _AgentRepo()


class _ExpertManager:
    def __init__(self, raw: str | None) -> None:
        self._hitl_session_store = _PersistedStore(raw)
        self._repos = _Repos()


def test_new_chat_inherits_the_expert_yolo_default() -> None:
    request = {"thread_id": "thr", "configurable": {}}
    assert acp_permission_mode(_ExpertManager(None), request, "agt") == "yolo"


def test_explicit_ask_on_the_chat_beats_the_expert_default() -> None:
    request = {"thread_id": "thr", "configurable": {}}
    assert acp_permission_mode(_ExpertManager('{"mode": "ask"}'), request, "agt") == "ask"
