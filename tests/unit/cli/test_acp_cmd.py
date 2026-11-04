"""Unit tests for inbound ``octop acp`` expert catalog helpers."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import click
import pytest

from octop.cli.commands.acp import (
    _ensure_running_harness,
    _load_acp_experts,
    _resolve_agent_ref,
    _resolve_default_agent_id,
    _running_experts,
)


class _Registry:
    def __init__(self, rows: list[Any], running: set[str]) -> None:
        self._rows = rows
        self._running = running

    def list_rows(self) -> list[Any]:
        return list(self._rows)

    def get_agent(self, agent_id: str) -> object:
        if agent_id not in self._running:
            raise KeyError(agent_id)
        return object()

    def get_row(self, agent_id: str) -> Any:
        for row in self._rows:
            if row.agent_id == agent_id:
                return row
        return None


def test_resolve_default_agent_id_uses_explicit() -> None:
    rows = [SimpleNamespace(agent_id="explicit", name="Explicit", description="")]
    reg = _Registry(rows, set())
    assert _resolve_default_agent_id(reg, "explicit") == "explicit"


def test_resolve_default_agent_id_falls_back_to_first_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "octop.cli.support.state.load",
        lambda _path: SimpleNamespace(default_agent=None),
    )
    monkeypatch.setattr(
        "octop.cli.support.state.default_state_path",
        lambda: "/tmp/cli_state.json",
    )
    rows = [SimpleNamespace(agent_id="a1"), SimpleNamespace(agent_id="a2")]
    reg = _Registry(rows, {"a1", "a2"})
    assert _resolve_default_agent_id(reg, None) == "a1"


def test_resolve_default_agent_id_errors_when_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "octop.cli.support.state.load",
        lambda _path: SimpleNamespace(default_agent=None),
    )
    monkeypatch.setattr(
        "octop.cli.support.state.default_state_path",
        lambda: "/tmp/cli_state.json",
    )
    with pytest.raises(click.ClickException, match="no agent found"):
        _resolve_default_agent_id(_Registry([], set()), None)


def test_running_experts_skips_stopped_agents() -> None:
    rows = [
        SimpleNamespace(agent_id="run", name="Run", description="ok"),
        SimpleNamespace(agent_id="stop", name="Stop", description="no"),
    ]
    experts = _running_experts(_Registry(rows, {"run"}))
    assert [e.value for e in experts] == ["run"]
    assert experts[0].name == "Run"
    assert experts[0].description == "ok"


def test_resolve_agent_ref_accepts_id_or_name() -> None:
    rows = [
        SimpleNamespace(agent_id="Y92KN8", name="dev", description=""),
        SimpleNamespace(agent_id="OTHER1", name="Ops", description=""),
    ]
    reg = _Registry(rows, {"Y92KN8", "OTHER1"})
    assert _resolve_agent_ref(reg, "Y92KN8") == "Y92KN8"
    assert _resolve_agent_ref(reg, "dev") == "Y92KN8"
    assert _resolve_agent_ref(reg, "DEV") == "Y92KN8"


def test_resolve_agent_ref_ambiguous_name_errors() -> None:
    rows = [
        SimpleNamespace(agent_id="A1", name="Twin", description=""),
        SimpleNamespace(agent_id="A2", name="twin", description=""),
    ]
    with pytest.raises(click.ClickException, match="ambiguous"):
        _resolve_agent_ref(_Registry(rows, set()), "Twin")


def test_resolve_default_agent_id_resolves_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "octop.cli.support.state.load",
        lambda _path: SimpleNamespace(default_agent=None),
    )
    monkeypatch.setattr(
        "octop.cli.support.state.default_state_path",
        lambda: "/tmp/cli_state.json",
    )
    rows = [SimpleNamespace(agent_id="Y92KN8", name="dev", description="")]
    reg = _Registry(rows, {"Y92KN8"})
    assert _resolve_default_agent_id(reg, "dev") == "Y92KN8"


def test_load_acp_experts_lists_all_and_puts_default_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        SimpleNamespace(agent_id="a1", name="Alpha", description="one"),
        SimpleNamespace(agent_id="a2", name="Beta", description="two"),
    ]

    class _Svc:
        class agent_repo:
            @staticmethod
            def list_all(*, include_disabled: bool = False) -> list[Any]:
                assert include_disabled is False
                return rows

    class _CM:
        def __enter__(self) -> _Svc:
            return _Svc()

        def __exit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr("octop.cli.support.db.open_cli_services", lambda: _CM())
    monkeypatch.setattr(
        "octop.cli.support.state.load",
        lambda _path: SimpleNamespace(default_agent=None),
    )
    monkeypatch.setattr(
        "octop.cli.support.state.default_state_path",
        lambda: "/tmp/cli_state.json",
    )

    default_id, experts = _load_acp_experts(None)
    assert default_id == "a1"
    assert [e.value for e in experts] == ["a1", "a2"]

    default_id, experts = _load_acp_experts("Beta")
    assert default_id == "a2"
    assert [e.value for e in experts] == ["a2", "a1"]
    assert experts[0].name == "Beta"


@pytest.mark.asyncio
async def test_ensure_running_harness_starts_stopped_agent() -> None:
    rows = [SimpleNamespace(agent_id="ops", name="Ops", description="")]
    reg = _Registry(rows, set())
    started: list[str] = []

    async def _start(agent_id: str) -> None:
        started.append(agent_id)
        reg._running.add(agent_id)

    reg.start = _start  # type: ignore[method-assign]
    harness = await _ensure_running_harness(reg, "ops")
    assert harness is not None
    assert started == ["ops"]
