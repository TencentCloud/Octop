"""
Tarot Card Drawing Script
Uses secrets module for cryptographically secure random card draws
Supports Rider-Waite-Smith 78-card deck, all standard spreads
Supports multiple languages: Chinese (cn) and English (en)
"""
import secrets
import datetime
import json
import sys
import os
import random as _random

# 解决 Windows 终端 emoji 输出问题
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# 添加 references 路径以便导入牌数据库
script_dir = os.path.dirname(os.path.abspath(__file__))
ref_dir = os.path.join(os.path.dirname(script_dir), 'references')
sys.path.insert(0, ref_dir)

from cards import major_arcana, minor_arcana
from spreads import spreads as spreads_cn
try:
    from spreads_en import spreads as spreads_en
except Exception:
    spreads_en = None


def draw_cards(count=1, exclude_indices=None):
    """从78张牌中抽取指定数量，不重复"""
    if exclude_indices is None:
        exclude_indices = set()
    else:
        exclude_indices = set(exclude_indices)

    drawn = []
    available = [i for i in range(78) if i not in exclude_indices]

    for _ in range(count):
        if not available:
            break
        idx = secrets.randbelow(len(available))
        card_idx = available[idx]
        orientation = 'Upright' if secrets.randbelow(2) == 0 else 'Reversed'
        drawn.append((card_idx, orientation))
        available.pop(idx)

    return drawn


def get_card_info(card_idx, orientation):
    """获取单张牌的信息"""
    if card_idx <= 21:
        card = major_arcana[card_idx]
        card_type_cn = "Major Arcana"
        card_type_en = "Major Arcana"
        cn = card["cn"]
        en = card["en"]
        element = "Spirit"
        meaning_upright = card["upright"]
        meaning_reversed = card["reversed"]
    else:
        adjusted = card_idx - 22
        suit_idx = adjusted // 14
        value_idx = adjusted % 14
        suit_keys = list(minor_arcana.keys())
        suit_key = suit_keys[suit_idx]
        suit_data = minor_arcana[suit_key]

        element = suit_data["element"]
        suit_cn = suit_data["name_cn"]
        suit_en_map = {"权杖": "Wands", "圣杯": "Cups", "宝剑": "Swords", "星币": "Pentacles"}
        suit_en = suit_en_map.get(suit_cn, suit_cn)
        card_type_cn = "Minor Arcana · " + suit_cn
        card_type_en = "Minor Arcana · " + suit_en

        if value_idx == 0:
            cn = suit_cn + " Ace"
            en = "Ace of " + suit_key.capitalize()
            meaning_upright = suit_data["ace"]["upright"]
            meaning_reversed = suit_data["ace"]["reversed"]
        elif 1 <= value_idx <= 9:
            card_num = value_idx + 1
            cn = suit_cn + " " + str(card_num)
            en = str(card_num) + " of " + suit_key.capitalize()
            meaning_upright = suit_data["numbered"][card_num]["upright"]
            meaning_reversed = suit_data["numbered"][card_num]["reversed"]
        else:
            court_idx = value_idx - 10
            court_cn = suit_data["court"][court_idx]
            court_en_map = {"Page": "Page", "Knight": "Knight", "Queen": "Queen", "King": "King"}
            court_en = court_en_map.get(court_cn, court_cn)
            cn = suit_cn + " " + court_cn
            en = court_en + " of " + suit_key.capitalize()
            cm = suit_data["court_meanings"][court_cn]
            meaning_upright = cm["upright"]
            meaning_reversed = cm["reversed"]

    meaning = meaning_upright if orientation == "Upright" else meaning_reversed

    return {
        "index": card_idx,
        "type_cn": card_type_cn,
        "type_en": card_type_en,
        "cn": cn,
        "en": en,
        "orientation": orientation,
        "element": element,
        "meaning_upright": meaning_upright,
        "meaning_reversed": meaning_reversed,
        "meaning": meaning
    }


def judge_yes_no(cards_info):
    """判断是否问题的答案"""
    card_idx = cards_info[0]["index"]
    orientation = cards_info[0]["orientation"]

    if card_idx <= 21:
        positive_major = [0, 1, 3, 6, 8, 9, 10, 11, 14, 17, 19, 20, 21]
        negative_major = [5, 7, 12, 13, 15, 16, 18]
        if card_idx in positive_major:
            return "YES"
        elif card_idx in negative_major:
            return "NO"
        else:
            return "YES" if orientation == "Upright" else "NO"
    else:
        adjusted = card_idx - 22
        suit_idx = adjusted // 14
        if suit_idx in [0, 1, 3]:
            return "YES" if orientation == "Upright" else "NO"
        else:
            return "NO" if orientation == "Upright" else "YES"


