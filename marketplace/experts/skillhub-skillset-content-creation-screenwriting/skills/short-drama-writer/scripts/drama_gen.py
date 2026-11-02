#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""短剧剧本生成器 - Python 3.6 compatible"""

from __future__ import print_function
import sys
import random
import textwrap
import argparse


GENRES = {
    "霸总": {
        "name": "霸道总裁",
        "keywords": ["豪门", "契约", "身份", "商战", "宠溺"],
        "male_lead": "冷面霸总",
        "female_lead": "倔强灰姑娘",
        "conflict": "身份差距 + 家族阻力",
        "episodes_template": [
            ("相遇", "意外相遇/碰撞，第一印象极差"),
            ("纠缠", "被迫绑定（契约/工作/同居），矛盾不断"),
            ("心动", "霸总开始对女主特别，但嘴硬心软"),
            ("误会", "第三者/前任出现，造成误会"),
            ("分离", "女主离开，霸总意识到感情"),
            ("追回", "霸总放下一切去找女主"),
            ("真相", "身世/秘密揭露，剧情反转"),
            ("考验", "外界压力（家族/商业对手）"),
            ("高潮", "最大危机，生死抉择"),
            ("团圆", "化解一切，甜蜜结局"),
        ],
    },
    "穿越": {
        "name": "穿越重生",
        "keywords": ["重生", "逆袭", "金手指", "蝴蝶效应", "命运"],
        "male_lead": "重生知情者",
        "female_lead": "命运改写者",
        "conflict": "改变命运 vs 历史惯性",
        "episodes_template": [
            ("重生", "主角重生/穿越，发现回到过去"),
            ("试探", "确认重生事实，回忆前世关键事件"),
            ("布局", "利用先知优势开始改变命运"),
            ("蝴蝶效应", "一些改变带来意想不到的后果"),
            ("复仇", "对前世伤害过自己的人展开反击"),
            ("新变量", "出现前世不存在的人/事"),
            ("动摇", "是否继续改变？道德困境"),
            ("决战", "面对最终Boss/最大命运节点"),
            ("代价", "改变命运需要付出的代价"),
            ("新生", "新的人生，新的结局"),
        ],
    },
    "复仇": {
        "name": "复仇逆袭",
        "keywords": ["隐忍", "反杀", "身份", "布局", "真相"],
        "male_lead": "深藏不露复仇者",
        "female_lead": "黑化归来者",
        "conflict": "复仇 vs 人性 vs 真相",
        "episodes_template": [
            ("屈辱", "主角遭受极大不公/背叛"),
            ("蛰伏", "忍辱负重，暗中准备"),
            ("归来", "以全新身份/面貌回归"),
            ("试探", "接近仇人，暗中观察"),
            ("第一击", "第一个复仇计划执行"),
            ("反击", "对手发觉，开始反击"),
            ("同盟", "找到盟友，或敌人内部分化"),
            ("真相", "发现更大的阴谋/真相"),
            ("终极对决", "与最终Boss正面交锋"),
            ("抉择", "复仇完成后的选择——放下或继续？"),
        ],
    },
    "甜宠": {
        "name": "甜蜜宠爱",
        "keywords": ["撒糖", "日常", "双向奔赴", "甜", "心跳"],
        "male_lead": "深情忠犬/腹黑竹马",
        "female_lead": "元气少女/软萌学霸",
        "conflict": "误会 + 成长 + 外界阻碍（轻度）",
        "episodes_template": [
            ("初遇", "有趣的第一次见面，埋下伏笔"),
            ("靠近", "频繁偶遇/被迫接触，开始熟悉"),
            ("暧昧", "开始有暧昧互动，双方都不承认"),
            ("表白", "一方表白/关系确认"),
            ("热恋", "甜蜜日常，各种糖"),
            ("小波折", "小误会/小吃醋，但很快解决"),
            ("见家长", "关系进一步，但面临外界看法"),
            ("考验", "分离/距离/事业考验感情"),
            ("和好", "解除误会，更加珍惜"),
            ("结局", "梦幻甜蜜结局+彩蛋"),
        ],
    },
    "悬疑": {
        "name": "悬疑烧脑",
        "keywords": ["反转", "真相", "线索", "推理", "人性"],
        "male_lead": "天才侦探/受害者",
        "female_lead": "神秘女人/关键证人",
        "conflict": "真相 vs 谎言 vs 人性",
        "episodes_template": [
            ("案发", "核心事件发生，疑点重重"),
            ("调查", "开始调查，发现第一批线索"),
            ("嫌疑人", "锁定嫌疑人，但证据不足"),
            ("反转1", "第一个反转——嫌疑人有不在场证明"),
            ("深入", "深挖关系网，发现隐藏关系"),
            ("第二具", "新的事件发生，增加复杂度"),
            ("反转2", "核心线索指向意想不到的人"),
            ("真相接近", "拼图即将完成，但主角陷入危险"),
            ("揭露", "真相大白，但令人唏嘘"),
            ("余韵", "案件结束，留下思考/彩蛋暗示"),
        ],
    },
}


