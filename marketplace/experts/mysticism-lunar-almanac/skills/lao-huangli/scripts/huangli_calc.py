#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple


ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

IMPORT_ERROR: ModuleNotFoundError | None = None
try:
    from lao_huangli.calendar_core import CalendarCoreInput, build_calendar_context
    from lao_huangli.rule_engine import compute_time_gods, evaluate_rule_layer
except ModuleNotFoundError as exc:
    if exc.name not in {"skyfield", "jplephem"}:
        raise
    IMPORT_ERROR = exc


TIANGAN = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
DIZHI = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
SHENGXIAO = ["鼠", "牛", "虎", "兔", "龙", "蛇", "马", "羊", "猴", "鸡", "狗", "猪"]

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
    0x04BD8,
    0x04AE0,
    0x0A570,
    0x054D5,
    0x0D260,
    0x0D950,
    0x16554,
    0x056A0,
    0x09AD0,
    0x055D2,
    0x04AE0,
    0x0A5B6,
    0x0A4D0,
    0x0D250,
    0x1D255,
    0x0B540,
    0x0D6A0,
    0x0ADA2,
    0x095B0,
    0x14977,
    0x04970,
    0x0A4B0,
    0x0B4B5,
    0x06A50,
    0x06D40,
    0x1AB54,
    0x02B60,
    0x09570,
    0x052F2,
    0x04970,
    0x06566,
    0x0D4A0,
    0x0EA50,
    0x06E95,
    0x05AD0,
    0x02B60,
    0x186E3,
    0x092E0,
    0x1C8D7,
    0x0C950,
    0x0D4A0,
    0x1D8A6,
    0x0B550,
    0x056A0,
    0x1A5B4,
    0x025D0,
    0x092D0,
    0x0D2B2,
    0x0A950,
    0x0B557,
    0x06CA0,
    0x0B550,
    0x15355,
    0x04DA0,
    0x0A5D0,
    0x14573,
    0x052D0,
    0x0A9A8,
    0x0E950,
    0x06AA0,
    0x0AEA6,
    0x0AB50,
    0x04B60,
    0x0AAE4,
    0x0A570,
    0x05260,
    0x0F263,
    0x0D950,
    0x05B57,
    0x056A0,
    0x096D0,
    0x04DD5,
    0x04AD0,
    0x0A4D0,
    0x0D4D4,
    0x0D250,
    0x0D558,
    0x0B540,
    0x0B5A0,
    0x195A6,
    0x095B0,
    0x049B0,
    0x0A974,
    0x0A4B0,
    0x0B27A,
    0x06A50,
    0x06D40,
    0x0AF46,
    0x0AB60,
    0x09570,
    0x04AF5,
    0x04970,
    0x064B0,
    0x074A3,
    0x0EA50,
    0x06B58,
    0x05AC0,
    0x0AB60,
    0x096D5,
    0x092E0,
    0x0C960,
    0x0D954,
    0x0D4A0,
    0x0DA50,
    0x07552,
    0x056A0,
    0x0ABB7,
    0x025D0,
    0x092D0,
    0x0CAB5,
    0x0A950,
    0x0B4A0,
    0x0BAA4,
    0x0AD50,
    0x055D9,
    0x04BA0,
    0x0A5B0,
    0x15176,
    0x052B0,
    0x0A930,
    0x07954,
    0x06AA0,
    0x0AD50,
    0x05B52,
    0x04B60,
    0x0A6E6,
    0x0A4E0,
    0x0D260,
    0x0EA65,
    0x0D530,
    0x05AA0,
    0x076A3,
    0x096D0,
    0x04AFB,
    0x04AD0,
    0x0A4D0,
    0x1D0B6,
    0x0D250,
    0x0D520,
    0x0DD45,
    0x0B5A0,
    0x056D0,
    0x055B2,
    0x049B0,
    0x0A577,
    0x0A4B0,
    0x0AA50,
    0x1B255,
    0x06D20,
    0x0ADA0,
    0x14B63,
    0x09370,
    0x049F8,
    0x04970,
    0x064B0,
    0x168A6,
    0x0EA50,
    0x06AA0,
    0x1A6C4,
    0x0AAE0,
    0x092E0,
    0x0D2E3,
    0x0C960,
    0x0D557,
    0x0D4A0,
    0x0DA50,
    0x05D55,
    0x056A0,
    0x0A6D0,
    0x055D4,
    0x052D0,
    0x0A9B8,
    0x0A950,
    0x0B4A0,
    0x0B6A6,
    0x0AD50,
    0x055A0,
    0x0ABA4,
    0x0A5B0,
    0x052B0,
    0x0B273,
    0x06930,
    0x07337,
    0x06AA0,
    0x0AD50,
    0x14B55,
    0x04B60,
    0x0A570,
    0x054E4,
    0x0D160,
    0x0E968,
    0x0D520,
    0x0DAA0,
    0x16AA6,
    0x056D0,
    0x04AE0,
    0x0A9D4,
    0x0A2D0,
    0x0D150,
    0x0F252,
]