def judge_whereabouts(cards_info, lang='cn'):
    """判断物品在哪里（找物功能）"""
    orientation = cards_info[0]["orientation"]
    seed = secrets.randbelow(1000000)
    rng = _random.Random(seed)

    hints_cn_upright = [
        "物品可能在经常放东西的地方（桌面、包包、口袋），仔细找找",
        "就在视线容易忽略的地方，被其他东西遮住了",
        "近期有移动，和记忆中位置不一致",
        "物品就在附近，耐心找一下就能找到"
    ]
    hints_cn_reversed = [
        "可能在不常用的位置（抽屉深处、衣柜角落）",
        "可能被借走了或放在别人那里",
        "掉进了某个缝隙或容器里",
        "建议回想最后一次使用它的场景"
    ]
    hints_en_upright = [
        "The item is probably in a place where you often put things - check your desk, bag, or pockets",
        "It's in a spot your eyes easily miss, maybe hidden under something",
        "It was moved recently and isn't where you remember leaving it",
        "The item is nearby - just be patient and you'll find it"
    ]
    hints_en_reversed = [
        "It might be in an unused area - deep in a drawer or corner of a closet",
        "It may have been borrowed or placed with someone else",
        "It could have fallen into a gap or container",
        "Try to recall the last time you actually used it"
    ]

    if lang == 'en':
        hints = hints_en_upright if orientation == "Upright" else hints_en_reversed
    else:
        hints = hints_cn_upright if orientation == "Upright" else hints_cn_reversed

    return rng.choice(hints)


def get_texts(lang='cn'):
    """获取多语言文本"""
    if lang == 'en':
        return {
            "header": "[Draw Result]",
            "spread_label": "Spread:",
            "time_label": "Time:",
            "card_label": "Card",
            "position_label": "Position",
            "meaning_label": "Meaning:",
            "answer_label": "[Answer]:",
            "finding_header": "[Item Clues]",
            "insight_header": "[Insight]",
            "reminder_header": "[Reminder]",
            "tip_label": "Hint:",
            "detail_label": "Detail:",
            "guidance_label": "Guidance:",
            "positions_detail": "Position-by-position breakdown:",
            "drawn_cards": "Cards drawn:",
            "yes": "YES",
            "no": "NO",
            "upright": "Upright",
            "reversed": "Reversed",
        }
    else:
        return {
            "header": "[Draw Result]",
            "spread_label": "Card Spread:",
            "time_label": "Time:",
            "card_label": "Card",
            "position_label": "Position",
            "meaning_label": "Meaning:",
            "answer_label": "[Answer]:",
            "finding_header": "[Item Clues]",
            "insight_header": "[Insight]",
            "reminder_header": "[Reminder]",
            "tip_label": "Hint:",
            "detail_label": "Detail:",
            "guidance_label": "Guidance:",
            "positions_detail": "Position-by-position breakdown:",
            "drawn_cards": "Cards drawn:",
            "yes": "Yes",
            "no": "No",
            "upright": "Upright",
            "reversed": "Reversed",
        }


