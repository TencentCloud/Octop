#!/usr/bin/env bash
# ad.sh - 广告文案生成器
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

CMD="${1:-help}"
shift 2>/dev/null || true

python3 - "$CMD" "$@" << 'PYTHON_EOF'
# -*- coding: utf-8 -*-
import sys
import random

def show_help():
    print("""
====================================
  广告文案生成器 ad.sh
====================================

用法:
  ad.sh feed "产品" "目标人群"      信息流广告文案（抖音/头条）
  ad.sh search "产品" "关键词"      搜索广告文案（百度/360）
  ad.sh brand "品牌名" "品牌调性"    品牌slogan和文案
  ad.sh moments "产品"              朋友圈广告文案
  ad.sh ab-test "产品"              A/B测试文案对（5对对照+测试建议）
  ad.sh roi "预算" "单价" "转化率"   ROI计算器（投入产出比+盈亏平衡）
  ad.sh platform "产品" "平台"      平台适配文案（抖音/微信/百度/Google）
  ad.sh help                       显示本帮助

示例:
  ad.sh feed "美白面膜" "25-35岁女性"
  ad.sh search "英语培训" "成人英语,零基础"
  ad.sh brand "花西子" "国风,高端,东方美学"
  ad.sh moments "智能手表"
  ad.sh ab-test "蓝牙耳机"
  ad.sh roi "10000" "99" "3"
  ad.sh platform "面膜" "抖音"
  ad.sh platform "英语课" "百度"
""")

def gen_feed(product, audience):
    print("=" * 50)
    print("  信息流广告文案 - {}".format(product))
    print("  目标人群: {}".format(audience))
    print("=" * 50)
    print("")

    # 抖音风格
    print("📱 【抖音信息流】")
    print("")

    douyin_hooks = [
        "还在为{product}踩雷？{audience}都在用这款！",
        "{audience}注意了！这款{product}我后悔没早买！",
        "被{audience}疯抢的{product}，到底有多好用？",
        "闺蜜推荐的{product}，{audience}用了都说绝！",
        "刷到就是赚到！{audience}必入的{product}来了！",
    ]

    for i in range(3):
        hook = random.choice(douyin_hooks).format(product=product, audience=audience)
        print("  方案{}:".format(i + 1))
        print("  标题: {}".format(hook))
        bodies = [
            "✅ 亲测有效，用了{product}之后再也回不去了\n    ✅ {audience}专属福利，限时特价\n    ✅ 已有10万+人验证，好评率99%\n    👉 点击下方链接，立即抢购！".format(product=product, audience=audience),
            "💡 {audience}都在找的{product}终于来了！\n    🔥 今天下单立减50元\n    📦 顺丰包邮，48小时发货\n    ⏰ 限时活动，手慢无！".format(product=product, audience=audience),
            "🌟 为什么{audience}都选这款{product}？\n    1. 效果看得见，3天就有变化\n    2. 大牌品质，平价价格\n    3. 无理由退换，零风险尝试\n    👇 现在就试试！".format(product=product, audience=audience),
        ]
        print("  正文:\n    {}".format(bodies[i]))
        print("")
        print("  -" * 25)
        print("")

    # 头条风格
    print("📰 【今日头条信息流】")
    print("")

    toutiao_templates = [
        {
            "title": "{audience}都在用的{product}，原来秘密在这里".format(product=product, audience=audience),
            "desc": "专家推荐，{audience}首选{product}。科学配方/工艺，效果经过权威验证。现在购买享受新客专属优惠，限量500份，抢完即止。".format(product=product, audience=audience),
        },
        {
            "title": "这款{product}在{audience}中火了，日销10000+".format(product=product, audience=audience),
            "desc": "不打广告不刷单，靠真实口碑做到品类TOP1。{audience}实测反馈超好评，现在入手正当时。首单立减，还送精美赠品！".format(product=product, audience=audience),
        },
        {
            "title": "{audience}如何选{product}？看完这篇就够了".format(product=product, audience=audience),
            "desc": "选{product}最怕踩雷，行业人士教你3个核心指标。{audience}按这个标准选，闭眼入都不会错。文末有独家优惠码！".format(product=product, audience=audience),
        },
    ]

    for i, t in enumerate(toutiao_templates):
        print("  方案{}:".format(i + 1))
        print("  标题: {}".format(t["title"]))
        print("  描述: {}".format(t["desc"]))
        print("")

    print("-" * 50)
    print("💡 信息流广告技巧:")
    print("  - 前3秒/前15字决定点击率")
    print("  - 用数字增加可信度（10万+、99%）")
    print("  - 制造紧迫感（限时、限量）")
    print("  - A/B测试不同标题，找到最优解")

