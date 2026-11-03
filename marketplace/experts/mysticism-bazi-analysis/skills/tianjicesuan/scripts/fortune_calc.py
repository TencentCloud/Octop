#!/usr/bin/env python3
"""
天机 · 综合命理测算计算脚本
支持：八字五行、日柱自主计算、袁天罡称骨、紫微排盘概要、西洋星座、三才五格姓名测算、多人合盘评分

用法：
  python fortune_calc.py --input data.json --output result.json

输入JSON格式：
{
  "members": [
    {
      "name": "张三",
      "gender": "男",
      "solar_date": "1990-05-20",
      "birth_time": "08:30",
      "bazi": ["庚午", "辛巳", "乙酉", "庚辰"],
      "lunar": {"month": 4, "day": 26},
      "surname_len": 1
    }
  ]
}

说明：
- bazi 为四柱八字（年柱、月柱、日柱、时柱）
- 日柱可由脚本自动计算（基于儒略日算法），也可由调用者预填
- lunar.month 为农历月份数字（1-12）
- lunar.day 为农历日期数字（1-30）
- birth_time 为真太阳时
- surname_len 为姓氏字数（默认1，复姓填2），用于三才五格计算
"""

import json
import sys
import argparse
import math

# ============================================================
# 基础数据
# ============================================================

TIAN_GAN = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
DI_ZHI = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
SHENG_XIAO = ["鼠", "牛", "虎", "兔", "龙", "蛇", "马", "羊", "猴", "鸡", "狗", "猪"]

WU_XING_GAN = {"甲": "木", "乙": "木", "丙": "火", "丁": "火", "戊": "土", "己": "土", "庚": "金", "辛": "金", "壬": "水", "癸": "水"}
WU_XING_ZHI = {"子": "水", "丑": "土", "寅": "木", "卯": "木", "辰": "土", "巳": "火", "午": "火", "未": "土", "申": "金", "酉": "金", "戌": "土", "亥": "水"}
YIN_YANG_GAN = {"甲": "阳", "乙": "阴", "丙": "阳", "丁": "阴", "戊": "阳", "己": "阴", "庚": "阳", "辛": "阴", "壬": "阳", "癸": "阴"}

NA_YIN = {
    "甲子": "海中金", "乙丑": "海中金", "丙寅": "炉中火", "丁卯": "炉中火",
    "戊辰": "大林木", "己巳": "大林木", "庚午": "路旁土", "辛未": "路旁土",
    "壬申": "剑锋金", "癸酉": "剑锋金", "甲戌": "山头火", "乙亥": "山头火",
    "丙子": "涧下水", "丁丑": "涧下水", "戊寅": "城头土", "己卯": "城头土",
    "庚辰": "白蜡金", "辛巳": "白蜡金", "壬午": "杨柳木", "癸未": "杨柳木",
    "甲申": "泉中水", "乙酉": "泉中水", "丙戌": "屋上土", "丁亥": "屋上土",
    "戊子": "霹雳火", "己丑": "霹雳火", "庚寅": "松柏木", "辛卯": "松柏木",
    "壬辰": "长流水", "癸巳": "长流水", "甲午": "沙中金", "乙未": "沙中金",
    "丙申": "山下火", "丁酉": "山下火", "戊戌": "平地木", "己亥": "平地木",
    "庚子": "壁上土", "辛丑": "壁上土", "壬寅": "金箔金", "癸卯": "金箔金",
    "甲辰": "覆灯火", "乙巳": "覆灯火", "丙午": "天河水", "丁未": "天河水",
    "戊申": "大驿土", "己酉": "大驿土", "庚戌": "钗钏金", "辛亥": "钗钏金",
    "壬子": "桑柘木", "癸丑": "桑柘木", "甲寅": "大溪水", "乙卯": "大溪水",
    "丙辰": "沙中土", "丁巳": "沙中土", "戊午": "天上火", "己未": "天上火",
    "庚申": "石榴木", "辛酉": "石榴木", "壬戌": "大海水", "癸亥": "大海水",
}

CANG_GAN = {
    "子": ["癸"], "丑": ["己", "癸", "辛"], "寅": ["甲", "丙", "戊"],
    "卯": ["乙"], "辰": ["戊", "乙", "癸"], "巳": ["丙", "庚", "戊"],
    "午": ["丁", "己"], "未": ["己", "丁", "乙"], "申": ["庚", "壬", "戊"],
    "酉": ["辛"], "戌": ["戊", "辛", "丁"], "亥": ["壬", "甲"],
}

SEASON_MAP = {
    "寅": "春", "卯": "春", "辰": "春",
    "巳": "夏", "午": "夏", "未": "夏",
    "申": "秋", "酉": "秋", "戌": "秋",
    "亥": "冬", "子": "冬", "丑": "冬",
}

LUNAR_DAY_NAME = [
    "", "初一", "初二", "初三", "初四", "初五", "初六", "初七", "初八", "初九", "初十",
    "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十",
    "廿一", "廿二", "廿三", "廿四", "廿五", "廿六", "廿七", "廿八", "廿九", "三十"
]

LUNAR_MONTH_NAME = [
    "", "正", "二", "三", "四", "五", "六", "七", "八", "九", "十", "冬", "腊"
]


# ============================================================
# 儒略日与日期转换
# ============================================================

def gregorian_to_jdn(year, month, day):
    """格里历日期转儒略日编号 (Julian Day Number)。"""
    if month <= 2:
        year -= 1
        month += 12
    A = year // 100
    B = 2 - A + A // 4
    return int(365.25 * (year + 4716)) + int(30.6001 * (month + 1)) + day + B - 1524


def gregorian_to_jd(year, month, day, hour=0, minute=0):
    """公历日期时间转儒略日（浮点数）。"""
    y, m = year, month
    if m <= 2:
        y -= 1
        m += 12
    A = y // 100
    B = 2 - A + A // 4
    jd = int(365.25 * (y + 4716)) + int(30.6001 * (m + 1)) + day + B - 1524.5
    jd += (hour + minute / 60.0) / 24.0
    return jd


# ============================================================
# 太阳黄经与节气计算
# ============================================================

