#!/usr/bin/env bash
# taobao.sh - 淘宝商品标题和详情页文案生成器
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

CMD="${1:-help}"
shift 2>/dev/null || true

python3 - "$CMD" "$@" << 'PYTHON_EOF'
# -*- coding: utf-8 -*-
import sys
import random
import datetime

def show_help():
    print("""
====================================
  淘宝商品文案生成器 taobao.sh
====================================

用法:
  taobao.sh title "产品名" "关键词1,关键词2"   生成淘宝爆款标题（30字内）
  taobao.sh selling-point "产品名"             五大卖点提炼
  taobao.sh detail "产品名" ["材质,尺寸,功能"]  详情页文案（卖点+场景+信任+促销）
  taobao.sh review-reply "评价内容"             评价回复话术
  taobao.sh keyword "产品名"                   关键词挖掘（核心词+长尾词+属性词+热搜词）
  taobao.sh promotion "活动类型"               促销文案（双11/618/聚划算/日常促销）
  taobao.sh help                               显示本帮助

示例:
  taobao.sh title "蓝牙耳机" "降噪,运动,长续航"
  taobao.sh selling-point "蓝牙耳机"
  taobao.sh detail "蓝牙耳机" "ABS材质,入耳式,主动降噪"
  taobao.sh detail "蓝牙耳机"
  taobao.sh review-reply "音质不错，就是续航短了点"
  taobao.sh keyword "蓝牙耳机"
  taobao.sh promotion "双11"
  taobao.sh promotion "618"
  taobao.sh promotion "聚划算"
""")

def gen_title(product, keywords_str):
    keywords = [k.strip() for k in keywords_str.split(",") if k.strip()]
    prefixes = ["【爆款推荐】", "【热销榜单】", "【品质之选】", "【限时特惠】", "【新品首发】", "【TOP1爆款】"]
    modifiers = ["正品", "新款", "升级版", "旗舰", "加强版", "热卖", "必备"]
    suffixes = ["包邮", "送运费险", "顺丰包邮", "7天无理由", "当日发货"]

    print("=" * 50)
    print("  淘宝爆款标题生成 - {}".format(product))
    print("=" * 50)
    print("")
    print("关键词: {}".format(", ".join(keywords)))
    print("")

    for i in range(5):
        prefix = random.choice(prefixes)
        mod = random.choice(modifiers)
        kw_sample = random.sample(keywords, min(len(keywords), random.randint(1, max(1, len(keywords)))))
        suffix = random.choice(suffixes)
        title = "{prefix}{product}{mod} {kws} {suffix}".format(
            prefix=prefix, product=product, mod=mod,
            kws=" ".join(kw_sample), suffix=suffix
        )
        # 淘宝标题限30字，去掉多余
        if len(title) > 30:
            title = title[:30]
        print("标题{num}: {title}".format(num=i+1, title=title))
        print("  字数: {n}字".format(n=len(title)))
        print("")

    print("💡 技巧提示:")
    print("  - 核心关键词放前面，长尾词放后面")
    print("  - 避免重复词，每个字都要有搜索价值")
    print("  - 标题不超过30个字（含标点）")

def gen_selling_points(product):
    categories = [
        {"name": "品质保障", "templates": [
            "{product}精选优质原料，品质看得见",
            "严格质检，{product}每一件都经得起考验",
            "大牌同厂同质，{product}品质有保障",
        ]},
        {"name": "功能亮点", "templates": [
            "{product}多功能设计，一物多用更实用",
            "创新升级，{product}使用体验全面提升",
            "核心技术加持，{product}性能远超同价位",
        ]},
        {"name": "用户体验", "templates": [
            "{product}人体工学设计，舒适度拉满",
            "操作简单，{product}老人小孩都能轻松使用",
            "贴心细节设计，{product}处处为你着想",
        ]},
        {"name": "性价比", "templates": [
            "工厂直发，{product}省去中间商差价",
            "同品质中价格最优，{product}真正物超所值",
            "买到就是赚到，{product}超高性价比之选",
        ]},
        {"name": "售后服务", "templates": [
            "{product}7天无理由退换，购物零风险",
            "专业客服团队，{product}售后无忧",
            "质量问题免费换新，{product}买得放心用得安心",
        ]},
    ]

    print("=" * 50)
    print("  五大卖点提炼 - {}".format(product))
    print("=" * 50)
    print("")

    for idx, cat in enumerate(categories):
        template = random.choice(cat["templates"])
        point = template.format(product=product)
        print("卖点{num} [{cat}]".format(num=idx+1, cat=cat["name"]))
        print("  ✅ {}".format(point))
        print("")

    print("-" * 50)
    print("📋 卖点使用建议:")
    print("  - 主图上突出卖点1-2")
    print("  - 详情页依次展开5个卖点")
    print("  - 每个卖点配合实拍图/对比图更有说服力")