def gen_search(product, keywords_str):
    keywords = [k.strip() for k in keywords_str.split(",") if k.strip()]

    print("=" * 50)
    print("  搜索广告文案 - {}".format(product))
    print("  关键词: {}".format(", ".join(keywords)))
    print("=" * 50)
    print("")

    # 百度搜索广告
    print("🔍 【百度搜索广告】")
    print("")

    for i in range(3):
        kw = keywords[i % len(keywords)]
        titles = [
            "{product}-{kw}「官方正品」限时优惠中".format(product=product, kw=kw),
            "{kw}就选{product} | 品质保障 | 售后无忧".format(product=product, kw=kw),
            "{product}_{kw}_口碑之选 | 今日下单立享8折".format(product=product, kw=kw),
        ]
        descs = [
            "{product}，专注{kw}领域多年。品牌直营，正品保障，全国包邮。现在咨询享专属优惠！".format(product=product, kw=kw),
            "寻找靠谱的{product}？我们专业提供{kw}服务/产品，已服务10万+客户，好评率98%。立即了解详情！".format(product=product, kw=kw),
            "{kw}首选{product}！行业领先品质，价格透明公道。在线咨询免费获取报价方案。".format(product=product, kw=kw),
        ]
        print("  创意{}:".format(i + 1))
        print("  标题: {}".format(titles[i]))
        print("  描述: {}".format(descs[i]))
        print("  显示URL: www.xxx.com/{}".format(product))
        print("")

    # 360搜索广告
    print("🔍 【360搜索广告】")
    print("")

    for i in range(2):
        kw = keywords[i % len(keywords)]
        print("  创意{}:".format(i + 1))
        print("  标题: {product} | {kw} | 厂家直销价格更优".format(product=product, kw=kw))
        print("  描述: {product}，{kw}行业标杆。高品质低价格，厂家直销省去中间环节。支持定制，量大从优。立即咨询获取最新报价！".format(product=product, kw=kw))
        print("")

    print("-" * 50)
    print("💡 搜索广告技巧:")
    print("  - 标题必须包含核心关键词")
    print("  - 描述中自然融入2-3个关键词")
    print("  - 使用行动号召语（立即、马上、今日）")
    print("  - 突出差异化卖点和促销信息")
    print("  - 标题建议28字以内，描述80字以内")

