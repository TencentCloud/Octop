from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Dict, List
from zoneinfo import ZoneInfo

from skyfield import almanac, almanac_east_asia
from skyfield.api import Loader


DEFAULT_TIMEZONE = "Asia/Shanghai"
EPHEMERIS_NAME = "de440s.bsp"
SOLAR_TERM_NAMES = tuple(almanac_east_asia.SOLAR_TERMS_ZHS)
JIE_TO_MONTH = {
    "立春": 1,
    "惊蛰": 2,
    "清明": 3,
    "立夏": 4,
    "芒种": 5,
    "小暑": 6,
    "立秋": 7,
    "白露": 8,
    "寒露": 9,
    "立冬": 10,
    "大雪": 11,
    "小寒": 12,
}
JIE_NAMES = frozenset(JIE_TO_MONTH.keys())
QI_NAMES = frozenset(
    {
        "雨水",
        "春分",
        "谷雨",
        "小满",
        "夏至",
        "大暑",
        "处暑",
        "秋分",
        "霜降",
        "小雪",
        "冬至",
        "大寒",
    }
)


def _cache_dir() -> Path:
    path = Path.home() / ".cache" / "lao-huangli" / "skyfield"
    path.mkdir(parents=True, exist_ok=True)
    return path


@lru_cache(maxsize=1)
def _loader() -> Loader:
    return Loader(str(_cache_dir()))


@lru_cache(maxsize=1)
def _timescale():
    return _loader().timescale()


@lru_cache(maxsize=1)
def _ephemeris():
    return _loader()(EPHEMERIS_NAME)


def _to_local(dt: datetime, timezone_name: str) -> datetime:
    tz = ZoneInfo(timezone_name)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=tz)
    return dt.astimezone(tz)


