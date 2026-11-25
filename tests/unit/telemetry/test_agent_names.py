"""Agent id -> name resolver with a TTL cache."""

from __future__ import annotations

from types import SimpleNamespace

from octop.infra.telemetry.agent_names import AgentNameResolver


class _FakeSource:
    def __init__(self, names: dict[str, str]) -> None:
        self.names = names
        self.calls = 0
        self.fail = False

    def get(self, agent_id: str) -> SimpleNamespace | None:
        self.calls += 1
        if self.fail:
            raise RuntimeError("db down")
        name = self.names.get(agent_id)
        return None if name is None else SimpleNamespace(name=name)


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_returns_name_and_caches() -> None:
    source = _FakeSource({"a1": "Writer"})
    resolver = AgentNameResolver(source, clock=_Clock())
    assert resolver.name_for("a1") == "Writer"
    assert resolver.name_for("a1") == "Writer"
    assert source.calls == 1


def test_rename_visible_after_ttl() -> None:
    clock = _Clock()
    source = _FakeSource({"a1": "Writer"})
    resolver = AgentNameResolver(source, ttl_s=30.0, clock=clock)
    assert resolver.name_for("a1") == "Writer"
    source.names["a1"] = "Editor"
    clock.now += 31.0
    assert resolver.name_for("a1") == "Editor"


def test_rename_not_visible_within_ttl() -> None:
    clock = _Clock()
    source = _FakeSource({"a1": "Writer"})
    resolver = AgentNameResolver(source, ttl_s=30.0, clock=clock)
    assert resolver.name_for("a1") == "Writer"
    source.names["a1"] = "Editor"
    clock.now += 10.0
    assert resolver.name_for("a1") == "Writer"


def test_missing_agent_returns_empty() -> None:
    resolver = AgentNameResolver(_FakeSource({}), clock=_Clock())
    assert resolver.name_for("ghost") == ""


def test_source_error_returns_empty_and_is_not_cached() -> None:
    source = _FakeSource({"a1": "Writer"})
    resolver = AgentNameResolver(source, clock=_Clock())
    source.fail = True
    assert resolver.name_for("a1") == ""
    source.fail = False
    assert resolver.name_for("a1") == "Writer"


def test_empty_agent_id_skips_source() -> None:
    source = _FakeSource({"": "x"})
    resolver = AgentNameResolver(source, clock=_Clock())
    assert resolver.name_for("") == ""
    assert source.calls == 0
