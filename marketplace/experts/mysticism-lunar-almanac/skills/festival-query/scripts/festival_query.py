#!/usr/bin/env python3
"""节日查询工具 - 支持中国传统节日、二十四节气、欧美主流节日查询"""

import argparse
import sys
from datetime import datetime, date, timedelta

from zhdate import ZhDate

# ──────────────────────────────────────────────
# 24 Solar Terms (二十四节气) - precomputed per year
# Source: astronomical calculation; covers 2020-2030
# Each entry: (month, day)
# ──────────────────────────────────────────────
SOLAR_TERMS_TABLE = {
    #  year: {term_cn: (month, day), ...}
    2020: {"小寒":(1,6),"大寒":(1,20),"立春":(2,4),"雨水":(2,19),"惊蛰":(3,5),"春分":(3,20),
            "清明":(4,4),"谷雨":(4,19),"立夏":(5,5),"小满":(5,20),"芒种":(6,5),"夏至":(6,21),
            "小暑":(7,6),"大暑":(7,22),"立秋":(8,7),"处暑":(8,22),"白露":(9,7),"秋分":(9,22),
            "寒露":(10,8),"霜降":(10,23),"立冬":(11,7),"小雪":(11,22),"大雪":(12,7),"冬至":(12,21)},
    2021: {"小寒":(1,5),"大寒":(1,20),"立春":(2,3),"雨水":(2,18),"惊蛰":(3,5),"春分":(3,20),
            "清明":(4,4),"谷雨":(4,20),"立夏":(5,5),"小满":(5,21),"芒种":(6,5),"夏至":(6,21),
            "小暑":(7,7),"大暑":(7,22),"立秋":(8,7),"处暑":(8,23),"白露":(9,7),"秋分":(9,23),
            "寒露":(10,8),"霜降":(10,23),"立冬":(11,7),"小雪":(11,22),"大雪":(12,7),"冬至":(12,21)},
    2022: {"小寒":(1,5),"大寒":(1,20),"立春":(2,4),"雨水":(2,19),"惊蛰":(3,5),"春分":(3,20),
            "清明":(4,5),"谷雨":(4,20),"立夏":(5,5),"小满":(5,21),"芒种":(6,6),"夏至":(6,21),
            "小暑":(7,7),"大暑":(7,23),"立秋":(8,7),"处暑":(8,23),"白露":(9,7),"秋分":(9,23),
            "寒露":(10,8),"霜降":(10,23),"立冬":(11,7),"小雪":(11,22),"大雪":(12,7),"冬至":(12,22)},
    2023: {"小寒":(1,5),"大寒":(1,20),"立春":(2,4),"雨水":(2,19),"惊蛰":(3,6),"春分":(3,21),
            "清明":(4,5),"谷雨":(4,20),"立夏":(5,6),"小满":(5,21),"芒种":(6,6),"夏至":(6,21),
            "小暑":(7,7),"大暑":(7,23),"立秋":(8,8),"处暑":(8,23),"白露":(9,8),"秋分":(9,23),
            "寒露":(10,8),"霜降":(10,24),"立冬":(11,8),"小雪":(11,22),"大雪":(12,7),"冬至":(12,22)},
    2024: {"小寒":(1,6),"大寒":(1,20),"立春":(2,4),"雨水":(2,19),"惊蛰":(3,5),"春分":(3,20),
            "清明":(4,4),"谷雨":(4,19),"立夏":(5,5),"小满":(5,20),"芒种":(6,5),"夏至":(6,21),
            "小暑":(7,6),"大暑":(7,22),"立秋":(8,7),"处暑":(8,22),"白露":(9,7),"秋分":(9,22),
            "寒露":(10,8),"霜降":(10,23),"立冬":(11,7),"小雪":(11,22),"大雪":(12,6),"冬至":(12,21)},
    2025: {"小寒":(1,5),"大寒":(1,20),"立春":(2,3),"雨水":(2,18),"惊蛰":(3,5),"春分":(3,20),
            "清明":(4,4),"谷雨":(4,20),"立夏":(5,5),"小满":(5,21),"芒种":(6,5),"夏至":(6,21),
            "小暑":(7,7),"大暑":(7,22),"立秋":(8,7),"处暑":(8,23),"白露":(9,7),"秋分":(9,22),
            "寒露":(10,8),"霜降":(10,23),"立冬":(11,7),"小雪":(11,22),"大雪":(12,7),"冬至":(12,21)},
    2026: {"小寒":(1,5),"大寒":(1,20),"立春":(2,4),"雨水":(2,18),"惊蛰":(3,5),"春分":(3,20),
            "清明":(4,5),"谷雨":(4,20),"立夏":(5,5),"小满":(5,21),"芒种":(6,5),"夏至":(6,21),
            "小暑":(7,7),"大暑":(7,23),"立秋":(8,7),"处暑":(8,23),"白露":(9,7),"秋分":(9,23),
            "寒露":(10,8),"霜降":(10,23),"立冬":(11,7),"小雪":(11,22),"大雪":(12,7),"冬至":(12,22)},
    2027: {"小寒":(1,5),"大寒":(1,20),"立春":(2,4),"雨水":(2,18),"惊蛰":(3,5),"春分":(3,20),
            "清明":(4,5),"谷雨":(4,20),"立夏":(5,5),"小满":(5,21),"芒种":(6,6),"夏至":(6,21),
            "小暑":(7,7),"大暑":(7,23),"立秋":(8,7),"处暑":(8,23),"白露":(9,8),"秋分":(9,23),
            "寒露":(10,8),"霜降":(10,23),"立冬":(11,7),"小雪":(11,22),"大雪":(12,7),"冬至":(12,22)},
    2028: {"小寒":(1,5),"大寒":(1,20),"立春":(2,4),"雨水":(2,19),"惊蛰":(3,5),"春分":(3,20),
            "清明":(4,4),"谷雨":(4,19),"立夏":(5,5),"小满":(5,20),"芒种":(6,5),"夏至":(6,21),
            "小暑":(7,7),"大暑":(7,22),"立秋":(8,7),"处暑":(8,23),"白露":(9,7),"秋分":(9,22),
            "寒露":(10,8),"霜降":(10,23),"立冬":(11,7),"小雪":(11,22),"大雪":(12,6),"冬至":(12,21)},
    2029: {"小寒":(1,5),"大寒":(1,20),"立春":(2,3),"雨水":(2,18),"惊蛰":(3,5),"春分":(3,20),
            "清明":(4,5),"谷雨":(4,20),"立夏":(5,5),"小满":(5,21),"芒种":(6,5),"夏至":(6,21),
            "小暑":(7,7),"大暑":(7,22),"立秋":(8,7),"处暑":(8,23),"白露":(9,7),"秋分":(9,23),
            "寒露":(10,8),"霜降":(10,24),"立冬":(11,7),"小雪":(11,22),"大雪":(12,7),"冬至":(12,21)},
    2030: {"小寒":(1,5),"大寒":(1,20),"立春":(2,4),"雨水":(2,18),"惊蛰":(3,5),"春分":(3,20),
            "清明":(4,5),"谷雨":(4,20),"立夏":(5,5),"小满":(5,21),"芒种":(6,5),"夏至":(6,21),
            "小暑":(7,7),"大暑":(7,23),"立秋":(8,7),"处暑":(8,23),"白露":(9,7),"秋分":(9,23),
            "寒露":(10,8),"霜降":(10,23),"立冬":(11,7),"小雪":(11,22),"大雪":(12,7),"冬至":(12,22)},
}

