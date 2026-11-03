#!/usr/bin/env python3
"""
三才五格姓名测算脚本
基于康熙字典笔画数，计算姓名的天格、人格、地格、外格、总格及三才配置。

用法：
  python name_wuge_calc.py --name "张三" --surname-len 1
  python name_wuge_calc.py --input names.json --output result.json

输入JSON格式：
{
  "names": [
    {"name": "张三", "surname_len": 1},
    {"name": "欧阳明华", "surname_len": 2}
  ]
}

说明：
- surname_len: 姓氏字数（1=单姓，2=复姓）
- 笔画按康熙字典为准（references/kangxi_strokes.json）
- 81数理循环：超过81则减去80
"""

import json
import sys
import os
import argparse

# ============================================================
# 加载康熙字典笔画数据
# ============================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STROKE_FILE = os.path.join(SCRIPT_DIR, "..", "references", "kangxi_strokes.json")

_stroke_cache = None

def load_strokes():
    global _stroke_cache
    if _stroke_cache is not None:
        return _stroke_cache
    with open(STROKE_FILE, "r", encoding="utf-8") as f:
        _stroke_cache = json.load(f)
    return _stroke_cache


def get_stroke(char):
    """获取单个汉字的康熙字典笔画数。"""
    strokes = load_strokes()
    s = strokes.get(char)
    if s is not None:
        return s
    # 特殊偏旁规则（姓名学常见）
    SPECIAL = {
        '氵': 4,  # 水
        '扌': 4,  # 手
        '忄': 4,  # 心
        '犭': 4,  # 犬
        '阝': 7,  # 左阝=阜(8)? 实际姓名学中左阝=8,右阝=7; 但康熙字典已处理
        '礻': 5,  # 示
        '衤': 6,  # 衣
        '钅': 8,  # 金
        '饣': 9,  # 食
        '纟': 6,  # 糸
        '月': 6,  # 月=肉部时6画
        '王': 5,  # 王=玉部时5画
        '艹': 6,  # 艸
    }
    return SPECIAL.get(char)


# ============================================================
# 81数理吉凶表
# ============================================================

