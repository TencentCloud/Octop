#!/usr/bin/env bash
# bytesagain-copywriter-cn — Chinese copywriting generator
set -euo pipefail

CMD="${1:-help}"
shift || true

show_help() {
    echo "bytesagain-copywriter-cn — 中英文广告文案生成工具"
    echo ""
    echo "Usage:"
    echo "  bytesagain-copywriter-cn ad <product> <audience>     广告文案"
    echo "  bytesagain-copywriter-cn product <name> <features>   产品描述"
    echo "  bytesagain-copywriter-cn email <topic> <goal>        邮件文案"
    echo "  bytesagain-copywriter-cn aida <product>              AIDA框架"
    echo "  bytesagain-copywriter-cn ab <product>                A/B变体"
    echo "  bytesagain-copywriter-cn slogan <brand> <values>     品牌口号"
    echo ""
}

cmd_ad() {
    local product="${1:-产品}"; local audience="${2:-用户}"
    CW_PRODUCT="$product" CW_AUDIENCE="${audience:-}" CW_NAME="${name:-}" CW_FEATURES="${features:-}" CW_TOPIC="${topic:-}" CW_GOAL="${goal:-转化}" python3 << 'PYEOF'
import os; product = os.environ.get("CW_PRODUCT",""); audience = os.environ.get("CW_AUDIENCE","")
print(f"""
=== 广告文案: {product} ===
目标受众: {audience}

【版本A — 痛点切入】
还在为[痛点]烦恼？
{product}帮你一步解决。
不是吹的，[具体数据/结果]。
→ 立即体验，首单优惠

【版本B — 结果导向】
用了{product}之后：
✅ [结果1]
✅ [结果2]  
✅ [结果3]
{audience}都在用，你还在等什么？

【版本C — 社交证明】
"[用户真实评价]" — 来自真实用户
{product}已帮助10,000+用户实现[目标]
限时优惠，今天下单立减[X]元

【版本D — 紧迫感】
⚠️ 最后[X]小时
{product}限时特惠即将结束
错过今天，等三个月
[立即抢购按钮]

【文案要素清单】
□ 核心卖点（1句话说清楚）
□ 社交证明（用户数/评价）
□ 紧迫感（时间/数量限制）
□ 行动号召（明确的CTA）
□ 风险消除（退款保障等）
""")
PYEOF
}

cmd_product() {
    local name="${1:-产品}"; local features="${2:-功能}"
    CW_PRODUCT="$product" CW_AUDIENCE="${audience:-}" CW_NAME="${name:-}" CW_FEATURES="${features:-}" CW_TOPIC="${topic:-}" CW_GOAL="${goal:-转化}" python3 << 'PYEOF'
import os; name = os.environ.get("CW_NAME",""); features = os.environ.get("CW_FEATURES","")
feat_list = [f.strip() for f in features.split(",")]
print(f"""
=== 产品描述文案: {name} ===

【简短版 (50字)】
{name} — 专为[目标用户]设计的[品类]。
{feat_list[0] if feat_list else '核心功能'}，让你[核心价值]。

【标准版 (150字)】
你有没有遇到过[场景痛点]？

{name}就是为解决这个问题而生的。

{"、".join(feat_list[:3]) if len(feat_list)>=3 else features}，
真正做到[差异化价值]。

已有[X]位用户选择了{name}，平均[结果指标]提升[X]%。

立即体验，[具体行动]→

【详细版 (300字)】
**产品简介**
{name}是一款[品类]，专为[目标用户]打造。

**核心功能**
{"".join(chr(10)+"• "+f for f in feat_list)}

**适用场景**
• 当你需要[场景1]
• 当你面对[场景2]
• 当你想要[场景3]

**用户评价**
"[真实用户语录]" — [用户身份]

**立即开始**
[注册/购买/下载] → [链接]
""")
PYEOF
}

cmd_email() {
    local topic="${1:-主题}"; local goal="${2:-转化}"
    CW_PRODUCT="$product" CW_AUDIENCE="${audience:-}" CW_NAME="${name:-}" CW_FEATURES="${features:-}" CW_TOPIC="${topic:-}" CW_GOAL="${goal:-转化}" python3 << 'PYEOF'
import os; topic = os.environ.get("CW_TOPIC",""); goal = os.environ.get("CW_GOAL","转化")
print(f"""
=== 邮件文案: {topic} ===
目标: {goal}

【主题行 (5个变体)】
1. [紧迫] 最后24小时：{topic}特惠即将结束
2. [好奇] 关于{topic}，你可能不知道的事
3. [利益] 用{topic}，3步实现[目标]
4. [个性] [姓名]，你的{topic}报告来了
5. [问题] 你的{topic}遇到这个问题了吗？

【邮件正文框架】
---
嗨 [姓名]，

[开场白 — 共情或引发兴趣，1-2句]

[问题阐述 — 描述他们正面临的挑战，2-3句]

[解决方案 — 你能如何帮助，2-3句]

[社会证明 — 数据或用户案例，1-2句]

[行动号召 — 明确、单一、有紧迫感]
→ [CTA按钮文字]

[签名]

附：[P.S. 强化关键信息或增加紧迫感]
---

【写作技巧】
• 主题行 < 50字符，前15字最关键
• 正文控制在200字以内
• 只有一个CTA
• 移动端预览必做
• 最佳发送时间：周二/周四 上午9-11点
""")
PYEOF
}