def _solar_longitude(jde):
    """
    计算给定儒略日(力学时)的太阳视黄经（简化VSOP87）。
    参考：Jean Meeus《天文算法》第25章
    精度约0.01度，节气时刻误差 < 10分钟。
    """
    T = (jde - 2451545.0) / 36525.0
    L0 = (280.46646 + 36000.76983 * T + 0.0003032 * T * T) % 360
    M = (357.52911 + 35999.05029 * T - 0.0001537 * T * T) % 360
    M_rad = math.radians(M)
    C = (1.914602 - 0.004817 * T - 0.000014 * T * T) * math.sin(M_rad) \
      + (0.019993 - 0.000101 * T) * math.sin(2 * M_rad) \
      + 0.000289 * math.sin(3 * M_rad)
    sun_lon = L0 + C
    omega = 125.04 - 1934.136 * T
    sun_lon = sun_lon - 0.00569 - 0.00478 * math.sin(math.radians(omega))
    return sun_lon % 360


# 节气对应太阳黄经度数 → 大致公历(月, 日)
_JIEQI_APPROX = {
    285: (1, 6), 300: (1, 20), 315: (2, 4), 330: (2, 19),
    345: (3, 6), 0: (3, 21), 15: (4, 5), 30: (4, 20),
    45: (5, 6), 60: (5, 21), 75: (6, 6), 90: (6, 21),
    105: (7, 7), 120: (7, 23), 135: (8, 7), 150: (8, 23),
    165: (9, 8), 180: (9, 23), 195: (10, 8), 210: (10, 23),
    225: (11, 7), 240: (11, 22), 255: (12, 7), 270: (12, 22),
}


def _find_solar_term_jde(year, target_lon):
    """
    精确计算指定年份太阳黄经到达target_lon的时刻(JDE)。
    使用牛顿迭代法，初始估算基于节气的近似公历日期。
    """
    m, d = _JIEQI_APPROX.get(target_lon, (3, 21))
    jde_est = gregorian_to_jd(year, m, d, 12, 0)
    for _ in range(50):
        lon = _solar_longitude(jde_est)
        diff = target_lon - lon
        if diff > 180:
            diff -= 360
        elif diff < -180:
            diff += 360
        if abs(diff) < 0.00001:
            break
        jde_est += diff / 360.0 * 365.25
    return jde_est


def _jde_to_beijing(jde):
    """JDE(≈UT) 转北京时间 (year, month, day, hour, minute)。"""
    jd_bj = jde + 8.0 / 24.0
    z = jd_bj + 0.5
    Z = int(z)
    F = z - Z
    if Z < 2299161:
        A = Z
    else:
        alpha = int((Z - 1867216.25) / 36524.25)
        A = Z + 1 + alpha - alpha // 4
    B = A + 1524
    C = int((B - 122.1) / 365.25)
    D = int(365.25 * C)
    E = int((B - D) / 30.6001)
    day = B - D - int(30.6001 * E)
    month = E - 1 if E < 14 else E - 13
    year = C - 4716 if month > 2 else C - 4715
    hf = F * 24.0
    hour = int(hf)
    minute = int((hf - hour) * 60)
    return year, month, day, hour, minute


# 月建节气表：(节气名, 太阳黄经, 月支index in DI_ZHI)
_MONTH_JIEQI = [
    ("小寒", 285, 1),   # 丑月
    ("立春", 315, 2),   # 寅月
    ("惊蛰", 345, 3),   # 卯月
    ("清明", 15, 4),    # 辰月
    ("立夏", 45, 5),    # 巳月
    ("芒种", 75, 6),    # 午月
    ("小暑", 105, 7),   # 未月
    ("立秋", 135, 8),   # 申月
    ("白露", 165, 9),   # 酉月
    ("寒露", 195, 10),  # 戌月
    ("立冬", 225, 11),  # 亥月
    ("大雪", 255, 0),   # 子月
]


def _get_month_jieqi_dates(year):
    """
    获取覆盖指定公历年份的所有月建节气时刻（北京时间）。
    返回按时间排序的列表: [(solar_year, month, day, hour, minute, zhi_index, jieqi_name), ...]
    包含前一年12月的大雪、当年1月的小寒，以及当年所有节气直到下一年小寒。
    """
    results = []
    # 上一年大雪
    jde = _find_solar_term_jde(year - 1, 255)
    dt = _jde_to_beijing(jde)
    results.append((*dt, 0, "大雪"))
    # 当年小寒
    jde = _find_solar_term_jde(year, 285)
    dt = _jde_to_beijing(jde)
    results.append((*dt, 1, "小寒"))
    # 当年立春到大雪
    for name, lon, zhi_idx in _MONTH_JIEQI:
        if name in ("小寒",):
            continue
        jde = _find_solar_term_jde(year, lon)
        dt = _jde_to_beijing(jde)
        results.append((*dt, zhi_idx, name))
    # 下一年小寒
    jde = _find_solar_term_jde(year + 1, 285)
    dt = _jde_to_beijing(jde)
    results.append((*dt, 1, "小寒"))
    results.sort(key=lambda x: (x[0], x[1], x[2], x[3], x[4]))
    return results


# ============================================================
# 年柱计算
# ============================================================

def calc_year_pillar(year, month, day, hour=0, minute=0):
    """
    根据公历日期时间计算年柱天干地支。
    以立春为年的分界：立春前属上一年，立春后（含）属当年。
    hour/minute 为北京时间。
    """
    # 计算当年立春时刻（北京时间）
    jde = _find_solar_term_jde(year, 315)
    lc_y, lc_m, lc_d, lc_h, lc_mi = _jde_to_beijing(jde)
    
    # 比较出生时间与立春时间
    birth_val = (month, day, hour, minute)
    lichun_val = (lc_m, lc_d, lc_h, lc_mi)
    
    if birth_val < lichun_val:
        gz_year = year - 1  # 立春前，属上一年
    else:
        gz_year = year
    
    gan_idx = (gz_year - 4) % 10
    zhi_idx = (gz_year - 4) % 12
    return TIAN_GAN[gan_idx] + DI_ZHI[zhi_idx]


# ============================================================
# 月柱计算
# ============================================================