def gen_plot(genre_key, episodes=10):
    """生成剧情大纲"""
    episodes = int(episodes)
    genre_key_lower = genre_key.lower()

    # 模糊匹配
    matched = None
    for key in GENRES:
        if key in genre_key or genre_key in key:
            matched = key
            break

    if matched is None:
        print("未知类型: {}".format(genre_key))
        print("支持的类型: {}".format(", ".join(GENRES.keys())))
        sys.exit(1)

    genre = GENRES[matched]

    print("=" * 60)
    print("🎬 短剧剧情大纲 | 类型: {} | 集数: {}集".format(genre["name"], episodes))
    print("=" * 60)
    print("")

    print("## 📋 基本信息")
    print("")
    print("- **类型：** {}".format(genre["name"]))
    print("- **集数：** {}集".format(episodes))
    print("- **每集时长：** 2-3分钟（竖屏短剧标准）")
    print("- **关键词：** {}".format("、".join(genre["keywords"])))
    print("- **男主类型：** {}".format(genre["male_lead"]))
    print("- **女主类型：** {}".format(genre["female_lead"]))
    print("- **核心冲突：** {}".format(genre["conflict"]))
    print("")

    print("## 📖 剧情大纲")
    print("")

    template = genre["episodes_template"]
    # 如果集数不等于模板长度，进行调整
    if episodes <= len(template):
        selected = template[:episodes]
    else:
        # 扩展：在中间部分插入更多剧集
        selected = list(template)
        extra = episodes - len(template)
        insert_names = ["支线", "深化", "波折", "暗流", "转折", "伏笔", "对峙", "挣扎"]
        for i in range(extra):
            name = insert_names[i % len(insert_names)]
            pos = len(selected) - 2  # 插在倒数第二个前面
            selected.insert(pos, (name, "[补充剧情——支线展开/感情深化/新角色引入]"))

    for i, (ep_name, ep_desc) in enumerate(selected, 1):
        print("### 第{}集：{}".format(i, ep_name))
        print("")
        print("**剧情：** {}".format(ep_desc))
        print("")
        if i == 1:
            print("> 💡 第1集最关键！前30秒必须抓住观众。建议用倒叙/冲突开场。")
            print("")
        elif i == len(selected):
            print("> 💡 结局集要给观众满足感。可以留小彩蛋暗示第二季。")
            print("")
        elif i == len(selected) // 2:
            print("> 💡 中间集是流失高峰，需要强反转/大悬念来留住观众。")
            print("")

    print("## 🔑 创作要点")
    print("")
    print("1. **每集结尾必须有钩子** — 让观众忍不住看下一集")
    print("2. **前3集定生死** — 节奏要快，迅速建立冲突")
    print("3. **每集1个爽点** — 给观众情绪释放的出口")
    print("4. **台词要短** — 短剧不适合长对白，要金句化")
    print("5. **视觉冲击** — 竖屏构图，表情特写，强化情绪")


