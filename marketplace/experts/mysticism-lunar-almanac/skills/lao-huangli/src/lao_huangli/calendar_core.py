from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from zoneinfo import ZoneInfo

from lao_huangli.astronomy import (
    DEFAULT_TIMEZONE,
    EPHEMERIS_NAME,
    get_lunar_month_context,
    build_lunar_months_for_anchor_year,
    get_jieqi_month_for_datetime,
    get_solar_term_occurrence,
    get_solar_term_window,
)


TIANGAN = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
DIZHI = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
SHENGXIAO = ["鼠", "牛", "虎", "兔", "龙", "蛇", "马", "羊", "猴", "鸡", "狗", "猪"]

DAY_GANZHI_REFERENCE_DATE = (1949, 10, 1)
YEAR_GANZHI_REFERENCE_YEAR = 1984

# GB/T 33661-2017 指定 1949-10-01 对应甲子日。
DAY_GANZHI_BASE_JDN = 2433191

SHICHEN_SEGMENTS = [
    ("子", "23:00-00:59"),
    ("丑", "01:00-02:59"),
    ("寅", "03:00-04:59"),
    ("卯", "05:00-06:59"),
    ("辰", "07:00-08:59"),
    ("巳", "09:00-10:59"),
    ("午", "11:00-12:59"),
    ("未", "13:00-14:59"),
    ("申", "15:00-16:59"),
    ("酉", "17:00-18:59"),
    ("戌", "19:00-20:59"),
    ("亥", "21:00-22:59"),
]

HOUR_TO_SHICHEN_INDEX = {
    23: 0,
    0: 0,
    1: 1,
    2: 1,
    3: 2,
    4: 2,
    5: 3,
    6: 3,
    7: 4,
    8: 4,
    9: 5,
    10: 5,
    11: 6,
    12: 6,
    13: 7,
    14: 7,
    15: 8,
    16: 8,
    17: 9,
    18: 9,
    19: 10,
    20: 10,
    21: 11,
    22: 11,
}

YEAR_INFOS = [
    0x04BD8, 0x04AE0, 0x0A570, 0x054D5, 0x0D260, 0x0D950, 0x16554, 0x056A0, 0x09AD0, 0x055D2,
    0x04AE0, 0x0A5B6, 0x0A4D0, 0x0D250, 0x1D255, 0x0B540, 0x0D6A0, 0x0ADA2, 0x095B0, 0x14977,
    0x04970, 0x0A4B0, 0x0B4B5, 0x06A50, 0x06D40, 0x1AB54, 0x02B60, 0x09570, 0x052F2, 0x04970,
    0x06566, 0x0D4A0, 0x0EA50, 0x06E95, 0x05AD0, 0x02B60, 0x186E3, 0x092E0, 0x1C8D7, 0x0C950,
    0x0D4A0, 0x1D8A6, 0x0B550, 0x056A0, 0x1A5B4, 0x025D0, 0x092D0, 0x0D2B2, 0x0A950, 0x0B557,
    0x06CA0, 0x0B550, 0x15355, 0x04DA0, 0x0A5D0, 0x14573, 0x052D0, 0x0A9A8, 0x0E950, 0x06AA0,
    0x0AEA6, 0x0AB50, 0x04B60, 0x0AAE4, 0x0A570, 0x05260, 0x0F263, 0x0D950, 0x05B57, 0x056A0,
    0x096D0, 0x04DD5, 0x04AD0, 0x0A4D0, 0x0D4D4, 0x0D250, 0x0D558, 0x0B540, 0x0B5A0, 0x195A6,
    0x095B0, 0x049B0, 0x0A974, 0x0A4B0, 0x0B27A, 0x06A50, 0x06D40, 0x0AF46, 0x0AB60, 0x09570,
    0x04AF5, 0x04970, 0x064B0, 0x074A3, 0x0EA50, 0x06B58, 0x05AC0, 0x0AB60, 0x096D5, 0x092E0,
    0x0C960, 0x0D954, 0x0D4A0, 0x0DA50, 0x07552, 0x056A0, 0x0ABB7, 0x025D0, 0x092D0, 0x0CAB5,
    0x0A950, 0x0B4A0, 0x0BAA4, 0x0AD50, 0x055D9, 0x04BA0, 0x0A5B0, 0x15176, 0x052B0, 0x0A930,
    0x07954, 0x06AA0, 0x0AD50, 0x05B52, 0x04B60, 0x0A6E6, 0x0A4E0, 0x0D260, 0x0EA65, 0x0D530,
    0x05AA0, 0x076A3, 0x096D0, 0x04AFB, 0x04AD0, 0x0A4D0, 0x1D0B6, 0x0D250, 0x0D520, 0x0DD45,
    0x0B5A0, 0x056D0, 0x055B2, 0x049B0, 0x0A577, 0x0A4B0, 0x0AA50, 0x1B255, 0x06D20, 0x0ADA0,
    0x14B63, 0x09370, 0x049F8, 0x04970, 0x064B0, 0x168A6, 0x0EA50, 0x06AA0, 0x1A6C4, 0x0AAE0,
    0x092E0, 0x0D2E3, 0x0C960, 0x0D557, 0x0D4A0, 0x0DA50, 0x05D55, 0x056A0, 0x0A6D0, 0x055D4,
    0x052D0, 0x0A9B8, 0x0A950, 0x0B4A0, 0x0B6A6, 0x0AD50, 0x055A0, 0x0ABA4, 0x0A5B0, 0x052B0,
    0x0B273, 0x06930, 0x07337, 0x06AA0, 0x0AD50, 0x14B55, 0x04B60, 0x0A570, 0x054E4, 0x0D160,
    0x0E968, 0x0D520, 0x0DAA0, 0x16AA6, 0x056D0, 0x04AE0, 0x0A9D4, 0x0A2D0, 0x0D150, 0x0F252,
]