cmd_aida() {
    local product="${1:-产品}"
    CW_PRODUCT="$product" CW_AUDIENCE="${audience:-}" CW_NAME="${name:-}" CW_FEATURES="${features:-}" CW_TOPIC="${topic:-}" CW_GOAL="${goal:-转化}" python3 << 'PYEOF'
import os; product = os.environ.get("CW_PRODUCT","")
print(f"""
=== AIDA框架文案: {product} ===

A — ATTENTION (注意) ████████████████████████████████
打破惯性，抓住眼球的第一句话

示例:
• "90%的人都不知道{product}还能这么用"
• "我用{product}3个月，结果让我震惊了"
• "[痛点]?是时候换个方式了"

─────────────────────────────────────

I — INTEREST (兴趣) ████████████████████████████████
让他们想继续读下去

内容要素:
• 揭示他们不知道的信息
• 数据/研究支撑
• 与他们生活的关联
• "你是不是也..."开头

示例:
"我们调查了1000名[目标用户]，发现..."
"使用{product}之前vs之后的真实对比:"

─────────────────────────────────────

D — DESIRE (欲望) ████████████████████████████████
从"有趣"变成"我需要这个"

策略:
• 具体的利益/结果，不是功能
• 画出理想状态的图景
• 消除顾虑（保障、案例）
• FOMO（错过的恐惧）

示例:
"想象一下，当你终于[理想结果]..."
"已经有[X]人实现了[目标]，你也可以"

─────────────────────────────────────

A — ACTION (行动) ████████████████████████████████
清晰、低门槛、有紧迫感的CTA

好的CTA:
✅ 立即免费试用 →
✅ 30秒完成注册 →
✅ 今天领取优惠（仅剩[X]个）→

差的CTA:
❌ 点击这里
❌ 了解更多
❌ 提交
""")
PYEOF
}

cmd_ab() {
    local product="${1:-产品}"
    CW_PRODUCT="$product" CW_AUDIENCE="${audience:-}" CW_NAME="${name:-}" CW_FEATURES="${features:-}" CW_TOPIC="${topic:-}" CW_GOAL="${goal:-转化}" python3 << 'PYEOF'
import os; product = os.environ.get("CW_PRODUCT","")
print(f"""
=== A/B测试文案变体: {product} ===

测试维度1: 开头方式
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
版本A (提问式): "你还在用[旧方式]吗？"
版本B (陈述式): "{product}用户平均节省[X]小时/周"
版本C (故事式): "上个月，我因为[问题]差点..."
版本D (数字式): "3步，10分钟，用{product}搞定[任务]"
版本E (反转式): "别用{product}，除非你想..."

测试维度2: CTA按钮
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
A: 立即开始
B: 免费试用14天
C: 查看演示
D: 获取专属方案
E: 限时领取

测试维度3: 价格呈现
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
A: ¥299/月
B: 每天不到¥10，解锁全功能
C: 省下[X]小时工时，成本早已回本
D: 比竞品便宜40%，功能多2倍

【A/B测试规则】
• 每次只测一个变量
• 最少运行2周，样本≥1000
• 衡量转化率，不是点击率
• 获胜版本继续迭代测试
""")
PYEOF
}

cmd_slogan() {
    local brand="${1:-品牌}"; local values="${2:-效率,简单,专业}"
    CW_BRAND="$brand" CW_VALUES="${values:-效率,简单,专业}" CW_PRODUCT="$product" python3 << 'PYEOF'
import os; brand = os.environ.get("CW_BRAND","品牌")
values = [v.strip() for v in "$values".split(",")]
print(f"""
=== 品牌口号生成: {brand} ===
核心价值: {", ".join(values)}

【口号公式1: 动词+结果】
• 让[痛点]成为过去
• 重新定义[品类]
• [动词]更好的[结果]

【口号公式2: 对比反转】
• 少做，多成
• 不是更努力，是更聪明
• 化繁为简，释放可能

【口号公式3: 身份认同】
• 为[目标用户]而生
• 聪明人的选择
• 不将就的人用{brand}

【基于你的价值观生成】
{"效率" in values and "· 效率至上，" + brand + "帮你找回时间" or ""}
{"简单" in values and "· 简单，就是最好的设计" or ""}
{"专业" in values and "· 专业级工具，人人可用" or ""}

【检验口号的标准】
✅ 10秒内能记住
✅ 说出核心差异
✅ 目标用户能共鸣
✅ 竞品说不了
✅ 翻译成英文仍有力量
""")
PYEOF
}

case "$CMD" in
    ad)      cmd_ad "$@" ;;
    product) cmd_product "$@" ;;
    email)   cmd_email "$@" ;;
    aida)    cmd_aida "$@" ;;
    ab)      cmd_ab "$@" ;;
    slogan)  cmd_slogan "$@" ;;
    help|--help|-h) show_help ;;
    *) echo "Unknown: $CMD"; show_help; exit 1 ;;
esac
