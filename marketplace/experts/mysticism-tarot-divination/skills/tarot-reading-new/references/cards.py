# 塔罗牌完整数据库
# 韦特塔罗 Rider-Waite-Smith 78张
# 大阿尔卡纳 22张 + 小阿尔卡纳 56张

major_arcana = {
    # 编号(0-21)：(中文名, 英文名, 正位含义, 逆位含义)
    0: {
        "cn": "愚人", "en": "The Fool",
        "upright": "纯真、冒险、自由、新开始、天真、 spontaneity",
        "reversed": "冲动、轻率、鲁莽、延误、缺乏计划、天真幼稚"
    },
    1: {
        "cn": "魔术师", "en": "The Magician",
        "upright": "意志力、行动、创造力、沟通、skill、manifestation",
        "reversed": "欺骗、伎俩、缺乏方向、浪费天赋、拖延、光说不做"
    },
    2: {
        "cn": "女祭司", "en": "The High Priestess",
        "upright": "直觉、神秘、智慧、內在知识、信仰、潜意识",
        "reversed": "隐秘、秘密、缺乏直觉、表面化、欺骗、隐瞒"
    },
    3: {
        "cn": "皇后", "en": "The Empress",
        "upright": "丰盛、滋养、自然、母亲般关怀、创造力、感官",
        "reversed": "依赖、过度保护、停滞、创造力受阻、母亲问题"
    },
    4: {
        "cn": "皇帝", "en": "The Emperor",
        "upright": "权威、结构、父亲般领导、稳定性、control、决断",
        "reversed": "暴政、控制欲过强、缺乏纪律、rigidity、冲动"
    },
    5: {
        "cn": "教皇", "en": "The Hierophant",
        "upright": "传统、精神指引、导师、信仰、价值观、社会规范",
        "reversed": "反叛、打破常规、个人信仰、误导导师、不合群"
    },
    6: {
        "cn": "恋人", "en": "The Lovers",
        "upright": "爱情、选择、伙伴关系、价值观、吸引、结合",
        "reversed": "失衡、不和、价值观冲突、欺骗、犹豫不决"
    },
    7: {
        "cn": "战车", "en": "The Chariot",
        "upright": "意志力、胜利、决心、掌控、掌控、行动力",
        "reversed": "失控、缺乏方向、冲动、失去控制、固执"
    },
    8: {
        "cn": "力量", "en": "Strength",
        "upright": "勇气、耐心、内在力量、同情心、韧性、温柔的力量",
        "reversed": "自我怀疑、脆弱、失控、内在勇气不足、恐惧"
    },
    9: {
        "cn": "隐士", "en": "The Hermit",
        "upright": "內省、孤独、內在指引、寻找真理、休息、洞察",
        "reversed": "孤立、孤独感、过度內省、退缩、拒绝帮助"
    },
    10: {
        "cn": "命运之轮", "en": "Wheel of Fortune",
        "upright": "命运转变、 cycle、机会、好运、 inevitability",
        "reversed": "厄运、cycle中断、抗拒改变、错失机会、停滞"
    },
    11: {
        "cn": "正义", "en": "Justice",
        "upright": "公正、真相、法律、因果报应、平衡、诚实",
        "reversed": "不公正、不诚实、法律问题、缺乏责任感、偏见"
    },
    12: {
        "cn": "吊人", "en": "The Hanged Man",
        "upright": "暂停、牺牲、新的视角、臣服、等待、转变观点",
        "reversed": "拖延、牺牲过度、拒绝妥协、坐以待毙、牺牲白费"
    },
    13: {
        "cn": "死神", "en": "Death",
        "upright": "结束、彻底转变、重生、释放过去、蜕变",
        "reversed": "抗拒改变、停滞、渐进的结束、恐惧结束、腐烂"
    },
    14: {
        "cn": "节制", "en": "Temperance",
        "upright": "平衡、耐心、目的、调和、整合、适中",
        "reversed": "失衡、过度、极端、缺乏目标、浪费"
    },
    15: {
        "cn": "恶魔", "en": "The Devil",
        "upright": "束缚、物质主义、欲望、阴影面、沉迷、成瘾",
        "reversed": "打破束缚、释放、面对阴影、改变模式、摆脱控制"
    },
    16: {
        "cn": "塔", "en": "The Tower",
        "upright": "突然改变、 disruption、启示、觉醒、打破旧结构",
        "reversed": "害怕改变、内在动荡、延迟灾难、被困在旧结构中"
    },
    17: {
        "cn": "星星", "en": "The Star",
        "upright": "希望、灵感、宁静、疗愈、 faith、Guidance",
        "reversed": "绝望、失去信心、混乱、缺乏希望、误导"
    },
    18: {
        "cn": "月亮", "en": "The Moon",
        "upright": "幻象、恐惧、潜意识、不安、 illusion、夜晚",
        "reversed": "恐惧暴露、压抑情绪、寻找真相、幻觉消退"
    },
    19: {
        "cn": "太阳", "en": "The Sun",
        "upright": "喜悦、成功、活力、生命力、乐观、温暖、成功",
        "reversed": "过度乐观、过度兴奋、成功路上有障碍、暂时的阴霾"
    },
    20: {
        "cn": "审判", "en": "Judgement",
        "upright": "重生、內省、评判、觉醒、因果、宽恕",
        "reversed": "自我怀疑、后悔、忽视內在呼声、不反省、自我否定"
    },
    21: {
        "cn": "世界", "en": "The World",
        "upright": "完成、成就、圆满、整合、旅程终点、成功",
        "reversed": "功亏一篑、缺乏成就感、停滞、延迟完成、原地踏步"
    }
}

