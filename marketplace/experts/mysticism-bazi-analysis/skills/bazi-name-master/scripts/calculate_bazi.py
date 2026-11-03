#!/usr/bin/env -S uv run
# /// script
# dependencies = ["lunar-python>=1.4.8,<2"]
# ///

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass

from lunar_python import Lunar, Solar


@dataclass
class ParsedInput:
    calendar: str
    year: int
    month: int
    day: int
    hour: int
    minute: int
    second: int
    birthplace: str | None
    is_leap_month: bool
    expected_pillars: list[str] | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="根据出生信息计算四柱八字，并可对用户自带四柱做一致性核验。"
    )
    parser.add_argument(
        "--calendar",
        required=True,
        choices=("solar", "lunar"),
        help="历法类型：solar 表示公历，lunar 表示农历。",
    )
    parser.add_argument(
        "--date",
        required=True,
        help="日期，格式为 YYYY-MM-DD。",
    )
    parser.add_argument(
        "--time",
        required=True,
        help="时间，格式为 HH:MM 或 HH:MM:SS。",
    )
    parser.add_argument(
        "--birthplace",
        help="出生地。该字段不会影响排盘计算，但会作为核验信息原样返回。",
    )
    parser.add_argument(
        "--is-leap-month",
        action="store_true",
        help="当 --calendar=lunar 且出生在农历闰月时传入。",
    )
    parser.add_argument(
        "--expected-pillars",
        help="用户自带四柱，用逗号、空格或竖线分隔，例如：甲辰,戊辰,丙辰,乙未。",
    )
    return parser.parse_args()


