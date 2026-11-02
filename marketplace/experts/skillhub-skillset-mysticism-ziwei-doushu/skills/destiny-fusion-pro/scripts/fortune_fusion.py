#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import json
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from lunar_python import Solar
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

GAN_WUXING = {
    "甲": "木",
    "乙": "木",
    "丙": "火",
    "丁": "火",
    "戊": "土",
    "己": "土",
    "庚": "金",
    "辛": "金",
    "壬": "水",
    "癸": "水",
}
ZHI_WUXING = {
    "子": "水",
    "丑": "土",
    "寅": "木",
    "卯": "木",
    "辰": "土",
    "巳": "火",
    "午": "火",
    "未": "土",
    "申": "金",
    "酉": "金",
    "戌": "土",
    "亥": "水",
}
BRANCHES = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
MUTAGEN_KEY_TO_CN = {
    "taiyinMaj": "太阴",
    "tiantongMaj": "天同",
    "tianjiMaj": "天机",
    "jumenMaj": "巨门",
    "wuquMaj": "武曲",
    "tanlangMaj": "贪狼",
    "tianliangMaj": "天梁",
    "wenquMin": "文曲",
    "pojunMaj": "破军",
    "wenchangMin": "文昌",
    "lianzhenMaj": "廉贞",
    "ziweiMaj": "紫微",
    "taiyangMaj": "太阳",
}
PALACE_ALIAS_MAP = {
    "仆役宫": "交友宫",
    "奴仆宫": "交友宫",
    "事业宫": "官禄宫",
}
ZH_FONT_STACK = '"WenQuanYi Zen Hei", "WenQuanYi Micro Hei", "Noto Sans CJK SC", "Source Han Sans SC", "PingFang SC", "Microsoft YaHei", "SimHei", "Arial Unicode MS", sans-serif'
PALACE_COLOR_MAP = {
    "命宫": ("#8f4b38", "#f8ebe5"),
    "兄弟宫": ("#8f5f2f", "#f8efe4"),
    "夫妻宫": ("#8b3f5d", "#f9e9f1"),
    "子女宫": ("#86521d", "#f7eddc"),
    "财帛宫": ("#83611f", "#f8f2df"),
    "疾厄宫": ("#6b4c2d", "#f4ebdf"),
    "迁移宫": ("#2f6a6e", "#e5f4f5"),
    "交友宫": ("#365d8b", "#e7eef8"),
    "官禄宫": ("#325874", "#e5f0f7"),
    "田宅宫": ("#5a6a2f", "#edf4e2"),
    "福德宫": ("#4c5f5c", "#e8f3f1"),
    "父母宫": ("#6f546c", "#f1e8f4"),
}

STAR_HINTS: dict[str, dict[str, str]] = {
    "紫微": {
        "strength": "统筹与整合能力强，能在复杂局面下抓住主轴。",
        "challenge": "标准过高时容易把节奏推得太满，增加团队压力。",
        "career": "适合平台管理、资源整合、负责人角色。",
        "wealth": "偏向通过组织与权责扩张带来收入上限。",
    },
    "天机": {
        "strength": "思考快、策略感强，擅长信息整合与方案设计。",
        "challenge": "选项过多时可能反复权衡，延迟关键决策。",
        "career": "适合策略、产品、咨询、研究类岗位。",
        "wealth": "更适合知识与脑力驱动型收入模型。",
    },
    "太阳": {
        "strength": "表达与影响力强，能带动外部资源与机会。",
        "challenge": "外耗过高时容易透支精力和耐心。",
        "career": "适合市场、品牌、管理、公众沟通方向。",
        "wealth": "财富与职业曝光度、输出稳定度联动明显。",
    },
    "太阴": {
        "strength": "细节感强，适合长期沉淀与复利路径。",
        "challenge": "在不确定阶段容易产生内耗。",
        "career": "适合研究、内容、财务、后台规划工作。",
        "wealth": "偏向稳健积累，擅长长期配置。",
    },
    "武曲": {
        "strength": "执行与纪律性高，重结果与落地。",
        "challenge": "节奏过满时，容易忽略恢复与身心缓冲。",
        "career": "适合经营管理、金融运营、强执行岗位。",
        "wealth": "适合规则化资产管理与风险控制。",
    },
    "廉贞": {
        "strength": "原则感和边界感强，做事有底线。",
        "challenge": "态度偏硬时，沟通摩擦会增加。",
        "career": "适合规则密集、博弈性强的环境。",
        "wealth": "财务决策重规则，但要防止过度保守。",
    },
    "贪狼": {
        "strength": "开拓与社交能力强，善于抓机会。",
        "challenge": "机会太多时容易分散主线。",
        "career": "适合商务、创新项目、资源链接岗位。",
        "wealth": "适合机会型收益，但必须配套仓位纪律。",
    },
    "巨门": {
        "strength": "辨析能力强，能发现隐藏问题。",
        "challenge": "表达过于锋利时容易引发误读。",
        "career": "适合法务、审计、咨询、技术评审。",
        "wealth": "适合通过专业壁垒变现，而非盲目追热点。",
    },
    "天相": {
        "strength": "组织协同与秩序意识较强。",
        "challenge": "过度顾全时决策速度下降。",
        "career": "适合中后台管理与跨团队协同岗位。",
        "wealth": "重稳健与可持续，偏好可验证收益。",
    },
    "天梁": {
        "strength": "责任感强，具备守护与支持能力。",
        "challenge": "容易替他人承担过多责任。",
        "career": "适合顾问、教育、服务、管理岗位。",
        "wealth": "收益偏稳，适合中长期规划。",
    },
    "天府": {
        "strength": "稳健、持重，擅长资源管理。",
        "challenge": "过稳会错失窗口期机会。",
        "career": "适合运营中枢、资产管理岗位。",
        "wealth": "偏守成，强调本金安全与现金流稳定。",
    },
    "天同": {
        "strength": "关系润滑度高，善于营造合作氛围。",
        "challenge": "舒适区惯性会拖慢突破节奏。",
        "career": "适合服务协同、团队支持型岗位。",
        "wealth": "适合稳中求进，避免情绪化投资。",
    },
    "七杀": {
        "strength": "攻坚力强，适应高压与变化。",
        "challenge": "节奏过猛会放大波动与风险。",
        "career": "适合转型期、关键战役型角色。",
        "wealth": "高波动偏好明显，需要更强风控框架。",
    },
    "破军": {
        "strength": "变革与重构能力突出。",
        "challenge": "频繁推翻重来会提高沉没成本。",
        "career": "适合创业、转型、结构重建任务。",
        "wealth": "收益与波动并存，适合分层仓位管理。",
    },
}
TEN_GOD_TREND = {
    "正财": "适合现金流与预算管理，强调稳健执行。",
    "偏财": "机会与资源变动增多，先控回撤再加杠杆。",
    "正官": "规则、责任、流程要求增强，利于体系化升级。",
    "七杀": "外部压力和竞争增大，宜主动卡位并守住边界。",
    "正印": "学习、认证、修复与支持力量增强，利于蓄能。",
    "偏印": "思维活跃但也易内耗，适合聚焦关键问题深挖。",
    "食神": "输出与口碑有提升机会，宜持续内容化产出。",
    "伤官": "表达锋芒增强，需注意沟通边界与合规风险。",
    "比肩": "同类竞争上升，适合强化差异化与执行效率。",
    "劫财": "资源争夺加剧，合作与分配规则要先立后动。",
}
METHODOLOGY_SOURCES = [
    {
        "title": "紫微斗数基础",
        "source": "offline:ziwei-pro/basis",
        "focus": "本命盘/大限盘/流年盘与三方四正等基础术语。",
    },
    {
        "title": "紫微斗数宫位系统",
        "source": "offline:ziwei-pro/palace",
        "focus": "宫位结构与三方四正联动框架。",
    },
    {
        "title": "紫微斗数四化",
        "source": "offline:ziwei-pro/mutagen",
        "focus": "禄权科忌的动态意义与运限四化逻辑。",
    },
    {
        "title": "十四主星",
        "source": "offline:ziwei-pro/major-star",
        "focus": "主星定调与空宫借对宫的解释原则。",
    },
    {
        "title": "紫微斗数全书（目录）",
        "source": "offline:ziwei-pro/ancient-book",
        "focus": "古籍章节脉络：宫位、星曜、四化、运限。",
    },
    {
        "title": "iztro 官方文档 quick-start",
        "source": "offline:iztro/quick-start",
        "focus": "horoscope 返回结构与 mutagen 字段形态。",
    },
    {
        "title": "iztro 运限文档",
        "source": "offline:iztro/horoscope",
        "focus": "大限/流年运限对象及四化说明。",
    },
]


