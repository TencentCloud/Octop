"""tests/unit/test_cron_trigger.py"""

from __future__ import annotations

import datetime as dt

import pytest
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from octop.infra.cron.trigger import build_trigger
from octop.infra.errors import ErrorCode, OctopError


def test_interval_seconds():
    trig = build_trigger("interval:60")
    assert isinstance(trig, IntervalTrigger)
    assert trig.interval == dt.timedelta(seconds=60)


def test_cron_expression():
    trig = build_trigger("cron:0 9 * * *")
    assert isinstance(trig, CronTrigger)


def _next_weekdays(trig: CronTrigger, *, count: int) -> list[int]:
    next_fire = trig.get_next_fire_time(None, dt.datetime(2026, 8, 8, 12, tzinfo=trig.timezone))
    actual: list[int] = []
    while next_fire is not None and len(actual) < count:
        actual.append(next_fire.weekday())
        next_fire = trig.get_next_fire_time(next_fire, next_fire)
    return actual


@pytest.mark.parametrize(
    ("weekday", "expected_weekday"),
    [
        ("0", 6),  # Sunday
        ("7", 6),  # Sunday (Unix alias)
        ("1", 0),  # Monday
        ("2", 1),  # Tuesday
        ("3", 2),  # Wednesday
        ("4", 3),  # Thursday
        ("5", 4),  # Friday
        ("6", 5),  # Saturday
        ("sun", 6),
        ("mon", 0),
        ("fri", 4),
        ("sat", 5),
        ("SUN", 6),
        ("Mon", 0),
    ],
)
def test_cron_weekday_uses_unix_semantics(weekday: str, expected_weekday: int):
    trig = build_trigger(f"cron:0 9 * * {weekday}")
    assert isinstance(trig, CronTrigger)
    assert _next_weekdays(trig, count=1) == [expected_weekday]


@pytest.mark.parametrize(
    ("weekday", "expected_weekdays"),
    [
        ("1-5", [0, 1, 2, 3, 4]),  # Mon-Fri
        ("mon-fri", [0, 1, 2, 3, 4]),
        ("0-6", [6, 0, 1, 2, 3, 4, 5]),  # every day via numeric range
        ("5-7", [6, 4, 5]),  # Fri-Sun; after Sat noon → Sun,Fri,Sat
        ("*/2", [6, 1, 3, 5]),  # Sun,Tue,Thu,Sat
        ("1-5/2", [0, 2, 4]),  # Mon,Wed,Fri
        ("1/2", [6, 0, 2, 4]),  # Mon,Wed,Fri,Sun; after Sat noon → Sun first
        ("0,6", [6, 5]),  # Sun,Sat
        ("1,3,5", [0, 2, 4]),  # Mon,Wed,Fri
        ("0,7", [6]),  # both Sunday aliases; deduped
        ("sun,sat", [6, 5]),
        ("0,sat", [6, 5]),  # mixed numeric + name
    ],
)
def test_cron_weekday_ranges_use_unix_semantics(weekday: str, expected_weekdays: list[int]):
    trig = build_trigger(f"cron:0 9 * * {weekday}")
    assert isinstance(trig, CronTrigger)
    assert _next_weekdays(trig, count=len(expected_weekdays)) == expected_weekdays


def test_date_iso():
    trig = build_trigger("date:2026-12-31T09:00:00")
    assert isinstance(trig, DateTrigger)


def test_unknown_kind_raises():
    with pytest.raises(OctopError) as ei:
        build_trigger("webhook:foo")
    assert ei.value.code is ErrorCode.CRON_TRIGGER_INVALID


def test_missing_colon_raises():
    with pytest.raises(OctopError):
        build_trigger("interval60")


def test_malformed_cron_raises():
    with pytest.raises(OctopError):
        build_trigger("cron:not a cron")


@pytest.mark.parametrize(
    "weekday",
    [
        "8",
        "5-1",
        "1/0",
        "*/0",
        "foo",
    ],
)
def test_cron_rejects_invalid_weekday(weekday: str):
    with pytest.raises(OctopError):
        build_trigger(f"cron:0 9 * * {weekday}")