# 五虎遁口诀：年干 → 寅月天干
_WUHU_DUN = {
    "甲": "丙", "己": "丙",  # 甲己之年丙作首
    "乙": "戊", "庚": "戊",  # 乙庚之年戊为头
    "丙": "庚", "辛": "庚",  # 丙辛之岁寻庚上
    "丁": "壬", "壬": "壬",  # 丁壬壬寅顺水流
    "戊": "甲", "癸": "甲",  # 戊癸之年甲寅头
}


def calc_month_pillar(year, month, day, hour=0, minute=0):
    """
    根据公历日期时间计算月柱天干地支。
    月支由节气决定（每月以节气为界，非公历月初）。
    月干由五虎遁推算。
    hour/minute 为北京时间。
    """
    # 获取覆盖该年的节气日期表
    jieqi_dates = _get_month_jieqi_dates(year)
    
    # 将出生时间与节气时间逐一比较，找到所属月建
    birth_val = (year, month, day, hour, minute)
    
    zhi_idx = None
    for i in range(len(jieqi_dates) - 1):
        cur = jieqi_dates[i]
        nxt = jieqi_dates[i + 1]
        cur_val = (cur[0], cur[1], cur[2], cur[3], cur[4])
        nxt_val = (nxt[0], nxt[1], nxt[2], nxt[3], nxt[4])
        if cur_val <= birth_val < nxt_val:
            zhi_idx = cur[5]
            break
    
    if zhi_idx is None:
        # 回退：如果在所有区间之外，使用最后一个区间
        zhi_idx = jieqi_dates[-1][5]
    
    month_zhi = DI_ZHI[zhi_idx]
    
    # 确定年干（需要考虑立春分界）
    year_gz = calc_year_pillar(year, month, day, hour, minute)
    year_gan = year_gz[0]
    
    # 五虎遁推月干：从年干查寅月起始天干，然后顺推
    yin_gan = _WUHU_DUN[year_gan]
    yin_gan_idx = TIAN_GAN.index(yin_gan)
    # 寅=2，月支zhi_idx相对于寅的偏移
    offset = (zhi_idx - 2) % 12
    month_gan_idx = (yin_gan_idx + offset) % 10
    month_gan = TIAN_GAN[month_gan_idx]
    
    return month_gan + month_zhi


# ============================================================
# 时柱计算
# ============================================================

# 五鼠遁口诀：日干 → 子时天干
_WUSHU_DUN = {
    "甲": "甲", "己": "甲",  # 甲己还加甲
    "乙": "丙", "庚": "丙",  # 乙庚丙作初
    "丙": "戊", "辛": "戊",  # 丙辛从戊起
    "丁": "庚", "壬": "庚",  # 丁壬庚子居
    "戊": "壬", "癸": "壬",  # 戊癸壬子头
}


def calc_hour_pillar(day_gan, hour_float):
    """
    根据日干和出生时间（小时数）计算时柱。
    hour_float: 0-24 的浮点数。
    """
    shichen_idx = get_shichen(hour_float)
    hour_zhi = DI_ZHI[shichen_idx]
    
    # 五鼠遁推时干
    zi_gan = _WUSHU_DUN[day_gan]
    zi_gan_idx = TIAN_GAN.index(zi_gan)
    hour_gan_idx = (zi_gan_idx + shichen_idx) % 10
    hour_gan = TIAN_GAN[hour_gan_idx]
    
    return hour_gan + hour_zhi


# ============================================================
# 日柱计算（儒略日算法）
# ============================================================

def calc_day_pillar(year, month, day):
    """
    根据公历日期计算日柱天干地支。

    原理：干支纪日是连续的60周期循环。利用儒略日编号 (JDN) 与已知
    基准日的差值推算任意日期的干支。
    基准：2000-01-01 = JDN 2451545 = 戊午日
    """
    jdn = gregorian_to_jdn(year, month, day)
    base_jdn = 2451545  # 2000-01-01
    base_gan = 4        # 戊 = TIAN_GAN[4]
    base_zhi = 6        # 午 = DI_ZHI[6]
    diff = jdn - base_jdn
    gan_idx = (base_gan + diff) % 10
    zhi_idx = (base_zhi + diff) % 12
    return TIAN_GAN[gan_idx] + DI_ZHI[zhi_idx]


def calc_four_pillars(year, month, day, hour=0, minute=0):
    """
    一次性计算完整四柱八字。
    参数为公历日期+北京时间。
    返回 [年柱, 月柱, 日柱, 时柱] 列表。
    
    子时处理说明：
    采用“晚子时不换日柱”派（23:00-00:00 仍用当日日柱）。
    这是目前主流命理网站和大多数命理实践采用的方式。
    """
    hour_float = hour + minute / 60.0
    
    year_pillar = calc_year_pillar(year, month, day, hour, minute)
    month_pillar = calc_month_pillar(year, month, day, hour, minute)
    day_pillar = calc_day_pillar(year, month, day)
    hour_pillar = calc_hour_pillar(day_pillar[0], hour_float)
    
    return [year_pillar, month_pillar, day_pillar, hour_pillar]


# ============================================================
# 十神计算
# ============================================================

def get_shishen(day_gan, other_gan):
    day_wx = WU_XING_GAN[day_gan]
    other_wx = WU_XING_GAN[other_gan]
    same_yy = (YIN_YANG_GAN[day_gan] == YIN_YANG_GAN[other_gan])
    sheng = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
    ke = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}
    if day_wx == other_wx:
        return "比肩" if same_yy else "劫财"
    elif sheng[day_wx] == other_wx:
        return "食神" if same_yy else "伤官"
    elif sheng[other_wx] == day_wx:
        return "偏印" if same_yy else "正印"
    elif ke[day_wx] == other_wx:
        return "偏财" if same_yy else "正财"
    elif ke[other_wx] == day_wx:
        return "七杀" if same_yy else "正官"
    return "未知"


def get_shichen(hour_float):
    h = hour_float
    if h >= 23 or h < 1: return 0
    elif h < 3: return 1
    elif h < 5: return 2
    elif h < 7: return 3
    elif h < 9: return 4
    elif h < 11: return 5
    elif h < 13: return 6
    elif h < 15: return 7
    elif h < 17: return 8
    elif h < 19: return 9
    elif h < 21: return 10
    else: return 11


# ============================================================
# 五行分析
# ============================================================