def gen_detail(product, attrs_str=""):
    attrs = [a.strip() for a in attrs_str.split(",") if a.strip()] if attrs_str else []

    print("=" * 50)
    print("  详情页文案 - {}".format(product))
    print("=" * 50)
    print("")

    # 开场引导
    print("【开场引导】")
    hooks = [
        "还在为选择{product}而纠结？看完这篇你就知道该怎么选！",
        "一款好的{product}，到底好在哪里？往下看就知道了！",
        "为什么10万+买家都选择了这款{product}？答案就在详情里！",
    ]
    print("  {}".format(random.choice(hooks).format(product=product)))
    print("")

    # 产品属性（如果提供了）
    if attrs:
        print("【产品参数】")
        print("  产品名称: {}".format(product))
        for attr in attrs:
            print("  · {}".format(attr))
        print("")

    # ===== 升级：卖点提炼 =====
    print("【核心卖点提炼】")
    selling_modules = [
        {"icon": "🏆", "title": "品质保障", "points": [
            "精选优质原材料，源头品控",
            "通过国家权威检测认证",
            "大牌同厂同线，品质看得见",
        ]},
        {"icon": "⚡", "title": "功能亮点", "points": [
            "创新技术加持，体验全面升级",
            "多功能合一，一物多用更省心",
            "核心性能远超同价位竞品",
        ]},
        {"icon": "💎", "title": "细节设计", "points": [
            "人体工学设计，舒适度拉满",
            "每个细节反复打磨，匠心品质",
            "包装精美，自用送人两相宜",
        ]},
    ]
    for mod in selling_modules:
        print("  {icon} {title}".format(icon=mod["icon"], title=mod["title"]))
        point = random.choice(mod["points"])
        print("    → {}的{}，{}".format(product, mod["title"].lower(), point))
        print("")

    # ===== 升级：场景描述 =====
    print("【使用场景】")
    scenes = [
        {"scene": "居家日常", "desc": "在家使用{product}，享受舒适便捷的生活体验。无论是独处还是与家人共享，都能感受到它带来的品质提升。"},
        {"scene": "办公通勤", "desc": "上班族的必备好物！{product}陪你从早忙到晚，高效又省心，同事都问你哪里买的。"},
        {"scene": "出行旅游", "desc": "出门在外也少不了{product}，轻便易携，随时随地都能用。旅途中的贴心伴侣，让出行更加从容。"},
        {"scene": "送礼佳选", "desc": "精美包装+实用品质，{product}作为礼物送人特别有面子。收到的人都会夸你眼光好！"},
    ]
    for s in scenes:
        print("  🎯 {} | {}".format(s["scene"], s["desc"].format(product=product)))
        print("")

    # ===== 升级：信任背书 =====
    print("【信任背书】")
    print("  📊 数据说话:")
    print("    · 累计销量 {}+".format(random.choice(["5万", "10万", "50万", "100万"])))
    print("    · 好评率 {:.1f}%".format(random.uniform(97.5, 99.8)))
    print("    · 复购率 {:.0f}%".format(random.uniform(35, 65)))
    print("")
    print("  🏅 权威认证:")
    print("    · 通过国家质量检测")
    print("    · ISO9001质量管理体系认证")
    print("    · 正品保障，假一赔十")
    print("")
    print("  💬 买家真实评价:")
    reviews_pool = [
        "「用了之后再也回不去了，强烈推荐！」",
        "「这个价格买到这个品质，真的绝了」",
        "「已经第三次回购了，品质一直在线」",
        "「推荐给朋友，都说物超所值」",
        "「比实体店便宜还好用，下次还来」",
    ]
    for r in random.sample(reviews_pool, 3):
        print("    {}".format(r))
    print("")

    # ===== 升级：促销引导 =====
    print("【促销引导】")
    print("  🔥 限时福利（不要错过！）")
    print("    💰 现在下单立享限时折扣")
    print("    🎁 前{}名下单赠送精美赠品".format(random.choice(["100", "200", "500"])))
    print("    📦 全国包邮，当天发货")
    print("    🛡️ 7天无理由退换 + 运费险保障")
    print("")
    print("  ⏰ 优惠倒计时中，手慢无！")
    print("  👉 立即下单，锁定特惠价格！")
    print("")

    # 购买保障
    print("【购买保障】")
    print("  ✅ 正品保证，假一赔十")
    print("  ✅ 7天无理由退换货")
    print("  ✅ 运费险保障，退货免运费")
    print("  ✅ 专业客服，售前售后全程服务")
    print("")
    print("  🔥 现在下单还有限时优惠，手慢无！")

