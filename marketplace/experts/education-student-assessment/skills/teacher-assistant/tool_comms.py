#!/usr/bin/env python3
"""
家校沟通文稿生成器
生成各类家长通知、反馈信件、班级通知。
python scripts/communication_writer.py
"""

from pathlib import Path

TYPES = {
    "1": ("家长会通知", "parent_meeting"),
    "2": ("致家长的一封信", "parent_letter"),
    "3": ("学生在校表现反馈", "student_feedback"),
    "4": ("班级活动通知", "activity_notice"),
    "5": ("考试成绩通知", "exam_notice"),
}


def ask(prompt, default=""):
    val = input(f"  {prompt}" + (f" [{default}]" if default else "") + ": ").strip()
    return val if val else default


def generate_parent_meeting(teacher, class_name, date, time, location, agenda, contact):
    return f"""# 家长会通知函

尊敬的家长：

您好！

为了加强学校与家庭的沟通，形成教育合力，共同促进孩子的健康成长，
我班定于召开本学期家长会，诚挚邀请您准时出席。

## 会议信息

| 项目 | 内容 |
|------|------|
| 时间 | {date} {time} |
| 地点 | {location} |
| 班主任 | {teacher} |

## 会议议程

{agenda}

## 温馨提示

1. 请您提前5分钟入场签到
2. 请将手机调至静音模式
3. 如有特殊情况无法出席，请提前与班主任联系
4. 会议期间请勿带低龄儿童入场

{contact}

感谢您的支持与配合！

此致
敬礼

{teacher}
{class_name}
（日期）
"""


def generate_parent_letter(teacher, class_name, purpose, background, suggestions, closing):
    return f"""# 致家长的一封信

尊敬的家长：

您好！

{background}

【本次沟通目的】
{purpose}

【给您的建议】
{suggestions}

{closing}

让我们携手同行，共同见证孩子的成长！

此致
敬礼

{teacher}
{class_name}
（日期）
"""


def generate_student_feedback(student_name, grade_class, period, overview, strengths, challenges, suggestions, teacher):
    return f"""# 学生在校表现反馈单

尊敬的家长：

您好！现将{student_name}同学在{period}的在校表现反馈如下：

## 综合概述
{overview}

## 优势与亮点
{strengths}

## 需关注与改进
{challenges}

## 家庭配合建议
{suggestions}

孩子的成长离不开学校与家庭的共同努力，期待我们携手合作，
帮助{student_name}取得更大进步！

{teacher}
（日期）
"""


def generate_activity_notice(teacher, class_name, activity_name, date, time, location, content, items, note):
    return f"""# {activity_name}通知

尊敬的家长：

您好！

为了丰富学生的课余生活，增强班级凝聚力，
我班将组织{activity_name}，详情如下：

## 活动信息

| 项目 | 内容 |
|------|------|
| 活动名称 | {activity_name} |
| 时间 | {date} {time} |
| 地点 | {location} |

## 活动内容
{content}

## 需要准备
{items}

## 注意事项
{note}

请您在回执上签字，并于{date}前交给班主任。

{teacher}
{class_name}
（日期）

---

**回执单（请签字交回）**

学生姓名：__________　家长签字：__________　是否参加：□是 □否
"""


def main():
    print("\n" + "=" * 50)
    print("  新知绘宇·AI 家校沟通文稿生成器")
    print("=" * 50)

    print("\n[选择文稿类型]")
    for k, (name, _) in TYPES.items():
        print(f"  {k} - {name}")
    choice = ask("选择（1-5）", "1")
    tpl = TYPES.get(choice, TYPES["1"])[0]

    print("\n[基本信息]")
    teacher = ask("班主任/教师姓名", "")
    class_name = ask("班级", "")
    date = ask("日期", "2025年xx月xx日")

    if choice == "1":
        time_ = ask("时间", "下午14:00")
        location = ask("地点", "xx教室")
        agenda = ask("议程（换行用|分隔）", "班级情况通报|学科教学反馈|期中/期末总结|家长交流")
        contact = ask("联系方式（可选）", "")
        content = generate_parent_meeting(teacher, class_name, date, time_, location, agenda, contact)

    elif choice == "2":
        background = ask("写信背景/事由", "您的孩子正处于身心发展的关键时期，需要家校共同关注")
        purpose = ask("沟通目的", "共同关注孩子的学习习惯和心理健康")
        suggestions = ask("给家长的建议", "建议家长每天抽出时间与孩子交流，了解在校情况；关注孩子使用电子产品的时间；配合学校做好教育工作")
        closing = ask("结尾寄语（可选）", "让我们携手同行，共同见证孩子的成长！")
        content = generate_parent_letter(teacher, class_name, purpose, background, suggestions, closing)

    elif choice == "3":
        student_name = ask("学生姓名", "")
        period = ask("反馈周期", "本学期")
        overview = ask("综合概述（简要）", "该生在校表现良好，学习态度端正")
        strengths = ask("优势亮点", "上课认真听讲，积极发言；与同学相处融洽；劳动积极")
        challenges = ask("需关注点", "建议加强体育锻炼；部分学科需查漏补缺")
        suggestions = ask("家庭配合建议", "建议家长多与孩子沟通；关注心理健康；培养自主学习习惯")
        content = generate_student_feedback(student_name, class_name, period, overview, strengths, challenges, suggestions, teacher)

    elif choice == "4":
        activity_name = ask("活动名称", "")
        time_ = ask("时间", "另行通知")
        location = ask("地点", "待定")
        activity_content = ask("活动内容简介", "")
        items = ask("需准备物品", "请穿校服、运动鞋；自带水杯")
        note = ask("注意事项", "如有身体不适请提前告知；服从带队老师安排")
        content = generate_activity_notice(teacher, class_name, activity_name, date, time_, location, activity_content, items, note)

    else:
        content = f"# {tpl}\n\n（请在下方填写内容）\n"

    # 保存
    safe_class = class_name.replace("（", "").replace("）", "").replace(" ", "_")
    out_file = Path(__file__).parent.parent / "data" / f"家校沟通_{safe_class}_{tpl}_{date}.md"
    out_file.parent.mkdir(exist_ok=True)
    out_file.write_text(content, encoding="utf-8")

    print(f"\n  文稿已生成：{out_file.name}\n")
    print(content)


if __name__ == "__main__":
    main()