LUNAR_START_DATE = datetime(1900, 1, 31)


JIEQI_DATES = {
    1: [("小寒", 6), ("大寒", 20)],
    2: [("立春", 4), ("雨水", 19)],
    3: [("惊蛰", 6), ("春分", 21)],
    4: [("清明", 5), ("谷雨", 20)],
    5: [("立夏", 6), ("小满", 21)],
    6: [("芒种", 6), ("夏至", 21)],
    7: [("小暑", 7), ("大暑", 23)],
    8: [("立秋", 8), ("处暑", 23)],
    9: [("白露", 8), ("秋分", 23)],
    10: [("寒露", 8), ("霜降", 24)],
    11: [("立冬", 8), ("小雪", 22)],
    12: [("大雪", 7), ("冬至", 22)],
}

CHINESE_WEEKDAY = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]

RULES_DIR = ROOT / "rules"
PROFILES_DIR = ROOT / "rules" / "profiles"
LEGACY_MODE_TO_PROFILE = {"market": "market-folk-v1", "bazi": "bazi-v1"}


def load_profile(profile_id: str) -> Dict[str, object]:
    path = PROFILES_DIR / f"{profile_id}.json"
    if not path.exists():
        raise ValueError(f"unsupported profile={profile_id}")
    return json.loads(path.read_text())


def load_ruleset_items(profile_id: str, filename: str) -> List[Dict[str, object]]:
    path = RULES_DIR / profile_id / f"{filename}.json"
    if not path.exists():
        return []
    return json.loads(path.read_text())


def get_ruleset_source_metadata(ruleset_id: Optional[str]) -> Dict[str, object]:
    if not ruleset_id:
        return {"ruleSourceLevel": "none", "sourceRefs": []}

    ruleset_dir = RULES_DIR / ruleset_id
    if not ruleset_dir.exists():
        return {"ruleSourceLevel": "none", "sourceRefs": []}

    source_levels = OrderedDict()
    source_refs = OrderedDict()
    for path in sorted(ruleset_dir.glob("*.json")):
        data = json.loads(path.read_text())
        if not isinstance(data, list):
            continue
        for item in data:
            level = item.get("sourceLevel")
            if level:
                source_levels[level] = True
            for ref in item.get("sourceRef", []):
                key = (ref.get("work"), ref.get("location"), ref.get("url"))
                if key not in source_refs:
                    source_refs[key] = ref

    level_text = ",".join(source_levels.keys()) if source_levels else "none"
    return {"ruleSourceLevel": level_text, "sourceRefs": list(source_refs.values())}


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


def gregorian_to_lunar(year: int, month: int, day: int) -> Tuple[int, int, int, bool]:
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

    for m in range(1, 13):
        mdays = _month_days(year_info, m, False)
        if offset < mdays:
            return lunar_year, m, offset + 1, False
        offset -= mdays

        if m == leap_month:
            ldays = _month_days(year_info, m, True)
            if offset < ldays:
                return lunar_year, m, offset + 1, True
            offset -= ldays

    raise ValueError("lunar conversion failed")