def gen_brand(brand_name, tone_str):
    tones = [t.strip() for t in tone_str.split(",") if t.strip()]

    print("=" * 50)
    print("  品牌文案 - {}".format(brand_name))
    print("  品牌调性: {}".format(", ".join(tones)))
    print("=" * 50)
    print("")

    # Slogan
    print("📌 【品牌Slogan】")
    print("")
    slogans = [
        "{brand}，让{tone}触手可及".format(brand=brand_name, tone=tones[0] if tones else "美好"),
        "{tone}生活，{brand}定义".format(brand=brand_name, tone=tones[0] if tones else "品质"),
        "{brand} | 源于{tone}，忠于品质".format(brand=brand_name, tone=tones[0] if tones else "匠心"),
        "选择{brand}，选择{tone}".format(brand=brand_name, tone=tones[0] if tones else "卓越"),
        "{brand}，{tone}不止一面".format(brand=brand_name, tone=tones[-1] if tones else "精彩"),
        "{tone}之上，{brand}之选".format(brand=brand_name, tone=tones[0] if tones else "品质"),
    ]
    for i, s in enumerate(slogans):
        print("  Slogan {}: {}".format(i + 1, s))
    print("")

    # 品牌故事
    print("📖 【品牌故事】")
    print("")
    tone_desc = "、".join(tones) if tones else "品质"
    stories = [
        "  {brand}，诞生于对{tone}的执着追求。\n  我们相信，好的产品不需要过多修饰——它本身就是最好的语言。\n  从第一天起，{brand}就坚持用{tone}的标准要求自己，\n  每一个细节、每一次创新，都源于对用户最深的敬意。\n  {brand}，不只是一个品牌，更是一种生活态度。".format(brand=brand_name, tone=tone_desc),
        "  当{tone}成为一种信仰，{brand}应运而生。\n  我们不追随潮流，我们创造经典。\n  每一件产品都凝聚着匠人的心血，\n  每一次服务都传递着{tone}的温度。\n  选择{brand}，就是选择与众不同的品质人生。".format(brand=brand_name, tone=tone_desc),
    ]
    for i, story in enumerate(stories):
        print("  版本{}:".format(i + 1))
        print(story)
        print("")

    # 品牌宣言
    print("📢 【品牌宣言】")
    print("")
    manifestos = [
        "  我们是{brand}。\n  我们相信{tone}的力量。\n  我们用产品说话，用品质证明。\n  每一个选择{brand}的人，\n  都在为更好的生活投票。".format(brand=brand_name, tone=tone_desc),
        "  {brand}，为{tone}而生。\n  不将就，不妥协，不跟风。\n  我们只做一件事：\n  把{tone}融入生活的每一个瞬间。".format(brand=brand_name, tone=tone_desc),
    ]
    for i, m in enumerate(manifestos):
        print("  版本{}:".format(i + 1))
        print(m)
        print("")

    print("-" * 50)
    print("💡 品牌文案建议:")
    print("  - Slogan简短有力，易于传播")
    print("  - 品牌故事要有情感共鸣")
    print("  - 保持调性一致，所有物料统一风格")
    print("  - 好的品牌文案要能引发用户自我认同")

def gen_moments(product):
    print("=" * 50)
    print("  朋友圈广告文案 - {}".format(product))
    print("=" * 50)
    print("")

    # 朋友圈广告 - 图文
    print("📱 【朋友圈图文广告】")
    print("")

    ad_templates = [
        {
            "style": "种草型",
            "text": "被安利了这款{product}，本来没抱希望…结果？真香！用了之后才知道，好东西果然是要亲自试的。姐妹们冲！".format(product=product),
            "cta": "了解更多 →",
        },
        {
            "style": "故事型",
            "text": "上个月朋友送了我一个{product}，当时觉得普普通通。用了一个月后……我又自己买了两个送人😂 这大概就是真正好产品的魔力吧".format(product=product),
            "cta": "立即体验 →",
        },
        {
            "style": "痛点型",
            "text": "你是不是也有这样的困扰？试了很多{product}都不满意，不是太贵就是效果一般。直到遇到它——终于不用再纠结了！".format(product=product),
            "cta": "马上看看 →",
        },
        {
            "style": "数据型",
            "text": "100万人都在用的{product}，到底好在哪？\n✅ 好评率99.2%\n✅ 复购率超60%\n✅ 明星同款\n好东西不需要解释，数据会说话。".format(product=product),
            "cta": "查看详情 →",
        },
        {
            "style": "限时型",
            "text": "🔥 {product}年度最大福利来了！\n💰 直降100元，到手价仅需XXX\n🎁 前500名再送精美礼盒\n⏰ 活动仅剩最后3天！\n手慢真的无！".format(product=product),
            "cta": "立即抢购 →",
        },
    ]

    for i, ad in enumerate(ad_templates):
        print("  方案{} [{}]:".format(i + 1, ad["style"]))
        print("  文案: {}".format(ad["text"]))
        print("  按钮: {}".format(ad["cta"]))
        print("")
        print("  -" * 25)
        print("")

    # 朋友圈广告 - 视频
    print("🎬 【朋友圈视频广告脚本】")
    print("")
    print("  6秒版本:")
    print("  [画面] {product}特写 → 使用场景 → Logo".format(product=product))
    print("  [文字] 好物推荐 | {product}".format(product=product))
    print("  [配乐] 轻快BGM")
    print("")
    print("  15秒版本:")
    print("  [0-3秒] 痛点场景：展示没有{product}的困扰".format(product=product))
    print("  [3-8秒] 产品展示：{product}外观、质感、细节".format(product=product))
    print("  [8-12秒] 使用效果：使用前后对比")
    print("  [12-15秒] 行动号召：限时优惠+品牌Logo")
    print("")

    print("-" * 50)
    print("💡 朋友圈广告技巧:")
    print("  - 文案要像朋友分享，不要像硬广")
    print("  - 第一句话决定用户是否展开阅读")
    print("  - 图片/视频质感要高，避免廉价感")
    print("  - CTA按钮文案要有行动力")
    print("  - 定向投放比文案更重要")