def analyze_wuxing(bazi):
    counts = {"金": 0, "木": 0, "水": 0, "火": 0, "土": 0}
    for pillar in bazi:
        counts[WU_XING_GAN[pillar[0]]] += 1
        counts[WU_XING_ZHI[pillar[1]]] += 1
    return counts


def analyze_wuxing_with_canggan(bazi):
    counts = {"金": 0, "木": 0, "水": 0, "火": 0, "土": 0}
    for pillar in bazi:
        counts[WU_XING_GAN[pillar[0]]] += 1
        for cg in CANG_GAN.get(pillar[1], []):
            counts[WU_XING_GAN[cg]] += 0.5
    return counts


# ============================================================
# 袁天罡称骨
# ============================================================

YEAR_WEIGHT = {
    "甲子": 12, "丙子": 16, "戊子": 15, "庚子": 7, "壬子": 5,
    "乙丑": 9, "丁丑": 8, "己丑": 7, "辛丑": 7, "癸丑": 7,
    "丙寅": 6, "戊寅": 8, "庚寅": 9, "壬寅": 9, "甲寅": 12,
    "丁卯": 7, "己卯": 19, "辛卯": 12, "癸卯": 12, "乙卯": 8,
    "戊辰": 12, "庚辰": 12, "壬辰": 10, "甲辰": 8, "丙辰": 8,
    "己巳": 5, "辛巳": 6, "癸巳": 7, "乙巳": 7, "丁巳": 6,
    "庚午": 9, "壬午": 8, "甲午": 15, "丙午": 13, "戊午": 19,
    "辛未": 8, "癸未": 7, "乙未": 6, "丁未": 5, "己未": 6,
    "壬申": 7, "甲申": 5, "丙申": 5, "戊申": 14, "庚申": 8,
    "癸酉": 8, "乙酉": 15, "丁酉": 14, "己酉": 5, "辛酉": 16,
    "甲戌": 15, "丙戌": 6, "戊戌": 14, "庚戌": 9, "壬戌": 10,
    "乙亥": 9, "丁亥": 16, "己亥": 9, "辛亥": 17, "癸亥": 6,
}

MONTH_WEIGHT = {1: 6, 2: 7, 3: 18, 4: 9, 5: 5, 6: 16, 7: 9, 8: 15, 9: 18, 10: 8, 11: 9, 12: 5}

DAY_WEIGHT = {
    1: 5, 2: 10, 3: 8, 4: 15, 5: 16, 6: 15, 7: 8, 8: 16, 9: 8, 10: 16,
    11: 9, 12: 17, 13: 8, 14: 17, 15: 10, 16: 8, 17: 9, 18: 18, 19: 5, 20: 15,
    21: 10, 22: 9, 23: 8, 24: 9, 25: 15, 26: 18, 27: 7, 28: 8, 29: 16, 30: 6
}

HOUR_WEIGHT = {0: 16, 1: 6, 2: 7, 3: 10, 4: 9, 5: 16, 6: 10, 7: 8, 8: 8, 9: 9, 10: 6, 11: 6}