# ──────────────────────────────────────────────
# Chinese Traditional Festivals (农历节日)
# (lunar_month, lunar_day) -> festival name
# ──────────────────────────────────────────────
CHINESE_LUNAR_FESTIVALS = {
    (1,  1): "春节",
    (1, 15): "元宵节",
    (2,  2): "龙抬头",
    (5,  5): "端午节",
    (7,  7): "七夕节",
    (7, 15): "中元节",
    (8, 15): "中秋节",
    (9,  9): "重阳节",
    (12, 8): "腊八节",
    (12,23): "小年（北方）",
    (12,24): "小年（南方）",
}

# 除夕需要特殊处理：腊月最后一天（可能29或30）
def get_chuxi_date(year: int) -> date | None:
    """获取指定公历年份对应的除夕日期（农历上年腊月最后一天）"""
    try:
        # 除夕 = 农历(year)正月初一的前一天
        chunjie_dt = ZhDate(year, 1, 1).to_datetime()
        chunjie = date(chunjie_dt.year, chunjie_dt.month, chunjie_dt.day)
        return chunjie - timedelta(days=1)
    except Exception:
        return None

# ──────────────────────────────────────────────
# Western / International Festivals
# Fixed-date festivals (公历固定日期)
# ──────────────────────────────────────────────
WESTERN_FIXED = {
    (1,  1): "元旦（新年）",
    (2, 14): "情人节",
    (3,  8): "国际妇女节",
    (4,  1): "愚人节",
    (5,  1): "国际劳动节",
    (6,  1): "国际儿童节",
    (10, 31): "万圣节",
    (11, 11): " Veterans Day / 光棍节",
    (12, 24): "平安夜",
    (12, 25): "圣诞节",
    (12, 31): "新年前夜（跨年）",
}

# Variable-date Western festivals (公历变动日期)
def get_easter(year: int) -> date:
    """计算复活节日期（公历）- 使用 Gauss 算法"""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)