def gen_ab_test(product):
    print("=" * 60)
    print("  A/B测试文案对 - {}".format(product))
    print("=" * 60)
    print("")

    test_pairs = [
        {
            "dimension": "标题风格：疑问式 vs 陈述式",
            "variable": "标题句式",
            "a_title": "你还不知道这款{}？难怪效果不好！".format(product),
            "b_title": "这款{}已帮助10万人解决问题，效果显著！".format(product),
            "hypothesis": "疑问句激发好奇心，可能提高点击率；陈述句提供确定性，可能提高转化率",
        },
        {
            "dimension": "痛点 vs 利益",
            "variable": "文案切入角度",
            "a_title": "还在为{}踩雷？3个坑你一定要避开！".format(product),
            "b_title": "用了这款{}，生活质量直线上升！".format(product),
            "hypothesis": "痛点切入引发焦虑促行动，利益切入传递正面情绪促分享",
        },
        {
            "dimension": "价格锚点：原价对比 vs 单位价格",
            "variable": "价格呈现方式",
            "a_title": "{}原价¥299，今日特惠仅¥99！直降200！".format(product),
            "b_title": "{}每天只要0.3元，一杯水的钱换全新体验！".format(product),
            "hypothesis": "原价对比适合高客单价，每日均摊适合需要降低心理门槛的产品",
        },
        {
            "dimension": "社交证明：数据型 vs 故事型",
            "variable": "信任建立方式",
            "a_title": "{}累计销量100万+，好评率99.2%！".format(product),
            "b_title": "她用了这款{}三个月，从此再没换过其他品牌".format(product),
            "hypothesis": "数据型适合理性决策品类，故事型适合感性消费品类",
        },
        {
            "dimension": "紧迫感：限时 vs 限量",
            "variable": "紧迫感类型",
            "a_title": "{}限时特惠！倒计时3小时，过期恢复原价！".format(product),
            "b_title": "{}限量500件！已抢购467件，仅剩33件！".format(product),
            "hypothesis": "限时适合促进即时行动，限量适合制造稀缺感和FOMO心理",
        },
    ]

    for i, pair in enumerate(test_pairs, 1):
        print("━" * 60)
        print("测试对 {} | 测试维度: {}".format(i, pair["dimension"]))
        print("测试变量: {}".format(pair["variable"]))
        print("━" * 60)
        print("")
        print("  🅰️ 版本A:")
        print("  「{}」".format(pair["a_title"]))
        print("")
        print("  🅱️ 版本B:")
        print("  「{}」".format(pair["b_title"]))
        print("")
        print("  📊 测试假设:")
        print("  {}".format(pair["hypothesis"]))
        print("")

    print("=" * 60)
    print("📋 【A/B测试执行指南】")
    print("=" * 60)
    print("")
    print("  1️⃣ 测试设置:")
    print("     · 每次只测试一个变量，其他条件保持一致")
    print("     · 流量分配：50%/50%随机分配")
    print("     · 测试时长：至少3-7天，覆盖工作日+周末")
    print("     · 最低样本量：每组至少1000次展示")
    print("")
    print("  2️⃣ 关注指标:")
    print("     · 点击率(CTR): A/B文案哪个更吸引点击")
    print("     · 转化率(CVR): 点击后哪个更促进购买")
    print("     · 单次转化成本(CPA): 哪个获客成本更低")
    print("     · ROI: 最终哪个投入产出比更高")
    print("")
    print("  3️⃣ 结果判定:")
    print("     · 置信度≥95%才可判定胜出")
    print("     · CTR差异<5%视为无显著差异")
    print("     · 胜出方案全量投放，再测试新变量")
    print("")
    print("  4️⃣ 迭代建议:")
    print("     · 先测大方向（痛点vs利益），再测细节（用词/数字）")
    print("     · 每两周迭代一次，持续优化")
    print("     · 记录所有测试结果，形成品牌专属文案知识库")


