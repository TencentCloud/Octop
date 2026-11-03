#!/usr/bin/env python3
"""
周易占卜起卦工具
支持：铜钱起卦、数字起卦、时间起卦
输出：JSON
"""

import json
import random
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

try:
    from hexagram_data import HEXAGRAMS, BAGUA
except Exception:
    HEXAGRAMS = {}
    BAGUA = {}

# 先天八卦序号：乾1、兑2、离3、震4、巽5、坎6、艮7、坤8
TRIGRAMS = {
    1: {"name": "乾", "symbol": "☰", "bits": (1, 1, 1)},
    2: {"name": "兑", "symbol": "☱", "bits": (1, 1, 0)},
    3: {"name": "离", "symbol": "☲", "bits": (1, 0, 1)},
    4: {"name": "震", "symbol": "☳", "bits": (1, 0, 0)},
    5: {"name": "巽", "symbol": "☴", "bits": (0, 1, 1)},
    6: {"name": "坎", "symbol": "☵", "bits": (0, 1, 0)},
    7: {"name": "艮", "symbol": "☶", "bits": (0, 0, 1)},
    8: {"name": "坤", "symbol": "☷", "bits": (0, 0, 0)},
}

BITS_TO_TRIGRAM = {value["bits"]: key for key, value in TRIGRAMS.items()}

HEXAGRAM_MAP = {
    (1, 1): (1, "乾为天"), (8, 8): (2, "坤为地"), (6, 4): (3, "水雷屯"), (7, 6): (4, "山水蒙"),
    (6, 1): (5, "水天需"), (1, 6): (6, "天水讼"), (8, 6): (7, "地水师"), (6, 8): (8, "水地比"),
    (5, 1): (9, "风天小畜"), (1, 2): (10, "天泽履"), (8, 1): (11, "地天泰"), (1, 8): (12, "天地否"),
    (1, 3): (13, "天火同人"), (3, 1): (14, "火天大有"), (8, 7): (15, "地山谦"), (4, 8): (16, "雷地豫"),
    (2, 4): (17, "泽雷随"), (7, 5): (18, "山风蛊"), (8, 2): (19, "地泽临"), (5, 8): (20, "风地观"),
    (3, 4): (21, "火雷噬嗑"), (7, 3): (22, "山火贲"), (7, 8): (23, "山地剥"), (8, 4): (24, "地雷复"),
    (1, 4): (25, "天雷无妄"), (7, 1): (26, "山天大畜"), (7, 4): (27, "山雷颐"), (2, 5): (28, "泽风大过"),
    (6, 6): (29, "坎为水"), (3, 3): (30, "离为火"), (2, 7): (31, "泽山咸"), (4, 5): (32, "雷风恒"),
    (1, 7): (33, "天山遁"), (4, 1): (34, "雷天大壮"), (3, 8): (35, "火地晋"), (8, 3): (36, "地火明夷"),
    (5, 3): (37, "风火家人"), (3, 2): (38, "火泽睽"), (6, 7): (39, "水山蹇"), (4, 6): (40, "雷水解"),
    (7, 2): (41, "山泽损"), (5, 4): (42, "风雷益"), (2, 1): (43, "泽天夬"), (1, 5): (44, "天风姤"),
    (2, 8): (45, "泽地萃"), (8, 5): (46, "地风升"), (2, 6): (47, "泽水困"), (6, 5): (48, "水风井"),
    (2, 3): (49, "泽火革"), (3, 5): (50, "火风鼎"), (4, 4): (51, "震为雷"), (7, 7): (52, "艮为山"),
    (5, 7): (53, "风山渐"), (4, 2): (54, "雷泽归妹"), (4, 3): (55, "雷火丰"), (3, 7): (56, "火山旅"),
    (5, 5): (57, "巽为风"), (2, 2): (58, "兑为泽"), (5, 6): (59, "风水涣"), (6, 2): (60, "水泽节"),
    (5, 2): (61, "风泽中孚"), (4, 7): (62, "雷山小过"), (6, 3): (63, "水火既济"), (3, 6): (64, "火水未济"),
}


def line_to_yin_yang(value: int) -> int:
    return 1 if value in (7, 9) else 0


def lines_to_trigram(lines_bottom_to_top):
    bits = tuple(line_to_yin_yang(v) for v in lines_bottom_to_top)
    return BITS_TO_TRIGRAM[bits]