def get_jieqi_month(month: int, day: int) -> int:
    month_map = {
        2: 1,
        3: 2,
        4: 3,
        5: 4,
        6: 5,
        7: 6,
        8: 7,
        9: 8,
        10: 9,
        11: 10,
        12: 11,
        1: 12,
    }
    jieqi = JIEQI_DATES.get(month, [])
    jie_day = jieqi[0][1] if jieqi else 6
    if day >= jie_day:
        return month_map.get(month, month)
    prev_month = month - 1 if month > 1 else 12
    return month_map.get(prev_month, prev_month)


def _spring_festival_date(year: int) -> datetime:
    cursor = datetime(year, 1, 1)
    for _ in range(70):
        ly, lm, ld, is_leap = gregorian_to_lunar(cursor.year, cursor.month, cursor.day)
        if ly == year and lm == 1 and ld == 1 and not is_leap:
            return cursor
        cursor += timedelta(days=1)
    raise ValueError(f"spring festival date not found for year={year}")


def _apply_day_boundary(dt: datetime, day_boundary: str) -> datetime:
    logical_date = datetime(dt.year, dt.month, dt.day)
    if day_boundary == "23:00" and dt.hour >= 23:
        return logical_date + timedelta(days=1)
    return logical_date


def get_year_ganzhi(
    year: int, month: int, day: int, year_boundary: str
) -> Tuple[int, int]:
    current = datetime(year, month, day)

    if year_boundary == "lichun":
        lichun_day = JIEQI_DATES[2][0][1]
        calc_year = (
            year - 1 if (month < 2 or (month == 2 and day < lichun_day)) else year
        )
    elif year_boundary == "spring-festival":
        spring_festival = _spring_festival_date(year)
        calc_year = year - 1 if current < spring_festival else year
    else:
        raise ValueError(f"unsupported year_boundary={year_boundary}")

    offset = calc_year - 1984
    return offset % 10, offset % 12


def get_month_ganzhi(year_gan: int, jieqi_month: int) -> Tuple[int, int]:
    month_zhi = (jieqi_month + 1) % 12
    month_gan_start = {0: 2, 1: 4, 2: 6, 3: 8, 4: 0, 5: 2, 6: 4, 7: 6, 8: 8, 9: 0}
    start = month_gan_start[year_gan]
    month_gan = (start + jieqi_month - 1) % 10
    return month_gan, month_zhi


def get_day_ganzhi(year: int, month: int, day: int) -> Tuple[int, int]:
    a = (14 - month) // 12
    y = year + 4800 - a
    m = month + 12 * a - 3
    jd = day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045
    offset = jd - DAY_GANZHI_BASE_JDN
    return offset % 10, offset % 12


def get_hour_ganzhi(day_gan: int, hour: int) -> Tuple[int, int]:
    hour_zhi = HOUR_TO_SHICHEN_INDEX.get(hour, 0)
    hour_gan_start = {0: 0, 1: 2, 2: 4, 3: 6, 4: 8, 5: 0, 6: 2, 7: 4, 8: 6, 9: 8}
    start = hour_gan_start[day_gan]
    return (start + hour_zhi) % 10, hour_zhi


def compute_jianchu(profile_id: str, month_branch: str, day_branch: str) -> str:
    rules = load_ruleset_items(profile_id, "jianchu")
    if not rules:
        return "待规则库补齐"

    cycle = rules[0]["cycle"]
    month_index = DIZHI.index(month_branch)
    day_index = DIZHI.index(day_branch)
    return cycle[(day_index - month_index) % 12]


def compute_yellow_black_dao(profile_id: str, month_branch: str, day_branch: str) -> str:
    rules = load_ruleset_items(profile_id, "yellow-black-dao")
    if not rules:
        return "待规则库补齐"

    rule = rules[0]
    start_branch = rule["monthStarts"][month_branch]
    start_index = DIZHI.index(start_branch)
    day_index = DIZHI.index(day_branch)
    return rule["order"][(day_index - start_index) % 12]


def evaluate_rules(profile_id: str, rule_context: Dict[str, str]) -> Dict[str, List[str]]:
    decision = {"yi": [], "ji": [], "warnings": [], "explanations": []}
    for rule in load_ruleset_items(profile_id, "yi-ji-rules"):
        if rule_context.get(rule["field"]) not in rule["values"]:
            continue

        effect = rule["effect"]
        decision[effect].extend(rule["items"])
        decision["explanations"].append(rule["reason"])

    return decision