def _format_local(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _format_term_event(event: Dict[str, object]) -> Dict[str, object]:
    return {
        "name": event["name"],
        "index": event["index"],
        "at": _format_local(event["at"]),
    }


def _select_term(events: List[Dict[str, object]], names: frozenset[str], dt: datetime) -> Dict[str, object]:
    candidates = [event for event in events if event["name"] in names]
    current = candidates[0]
    next_event = candidates[-1]
    for idx, event in enumerate(candidates):
        if event["at"] <= dt:
            current = event
            if idx + 1 < len(candidates):
                next_event = candidates[idx + 1]
            continue
        next_event = event
        break
    return {"current": current, "next": next_event}


@lru_cache(maxsize=16)
def list_new_moons_for_anchor_year(anchor_year: int, timezone_name: str = DEFAULT_TIMEZONE) -> List[Dict[str, object]]:
    tz = ZoneInfo(timezone_name)
    ts = _timescale()
    eph = _ephemeris()
    start = datetime(anchor_year, 11, 1, tzinfo=tz).astimezone(timezone.utc)
    end = datetime(anchor_year + 2, 2, 1, tzinfo=tz).astimezone(timezone.utc)
    times, phases = almanac.find_discrete(
        ts.from_datetime(start),
        ts.from_datetime(end),
        almanac.moon_phases(eph),
    )

    events: List[Dict[str, object]] = []
    for time_obj, phase in zip(times, phases):
        if int(phase) != 0:
            continue
        local_dt = time_obj.utc_datetime().astimezone(tz)
        events.append(
            {
                "at": local_dt,
                "date": local_dt.date(),
            }
        )
    return events


def _find_lunation_index(lunations: List[Dict[str, object]], dt: datetime) -> int:
    for idx, lunation in enumerate(lunations):
        if lunation["startAt"] <= dt < lunation["endAt"]:
            return idx
    raise ValueError(f"lunation not found for {dt.isoformat()}")


@lru_cache(maxsize=16)
def build_lunar_months_for_anchor_year(anchor_year: int, timezone_name: str = DEFAULT_TIMEZONE) -> List[Dict[str, object]]:
    new_moons = list_new_moons_for_anchor_year(anchor_year, timezone_name)
    solar_terms: List[Dict[str, object]] = []
    for year in (anchor_year, anchor_year + 1):
        solar_terms.extend(list_solar_terms_for_year(year, timezone_name))
    zhongqi = [event for event in solar_terms if event["name"] in QI_NAMES]

    lunations: List[Dict[str, object]] = []
    for idx in range(len(new_moons) - 1):
        start_at = new_moons[idx]["at"]
        end_at = new_moons[idx + 1]["at"]
        current_qi = next((event for event in zhongqi if start_at <= event["at"] < end_at), None)
        lunations.append(
            {
                "startAt": start_at,
                "endAt": end_at,
                "startDate": start_at.date(),
                "endDate": end_at.date(),
                "dayCount": (end_at.date() - start_at.date()).days,
                "zhongQi": None if current_qi is None else _format_term_event(current_qi),
                "containsZhongQi": current_qi is not None,
            }
        )

    winter_solstice = get_solar_term_occurrence(anchor_year, "冬至", timezone_name)
    next_winter_solstice = get_solar_term_occurrence(anchor_year + 1, "冬至", timezone_name)
    start_idx = _find_lunation_index(lunations, winter_solstice)
    next_idx = _find_lunation_index(lunations, next_winter_solstice)
    has_leap = (next_idx - start_idx) == 13
    leap_idx = None
    if has_leap:
        for idx in range(start_idx + 1, next_idx):
            if not lunations[idx]["containsZhongQi"]:
                leap_idx = idx
                break

    months: List[Dict[str, object]] = []
    current_lunar_year = anchor_year
    last_regular_month = 11

    for idx in range(start_idx, next_idx):
        lunation = dict(lunations[idx])
        if idx == start_idx:
            lunar_month = 11
            is_leap = False
            lunar_year = anchor_year
        elif leap_idx is not None and idx == leap_idx:
            lunar_month = last_regular_month
            is_leap = True
            lunar_year = current_lunar_year
        else:
            lunar_month = 1 if last_regular_month == 12 else last_regular_month + 1
            if lunar_month == 1:
                current_lunar_year += 1
            last_regular_month = lunar_month
            is_leap = False
            lunar_year = current_lunar_year

        lunation.update(
            {
                "anchorYear": anchor_year,
                "lunarYear": lunar_year,
                "lunarMonth": lunar_month,
                "isLeap": is_leap,
            }
        )
        months.append(lunation)

    return months


def get_lunar_month_context(dt: datetime, timezone_name: str = DEFAULT_TIMEZONE) -> Dict[str, object]:
    local_dt = _to_local(dt, timezone_name)
    target_date = local_dt.date()
    for anchor_year in (local_dt.year - 1, local_dt.year):
        for month in build_lunar_months_for_anchor_year(anchor_year, timezone_name):
            if month["startDate"] <= target_date < month["endDate"]:
                return month
    raise ValueError(f"lunar month context not found for {target_date.isoformat()}")


@lru_cache(maxsize=16)
def list_solar_terms_for_year(year: int, timezone_name: str = DEFAULT_TIMEZONE) -> List[Dict[str, object]]:
    tz = ZoneInfo(timezone_name)
    ts = _timescale()
    eph = _ephemeris()
    start = datetime(year - 1, 12, 1, tzinfo=tz).astimezone(timezone.utc)
    end = datetime(year + 1, 1, 31, 23, 59, 59, tzinfo=tz).astimezone(timezone.utc)
    times, indexes = almanac.find_discrete(
        ts.from_datetime(start),
        ts.from_datetime(end),
        almanac_east_asia.solar_terms(eph),
    )

    events: List[Dict[str, object]] = []
    for time_obj, index in zip(times, indexes):
        local_dt = time_obj.utc_datetime().astimezone(tz)
        events.append(
            {
                "index": int(index),
                "name": SOLAR_TERM_NAMES[int(index)],
                "at": local_dt,
            }
        )
    return events


def get_solar_term_window(dt: datetime, timezone_name: str = DEFAULT_TIMEZONE) -> Dict[str, object]:
    local_dt = _to_local(dt, timezone_name)
    events = list_solar_terms_for_year(local_dt.year, timezone_name)

    current_event = events[0]
    next_event = events[-1]
    for idx, event in enumerate(events):
        if event["at"] <= local_dt:
            current_event = event
            if idx + 1 < len(events):
                next_event = events[idx + 1]
            continue
        next_event = event
        break

    jie_events = _select_term(events, JIE_NAMES, local_dt)
    qi_events = _select_term(events, QI_NAMES, local_dt)
    table = {
        event["name"]: _format_local(event["at"])
        for event in events
        if event["at"].year == local_dt.year
    }

    return {
        "current": current_event["name"],
        "currentIndex": current_event["index"],
        "currentAt": _format_local(current_event["at"]),
        "next": next_event["name"],
        "nextIndex": next_event["index"],
        "nextAt": _format_local(next_event["at"]),
        "currentJieQi": _format_term_event(current_event),
        "nextJieQi": _format_term_event(next_event),
        "currentJie": _format_term_event(jie_events["current"]),
        "nextJie": _format_term_event(jie_events["next"]),
        "currentQi": _format_term_event(qi_events["current"]),
        "nextQi": _format_term_event(qi_events["next"]),
        "table": table,
        "precision": "astronomical",
        "calculationMode": "skyfield-jpl",
        "ephemerisName": EPHEMERIS_NAME,
        "timezone": timezone_name,
        "note": "节气按 Skyfield + JPL 星历计算，时刻为本地时区结果",
    }


def get_jieqi_month_for_datetime(dt: datetime, timezone_name: str = DEFAULT_TIMEZONE) -> int:
    current_jie = get_solar_term_window(dt, timezone_name)["currentJie"]["name"]
    return JIE_TO_MONTH[current_jie]


def get_solar_term_occurrence(year: int, term_name: str, timezone_name: str = DEFAULT_TIMEZONE) -> datetime:
    for event in list_solar_terms_for_year(year, timezone_name):
        if event["name"] == term_name and event["at"].year == year:
            return event["at"]
    raise ValueError(f"solar term not found: year={year}, term={term_name}")