def gen_scene(description):
    """生成单场戏剧本"""
    print("=" * 60)
    print("🎬 单场戏剧本 | 场景: {}".format(description))
    print("=" * 60)
    print("")

    print(textwrap.dedent("""\
        ## 场景信息

        - **场景：** {desc}
        - **时间：** [日/夜]
        - **地点：** [具体地点]
        - **人物：** [出场人物]
        - **情绪基调：** [紧张/甜蜜/悲伤/愤怒]

        ---

        ## 剧本正文

        **场景：[地点] — [日/夜] — [内/外]**

        ---

        **【镜头1】** 中景/全景 — 建立场景

        _（环境描写：[描述场景氛围、灯光、声音]）_

        _（[角色A] 从[方向]走入画面，[动作描写]）_

        ---

        **【镜头2】** 近景 — 角色A

        **角色A：** （[情绪/语气]）
        "第一句台词。"

        _（[动作/表情描写]）_

        ---

        **【镜头3】** 反打近景 — 角色B

        **角色B：** （[情绪/语气]）
        "回应台词。"

        _（[微表情变化]）_

        ---

        **【镜头4】** 特写 — 关键道具/表情

        _（[特写什么？为什么？强调什么情绪/信息？]）_

        ---

        **【镜头5】** 双人中景 — 对峙/对话

        **角色A：** （[升级的情绪]）
        "冲突升级的台词。"

        **角色B：** （[相应反应]）
        "回应台词——可以是沉默、动作，或爆发。"

        ---

        **【镜头6】** 近景 — 角色A的反应

        _（[关键反应特写，这是本场戏的情绪高点]）_

        **角色A：** （低声/坚定/颤抖）
        "本场最重要的一句台词。"

        ---

        **【镜头7】** 全景/远景 — 收场

        _（[角色离开/沉默/某个动作收尾]）_
        _（[可选：背景音乐渐起]）_

        ---

        ## 🎬 导演备注

        - **本场核心：** [这场戏要传达什么？]
        - **情绪走向：** [平静 → 紧张 → 爆发 → 余韵]
        - **拍摄提示：** [手持/稳定器/固定机位]
        - **配乐建议：** [什么风格的BGM]
        - **时长估计：** 约60-90秒
    """.format(desc=description)))