def normalize_gender(raw: str) -> str:
    token = str(raw).strip().lower()
    if token in {"male", "m", "1", "男"}:
        return "男"
    if token in {"female", "f", "0", "女"}:
        return "女"
    raise ValueError("gender 仅支持 male/female/男/女")


def parse_local_datetime(date_text: str, time_text: str, timezone_name: str) -> datetime:
    try:
        naive = datetime.strptime(f"{date_text} {time_text}", "%Y-%m-%d %H:%M")
    except ValueError as exc:
        raise ValueError("date/time 格式错误，需要 YYYY-MM-DD + HH:MM") from exc

    try:
        tz = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"无效时区: {timezone_name}") from exc

    return naive.replace(tzinfo=tz)


def apply_longitude(local_dt: datetime, longitude: float) -> tuple[datetime, int]:
    offset_min = int(round((longitude - 120.0) * 4))
    return local_dt + timedelta(minutes=offset_min), offset_min


def shichen_index(hour: int, minute: int) -> int:
    total = hour * 60 + minute
    if total >= 23 * 60 or total < 60:
        return 0
    return ((total - 60) // 120) + 1


def safe_anchor_date(year: int, birth_mm_dd: str) -> tuple[str, str | None]:
    month, day = map(int, birth_mm_dd.split("-"))
    try:
        dt = datetime(year, month, day)
        return dt.strftime("%Y-%m-%d"), None
    except ValueError:
        fallback = datetime(year, month, 28)
        note = f"生日锚点 {year}-{birth_mm_dd} 不存在，自动回退到 {fallback:%Y-%m-%d}"
        return fallback.strftime("%Y-%m-%d"), note


def unique_keep_order(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def normalize_palace_name(name: str) -> str:
    token = name if name.endswith("宫") else f"{name}宫"
    return PALACE_ALIAS_MAP.get(token, token)


def normalize_mutagen(mutagen: list[str]) -> list[str]:
    out = [MUTAGEN_KEY_TO_CN.get(x, x) for x in mutagen]
    return unique_keep_order(out)


def _ensure_iztro_py() -> Any:
    try:
        from iztro_py import astro
    except ModuleNotFoundError as exc:
        raise RuntimeError("未安装 iztro-py，请先安装：pip install iztro-py") from exc
    return astro


def _safe_names(stars: Any) -> list[str]:
    result: list[str] = []
    for star in stars or []:
        try:
            result.append(star.translate_name())
        except Exception:
            try:
                result.append(star.name)
            except Exception:
                result.append(str(star))
    return result


def ziwei_block_py(
    calc_date: str,
    calc_time: str,
    gender_cn: str,
    year: int | None,
    birth_mm_dd: str,
) -> dict[str, Any]:
    astro = _ensure_iztro_py()

    hour, minute = map(int, calc_time.split(":"))
    idx = shichen_index(hour, minute)
    chart = astro.by_solar(calc_date, idx, gender_cn)

    palaces: list[dict[str, Any]] = []
    for i in range(12):
        p = chart.palace(i)
        palaces.append(
            {
                "index": i,
                "name": normalize_palace_name(p.translate_name()),
                "stem": p.translate_heavenly_stem(),
                "branch": p.translate_earthly_branch(),
                "major": _safe_names(getattr(p, "major_stars", [])),
                "minor": _safe_names(getattr(p, "minor_stars", [])),
                "adj": _safe_names(getattr(p, "adjective_stars", [])),
                "decadal_range": [p.decadal.range[0], p.decadal.range[1]],
                "ages": list(p.ages),
            }
        )

    ming = palaces[0]
    body_name = normalize_palace_name(chart.get_body_palace().translate_name())
    body = next((p for p in palaces if p["name"] == body_name), None)

    horoscope = None
    anchor_note = None
    if year:
        anchor_date, anchor_note = safe_anchor_date(year, birth_mm_dd)
        hs = chart.horoscope(anchor_date)
        d = chart.palace(hs.decadal.index)
        y = chart.palace(hs.yearly.index)
        a = chart.palace(hs.age.index)
        mutagen_keys = list(hs.yearly.mutagen or [])
        horoscope = {
            "year": year,
            "anchor_date": anchor_date,
            "decadal": {
                "palace": normalize_palace_name(d.translate_name()),
                "stem_branch": f"{d.translate_heavenly_stem()}{d.translate_earthly_branch()}",
                "major": _safe_names(getattr(d, "major_stars", [])),
            },
            "yearly": {
                "palace": normalize_palace_name(y.translate_name()),
                "stem_branch": f"{y.translate_heavenly_stem()}{y.translate_earthly_branch()}",
                "major": _safe_names(getattr(y, "major_stars", [])),
                "mutagen": normalize_mutagen(mutagen_keys),
            },
            "age": {
                "name": hs.age.name,
                "palace": normalize_palace_name(a.translate_name()),
                "stem_branch": f"{a.translate_heavenly_stem()}{a.translate_earthly_branch()}",
            },
        }

    return {
        "engine": "py",
        "hour_index": idx,
        "hour_branch": BRANCHES[idx],
        "five_elements_class": chart.five_elements_class,
        "ming": ming,
        "body": body,
        "palaces": palaces,
        "horoscope": horoscope,
        "anchor_note": anchor_note,
    }


def ziwei_block_js(
    calc_date: str,
    calc_time: str,
    gender_cn: str,
    year: int | None,
    birth_mm_dd: str,
) -> dict[str, Any]:
    hour, minute = map(int, calc_time.split(":"))
    idx = shichen_index(hour, minute)

    script = Path(__file__).with_name("ziwei_engine_js.mjs")
    if not script.exists():
        raise RuntimeError(f"缺少 JS 引擎脚本: {script}")

    args = [
        "node",
        str(script),
        "--date",
        calc_date,
        "--time-index",
        str(idx),
        "--gender",
        gender_cn,
    ]
    if year:
        anchor_date, _ = safe_anchor_date(year, birth_mm_dd)
        args.extend(["--year", str(year), "--anchor-date", anchor_date])

    try:
        out = subprocess.check_output(args, text=True)
    except FileNotFoundError as exc:
        raise RuntimeError("当前环境缺少 node，无法启用 JS 备用引擎") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"JS 备用引擎执行失败: {exc}") from exc

    data = json.loads(out)
    for p in data.get("palaces", []):
        p["name"] = normalize_palace_name(p["name"])
    if data.get("ming"):
        data["ming"]["name"] = normalize_palace_name(data["ming"]["name"])
    if data.get("body"):
        data["body"]["name"] = normalize_palace_name(data["body"]["name"])
    if data.get("horoscope"):
        yearly = data["horoscope"].get("yearly", {})
        yearly["mutagen"] = normalize_mutagen(yearly.get("mutagen", []))
        data["horoscope"]["yearly"] = yearly
        data["horoscope"]["decadal"]["palace"] = normalize_palace_name(data["horoscope"]["decadal"]["palace"])
        data["horoscope"]["yearly"]["palace"] = normalize_palace_name(data["horoscope"]["yearly"]["palace"])
        data["horoscope"]["age"]["palace"] = normalize_palace_name(data["horoscope"]["age"]["palace"])

    data["engine"] = "js"
    data["hour_index"] = idx
    data["hour_branch"] = BRANCHES[idx]
    return data


def _ziwei_core(ziwei: dict[str, Any]) -> dict[str, Any]:
    core = {
        "five_elements_class": ziwei["five_elements_class"],
        "hour_index": ziwei["hour_index"],
        "hour_branch": ziwei["hour_branch"],
        "ming_stem_branch": f"{ziwei['ming']['stem']}{ziwei['ming']['branch']}",
        "ming_major": ziwei["ming"]["major"],
        "body_palace": ziwei["body"]["name"] if ziwei.get("body") else None,
        "palace_signature": [
            f"{p['name']}|{p['stem']}{p['branch']}|{','.join(p['major'])}" for p in ziwei.get("palaces", [])
        ],
    }
    if ziwei.get("horoscope"):
        core["yearly_palace"] = ziwei["horoscope"]["yearly"]["palace"]
        core["yearly_mutagen"] = ziwei["horoscope"]["yearly"]["mutagen"]
        core["decadal_palace"] = ziwei["horoscope"]["decadal"]["palace"]
    return core


def _core_diff(a: dict[str, Any], b: dict[str, Any]) -> dict[str, dict[str, Any]]:
    diff: dict[str, dict[str, Any]] = {}
    for key in sorted(set(a.keys()) | set(b.keys())):
        if a.get(key) != b.get(key):
            diff[key] = {"py": a.get(key), "js": b.get(key)}
    return diff


def bazi_block(
    calc_dt: datetime,
    gender_cn: str,
    sect: int,
    from_year: int | None,
    years: int,
    birth_mm_dd: str,
) -> dict[str, Any]:
    solar = Solar.fromYmdHms(calc_dt.year, calc_dt.month, calc_dt.day, calc_dt.hour, calc_dt.minute, 0)
    lunar = solar.getLunar()
    ec = lunar.getEightChar()
    ec.setSect(sect)

    def pillar_detail(prefix: str) -> dict[str, Any]:
        return {
            "ganzhi": getattr(ec, f"get{prefix}")(),
            "na_yin": getattr(ec, f"get{prefix}NaYin")(),
            "wu_xing": getattr(ec, f"get{prefix}WuXing")(),
            "shi_shen_gan": getattr(ec, f"get{prefix}ShiShenGan")(),
            "shi_shen_zhi": list(getattr(ec, f"get{prefix}ShiShenZhi")()),
            "hide_gan": list(getattr(ec, f"get{prefix}HideGan")()),
            "xun": getattr(ec, f"get{prefix}Xun")(),
            "xun_kong": getattr(ec, f"get{prefix}XunKong")(),
            "di_shi": getattr(ec, f"get{prefix}DiShi")(),
        }

    pillars = {
        "year": pillar_detail("Year"),
        "month": pillar_detail("Month"),
        "day": pillar_detail("Day"),
        "time": pillar_detail("Time"),
    }

    count: Counter[str] = Counter()
    for p in pillars.values():
        gz = p["ganzhi"]
        count[GAN_WUXING.get(gz[0], "?")] += 1
        count[ZHI_WUXING.get(gz[1], "?")] += 1

    is_male = gender_cn == "男"
    yun = ec.getYun(1 if is_male else 0)

    dayun: list[dict[str, Any]] = []
    for dy in yun.getDaYun()[:8]:
        if dy.getIndex() == 0:
            continue
        dayun.append(
            {
                "idx": dy.getIndex(),
                "ganzhi": dy.getGanZhi(),
                "age_range": f"{dy.getStartAge()}-{dy.getEndAge()}",
                "start_age": dy.getStartAge(),
                "end_age": dy.getEndAge(),
                "start_year": dy.getStartYear(),
                "end_year": dy.getEndYear(),
            }
        )

    start_year = from_year or datetime.now().year
    liunian: list[dict[str, Any]] = []
    for yy in range(start_year, start_year + max(1, years)):
        anchor_date, _ = safe_anchor_date(yy, birth_mm_dd)
        ay, am, ad = map(int, anchor_date.split("-"))
        yec = Solar.fromYmdHms(ay, am, ad, 12, 0, 0).getLunar().getEightChar()
        liunian.append(
            {
                "year": yy,
                "ganzhi": yec.getYear(),
                "na_yin": yec.getYearNaYin(),
                "shi_shen_gan": yec.getYearShiShenGan(),
                "shi_shen_zhi": list(yec.getYearShiShenZhi()),
            }
        )

    return {
        "lunar": f"{lunar.getYearInChinese()}年{lunar.getMonthInChinese()}月{lunar.getDayInChinese()}",
        "sect": sect,
        "pillars": pillars,
        "day_master": pillars["day"]["ganzhi"][0],
        "minggong": ec.getMingGong(),
        "shengong": ec.getShenGong(),
        "taiyuan": ec.getTaiYuan(),
        "minggong_nayin": ec.getMingGongNaYin(),
        "shengong_nayin": ec.getShenGongNaYin(),
        "taiyuan_nayin": ec.getTaiYuanNaYin(),
        "wuxing_count": dict(count),
        "yun_start": {
            "solar": yun.getStartSolar().toYmd(),
            "year": yun.getStartYear(),
            "month": yun.getStartMonth(),
            "day": yun.getStartDay(),
            "hour": yun.getStartHour(),
        },
        "dayun": dayun,
        "liunian": liunian,
    }


def palace_of(ziwei: dict[str, Any], name: str) -> dict[str, Any] | None:
    for p in ziwei.get("palaces", []):
        if p.get("name") == name:
            return p
    return None


def star_insight(stars: list[str], mode: str, default: str) -> str:
    for s in stars:
        if s in STAR_HINTS and STAR_HINTS[s].get(mode):
            return STAR_HINTS[s][mode]
    return default


def summarize_wuxing(w: dict[str, int]) -> tuple[str, str]:
    focus = sorted(((v, k) for k, v in w.items() if k != "?"), reverse=True)
    if not focus:
        return "五行信息不足。", "建议补充更精确出生时刻后再复核。"
    strong = "/".join(k for _, k in focus[:2])
    weak = "/".join(k for _, k in focus[-2:])
    return (
        f"五行结构偏向 {strong}，相对偏弱 {weak}。",
        "策略上优先补短板，避免在单一维度过度用力。",
    )


def current_dayun(dayun: list[dict[str, Any]], target_age: int) -> dict[str, Any] | None:
    for item in dayun:
        if item["start_age"] <= target_age <= item["end_age"]:
            return item
    return dayun[0] if dayun else None


def dayun_outlook(dayun: list[dict[str, Any]], target_age: int) -> tuple[str, str]:
    if not dayun:
        return "当前大运信息不足。", "建议补充更多参数后再解读阶段走势。"

    cur = current_dayun(dayun, target_age)
    if not cur:
        return "当前大运信息不足。", "建议补充更多参数后再解读阶段走势。"

    idx = next((i for i, x in enumerate(dayun) if x["idx"] == cur["idx"]), 0)
    nxt = dayun[idx + 1] if idx + 1 < len(dayun) else None
    line1 = f"当前位于第{cur['idx']}步大运（{cur['ganzhi']}，{cur['age_range']}岁），阶段主题是能力结构升级与责任扩大。"
    if nxt:
        line2 = (
            f"下一步大运为{nxt['ganzhi']}（{nxt['age_range']}岁），可提前观察能力结构与角色边界变化，"
            "减少在运势切换点的被动性。"
        )
    else:
        line2 = "后续大运信息已接近样本上限，可按年度继续滚动复盘。"
    return line1, line2


def liunian_outlook(liunian: list[dict[str, Any]], limit: int = 10) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for item in liunian[: max(1, limit)]:
        tg = item.get("shi_shen_gan", "")
        out.append(
            {
                "year": str(item["year"]),
                "ganzhi": item["ganzhi"],
                "focus": TEN_GOD_TREND.get(tg, "年度重心建议以稳节奏、强执行、控风险为主。"),
            }
        )
    return out


def build_consulting(ziwei: dict[str, Any], bazi: dict[str, Any], target_age: int) -> dict[str, Any]:
    ming_major = ziwei["ming"].get("major", [])
    ming_text = "、".join(ming_major) if ming_major else "无主星（空宫）"
    body_name = ziwei["body"]["name"] if ziwei.get("body") else "未知"
    dm = bazi["day_master"]

    wuxing_note, wuxing_action = summarize_wuxing(bazi.get("wuxing_count", {}))
    cur_dayun = current_dayun(bazi.get("dayun", []), target_age)
    cur_dayun_text = (
        f"{cur_dayun['ganzhi']}（{cur_dayun['age_range']}岁）" if cur_dayun else "信息不足"
    )

    career_palace = palace_of(ziwei, "官禄宫") or {}
    relation_palace = palace_of(ziwei, "夫妻宫") or {}
    health_palace = palace_of(ziwei, "疾厄宫") or {}
    wealth_palace = palace_of(ziwei, "财帛宫") or {}

    career_major = career_palace.get("major", [])
    relation_major = relation_palace.get("major", [])
    health_major = health_palace.get("major", [])
    wealth_major = wealth_palace.get("major", [])

    year_info = ziwei.get("horoscope", {}).get("yearly", {})
    mutagen = year_info.get("mutagen", [])
    mutagen_text = "、".join(mutagen) if mutagen else "无"

    dayun_line1, dayun_line2 = dayun_outlook(bazi.get("dayun", []), target_age)

    def sec(conclusion: str, signals: list[str], classics: list[str]) -> dict[str, Any]:
        return {"结论": conclusion, "盘面": signals, "经验": classics}

    return {
        "positioning": sec(
            f"日主{dm}，命宫格局为{ming_text}，整体路径更偏“长期复利、体系沉淀”。",
            [
                f"命宫落{ziwei['ming']['stem']}{ziwei['ming']['branch']}，主星结构：{ming_text}。",
                f"身宫在{body_name}，现实执行重心与责任议题绑定。",
                wuxing_note,
            ],
            [
                star_insight(ming_major, "strength", "空宫格局重后天修为，宜以方法论与系统能力立身。"),
                star_insight(ming_major, "challenge", "空宫借星断事，关键在主线稳定与阶段复盘。"),
                f"五行取向：{wuxing_action}",
            ],
        ),
        "career": sec(
            "事业宫位信号偏向“先深耕、后扩张”，适合走专业壁垒路线。",
            [
                f"官禄宫主星：{'、'.join(career_major) if career_major else '无主星'}。",
                f"当前年龄对应大运：{cur_dayun_text}。",
                f"本年四化：{mutagen_text}。",
            ],
            [
                star_insight(career_major, "career", "事业研判重“职责-权柄-资源”三者是否同向。"),
                "流年宫与官禄宫同频时，常见职位/职责结构变化。",
                "传统经验强调“先定轴后扩边”，避免在运限转换点盲目横跳。",
            ],
        ),
        "relationship": sec(
            "关系议题重在节奏与边界，先看结构稳定性，再看情绪波动。",
            [
                f"夫妻宫主星：{'、'.join(relation_major) if relation_major else '无主星'}。",
                "关系议题通常在压力期被放大，需提前约定冲突处理流程。",
            ],
            [
                star_insight(relation_major, "strength", "夫妻宫主星多主沟通模式，先辨“表达节奏”后定结论。"),
                star_insight(relation_major, "challenge", "传统断法多忌情绪峰值时做终局判断。"),
            ],
        ),
        "health": sec(
            "健康位重在“节律与恢复”，不宜仅以短期强度判断状态。",
            [
                f"疾厄宫主星：{'、'.join(health_major) if health_major else '无主星'}。",
                "高压阶段要防慢性透支，而不是只盯短期爆发。",
            ],
            [
                star_insight(health_major, "challenge", "疾厄宫研判宜先看长期负荷，再看阶段波动。"),
                "传统经验强调“先稳节律，再谈强度”。",
            ],
        ),
        "finance": sec(
            "财务位宜先判风险预算与回撤承受，再判收益扩张节奏。",
            [
                f"财帛宫主星：{'、'.join(wealth_major) if wealth_major else '无主星'}。",
                f"流年十神节奏提示：{bazi['liunian'][0]['year']}年起未来几年波动管理很关键。"
                if bazi.get("liunian")
                else "流年信息不足。",
            ],
            [
                star_insight(wealth_major, "wealth", "财帛宫多主资金风格，宜分层研判而非单点押注。"),
                "传统经验重“先守后攻、先纪后势”。",
            ],
        ),
        "risk": sec(
            "命理结论首先受输入精度约束，边界时辰与地区口径必须复核。",
            [
                "时辰跨界会改变命身宫及部分断语权重。",
                "默认口径为东八区（Asia/Shanghai）和120.0E，偏离地区需显式设定经度。",
                "命理只能作为决策辅助，不能替代医疗/法律/投资等专业意见。",
            ],
            [
                "传统断盘先校准时空口径，再进入解读层。",
                "边界时辰建议采用多档复盘，比较宫位与四化变化。",
            ],
        ),
        "dayun": sec(dayun_line1, [], [dayun_line2]),
        "liunian": liunian_outlook(bazi.get("liunian", []), 15),
    }


def _format_items(items: list[str], empty: str = "无") -> str:
    return "、".join(items) if items else empty


def _format_lines(title: str, items: list[str]) -> list[str]:
    out = [f"### {title}"]
    if not items:
        out.append("- 无")
        return out
    for i, item in enumerate(items, 1):
        out.append(f"- {title}{i}：{item}")
    return out


def render_markdown(payload: dict[str, Any], template: str) -> str:
    z = payload["ziwei"]
    b = payload["bazi"]
    c = payload["consulting"]
    meta = payload["meta"]

    lines: list[str] = [
        "# Destiny Fusion Pro 专业命理报告",
        "",
        "> 紫微斗数 × 八字（咨询交付版）",
        "",
        "## 0) 排盘口径",
        f"- 出生输入：{meta['input']['date']} {meta['input']['time']} / {meta['input']['gender_raw']}",
        f"- 默认时区：{meta['timezone']}（东八区基准）",
        f"- 默认经度：{meta['longitude']}°E（120.0=北京基准）",
        f"- 统一计算时间：{meta['calc']['date']} {meta['calc']['time']}（经度修正 {meta['calc']['offset_min']} 分钟）",
        f"- 紫微引擎：{payload['engine']['used']}（请求：{payload['engine']['requested']}）",
    ]

    if payload["engine"].get("fallback"):
        lines.append(f"- 引擎回退：{payload['engine']['fallback']}")
    for warn in payload["engine"].get("warnings", []):
        lines.append(f"- 注意：{warn}")

    lines.extend(
        [
            "",
            "## 1) 紫微斗数全盘",
            f"- 五行局：{z['five_elements_class']}",
            f"- 时辰：{z['hour_index']}（{z['hour_branch']}时）",
            f"- 命宫：{z['ming']['name']} {z['ming']['stem']}{z['ming']['branch']}（主星：{_format_items(z['ming']['major'], '无主星')}）",
            f"- 身宫：{z['body']['name'] if z.get('body') else '未知'}",
        ]
    )

    if z.get("horoscope"):
        h = z["horoscope"]
        lines.extend(
            [
                f"- 年度锚点：{h['year']} / {h['anchor_date']}",
                f"- 大限宫：{h['decadal']['palace']}（{h['decadal']['stem_branch']}）",
                f"- 流年宫：{h['yearly']['palace']}（{h['yearly']['stem_branch']}）",
                f"- 岁位：{h['age']['name']} @ {h['age']['palace']}",
                f"- 四化：{_format_items(h['yearly']['mutagen'])}",
            ]
        )

    lines.extend(["", "### 十二宫主星摘要"])
    for p in z["palaces"]:
        lines.append(
            f"- {p['name']}（{p['stem']}{p['branch']}）｜主星：{_format_items(p['major'], '无主星')}｜辅星：{_format_items(p['minor'])}｜杂曜：{_format_items(p['adj'])}"
        )

    lines.extend(
        [
            "",
            "## 2) 八字深度",
            f"- 农历：{b['lunar']}（sect={b['sect']}）",
            f"- 日主：{b['day_master']}｜命宫：{b['minggong']}（{b['minggong_nayin']}）｜身宫：{b['shengong']}（{b['shengong_nayin']}）｜胎元：{b['taiyuan']}（{b['taiyuan_nayin']}）",
            f"- 五行计数：木{b['wuxing_count'].get('木', 0)} 火{b['wuxing_count'].get('火', 0)} 土{b['wuxing_count'].get('土', 0)} 金{b['wuxing_count'].get('金', 0)} 水{b['wuxing_count'].get('水', 0)}",
            "",
            "### 四柱详解",
        ]
    )

    pillar_labels = {"year": "年柱", "month": "月柱", "day": "日柱", "time": "时柱"}
    for key in ["year", "month", "day", "time"]:
        p = b["pillars"][key]
        lines.append(
            f"- {pillar_labels[key]} {p['ganzhi']}｜纳音 {p['na_yin']}｜五行 {p['wu_xing']}｜十神(干:{p['shi_shen_gan']} / 支:{_format_items(p['shi_shen_zhi'])})｜藏干 {_format_items(p['hide_gan'])}｜旬空 {p['xun_kong']}"
        )

    lines.extend(["", "## 3) 运限研判"])
    lines.append("### 大运阶段")
    dayun_limit = 5 if template == "lite" else 8
    for item in b["dayun"][:dayun_limit]:
        lines.append(
            f"- 大运{item['idx']}：{item['ganzhi']}｜年龄 {item['age_range']}｜年份 {item['start_year']}-{item['end_year']}"
        )

    lines.append("")
    lines.append("### 流年节奏")
    ly_limit = 5 if template == "lite" else (15 if template == "executive" else 10)
    for item in c["liunian"][:ly_limit]:
        lines.append(f"- {item['year']}（{item['ganzhi']}）：{item['focus']}")

    lines.extend(["", "## 4) 传统研判框架（供二次解读）"])
    section_titles = [
        ("positioning", "总定位"),
        ("career", "事业"),
        ("relationship", "关系"),
        ("health", "健康"),
        ("finance", "财务"),
        ("risk", "风险边界"),
        ("dayun", "大运策略"),
    ]

    for key, title in section_titles:
        sec = c[key]
        lines.append(f"### {title}")
        lines.append(f"- 结论：{sec['结论']}")
        if template != "lite":
            for i, sig in enumerate(sec.get("盘面", []), 1):
                lines.append(f"- 盘面{i}：{sig}")
        for i, exp in enumerate(sec.get("经验", []), 1):
            lines.append(f"- 经验{i}：{exp}")

    if payload.get("chart"):
        chart_type = str(payload["chart"].get("type", "svg")).upper()
        lines.extend(["", "## 排盘图", f"- {chart_type}：{payload['chart']['path']}"])
        if payload["chart"].get("backend"):
            lines.append(f"- 生成引擎：{payload['chart']['backend']}")
        for warning in payload["chart"].get("warnings", []):
            lines.append(f"- 注意：{warning}")

    if payload["engine"].get("diff"):
        lines.extend(["", "## 双引擎差异"])
        for k, v in payload["engine"]["diff"].items():
            lines.append(f"- {k}: py={v['py']} | js={v['js']}")

    lines.extend(
        [
            "",
            "## 方法论依据",
            "- 采用“命宫定调 + 三方四正联动 + 四化动态 + 大限流年交叉”框架。",
            "- 输出为传统命理研究与咨询辅助，不替代医疗、法律、投资等专业意见。",
            "",
            "## 免责声明",
            "- 报告仅供命理研究与个人规划参考。",
            "- 重大决策请结合现实数据与专业建议。",
        ]
    )
    return "\n".join(lines)


def _chunks(text: str, size: int) -> list[str]:
    if len(text) <= size:
        return [text]
    out = []
    i = 0
    while i < len(text):
        out.append(text[i : i + size])
        i += size
    return out


def _clip_items(items: list[str], limit: int) -> list[str]:
    if len(items) <= limit:
        return items
    return items[:limit] + ["…"]


def _palace_palette(name: str) -> tuple[str, str]:
    return PALACE_COLOR_MAP.get(name, ("#6c5a44", "#efe7dd"))


def _compact_error(text: str, limit: int = 180) -> str:
    clean = " ".join(str(text or "").strip().split())
    if len(clean) <= limit:
        return clean
    return clean[:limit] + "..."


def _render_backend_once(
    backend: str,
    svg: str,
    out: Path,
    chart_quality: int,
) -> dict[str, Any]:
    if backend == "cairosvg":
        out.write_bytes(render_jpg_cairosvg(svg, quality=chart_quality))
        return {"path": str(out), "type": "jpg", "backend": "cairosvg", "warnings": []}
    raise RuntimeError(f"不支持的 chart backend: {backend}")


def render_svg(payload: dict[str, Any]) -> str:
    z = payload["ziwei"]
    meta = payload["meta"]

    box_w, box_h, gap = 240, 168, 16
    cols, rows = 4, 4
    top_offset = 132
    grid_h = rows * box_h + (rows + 1) * gap
    width = cols * box_w + (cols + 1) * gap
    height = top_offset + grid_h + 12

    positions = [
        (1, 0),
        (2, 0),
        (3, 0),
        (3, 1),
        (3, 2),
        (3, 3),
        (2, 3),
        (1, 3),
        (0, 3),
        (0, 2),
        (0, 1),
        (0, 0),
    ]

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        "<defs>",
        '<linearGradient id="bgGrad" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#f7f1e7"/><stop offset="55%" stop-color="#f2e8dc"/><stop offset="100%" stop-color="#eadcc9"/></linearGradient>',
        '<linearGradient id="headGrad" x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stop-color="#3f3326"/><stop offset="100%" stop-color="#624b33"/></linearGradient>',
        '<linearGradient id="coreGrad" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#fffefb"/><stop offset="100%" stop-color="#f7efe0"/></linearGradient>',
        '<pattern id="dotPattern" width="20" height="20" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r="1" fill="#d9c8b4" fill-opacity="0.24"/></pattern>',
        '<filter id="cardShadow" x="-20%" y="-20%" width="140%" height="160%"><feDropShadow dx="0" dy="2" stdDeviation="2.4" flood-color="#2f2418" flood-opacity="0.16"/></filter>',
        '<style><![CDATA[',
        f'.bg{{fill:url(#bgGrad)}}.pat{{fill:url(#dotPattern)}}.head{{fill:url(#headGrad)}}.title{{font:700 30px {ZH_FONT_STACK};fill:#f8f1e8;letter-spacing:1px}}.meta{{font:500 13px {ZH_FONT_STACK};fill:#f0e4d6}}.sub{{font:500 12px {ZH_FONT_STACK};fill:#6a5743}}.card{{fill:#fffdfa;stroke:#3f3326;stroke-width:1.05}}.tag{{font:700 16px {ZH_FONT_STACK};fill:#fffdfa}}.tagmeta{{font:600 12px {ZH_FONT_STACK};fill:#fff3e8}}.major{{font:700 13px {ZH_FONT_STACK};fill:#2f251c}}.minor{{font:500 12px {ZH_FONT_STACK};fill:#4a3c30}}.adj{{font:500 11.5px {ZH_FONT_STACK};fill:#615244}}.core{{fill:url(#coreGrad);stroke:#3f3326;stroke-width:1.25}}.coretitle{{font:700 20px {ZH_FONT_STACK};fill:#2d241a}}.coreline{{font:500 13px {ZH_FONT_STACK};fill:#45372b}}.mutagen{{font:700 13px {ZH_FONT_STACK};fill:#7a3f1f}}.footer{{font:500 11px {ZH_FONT_STACK};fill:#76614c}}',
        ']]></style>',
        "</defs>",
        f'<rect class="bg" x="0" y="0" width="{width}" height="{height}"/>',
        f'<rect class="pat" x="0" y="0" width="{width}" height="{height}"/>',
        f'<rect class="head" x="{gap}" y="{gap}" width="{width - gap * 2}" height="96" rx="18"/>',
        f'<text class="title" x="{gap + 22}" y="{gap + 40}">Destiny Fusion Pro 紫微斗数排盘</text>',
        f'<text class="meta" x="{gap + 22}" y="{gap + 64}">{escape(meta["input"]["date"])} {escape(meta["input"]["time"])} / {escape(meta["input"]["gender"])} | 时区 {escape(meta["timezone"])} | 经度 {meta["longitude"]}E</text>',
        f'<text class="meta" x="{gap + 22}" y="{gap + 84}">统一计算时间 {escape(meta["calc"]["date"])} {escape(meta["calc"]["time"])}（经度修正 {meta["calc"]["offset_min"]} 分钟） | 引擎 {escape(payload["engine"]["used"])}</text>',
    ]

    for p, (col, row) in zip(z["palaces"], positions):
        x = gap + col * (box_w + gap)
        y = top_offset + gap + row * (box_h + gap)
        accent, soft = _palace_palette(p["name"])
        lines.append(
            f'<rect class="card" filter="url(#cardShadow)" x="{x}" y="{y}" width="{box_w}" height="{box_h}" rx="14"/>'
        )
        lines.append(f'<rect x="{x}" y="{y}" width="{box_w}" height="36" rx="14" fill="{accent}"/>')
        lines.append(f'<rect x="{x}" y="{y + 24}" width="{box_w}" height="{box_h - 24}" rx="0" fill="{soft}" fill-opacity="0.45"/>')
        lines.append(f'<text class="tag" x="{x + 12}" y="{y + 24}">{escape(p["name"])}</text>')
        lines.append(
            f'<text class="tagmeta" x="{x + box_w - 12}" y="{y + 24}" text-anchor="end">{escape(p["stem"] + p["branch"])}</text>'
        )

        major_text = f"主星：{_format_items(_clip_items(p['major'], 4), '无主星')}"
        minor_text = f"辅星：{_format_items(_clip_items(p['minor'], 5), '无')}"
        adj_text = f"杂曜：{_format_items(_clip_items(p['adj'], 5), '无')}"
        rows: list[tuple[str, str]] = []
        for seg in _chunks(major_text, 16):
            rows.append(("major", seg))
        for seg in _chunks(minor_text, 16):
            rows.append(("minor", seg))
        for seg in _chunks(adj_text, 16):
            rows.append(("adj", seg))

        max_rows = 6
        if len(rows) > max_rows:
            rows = rows[: max_rows - 1] + [("adj", "…")]

        yy = y + 56
        for klass, text in rows:
            lines.append(f'<text class="{klass}" x="{x + 12}" y="{yy}">{escape(text)}</text>')
            yy += 18

        lines.append(
            f'<text class="sub" x="{x + 12}" y="{y + box_h - 12}">大限 {p["decadal_range"][0]}-{p["decadal_range"][1]} 岁</text>'
        )

    cx = gap + (box_w + gap)
    cy = top_offset + gap + (box_h + gap)
    cw = box_w * 2 + gap
    ch = box_h * 2 + gap
    lines.append(f'<rect class="core" filter="url(#cardShadow)" x="{cx}" y="{cy}" width="{cw}" height="{ch}" rx="16"/>')
    lines.append(f'<text class="coretitle" x="{cx + 18}" y="{cy + 30}">中宫总览</text>')

    center = [
        f"命宫：{z['ming']['stem']}{z['ming']['branch']}  主星 {_format_items(_clip_items(z['ming']['major'], 4), '无主星')}",
        f"身宫：{z['body']['name'] if z.get('body') else '未知'}",
        f"五行局：{z['five_elements_class']}",
    ]
    if z.get("horoscope"):
        center.append(f"{z['horoscope']['year']} 流年宫：{z['horoscope']['yearly']['palace']}")
        center.append(f"大限宫：{z['horoscope']['decadal']['palace']}  岁位：{z['horoscope']['age']['name']}")
        center.append(f"四化：{_format_items(_clip_items(z['horoscope']['yearly']['mutagen'], 6), '无')}")

    yy = cy + 56
    for idx, item in enumerate(center):
        klass = "mutagen" if item.startswith("四化") else "coreline"
        for seg in _chunks(item, 28):
            lines.append(f'<text class="{klass}" x="{cx + 18}" y="{yy}">{escape(seg)}</text>')
            yy += 22
        if idx == 2:
            lines.append(f'<line x1="{cx + 18}" y1="{yy - 10}" x2="{cx + cw - 18}" y2="{yy - 10}" stroke="#c9b8a2" stroke-width="1"/>')

    lines.append(
        f'<text class="footer" x="{width - gap - 8}" y="{height - 14}" text-anchor="end">offline renderer • local svg/cairosvg</text>'
    )

    lines.append("</svg>")
    return "\n".join(lines)