def get_active_ruleset(profile_id: str, overlay_ruleset: Optional[str]) -> Optional[str]:
    if profile_id == "bazi-v1":
        return overlay_ruleset
    return profile_id


def get_capabilities(profile_id: str, ruleset_id: Optional[str], is_hybrid: bool) -> Dict[str, bool]:
    has_rule_layer = ruleset_id is not None
    return {
        "calendarCore": True,
        "ganzhi": True,
        "solarTerms": True,
        "jianchu": has_rule_layer,
        "yellowBlackDao": has_rule_layer,
        "dutyGod": False,
        "yiJi": has_rule_layer,
        "sourceTrace": has_rule_layer,
        "isHybrid": is_hybrid,
    }


def _get_terms_for_date(month: int, day: int) -> Dict[str, str]:
    terms = JIEQI_DATES.get(month, [])
    if not terms:
        return {"current": "待补齐", "next": "待补齐", "note": "简化节气表"}

    first_name, first_day = terms[0]
    second_name, second_day = terms[1]

    if day < first_day:
        prev_month = month - 1 if month > 1 else 12
        current = JIEQI_DATES[prev_month][1][0]
        nxt = first_name
    elif day < second_day:
        current = first_name
        nxt = second_name
    else:
        current = second_name
        next_month = month + 1 if month < 12 else 1
        nxt = JIEQI_DATES[next_month][0][0]

    return {
        "current": current,
        "next": nxt,
        "note": "日期为近似值，若需天文精度需天文历算",
    }


def _render_calendar_block(data: Dict) -> str:
    date = data["date"]
    daily = data.get("daily", {})
    decision = data.get("decision", {})
    capabilities = data.get("capabilities", {})
    provenance = data.get("provenance", {})
    if capabilities.get("yiJi", True):
        yi_text = "  ".join(decision.get("yi", [])) or "无"
        ji_text = "  ".join(decision.get("ji", [])) or "无"
        jianchu_text = daily.get("jianchu", "待规则库补齐")
        yellow_black_text = daily.get("yellowBlackDao", "待规则库补齐")
        duty_god_text = daily.get("dutyGod", "待规则库补齐")
        good_stars_text = "、".join(daily.get("goodStars", [])) or "无"
        bad_stars_text = "、".join(daily.get("badStars", [])) or "无"
        chongsha_text = daily.get("chongsha", "待规则库补齐")
        taishen_text = daily.get("taishen", "待规则库补齐")
        pengzu_text = daily.get("pengzu", "待规则库补齐")
        cai_shen_text = daily.get("caiShen", "待规则库补齐")
        xi_shen_text = daily.get("xiShen", "待规则库补齐")
        fu_shen_text = daily.get("fuShen", "待规则库补齐")
    else:
        yi_text = "未启用（bazi-core）"
        ji_text = "未启用（bazi-core）"
        jianchu_text = "未启用"
        yellow_black_text = "未启用"
        duty_god_text = "未启用"
        good_stars_text = "未启用"
        bad_stars_text = "未启用"
        chongsha_text = "未启用"
        taishen_text = "未启用"
        pengzu_text = "未启用"
        cai_shen_text = "未启用"
        xi_shen_text = "未启用"
        fu_shen_text = "未启用"

    if provenance.get("ruleLayer"):
        rule_note = f"说明：{data['meta']['profileLabel']}；农历/干支/节气可复算，宜忌供民俗参考。"
    else:
        rule_note = "说明：bazi-core，仅输出历法核心。"
    lines = [
        "┌────────────────────────────────────────────────────────────┐",
        f"│ {date['date_cn']}  {date['weekday_cn']:<44}│",
        f"│ 农历：{data['lunar']['text']:<52}│",
        f"│ 干支：{data['ganzhi']['text']:<52}│",
        f"│ 节气：{data['solar_terms']['current']} → 下个 {data['solar_terms']['next']:<35}│",
        f"│ 口径：{data['meta']['profileLabel']:<52}│",
        "├────────────────────────────────────────────────────────────┤",
        f"│ 【宜】{yi_text:<52}│",
        f"│ 【忌】{ji_text:<52}│",
        "├────────────────────────────────────────────────────────────┤",
        f"│ 建除：{jianchu_text:<8} 黄黑道：{yellow_black_text:<8} 值神：{duty_god_text:<8} │",
        f"│ 冲煞：{chongsha_text}  胎神：{taishen_text}  彭祖百忌：{pengzu_text} │",
        f"│ 吉神宜趋：{good_stars_text:<12} 凶神宜忌：{bad_stars_text:<24}│",
        f"│ 财神：{cai_shen_text:<6} 喜神：{xi_shen_text:<6} 福神：{fu_shen_text:<26}│",
        "├────────────────────────────────────────────────────────────┤",
        "│ 时辰干支（12时辰）                                           │",
    ]

    for item in data["hour_slots"]:
        if item.get("tianShen") and item.get("luck"):
            lines.append(
                f"│ {item['name']}时 {item['range']} {item['ganzhi']} {item['tianShen']} {item['luck']:<23}│"
            )
        else:
            lines.append(f"│ {item['name']}时 {item['range']:<13} {item['ganzhi']:<39}│")

    lines.extend(
        [
            "└────────────────────────────────────────────────────────────┘",
            rule_note,
        ]
    )
    return "\n".join(lines)