def gen_character(char_type):
    """角色设定生成"""
    archetypes = {
        "霸道总裁": {
            "name_options": ["陆少卿", "顾霆琛", "沈夜寒", "裴司宴", "傅景珩"],
            "age": "28-35岁",
            "appearance": "身高185+，天生冷相，穿定制西装，手戴百达翡丽",
            "personality": "表面冷漠无情，实则专一深情。说话简短有力，不废话。对外人冷若冰霜，对女主偷偷宠溺。",
            "background": "X氏集团CEO/继承人，从小被精英教育，缺少温暖。有一段不为人知的过去。",
            "habit": "生气时松领带、揉眉心。心情好时嘴角微微上扬（只有女主能察觉）。",
            "catchphrase": ["\"你在找死。\"", "\"我说过，你是我的人。\"", "\"不许哭。\"（说完却帮她擦眼泪）"],
        },
        "白月光": {
            "name_options": ["苏念安", "林知意", "温如初", "沈清辞", "江晚吟"],
            "age": "22-26岁",
            "appearance": "清冷如月，气质温婉，穿衣素净得体，笑起来很治愈",
            "personality": "温柔善良但不软弱，有自己的底线和原则。外表柔弱内心坚韧。",
            "background": "书香门第/普通家庭出身，凭实力立足。可能有一段被隐瞒的身世。",
            "habit": "紧张时捏衣角，思考时微微歪头。生气时不说话，但眼眶会红。",
            "catchphrase": ["\"我没事。\"（其实很在意）", "\"谢谢你，但我可以自己来。\"", "\"有些事，不是不在乎，是不想让你为难。\""],
        },
        "反派": {
            "name_options": ["赵明轩", "周子衡", "钱瑶", "孙茹萱", "郑海"],
            "age": "25-40岁",
            "appearance": "外表精致/正派，善于伪装，细看眼神阴鸷",
            "personality": "表面温文尔雅，内心阴险毒辣。极度自私，嫉妒心强。前期伪善，后期黑化。",
            "background": "与主角有直接利益冲突。可能是情敌、商业对手、或假装亲近的人。有一个令人同情的过去（增加人物层次）。",
            "habit": "笑的时候不达眼底，说话喜欢绕弯子。得意时有小动作。",
            "catchphrase": ["\"我们是朋友，不是吗？\"（笑）", "\"你以为你赢了？游戏才刚开始。\"", "\"（独白）这个世界，从来不会善待好人。\""],
        },
    }

    # 模糊匹配
    matched = None
    for key in archetypes:
        if key in char_type or char_type in key:
            matched = key
            break

    if matched is None:
        # 使用通用模板
        print("=" * 60)
        print("👤 角色设定 | 类型: {}".format(char_type))
        print("=" * 60)
        print("")
        print(textwrap.dedent("""\
            ## 基本信息

            - **姓名：** [取一个符合角色气质的名字]
            - **年龄：** [根据角色类型设定]
            - **类型：** {char_type}

            ## 外形特征

            [描述外貌、穿着风格、标志性特征]

            ## 性格特点

            - **表面：** [别人看到的样子]
            - **内在：** [真实的性格]
            - **反差：** [表里不一的地方——这是角色魅力所在]

            ## 人物背景

            [家庭背景、成长经历、关键转折事件]
            [这段经历如何塑造了现在的TA]

            ## 行为习惯

            - [标志性小动作1]
            - [标志性小动作2]
            - [情绪化时的表现]

            ## 经典台词

            1. "[符合角色性格的台词]"
            2. "[展现角色魅力的台词]"
            3. "[关键剧情的台词]"

            ## 角色弧光

            开始：[故事开始时的状态]
            转折：[经历什么改变]
            结局：[最终成为什么样的人]

            ---
            💡 好角色的标准：有矛盾、有反差、有成长。
        """.format(char_type=char_type)))
        return

    archetype = archetypes[matched]
    name = random.choice(archetype["name_options"])

    print("=" * 60)
    print("👤 角色设定 | 类型: {} | 姓名: {}".format(matched, name))
    print("=" * 60)
    print("")

    print("## 基本信息")
    print("")
    print("- **姓名：** {}".format(name))
    print("- **年龄：** {}".format(archetype["age"]))
    print("- **类型：** {}".format(matched))
    print("")

    print("## 外形特征")
    print("")
    print(archetype["appearance"])
    print("")

    print("## 性格特点")
    print("")
    print(archetype["personality"])
    print("")

    print("## 人物背景")
    print("")
    print(archetype["background"])
    print("")

    print("## 行为习惯")
    print("")
    print(archetype["habit"])
    print("")

    print("## 经典台词")
    print("")
    for i, line in enumerate(archetype["catchphrase"], 1):
        print("{}. {}".format(i, line))
    print("")

    print("## 角色弧光建议")
    print("")
    print("- **开始：** [角色初始状态]")
    print("- **转折：** [关键事件改变角色]")
    print("- **结局：** [角色最终走向]")
    print("")
    print("---")
    print("💡 提示：可以用 `drama.sh character \"自定义类型\"` 生成任意角色设定")


