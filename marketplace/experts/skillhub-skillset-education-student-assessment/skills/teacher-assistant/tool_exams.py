#!/usr/bin/env python3
"""
智能出题器（交互式）
支持多种题型、难度、分层试卷组合。
python scripts/exam_generator.py
"""

import random
from pathlib import Path

DIFFICULTY_LABEL = {1: "★☆☆☆☆", 2: "★★☆☆☆", 3: "★★★☆☆", 4: "★★★★☆", 5: "★★★★★"}
DIFFICULTY_DESC = {1: "基础", 2: "偏基础", 3: "中等", 4: "较难", 5: "困难"}


def ask(prompt, default=""):
    val = input(f"  {prompt}" + (f" [{default}]" if default else "") + ": ").strip()
    return val if val else default


def ask_int(prompt, default=0):
    val = ask(prompt, str(default))
    try:
        return int(val)
    except Exception:
        return default


def difficulty_menu():
    print("  难度选项：")
    print("    1 - 基础（面向全体学生，70%基础题）")
    print("    2 - 中等（有一定区分度，70%中等难度）")
    print("    3 - 较难（选拔性质，60%中等+40%较难）")
    print("    4 - 分层（A卷基础70%+B卷提高30%）")
    print("    5 - 自定义")
    return ask_int("选择难度（1-5）", 1)


