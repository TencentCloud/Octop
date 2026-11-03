#!/usr/bin/env python3
"""
每日宜忌查询系统
基于传统黄历的彭祖百忌、神煞方位、宜忌事项
"""

import sys
from datetime import datetime, timedelta

# 天干
TIANGAN = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]

# 地支
DIZHI = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]

# 生肖
SHENGXIAO = ["鼠", "牛", "虎", "兔", "龙", "蛇", "马", "羊", "猴", "鸡", "狗", "猪"]

# 彭祖百忌
PENGZU = {
    "甲": "甲不开仓，乙不栽植",
    "乙": "乙不栽植，丁不剃头",
    "丙": "丙不修灶，戊不受田",
    "丁": "丁不剃头，己不破券",
    "戊": "戊不受田，庚不经络",
    "己": "己不破券，辛不合酱",
    "庚": "庚不经络，壬不汲水",
    "辛": "辛不合酱，癸不词讼",
    "壬": "壬不汲水，甲不开仓",
    "癸": "癸不词讼，乙不栽植",
    "子": "子不问卜，丑不冠带",
    "丑": "丑不冠带，寅不祭祀",
    "寅": "寅不祭祀，卯不穿井",
    "卯": "卯不穿井，辰不哭泣",
    "辰": "辰不哭泣，巳不远行",
    "巳": "巳不远行，午不苫盖",
    "午": "午不苫盖，未不服药",
    "未": "未不服药，申不安床",
    "申": "申不安床，酉不会客",
    "酉": "酉不会客，戌不吃犬",
    "戌": "戌不吃犬，亥不嫁娶",
    "亥": "亥不嫁娶，子不问卜",
}

# 财神方位
CAISHEN = {
    0: "正东", 1: "正东", 2: "东南", 3: "东南", 4: "正南", 
    5: "西南", 6: "正西", 7: "西北", 8: "正北", 9: "东北",
}

# 福神方位
FUSHEN = {
    0: "东南", 1: "正东", 2: "东南", 3: "正南", 4: "西南",
    5: "正西", 6: "西北", 7: "正北", 8: "东北", 9: "西南",
}

# 喜神方位
XISHEN = {
    0: "东北", 1: "正北", 2: "正北", 3: "东北", 4: "正东",
    5: "东南", 6: "正南", 7: "西南", 8: "正西", 9: "西北",
}

# 阳贵神方位（白天贵人）
YANGGUI = {
    0: "正北", 1: "东北", 2: "正东", 3: "东南", 4: "正南",
    5: "西南", 6: "正西", 7: "西北", 8: "正北", 9: "东北",
}

# 凶煞冲属相
CHONG = {
    "子": "午", "丑": "未", "寅": "申", "卯": "酉",
    "辰": "戌", "巳": "亥", "午": "子", "未": "丑",
    "申": "寅", "酉": "卯", "戌": "辰", "亥": "巳",
}

# 宜事项
YI_ITEMS = [
    ["祭祀、祈福、嫁娶、订盟", "动土、起基、定磉", "纳采、问名", "入学、会友"],
    ["订盟、纳采、嫁娶", "出行、移徙、入宅", "开市、交易、立券", "挂匾、拆卸"],
    ["祈福、嫁娶、纳采", "动土、破土、安葬", "安床、解除", "冠笄、整手足甲"],
    ["嫁娶、纳采、订盟", "出行、移徙", "竖柱、上梁", "纳畜、牧养"],
]

# 忌事项
JI_ITEMS = [
    ["安葬、动针线", "词讼、造庙", "开市、动土", "安床、破土"],
    ["出货财、动针线", "祈福、嫁娶", "安葬、动土", "入宅、移徙"],
    ["安葬、动针线", "词讼、造谣", "开市、动土", "安床、破土"],
    ["安葬、动土", "祈福、嫁娶", "动针线、词讼", "出货财"],
]


def get_ganzhi(date: datetime) -> tuple:
    """获取指定日期的干支"""
    # 基准：2024-01-01 是甲子日
    base = datetime(2024, 1, 1)
    days_diff = (date - base).days
    
    gan_idx = days_diff % 10
    zhi_idx = days_diff % 12
    
    return TIANGAN[gan_idx], DIZHI[zhi_idx]


def get_pengzu(gan: str, zhi: str) -> list:
    """获取彭祖百忌"""
    result = []
    if gan in PENGZU:
        result.append(PENGZU[gan])
    if zhi in PENGZU:
        result.append(PENGZU[zhi])
    return result


def get_shensha(gan: str, zhi: str) -> dict:
    """获取神煞方位"""
    gan_idx = TIANGAN.index(gan)
    zhi_idx = DIZHI.index(zhi)
    
    return {
        "caishen": CAISHEN[gan_idx],
        "fushen": FUSHEN[zhi_idx],
        "xishen": XISHEN[gan_idx],
        "yanggui": YANGGUI[gan_idx],
    }


def get_yiji(zhi: str) -> tuple:
    """获取宜忌事项"""
    zhi_idx = DIZHI.index(zhi)
    
    yi = YI_ITEMS[zhi_idx % len(YI_ITEMS)]
    ji = JI_ITEMS[zhi_idx % len(JI_ITEMS)]
    
    return yi, ji


def get_chong(zhi: str) -> str:
    """获取冲煞"""
    chong_zhi = CHONG.get(zhi, "")
    chong_shengxiao = SHENGXIAO[DIZHI.index(chong_zhi)] if chong_zhi else ""
    return f"冲{chong_shengxiao}（{chong_zhi}）"


def format_output(date: datetime, gan: str, zhi: str, lunar: str = "") -> str:
    """格式化输出"""
    gan_idx = TIANGAN.index(gan)
    zhi_idx = DIZHI.index(zhi)
    
    pengzu = get_pengzu(gan, zhi)
    shensha = get_shensha(gan, zhi)
    yi, ji = get_yiji(zhi)
    chong = get_chong(zhi)
    
    # 地支对应农历月份（简化）
    month_lunar = ["正月", "二月", "三月", "四月", "五月", "六月",
                   "七月", "八月", "九月", "十月", "冬月", "腊月"]
    
    output = f"""📅 每日宜忌

【日期】{date.strftime('%Y年%m月%d日')} 农历{month_lunar[zhi_idx]}{zhi}日

【干支】{gan}{zhi}

【彭祖百忌】
"""
    for p in pengzu:
        output += f"• {p}\n"
    
    output += f"""
【神煞方位】
• 财神：{shensha['caishen']}  |  福神：{shensha['fushen']}
• 喜神：{shensha['xishen']}  |  阳贵：{shensha['yanggui']}

【宜】
"""
    for y in yi:
        output += f"✅ {y}\n"
    
    output += """
【忌】
"""
    for j in ji:
        output += f"❌ {j}\n"
    
    output += f"""
【冲煞】
• {chong}

---
※ 黄历仅供参考 ※"""
    
    return output


def cmd_today():
    """查询今日"""
    date = datetime.now()
    gan, zhi = get_ganzhi(date)
    print(format_output(date, gan, zhi))


def cmd_tomorrow():
    """查询明日"""
    date = datetime.now() + timedelta(days=1)
    gan, zhi = get_ganzhi(date)
    print(format_output(date, gan, zhi))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "tomorrow":
        cmd_tomorrow()
    else:
        cmd_today()