def gen_review_reply(review):
    print("=" * 50)
    print("  评价回复话术生成")
    print("=" * 50)
    print("")
    print("原始评价: {}".format(review))
    print("")

    # 判断情感倾向
    positive_words = ["好", "不错", "满意", "喜欢", "棒", "值", "推荐", "快", "舒服", "方便", "实用"]
    negative_words = ["差", "坏", "破", "慢", "贵", "假", "不好", "退", "烂", "垃圾", "失望", "骗"]

    pos_count = sum(1 for w in positive_words if w in review)
    neg_count = sum(1 for w in negative_words if w in review)

    if neg_count > pos_count:
        sentiment = "negative"
    elif pos_count > 0:
        sentiment = "positive"
    else:
        sentiment = "neutral"

    if sentiment == "positive":
        replies = [
            "亲，感谢您的认可和好评！您的满意是我们最大的动力～我们会继续努力，为您提供更好的产品和服务！有任何需要随时联系我们哦，祝您生活愉快！❤️",
            "谢谢亲的好评！看到您喜欢真的太开心了！我们家还有很多好物，欢迎常来逛逛～有问题随时找我们，一定给您满意的答复！😊",
            "亲爱的，非常感谢您的认可！能得到您的好评是我们莫大的荣幸～我们会持续优化产品，期待您的再次光临！🌟",
        ]
    elif sentiment == "negative":
        replies = [
            "亲，非常抱歉给您带来了不好的体验，我们深表歉意！看到您的反馈我们非常重视，已经第一时间安排专人跟进处理。请您联系我们的客服，我们一定给您一个满意的解决方案！您的意见是我们改进的动力！🙏",
            "亲爱的顾客，对于您遇到的问题我们深感抱歉！这不是我们产品应有的表现，我们会立即排查原因并改进。请您放心，我们一定负责到底，麻烦联系在线客服，我们马上为您处理！💪",
            "亲，真的很抱歉让您失望了！您反馈的问题我们已经记录并会认真改进。为了弥补给您造成的不便，请联系客服，我们会为您提供补偿方案。感谢您的宝贵意见，我们一定做得更好！❤️",
        ]
    else:
        replies = [
            "亲，感谢您的评价和反馈！我们会认真对待每一条建议，不断优化产品。有任何使用上的问题都可以随时咨询我们客服，我们一定竭诚为您服务！😊",
            "谢谢亲的评价！您的每一条反馈对我们都很重要，我们会持续改进。如有任何问题，随时联系我们，祝您生活愉快！🌟",
            "亲爱的，感谢您花时间给我们评价！我们会根据您的反馈不断提升产品和服务质量。期待您的再次光临，有问题随时找我们哦！❤️",
        ]

    print("情感判断: {}".format(
        "好评 👍" if sentiment == "positive" else ("差评 ⚠️" if sentiment == "negative" else "中评 💬")
    ))
    print("")

    for i, reply in enumerate(replies):
        print("回复方案{}: ".format(i + 1))
        print("  {}".format(reply))
        print("")

    print("-" * 50)
    print("💡 回复技巧:")
    print("  - 好评: 真诚感谢 + 邀请复购")
    print("  - 差评: 诚恳道歉 + 解决方案 + 引导私聊")
    print("  - 中评: 感谢反馈 + 表示改进")
    print("  - 回复时效: 24小时内回复效果最佳")