def render_jpg_cairosvg(svg: str, quality: int = 92) -> bytes:
    try:
        import cairosvg
    except ModuleNotFoundError as exc:
        raise RuntimeError("生成 JPG 需要 cairosvg，请先安装：pip install cairosvg") from exc

    try:
        from PIL import Image
    except ModuleNotFoundError as exc:
        raise RuntimeError("生成 JPG 需要 pillow，请先安装：pip install pillow") from exc

    quality = max(1, min(100, int(quality)))
    png_bytes = cairosvg.svg2png(bytestring=svg.encode("utf-8"), scale=2.2)
    with Image.open(io.BytesIO(png_bytes)) as img:
        rgb = img.convert("RGB")
        out = io.BytesIO()
        rgb.save(out, format="JPEG", quality=quality, optimize=True)
        return out.getvalue()


def maybe_generate_chart(
    payload: dict[str, Any],
    chart: str,
    chart_out: str | None,
    chart_quality: int,
    chart_backend: str,
) -> dict[str, Any] | None:
    if chart == "none":
        return None
    svg = render_svg(payload)
    if chart_out:
        out = Path(chart_out).expanduser().resolve()
    else:
        stamp = payload["meta"]["calc"]["date"].replace("-", "") + "_" + payload["meta"]["calc"]["time"].replace(":", "")
        ext = "svg" if chart == "svg" else "jpg"
        out = Path.cwd() / f"destiny_fusion_chart_{stamp}.{ext}"
    out.parent.mkdir(parents=True, exist_ok=True)
    if chart == "svg":
        out.write_text(svg, encoding="utf-8")
        return {"path": str(out), "type": "svg"}
    backend = str(chart_backend or "auto").lower()
    warnings: list[str] = []
    allowed = {"auto", "cairosvg"}
    if backend not in allowed:
        backend = "auto"
        warnings.append("chart-backend 参数无效，已自动使用 auto")

    if backend == "auto":
        attempts = [("cairosvg", "cairosvg")]
        for key, label in attempts:
            try:
                result = _render_backend_once(key, svg, out, chart_quality)
                result["warnings"] = warnings
                return result
            except Exception as exc:
                warnings.append(f"{label} 渲染失败：{_compact_error(exc)}")
        raise RuntimeError("JPG 渲染失败（已跳过）")

    result = _render_backend_once(backend, svg, out, chart_quality)
    result["warnings"] = warnings
    return result


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    gender_cn = normalize_gender(args.gender)

    input_local = parse_local_datetime(args.date, args.time, args.timezone)
    calc_local, offset_min = apply_longitude(input_local, args.longitude)
    calc_date = calc_local.strftime("%Y-%m-%d")
    calc_time = calc_local.strftime("%H:%M")
    birth_mm_dd = args.date[5:]

    target_year = args.year or calc_local.year
    target_age = target_year - int(args.date[:4]) + 1

    ziwei_py = None
    ziwei_js = None
    engine_info: dict[str, Any] = {
        "requested": args.engine,
        "used": args.engine,
        "warnings": [],
    }

    if args.engine in {"py", "dual"}:
        try:
            ziwei_py = ziwei_block_py(calc_date, calc_time, gender_cn, args.year, birth_mm_dd)
        except Exception as exc:
            engine_info["warnings"].append(f"py 引擎失败：{exc}")

    if args.engine in {"js", "dual"}:
        try:
            ziwei_js = ziwei_block_js(calc_date, calc_time, gender_cn, args.year, birth_mm_dd)
        except Exception as exc:
            engine_info["warnings"].append(f"js 引擎失败：{exc}")

    if args.engine == "py":
        if ziwei_py is None and ziwei_js is None:
            raise RuntimeError("py/js 引擎都失败，无法生成紫微盘")
        if ziwei_py is None:
            ziwei = ziwei_js
            engine_info["used"] = "js"
            engine_info["fallback"] = "py->js"
        else:
            ziwei = ziwei_py
            engine_info["used"] = "py"
    elif args.engine == "js":
        if ziwei_py is None and ziwei_js is None:
            raise RuntimeError("js/py 引擎都失败，无法生成紫微盘")
        if ziwei_js is None:
            ziwei = ziwei_py
            engine_info["used"] = "py"
            engine_info["fallback"] = "js->py"
        else:
            ziwei = ziwei_js
            engine_info["used"] = "js"
    else:
        if ziwei_py is None and ziwei_js is None:
            raise RuntimeError("dual 模式下 py/js 全部失败")
        ziwei = ziwei_py or ziwei_js
        engine_info["used"] = "py" if ziwei_py else "js"
        if ziwei_py and ziwei_js:
            engine_info["diff"] = _core_diff(_ziwei_core(ziwei_py), _ziwei_core(ziwei_js))

    if ziwei.get("anchor_note"):
        engine_info["warnings"].append(ziwei["anchor_note"])

    bazi = bazi_block(calc_local, gender_cn, args.sect, args.from_year, args.years, birth_mm_dd)
    consulting = build_consulting(ziwei, bazi, target_age)

    payload: dict[str, Any] = {
        "meta": {
            "input": {
                "date": args.date,
                "time": args.time,
                "gender": gender_cn,
                "gender_raw": args.gender,
            },
            "timezone": args.timezone,
            "longitude": args.longitude,
            "calc": {
                "date": calc_date,
                "time": calc_time,
                "offset_min": offset_min,
            },
            "target_year": target_year,
            "target_age": target_age,
        },
        "engine": engine_info,
        "ziwei": ziwei,
        "bazi": bazi,
        "consulting": consulting,
        "methodology": {
            "summary": "命宫定调 + 三方四正联动 + 四化动态 + 大限流年交叉",
            "sources": METHODOLOGY_SOURCES,
        },
    }

    try:
        chart_info = maybe_generate_chart(payload, args.chart, args.chart_out, args.chart_quality, args.chart_backend)
        if chart_info:
            payload["chart"] = chart_info
    except Exception as exc:
        payload["engine"]["warnings"].append(f"排盘图生成失败，已跳过：{_compact_error(exc)}")

    return payload


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--time", required=True, help="HH:MM")
    ap.add_argument("--gender", required=True, help="male/female/男/女")
    ap.add_argument("--timezone", default="Asia/Shanghai", help="IANA 时区，默认 Asia/Shanghai")
    ap.add_argument("--longitude", type=float, default=120.0, help="出生地经度，默认 120.0（北京基准）")
    ap.add_argument("--engine", choices=["py", "js", "dual"], default="py", help="紫微引擎")
    ap.add_argument("--year", type=int, default=None, help="年度锚点")
    ap.add_argument("--sect", type=int, default=2, help="八字 sect 参数")
    ap.add_argument("--from-year", type=int, default=None, help="流年起始年")
    ap.add_argument("--years", type=int, default=10, help="流年年数")
    ap.add_argument("--template", choices=["lite", "pro", "executive"], default="pro")
    ap.add_argument("--chart", choices=["none", "svg", "jpg"], default="jpg")
    ap.add_argument("--chart-out", default=None)
    ap.add_argument("--chart-quality", type=int, default=92, help="JPG 质量（1-100），默认 92")
    ap.add_argument("--chart-backend", choices=["auto", "cairosvg"], default="auto")
    ap.add_argument("--format", choices=["markdown", "json"], default="markdown")
    args = ap.parse_args()

    payload = build_payload(args)
    payload["template"] = args.template

    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(payload, args.template))


if __name__ == "__main__":
    main()
