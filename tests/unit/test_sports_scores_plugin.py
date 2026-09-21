"""The bundled sports-scores plugin must honour its league argument and null scores."""

from __future__ import annotations

import importlib.util
import json
from typing import Any

import pytest

from octop.infra.agents.plugins.bundled import default_bundled_plugins_root


def _load_sports_scores():
    path = default_bundled_plugins_root() / "sports-scores" / "main.py"
    spec = importlib.util.spec_from_file_location("bundled_sports_scores", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _FakeResp:
    def __init__(self, payload: Any) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self._payload


class _RecordingClient:
    calls: list[Any] = []
    payload: Any = {"event": []}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def __enter__(self) -> _RecordingClient:
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def get(self, url: str, **kwargs: Any) -> _FakeResp:
        type(self).calls.append((url, kwargs.get("params")))
        return _FakeResp(self.payload)


@pytest.fixture(autouse=True)
def _reset_client() -> Any:
    _RecordingClient.calls = []
    _RecordingClient.payload = {"event": []}


def _data(raw: str) -> dict[str, Any]:
    return json.loads(raw)["data"]


@pytest.mark.asyncio
async def test_numeric_league_id_is_passed_through(monkeypatch: Any) -> None:
    mod = _load_sports_scores()
    monkeypatch.setattr(mod.httpx, "Client", _RecordingClient)
    await mod.sports_scores(league="4331")
    assert _RecordingClient.calls[0][1] == {"id": "4331"}


@pytest.mark.parametrize("league", ["epl", "EPL", "soccer", "4328", ""])
@pytest.mark.asyncio
async def test_epl_aliases_still_use_the_default_league(monkeypatch: Any, league: str) -> None:
    mod = _load_sports_scores()
    monkeypatch.setattr(mod.httpx, "Client", _RecordingClient)
    await mod.sports_scores(league=league)
    assert _RecordingClient.calls[0][1] == {"id": "4328"}


@pytest.mark.asyncio
async def test_unknown_league_name_is_rejected_without_fetching(monkeypatch: Any) -> None:
    mod = _load_sports_scores()
    monkeypatch.setattr(mod.httpx, "Client", _RecordingClient)
    data = _data(await mod.sports_scores(league="nba"))
    assert data["error"] == "unknown league"
    assert _RecordingClient.calls == []


@pytest.mark.asyncio
async def test_null_scores_render_as_dash_not_none(monkeypatch: Any) -> None:
    mod = _load_sports_scores()
    _RecordingClient.payload = {
        "event": [
            {
                "strEvent": "Arsenal vs Chelsea",
                "strHomeTeam": "Arsenal",
                "strAwayTeam": "Chelsea",
                "intHomeScore": None,
                "intAwayScore": None,
                "dateEvent": "2026-09-26",
            },
            {
                "strEvent": "Everton vs Liverpool",
                "strHomeTeam": "Everton",
                "strAwayTeam": "Liverpool",
                "intHomeScore": "0",
                "intAwayScore": "0",
                "dateEvent": "2026-09-19",
            },
        ]
    }
    monkeypatch.setattr(mod.httpx, "Client", _RecordingClient)
    items = _data(await mod.sports_scores())["items"]
    assert items[0]["score"] == "-"
    assert items[1]["score"] == "0 - 0"