LUNAR_START_DATE = datetime(1900, 1, 31)

CHINESE_WEEKDAY = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]


@dataclass
class CalendarCoreInput:
    year: int
    month: int
    day: int
    hour: int
    year_boundary: str
    day_boundary: str


def _year_days(year_info: int) -> int:
    days = 29 * 12
    leap_month = year_info & 0xF
    if leap_month:
        days += 29
        if (year_info >> 16) & 1:
            days += 1
    for month in range(1, 13):
        if (year_info >> (16 - month)) & 1:
            days += 1
    return days


def _month_days(year_info: int, month: int, is_leap: bool = False) -> int:
    if is_leap:
        return 30 if (year_info >> 16) & 1 else 29
    return 30 if (year_info >> (16 - month)) & 1 else 29


def _gregorian_to_lunar_table(year: int, month: int, day: int) -> Tuple[int, int, int, bool]:
    if year < 1900 or year > 2099:
        raise ValueError("year out of range 1900-2099")

    target = datetime(year, month, day)
    offset = (target - LUNAR_START_DATE).days
    if offset < 0:
        raise ValueError("date before 1900-01-31")

    lunar_year = 1900
    idx = 0
    while idx < len(YEAR_INFOS):
        year_info = YEAR_INFOS[idx]
        ydays = _year_days(year_info)
        if offset < ydays:
            break
        offset -= ydays
        lunar_year += 1
        idx += 1

    year_info = YEAR_INFOS[idx]
    leap_month = year_info & 0xF

    for current_month in range(1, 13):
        mdays = _month_days(year_info, current_month, False)
        if offset < mdays:
            return lunar_year, current_month, offset + 1, False
        offset -= mdays

        if current_month == leap_month:
            ldays = _month_days(year_info, current_month, True)
            if offset < ldays:
                return lunar_year, current_month, offset + 1, True
            offset -= ldays

    raise ValueError("lunar conversion failed")


def gregorian_to_lunar(year: int, month: int, day: int) -> Tuple[int, int, int, bool, Dict[str, object]]:
    target = datetime(year, month, day, 12)
    try:
        month_context = get_lunar_month_context(target, DEFAULT_TIMEZONE)
        lunar_day = (target.date() - month_context["startDate"]).days + 1
        year_months = get_lunar_months_for_year(int(month_context["lunarYear"]))
        year_leap_month = next((int(month["lunarMonth"]) for month in year_months if month["isLeap"]), 0)
        current_month_index = next(
            (
                idx
                for idx, month in enumerate(year_months, start=1)
                if month["startDate"] == month_context["startDate"] and bool(month["isLeap"]) == bool(month_context["isLeap"])
            ),
            0,
        )
        return (
            int(month_context["lunarYear"]),
            int(month_context["lunarMonth"]),
            int(lunar_day),
            bool(month_context["isLeap"]),
            {
                "monthStartDate": month_context["startDate"].isoformat(),
                "monthEndDate": month_context["endDate"].isoformat(),
                "monthDayCount": int(month_context["dayCount"]),
                "leapMonth": 0 if not month_context["isLeap"] else int(month_context["lunarMonth"]),
                "zhongQi": month_context["zhongQi"],
                "containsZhongQi": bool(month_context["containsZhongQi"]),
                "anchorYear": int(month_context["anchorYear"]),
                "yearMonthTable": [_serialize_lunar_month(month) for month in year_months],
                "yearMonthCount": len(year_months),
                "yearLeapMonth": year_leap_month,
                "currentMonthIndex": current_month_index,
                "ephemerisName": EPHEMERIS_NAME,
                "calculationMode": "astronomical-lunation-table",
            },
        )
    except ValueError:
        lunar_year, lunar_month, lunar_day, is_leap = _gregorian_to_lunar_table(year, month, day)
        return (
            lunar_year,
            lunar_month,
            lunar_day,
            is_leap,
            {
                "monthStartDate": None,
                "monthEndDate": None,
                "monthDayCount": None,
                "leapMonth": 0,
                "zhongQi": None,
                "containsZhongQi": None,
                "anchorYear": None,
                "yearMonthTable": [],
                "yearMonthCount": None,
                "yearLeapMonth": 0,
                "currentMonthIndex": None,
                "ephemerisName": None,
                "calculationMode": "table-fallback",
            },
        )