CHENGGU_POEM = {
    21: ("短命非业谓大凶，平生灾难事重重，凶祸频临限逆境，终世困苦事不成。", "命极薄"),
    22: ("身寒骨冷苦伶仃，此命推来行乞人，劳劳碌碌无度日，中年打拱过平生。", "命薄"),
    23: ("此命推来骨轻轻，求谋做事事难成，妻儿兄弟应难许，别处他乡作散人。", "命薄"),
    24: ("此命推来福禄无，门庭困苦总难荣，六亲骨肉皆无靠，流到他乡作老人。", "命薄"),
    25: ("此命推来祖业微，门庭营度似希奇，六亲骨肉如水炭，一世勤劳自把持。", "命轻"),
    26: ("平生一路苦中求，独自营谋事不休，离祖出门宜早计，晚来衣禄自无忧。", "命轻"),
    27: ("一生做事少商量，难靠祖宗作主张，独马单枪空作去，早年晚岁总无长。", "命轻"),
    28: ("一生作事似飘蓬，祖宗产业在梦中，若不过房并改姓，也当移徒二三通。", "命轻"),
    29: ("初年运限未曾亨，纵有功名在后成，须过四旬方可上，移居改姓使为良。", "中等偏下"),
    30: ("劳劳碌碌苦中求，东走西奔何日休，若能终身勤与俭，老来稍可免忧愁。", "中等偏下"),
    31: ("忙忙碌碌苦中求，何日云开见日头，难得祖基家可立，中年衣食渐无忧。", "中等"),
    32: ("初年运错事难谋，渐有财源如水流，到的中年衣食旺，那时名利一齐来。", "中等"),
    33: ("早年做事事难成，百计徒劳枉费心，半世自如流水去，后来运到始得金。", "中等"),
    34: ("此命福气果如何，僧道门中衣禄多，离祖出家方得妙，终朝拜佛念弥陀。", "中等"),
    35: ("生平福量不周全，祖业根基觉少传，营事生涯宜守旧，时来衣食胜从前。", "中等"),
    36: ("不须劳碌过平生，独自成家福不轻，早有福星常照命，任君行去百般成。", "中等偏上"),
    37: ("此命般般事不成，弟兄少力自孤成，虽然祖业须微有，来的明时去的暗。", "中等"),
    38: ("一生骨肉最清高，早入学门姓名标，待看年将三十六，蓝衣脱去换红袍。", "中等偏上"),
    39: ("此命终身运不通，劳劳做事尽皆空，苦心竭力成家计，到得那时在梦中。", "中等偏下"),
    40: ("平生衣禄是绵长，件件心中自主张，前面风霜都受过，从来必定享安泰。", "中上"),
    41: ("此命推来事不同，为人能干异凡庸，中年还有逍遥福，不比前年云未通。", "中上"),
    42: ("得宽怀处且宽怀，何用双眉总不开，若使中年命运济，那时名利一齐来。", "中上"),
    43: ("为人心性最聪明，做事轩昂近贵人，衣禄一生天数定，不须劳碌是丰亨。", "中上"),
    44: ("来事由天莫苦求，须知福禄胜前途，当年财帛难如意，晚景欣然便不忧。", "中上"),
    45: ("福中取贵格求真，明敏才华志自伸，福禄寿全家道吉，桂兰毓秀晚荣臻。", "上等"),
    46: ("东西南北尽皆通，出姓移名更觉隆，衣禄无亏天数定，中年晚景一般同。", "上等"),
    47: ("此命推来旺末年，妻荣子贵自怡然，平生原有滔滔福，可有财源如水流。", "上等"),
    48: ("幼年运道未曾享，苦是蹉跎再不兴，兄弟六亲皆无靠，一身事业晚年成。", "中上"),
    49: ("此命推来福不轻，自立自成显门庭，从来富贵人亲近，使婢差奴过一生。", "上等"),
    50: ("为利为名终日劳，中年福禄也多遭，老来是有财星照，不比前番目下高。", "上等"),
    51: ("一世荣华事事通，不须劳碌自亨通，兄弟叔侄皆如意，家业成时福禄宏。", "上等"),
    52: ("一世亨通事事能，不须劳思自然能，宗施欣然心皆好，家业丰亨自称心。", "上等"),
    53: ("此格推来气象真，兴家发达在其中，一生福禄安排定，却是人间一富翁。", "上等"),
    54: ("此命推来厚且清，诗书满腹看功成，丰衣足食自然稳，正是人间有福人。", "上等"),
    55: ("走马扬鞭争名利，少年做事废筹论，一朝福禄源源至，富贵荣华显六亲。", "上上"),
    56: ("此格推来礼仪通，一生福禄用无穷，甜酸苦辣皆尝过，财源滚滚稳且丰。", "上上"),
    57: ("福禄盈盈万事全，一生荣耀显双亲，名扬威震人钦敬，处世逍遥似遇春。", "上上"),
    58: ("平生福禄自然来，名利兼全福禄偕，雁塔提名为贵客，紫袍金带走金鞋。", "上上"),
    59: ("细推此格妙且清，必定才高礼仪通，甲第之中应有分，扬鞭走马显威荣。", "极佳"),
    60: ("一朝金榜快题名，显祖荣宗立大功，衣食定然原欲足，田园财帛更丰盈。", "极佳"),
    61: ("不做朝中金榜客，定为世上一财翁，聪明天赋经书熟，名显高克自是荣。", "极佳"),
    62: ("此名生来福不穷，读书必定显亲荣，紫衣金带为卿相，富贵荣华皆可同。", "极佳"),
    63: ("命主为官福禄长，得来富贵定非常，名题金塔传金榜，定中高科天下扬。", "极佳"),
    64: ("此格权威不可当，紫袍金带坐高堂，荣华富贵谁能及，积玉堆金满储仓。", "极佳"),
    65: ("细推此命福不轻，安国安邦极品人，文绣雕梁政富贵，威声照耀四方闻。", "极佳"),
    66: ("此格人间一福人，堆金积玉满堂春，从来富贵由天定，正笏垂绅谒圣君。", "极佳"),
    67: ("此名生来福自宏，田园家业最高隆，平生衣禄丰盈足，一世荣华万事通。", "极佳"),
    68: ("富贵由天莫苦求，万金家计不须谋，十年不比前番事，祖业根基水上舟。", "极佳"),
    69: ("君是人间衣禄星，一生福贵众人钦，纵然福禄由天定，安享荣华过一生。", "极佳"),
    70: ("此命推来福不轻，不须愁虑苦劳心，一生天定衣与禄，富贵荣华过一生。", "极佳"),
    71: ("此命生来大不同，公侯卿相在其中，一生自有逍遥福，富贵荣华极品隆。", "极佳"),
    72: ("此格世界罕有生，十代积善产此人，天上紫微来照命，统治万民乐太平。", "极佳"),
}


def weight_str(w):
    if w >= 10:
        return f"{w // 10}两{w % 10}钱"
    return f"{w}钱"


def calc_chenggu(year_gz, lunar_month, lunar_day, hour):
    hour_idx = get_shichen(hour)
    year_w = YEAR_WEIGHT.get(year_gz, 0)
    month_w = MONTH_WEIGHT.get(lunar_month, 0)
    day_w = DAY_WEIGHT.get(lunar_day, 0)
    hour_w = HOUR_WEIGHT.get(hour_idx, 0)
    total = year_w + month_w + day_w + hour_w
    poem, level = CHENGGU_POEM.get(total, ("此骨重不在常规歌诀范围内", ""))
    return {
        "年": weight_str(year_w), "月": weight_str(month_w),
        "日": weight_str(day_w), "时": weight_str(hour_w),
        "总重": weight_str(total), "总重数": total,
        "歌诀": poem, "等级": level,
    }


# ============================================================
# 星座
# ============================================================

ZODIAC_INFO = {
    "白羊座": {"元素": "火", "守护星": "火星", "模式": "开创", "特质": "勇敢、冲动、直率、热情、好胜"},
    "金牛座": {"元素": "土", "守护星": "金星", "模式": "固定", "特质": "稳重、务实、固执、享受、忠诚"},
    "双子座": {"元素": "风", "守护星": "水星", "模式": "变动", "特质": "聪明、善变、沟通、好奇、灵活"},
    "巨蟹座": {"元素": "水", "守护星": "月亮", "模式": "开创", "特质": "温柔、顾家、敏感、保护、多情"},
    "狮子座": {"元素": "火", "守护星": "太阳", "模式": "固定", "特质": "自信、慷慨、热情、领导、骄傲"},
    "处女座": {"元素": "土", "守护星": "水星", "模式": "变动", "特质": "细致、完美、分析、服务、挑剔"},
    "天秤座": {"元素": "风", "守护星": "金星", "模式": "开创", "特质": "和谐、优雅、犹豫、公正、社交"},
    "天蝎座": {"元素": "水", "守护星": "冥王星", "模式": "固定", "特质": "深邃、神秘、执着、洞察、占有"},
    "射手座": {"元素": "火", "守护星": "木星", "模式": "变动", "特质": "自由、乐观、冒险、直言、哲思"},
    "摩羯座": {"元素": "土", "守护星": "土星", "模式": "开创", "特质": "严谨、上进、坚韧、务实、保守"},
    "水瓶座": {"元素": "风", "守护星": "天王星", "模式": "固定", "特质": "独立、创新、博爱、叛逆、理性"},
    "双鱼座": {"元素": "水", "守护星": "海王星", "模式": "变动", "特质": "浪漫、直觉、同情、梦幻、牺牲"},
}

