#!/usr/bin/env bash
# court-prep — 法庭/诉讼准备工具
set -euo pipefail
CMD="${1:-help}"; shift 2>/dev/null || true; INPUT="$*"
run_python() {
python3 << 'PYEOF'
import sys, json
from datetime import datetime, timedelta

cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
inp = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""

CASE_TYPES = {
    "civil": {"name": "民事案件", "stages": ["立案","举证期限","开庭审理","判决","上诉期"],
              "docs": ["起诉状","证据目录","证据清单","授权委托书","身份证明"]},
    "labor": {"name": "劳动争议", "stages": ["仲裁申请","仲裁开庭","仲裁裁决","不服起诉","法院审理"],
              "docs": ["仲裁申请书","劳动合同","工资条","考勤记录","社保证明"]},
    "contract": {"name": "合同纠纷", "stages": ["协商","调解","立案","举证","开庭"],
                 "docs": ["合同原件","履行证据","违约证据","损失证明","催告函"]},
    "injury": {"name": "人身损害", "stages": ["报案","伤残鉴定","立案","开庭","执行"],
               "docs": ["诊断证明","医疗费票据","误工证明","伤残鉴定书","事故认定书"]},
    "divorce": {"name": "离婚案件", "stages": ["起诉","调解","财产调查","开庭","判决"],
                "docs": ["起诉状","结婚证","财产证明","子女出生证","感情破裂证据"]},
}

EVIDENCE_RULES = [
    "原件优于复印件",
    "公证文书证明力最强",
    "视听资料需说明来源和制作过程",
    "证人应出庭作证",
    "电子数据需原始载体或公证",
    "当事人陈述需其他证据佐证",
    "鉴定结论需有资质的机构出具",
    "书证应提交原件，不能提交原件需说明理由",
]

def cmd_checklist():
    if not inp:
        print("Usage: checklist <case_type>")
        print("Types: {}".format(", ".join(CASE_TYPES.keys())))
        return
    ctype = inp.strip().lower()
    if ctype not in CASE_TYPES:
        print("Unknown case type. Available: {}".format(", ".join(CASE_TYPES.keys())))
        return
    ct = CASE_TYPES[ctype]
    print("=" * 55)
    print("  {} — 准备清单".format(ct["name"]))
    print("=" * 55)
    print("")
    print("  一、必备文件:")
    for i, d in enumerate(ct["docs"], 1):
        print("    [ ] {}. {}".format(i, d))
    print("")
    print("  二、诉讼流程:")
    for i, s in enumerate(ct["stages"], 1):
        print("    {}. {}".format(i, s))
    print("")
    print("  三、通用准备:")
    general = ["身份证复印件(2份)","授权委托书(如有代理人)","证据副本(按对方人数+1)","诉讼费缴纳凭证","法院地址和开庭时间确认"]
    for g in general:
        print("    [ ] {}".format(g))

def cmd_complaint():
    if not inp:
        print("Usage: complaint <plaintiff> <defendant> <case_type> [amount]")
        print("Example: complaint 张三 某公司 contract 50000")
        return
    parts = inp.split()
    plaintiff = parts[0] if len(parts) > 0 else "原告"
    defendant = parts[1] if len(parts) > 1 else "被告"
    ctype = parts[2] if len(parts) > 2 else "civil"
    amount = parts[3] if len(parts) > 3 else "___"

    print("=" * 55)
    print("  民 事 起 诉 状")
    print("=" * 55)
    print("")
    print("  原告: {}, 性别___, 年龄___, ".format(plaintiff))
    print("        住址: ___")
    print("        联系电话: ___")
    print("")
    print("  被告: {}, ".format(defendant))
    print("        住所地: ___")
    print("        法定代表人: ___")
    print("")
    print("  诉讼请求:")
    print("    1. 判令被告向原告支付{}元;".format(amount))
    print("    2. 判令被告承担本案诉讼费用;")
    print("    3. ___")
    print("")
    print("  事实与理由:")
    print("    [在此详细描述案件事实经过]")
    print("    ___")
    print("")
    print("  证据及证据来源:")
    print("    1. ___")
    print("    2. ___")
    print("")
    print("  此致")
    print("  ___人民法院")
    print("")
    print("  起诉人: {}".format(plaintiff))
    print("  日期: {}".format(datetime.now().strftime("%Y年%m月%d日")))

def cmd_evidence():
    print("=" * 55)
    print("  证据准备指南")
    print("=" * 55)
    print("")
    print("  一、证据种类 (民诉法第66条)")
    types = ["当事人陈述","书证","物证","视听资料","电子数据","证人证言","鉴定意见","勘验笔录"]
    for i, t in enumerate(types, 1):
        print("    {}. {}".format(i, t))
    print("")
    print("  二、举证规则")
    for i, r in enumerate(EVIDENCE_RULES, 1):
        print("    {}. {}".format(i, r))
    print("")
    print("  三、证据目录模板")
    print("  {:>4s} {:>12s} {:>8s} {:>20s}".format("序号", "证据名称", "类型", "证明内容"))
    print("  " + "-" * 48)
    for i in range(1, 6):
        print("  {:>4d} {:>12s} {:>8s} {:>20s}".format(i, "___", "___", "___"))

def cmd_timeline():
    if not inp:
        print("Usage: timeline <filing_date> <case_type>")
        print("Example: timeline 2026-04-01 civil")
        return
    parts = inp.split()
    try:
        filing = datetime.strptime(parts[0], "%Y-%m-%d")
    except:
        print("Date format: YYYY-MM-DD")
        return
    ctype = parts[1] if len(parts) > 1 else "civil"

    print("=" * 55)
    print("  诉讼时间线预估")
    print("  立案日期: {}".format(filing.strftime("%Y-%m-%d")))
    print("=" * 55)
    print("")
    milestones = [
        ("立案受理", 7), ("送达被告", 12), ("举证期限", 30),
        ("开庭通知", 37), ("开庭审理", 45), ("判决书送达", 90),
        ("上诉期届满", 105),
    ]
    for name, days in milestones:
        d = filing + timedelta(days=days)
        print("  {} — {} (第{}天)".format(d.strftime("%Y-%m-%d"), name, days))

def cmd_fee():
    if not inp:
        print("Usage: fee <amount>")
        print("Example: fee 100000")
        return
    amount = float(inp)
    # Simplified Chinese court fee schedule
    if amount <= 10000:
        fee = 50
    elif amount <= 100000:
        fee = amount * 0.025 - 200
    elif amount <= 200000:
        fee = amount * 0.02 + 300
    elif amount <= 500000:
        fee = amount * 0.015 + 1300
    elif amount <= 1000000:
        fee = amount * 0.01 + 3800
    elif amount <= 2000000:
        fee = amount * 0.009 + 4800
    else:
        fee = amount * 0.005 + 12800

    print("=" * 45)
    print("  诉讼费计算")
    print("=" * 45)
    print("")
    print("  标的金额: {:>12,.0f} 元".format(amount))
    print("  诉讼费:   {:>12,.0f} 元".format(fee))
    print("  减半(简易): {:>10,.0f} 元".format(fee / 2))
    print("")
    print("  注: 实际费用以法院收费标准为准")
    print("  败诉方承担诉讼费用")

commands = {
    "checklist": cmd_checklist, "complaint": cmd_complaint,
    "evidence": cmd_evidence, "timeline": cmd_timeline, "fee": cmd_fee,
}
if cmd == "help":
    print("Court Preparation Tool")
    print("")
    print("Commands:")
    print("  checklist <type>                — Case preparation checklist")
    print("  complaint <p> <d> <type> [amt]  — Generate complaint template")
    print("  evidence                        — Evidence preparation guide")
    print("  timeline <date> [type]          — Litigation timeline estimate")
    print("  fee <amount>                    — Court fee calculator")
    print("")
    print("Case types: civil, labor, contract, injury, divorce")
elif cmd in commands:
    commands[cmd]()
else:
    print("Unknown: {}".format(cmd))
print("")
print("Powered by BytesAgain | bytesagain.com")
print("Disclaimer: For reference only. Consult a licensed attorney.")
PYEOF
}
run_python "$CMD" $INPUT
