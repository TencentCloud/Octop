#!/usr/bin/env python3
"""
分层作业设计器
输入学科/年级/单元，生成基础/提高/拓展三层作业。
python scripts/homework_designer.py
"""

from pathlib import Path

TEMPLATE = """# 【分层作业】{grade}{subject} - {unit}

## 作业目标
1. 巩固本单元核心知识点
2. 培养知识迁移与应用能力
3. 激发学科探究兴趣（选做层）

## 预计完成时间
- 基础层：{basic_time}分钟
- 提高层：{medium_time}分钟
- 拓展层：{advanced_time}分钟（选做）

---

## 【基础层】{basic_label}
**适合对象**：大多数学生

### 一、基础知识巩固
1. [基础题题干]
2. [基础题题干]
3. [基础题题干]

### 二、基本技能训练
1. [技能题题干]
2. [技能题题干]

**设计说明**：覆盖本单元核心概念和基本公式/语法/词汇，做到"会用"。

---

## 【提高层】{medium_label}
**适合对象**：完成基础后学有余力

### 一、变式训练
1. [变式题题干，需稍作变形]
2. [变式题题干]

### 二、综合应用
1. [综合题题干，涉及多个知识点]
2. [综合题题干]

**设计说明**：在基础上有提升，考察知识迁移能力，做到"会用且会用对方法"。

---

## 【拓展层】选做（{advanced_label}）
**适合对象**：学优生 / 对本学科有浓厚兴趣

### 一、探究性任务
1. [探究/实践/项目类题目]
2. [开放性问题，需自主查阅资料]

### 二、挑战题
1. [拔高题题干]
2. [跨学科/竞赛类题目]

**设计说明**：挑战思维极限，培养学科核心素养，做到"深度理解+创新应用"。

---

## 教师使用说明
- 基础层作业为必做，全班统一布置
- 提高层建议A/B两层布置（基础完成→提高）
- 拓展层鼓励优秀学生挑战，不强制
- "双减"要求：书面作业总量不超过90分钟，请合理控制

*本作业设计由 AI 辅助生成，请根据实际教学情况调整。*
"""


def ask(prompt, default=""):
    val = input(f"  {prompt}" + (f" [{default}]" if default else "") + ": ").strip()
    return val if val else default


def main():
    print("\n" + "=" * 50)
    print("  新知绘宇·AI 分层作业设计器")
    print("=" * 50)

    print("\n[基本信息]")
    subject = ask("学科", "数学")
    grade = ask("年级", "七年级")
    unit = ask("单元/课题名称", "一元一次方程")
    unit_index = ask("第几单元（数字）", "3")

    print("\n[时间设置]")
    basic_time = ask("基础层预计时间（分钟）", "15")
    medium_time = ask("提高层预计时间（分钟）", "20")
    advanced_time = ask("拓展层预计时间（分钟）", "25")

    print("\n[难度标签（可自定义）]")
    basic_label = ask("基础层标签", "达标")
    medium_label = ask("提高层标签", "优秀")
    advanced_label = ask("拓展层标签", "卓越")

    # 根据学科调整提示
    if subject in ["数学", "物理", "化学"]:
        unit_hint = "如：一元一次方程的解法、应用题列方程"
    elif subject in ["语文"]:
        unit_hint = "如：记叙文阅读、文言文词汇"
    elif subject in ["英语"]:
        unit_hint = "如：现在进行时、重点句型"
    else:
        unit_hint = "本单元核心知识点"

    print(f"\n[作业内容生成提示]")
    print(f"  请在下方输入各层作业的核心知识点（用逗号分隔）")
    basic_points = ask(f"基础层知识点（{unit_hint}）", "")
    medium_points = ask("提高层知识点（综合性/变式）", "")
    advanced_points = ask("拓展层知识点（探究/挑战）", "")

    # 生成作业
    homework = TEMPLATE.format(
        grade=grade,
        subject=subject,
        unit=f"第{unit_index}单元 {unit}" if unit_index else unit,
        basic_time=basic_time,
        medium_time=medium_time,
        advanced_time=advanced_time,
        basic_label=basic_label,
        medium_label=medium_label,
        advanced_label=advanced_label,
    )

    # 添加教师填写区
    fill_guide = f"""

---

## 【教师填写区】

### 基础层作业（{basic_time}分钟）
**知识点**：{basic_points or '（请填写）'}

1. _______________
2. _______________
3. _______________

### 提高层作业（{medium_time}分钟）
**知识点**：{medium_points or '（请填写）'}

1. _______________
2. _______________

### 拓展层作业（{advanced_time}分钟，选做）
**知识点**：{advanced_points or '（请填写）'}

1. _______________
2. _______________
"""
    homework += fill_guide

    # 保存
    safe_unit = unit.replace(" ", "_").replace("/", "_")
    out_file = Path(__file__).parent.parent / "data" / f"分层作业_{grade}{subject}_单元{unit_index}.md"
    out_file.parent.mkdir(exist_ok=True)
    out_file.write_text(homework, encoding="utf-8")

    print(f"\n  分层作业已生成：{out_file.name}\n")
    print(homework)


if __name__ == "__main__":
    main()
