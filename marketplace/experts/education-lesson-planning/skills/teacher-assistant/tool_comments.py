#!/usr/bin/env python3
"""
批量评语生成器
输入班级名单和基本信息，批量生成个性化期末评语。
python scripts/report_card_writer.py
"""

import json
from pathlib import Path

# 默认评语库（按类型分类，供 AI 参考）
COMMENT_POOL = {
    "study_positive": [
        "学习态度认真，课堂上积极思考，回答问题声音洪亮。",
        "作业书写工整，每次都能按时完成，学习习惯很好。",
        "对本学科有浓厚兴趣，经常主动查阅相关资料。",
        "思维活跃，接受新知识速度快，举一反三能力强。",
    ],
    "study_negative": [
        "上课有时走神，需要更加专注。",
        "作业完成质量不稳定，需要认真对待每一次练习。",
        "课堂上较少主动发言，希望能看到你更多的参与。",
    ],
    "moral": [
        "尊敬师长，团结同学，是老师的好帮手。",
        "热心班级事务，乐于助人，同学们都很喜欢你。",
        "遵守校纪校规，是班级遵纪守法的模范。",
    ],
    "pe": [
        "积极参加体育活动，是班级的运动健将。",
        "认真上好每一节体育课，身体素质有了明显提高。",
    ],
    "art": [
        "热爱劳动，每次大扫除都冲在前面。",
        "有审美情趣，在班级板报和文艺活动中表现出色。",
    ],
    "improvement": [
        "这学期进步明显，继续保持！",
        "相比上学期，各方面都有了很大进步，老师为你骄傲。",
        "希望你继续保持这股劲头，下学期一定更出色！",
    ],
}


def ask(prompt, default=""):
    val = input(f"  {prompt}" + (f" [{default}]" if default else "") + ": ").strip()
    return val if val else default


def generate_comment(
    name, gender, grade, strengths, weaknesses, moral="表现良好", pe="体育达标", art="积极参与"
):
    """为单个学生生成一条评语"""
    pronoun = "他" if gender in ["男", "男生", "male", "m"] else "她"
    subject = "他" if gender in ["男", "男生", "male", "m"] else "她"

    intro_options = [
        f"{name}是一个",
        f"{subject}是一位",
        f"{name}这学期",
    ]
    intro = intro_options[0]

    strengths_line = strengths if strengths else COMMENT_POOL["study_positive"][0]
    moral_line = moral if moral else COMMENT_POOL["moral"][0]
    pe_line = pe if pe else (COMMENT_POOL["pe"][0])
    art_line = art if art else COMMENT_POOL["art"][0]

    improvement = COMMENT_POOL["improvement"][0]

    # 劣势的处理（用正向语言表达）
    weak_note = ""
    if weaknesses and weaknesses.strip():
        weak_note = f"老师希望{pronoun}在{weaknesses}方面更加努力，"

    comment = f"""你是一个{strengths_line}的孩子。

在学习上，{strengths_line}。{weak_note}相信{pronoun}一定可以做得更好！

在日常生活中，{moral_line}。{pe_line}。{art_line}。

{improvement}

—— 班主任
"""
    return comment.strip()


def main():
    print("\n" + "=" * 50)
    print("  新知绘宇·AI 批量评语生成器")
    print("=" * 50)

    print("\n[基本信息]")
    class_name = ask("班级名称", "三年级（1）班")
    term = ask("学期（如：2024学年第二学期）", "2025学年第一学期")
    teacher = ask("班主任姓名", "")

    print("\n[学生名单]")
    print("  请输入学生信息，多条用 | 分隔：")
    print("    格式：姓名,性别（男/女）,学习优势（可选）,需改进（可选）")
    print("    示例：张三,男,数学思维敏捷,计算准确率 | 李四,女,英语口语流利,写作需加强")
    student_raw = ask("学生信息（多条用 | 分隔）", "张三,男,数学思维敏捷,计算马虎 | 李四,女,英语流利,写作薄弱")
    lines = [l.strip() for l in student_raw.split("|") if l.strip()]

    students = []
    for line in lines:
        parts = [p.strip() for p in line.split(",")]
        name = parts[0] if parts else "学生"
        gender = parts[1] if len(parts) > 1 else "男"
        strengths = parts[2] if len(parts) > 2 else ""
        weaknesses = parts[3] if len(parts) > 3 else ""
        students.append({"name": name, "gender": gender, "strengths": strengths, "weaknesses": weaknesses})

    print(f"\n  共 {len(students)} 名学生，开始生成评语……\n")

    all_comments = f"# 【期末评语册】{class_name} - {term}\n"
    all_comments += f"**班主任**：{teacher}\n"
    all_comments += f"**学生总数**：{len(students)}人\n\n---\n\n"

    for i, s in enumerate(students, 1):
        comment = generate_comment(
            name=s["name"],
            gender=s["gender"],
            grade=class_name,
            strengths=s["strengths"],
            weaknesses=s["weaknesses"],
        )
        all_comments += f"## {i}. {s['name']}\n\n{comment}\n\n---\n\n"

    all_comments += "\n*本评语册由 AI 辅助生成，请班主任审核后使用。*\n"

    # 保存
    safe_class = class_name.replace("（", "").replace("）", "").replace(" ", "_")
    out_file = Path(__file__).parent.parent / "data" / f"评语册_{safe_class}_{term}.md"
    out_file.parent.mkdir(exist_ok=True)
    out_file.write_text(all_comments, encoding="utf-8")

    # 保存 JSON 数据
    json_file = out_file.with_suffix(".json")
    json_file.write_text(
        json.dumps({"class": class_name, "term": term, "teacher": teacher, "students": students}, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"\n  评语册已生成：{out_file.name}\n")
    print(all_comments[:2000])
    if len(all_comments) > 2000:
        print(f"\n  ……（共 {len(all_comments)} 字，已保存到文件）")


if __name__ == "__main__":
    main()
