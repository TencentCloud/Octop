#!/usr/bin/env python3
"""
教案生成器（交互式）
引导教师填写关键信息，生成完整教案。
python scripts/lesson_planner.py
"""

import json
from pathlib import Path

TEMPLATE = """
# 【教案】《{topic}》- 第{period}课时 / 共{total_periods}课时

| 项目 | 内容 |
|------|------|
| 学科 | {grade}{subject} |
| 教材 | {textbook} |
| 课时 | {duration}分钟 |
| 授课教师 | {teacher} |

## 一、教学目标

### 知识与技能
{objective_knowledge}

### 过程与方法
{objective_method}

### 情感态度与价值观
{objective_emotion}

## 二、教学重点
{teaching_focus}

## 三、教学难点
{teaching_difficulty}

## 四、教学准备
- 教师：{teacher_prep}
- 学生：{student_prep}

## 五、教学过程

| 环节 | 时间 | 教师活动 | 学生活动 | 设计意图 |
|------|------|---------|---------|----------|
| 导入 | {time_intro}分钟 | | | |
| 新授 | {time_teach}分钟 | | | |
| 练习 | {time_practice}分钟 | | | |
| 总结 | {time_summary}分钟 | | | |

## 六、板书设计
```
{blackboard_design}
```

## 七、作业布置
- 必做：{homework_required}
- 选做：{homework_optional}

## 八、教学反思
（课后填写）
1. 本课目标达成情况：
2. 学生反应与生成：
3. 改进措施：
"""


def ask(prompt, default=""):
    val = input(f"  {prompt}" + (f" [{default}]" if default else "") + ": ").strip()
    return val if val else default


def main():
    print("\n" + "=" * 50)
    print("  新知绘宇·AI 教案生成器")
    print("=" * 50)

    print("\n[基本信息]")
    subject = ask("学科", "语文")
    grade = ask("年级（如：八年级）", "八年级")
    topic = ask("课题名称", "《背影》")
    textbook = ask("教材版本", "部编版")
    period = ask("第几课时", "1")
    total_periods = ask("共几课时", "2")
    duration = ask("课时时长（分钟）", "45")
    teacher = ask("授课教师", "张老师")

    print("\n[教学目标]")
    objective_knowledge = ask("知识与技能目标", "掌握本课生字词，理解文章主要内容")
    objective_method = ask("过程与方法目标", "通过朗读、讨论，体会作者情感")
    objective_emotion = ask("情感态度与价值观目标", "感受亲情，培养感恩意识")

    print("\n[重难点]")
    teaching_focus = ask("教学重点", "理解文中关键语句的含义")
    teaching_difficulty = ask("教学难点", "体会父子之间的深情")

    print("\n[教学准备]")
    teacher_prep = ask("教师准备", "多媒体课件、朗读音频")
    student_prep = ask("学生准备", "预习课文，标记不理解的句子")

    print("\n[时间分配（分钟）]")
    time_intro = ask("导入环节", "5")
    time_teach = ask("新授环节", "25")
    time_practice = ask("练习环节", "10")
    time_summary = ask("总结环节", "5")

    print("\n[板书设计]")
    board_raw = ask("板书内容（多行用 | 分隔）", "课题 | 核心公式 | 例题步骤")
    lines = [l.strip() for l in board_raw.split("|") if l.strip()]
    blackboard_design = "\n".join(f"  {i+1}. {l}" for i, l in enumerate(lines)) if lines else "（根据实际填写）"

    print("\n[作业布置]")
    homework_required = ask("必做作业", "完成课后练习第1-3题")
    homework_optional = ask("选做作业", "写一段给父母的心里话")

    # 生成教案
    plan = TEMPLATE.format(
        topic=topic,
        period=period,
        total_periods=total_periods,
        grade=grade,
        subject=subject,
        textbook=textbook,
        duration=duration,
        teacher=teacher,
        objective_knowledge=objective_knowledge,
        objective_method=objective_method,
        objective_emotion=objective_emotion,
        teaching_focus=teaching_focus,
        teaching_difficulty=teaching_difficulty,
        teacher_prep=teacher_prep,
        student_prep=student_prep,
        time_intro=time_intro,
        time_teach=time_teach,
        time_practice=time_practice,
        time_summary=time_summary,
        blackboard_design=blackboard_design,
        homework_required=homework_required,
        homework_optional=homework_optional,
    )

    # 保存
    safe_name = topic.replace("《", "").replace("》", "").replace(" ", "_")
    out_file = Path(__file__).parent.parent / "data" / f"教案_{safe_name}_课时{period}.md"
    out_file.parent.mkdir(exist_ok=True)
    out_file.write_text(plan, encoding="utf-8")

    print("\n" + "=" * 50)
    print(f"  教案已生成：{out_file.name}")
    print("=" * 50)
    print("\n" + plan)


if __name__ == "__main__":
    main()