def gen_roi(budget_str, unit_price_str, conv_rate_str):
    print("=" * 60)
    print("  广告ROI计算器")
    print("=" * 60)
    print("")

    try:
        budget = float(budget_str)
        unit_price = float(unit_price_str)
        conv_rate = float(conv_rate_str) / 100.0
    except (ValueError, TypeError):
        print("错误: 请输入有效数字")
        print("用法: ad.sh roi \"预算\" \"产品单价\" \"转化率(%)\"")
        sys.exit(1)

    # 假设CPM和CPC
    cpm_range = [(15, "低竞争行业"), (35, "中等竞争"), (60, "高竞争行业")]
    cpc_range = [(0.5, "低"), (1.5, "中"), (3.0, "高")]

    print("📊 【投放参数】")
    print("  广告预算: ¥{:,.0f}".format(budget))
    print("  产品单价: ¥{:,.0f}".format(unit_price))
    print("  预估转化率: {:.1f}%".format(conv_rate * 100))
    print("")

    print("📈 【ROI测算（三种场景）】")
    print("")

    scenarios = [
        {"name": "乐观场景", "cpc": 0.5, "ctr": 0.03},
        {"name": "中等场景", "cpc": 1.5, "ctr": 0.015},
        {"name": "保守场景", "cpc": 3.0, "ctr": 0.008},
    ]

    for sc in scenarios:
        clicks = int(budget / sc["cpc"])
        orders = int(clicks * conv_rate)
        revenue = orders * unit_price
        profit_margin = 0.30  # 假设30%利润率
        gross_profit = revenue * profit_margin
        roi = (revenue - budget) / budget * 100 if budget > 0 else 0
        net_roi = (gross_profit - budget) / budget * 100 if budget > 0 else 0
        cpa = budget / orders if orders > 0 else float('inf')
        break_even_orders = int(budget / (unit_price * profit_margin)) + 1 if unit_price * profit_margin > 0 else 0
        break_even_rate = (break_even_orders / clicks * 100) if clicks > 0 else 0

        print("  ┌─ {} (CPC=¥{:.1f}) ─────────────────────┐".format(sc["name"], sc["cpc"]))
        print("  │")
        print("  │  点击量: {:,} 次".format(clicks))
        print("  │  预估订单: {:,} 单".format(orders))
        print("  │  预估收入: ¥{:,.0f}".format(revenue))
        print("  │  毛利润(30%): ¥{:,.0f}".format(gross_profit))
        print("  │")
        print("  │  💰 GMV ROI: {:.1f}% ({})".format(
            roi, "盈利 ✅" if roi > 0 else "亏损 ❌"))
        print("  │  💰 净利ROI: {:.1f}% ({})".format(
            net_roi, "盈利 ✅" if net_roi > 0 else "亏损 ❌"))
        print("  │  📊 单客获取成本(CPA): ¥{:.1f}".format(cpa if cpa != float('inf') else 0))
        print("  │")
        print("  │  ⚖️ 盈亏平衡点: {}单 (转化率需≥{:.2f}%)".format(
            break_even_orders, break_even_rate))
        print("  │")
        print("  └──────────────────────────────────────────┘")
        print("")

    # 优化建议
    print("🔧 【优化建议】")
    print("")
    if conv_rate < 0.02:
        print("  ⚠️ 转化率偏低({:.1f}%)，建议:".format(conv_rate * 100))
        print("    · 优化落地页，缩短转化路径")
        print("    · 增加信任元素（评价/认证/担保）")
        print("    · 测试不同的CTA按钮文案")
        print("    · 检查目标人群是否精准")
    elif conv_rate < 0.05:
        print("  📊 转化率中等({:.1f}%)，建议:".format(conv_rate * 100))
        print("    · 优化广告文案，提高点击质量")
        print("    · 做A/B测试找到最优文案")
        print("    · 优化投放时段和人群定向")
    else:
        print("  ✅ 转化率较好({:.1f}%)，建议:".format(conv_rate * 100))
        print("    · 逐步放大预算，观察边际效益")
        print("    · 拓展新的投放渠道")
        print("    · 优化CPC降低获客成本")
    print("")
    print("  💡 ROI提升公式: 降CPC + 提转化率 + 提客单价")
    print("  💡 健康ROI: GMV ROI>200%, 净利ROI>30%")