# 吉凶标记: 吉/半吉/凶
SHULI_81 = {
    1:  ("宇宙起源", "天地开泰，万物开泰，生发无穷，利禄亨通", "大吉"),
    2:  ("一身孤节", "混沌未开，进退保守，志望难达", "凶"),
    3:  ("吉祥", "天地人和，大事大业，繁荣昌隆", "大吉"),
    4:  ("凶变", "待于生发，万事慎重，不具营谋", "凶"),
    5:  ("种竹成林", "五行俱权，循环相生，圆通畅达，福祉无穷", "大吉"),
    6:  ("安稳", "天赋美德，吉祥安泰", "大吉"),
    7:  ("精悍", "精悍严谨，天赋之力，吉星照耀", "吉"),
    8:  ("坚刚", "意志刚健的勤勉发展数", "半吉"),
    9:  ("破舟入海", "蕴涵凶险，或成或败，难以把握", "凶"),
    10: ("零暗", "终结之数，雪暗飘零，偶或有成", "凶"),
    11: ("旱苗逢雨", "万物更新，调顺发达，恢弘泽世，繁荣富贵", "大吉"),
    12: ("掘井无泉", "发展薄弱，虽生不足，难酬志向", "凶"),
    13: ("春日牡丹", "才艺多能，智谋奇略，忍柔当事，鸣奏大功", "大吉"),
    14: ("破兆", "家庭缘薄，孤独遭难，谋事不达", "凶"),
    15: ("福寿", "福寿圆满，富贵荣誉，涵养雅量，德高望重", "大吉"),
    16: ("厚重", "安富尊荣，财官双美，功成名就", "大吉"),
    17: ("刚强", "权威刚强，突破万难，如能容忍，必获成功", "半吉"),
    18: ("铁镜重磨", "权威显达，博得名利，且养柔德", "半吉"),
    19: ("多难", "风云蔽日，辛苦重来，虽有智谋，万事挫折", "凶"),
    20: ("屋下藏金", "非业破运，灾难重重，进退维谷，万事难成", "凶"),
    21: ("明月中天", "光风霁月，万物确立，官运亨通，大搏名利", "大吉"),
    22: ("秋草逢霜", "困难疾弱，虽出豪杰，人生波折", "凶"),
    23: ("壮丽", "旭日东升，壮丽壮观，权威旺盛，功名荣达", "大吉"),
    24: ("掘藏得金", "家门余庆，金钱丰盈，白手成家，财源广进", "大吉"),
    25: ("英俊", "资性英敏，才能奇特，克服傲慢，尚可成功", "半吉"),
    26: ("变怪", "英雄豪杰，波澜重叠，而奏大功", "凶"),
    27: ("增长", "欲望无止，自我强烈，多受毁谤", "凶"),
    28: ("阔水浮萍", "豪杰气概，四海漂泊，终世浮躁", "凶"),
    29: ("智谋", "智谋优秀，财力归集，名闻海内，成就大业", "大吉"),
    30: ("非运", "沉浮不定，凶吉难变，若明若暗，大成大败", "半吉"),
    31: ("春日花开", "智勇得志，博得名利，统领众人，繁荣富贵", "大吉"),
    32: ("宝马金鞍", "侥幸多望，贵人得助，财帛如裕", "大吉"),
    33: ("旭日升天", "鸾凤相会，名闻天下，隆昌至极", "大吉"),
    34: ("破家", "见识短小，辛苦遭逢，灾祸至极", "凶"),
    35: ("高楼望月", "温和平静，智达通畅，文昌技艺，奏功洋洋", "大吉"),
    36: ("波澜重叠", "沉浮万状，侠肝义胆，舍己成仁", "半吉"),
    37: ("猛虎出林", "权威显达，热诚忠信，宜着雅量，终身荣富", "大吉"),
    38: ("磨铁成针", "意志薄弱，刻意经营，才识不凡，技艺有成", "半吉"),
    39: ("富贵荣华", "财帛丰盈，暗藏险象，德泽四方", "半吉"),
    40: ("退安", "智谋胆力，冒险投机，沉浮不定，退保平安", "凶"),
    41: ("有德", "纯阳独秀，德高望重，和顺畅达，博得名利", "大吉"),
    42: ("寒蝉在柳", "博识多能，精通世情，如能专心，尚可成功", "凶"),
    43: ("散财", "散财破产，诸事不遂，虽有智谋，财来财去", "凶"),
    44: ("烦闷", "破家亡身，暗藏惨淡，事不如意", "凶"),
    45: ("顺风", "新生泰和，顺风扬帆，智谋经纬，富贵繁荣", "大吉"),
    46: ("浪里淘金", "载宝沉舟，大难尝尽，大功有成", "凶"),
    47: ("点石成金", "花开之象，万事如意，祯祥吉庆，天赋幸福", "大吉"),
    48: ("古松立鹤", "智谋兼备，德量荣达，威望成师，洋洋大观", "大吉"),
    49: ("转变", "吉临则吉，凶来则凶，转凶为吉，配好三才", "半吉"),
    50: ("小舟入海", "一成一败，吉凶参半，先得庇荫，后遭凄惨", "半吉"),
    51: ("沉浮", "盛衰交加，波澜重叠，如能慎始，必获成功", "半吉"),
    52: ("达眼", "卓识达眼，先见之明，智谋超群，名利双收", "大吉"),
    53: ("曲卷难星", "外祥内患，先富后贫", "凶"),
    54: ("石上栽花", "难得有活，忧闷烦来，辛惨不绝", "凶"),
    55: ("善恶", "善善得恶，恶恶得善，吉到极限，反生凶险", "半吉"),
    56: ("浪里行舟", "四周障碍，万事龃龉，做事难成", "凶"),
    57: ("日照春松", "寒雪青松，夜莺吟春，必遭一过，繁荣白事", "吉"),
    58: ("晚行遇月", "沉浮多端，先苦后甜，宽宏扬名", "半吉"),
    59: ("寒蝉悲风", "意志衰退，缺乏忍耐，苦难不休", "凶"),
    60: ("无谋", "漂泊不定，晦暝暗黑，动摇不安", "凶"),
    61: ("牡丹芙蓉", "花开富贵，名利双收，定享天赋", "大吉"),
    62: ("衰败", "内外不和，志望难达，灾祸频来", "凶"),
    63: ("舟归平海", "富贵荣华，身心安泰，雨露惠泽，万事亨通", "大吉"),
    64: ("非命", "骨肉分离，孤独悲愁，难得心安", "凶"),
    65: ("巨流归海", "天长地久，家运隆昌，福寿绵长，事事成就", "大吉"),
    66: ("岩头步马", "进退维谷，艰难不堪，等待时机", "凶"),
    67: ("通达", "天赋幸运，四通八达，家道繁昌，富贵东来", "大吉"),
    68: ("顺风吹帆", "智虑周密，集众信达，发明能智，拓展昂进", "大吉"),
    69: ("非业", "精神迫滞，灾害交至，遍偿痛苦", "凶"),
    70: ("残菊逢霜", "寂寞无碍，惨淡忧愁，晚景凄凉", "凶"),
    71: ("石上金花", "内心劳苦，贯彻始终，定可昌隆", "半吉"),
    72: ("劳苦", "荣苦相伴，阴云覆月，外表吉祥，内实凶祸", "半吉"),
    73: ("无勇", "盛衰交加，徒有高志，终世平安", "半吉"),
    74: ("残菊经霜", "无能无智，辛苦繁多", "凶"),
    75: ("退守", "发迹甚迟，虽有吉象，无谋难成", "凶"),
    76: ("离散", "倾覆离散，骨肉分离，内外不和", "凶"),
    77: ("半吉半凶", "家庭有悦，半吉半凶，能获援护", "半吉"),
    78: ("晚苦", "祸福参半，先天智能，中年发达，晚景困苦", "凶"),
    79: ("云头望月", "身疲力尽，穷迫不伸，精神不定", "凶"),
    80: ("遁吉", "辛苦不绝，早入隐遁，安心立命，化凶转吉", "凶"),
    81: ("万物回春", "还本归元，吉祥重叠，富贵尊荣", "大吉"),
}


