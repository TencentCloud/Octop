#!/usr/bin/env python3
"""
学情分析器（交互式）
输入学生成绩数据，输出统计分析和教学建议。
python scripts/grade_analyzer.py
"""

import statistics
from pathlib import Path


def ask(prompt, default=""):
    val = input(f"  {prompt}" + (f" [{default}]" if default else "") + ": ").strip()
    return val if val else default


def parse_scores(text):
    """从文本中解析分数列表"""
    scores = []
    for part in text.replace("，", ",").replace("、", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            scores.append(float(part))
        except ValueError:
            # 可能是"姓名:分数"格式
            if ":" in part or "=" in part or "：" in part:
                try:
                    num = part.split(":")[-1].split("=")[-1].split("：")[-1].strip()
                    scores.append(float(num))
                except Exception:
                    pass
    return scores


def percentile_rank(scores, value):
    """计算某分数的百分位"""
    lower = sum(1 for s in scores if s < value)
    return round(lower / len(scores) * 100, 1)


def grade_distribution(scores, thresholds=(60, 72, 85, 100)):
    """分数段分布"""
    bands = [
        (0, thresholds[0] - 1, "不及格（<60）"),
        (thresholds[0], thresholds[1] - 1, "及格（60-71）"),
        (thresholds[1], thresholds[2] - 1, "中等（72-84）"),
        (thresholds[2], thresholds[3], "良好（85-100）"),
    ]
    dist = []
    for lo, hi, label in bands:
        count = sum(1 for s in scores if lo <= s <= hi)
        pct = round(count / len(scores) * 100, 1)
        dist.append((label, count, pct))
    return dist


def generate_report(class_name, exam_name, scores):
    if not scores:
        return "未检测到有效分数，请重新输入。"

    scores_sorted = sorted(scores, reverse=True)
    n = len(scores)

    avg = round(statistics.mean(scores), 1)
    median = round(statistics.median(scores), 1)
    std = round(statistics.stdev(scores), 1) if n > 1 else 0
    max_score = max(scores)
    min_score = min(scores)
    pass_threshold = 60
    passed = sum(1 for s in scores if s >= pass_threshold)
    pass_rate = round(passed / n * 100, 1)
    excellent_threshold = 85
    excellent = sum(1 for s in scores if s >= excellent_threshold)
    excellent_rate = round(excellent / n * 100, 1)

    # 进步/退步前5名（假设有上次数据）
    top5 = scores_sorted[:5]

    # 分数段分布
    dist = grade_distribution(scores)

    # 班级画像
    if avg >= 85:
        overall = "优秀，班级整体表现优异"
    elif avg >= 72:
        overall = "良好，班级整体处于中上水平"
    elif avg >= 60:
        overall = "一般，班级整体处于中等水平，需加强基础"
    else:
        overall = "较弱，班级整体基础薄弱，建议系统复习"

    # 教学建议
    weakest_q = "（请根据本次考试错题情况填写）"
    suggestions = f"""
### 教学建议

1. **班级整体复习策略**
   针对本次考试反映出的问题，建议在下阶段重点复习：{weakest_q}

2. **分层辅导计划**
   - 及格线以下（{passed}人）：加强基础概念讲解，每天布置5分钟基础练习
   - 良好以上（{excellent}人）：提供拓展题，鼓励参加学科竞赛

3. **重点关注学生**
   本次低于40分的学生建议单独约谈，分析原因并制定个别辅导计划。

4. **家校沟通**
   建议对本次成绩波动较大的学生（进步/退步超过10分）主动与家长沟通。
"""

    report = f"""
# 【学情分析报告】{class_name} - {exam_name}

## 一、整体概况

| 指标 | 数值 |
|------|------|
| 应考人数 | {n}人 |
| 平均分 | {avg}分 |
| 中位数 | {median}分 |
| 最高分 | {max_score}分 |
| 最低分 | {min_score}分 |
| 标准差 | {std}分 |
| 及格率 | {pass_rate}%（{passed}人）|
| 优良率 | {excellent_rate}%（{excellent}人）|

## 二、分数段分布

| 分数段 | 人数 | 占比 |
|--------|------|------|
"""
    for label, count, pct in dist:
        report += f"| {label} | {count}人 | {pct}% |\n"

    report += f"""
## 三、班级画像

**整体水平**：{overall}

**主要失分点**：{weakest_q}

**进步显著**：（本次与上次对比后填写）

**需重点关注**：分数低于40分的学生（名单略）

## 四、分数分布（横向条形图示意）

"""
    # 简单条形图
    max_bar = 30
    for label, count, pct in dist:
        bar_len = int(pct / 100 * max_bar)
        report += f"{label:　<12} {'█' * bar_len} {count}人 ({pct}%)\n"

    report += f"""
## 五、TOP5 高分学生

| 排名 | 姓名 | 分数 | 百分位 |
|------|------|------|--------|
"""
    for rank, score in enumerate(top5, 1):
        pct = percentile_rank(scores, score)
        report += f"| {rank} | [姓名] | {score}分 | 前{pct}% |\n"

    report += suggestions

    report += f"""
---

*本报告由 AI 自动生成，数据仅供参考，请结合实际情况使用。*
*生成时间：自动记录*
"""
    return report


def main():
    print("\n" + "=" * 50)
    print("  新知绘宇·AI 学情分析器")
    print("=" * 50)

    print("\n[基本信息]")
    class_name = ask("班级名称", "八年级（3）班")
    exam_name = ask("考试名称", "期中考试")
    subject = ask("科目（可选）", "全科")

    print("\n[输入成绩]")
    print("  请输入学生分数，支持以下格式：")
    print("    85, 90, 76, 88, 92, ...")
    print("    张三:85, 李四:90, ...")
    raw_text = ask("输入分数（逗号分隔）", "85, 90, 76, 88, 92")
    scores = parse_scores(raw_text)

    if not scores:
        print("\n  未能解析到分数，请重试！")
        return

    print(f"\n  已解析 {len(scores)} 个成绩，开始分析……")

    report = generate_report(class_name, exam_name, scores)

    # 保存
    safe_name = class_name.replace("（", "").replace("）", "").replace(" ", "_")
    out_file = Path(__file__).parent.parent / "data" / f"学情分析_{safe_name}_{exam_name}.md"
    out_file.parent.mkdir(exist_ok=True)
    out_file.write_text(report, encoding="utf-8")

    print(f"\n  报告已生成：{out_file.name}\n")
    print(report)


if __name__ == "__main__":
    main()
