"""Built-in tool: ``current_time``.

Returns the current wall-clock time with timezone info **and** the weekday
in both English and Chinese. Emitting the weekday explicitly removes a
common LLM failure mode where the model has to compute day-of-week from a
date via mental arithmetic (and gets it wrong).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from langchain_core.tools import tool

# Authoritative weekday labels — the LLM should never re-derive the day of
# week from the date string.
_WEEKDAY_EN: tuple[str, ...] = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)
_WEEKDAY_ZH: tuple[str, ...] = (
    "周一",
    "周二",
    "周三",
    "周四",
    "周五",
    "周六",
    "周日",
)


def _format_now(now: datetime) -> str:
    """Render a datetime as ``YYYY-MM-DD HH:MM:SS TZ (UTC±HHMM) Weekday (周X)``.

    Falls back gracefully when the datetime is naive (no tzinfo): we drop
    the ``%Z (UTC%z)`` segment rather than letting strftime emit empty
    parens.
    """
    idx = now.weekday()  # 0=Mon .. 6=Sun
    weekday = f"{_WEEKDAY_EN[idx]} ({_WEEKDAY_ZH[idx]})"
    if now.tzinfo is None:
        return f"{now.strftime('%Y-%m-%d %H:%M:%S')} {weekday}"
    return f"{now.strftime('%Y-%m-%d %H:%M:%S %Z (UTC%z)')} {weekday}"


def _resolve_now(tz: str | None, default_timezone: str | None) -> datetime:
    chosen = tz if tz is not None else default_timezone
    if chosen:
        return datetime.now(ZoneInfo(chosen))
    return datetime.now().astimezone()


class CurrentTimeTool:
    def __init__(self, default_timezone: str | None = None) -> None:
        self._default_timezone = default_timezone

    def as_tool(self) -> Any:
        default_timezone = self._default_timezone

        @tool
        def current_time(tz: str | None = None) -> str:
            """Return the current wall-clock time with timezone info and weekday.

            The output bundles three things the LLM regularly needs but tends to
            get wrong on its own: the date, the timezone offset, and the day of
            the week (in both English and Chinese). Treat the weekday in the
            response as authoritative.

            Args:
                tz: Optional IANA timezone name, e.g. ``"Asia/Shanghai"`` or
                    ``"UTC"``. When omitted, the agent's configured default
                    timezone is used; if unset, the system local timezone is used.

            Returns:
                Human-readable timestamp, for example
                ``"2026-05-22 16:51:00 CST (UTC+0800) Friday (周五)"``.
                Unknown timezones return ``"Error: …"`` (does not raise).
            """
            try:
                return _format_now(_resolve_now(tz, default_timezone))
            except ZoneInfoNotFoundError:
                chosen = tz if tz is not None else default_timezone
                return f"Error: Unknown timezone: {chosen!r}. Pass an IANA name such as 'Asia/Shanghai' or 'UTC'."

        return current_time


current_time = CurrentTimeTool().as_tool()