# ============================================================
# 五行映射（尾数）
# ============================================================

def num_to_wuxing(n):
    """数字对应五行（取个位数，0按10算）。"""
    mod = n % 10
    if mod == 0:
        mod = 10
    mapping = {1: "木", 2: "木", 3: "火", 4: "火", 5: "土",
               6: "土", 7: "金", 8: "金", 9: "水", 10: "水"}
    return mapping[mod]


def num_to_yinyang(n):
    """数字对应阴阳（奇阳偶阴）。"""
    mod = n % 10
    if mod == 0:
        mod = 10
    return "阳" if mod % 2 == 1 else "阴"


# ============================================================
# 五格计算
# ============================================================

def calc_wuge(name, surname_len=1):
    """
    计算三才五格。

    参数：
        name: 姓名字符串（如"张三"、"欧阳明华"）
        surname_len: 姓氏字数（1=单姓，2=复姓）

    返回：
        dict 包含五格数值、吉凶、三才等信息
    """
    chars = list(name)
    total_len = len(chars)
    surname_chars = chars[:surname_len]
    given_chars = chars[surname_len:]
    given_len = len(given_chars)

    if given_len == 0:
        return {"error": "姓名中缺少名字部分"}

    # 获取每个字的康熙笔画
    strokes = []
    stroke_details = []
    for c in chars:
        s = get_stroke(c)
        if s is None:
            return {"error": f"无法找到「{c}」的康熙字典笔画数，请确认用字"}
        strokes.append(s)
        stroke_details.append({"字": c, "康熙笔画": s})

    surname_strokes = strokes[:surname_len]
    given_strokes = strokes[surname_len:]

    # 判断姓名类型
    is_fu_xing = surname_len >= 2  # 复姓
    is_dan_ming = given_len == 1   # 单名

    # ---- 天格 ----
    if is_fu_xing:
        tian_ge = sum(surname_strokes)
    else:
        tian_ge = surname_strokes[0] + 1

    # ---- 人格 ----
    if is_fu_xing:
        ren_ge = surname_strokes[-1] + given_strokes[0]
    else:
        ren_ge = surname_strokes[0] + given_strokes[0]

    # ---- 地格 ----
    if is_dan_ming:
        di_ge = given_strokes[0] + 1
    else:
        di_ge = sum(given_strokes)

    # ---- 总格 ----
    zong_ge = sum(strokes)

    # ---- 外格 ----
    if not is_fu_xing and is_dan_ming:
        # 单姓单名：外格固定为2
        wai_ge = 2
    elif not is_fu_xing and not is_dan_ming:
        # 单姓复名
        wai_ge = zong_ge - ren_ge + 1
    elif is_fu_xing and not is_dan_ming:
        # 复姓复名
        wai_ge = zong_ge - ren_ge
    else:
        # 复姓单名
        wai_ge = zong_ge - ren_ge + 1

    # 确保外格至少为2
    if wai_ge < 2:
        wai_ge = 2

    # 81数理循环
    def mod81(n):
        if n <= 0:
            return 1
        while n > 81:
            n -= 80
        return n

    tian_ge_m = mod81(tian_ge)
    ren_ge_m = mod81(ren_ge)
    di_ge_m = mod81(di_ge)
    zong_ge_m = mod81(zong_ge)
    wai_ge_m = mod81(wai_ge)

    # 查81数理
    def get_shuli(n):
        nm = mod81(n)
        info = SHULI_81.get(nm, ("未知", "未知", "未知"))
        return {
            "数理": n,
            "81循环": nm,
            "名称": info[0],
            "含义": info[1],
            "吉凶": info[2],
            "五行": num_to_wuxing(n),
            "阴阳": num_to_yinyang(n),
        }

    wuge = {
        "天格": get_shuli(tian_ge),
        "人格": get_shuli(ren_ge),
        "地格": get_shuli(di_ge),
        "外格": get_shuli(wai_ge),
        "总格": get_shuli(zong_ge),
    }

    # 三才配置
    sancai = [
        num_to_wuxing(tian_ge),
        num_to_wuxing(ren_ge),
        num_to_wuxing(di_ge),
    ]
    sancai_str = "".join(sancai)

    # 三才生克分析
    sancai_analysis = analyze_sancai(sancai)

    # 姓名类型标记
    if is_fu_xing and not is_dan_ming:
        name_type = "复姓复名"
    elif is_fu_xing and is_dan_ming:
        name_type = "复姓单名"
    elif not is_fu_xing and not is_dan_ming:
        name_type = "单姓复名"
    else:
        name_type = "单姓单名"

    # 综合评分 (100分制)
    score = calc_score(wuge, sancai_analysis)
    rating = score_to_rating(score)

    return {
        "姓名": name,
        "姓名类型": name_type,
        "笔画明细": stroke_details,
        "五格": wuge,
        "三才": {
            "配置": sancai_str,
            "天才": sancai[0],
            "人才": sancai[1],
            "地才": sancai[2],
            "分析": sancai_analysis,
        },
        "综合评分": score,
        "综合评级": rating,
    }