def get_thanksgiving_us(year: int) -> date:
    """美国感恩节：11月第4个星期四"""
    nov1 = date(year, 11, 1)
    # 第一个星期四
    first_thu = nov1 + timedelta(days=(3 - nov1.weekday()) % 7)
    return first_thu + timedelta(weeks=3)

def get_mothers_day(year: int) -> date:
    """母亲节：5月第2个星期日"""
    may1 = date(year, 5, 1)
    first_sun = may1 + timedelta(days=(6 - may1.weekday()) % 7)
    return first_sun + timedelta(weeks=1)

def get_fathers_day(year: int) -> date:
    """父亲节：6月第3个星期日"""
    jun1 = date(year, 6, 1)
    first_sun = jun1 + timedelta(days=(6 - jun1.weekday()) % 7)
    return first_sun + timedelta(weeks=2)

def get_western_variable(year: int) -> dict[date, list[str]]:
    """获取指定年份的变动日期西方节日 {date: [festival_names]}"""
    result = {}
    easter = get_easter(year)
    result.setdefault(easter, []).append("复活节")
    result.setdefault(easter - timedelta(days=2), []).append("耶稣受难日")
    result.setdefault(easter - timedelta(days=46), []).append("忏悔星期二（狂欢节）")

    result.setdefault(get_thanksgiving_us(year), []).append("感恩节（美国）")
    result.setdefault(get_mothers_day(year), []).append("母亲节")
    result.setdefault(get_fathers_day(year), []).append("父亲节")
    return result

# ──────────────────────────────────────────────
# Core query functions
# ──────────────────────────────────────────────

def get_lunar_info(d: date) -> str:
    """获取农历日期字符串"""
    try:
        dt = datetime(d.year, d.month, d.day)
        lunar = ZhDate.from_datetime(dt)
        leap = "闰" if lunar.leap_month == lunar.lunar_month and lunar.leap_month > 0 else ""
        # 天干地支年份
        tian_gan = "甲乙丙丁戊己庚辛壬癸"
        di_zhi = "子丑寅卯辰巳午未申酉戌亥"
        sheng_xiao = "鼠牛虎兔龙蛇马羊猴鸡狗猪"
        gan_idx = (lunar.lunar_year - 4) % 10
        zhi_idx = (lunar.lunar_year - 4) % 12
        ganzhi = tian_gan[gan_idx] + di_zhi[zhi_idx]
        sx = sheng_xiao[zhi_idx]

        lunar_month_names = ["正","二","三","四","五","六","七","八","九","十","冬","腊"]
        lunar_day_names = [
            "初一","初二","初三","初四","初五","初六","初七","初八","初九","初十",
            "十一","十二","十三","十四","十五","十六","十七","十八","十九","二十",
            "廿一","廿二","廿三","廿四","廿五","廿六","廿七","廿八","廿九","三十"
        ]
        m_name = lunar_month_names[min(lunar.lunar_month - 1, 11)]
        d_name = lunar_day_names[min(lunar.lunar_day - 1, 29)]

        return f"{ganzhi}年（{sx}年）农历{leap}{m_name}月{d_name}"
    except Exception:
        return "无法计算农历日期"

def query_date(date_str: str) -> str:
    """查询指定日期的节日和节气信息"""
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return f"❌ 日期格式不正确，请使用 YYYY-MM-DD 格式，例如 2025-05-01"

    lines = []
    lines.append(f"📅 公历：{d.strftime('%Y年%m月%d日')}（周{'一二三四五六日'[d.weekday()]}）")
    lines.append(f"🌕 农历：{get_lunar_info(d)}")
    lines.append("")

    # 中国传统节日
    chinese_festivals = []
    try:
        lunar = ZhDate.from_datetime(datetime(d.year, d.month, d.day))
        key = (lunar.lunar_month, lunar.lunar_day)
        if key in CHINESE_LUNAR_FESTIVALS:
            chinese_festivals.append(CHINESE_LUNAR_FESTIVALS[key])
    except Exception:
        pass

    # 除夕特殊处理
    for y in range(d.year - 1, d.year + 1):
        chuxi = get_chuxi_date(y + 1)  # (y+1)年春节的前一天
        if chuxi and chuxi == d:
            chinese_festivals.append("除夕")
            break

    # 清明节（公历4月4-6日范围内，精确匹配节气表）
    # 清明已包含在节气表中

    # 二十四节气
    solar_term = ""
    if d.year in SOLAR_TERMS_TABLE:
        for term_name, (m, day) in SOLAR_TERMS_TABLE[d.year].items():
            if m == d.month and day == d.day:
                solar_term = term_name
                break

    # 西方固定节日
    western_fixed = WESTERN_FIXED.get((d.month, d.day), "")

    # 西方变动节日
    western_variable = get_western_variable(d.year).get(d, [])

    # 汇总输出
    all_items = []
    if chinese_festivals:
        lines.append(f"🏮 中国传统节日：{'、'.join(chinese_festivals)}")
        all_items.extend(chinese_festivals)
    if solar_term:
        lines.append(f"🌿 节气：{solar_term}")
        all_items.append(solar_term)
    if western_fixed:
        lines.append(f"🌍 国际/西方节日：{western_fixed}")
        all_items.append(western_fixed)
    if western_variable:
        lines.append(f"🌍 国际/西方节日：{'、'.join(western_variable)}")
        all_items.extend(western_variable)

    if not all_items:
        lines.append("ℹ️ 今天没有特别节日或节气")

    return "\n".join(lines)


