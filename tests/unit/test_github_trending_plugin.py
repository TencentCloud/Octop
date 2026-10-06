"""github-trending must derive its `created:` cutoff from UTC, not the host clock.

GitHub compares the `created:` qualifier against `created_at` in UTC, while
`date.today()` follows the host calendar day. In the repo's default timezone
(Asia/Shanghai, UTC+8) the two disagree for part of every day, so the same tool
call produced different queries on different hosts.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import re
import time
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest

from octop.infra.agents.plugins.bundled import default_bundled_plugins_root

posix_only = pytest.mark.skipif(os.name != "posix", reason="time.tzset() is POSIX-only")

# UTC+14 and UTC-11: their calendar day always differs, whatever the current instant.
EAST = "Pacific/Kiritimati"
WEST = "Pacific/Pago_Pago"


def _load_plugin():
    path = default_bundled_plugins_root() / "github-trending" / "main.py"
    spec = importlib.util.spec_from_file_location("bundled_github_trending", path)
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
    last_params: dict[str, Any] = {}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def __enter__(self) -> _RecordingClient:
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def get(self, url: str, **kwargs: Any) -> _FakeResp:
        type(self).last_params = dict(kwargs.get("params") or {})
        return _FakeResp({"items": []})


@contextmanager
def _host_timezone(name: str):
    previous = os.environ.get("TZ")
    os.environ["TZ"] = name
    time.tzset()
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = previous
        time.tzset()


def _query_for(since: str, tz: str, monkeypatch: pytest.MonkeyPatch) -> date:
    mod = _load_plugin()
    monkeypatch.setattr(mod.httpx, "Client", _RecordingClient)
    with _host_timezone(tz):
        asyncio.run(mod.github_trending(language="python", since=since, limit=5))
    params = _RecordingClient.last_params
    created = re.search(r"created:([<>]=?)(\d{4}-\d{2}-\d{2})", str(params.get("q") or ""))
    assert created is not None, f"no created: cutoff in {params!r}"
    return date.fromisoformat(created.group(2))


@posix_only
def test_daily_cutoff_is_the_same_on_every_host_timezone(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _query_for("daily", EAST, monkeypatch) == _query_for("daily", WEST, monkeypatch)


@posix_only
def test_weekly_and_monthly_cutoffs_are_the_same_on_every_host_timezone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for since in ("weekly", "monthly"):
        assert _query_for(since, EAST, monkeypatch) == _query_for(since, WEST, monkeypatch), since


@posix_only
def test_daily_cutoff_is_anchored_to_the_utc_day(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = datetime.now(UTC).date() - timedelta(days=1)
    assert _query_for("daily", "Asia/Shanghai", monkeypatch) == expected