def main():
    print("\n" + "=" * 50)
    print("  新知绘宇·AI 智能出题器")
    print("=" * 50)

    print("\n[基本信息]")
    subject = ask("学科", "数学")
    grade = ask("年级（如：九年级）", "九年级")
    topic = ask("考试范围/单元", "第二单元")
    exam_type = ask("考试类型（随堂/单元/月考/期中/期末）", "单元测试")
    total_score = ask_int("满分", 100)
    duration = ask_int("时长（分钟）", 90)
    textbook = ask("教材版本", "人教版")
    has_ab = ask("是否需要A/B卷（防作弊）", "否")

    diff_mode = difficulty_menu()

    print("\n[题型设置]")
    q_choice = ask_int("选择题数量", 12)
    q_blank = ask_int("填空题数量", 6)
    q_calc = ask_int("计算/解答题数量", 5)
    q_essay = ask_int("作文/主观题数量", 0)

    print("\n[分值设置]")
    score_choice = ask_int("选择题每题分值", 3)
    score_blank = ask_int("填空题每题分值", 4)
    score_calc = ask_int("解答题每题分值", 8)

    # 计算总分
    calc_total = q_choice * score_choice + q_blank * score_blank + q_calc * score_calc
    if q_essay > 0:
        essay_score = total_score - calc_total
        score_essay = ask_int(f"作文/主观题总分（当前剩余：{essay_score}分）", essay_score)
    else:
        score_essay = 0

    # 难度比例
    if diff_mode == 1:
        level_map = lambda q: [(1, 0.7), (2, 0.3)]
    elif diff_mode == 2:
        level_map = lambda q: [(2, 0.5), (3, 0.5)]
    elif diff_mode == 3:
        level_map = lambda q: [(3, 0.4), (4, 0.4), (5, 0.2)]
    elif diff_mode == 4:
        level_map = lambda q: [(1, 0.8), (2, 0.2)]
    else:
        level_map = lambda q: [(3, 1.0)]

    def assign_levels(count, mapper):
        levels = []
        for level, ratio in mapper(count):
            levels.extend([level] * int(count * ratio))
        while len(levels) < count:
            levels.append(3)
        return levels[:count]

    choice_levels = assign_levels(q_choice, level_map)
    blank_levels = assign_levels(q_blank, level_map)
    calc_levels = assign_levels(q_calc, level_map)

    # 生成试卷
    print("\n" + "=" * 50)
    print("  正在生成试卷……")
    print("=" * 50)

    lines = []
    lines.append(f"# 【{exam_type}】{grade}{subject} - {topic}")
    lines.append(f"\n| 项目 | 内容 |")
    lines.append(f"|------|------|")
    lines.append(f"| 学科 | {grade}{subject} |")
    lines.append(f"| 教材 | {textbook} |")
    lines.append(f"| 范围 | {topic} |")
    lines.append(f"| 满分 | {total_score}分 |")
    lines.append(f"| 时长 | {duration}分钟 |")
    lines.append(f"| 难度 | {DIFFICULTY_DESC.get(diff_mode, '中等')} |")
    lines.append("")

    # 选择题
    if q_choice > 0:
        lines.append(f"\n## 一、选择题（共{q_choice}题，每题{score_choice}分，共{q_choice*score_choice}分）")
        for i, lvl in enumerate(choice_levels, 1):
            lines.append(f"{i}. [题干，请教师填写]")
            lines.append(f"   A. [选项A]  B. [选项B]  C. [选项C]  D. [选项D]")
            lines.append(f"   答案：[  ]  难度：{DIFFICULTY_LABEL.get(lvl,'★★★☆☆')}  考点：[填写]")

    # 填空题
    if q_blank > 0:
        lines.append(f"\n## 二、填空题（共{q_blank}题，每题{score_blank}分，共{q_blank*score_blank}分）")
        for i, lvl in enumerate(blank_levels, 1):
            lines.append(f"{i}. [题干]")
            lines.append(f"   答案：[  ]  难度：{DIFFICULTY_LABEL.get(lvl,'★★★☆☆')}  考点：[填写]")

    # 解答题
    if q_calc > 0:
        lines.append(f"\n## 三、解答题（共{q_calc}题，每题{score_calc}分，共{q_calc*score_calc}分）")
        for i, lvl in enumerate(calc_levels, 1):
            lines.append(f"{i}. [解答题题干，需写出详细解答步骤]")
            lines.append(f"   答案：[  ]  难度：{DIFFICULTY_LABEL.get(lvl,'★★★☆☆')}  考点：[填写]")

    # 作文/主观
    if q_essay > 0:
        lines.append(f"\n## 四、{'作文' if subject in ['语文'] else '综合题'}（共{score_essay}分）")
        for i in range(1, q_essay + 1):
            lines.append(f"{i}. [题目要求，请教师填写]")
            lines.append(f"   字数/要求：[填写]  评分标准：[填写]")

    # 参考答案
    lines.append("\n---\n")
    lines.append("## 【参考答案与评分标准】")
    if q_choice > 0:
        lines.append(f"\n一、选择题参考答案（共{q_choice*score_choice}分）")
        ans = []
        for i in range(q_choice):
            ans.append(random.choice(["A", "B", "C", "D"]))
        for i, a in enumerate([ans[i:i+5] for i in range(0, len(ans), 5)], 1):
            lines.append(f"  {i*5-4}-{min(i*5, q_choice)}题：" + "  ".join(a))
    if q_blank > 0:
        lines.append(f"\n二、填空题参考答案（共{q_blank*score_blank}分）")
        for i in range(q_blank):
            lines.append(f"  {i+1}. [参考答案]")
    if q_calc > 0:
        lines.append(f"\n三、解答题参考答案（共{q_calc*score_calc}分）")
        for i in range(q_calc):
            lines.append(f"  {i+1}. [详细解答步骤]")
    if q_essay > 0:
        lines.append(f"\n四、{'作文' if subject in ['语文'] else '综合题'}评分标准（共{score_essay}分）")
        lines.append("  一类文（90%+）：……")
        lines.append("  二类文（75-89%）：……")
        lines.append("  三类文（60-74%）：……")
        lines.append("  四类文（60%以下）：……")

    # A/B卷说明
    if has_ab.lower() not in ["否", "不", "no", "n"]:
        lines.append("\n---\n**注：本卷含A/B两卷，A卷基础题，B卷提高题，可用于分层考试或防作弊。**")

    result = "\n".join(lines)

    # 保存
    safe_topic = topic.replace(" ", "_").replace("/", "_")
    out_file = Path(__file__).parent.parent / "data" / f"{exam_type}_{grade}{subject}_{safe_topic}.md"
    out_file.parent.mkdir(exist_ok=True)
    out_file.write_text(result, encoding="utf-8")

    print(f"\n  试卷已生成：{out_file.name}\n")
    print(result)


if __name__ == "__main__":
    main()