def build_hexagram(upper, lower):
    number, full_name = HEXAGRAM_MAP[(upper, lower)]
    data = HEXAGRAMS.get(number, {})
    return {
        "number": number,
        "name": full_name,
        "short_name": data.get("name"),
        "upper": {
            "number": upper,
            "name": TRIGRAMS[upper]["name"],
            "symbol": TRIGRAMS[upper]["symbol"],
        },
        "lower": {
            "number": lower,
            "name": TRIGRAMS[lower]["name"],
            "symbol": TRIGRAMS[lower]["symbol"],
        },
    }


def interpret_hexagram(hexagram_number, changing_yao=None):
    data = HEXAGRAMS.get(hexagram_number, {})
    changing_yao = changing_yao or []

    result = {
        "summary": data.get("meaning", "可结合卦辞、象辞与现实问题综合判断。"),
    }
    if data.get("guaci"):
        result["guaci"] = data["guaci"]
    if data.get("xiang"):
        result["xiang"] = data["xiang"]
    if data.get("tuan"):
        result["tuan"] = data["tuan"]

    if changing_yao and data.get("yaoci"):
        selected = []
        for idx in changing_yao:
            if 1 <= idx <= 6:
                selected.append({"yao": idx, "text": data["yaoci"][idx - 1]})
        if selected:
            result["changing_yao_text"] = selected
    return result


def coin_toss():
    total = sum(random.choice([2, 3]) for _ in range(3))
    mapping = {
        6: (6, "⚋", True),
        7: (7, "⚊", False),
        8: (8, "⚋", False),
        9: (9, "⚊", True),
    }
    return mapping[total]


def changed_line(value):
    if value == 6:
        return 7
    if value == 9:
        return 8
    return value


def analyze_lines(lines):
    lower = lines_to_trigram(lines[:3])
    upper = lines_to_trigram(lines[3:])
    return upper, lower


def coin_divination():
    lines = []
    results = []
    changing_yao = []

    for idx in range(1, 7):
        value, symbol, changing = coin_toss()
        lines.append(value)
        results.append({
            "yao": idx,
            "value": value,
            "symbol": symbol,
            "changing": changing,
        })
        if changing:
            changing_yao.append(idx)

    upper, lower = analyze_lines(lines)
    changed = [changed_line(v) for v in lines]
    changed_upper, changed_lower = analyze_lines(changed)

    return {
        "method": "coin",
        "method_zh": "铜钱起卦",
        "lines": results,
        "changing_yao": changing_yao,
        "hexagram": build_hexagram(upper, lower),
        "changed_hexagram": build_hexagram(changed_upper, changed_lower) if changing_yao else None,
        "interpretation": interpret_hexagram(HEXAGRAM_MAP[(upper, lower)][0], changing_yao),
    }


def number_divination(num1, num2):
    upper = num1 % 8 or 8
    lower = num2 % 8 or 8
    changing_yao = [((num1 + num2) % 6) or 6]
    hexagram_number = HEXAGRAM_MAP[(upper, lower)][0]

    return {
        "method": "number",
        "method_zh": "数字起卦",
        "numbers": [num1, num2],
        "changing_yao": changing_yao,
        "hexagram": build_hexagram(upper, lower),
        "interpretation": interpret_hexagram(hexagram_number, changing_yao),
    }


def time_divination(now=None):
    now = now or datetime.now()
    upper = (now.year + now.month + now.day) % 8 or 8
    lower = (now.year + now.month + now.day + now.hour) % 8 or 8
    changing_yao = [((now.year + now.month + now.day + now.hour + now.minute) % 6) or 6]
    hexagram_number = HEXAGRAM_MAP[(upper, lower)][0]

    return {
        "method": "time",
        "method_zh": "时间起卦",
        "time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "changing_yao": changing_yao,
        "hexagram": build_hexagram(upper, lower),
        "interpretation": interpret_hexagram(hexagram_number, changing_yao),
    }


def usage():
    print(
        "Usage:\n"
        "  python divination.py coin\n"
        "  python divination.py number <num1> <num2>\n"
        "  python divination.py time\n",
        file=sys.stderr,
    )


def main():
    if len(sys.argv) < 2:
        usage()
        sys.exit(1)

    command = sys.argv[1].lower()

    if command == "coin":
        result = coin_divination()
    elif command == "number":
        if len(sys.argv) != 4:
            usage()
            sys.exit(1)
        try:
            num1 = int(sys.argv[2])
            num2 = int(sys.argv[3])
        except ValueError:
            print("数字起卦参数必须是整数", file=sys.stderr)
            sys.exit(1)
        result = number_divination(num1, num2)
    elif command == "time":
        result = time_divination()
    else:
        usage()
        sys.exit(1)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