# ============================================================
# 三才生克分析
# ============================================================

SHENG = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
KE = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}

def wx_relation(a, b):
    """返回a对b的关系。"""
    if a == b:
        return "比和"
    elif SHENG[a] == b:
        return "相生"
    elif SHENG[b] == a:
        return "被生"
    elif KE[a] == b:
        return "相克"
    elif KE[b] == a:
        return "被克"
    return "未知"


def analyze_sancai(sancai):
    """分析三才（天人地）的生克关系。"""
    tian, ren, di = sancai

    # 天→人关系（成功运）
    tr_rel = wx_relation(tian, ren)
    # 人→地关系（基础运）
    rd_rel = wx_relation(ren, di)
    # 天→地关系（综合）
    td_rel = wx_relation(tian, di)

    # 评分逻辑
    score = 0
    details = []

    # 成功运（天→人）
    if tr_rel in ("比和", "被生"):
        score += 10
        details.append(f"天格({tian})→人格({ren})：{tr_rel}，成功运佳")
    elif tr_rel == "相生":
        score += 8
        details.append(f"天格({tian})→人格({ren})：{tr_rel}，成功运良好")
    elif tr_rel == "被克":
        score += 3
        details.append(f"天格({tian})→人格({ren})：{tr_rel}，成功运受压")
    elif tr_rel == "相克":
        score += 5
        details.append(f"天格({tian})→人格({ren})：{tr_rel}，成功运有阻")

    # 基础运（人→地）
    if rd_rel in ("比和", "相生"):
        score += 10
        details.append(f"人格({ren})→地格({di})：{rd_rel}，基础运稳固")
    elif rd_rel == "被生":
        score += 8
        details.append(f"人格({ren})→地格({di})：{rd_rel}，基础运良好")
    elif rd_rel == "被克":
        score += 3
        details.append(f"人格({ren})→地格({di})：{rd_rel}，基础运不稳")
    elif rd_rel == "相克":
        score += 5
        details.append(f"人格({ren})→地格({di})：{rd_rel}，基础运有碍")

    # 天地配合
    if td_rel in ("比和", "相生", "被生"):
        score += 5
        details.append(f"天格({tian})↔地格({di})：{td_rel}，天地配合良好")
    else:
        score += 2
        details.append(f"天格({tian})↔地格({di})：{td_rel}，天地配合欠佳")

    # 三才全同
    if tian == ren == di:
        score += 5
        details.append(f"三才同属{tian}，气场纯粹")

    # 判断等级
    if score >= 28:
        level = "大吉"
    elif score >= 22:
        level = "吉"
    elif score >= 16:
        level = "半吉"
    elif score >= 10:
        level = "平"
    else:
        level = "凶"

    return {
        "成功运": tr_rel,
        "基础运": rd_rel,
        "天地配": td_rel,
        "评级": level,
        "得分": score,
        "详细": details,
    }


