"""Trigger string → APScheduler trigger."""

from __future__ import annotations

import datetime as dt
import re

from apscheduler.triggers.base import BaseTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from octop.infra.errors import ErrorCode, OctopError

_NUMERIC_DAY_OF_WEEK = re.compile(r"(?P<first>\*|\d+)(?:-(?P<last>\d+))?(?:/(?P<step>\d+))?")
_UNIX_WEEKDAYS = ("sun", "mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _unix_day_of_week(expression: str) -> str:
    """Translate numeric Unix weekdays to unambiguous names for APScheduler 3."""
    translated: list[str] = []
    for item in expression.split(","):
        match = _NUMERIC_DAY_OF_WEEK.fullmatch(item)
        if match is None:
            translated.append(item)
            continue

        first_text = match.group("first")
        last_text = match.group("last")
        step_text = match.group("step")
        if first_text == "*" and step_text is None:
            translated.append("*")
            continue

        first = 0 if first_text == "*" else int(first_text)
        last = int(last_text) if last_text is not None else (7 if step_text is not None else first)
        step = int(step_text) if step_text is not None else 1
        if not 0 <= first <= 7 or not 0 <= last <= 7:
            raise ValueError("weekday number must be in 0-7")
        if first > last:
            raise ValueError("weekday range start must not be greater than its end")
        if step <= 0:
            raise ValueError("weekday step must be greater than 0")

        for weekday in range(first, last + 1, step):
            name = _UNIX_WEEKDAYS[weekday]
            if name not in translated:
                translated.append(name)

    return ",".join(translated)


def _cron_trigger_from_unix_crontab(expression: str) -> CronTrigger:
    """Build a trigger whose weekday field follows Unix crontab semantics."""
    fields = expression.split()
    if len(fields) != 5:
        raise ValueError(f"Wrong number of fields; got {len(fields)}, expected 5")
    fields[4] = _unix_day_of_week(fields[4])
    return CronTrigger.from_crontab(" ".join(fields))


def build_trigger(spec: str) -> BaseTrigger:
    """Parse 'cron:<expr>' / 'interval:<seconds>' / 'date:<ISO>'."""
    if ":" not in spec:
        raise OctopError(ErrorCode.CRON_TRIGGER_INVALID, f"trigger spec missing kind: {spec!r}")
    kind, _, value = spec.partition(":")
    value = value.strip()
    if not value:
        raise OctopError(ErrorCode.CRON_TRIGGER_INVALID, f"trigger value empty: {spec!r}")
    try:
        if kind == "interval":
            return IntervalTrigger(seconds=int(value))
        if kind == "cron":
            return _cron_trigger_from_unix_crontab(value)
        if kind == "date":
            return DateTrigger(run_date=dt.datetime.fromisoformat(value))
    except (ValueError, TypeError) as exc:
        raise OctopError(
            ErrorCode.CRON_TRIGGER_INVALID,
            f"trigger spec {spec!r} could not be parsed: {exc}",
        ) from exc
    raise OctopError(ErrorCode.CRON_TRIGGER_INVALID, f"unknown trigger kind: {kind!r}")