def _render_markdown_block(data: Dict) -> str:
    date = data["date"]
    daily = data.get("daily", {})
    decision = data.get("decision", {})
    capabilities = data.get("capabilities", {})
    provenance = data.get("provenance", {})
    yi_text = "、".join(decision.get("yi", [])) or "无"
    ji_text = "、".join(decision.get("ji", [])) or "无"
    good_stars_text = "、".join(daily.get("goodStars", [])) or "无"
    bad_stars_text = "、".join(daily.get("badStars", [])) or "无"

    if provenance.get("ruleLayer"):
        note = f"{data['meta']['profileLabel']}；农历/干支/节气可复算，宜忌供民俗参考。"
    else:
        note = "bazi-core，仅输出历法核心。"

    lines = [
        f"# {date['date_cn']} {date['weekday_cn']}",
        "",
        f"- 农历：{data['lunar']['text']}",
        f"- 干支：{data['ganzhi']['text']}",
        f"- 节气：{data['solar_terms']['current']} → 下个 {data['solar_terms']['next']}",
        f"- 口径：{data['meta']['profileLabel']}",
        "",
        "## 宜忌",
        f"- 宜：{yi_text}",
        f"- 忌：{ji_text}",
        "",
        "## 日值",
        f"- 建除：{daily.get('jianchu', '未启用') if capabilities.get('yiJi', True) else '未启用'}",
        f"- 黄黑道：{daily.get('yellowBlackDao', '未启用') if capabilities.get('yiJi', True) else '未启用'}",
        f"- 值神：{daily.get('dutyGod', '未启用') if capabilities.get('yiJi', True) else '未启用'}",
        f"- 冲煞：{daily.get('chongsha', '未启用') if capabilities.get('yiJi', True) else '未启用'}",
        f"- 胎神：{daily.get('taishen', '未启用') if capabilities.get('yiJi', True) else '未启用'}",
        f"- 彭祖百忌：{daily.get('pengzu', '未启用') if capabilities.get('yiJi', True) else '未启用'}",
        f"- 吉神宜趋：{good_stars_text if capabilities.get('yiJi', True) else '未启用'}",
        f"- 凶神宜忌：{bad_stars_text if capabilities.get('yiJi', True) else '未启用'}",
        f"- 财神：{daily.get('caiShen', '未启用') if capabilities.get('yiJi', True) else '未启用'}",
        f"- 喜神：{daily.get('xiShen', '未启用') if capabilities.get('yiJi', True) else '未启用'}",
        f"- 福神：{daily.get('fuShen', '未启用') if capabilities.get('yiJi', True) else '未启用'}",
        "",
        "## 时辰",
        "",
        "| 时辰 | 时间 | 干支 | 值时神 | 吉凶 |",
        "| --- | --- | --- | --- | --- |",
    ]

    for item in data["hour_slots"]:
        lines.append(
            f"| {item['name']}时 | {item['range']} | {item['ganzhi']} | {item.get('tianShen', '—')} | {item.get('luck', '—')} |"
        )

    lines.extend(
        [
            "",
            f"> 说明：{note}",
        ]
    )
    return "\n".join(lines)