# ============================================================
# 综合评分
# ============================================================

def jixiong_score(jx):
    """吉凶转数值分。"""
    mapping = {"大吉": 100, "吉": 80, "半吉": 60, "平": 50, "凶": 25, "大凶": 0}
    return mapping.get(jx, 50)


def calc_score(wuge, sancai_analysis):
    """加权综合评分，满分100。

    修复说明（v4.1）：
    三才分数直接使用其内部原始得分（0-30）归一化到 0-100，
    而非通过评级标签（大吉/吉/半吉…）再反查分数。
    旧逻辑会导致三才"大吉"=100 与五格全"半吉"=60 严重脱节，
    出现"大吉"却只有66分的反直觉结果。
    """
    # 权重：天格5%、人格35%、地格20%、总格20%、外格5%、三才15%
    tian_s = jixiong_score(wuge["天格"]["吉凶"])
    ren_s = jixiong_score(wuge["人格"]["吉凶"])
    di_s = jixiong_score(wuge["地格"]["吉凶"])
    zong_s = jixiong_score(wuge["总格"]["吉凶"])
    wai_s = jixiong_score(wuge["外格"]["吉凶"])

    # 三才：用原始得分（满分30）归一化到0-100，不再经过标签转换
    sancai_raw = sancai_analysis.get("得分", 0)
    sancai_s = round(sancai_raw / 30.0 * 100, 1)

    score = (tian_s * 0.05 + ren_s * 0.35 + di_s * 0.20 +
             zong_s * 0.20 + wai_s * 0.05 + sancai_s * 0.15)
    return round(score, 1)


def score_to_rating(score):
    """根据综合评分输出总体评级。

    用于姓名综合评分的最终展示，避免“三才大吉”与“总分66分”的认知矛盾。
    三才评级仅反映三才配置本身的优劣，此评级反映姓名整体质量。
    """
    if score >= 90:
        return "大吉 · 上上等"
    elif score >= 80:
        return "吉 · 上等"
    elif score >= 70:
        return "半吉 · 中上"
    elif score >= 60:
        return "平 · 中等"
    elif score >= 50:
        return "偏弱 · 中下"
    else:
        return "凶 · 下等"