def get_jieqi_month(dt: datetime) -> int:
    return get_jieqi_month_for_datetime(dt, DEFAULT_TIMEZONE)


def _spring_festival_date(year: int) -> datetime:
    for month in get_lunar_months_for_year(year):
        if month["lunarYear"] == year and month["lunarMonth"] == 1 and not month["isLeap"]:
            return datetime.combine(month["startDate"], datetime.min.time())
    cursor = datetime(year, 1, 1)
    for _ in range(70):
        lunar_year, lunar_month, lunar_day, is_leap, _ = gregorian_to_lunar(
            cursor.year, cursor.month, cursor.day
        )
        if lunar_year == year and lunar_month == 1 and lunar_day == 1 and not is_leap:
            return cursor
        cursor += timedelta(days=1)
    raise ValueError(f"spring festival date not found for year={year}")


def get_lunar_months_for_year(lunar_year: int) -> List[Dict[str, object]]:
    months: List[Dict[str, object]] = []
    for anchor_year in (lunar_year - 1, lunar_year):
        for month in get_lunar_month_contexts(anchor_year):
            if month["lunarYear"] == lunar_year:
                months.append(month)
    months.sort(key=lambda item: item["startDate"])
    return months


def get_lunar_month_contexts(anchor_year: int) -> List[Dict[str, object]]:
    return [dict(month) for month in build_lunar_months_for_anchor_year(anchor_year)]


def _serialize_lunar_month(month: Dict[str, object]) -> Dict[str, object]:
    return {
        "anchorYear": int(month["anchorYear"]),
        "lunarYear": int(month["lunarYear"]),
        "lunarMonth": int(month["lunarMonth"]),
        "isLeap": bool(month["isLeap"]),
        "startDate": month["startDate"].isoformat(),
        "endDate": month["endDate"].isoformat(),
        "dayCount": int(month["dayCount"]),
        "containsZhongQi": bool(month["containsZhongQi"]),
        "zhongQi": month["zhongQi"],
    }


def apply_day_boundary(dt: datetime, day_boundary: str) -> datetime:
    logical_date = datetime(dt.year, dt.month, dt.day)
    if day_boundary == "23:00" and dt.hour >= 23:
        return logical_date + timedelta(days=1)
    return logical_date


def get_year_ganzhi(current_dt: datetime, year_boundary: str) -> Tuple[int, int]:
    current = current_dt.replace(tzinfo=ZoneInfo(DEFAULT_TIMEZONE))
    year = current.year

    if year_boundary == "lichun":
        lichun_at = get_solar_term_occurrence(year, "立春", DEFAULT_TIMEZONE)
        calc_year = year - 1 if current < lichun_at else year
    elif year_boundary == "spring-festival":
        spring_festival = _spring_festival_date(year).replace(tzinfo=ZoneInfo(DEFAULT_TIMEZONE))
        calc_year = year - 1 if current < spring_festival else year
    else:
        raise ValueError(f"unsupported year_boundary={year_boundary}")

    offset = calc_year - YEAR_GANZHI_REFERENCE_YEAR
    return offset % 10, offset % 12


def get_month_ganzhi(year_gan: int, jieqi_month: int) -> Tuple[int, int]:
    month_zhi = (jieqi_month + 1) % 12
    month_gan_start = {0: 2, 1: 4, 2: 6, 3: 8, 4: 0, 5: 2, 6: 4, 7: 6, 8: 8, 9: 0}
    start = month_gan_start[year_gan]
    month_gan = (start + jieqi_month - 1) % 10
    return month_gan, month_zhi


def get_day_ganzhi(year: int, month: int, day: int) -> Tuple[int, int]:
    a = (14 - month) // 12
    calc_year = year + 4800 - a
    calc_month = month + 12 * a - 3
    jdn = day + (153 * calc_month + 2) // 5 + 365 * calc_year + calc_year // 4 - calc_year // 100 + calc_year // 400 - 32045
    offset = jdn - DAY_GANZHI_BASE_JDN
    return offset % 10, offset % 12