def parse_date(date_text: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", date_text.strip())
    if not match:
        raise ValueError("日期格式错误，应为 YYYY-MM-DD。")
    year, month, day = map(int, match.groups())
    return year, month, day


def parse_time(time_text: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?", time_text.strip())
    if not match:
        raise ValueError("时间格式错误，应为 HH:MM 或 HH:MM:SS。")
    hour = int(match.group(1))
    minute = int(match.group(2))
    second = int(match.group(3) or 0)
    if hour > 23 or minute > 59 or second > 59:
        raise ValueError("时间数值超出范围，请检查时分秒。")
    return hour, minute, second


def parse_expected_pillars(raw_text: str | None) -> list[str] | None:
    if not raw_text:
        return None
    tokens = [token for token in re.split(r"[\s,|/，、]+", raw_text.strip()) if token]
    if len(tokens) != 4:
        raise ValueError("expected-pillars 需要准确提供 4 柱，例如：甲辰,戊辰,丙辰,乙未。")
    return tokens


def normalize_input(args: argparse.Namespace) -> ParsedInput:
    year, month, day = parse_date(args.date)
    hour, minute, second = parse_time(args.time)
    if args.calendar == "solar" and args.is_leap_month:
        raise ValueError("公历日期不应传入 --is-leap-month。")
    normalized_month = -month if args.calendar == "lunar" and args.is_leap_month else month
    return ParsedInput(
        calendar=args.calendar,
        year=year,
        month=normalized_month,
        day=day,
        hour=hour,
        minute=minute,
        second=second,
        birthplace=args.birthplace,
        is_leap_month=args.is_leap_month,
        expected_pillars=parse_expected_pillars(args.expected_pillars),
    )


def build_chart(data: ParsedInput) -> dict:
    if data.calendar == "solar":
        solar = Solar.fromYmdHms(data.year, data.month, data.day, data.hour, data.minute, data.second)
        lunar = solar.getLunar()
    else:
        lunar = Lunar.fromYmdHms(data.year, data.month, data.day, data.hour, data.minute, data.second)
        solar = lunar.getSolar()

    eight_char = lunar.getEightChar()
    computed_pillars = [
        eight_char.getYear(),
        eight_char.getMonth(),
        eight_char.getDay(),
        eight_char.getTime(),
    ]
    lunar_ymdhms = (
        f"{lunar.getYear():04d}-"
        f"{abs(lunar.getMonth()):02d}-"
        f"{lunar.getDay():02d} "
        f"{lunar.getHour():02d}:{lunar.getMinute():02d}:{lunar.getSecond():02d}"
    )

    result = {
        "calculation_basis": {
            "library": "lunar-python",
            "note": "基于 6tail/lunar-python 计算四柱八字。",
        },
        "input": asdict(data),
        "normalized": {
            "solar": solar.toYmdHms(),
            "lunar": lunar_ymdhms,
            "lunar_text": lunar.toFullString(),
            "solar_text": solar.toFullString(),
        },
        "bazi": {
            "pillars": {
                "year": computed_pillars[0],
                "month": computed_pillars[1],
                "day": computed_pillars[2],
                "time": computed_pillars[3],
            },
            "pillars_text": " ".join(computed_pillars),
            "stems": {
                "year": eight_char.getYearGan(),
                "month": eight_char.getMonthGan(),
                "day": eight_char.getDayGan(),
                "time": eight_char.getTimeGan(),
            },
            "branches": {
                "year": eight_char.getYearZhi(),
                "month": eight_char.getMonthZhi(),
                "day": eight_char.getDayZhi(),
                "time": eight_char.getTimeZhi(),
            },
            "wuxing": {
                "year": eight_char.getYearWuXing(),
                "month": eight_char.getMonthWuXing(),
                "day": eight_char.getDayWuXing(),
                "time": eight_char.getTimeWuXing(),
            },
            "na_yin": {
                "year": eight_char.getYearNaYin(),
                "month": eight_char.getMonthNaYin(),
                "day": eight_char.getDayNaYin(),
                "time": eight_char.getTimeNaYin(),
            },
            "ten_gods_stem": {
                "year": eight_char.getYearShiShenGan(),
                "month": eight_char.getMonthShiShenGan(),
                "day": eight_char.getDayShiShenGan(),
                "time": eight_char.getTimeShiShenGan(),
            },
            "ten_gods_branch": {
                "year": eight_char.getYearShiShenZhi(),
                "month": eight_char.getMonthShiShenZhi(),
                "day": eight_char.getDayShiShenZhi(),
                "time": eight_char.getTimeShiShenZhi(),
            },
            "hidden_stems": {
                "year": eight_char.getYearHideGan(),
                "month": eight_char.getMonthHideGan(),
                "day": eight_char.getDayHideGan(),
                "time": eight_char.getTimeHideGan(),
            },
            "di_shi": {
                "year": eight_char.getYearDiShi(),
                "month": eight_char.getMonthDiShi(),
                "day": eight_char.getDayDiShi(),
                "time": eight_char.getTimeDiShi(),
            },
            "xun_kong": {
                "year": eight_char.getYearXunKong(),
                "month": eight_char.getMonthXunKong(),
                "day": eight_char.getDayXunKong(),
                "time": eight_char.getTimeXunKong(),
            },
        },
        "extended": {
            "tai_yuan": eight_char.getTaiYuan(),
            "tai_yuan_na_yin": eight_char.getTaiYuanNaYin(),
            "ming_gong": eight_char.getMingGong(),
            "ming_gong_na_yin": eight_char.getMingGongNaYin(),
            "shen_gong": eight_char.getShenGong(),
            "shen_gong_na_yin": eight_char.getShenGongNaYin(),
            "tai_xi": eight_char.getTaiXi(),
            "tai_xi_na_yin": eight_char.getTaiXiNaYin(),
        },
        "uncertainty_notes": [],
    }

    if data.birthplace:
        result["uncertainty_notes"].append("出生地已记录，但当前脚本仅负责排盘与核验，不对地域命理解读作额外推断。")
    else:
        result["uncertainty_notes"].append("未提供出生地；脚本仍可排盘，但人工核验信息完整性时应标注该缺项。")

    if data.expected_pillars:
        mismatches = []
        for label, expected, actual in zip(
            ("年柱", "月柱", "日柱", "时柱"),
            data.expected_pillars,
            computed_pillars,
        ):
            if expected != actual:
                mismatches.append(
                    {
                        "pillar": label,
                        "expected": expected,
                        "computed": actual,
                    }
                )
        result["consistency_check"] = {
            "provided": data.expected_pillars,
            "computed": computed_pillars,
            "is_match": not mismatches,
            "mismatches": mismatches,
        }
    else:
        result["consistency_check"] = {
            "provided": None,
            "computed": computed_pillars,
            "is_match": None,
            "mismatches": [],
        }

    return result


def main() -> int:
    try:
        args = parse_args()
        normalized = normalize_input(args)
        result = build_chart(normalized)
    except Exception as exc:  # noqa: BLE001
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": f"八字计算失败：{exc}",
                },
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1

    print(
        json.dumps(
            {
                "ok": True,
                "result": result,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