def gen_keyword(product):
    print("=" * 60)
    print("  淘宝关键词挖掘 - {}".format(product))
    print("=" * 60)
    print("")

    # 核心词
    print("📌 【核心词】（搜索量最大，竞争最激烈）")
    core_words = [
        product,
        "{}正品".format(product),
        "{}旗舰店".format(product),
        "{}品牌".format(product),
        "{}官方".format(product),
    ]
    for i, w in enumerate(core_words, 1):
        stars = random.randint(3, 5)
        print("  {}. {} | 竞争度: {} | 建议出价: ¥{:.1f}".format(
            i, w, "★" * stars + "☆" * (5 - stars), random.uniform(1.5, 8.0)))
    print("")

    # 长尾词
    print("🔍 【长尾词】（精准流量，转化率高）")
    long_tail_patterns = [
        "{}什么牌子好", "{}推荐", "{}排行榜",
        "{}怎么选", "{}哪个好", "{}性价比高",
        "{}评测", "{}对比", "{}2024新款",
        "{}平价替代", "{}学生党", "{}送礼",
    ]
    selected_long = random.sample(long_tail_patterns, 8)
    for i, pat in enumerate(selected_long, 1):
        word = pat.format(product)
        conv_rate = random.uniform(2.5, 12.0)
        print("  {}. {} | 预估转化率: {:.1f}%".format(i, word, conv_rate))
    print("")

    # 属性词
    print("🏷️ 【属性词】（描述产品特征，提升相关性）")
    attr_categories = {
        "材质": ["纯棉", "真皮", "不锈钢", "硅胶", "ABS", "实木", "陶瓷", "合金"],
        "风格": ["简约", "复古", "日系", "韩版", "ins风", "轻奢", "国潮", "商务"],
        "功能": ["多功能", "便携", "折叠", "智能", "防水", "升级版", "加厚", "静音"],
        "人群": ["男士", "女士", "儿童", "学生", "孕妇", "老人", "情侣", "送礼"],
        "场景": ["家用", "办公", "户外", "旅行", "车载", "宿舍", "厨房", "卧室"],
    }
    for cat_name, words in attr_categories.items():
        selected = random.sample(words, min(4, len(words)))
        combos = ["{} {}".format(product, w) for w in selected]
        print("  📂 {}: {}".format(cat_name, " | ".join(combos)))
    print("")

    # 热搜词/趋势词
    print("🔥 【热搜趋势词】（蹭热度，抢流量）")
    trend_patterns = [
        "{}2024新款", "{}爆款", "{}网红同款",
        "{}明星同款", "{}直播间", "{}李佳琦推荐",
        "{}小红书推荐", "{}抖音爆款", "{}好物推荐",
        "{}必买清单", "{}双11", "{}618",
    ]
    selected_trends = random.sample(trend_patterns, 8)
    for i, pat in enumerate(selected_trends, 1):
        heat = random.randint(5000, 50000)
        print("  {}. {} | 搜索热度: {:,}".format(i, pat.format(product), heat))
    print("")

    # 标题组合建议
    print("=" * 60)
    print("💡 【标题组合公式】")
    print("  公式: 核心词 + 属性词 + 长尾词 + 热搜词")
    print("")
    print("  示例标题组合:")
    combos = [
        "【{}】{} {} {}".format(
            random.choice(["新款", "爆款", "热销"]),
            product,
            random.choice(["简约", "多功能", "便携", "升级版"]),
            random.choice(["学生党", "家用", "送礼", "网红同款"])
        ),
        "{} {} {} {}".format(
            product,
            random.choice(["正品", "旗舰", "品牌"]),
            random.choice(["2024新款", "ins风", "韩版"]),
            random.choice(["包邮", "顺丰包邮", "送运费险"])
        ),
        "【{}】{} {} {} {}".format(
            random.choice(["限时特惠", "TOP1爆款", "品质之选"]),
            product,
            random.choice(["高品质", "加厚", "防水"]),
            random.choice(["男女通用", "情侣款", "学生"]),
            random.choice(["包邮", "7天无理由", "当日发货"])
        ),
    ]
    for i, c in enumerate(combos, 1):
        title = c[:30]
        print("  {}. {} ({}字)".format(i, title, len(title)))
    print("")

    print("-" * 60)
    print("💡 关键词使用技巧:")
    print("  - 标题中核心词放最前面，权重最高")
    print("  - 长尾词布局在标题中后段，精准引流")
    print("  - 属性词自然融入，提高搜索相关性")
    print("  - 热搜词适度使用，避免堆砌被降权")
    print("  - 定期更新关键词，跟踪搜索趋势变化")
    print("  - 避免空格分割关键词（淘宝用紧密排列）")


