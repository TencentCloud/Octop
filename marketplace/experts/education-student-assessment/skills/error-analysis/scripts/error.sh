#!/usr/bin/env bash
# error-analysis: 错题分析助手
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DATA_DIR="$SCRIPT_DIR/../data"
mkdir -p "$DATA_DIR"

CMD="${1:-help}"
shift 2>/dev/null || true

python3 - "$CMD" "$DATA_DIR" "$@" << 'PYTHON_EOF'
# -*- coding: utf-8 -*-
import sys
import os
import json
from datetime import datetime

def show_help():
    print("""
=== 错题分析助手 ===

用法:
  error.sh analyze "题目" "错误答案" "正确答案"   分析错题原因
  error.sh knowledge "知识点"                     知识点详细解析
  error.sh similar "题目类型"                     生成变式练习题
  error.sh summary                                错题统计与分析
  error.sh help                                   显示此帮助
""".strip())

def load_errors(data_dir):
    path = os.path.join(data_dir, "errors.json")
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return []

def save_errors(data_dir, errors):
    path = os.path.join(data_dir, "errors.json")
    with open(path, "w") as f:
        json.dump(errors, f, ensure_ascii=False, indent=2)

def analyze(data_dir, args):
    if len(args) < 3:
        print("[错误] 用法: error.sh analyze \"题目\" \"错误答案\" \"正确答案\"")
        sys.exit(1)

    question = args[0]
    wrong_answer = args[1]
    correct_answer = args[2]

    # 错误类型分析
    error_types = [
        {"type": "概念理解错误", "desc": "对基本概念、定义、定理的理解有偏差", "fix": "重新学习相关概念，用自己的话复述定义"},
        {"type": "计算失误", "desc": "思路正确但计算过程出错", "fix": "做题时放慢速度，养成验算习惯"},
        {"type": "审题不清", "desc": "没有看清题目条件或要求", "fix": "做题前先把关键词圈出来，读三遍题目"},
        {"type": "方法选择不当", "desc": "知道知识点但选错了解题方法", "fix": "总结同类题型的常用方法，建立解题模板"},
        {"type": "知识点遗忘", "desc": "之前学过但已经忘记", "fix": "按照艾宾浩斯遗忘曲线安排复习"},
    ]

    print("=" * 60)
    print("  🔍 错题分析报告")
    print("=" * 60)
    print()
    print("📋 【题目信息】")
    print("  题目：{}".format(question))
    print("  ❌ 你的答案：{}".format(wrong_answer))
    print("  ✅ 正确答案：{}".format(correct_answer))

    print("\n🧠 【可能的错误原因分析】\n")
    for i, et in enumerate(error_types, 1):
        print("  {}. 🏷️ {}".format(i, et["type"]))
        print("     描述：{}".format(et["desc"]))
        print("     纠正方法：{}".format(et["fix"]))
        print()

    print("📝 【纠错步骤建议】\n")
    steps = [
        "第一步：重新审题，圈出关键条件和问题",
        "第二步：不看答案，尝试独立重新解题",
        "第三步：对比正确解法，找出思维偏差点",
        "第四步：在错题本上记录题目、错因、正确思路",
        "第五步：找3道同类型题目巩固练习",
        "第六步：3天后再做一次这道题，检验是否掌握",
    ]
    for step in steps:
        print("  • {}".format(step))

    print("\n🔗 【举一反三】\n")
    print("  这道题考查的核心是理解题意并正确运用相关知识点。")
    print("  建议从以下角度深入思考：")
    print("  1. 如果改变题目中的某个条件，答案会怎样变化？")
    print("  2. 这道题还有其他解法吗？")
    print("  3. 能否把这道题推广到更一般的情况？")

    # 保存错题记录
    errors = load_errors(data_dir)
    record = {
        "id": len(errors) + 1,
        "question": question,
        "wrong_answer": wrong_answer,
        "correct_answer": correct_answer,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    errors.append(record)
    save_errors(data_dir, errors)
    print("\n✅ 已保存到错题本（第{}条记录）".format(record["id"]))

def knowledge(args):
    if not args:
        print("[错误] 用法: error.sh knowledge \"知识点\"")
        sys.exit(1)

    topic = args[0]

    # 常见知识点模板库
    knowledge_db = {
        "一元二次方程": {
            "definition": "形如 ax² + bx + c = 0 (a≠0) 的方程",
            "key_formulas": [
                "求根公式：x = (-b ± √(b²-4ac)) / 2a",
                "判别式：Δ = b² - 4ac",
                "韦达定理：x₁ + x₂ = -b/a, x₁ · x₂ = c/a",
            ],
            "common_errors": [
                "忘记 a≠0 的条件",
                "判别式计算错误导致根的个数判断错误",
                "韦达定理符号搞反",
            ],
            "tips": "解题时先算判别式，确定根的情况再求解",
        },
        "函数求导": {
            "definition": "导数表示函数在某点的瞬时变化率",
            "key_formulas": [
                "(xⁿ)' = nxⁿ⁻¹",
                "(sin x)' = cos x, (cos x)' = -sin x",
                "(eˣ)' = eˣ, (ln x)' = 1/x",
                "乘法法则：(fg)' = f'g + fg'",
                "链式法则：[f(g(x))]' = f'(g(x)) · g'(x)",
            ],
            "common_errors": [
                "复合函数求导忘记乘以内函数的导数",
                "常数项求导结果不是0",
                "三角函数导数符号搞错",
            ],
            "tips": "复合函数求导要\"由外到内，层层求导\"",
        },
    }

    print("=" * 60)
    print("  📖 知识点解析：{}".format(topic))
    print("=" * 60)

    info = knowledge_db.get(topic)
    if info:
        print("\n📌 【定义】")
        print("  {}".format(info["definition"]))

        print("\n📐 【核心公式/要点】")
        for i, f in enumerate(info["key_formulas"], 1):
            print("  {}. {}".format(i, f))

        print("\n⚠️ 【常见错误】")
        for i, e in enumerate(info["common_errors"], 1):
            print("  {}. {}".format(i, e))

        print("\n💡 【解题技巧】")
        print("  {}".format(info["tips"]))
    else:
        print("\n📌 【知识点概述】")
        print("  「{}」是一个重要的知识点。".format(topic))
        print()
        print("  建议从以下几个维度进行学习：")
        print("  1. 📖 基本定义：这个概念是什么？有什么前提条件？")
        print("  2. 📐 核心公式：有哪些关键公式/定理？推导过程是怎样的？")
        print("  3. 🔗 关联知识：与哪些知识点有联系？")
        print("  4. 📝 典型例题：常见的出题方式有哪些？")
        print("  5. ⚠️ 易错点：哪些地方容易犯错？")
        print()
        print("  💡 建议翻阅教材中「{}」相关章节，结合例题深入理解。".format(topic))

    print("\n📚 【推荐学习方法】\n")
    methods = [
        "费曼学习法：尝试用最简单的语言向别人解释这个知识点",
        "思维导图法：画出知识点之间的关联图",
        "例题驱动法：通过典型例题来理解抽象概念",
        "对比学习法：找到相似/相反的知识点进行对比",
    ]
    for m in methods:
        print("  • {}".format(m))

def similar(args):
    if not args:
        print("[错误] 用法: error.sh similar \"题目类型\"")
        sys.exit(1)

    topic = args[0]

    # 变式题模板库
    similar_db = {
        "一元二次方程": [
            {"q": "解方程：x² - 5x + 6 = 0", "a": "x = 2 或 x = 3", "method": "因式分解法"},
            {"q": "解方程：2x² + 3x - 2 = 0", "a": "x = 1/2 或 x = -2", "method": "求根公式法"},
            {"q": "已知方程 x² - 3x + k = 0 有两个相等的实数根，求 k 的值", "a": "k = 9/4", "method": "判别式法"},
            {"q": "已知方程 x² + px + q = 0 的两根之和为4，两根之积为3，求 p 和 q", "a": "p = -4, q = 3", "method": "韦达定理"},
            {"q": "解方程：(x-1)² = 4", "a": "x = 3 或 x = -1", "method": "直接开平方法"},
        ],
        "函数求导": [
            {"q": "求 f(x) = 3x⁴ - 2x² + 5x - 1 的导数", "a": "f'(x) = 12x³ - 4x + 5", "method": "幂函数求导"},
            {"q": "求 f(x) = x·sin(x) 的导数", "a": "f'(x) = sin(x) + x·cos(x)", "method": "乘法法则"},
            {"q": "求 f(x) = sin(2x+1) 的导数", "a": "f'(x) = 2cos(2x+1)", "method": "链式法则"},
            {"q": "求 f(x) = e^(x²) 的导数", "a": "f'(x) = 2x·e^(x²)", "method": "链式法则"},
            {"q": "求 f(x) = ln(x²+1) 的导数", "a": "f'(x) = 2x/(x²+1)", "method": "链式法则"},
        ],
    }

    print("=" * 60)
    print("  ✏️ 变式练习题：{}".format(topic))
    print("=" * 60)

    problems = similar_db.get(topic)
    if problems:
        for i, p in enumerate(problems, 1):
            print("\n📝 第{}题 [{}]".format(i, p["method"]))
            print("  题目：{}".format(p["q"]))
            print("  ────────────────────────────")
            print("  参考答案：{}".format(p["a"]))
    else:
        # 通用变式题生成
        print("\n📝 关于「{}」的变式练习建议：\n".format(topic))
        suggestions = [
            "第1题（基础）：从定义出发的直接应用题",
            "第2题（基础）：改变数值的同类型题",
            "第3题（中等）：需要两步推理的综合题",
            "第4题（中等）：逆向思维题（已知结果求条件）",
            "第5题（提高）：与其他知识点结合的综合题",
        ]
        for s in suggestions:
            print("  • {}".format(s))
        print()
        print("  💡 建议在教材或题库中搜索「{}」相关题目进行练习".format(topic))

    print("\n💡 【做题建议】\n")
    print("  1. 先独立做，不要看答案")
    print("  2. 每道题限时5-10分钟")
    print("  3. 做错的题标记出来，分析错因")
    print("  4. 隔3天再做一遍做错的题")

def summary(data_dir, args):
    errors = load_errors(data_dir)

    print("=" * 60)
    print("  📊 错题统计报告")
    print("=" * 60)

    if not errors:
        print("\n  📭 错题本为空！")
        print("  使用 error.sh analyze 命令添加错题记录")
        return

    print("\n📈 【总体统计】\n")
    print("  总错题数：{}道".format(len(errors)))

    # 按日期统计
    date_count = {}
    for e in errors:
        date = e.get("date", "未知").split(" ")[0]
        date_count[date] = date_count.get(date, 0) + 1

    print("  记录天数：{}天".format(len(date_count)))
    print("  平均每天：{:.1f}道".format(len(errors) * 1.0 / max(1, len(date_count))))

    print("\n📅 【按日期分布】\n")
    for date in sorted(date_count.keys(), reverse=True)[:10]:
        count = date_count[date]
        bar = "█" * count
        print("  {} │ {} ({})".format(date, bar, count))

    print("\n📋 【最近错题记录】\n")
    recent = errors[-5:]
    for e in reversed(recent):
        print("  #{} [{}]".format(e["id"], e.get("date", "未知")))
        print("     题目：{}".format(e["question"][:50]))
        print("     ❌ {} → ✅ {}".format(e["wrong_answer"][:30], e["correct_answer"][:30]))
        print()

    print("💡 【改进建议】\n")
    print("  • 定期回顾错题本，每周至少1次")
    print("  • 对反复出错的题目重点标记")
    print("  • 错题超过5道的知识点需要重新学习")
    print("  • 建议用 error.sh knowledge 深入学习薄弱知识点")

def main():
    args = sys.argv[1:]
    if not args:
        show_help()
        return

    cmd = args[0]
    data_dir = args[1] if len(args) > 1 else "."
    rest = args[2:]

    if cmd == "help":
        show_help()
    elif cmd == "analyze":
        analyze(data_dir, rest)
    elif cmd == "knowledge":
        knowledge(rest)
    elif cmd == "similar":
        similar(rest)
    elif cmd == "summary":
        summary(data_dir, rest)
    elif cmd == "pattern":
        subject = rest[0] if rest else "数学"
        print("=" * 56)
        print("  🔍 错误模式分析 — {}".format(subject))
        print("=" * 56)
        patterns = [
            ("知识盲点型", "概念/公式/定义掌握不牢", [
                "典型表现: 完全不会做，看答案恍然大悟",
                "占比估计: ____%",
                "补救: 回归课本，整理知识清单",
                "优先级: ⭐⭐⭐⭐⭐（必须先解决）",
            ]),
            ("粗心大意型", "计算错误/审题不仔细/抄错数", [
                "典型表现: 会做但做错，事后一看就知道",
                "占比估计: ____%",
                "补救: 建立检查流程，草稿纸规范化",
                "优先级: ⭐⭐⭐（习惯养成）",
            ]),
            ("理解偏差型", "概念理解有误/思路方向错", [
                "典型表现: 做了但思路完全跑偏",
                "占比估计: ____%",
                "补救: 找老师一对一纠正，做变式题",
                "优先级: ⭐⭐⭐⭐（根治需要时间）",
            ]),
            ("综合应用型", "单个知识点会但综合题不会", [
                "典型表现: 基础题会做，难题无从下手",
                "占比估计: ____%",
                "补救: 专项练习综合题，建立解题模型",
                "优先级: ⭐⭐⭐⭐（提分关键）",
            ]),
            ("时间管理型", "会做但来不及做完", [
                "典型表现: 考试时间不够，后面题没做",
                "占比估计: ____%",
                "补救: 限时训练，优化做题顺序",
                "优先级: ⭐⭐⭐（考试策略）",
            ]),
        ]
        for i, (name, desc, items) in enumerate(patterns):
            print()
            print("  {}. {} — {}".format(i+1, name, desc))
            for item in items:
                print("    {}".format(item))
        print()
        print("  📊 自测: 统计你最近20道错题，归类到以上5种模式")
        print("  🎯 策略: 先解决占比最高的类型，效果最明显")
        print()
        print("  Powered by BytesAgain | bytesagain.com | hello@bytesagain.com")
    elif cmd == "plan":
        subject = rest[0] if rest else "数学"
        import datetime
        today = datetime.datetime.now()
        print("=" * 56)
        print("  📋 补强计划 — {}".format(subject))
        print("=" * 56)
        weeks = [
            ("诊断周", "找出所有薄弱知识点", [
                "□ 整理最近3次考试/作业的错题",
                "□ 按知识点分类，统计错误频率",
                "□ 标记TOP3高频错误知识点",
                "□ 回归课本，重新学习这3个知识点",
            ]),
            ("攻坚周", "集中突破TOP3薄弱点", [
                "□ 每天30分钟专项练习",
                "□ 每个知识点做10道基础题",
                "□ 错题重做，确保理解",
                "□ 用费曼技巧给别人讲一遍",
            ]),
            ("巩固周", "变式训练+综合应用", [
                "□ 做变式题检验是否真的掌握",
                "□ 尝试综合题，串联知识点",
                "□ 限时模拟，训练速度",
                "□ 更新错题本，看是否有新的薄弱点",
            ]),
            ("检验周", "自我测试+查漏补缺", [
                "□ 做一套完整测试卷",
                "□ 对比之前的成绩，评估进步",
                "□ 针对剩余弱点制定下轮计划",
                "□ 奖励自己！🎉",
            ]),
        ]
        for i, (name, goal, tasks) in enumerate(weeks):
            week_start = today + datetime.timedelta(weeks=i)
            print()
            print("  第{}周 ({}) — {}".format(i+1, week_start.strftime("%m/%d"), name))
            print("  目标: {}".format(goal))
            for t in tasks:
                print("    {}".format(t))
        print()
        print("  ⏰ 每天投入: 30-45分钟")
        print("  📈 预期效果: 4周后该科目提升10-20%")
        print()
        print("  Powered by BytesAgain | bytesagain.com | hello@bytesagain.com")
    else:
        print("[错误] 未知命令: {}".format(cmd))
        show_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
PYTHON_EOF

echo ""
echo "  Powered by BytesAgain | bytesagain.com | hello@bytesagain.com"