# ============================================================
# 多人姓名合盘评估
# ============================================================

def synastry_name_score(results):
    """多人姓名合盘：综合比较各人三才五格的互补和冲突。"""
    if len(results) < 2:
        return None

    details = []
    score = 0
    n = len(results)

    # 1. 各人综合分平均（40分）
    avg_score = sum(r["综合评分"] for r in results) / n
    name_avg_part = round(avg_score * 0.4, 1)
    score += name_avg_part
    details.append(f"各人姓名平均得分 {avg_score:.1f}（权重40%）→ +{name_avg_part}分")

    # 2. 人格五行互补（30分）
    ren_wx_list = [r["五格"]["人格"]["五行"] for r in results]
    wx_set = set(ren_wx_list)
    # 检查相生关系
    sheng_count = 0
    ke_count = 0
    for i in range(len(ren_wx_list)):
        for j in range(i+1, len(ren_wx_list)):
            rel = wx_relation(ren_wx_list[i], ren_wx_list[j])
            if rel in ("相生", "被生"):
                sheng_count += 1
            elif rel in ("相克", "被克"):
                ke_count += 1

    pairs_total = n * (n - 1) // 2
    if pairs_total > 0:
        sheng_ratio = sheng_count / pairs_total
        ke_ratio = ke_count / pairs_total
    else:
        sheng_ratio = 0
        ke_ratio = 0

    wx_part = round((sheng_ratio * 30 - ke_ratio * 10), 1)
    wx_part = max(0, min(30, wx_part))
    score += wx_part
    wx_names = "、".join([f"{r['姓名']}({r['五格']['人格']['五行']})" for r in results])
    details.append(f"人格五行配置 {wx_names}（相生{sheng_count}对/相克{ke_count}对）→ +{wx_part}分")

    # 3. 三才配置平均得分（30分）
    sancai_scores = [r["三才"]["分析"]["得分"] for r in results]
    avg_sancai = sum(sancai_scores) / n
    # 三才最高30分（满分），归一化
    sancai_part = round(avg_sancai / 30 * 30, 1)
    sancai_part = min(30, sancai_part)
    score += sancai_part
    details.append(f"三才配置平均 {avg_sancai:.1f}/30 → +{sancai_part}分")

    score = round(score, 1)
    score = min(100, max(0, score))

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
        "姓名合盘得分": score,
        "评级": rating,
        "详细": details,
    }


# ============================================================
# 主程序
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="三才五格姓名测算")
    parser.add_argument("--name", help="单个姓名")
    parser.add_argument("--surname-len", type=int, default=1, help="姓氏字数（默认1）")
    parser.add_argument("--input", help="批量输入JSON文件")
    parser.add_argument("--output", help="输出JSON文件")
    args = parser.parse_args()

    results = []

    if args.input:
        with open(args.input, "r", encoding="utf-8") as f:
            data = json.load(f)
        for entry in data["names"]:
            r = calc_wuge(entry["name"], entry.get("surname_len", 1))
            results.append(r)
            if "error" in r:
                print(f"❌ {entry['name']}: {r['error']}")
            else:
                print(f"✅ {entry['name']} 综合评分: {r['综合评分']}")
    elif args.name:
        r = calc_wuge(args.name, args.surname_len)
        results.append(r)
        if "error" in r:
            print(f"❌ {args.name}: {r['error']}")
        else:
            print(json.dumps(r, ensure_ascii=False, indent=2))

    # 多人合盘
    valid = [r for r in results if "error" not in r]
    synastry = None
    if len(valid) >= 2:
        synastry = synastry_name_score(valid)
        print(f"\n✅ 姓名合盘: {synastry['姓名合盘得分']}分 {synastry['评级']}")

    if args.output:
        output = {"names": results, "synastry": synastry}
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"\n结果已保存至 {args.output}")


if __name__ == "__main__":
    main()