ZODIAC_ORDER = ["白羊座", "金牛座", "双子座", "巨蟹座", "狮子座", "处女座",
                "天秤座", "天蝎座", "射手座", "摩羯座", "水瓶座", "双鱼座"]


def get_zodiac(month, day):
    boundaries = [
        (1, 20), (2, 19), (3, 21), (4, 20), (5, 21), (6, 22),
        (7, 23), (8, 23), (9, 23), (10, 24), (11, 23), (12, 22)
    ]
    signs = ["摩羯座", "水瓶座", "双鱼座", "白羊座", "金牛座", "双子座",
             "巨蟹座", "狮子座", "处女座", "天秤座", "天蝎座", "射手座", "摩羯座"]
    for i, (m, d) in enumerate(boundaries):
        if month == m and day < d:
            return signs[i], ZODIAC_INFO.get(signs[i], {})
        elif month == m and day >= d:
            return signs[i + 1], ZODIAC_INFO.get(signs[i + 1], {})
    return "未知", {}


def zodiac_angle(z1, z2):
    idx1 = ZODIAC_ORDER.index(z1)
    idx2 = ZODIAC_ORDER.index(z2)
    diff = abs(idx2 - idx1)
    if diff > 6:
        diff = 12 - diff
    return diff * 30


# ============================================================
# 紫微斗数排盘概要
# ============================================================

def calc_ziwei(year_gan, year_zhi, lunar_month, lunar_day, hour, gender):
    month_gong = (DI_ZHI.index("寅") + lunar_month - 1) % 12
    hour_idx = get_shichen(hour)
    ming_gong_idx = (month_gong - hour_idx) % 12
    shen_gong_idx = (month_gong + hour_idx) % 12
    ming_gong = DI_ZHI[ming_gong_idx]
    shen_gong = DI_ZHI[shen_gong_idx]

    twelve_gong_names = ["命宫", "兄弟宫", "夫妻宫", "子女宫", "财帛宫", "疾厄宫",
                         "迁移宫", "交友宫", "官禄宫", "田宅宫", "福德宫", "父母宫"]
    gong_map = {}
    for i, gn in enumerate(twelve_gong_names):
        gong_zhi_idx = (ming_gong_idx - i) % 12
        gong_map[gn] = DI_ZHI[gong_zhi_idx]

    year_gan_idx = TIAN_GAN.index(year_gan)
    yin_start = {0: 2, 1: 4, 2: 6, 3: 8, 4: 0, 5: 2, 6: 4, 7: 6, 8: 8, 9: 0}
    start = yin_start[year_gan_idx]
    ming_gan_idx = (start + (ming_gong_idx - 2) % 12) % 10
    ming_gan = TIAN_GAN[ming_gan_idx]

    wu_xing_ju_map = {
        ("甲", "子"): ("金四局", 4), ("乙", "丑"): ("金四局", 4),
        ("丙", "寅"): ("火六局", 6), ("丁", "卯"): ("火六局", 6),
        ("戊", "辰"): ("木三局", 3), ("己", "巳"): ("木三局", 3),
        ("庚", "午"): ("土五局", 5), ("辛", "未"): ("土五局", 5),
        ("壬", "申"): ("水二局", 2), ("癸", "酉"): ("水二局", 2),
        ("甲", "戌"): ("火六局", 6), ("乙", "亥"): ("火六局", 6),
        ("丙", "子"): ("水二局", 2), ("丁", "丑"): ("水二局", 2),
        ("戊", "寅"): ("金四局", 4), ("己", "卯"): ("金四局", 4),
        ("庚", "辰"): ("火六局", 6), ("辛", "巳"): ("火六局", 6),
        ("壬", "午"): ("木三局", 3), ("癸", "未"): ("木三局", 3),
        ("甲", "申"): ("水二局", 2), ("乙", "酉"): ("水二局", 2),
        ("丙", "戌"): ("土五局", 5), ("丁", "亥"): ("土五局", 5),
        ("戊", "子"): ("火六局", 6), ("己", "丑"): ("火六局", 6),
        ("庚", "寅"): ("木三局", 3), ("辛", "卯"): ("木三局", 3),
        ("壬", "辰"): ("金四局", 4), ("癸", "巳"): ("金四局", 4),
        ("甲", "午"): ("金四局", 4), ("乙", "未"): ("金四局", 4),
        ("丙", "申"): ("火六局", 6), ("丁", "酉"): ("火六局", 6),
        ("戊", "戌"): ("木三局", 3), ("己", "亥"): ("木三局", 3),
        ("庚", "子"): ("土五局", 5), ("辛", "丑"): ("土五局", 5),
        ("壬", "寅"): ("水二局", 2), ("癸", "卯"): ("水二局", 2),
        ("甲", "辰"): ("火六局", 6), ("乙", "巳"): ("火六局", 6),
        ("丙", "午"): ("水二局", 2), ("丁", "未"): ("水二局", 2),
        ("戊", "申"): ("金四局", 4), ("己", "酉"): ("金四局", 4),
        ("庚", "戌"): ("火六局", 6), ("辛", "亥"): ("火六局", 6),
        ("壬", "子"): ("木三局", 3), ("癸", "丑"): ("木三局", 3),
        ("甲", "寅"): ("水二局", 2), ("乙", "卯"): ("水二局", 2),
        ("丙", "辰"): ("土五局", 5), ("丁", "巳"): ("土五局", 5),
        ("戊", "午"): ("火六局", 6), ("己", "未"): ("火六局", 6),
        ("庚", "申"): ("木三局", 3), ("辛", "酉"): ("木三局", 3),
        ("壬", "戌"): ("金四局", 4), ("癸", "亥"): ("金四局", 4),
    }

    ju_info = wu_xing_ju_map.get((ming_gan, ming_gong), ("未知", 0))
    wu_xing_ju = ju_info[0]

    ming_zhu_map = {
        "子": "贪狼", "丑": "巨门", "寅": "禄存", "卯": "文曲",
        "辰": "廉贞", "巳": "武曲", "午": "破军", "未": "武曲",
        "申": "廉贞", "酉": "文曲", "戌": "禄存", "亥": "巨门"
    }
    shen_zhu_map = {
        "子": "铃星", "丑": "天相", "寅": "天梁", "卯": "天同",
        "辰": "文昌", "巳": "天机", "午": "火星", "未": "天相",
        "申": "天梁", "酉": "天同", "戌": "文昌", "亥": "天机"
    }
    ming_zhu = ming_zhu_map.get(ming_gong, "未知")
    shen_zhu = shen_zhu_map.get(year_zhi, "未知")

    year_yy = YIN_YANG_GAN[year_gan]
    if gender == "男":
        da_yun = "顺行" if year_yy == "阳" else "逆行"
    else:
        da_yun = "逆行" if year_yy == "阳" else "顺行"

    shen_in_gong = ""
    for gn, gz in gong_map.items():
        if gz == shen_gong:
            shen_in_gong = gn
            break

    return {
        "命宫": f"{ming_gan}{ming_gong}宫",
        "身宫": f"{shen_gong}宫（落在{shen_in_gong}）" if shen_in_gong else f"{shen_gong}宫",
        "五行局": wu_xing_ju,
        "命主": ming_zhu,
        "身主": shen_zhu,
        "大运方向": da_yun,
        "十二宫": gong_map,
        "阴阳": f"年干{year_gan}为{year_yy}",
    }