def get_hour_ganzhi(day_gan: int, hour: int) -> Tuple[int, int]:
    hour_zhi = HOUR_TO_SHICHEN_INDEX.get(hour, 0)
    hour_gan_start = {0: 0, 1: 2, 2: 4, 3: 6, 4: 8, 5: 0, 6: 2, 7: 4, 8: 6, 9: 8}
    start = hour_gan_start[day_gan]
    return (start + hour_zhi) % 10, hour_zhi


def get_terms_for_date(dt: datetime) -> Dict[str, str]:
    return get_solar_term_window(dt, DEFAULT_TIMEZONE)


def build_hour_slots(hour_gan: int, hour_zhi: int) -> List[Dict[str, str]]:
    hour_slots: List[Dict[str, str]] = []
    for idx, (name, hour_range) in enumerate(SHICHEN_SEGMENTS):
        current_hour_gan = (hour_gan - hour_zhi + idx) % 10
        hour_slots.append(
            {
                "name": name,
                "range": hour_range,
                "ganzhi": f"{TIANGAN[current_hour_gan]}{DIZHI[idx]}",
            }
        )
    return hour_slots


def build_calendar_context(inp: CalendarCoreInput) -> Dict[str, object]:
    input_dt = datetime(inp.year, inp.month, inp.day, inp.hour)
    logical_dt = apply_day_boundary(input_dt, inp.day_boundary)
    boundary_shifted = logical_dt.date() != input_dt.date()
    solar_terms = get_terms_for_date(input_dt)

    lunar_year, lunar_month, lunar_day, is_leap, lunar_meta = gregorian_to_lunar(
        logical_dt.year, logical_dt.month, logical_dt.day
    )
    year_gan, year_zhi = get_year_ganzhi(input_dt, inp.year_boundary)
    jieqi_month = get_jieqi_month(input_dt)
    month_gan, month_zhi = get_month_ganzhi(year_gan, jieqi_month)
    day_gan, day_zhi = get_day_ganzhi(logical_dt.year, logical_dt.month, logical_dt.day)
    hour_gan, hour_zhi = get_hour_ganzhi(day_gan, inp.hour)

    return {
        "date": {
            "iso": logical_dt.strftime("%Y-%m-%d"),
            "date_cn": logical_dt.strftime("%Y年%m月%d日"),
            "weekday_cn": CHINESE_WEEKDAY[logical_dt.weekday()],
            "input_iso": input_dt.strftime("%Y-%m-%d %H:%M"),
            "effective_iso": input_dt.strftime("%Y-%m-%d %H:%M"),
            "logical_date_iso": logical_dt.strftime("%Y-%m-%d"),
            "boundaryShifted": boundary_shifted,
        },
        "lunar": {
            "year": lunar_year,
            "month": lunar_month,
            "day": lunar_day,
            "isLeap": is_leap,
            "text": f"{lunar_year}年{'闰' if is_leap else ''}{lunar_month}月{lunar_day}日",
            "monthStartDate": lunar_meta["monthStartDate"],
            "monthEndDate": lunar_meta["monthEndDate"],
            "monthDayCount": lunar_meta["monthDayCount"],
            "leapMonth": lunar_meta["leapMonth"],
            "zhongQi": lunar_meta["zhongQi"],
            "containsZhongQi": lunar_meta["containsZhongQi"],
            "anchorYear": lunar_meta["anchorYear"],
            "yearMonthTable": lunar_meta["yearMonthTable"],
            "yearMonthCount": lunar_meta["yearMonthCount"],
            "yearLeapMonth": lunar_meta["yearLeapMonth"],
            "currentMonthIndex": lunar_meta["currentMonthIndex"],
            "ephemerisName": lunar_meta["ephemerisName"],
            "calculationMode": lunar_meta["calculationMode"],
        },
        "ganzhi": {
            "year": f"{TIANGAN[year_gan]}{DIZHI[year_zhi]}",
            "month": f"{TIANGAN[month_gan]}{DIZHI[month_zhi]}",
            "day": f"{TIANGAN[day_gan]}{DIZHI[day_zhi]}",
            "hour": f"{TIANGAN[hour_gan]}{DIZHI[hour_zhi]}",
            "text": f"{TIANGAN[year_gan]}{DIZHI[year_zhi]}年 {TIANGAN[month_gan]}{DIZHI[month_zhi]}月 {TIANGAN[day_gan]}{DIZHI[day_zhi]}日 {TIANGAN[hour_gan]}{DIZHI[hour_zhi]}时",
        },
        "solar_terms": solar_terms,
        "hour_slots": build_hour_slots(hour_gan, hour_zhi),
        "zodiac": SHENGXIAO[year_zhi],
        "indices": {
            "year_gan": year_gan,
            "year_zhi": year_zhi,
            "month_gan": month_gan,
            "month_zhi": month_zhi,
            "day_gan": day_gan,
            "day_zhi": day_zhi,
            "hour_gan": hour_gan,
            "hour_zhi": hour_zhi,
        },
    }