def gen_promotion(event_type):
    print("=" * 60)
    print("  淘宝促销文案 - {}".format(event_type))
    print("=" * 60)
    print("")

    event_lower = event_type.lower().replace(" ", "")

    # 双11
    if "双11" in event_lower or "双十一" in event_lower or "1111" in event_lower:
        print("🎉 【双11狂欢节促销文案】")
        print("")
        print("📌 主标题方案:")
        titles = [
            "双11狂欢价！全年最低，错过等一年！",
            "11.11巅峰盛典 | 爆款直降，买到就是赚到！",
            "双十一提前购！预售锁定底价，尾款人冲！",
        ]
        for i, t in enumerate(titles, 1):
            print("  {}. {}".format(i, t))
        print("")
        print("📌 活动节奏:")
        print("  🔸 预售期（10.24-10.31）: 付定金立减，定金翻倍")
        print("  🔸 预热期（11.01-11.10）: 加购物车，领满减券")
        print("  🔸 爆发期（11.11当天）:   全场最低价，限时秒杀")
        print("  🔸 返场期（11.12-11.13）: 错过补货，最后机会")
        print("")
        print("📌 促销话术:")
        print("  · 「全年仅此一次的价格，手慢无！」")
        print("  · 「预售已抢XX件，库存告急！」")
        print("  · 「付定金立省XX元，尾款还能叠加满减！」")
        print("  · 「去年双11 XX分钟售罄，今年备货翻倍！」")
        print("  · 「双11不买=亏钱！全年最低到手价！」")
        print("")
        print("📌 详情页Banner文案:")
        print("  「双11巅峰钜惠 | 到手价¥XX | 买1送1 | 前100名加赠」")
        print("  「11.11狂欢盛典 | 跨店满300减50 | 叠加店铺券再减XX」")

    # 618
    elif "618" in event_lower:
        print("🎉 【618年中大促文案】")
        print("")
        print("📌 主标题方案:")
        titles = [
            "618年中狂欢！半年最低价，买它！",
            "6.18大促来袭 | 年中清仓，爆款直降！",
            "618提前抢！预售开启，定金膨胀翻3倍！",
        ]
        for i, t in enumerate(titles, 1):
            print("  {}. {}".format(i, t))
        print("")
        print("📌 活动节奏:")
        print("  🔸 种草期（6.01-6.15）: 加购领券，提前锁价")
        print("  🔸 开门红（6.16-6.17）: 限时秒杀，前N件半价")
        print("  🔸 高潮日（6.18当天）:  全场最低价，巅峰狂欢")
        print("  🔸 返场期（6.19-6.20）: 错过补购，尾货清仓")
        print("")
        print("📌 促销话术:")
        print("  · 「年中大促，半年等一回！」")
        print("  · 「618价到了！比日常省XX元！」")
        print("  · 「开门红秒杀！前100名半价！」")
        print("  · 「满减+券+赠品，三重优惠叠加！」")
        print("  · 「618必囤清单第一名！不买后悔！」")

    # 聚划算
    elif "聚划算" in event_lower or "juhuasuan" in event_lower:
        print("🎉 【聚划算专场文案】")
        print("")
        print("📌 主标题方案:")
        titles = [
            "聚划算限时秒杀！全网底价，拼手速！",
            "聚划算团购价 | 人越多越便宜！",
            "聚划算品牌日 | 正品保障，价格击穿！",
        ]
        for i, t in enumerate(titles, 1):
            print("  {}. {}".format(i, t))
        print("")
        print("📌 聚划算文案模板:")
        print("  · 「聚划算独家价，比日常省XX%！」")
        print("  · 「限时24小时！过期恢复原价！」")
        print("  · 「已有XXXX人参团，库存仅剩XX件！」")
        print("  · 「品牌授权，假一赔十，放心购！」")
        print("  · 「团购价到手¥XX，日常价¥XX，省¥XX！」")
        print("")
        print("📌 详情页必备元素:")
        print("  ✅ 聚划算LOGO + 限时标签")
        print("  ✅ 价格对比条（划线价 vs 聚划算价）")
        print("  ✅ 已参团人数实时展示")
        print("  ✅ 倒计时组件")
        print("  ✅ 赠品/满减信息突出展示")

    # 日常促销（默认）
    else:
        print("🎉 【{}促销文案】".format(event_type))
        print("")
        print("📌 主标题方案:")
        titles = [
            "{}特惠 | 限时折扣，错过不再有！".format(event_type),
            "{} | 爆款直降，买到就是赚到！".format(event_type),
            "{}福利来袭 | 全场满减，优惠享不停！".format(event_type),
        ]
        for i, t in enumerate(titles, 1):
            print("  {}. {}".format(i, t))
        print("")
        print("📌 促销话术模板:")
        print("  · 「限时特惠，倒计时XX小时！」")
        print("  · 「库存告急！仅剩最后XX件！」")
        print("  · 「满XX减XX，上不封顶！」")
        print("  · 「前100名下单赠送精美礼品！」")
        print("  · 「老客专享价，比新客再省XX元！」")
        print("  · 「收藏加购领5元无门槛券！」")
        print("")
        print("📌 日常促销工具箱:")
        print("  🔸 满减券: 满99减10 / 满199减30 / 满299减50")
        print("  🔸 限时折: 前1小时8折 / 前100件7折")
        print("  🔸 搭配购: 买A+B立减XX元 / 第二件半价")
        print("  🔸 赠品策: 买就送 / 满额送 / 评价晒单送")
        print("  🔸 会员价: VIP专享价 / 老客回馈价")

    print("")
    print("-" * 60)
    print("💡 促销文案通用技巧:")
    print("  - 突出价格对比（原价 vs 活动价），让优惠一目了然")
    print("  - 制造紧迫感（限时、限量、倒计时）")
    print("  - 叠加优惠（满减+券+赠品），提升客单价")
    print("  - 用数据说话（已售XX件、XX人加购）")
    print("  - 主图必须有活动氛围（红色/橙色+促销标签）")
    print("  - 提前设置购物车营销和收藏有礼")


