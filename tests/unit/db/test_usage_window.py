"""Unit tests for usage window resolution (server timezone day/month)."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from octop.infra.db.repos.usage import resolve_usage_window

TZ = "Asia/Shanghai"


def _ts(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> int:
    return int(datetime(year, month, day, hour, minute, tzinfo=ZoneInfo(TZ)).timestamp())


def test_resolve_day_window_shanghai() -> None:
    start, end = resolve_usage_window("day:2026-09-07", timezone=TZ)
    assert start == _ts(2026, 9, 7)
    assert end == _ts(2026, 9, 8)


def test_resolve_month_window_shanghai() -> None:
    start, end = resolve_usage_window("month:2026-09", timezone=TZ)
    assert start == _ts(2026, 9, 1)
    assert end == _ts(2026, 10, 1)


def test_resolve_month_december_rolls_year() -> None:
    start, end = resolve_usage_window("month:2025-12", timezone=TZ)
    assert start == _ts(2025, 12, 1)
    assert end == _ts(2026, 1, 1)


def test_resolve_today_uses_local_midnight() -> None:
    # 2026-09-07 15:30 CST
    now = _ts(2026, 9, 7, 15, 30)
    start, end = resolve_usage_window("today", timezone=TZ, now=now)
    assert start == _ts(2026, 9, 7)
    assert end == now + 1


def test_resolve_yesterday_local() -> None:
    now = _ts(2026, 9, 7, 10, 0)
    start, end = resolve_usage_window("yesterday", timezone=TZ, now=now)
    assert start == _ts(2026, 9, 6)
    assert end == _ts(2026, 9, 7)


def test_resolve_invalid_day_raises() -> None:
    with pytest.raises(ValueError, match="invalid usage window"):
        resolve_usage_window("day:2026-9-7", timezone=TZ)


def test_resolve_invalid_month_raises() -> None:
    with pytest.raises(ValueError, match="invalid usage window"):
        resolve_usage_window("month:2026-9", timezone=TZ)


def test_resolve_range_inclusive_days() -> None:
    start, end = resolve_usage_window("range:2026-09-01:2026-09-07", timezone=TZ)
    assert start == _ts(2026, 9, 1)
    assert end == _ts(2026, 9, 8)


def test_resolve_range_inverted_raises() -> None:
    with pytest.raises(ValueError, match="invalid usage window"):
        resolve_usage_window("range:2026-09-08:2026-09-07", timezone=TZ)