# ============================================================
# 个人完整测算
# ============================================================

def analyze_person(member):
    name = member["name"]
    gender = member["gender"]
    solar_date = member["solar_date"]
    birth_time = member["birth_time"]
    bazi = list(member["bazi"]) if member.get("bazi") else [None, None, None, None]
    lunar = member["lunar"]
    lunar_month = lunar["month"]
    lunar_day = lunar["day"]

    # 解析时间
    parts = birth_time.split(":")
    hour_float = int(parts[0]) + int(parts[1]) / 60.0
    s_hour = int(parts[0])
    s_minute = int(parts[1])

    # 解析日期
    solar_parts = solar_date.split("-")
    s_year, s_month, s_day = int(solar_parts[0]), int(solar_parts[1]), int(solar_parts[2])

    # 自动计算完整四柱（基于天文算法）
    computed = calc_four_pillars(s_year, s_month, s_day, s_hour, s_minute)

    # 与输入的bazi进行校验，自动修正差异
    pillar_names = ["年柱", "月柱", "日柱", "时柱"]
    for i in range(4):
        if bazi[i] is None:
            bazi[i] = computed[i]
        elif bazi[i] != computed[i]:
            print(f"⚠️ {name}: 输入{pillar_names[i]}「{bazi[i]}」与计算结果「{computed[i]}」不一致，已自动修正")
            bazi[i] = computed[i]

    # 基本信息
    year_gz = bazi[0]
    day_gz = bazi[2]
    day_gan = day_gz[0]
    sx_idx = DI_ZHI.index(year_gz[1])
    shengxiao = SHENG_XIAO[sx_idx]

    # 五行
    wx = analyze_wuxing(bazi)
    wx_canggan = analyze_wuxing_with_canggan(bazi)

    # 纳音
    nayins = [NA_YIN.get(p, "未知") for p in bazi]

    # 十神
    shishen = []
    for i, p in enumerate(bazi):
        if i == 2:
            shishen.append("日主")
        else:
            shishen.append(get_shishen(day_gan, p[0]))

    # 藏干
    canggan_info = []
    for p in bazi:
        zhi = p[1]
        cgs = CANG_GAN.get(zhi, [])
        canggan_info.append({"地支": zhi, "藏干": [{"干": cg, "五行": WU_XING_GAN[cg]} for cg in cgs]})

    # 五行缺失
    missing = [k for k, v in wx.items() if v == 0]
    max_wx = max(wx, key=wx.get)
    min_wx = min(wx, key=wx.get)

    # 出生季节
    month_zhi = bazi[1][1]
    season = SEASON_MAP.get(month_zhi, "")

    # 称骨
    chenggu = calc_chenggu(year_gz, lunar_month, lunar_day, hour_float)

    # 星座
    solar_parts = solar_date.split("-")
    solar_month = int(solar_parts[1])
    solar_day = int(solar_parts[2])
    zodiac, zodiac_info = get_zodiac(solar_month, solar_day)

    # 紫微
    ziwei = calc_ziwei(year_gz[0], year_gz[1], lunar_month, lunar_day, hour_float, gender)

    # 三才五格姓名测算
    wuge_result = None
    surname_len = member.get("surname_len", 1)
    try:
        from name_wuge_calc import calc_wuge
        wuge_result = calc_wuge(name, surname_len)
        if "error" in wuge_result:
            print(f"⚠️ {name}: 三才五格计算失败 - {wuge_result['error']}")
            wuge_result = None
    except ImportError:
        # name_wuge_calc 不可用时跳过
        pass
    except Exception as e:
        print(f"⚠️ {name}: 三才五格计算异常 - {e}")

    return {
        "name": name,
        "gender": gender,
        "solar_date": solar_date,
        "birth_time": birth_time,
        "bazi": bazi,
        "lunar_month": lunar_month,
        "lunar_day": lunar_day,
        "year_gz": year_gz,
        "day_gan": day_gan,
        "shengxiao": shengxiao,
        "year_zhi": year_gz[1],
        "wx": wx,
        "wx_canggan": wx_canggan,
        "nayins": nayins,
        "shishen": shishen,
        "canggan": canggan_info,
        "missing_wx": missing,
        "max_wx": max_wx,
        "min_wx": min_wx,
        "season": season,
        "chenggu": chenggu,
        "zodiac": zodiac,
        "zodiac_info": zodiac_info,
        "ziwei": ziwei,
        "wuge": wuge_result,
    }


# ============================================================
# 合盘分析
# ============================================================