@dataclass
class HuangliInput:
    year: int
    month: int
    day: int
    hour: int
    profile: str
    overlay_ruleset: Optional[str] = None


def calculate(inp: HuangliInput) -> Dict:
    profile_cfg = load_profile(inp.profile)
    calendar_context = build_calendar_context(
        CalendarCoreInput(
            year=inp.year,
            month=inp.month,
            day=inp.day,
            hour=inp.hour,
            year_boundary=profile_cfg["yearBoundary"],
            day_boundary=profile_cfg["dayBoundary"],
        )
    )
    indices = calendar_context.pop("indices")
    yg = indices["year_gan"]
    yz = indices["year_zhi"]
    rule_layer = evaluate_rule_layer(
        profile_id=profile_cfg["id"],
        overlay_ruleset=inp.overlay_ruleset,
        calendar_context=calendar_context,
    )

    data = {
        **calendar_context,
        "daily": rule_layer["daily"],
        "decision": rule_layer["decision"],
        "capabilities": rule_layer["capabilities"],
        "provenance": rule_layer["provenance"],
        "meta": {
            "profileId": profile_cfg["id"],
            "profileLabel": profile_cfg["label"],
            "mode": next(
                (
                    mode
                    for mode, profile_id in LEGACY_MODE_TO_PROFILE.items()
                    if profile_id == profile_cfg["id"]
                ),
                profile_cfg["id"],
            ),
            "modeLabel": profile_cfg["label"],
            "yearBoundary": profile_cfg["yearBoundary"],
            "dayBoundary": profile_cfg["dayBoundary"],
            "timezone": "Asia/Shanghai",
            "rulesetVersion": "zh-traditional-v1",
            "ruleLayer": rule_layer["ruleLayer"],
            "overlayRuleset": inp.overlay_ruleset,
            "notes": [
                "lunar/ganzhi/terms are algorithmic outputs",
                "yi-ji and shensha require external rule tables",
            ],
        },
    }
    data["hour_slots"] = compute_time_gods(
        profile_cfg["id"],
        data["ganzhi"]["day"][1],
        data["hour_slots"],
    )
    return data


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Calculate reproducible Huangli base fields"
    )
    parser.add_argument("year", type=int)
    parser.add_argument("month", type=int)
    parser.add_argument("day", type=int)
    parser.add_argument("hour", type=int, nargs="?", default=12)
    parser.add_argument("--profile")
    parser.add_argument("--mode", choices=["market", "bazi"], default="market")
    parser.add_argument("--overlay-ruleset")
    parser.add_argument("--format", choices=["json", "calendar", "markdown"], default="calendar")
    return parser.parse_args()


def main() -> None:
    if IMPORT_ERROR is not None:
        script_path = Path(__file__).resolve()
        print(
            "缺少老黄历运行依赖："
            f"{IMPORT_ERROR.name}\n"
            "推荐直接用 uv 运行，无需本地安装：\n"
            f"  uv run --with skyfield==1.54 --with jplephem==2.24 python {script_path} 2026 3 9 12 --profile market-folk-v1 --format markdown\n"
            "或先安装依赖：\n"
            "  uv venv .venv\n"
            "  uv pip install --python .venv/bin/python -r skills/lao-huangli/requirements.txt",
            file=sys.stderr,
        )
        sys.exit(2)
    args = parse_args()
    profile_id = args.profile or LEGACY_MODE_TO_PROFILE[args.mode]
    result = calculate(
        HuangliInput(
            args.year,
            args.month,
            args.day,
            args.hour,
            profile_id,
            args.overlay_ruleset,
        )
    )
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.format == "markdown":
        print(_render_markdown_block(result))
    else:
        print(_render_calendar_block(result))


if __name__ == "__main__":
    main()