def main():
    args = sys.argv[1:]
    if not args:
        show_help()
        return

    cmd = args[0]

    if cmd == "help":
        show_help()
    elif cmd == "title":
        if len(args) < 3:
            print("用法: taobao.sh title \"产品名\" \"关键词1,关键词2\"")
            sys.exit(1)
        gen_title(args[1], args[2])
    elif cmd == "selling-point":
        if len(args) < 2:
            print("用法: taobao.sh selling-point \"产品名\"")
            sys.exit(1)
        gen_selling_points(args[1])
    elif cmd == "detail":
        if len(args) < 2:
            print("用法: taobao.sh detail \"产品名\" [\"材质,尺寸,功能\"]")
            sys.exit(1)
        attrs_str = args[2] if len(args) >= 3 else ""
        gen_detail(args[1], attrs_str)
    elif cmd == "keyword":
        if len(args) < 2:
            print("用法: taobao.sh keyword \"产品名\"")
            sys.exit(1)
        gen_keyword(args[1])
    elif cmd == "promotion":
        if len(args) < 2:
            print("用法: taobao.sh promotion \"活动类型\"")
            print("支持: 双11, 618, 聚划算, 或任意活动名称")
            sys.exit(1)
        gen_promotion(args[1])
    elif cmd == "review-reply":
        if len(args) < 2:
            print("用法: taobao.sh review-reply \"评价内容\"")
            sys.exit(1)
        gen_review_reply(args[1])
    else:
        print("未知命令: {}".format(cmd))
        print("运行 taobao.sh help 查看帮助")
        sys.exit(1)

if __name__ == "__main__":
    main()
PYTHON_EOF

echo ""
echo "  Powered by BytesAgain | bytesagain.com | hello@bytesagain.com"