def gen_twist():
    """反转桥段生成器"""
    twists = [
        {
            "name": "身份反转",
            "desc": "真正的身份暴露",
            "examples": [
                "路边捡来的「穷小子」其实是失踪多年的集团继承人",
                "温柔善良的「闺蜜」其实是幕后黑手",
                "被所有人看不起的「废物」其实在下一盘大棋",
                "嫁入豪门的「灰姑娘」其实家族比男方还显赫",
                "公司新来的「保洁阿姨」其实是来微服私访的董事长",
            ],
        },
        {
            "name": "关系反转",
            "desc": "人物关系出人意料",
            "examples": [
                "恨了三年的「仇人」其实一直在暗中保护自己",
                "最信任的「爱人」其实是敌方安排的间谍",
                "素未谋面的「陌生人」其实是失散多年的亲生兄妹",
                "处处针对的「恶婆婆」其实是在试探真心",
                "一直帮忙的「好人」才是杀害父亲的真凶",
            ],
        },
        {
            "name": "认知反转",
            "desc": "观众以为的剧情被彻底颠覆",
            "examples": [
                "前5集都是主角的幻想/梦境/濒死走马灯",
                "「穿越到古代」其实是沉浸式剧本杀",
                "以为是恋爱故事，其实是精心策划的复仇",
                "看似在讲A的故事，其实主角一直是B",
                "整个故事是主角写的小说，而真实生活比小说更离谱",
            ],
        },
        {
            "name": "结局反转",
            "desc": "结局出乎意料",
            "examples": [
                "以为是HE（大团圆），最后一个镜头暗示一切会重来",
                "所有人都以为反派死了，最后一秒反派睁开眼睛",
                "主角放弃复仇选择原谅，但被原谅的人却没有放过主角",
                "大结局才揭示：真正的主角是一直不起眼的配角",
                "时间线打乱重组后，发现第一集就是结局",
            ],
        },
        {
            "name": "道具/线索反转",
            "desc": "一个不起眼的东西成为关键",
            "examples": [
                "第1集出现的一张旧照片，最后成为翻盘的关键证据",
                "一直戴着的平安扣，里面藏着改变命运的芯片",
                "反复出现的那首歌，歌词就是密码/遗嘱",
                "被扔掉的「垃圾」里藏着价值连城的东西",
                "背景里不起眼的路人，每一集都出现——TA才是真正的操纵者",
            ],
        },
    ]

    print("=" * 60)
    print("🔄 反转桥段生成器 — 随机生成3个反转创意")
    print("=" * 60)
    print("")

    selected = random.sample(twists, min(3, len(twists)))

    for i, twist in enumerate(selected, 1):
        example = random.choice(twist["examples"])
        print("## 反转 {} — {}".format(i, twist["name"]))
        print("")
        print("**类型：** {}".format(twist["desc"]))
        print("")
        print("**示例：**")
        print("> {}".format(example))
        print("")
        print("**更多同类反转：**")
        others = [e for e in twist["examples"] if e != example]
        for other in others[:2]:
            print("  - {}".format(other))
        print("")

    print("---")
    print("💡 反转写作技巧：")
    print("  1. **前期埋线** — 反转要有伏笔，不能空降")
    print("  2. **合理但意外** — 回头看逻辑通，但第一次看想不到")
    print("  3. **一集一个小反转** — 保持观众的新鲜感")
    print("  4. **大反转放在第3/4集和倒数第2集** — 关键节点")
    print("  5. **反转后给观众消化时间** — 别反转太快")
    print("")
    print("🔄 再次运行可获得不同的反转组合！")


def main():
    if len(sys.argv) < 2:
        print("用法: drama_gen.py <command> [args]")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "plot":
        parser = argparse.ArgumentParser()
        parser.add_argument("genre")
        parser.add_argument("--episodes", default="10")
        args = parser.parse_args(sys.argv[2:])
        gen_plot(args.genre, args.episodes)

    elif cmd == "scene":
        if len(sys.argv) < 3:
            print("用法: drama_gen.py scene \"场景描述\"")
            sys.exit(1)
        gen_scene(sys.argv[2])

    elif cmd == "character":
        if len(sys.argv) < 3:
            print("用法: drama_gen.py character \"角色类型\"")
            sys.exit(1)
        gen_character(sys.argv[2])

    elif cmd == "twist":
        gen_twist()

    else:
        print("未知命令: {}".format(cmd))
        sys.exit(1)


if __name__ == "__main__":
    main()