# 小阿尔卡纳：四要素 x 14张 = 56张
# 编号 22-77

minor_arcana = {
    # 权杖 suit = wands, element = fire
    "wands": {
        "name_cn": "权杖", "element": "火", "nature": "行动、热情、创造、野心",
        "court": ["侍从", "骑士", "王后", "国王"],
        "court_meanings": {
            "侍从": {"upright": "机会、好奇、探索、热忱", "reversed": "延迟、缺乏热情、浪费机会"},
            "骑士": {"upright": "行动、热情、旅行、冲动", "reversed": "延迟、挫折、冲动行事"},
            "王后": {"upright": "富足、自信、创业、社交", "reversed": "过度自信、炫耀、自私"},
            "国王": {"upright": "领导力、权威、创业、荣耀", "reversed": "专制、傲慢、缺乏远见"}
        },
        "ace": {"upright": "创造、灵感、新开始、潜力", "reversed": "延误计划、缺乏热情、方向不明"},
        "numbered": {
            2: {"upright": "创意计划、选择、远见、 partnership", "reversed": "犹豫不决、缺乏计划、冲突"},
            3: {"upright": "扩张、进步、沟通、进展", "reversed": "延误、挫折、停滞"},
            4: {"upright": "庆祝、 harmony、home、和平", "reversed": "冲突、打破和平、干扰"},
            5: {"upright": "竞争、冲突、变化、选择", "reversed": "避免冲突、赢得竞争、和平解决"},
            6: {"upright": "胜利、认可、荣誉、成就感", "reversed": "失去认可、失败、骄傲导致失败"},
            7: {"upright": "防御、坚持、挑战、面对竞争", "reversed": "放弃、失去优势、被击败"},
            8: {"upright": "快速行动、旅行、移动、消息", "reversed": "延误、挫折、被阻止"},
            9: {"upright": "坚韧、忍耐、hope、perseverance", "reversed": "精疲力尽、过度劳累、倦怠"},
            10: {"upright": "过度负担、责任、压力、辛劳", "reversed": "压力减轻、分享负担、卸下重担"}
        }
    },
    # 圣杯 suit = cups, element = water
    "cups": {
        "name_cn": "圣杯", "element": "水", "nature": "情感、爱、关系、情绪、直觉",
        "court": ["侍从", "骑士", "王后", "国王"],
        "court_meanings": {
            "侍从": {"upright": "创意、浪漫、好奇心、message、机会", "reversed": "忽略情绪、过度浪漫、消息延误"},
            "骑士": {"upright": "浪漫、想象、魅力、追求", "reversed": "欺骗、失望、逃避、浪漫过度"},
            "王后": {"upright": "情感成熟、滋养、直觉、慈悲", "reversed": "情绪化、依赖、缺乏边界"},
            "国王": {"upright": "情感掌控、慷慨、情绪平衡、爱", "reversed": "情绪操纵、喜怒无常、占有欲"}
        },
        "ace": {"upright": "爱、情感新开始、同情心、丰富", "reversed": "情绪压抑、空虚、缺乏情感"},
        "numbered": {
            2: {"upright": "爱、伙伴关系、吸引、浪漫", "reversed": "不平衡、欺骗、关系冲突"},
            3: {"upright": " friendship、 celebration、creative、 collaboration", "reversed": "过度、过度沉溺、孤独的庆祝"},
            4: {"upright": " apathetic、boredom、contemplation、dissatisfaction", "reversed": " new enthusiasm、awakening、hope"},
            5: {"upright": " loss、disappointment、regret、perspective", "reversed": " recovery、reconciliation、moving on"},
            6: {"upright": " memories、nostalgia、 innocence、reunion", "reversed": " stuck in past、unresolved issues、naivety"},
            7: {"upright": " choices、illusion、wishful thinking、opportunities", "reversed": " alignment、clarity、realistic view"},
            8: {"upright": " leaving、walking away、disillusionment、 search for meaning", "reversed": " fear of change、status quo、nostalgia"},
            9: {"upright": " wishes、satisfaction、contentment、gratitude", "reversed": " dissatisfaction、greed、unfulfilled wishes"},
            10: {"upright": " happiness、family、home、harmony、emotional fulfillment", "reversed": " family conflict、miscommunication、broken home"}
        }
    },
    # 宝剑 suit = swords, element = air
    "swords": {
        "name_cn": "宝剑", "element": "风", "nature": "心智、思维、沟通、冲突、真相、决定",
        "court": ["侍从", "骑士", "王后", "国王"],
        "court_meanings": {
            "侍从": {"upright": " curiosity、new ideas、thirst for knowledge", "reversed": " deception、gossip、manipulation"},
            "骑士": {"upright": "action、breakthrough、fast-moving、mental clarity", "reversed": "而立、冲突、冲动、鲁莽"},
            "王后": {"upright": " clear thinking、independence、direct communication", "reversed": " coldness、cruelty、bitterness、overthinking"},
            "国王": {"upright": " intellectual power、authority、truth、clear thinking", "reversed": " abuse of power、 manipulation、tyranny"}
        },
        "ace": {"upright": " clarity、breakthrough、new ideas、mental clarity", "reversed": " confusion、misinformation、chaos"},
        "numbered": {
            2: {"upright": " difficult choice、stalemate、contemplation、balance", "reversed": " indecision、stalemate、confusion"},
            3: {"upright": " heartbreak、painful ending、 grief、loss", "reversed": " recovery from loss、moving on、healing"},
            4: {"upright": " rest、recovery、contemplation、meditation", "reversed": " restlessness、burnout、lack of progress"},
            5: {"upright": " conflict、defeat、losing、dispute", "reversed": " reconciliation、making peace、overcoming conflict"},
            6: {"upright": " transition、moving on、leaving、passage", "reversed": " resisting change、stuck、transition problems"},
            7: {"upright": " deception、strategy、trickery、stealth", "reversed": " coming clean、confession、getting caught"},
            8: {"upright": " restriction、 imprisonment、 stuck、helplessness", "reversed": " freedom、release、new perspective"},
            9: {"upright": " anxiety、fear、worst-case scenario、nightmares", "reversed": " hope、recovery、overcoming fears"},
            10: {"upright": " ending、painful ending、crisis、loss", "reversed": " recovery、healing、end of problems"}
        }
    },
    # 星币 suit = pentacles, element = earth
    "pentacles": {
        "name_cn": "星币", "element": "土", "nature": "物质、财富、工作、健康、现实",
        "court": ["侍从", "骑士", "王后", "国王"],
        "court_meanings": {
            "侍从": {"upright": "manifestation、financial opportunity、skill development", "reversed": " missed opportunity、procrastination、lack of progress"},
            "骑士": {"upright": " efficiency、routine、hard work、productivity", "reversed": " laziness、overwork、boredom"},
            "王后": {"upright": " abundance、luxury、security、comfort", "reversed": " financial insecurity、overindulgence、stinginess"},
            "国王": {"upright": " wealth、business、leadership、security", "reversed": " greed、materialism、poor financial decisions"}
        },
        "ace": {"upright": " new financial opportunity、manifestation、abundance", "reversed": " missed opportunity、poor financial planning"},
        "numbered": {
            2: {"upright": " balance、adaptability、time management、prioritizing", "reversed": " imbalance、over-committed、poor prioritization"},
            3: {"upright": " teamwork、collaboration、learning、implementation", "reversed": " lack of teamwork、poor quality、disharmony"},
            4: {"upright": " security、conservation、control、avings", "reversed": " insecurity、greed、over-spending"},
            5: {"upright": " financial loss、isolation、hardship、homelessness", "reversed": " recovery、improvement、spiritual growth through hardship"},
            6: {"upright": " generosity、charity、giving and receiving、sharing", "reversed": " strings attached、inequality、egoism"},
            7: {"upright": " patience、long-term vision、investing、delayed gratification", "reversed": " impatience、poor returns、lack of long-term vision"},
            8: {"upright": " skill、mastery、dedication、quality craftsmanship", "reversed": " lack of quality、incomplete work、mediocrity"},
            9: {"upright": " abundance、luxury、self-sufficiency、independence", "reversed": " over-reliance、superficiality、greed"},
            10: {"upright": " wealth、inheritance、family、legacy、abundance", "reversed": " financial failure、family conflict、poverty"}
        }
    }
}