def analyze_synastry(members_results):
    if len(members_results) < 2:
        return {"note": "至少需要2人才能进行合盘分析"}

    # 五行合计
    group_wx = {"金": 0, "木": 0, "水": 0, "火": 0, "土": 0}
    for m in members_results:
        for w in group_wx:
            group_wx[w] += m["wx"][w]

    balance = max(group_wx.values()) - min(group_wx.values())
    missing_group = [k for k, v in group_wx.items() if v == 0]

    # 评分
    score = 0
    details = []

    # 1. 五行平衡 (25分)
    if balance <= 3:
        s = 25
    elif balance <= 5:
        s = 20
    elif balance <= 8:
        s = 14
    else:
        s = 8
    score += s
    details.append(f"五行平衡度（差异{balance}）+{s}分")
    if not missing_group:
        score += 5
        details.append("五行俱全加分 +5分")

    # 2. 生肖关系 (20分)
    liu_he = [("子", "丑"), ("寅", "亥"), ("卯", "戌"), ("辰", "酉"), ("巳", "申"), ("午", "未")]
    san_he = [("申", "子", "辰"), ("寅", "午", "戌"), ("巳", "酉", "丑"), ("亥", "卯", "未")]
    xiang_chong = [("子", "午"), ("丑", "未"), ("寅", "申"), ("卯", "酉"), ("辰", "戌"), ("巳", "亥")]
    xiang_hai = [("子", "未"), ("丑", "午"), ("寅", "巳"), ("卯", "辰"), ("申", "亥"), ("酉", "戌")]

    sx_score = 10
    sx_details = []
    pairs = []
    for i in range(len(members_results)):
        for j in range(i + 1, len(members_results)):
            pairs.append((members_results[i], members_results[j]))

    for m1, m2 in pairs:
        z1, z2 = m1["year_zhi"], m2["year_zhi"]
        for a, b in liu_he:
            if (z1 == a and z2 == b) or (z1 == b and z2 == a):
                sx_score += 7
                sx_details.append(f"{m1['name']}({z1})与{m2['name']}({z2})六合 +7分")
        for group in san_he:
            if z1 in group and z2 in group:
                sx_score += 5
                sx_details.append(f"{m1['name']}({z1})与{m2['name']}({z2})三合 +5分")
        for a, b in xiang_chong:
            if (z1 == a and z2 == b) or (z1 == b and z2 == a):
                sx_score -= 5
                sx_details.append(f"{m1['name']}({z1})与{m2['name']}({z2})六冲 -5分")
        for a, b in xiang_hai:
            if (z1 == a and z2 == b) or (z1 == b and z2 == a):
                sx_score -= 3
                sx_details.append(f"{m1['name']}({z1})与{m2['name']}({z2})相害 -3分")

    score += min(max(sx_score, 0), 20)
    details.extend(sx_details)

    # 3. 星座 (15分)
    zs = 0
    for m1, m2 in pairs:
        angle = zodiac_angle(m1["zodiac"], m2["zodiac"])
        if angle in [0, 60, 120]:
            zs += 5
            details.append(f"{m1['name']}与{m2['name']}星座和谐({angle}°) +5分")
        elif angle == 30:
            zs += 4
            details.append(f"{m1['name']}与{m2['name']}星座较和谐({angle}°) +4分")
        elif angle == 180:
            zs += 3
            details.append(f"{m1['name']}与{m2['name']}星座对冲互补({angle}°) +3分")
        elif angle == 90:
            zs += 2
            details.append(f"{m1['name']}与{m2['name']}星座有摩擦({angle}°) +2分")
        elif angle == 150:
            zs += 1
            details.append(f"{m1['name']}与{m2['name']}星座需调整({angle}°) +1分")
    score += min(zs, 15)

    # 4. 日主关系 (20分)
    tian_gan_he = {"甲己": "化土", "乙庚": "化金", "丙辛": "化水", "丁壬": "化木", "戊癸": "化火"}
    sheng_map = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
    ke_map = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}
    rg = 0
    for m1, m2 in pairs:
        g1, g2 = m1["day_gan"], m2["day_gan"]
        wx1, wx2 = WU_XING_GAN[g1], WU_XING_GAN[g2]
        for pair, result in tian_gan_he.items():
            if (g1 == pair[0] and g2 == pair[1]) or (g1 == pair[1] and g2 == pair[0]):
                rg += 7
                details.append(f"{m1['name']}与{m2['name']}天干合({pair}{result}) +7分")
        if wx1 == wx2:
            rg += 5
            details.append(f"{m1['name']}与{m2['name']}日主比和 +5分")
        elif sheng_map[wx1] == wx2 or sheng_map[wx2] == wx1:
            rg += 5
            details.append(f"{m1['name']}与{m2['name']}日主相生 +5分")
        elif ke_map[wx1] == wx2 or ke_map[wx2] == wx1:
            rg += 1
            details.append(f"{m1['name']}与{m2['name']}日主相克 +1分")
    score += min(rg, 20)

    # 5. 称骨 (20分)
    avg_weight = sum(m["chenggu"]["总重数"] for m in members_results) / len(members_results)
    if avg_weight >= 45:
        cs = 20
    elif avg_weight >= 40:
        cs = 16
    elif avg_weight >= 35:
        cs = 12
    elif avg_weight >= 30:
        cs = 9
    else:
        cs = 5
    score += cs
    details.append(f"团体平均骨重{avg_weight / 10:.1f}两 +{cs}分")

    # 评级
    if score >= 85:
        rating = "★★★★★ 极佳组合"
    elif score >= 70:
        rating = "★★★★☆ 良好组合"
    elif score >= 55:
        rating = "★★★☆☆ 中等组合"
    elif score >= 40:
        rating = "★★☆☆☆ 有待改善"
    else:
        rating = "★☆☆☆☆ 需多加注意"

    return {
        "group_wx": group_wx,
        "balance": balance,
        "missing_group": missing_group,
        "score": score,
        "rating": rating,
        "details": details,
        "avg_weight": avg_weight,
    }


# ============================================================
# 主程序
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="综合命理测算")
    parser.add_argument("--input", required=True, help="输入JSON文件路径")
    parser.add_argument("--output", required=True, help="输出JSON文件路径")
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)

    results = []
    for member in data["members"]:
        result = analyze_person(member)
        results.append(result)
        print(f"✅ {member['name']} 测算完成")

    synastry = None
    if len(results) >= 2:
        synastry = analyze_synastry(results)
        print(f"✅ 合盘分析完成：{synastry['score']}分 {synastry['rating']}")

    output = {
        "members": results,
        "synastry": synastry,
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n结果已保存至 {args.output}")


if __name__ == "__main__":
    main()