def query_period(year: int, month: int = None) -> str:
    """查询指定年份或月份的所有节日"""
    if month:
        try:
            start = date(year, month, 1)
            if month == 12:
                end = date(year + 1, 1, 1)
            else:
                end = date(year, month + 1, 1)
        except ValueError:
            return f"❌ 日期无效：{year}-{month}"
        period_str = f"{year}年{month}月"
    else:
        start = date(year, 1, 1)
        end = date(year + 1, 1, 1)
        period_str = f"{year}年"

    # 预计算变动节日
    western_var = get_western_variable(year)
    # 预计算除夕
    chuxi = get_chuxi_date(year + 1)

    results = []
    current = start
    while current < end:
        items = []

        # 中国传统节日（农历）
        try:
            lunar = ZhDate.from_datetime(datetime(current.year, current.month, current.day))
            key = (lunar.lunar_month, lunar.lunar_day)
            if key in CHINESE_LUNAR_FESTIVALS:
                items.append(("🏮", CHINESE_LUNAR_FESTIVALS[key]))
        except Exception:
            pass

        # 除夕
        if chuxi and current == chuxi:
            items.append(("🏮", "除夕"))

        # 节气
        if current.year in SOLAR_TERMS_TABLE:
            for term_name, (m, day) in SOLAR_TERMS_TABLE[current.year].items():
                if m == current.month and day == current.day:
                    items.append(("🌿", term_name))
                    break

        # 西方固定节日
        wf = WESTERN_FIXED.get((current.month, current.day))
        if wf:
            items.append(("🌍", wf))

        # 西方变动节日
        wv = western_var.get(current)
        if wv:
            for name in wv:
                items.append(("🌍", name))

        if items:
            date_label = current.strftime("%m月%d日")
            festival_str = "、".join(f"{emoji} {name}" for emoji, name in items)
            results.append(f"  {date_label}：{festival_str}")

        current += timedelta(days=1)

    if not results:
        return f"ℹ️ {period_str}没有找到节日或节气"

    lines = [f"📋 {period_str} 所有节日/节气一览：", "─" * 50]
    lines.extend(results)
    lines.append("─" * 50)
    lines.append(f"共 {len(results)} 个节日/节气")
    return "\n".join(lines)


def query_solar_terms(year: int) -> str:
    """查询指定年份的全部二十四节气"""
    if year not in SOLAR_TERMS_TABLE:
        return f"❌ 暂不支持 {year} 年的节气查询（仅支持 2020-2030）"

    lines = [f"☀️ {year} 年二十四节气：", "─" * 40]
    terms = SOLAR_TERMS_TABLE[year]
    # 按月份排序输出
    monthly = {}
    for name, (m, d) in terms.items():
        monthly.setdefault(m, []).append((d, name))
    for m in sorted(monthly.keys()):
        for d, name in sorted(monthly[m]):
            lines.append(f"  {m:2d}月{d:2d}日  {name}")
    lines.append("─" * 40)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="节日查询工具 - 中国传统节日 / 二十四节气 / 欧美主流节日",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例：
  python festival_query.py --date 2025-01-29    # 查询某天的节日
  python festival_query.py --year 2025           # 查询全年节日
  python festival_query.py --month 2025-10       # 查询某月节日
  python festival_query.py --terms 2025          # 查看全年二十四节气
        """)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--date", type=str, help="查询指定日期（YYYY-MM-DD）")
    group.add_argument("--year", type=int, help="查询指定年份的所有节日")
    group.add_argument("--month", type=str, help="查询指定月份的所有节日（YYYY-MM）")
    group.add_argument("--terms", type=int, help="查看指定年份的全部二十四节气")

    args = parser.parse_args()

    if args.date:
        print(query_date(args.date))
    elif args.year:
        print(query_period(args.year))
    elif args.month:
        try:
            y, m = map(int, args.month.split("-"))
            print(query_period(y, m))
        except ValueError:
            print("❌ 月份格式不正确，请使用 YYYY-MM 格式，例如 2025-10")
    elif args.terms:
        print(query_solar_terms(args.terms))


if __name__ == "__main__":
    main()