def gen_platform(product, platform):
    print("=" * 60)
    print("  平台适配文案 - {} | 平台: {}".format(product, platform))
    print("=" * 60)
    print("")

    plat = platform.lower().replace(" ", "")

    if "抖音" in plat or "douyin" in plat or "tiktok" in plat:
        print("📱 【抖音/巨量引擎 广告文案】")
        print("")
        print("  平台特点: 短视频+直播，用户注意力短，前3秒决胜")
        print("  投放形式: 信息流视频广告、DOU+、千川投流")
        print("  目标: 完播率>35%，互动率>5%，转化率>2%")
        print("")
        print("  📝 视频脚本框架 (15-30秒):")
        print("")
        print("  [0-3秒] 钩子/Hook（决定用户是否停下来）")
        hooks = [
            "「家人们！这款{}我后悔没早买！」".format(product),
            "「被骗了这么多年，原来{}要这样选！」".format(product),
            "「月薪3000也能用上好{}！」".format(product),
            "「闺蜜推荐的{}，用完我直接下单了3个！」".format(product),
            "「{}选贵的不如选对的！看完你就懂了」".format(product),
        ]
        for i, h in enumerate(hooks, 1):
            print("    Hook{}: {}".format(i, h))
        print("")
        print("  [3-15秒] 产品展示+痛点+卖点")
        print("    · 快速展示产品外观和使用场景")
        print("    · 突出1-2个核心卖点（不要贪多）")
        print("    · 用对比/测试增加可信度")
        print("")
        print("  [15-25秒] 价格+福利")
        print("    · 揭晓价格，制造惊喜感")
        print("    · 强调限时/限量优惠")
        print("")
        print("  [最后3秒] CTA行动号召")
        ctas = [
            "「点击下方小黄车，立即抢购！」",
            "「点击左下角链接，领券下单更划算！」",
            "「想要的宝子评论区扣1，我发链接给你！」",
        ]
        for c in ctas:
            print("    {}".format(c))
        print("")
        print("  📊 投放建议:")
        print("    · 单条视频预算: ¥300-1000/天测试")
        print("    · 测试期3天，ROI>1.5再加预算")
        print("    · 定向: 兴趣标签+相似达人粉丝+智能推荐")

    elif "微信" in plat or "wechat" in plat or "朋友圈" in plat:
        print("💬 【微信/朋友圈 广告文案】")
        print("")
        print("  平台特点: 社交属性强，信任度高，用户偏私域")
        print("  投放形式: 朋友圈广告、公众号广告、视频号广告")
        print("  目标: 点击率>1.5%，加粉率>3%，转化率>1%")
        print("")
        print("  📝 朋友圈广告文案 (原生感/像朋友分享):")
        print("")
        ads = [
            {
                "style": "种草型",
                "text": "最近被安利了一款{}，本来没抱啥期待…结果？真香警告！已经推荐给3个朋友了，她们都说好😂".format(product),
                "img": "日常使用场景图（非棚拍，要有生活感）",
            },
            {
                "style": "对话型",
                "text": "朋友问我最近气色怎么变好了，我说可能是换了这个{}吧（小声bb）感觉整个人都不一样了".format(product),
                "img": "自拍/生活照风格，带产品露出",
            },
            {
                "style": "干货型",
                "text": "做了3年{}功课，总结出这个选购公式：看XX+看XX+看XX。按这个标准选，闭眼入都不会错👇".format(product),
                "img": "图文并茂的选购指南图",
            },
        ]
        for i, ad in enumerate(ads, 1):
            print("  方案{}[{}]:".format(i, ad["style"]))
            print("  文案: {}".format(ad["text"]))
            print("  配图: {}".format(ad["img"]))
            print("")
        print("  📊 投放建议:")
        print("    · 定向: 地域+年龄+兴趣标签+行为定向")
        print("    · 文案像朋友分享，不像广告")
        print("    · 落地页用小程序，转化路径最短")
        print("    · 配合公众号内容，提高信任度")

    elif "百度" in plat or "baidu" in plat:
        print("🔍 【百度搜索 广告文案】")
        print("")
        print("  平台特点: 用户有明确搜索意图，转化意向最强")
        print("  投放形式: 搜索竞价(SEM)、信息流、知识营销")
        print("  目标: 点击率>5%，转化率>3%，质量度≥8")
        print("")
        print("  📝 搜索广告创意 (标题28字+描述80字):")
        print("")
        creatives = [
            {
                "kw": "{}哪个好".format(product),
                "title": "{}-2024热销排行榜「官方正品」限时8折".format(product),
                "desc": "精选{}TOP10品牌，品质保障价格透明。10万+用户选择，好评率99%。今日下单享专属优惠，支持7天无理由退换！".format(product),
            },
            {
                "kw": "{}多少钱".format(product),
                "title": "{}价格查询_厂家直销_省去中间商差价".format(product),
                "desc": "{}工厂直营，同品质价格低至5折。支持批发零售，量大从优。在线获取最新报价，免费包邮到家！".format(product),
            },
            {
                "kw": "{}品牌推荐".format(product),
                "title": "2024{}品牌推荐_专业评测_买前必看".format(product),
                "desc": "资深行业人士亲测推荐，{}选购不踩雷。从材质到功能全面对比，帮你找到最适合的那一款。立即查看→".format(product),
            },
        ]
        for i, c in enumerate(creatives, 1):
            print("  创意{} (关键词: {}):".format(i, c["kw"]))
            print("  标题: {} ({}字)".format(c["title"], len(c["title"])))
            print("  描述: {} ({}字)".format(c["desc"], len(c["desc"])))
            print("")
        print("  📊 投放建议:")
        print("    · 核心词出价高，长尾词出价低")
        print("    · 标题必须包含搜索关键词（提高质量度）")
        print("    · 用否定关键词排除无效流量")
        print("    · 分时段投放：工作日上午+晚间效果最佳")

    elif "google" in plat or "谷歌" in plat:
        print("🌐 【Google Ads 广告文案】")
        print("")
        print("  平台特点: 全球覆盖，适合跨境/出海，用户搜索意图明确")
        print("  投放形式: Search Ads, Display, Shopping, YouTube")
        print("  目标: CTR>3%, Conversion Rate>2%, Quality Score≥7")
        print("")
        print("  📝 Google Search Ads (Headlines 30chars + Descriptions 90chars):")
        print("")
        google_ads = [
            {
                "headline1": "Best {} - 50% Off Today".format(product),
                "headline2": "Free Shipping | Top Rated",
                "headline3": "Limited Time Offer - Shop Now",
                "desc1": "Discover premium {} at unbeatable prices. Rated 4.8/5 by 10,000+ customers. Order now and get free express shipping!".format(product),
                "desc2": "Why pay more? Get the same quality {} at half the price. 30-day money-back guarantee. Shop with confidence today!".format(product),
            },
            {
                "headline1": "{} Sale - Up to 60% Off".format(product),
                "headline2": "Trusted by 100K+ Customers",
                "headline3": "30-Day Money Back Guarantee",
                "desc1": "Premium {} direct from manufacturer. No middleman markup. Same quality, better price. Free returns within 30 days.".format(product),
                "desc2": "Looking for the best {}? Compare top brands, read real reviews, and find your perfect match. Special online-only pricing!".format(product),
            },
        ]
        for i, ad in enumerate(google_ads, 1):
            print("  Ad Group {}:".format(i))
            print("  H1: {} ({} chars)".format(ad["headline1"], len(ad["headline1"])))
            print("  H2: {} ({} chars)".format(ad["headline2"], len(ad["headline2"])))
            print("  H3: {} ({} chars)".format(ad["headline3"], len(ad["headline3"])))
            print("  D1: {} ({} chars)".format(ad["desc1"], len(ad["desc1"])))
            print("  D2: {} ({} chars)".format(ad["desc2"], len(ad["desc2"])))
            print("")
        print("  📊 Optimization Tips:")
        print("    · Use Responsive Search Ads (RSA) with 10+ headlines")
        print("    · Include keywords in headlines for relevance")
        print("    · Add sitelink, callout, and structured snippet extensions")
        print("    · Set up conversion tracking before spending budget")
        print("    · Start with exact match, expand to phrase match after data")

    else:
        print("📢 【{} 平台广告文案】".format(platform))
        print("")
        print("  ⚠️ 暂无「{}」的专属模板".format(platform))
        print("")
        print("  已支持的平台:")
        print("    · 抖音/巨量引擎 — ad.sh platform \"{}\" \"抖音\"".format(product))
        print("    · 微信/朋友圈   — ad.sh platform \"{}\" \"微信\"".format(product))
        print("    · 百度搜索      — ad.sh platform \"{}\" \"百度\"".format(product))
        print("    · Google Ads    — ad.sh platform \"{}\" \"Google\"".format(product))
        print("")
        print("  通用文案原则:")
        print("    · 了解平台用户画像和内容偏好")
        print("    · 适配平台的文案长度和格式限制")
        print("    · 使用平台原生的表达风格")
        print("    · 跟踪平台算法变化调整策略")

    print("")
    print("-" * 60)
    print("💡 跨平台投放黄金法则:")
    print("  - 同一产品在不同平台要用不同的文案风格")
    print("  - 抖音重「内容感」，微信重「社交感」，百度重「搜索相关性」")
    print("  - 先单平台测试跑通ROI，再多平台扩量")
    print("  - 各平台数据要统一追踪，用UTM参数区分来源")