def format_reading(question_type, spread_name, cards_info, lang='cn'):
    """格式化输出解读"""
    texts = get_texts(lang)

    # 选择对应语言的牌阵
    if lang == 'en' and spreads_en:
        spread_data = spreads_en.get(spread_name) or spreads_cn.get(spread_name)
    else:
        spread_data = spreads_cn.get(spread_name)

    positions = spread_data.get("positions", {})

    # 中文用中文牌阵名，英文用英文牌阵名
    if lang == 'en' and spreads_en:
        spread_display = spread_name
    else:
        spread_display = spread_name

    emoji_map_cn = {
        "Major Arcana": "[*]",
        "Minor Arcana": "[*]",
    }
    emoji_map_en = {
        "Major Arcana": "[*]",
        "Minor Arcana": "[*]",
    }
    emoji_map = emoji_map_en if lang == 'en' else emoji_map_cn

    output = []
    output.append(texts["header"])
    output.append(texts["spread_label"] + " " + spread_display)
    output.append(texts["time_label"] + " " + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    output.append("")

    for i, card in enumerate(cards_info):
        pos_name = positions.get(i + 1, (texts["card_label"] + " " + str(i + 1)))
        emoji = emoji_map.get(card["type_en" if lang == 'en' else "type_cn"], "[*]")
        card_type = card["en"] if lang == 'en' else card["cn"]
        output.append(texts["card_label"] + " " + str(i + 1) + " [" + pos_name + "]")
        output.append("  " + emoji + " " + card["cn"] + " / " + card["en"] + " (" + card["orientation"] + ")")
        output.append("  " + texts["meaning_label"] + " " + card["meaning"])
        output.append("")

    if question_type in ["Yes/No", "Yes/No"]:
        answer = judge_yes_no(cards_info)
        answer_display = texts["yes"] if answer == "YES" else texts["no"]
        emoji_ans = "[+] " + answer_display if lang == 'en' else "[+] " + answer_display
        output.append(texts["answer_label"] + " " + emoji_ans)
        output.append("")
        c0 = cards_info[0]
        output.append(texts["insight_header"].replace("[Insight]", "Interpretation:") + " " + c0["cn"] + " " + c0["orientation"] + " -- " + c0["meaning"])

    elif question_type == "Find":
        where_hint = judge_whereabouts(cards_info, lang)
        output.append(texts["finding_header"])
        output.append(texts["tip_label"] + " " + where_hint)
        if len(cards_info) >= 2:
            c1 = cards_info[1]
            output.append("")
            output.append(texts["detail_label"] + " " + c1["cn"] + " " + c1["orientation"] + " -- " + c1["meaning"])
        if len(cards_info) >= 3:
            c2 = cards_info[2]
            output.append(texts["guidance_label"] + " " + c2["cn"] + " " + c2["orientation"] + " -- " + c2["meaning"])

    elif question_type in ["Advice", "Reminder"]:
        header = texts["reminder_header"] if question_type == "Reminder" else texts["insight_header"]
        output.append(header)
        cards_str = " + ".join([c["cn"] + "(" + c["orientation"] + ")" for c in cards_info])
        output.append(texts["drawn_cards"] + " " + cards_str)
        output.append("")
        output.append(texts["positions_detail"])
        for i, card in enumerate(cards_info):
            pos_name = positions.get(i + 1, texts["card_label"] + " " + str(i + 1))
            output.append("  · " + pos_name + ": " + card["cn"] + " " + card["orientation"] + " -- " + card["meaning"])

    return "\n".join(output)


def main():
    args = sys.argv[1:]

    if len(args) < 2:
        print(json.dumps({"error": "Usage: draw_tarot.py <question_type> <spread_name> [lang]"}))
        sys.exit(1)

    question_type = args[0]
    spread_name = args[1]
    lang = args[2] if len(args) >= 3 else 'cn'

    # 标准化问题类型
    type_map_cn = {"是否": "Yes/No", "找物": "Find", "建议": "Advice", "提醒": "Reminder"}
    type_map_en = {"Yes/No": "Yes/No", "Find": "Find", "Advice": "Advice", "Reminder": "Reminder"}
    # 反向映射
    en_to_cn = {"Yes/No": "是否", "Find": "找物", "Advice": "建议", "Reminder": "提醒"}
    cn_to_en = {"是否": "Yes/No", "找物": "Find", "建议": "Advice", "提醒": "Reminder"}

    # 如果用英文问题类型，自动切换语言
    if question_type in type_map_en:
        lang = 'en'
        question_type_internal = question_type
    elif question_type in type_map_cn:
        question_type_internal = type_map_cn[question_type]
    else:
        question_type_internal = question_type

    # 获取牌阵数据
    spread_data = spreads_cn.get(spread_name)
    if spreads_en:
        spread_data_en = spreads_en.get(spread_name)
        if spread_data_en:
            spread_data = spread_data_en
    if not spread_data:
        available = list(set(list(spreads_cn.keys()) + (list(spreads_en.keys()) if spreads_en else [])))
        print(json.dumps({"error": "Unknown spread. Available: " + str(available)}))
        sys.exit(1)

    card_count = spread_data["cards"]
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    drawn = draw_cards(card_count)
    cards_info = [get_card_info(idx, ori) for idx, ori in drawn]

    reading = format_reading(question_type_internal, spread_name, cards_info, lang)

    result = {
        "timestamp": timestamp,
        "spread": spread_name,
        "question_type": question_type,
        "lang": lang,
        "cards": cards_info
    }

    print("===TAROT_JSON_START===")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("===TAROT_JSON_END===")
    print("")
    print(reading)


if __name__ == "__main__":
    main()