def main():
    args = sys.argv[1:]
    if not args:
        show_help()
        return

    cmd = args[0]

    if cmd == "help":
        show_help()
    elif cmd == "feed":
        if len(args) < 3:
            print("用法: ad.sh feed \"产品\" \"目标人群\"")
            sys.exit(1)
        gen_feed(args[1], args[2])
    elif cmd == "search":
        if len(args) < 3:
            print("用法: ad.sh search \"产品\" \"关键词\"")
            sys.exit(1)
        gen_search(args[1], args[2])
    elif cmd == "brand":
        if len(args) < 3:
            print("用法: ad.sh brand \"品牌名\" \"品牌调性\"")
            sys.exit(1)
        gen_brand(args[1], args[2])
    elif cmd == "moments":
        if len(args) < 2:
            print("用法: ad.sh moments \"产品\"")
            sys.exit(1)
        gen_moments(args[1])
    elif cmd == "ab-test":
        if len(args) < 2:
            print("用法: ad.sh ab-test \"产品\"")
            sys.exit(1)
        gen_ab_test(args[1])
    elif cmd == "roi":
        if len(args) < 4:
            print("用法: ad.sh roi \"预算\" \"产品单价\" \"转化率(%)\"")
            print("示例: ad.sh roi \"10000\" \"99\" \"3\"")
            sys.exit(1)
        gen_roi(args[1], args[2], args[3])
    elif cmd == "platform":
        if len(args) < 3:
            print("用法: ad.sh platform \"产品\" \"平台\"")
            print("支持平台: 抖音, 微信, 百度, Google")
            sys.exit(1)
        gen_platform(args[1], args[2])
    else:
        print("未知命令: {}".format(cmd))
        print("运行 ad.sh help 查看帮助")
        sys.exit(1)

if __name__ == "__main__":
    main()
PYTHON_EOF

echo ""
echo "  Powered by BytesAgain | bytesagain.com | hello@bytesagain.com"
