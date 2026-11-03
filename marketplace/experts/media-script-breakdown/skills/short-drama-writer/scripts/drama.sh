#!/usr/bin/env bash
# short-drama-writer — 短剧剧本创作工具
set -euo pipefail
CMD="${1:-help}"; shift 2>/dev/null || true; INPUT="$*"
run_python() {
python3 << 'PYEOF'
import sys, hashlib, random
from datetime import datetime

cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
inp = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""

GENRES = {
    "romance": {"name": "甜宠", "beats": ["邂逅","误会","心动","表白","分离","重逢","HE"],
                "archetypes": ["霸总+灰姑娘","青梅竹马","欢喜冤家","先婚后爱"]},
    "revenge": {"name": "逆袭", "beats": ["受辱","觉醒","蛰伏","崛起","反击","碾压","登顶"],
                "archetypes": ["废婿逆袭","重生复仇","小人物崛起","退婚后觉醒"]},
    "suspense": {"name": "悬疑", "beats": ["案发","调查","嫌疑","反转","真相","结局"],
                 "archetypes": ["密室","连环","心理","法医"]},
    "fantasy": {"name": "玄幻", "beats": ["废材","奇遇","修炼","对决","突破","称霸"],
                "archetypes": ["修仙","重生","系统","穿越"]},
    "family": {"name": "家庭", "beats": ["矛盾","爆发","反思","和解","成长","团圆"],
               "archetypes": ["婆媳","代际","兄弟","回归"]},
}

def cmd_outline():
    if not inp:
        print("Usage: outline <genre> <title> [episodes]")
        print("Genres: {}".format(", ".join(GENRES.keys())))
        return
    parts = inp.split()
    genre = parts[0].lower()
    title = parts[1] if len(parts) > 1 else "Untitled"
    eps = int(parts[2]) if len(parts) > 2 else 10

    if genre not in GENRES:
        print("Unknown genre. Available: {}".format(", ".join(GENRES.keys())))
        return

    g = GENRES[genre]
    beats = g["beats"]
    eps_per_beat = max(1, eps // len(beats))

    print("=" * 55)
    print("  {} 短剧大纲".format(title))
    print("  类型: {} | 集数: {}集 | 每集: 2-3分钟".format(g["name"], eps))
    print("=" * 55)
    print("")
    print("  推荐模式: {}".format(g["archetypes"][0]))
    print("")

    ep_num = 1
    for i, beat in enumerate(beats):
        n = eps_per_beat if i < len(beats) - 1 else eps - ep_num + 1
        if n <= 0:
            n = 1
        print("  --- {} ({} eps) ---".format(beat, n))
        for j in range(n):
            if ep_num > eps:
                break
            print("    EP{:02d}: [{}] ___".format(ep_num, beat))
            ep_num += 1
        print("")

    print("  钩子设计:")
    print("    EP01结尾: 必须有强悬念(留存关键)")
    print("    EP03结尾: 第一个大反转")
    print("    最终集: 情感高潮 + 开放式结局(续集空间)")

def cmd_character():
    if not inp:
        print("Usage: character <name> <role>")
        print("Roles: protagonist, antagonist, love-interest, mentor, comic-relief")
        return
    parts = inp.split()
    name = parts[0]
    role = parts[1] if len(parts) > 1 else "protagonist"

    templates = {
        "protagonist": {
            "arc": "从弱到强/从迷茫到清醒",
            "traits": ["坚韧","善良","有底线","隐藏实力"],
            "flaw": "过于信任他人/优柔寡断",
            "motivation": "证明自己/保护所爱",
        },
        "antagonist": {
            "arc": "从隐藏到暴露/从强势到崩塌",
            "traits": ["精明","自私","掌控欲强","表面温和"],
            "flaw": "傲慢/低估主角",
            "motivation": "权力/嫉妒/过往创伤",
        },
        "love-interest": {
            "arc": "从误解到理解/从冷漠到深情",
            "traits": ["外冷内热","能力强","专一","有秘密"],
            "flaw": "不善表达/过度保护",
            "motivation": "守护/救赎/陪伴",
        },
        "mentor": {
            "arc": "引导成长/关键时刻牺牲",
            "traits": ["智慧","神秘","严厉但关爱"],
            "flaw": "隐瞒真相",
            "motivation": "传承/弥补遗憾",
        },
        "comic-relief": {
            "arc": "搞笑外表下有真本事",
            "traits": ["话多","乐观","忠诚","意外有用"],
            "flaw": "冲动/嘴快",
            "motivation": "友情/存在感",
        },
    }

    t = templates.get(role, templates["protagonist"])
    print("=" * 50)
    print("  角色设定: {} ({})".format(name, role))
    print("=" * 50)
    print("")
    print("  基本信息:")
    print("    姓名: {}".format(name))
    print("    年龄: ___")
    print("    职业: ___")
    print("    外貌: ___")
    print("")
    print("  性格特征: {}".format(", ".join(t["traits"])))
    print("  性格缺陷: {}".format(t["flaw"]))
    print("  人物弧光: {}".format(t["arc"]))
    print("  核心动机: {}".format(t["motivation"]))
    print("")
    print("  关键台词(至少3句):")
    print("    1. [第一次出场] ___")
    print("    2. [转折点] ___")
    print("    3. [高潮] ___")
    print("")
    print("  与其他角色关系:")
    print("    与主角: ___")
    print("    与反派: ___")

def cmd_episode():
    if not inp:
        print("Usage: episode <ep_number> <scene_count>")
        print("Example: episode 1 5")
        return
    parts = inp.split()
    ep = int(parts[0]) if parts else 1
    scenes = int(parts[1]) if len(parts) > 1 else 4

    print("=" * 55)
    print("  EP{:02d} 分场景剧本".format(ep))
    print("  时长: 2-3分钟 | 场景数: {}".format(scenes))
    print("=" * 55)
    print("")

    for s in range(1, scenes + 1):
        dur = "{}s".format(180 // scenes)
        print("  场景{} [{}/{}] ~{}".format(s, s, scenes, dur))
        print("  " + "-" * 40)
        print("    地点: ___")
        print("    时间: 日/夜")
        print("    人物: ___")
        print("    动作: [描述画面和动作]")
        print("    对白:")
        print("      角色A: ___")
        print("      角色B: ___")
        print("    BGM/音效: ___")
        if s == scenes:
            print("    [钩子/悬念] ___")
        print("")

    print("  本集要点:")
    print("    - 开头: 3秒内抓住注意力")
    print("    - 结尾: 必须有悬念或情感冲击")
    print("    - 节奏: 快切,不要长对话")

def cmd_hooks():
    print("=" * 50)
    print("  短剧钩子设计库 (30+经典钩子)")
    print("=" * 50)
    hooks = [
        "开局钩子", ["主角当众受辱","神秘身份暴露","倒叙:从高潮开始","角色说出惊人秘密","致命危机降临"],
        "中段钩子", ["反派突然帮忙","盟友叛变","真实身份揭露","时间紧迫的选择","失去重要的人"],
        "结尾钩子", ["新角色神秘登场","主角做出意外决定","反转:受害者是幕后黑手","角色说了一半被打断","画面定格在关键表情"],
        "情感钩子", ["初吻/分手","被迫分离","牺牲自己","误会解除","重逢相认"],
    ]
    for i in range(0, len(hooks), 2):
        print("")
        print("  {}:".format(hooks[i]))
        for h in hooks[i+1]:
            print("    - {}".format(h))

    print("")
    print("  黄金法则: 每集结尾必须让观众想看下一集")

commands = {
    "outline": cmd_outline, "character": cmd_character,
    "episode": cmd_episode, "hooks": cmd_hooks,
}
if cmd == "help":
    print("Short Drama Writer")
    print("")
    print("Commands:")
    print("  outline <genre> <title> [eps]  — Full series outline")
    print("  character <name> <role>        — Character profile sheet")
    print("  episode <ep_num> [scenes]      — Episode scene breakdown")
    print("  hooks                          — Hook/cliffhanger library")
    print("")
    print("Genres: romance, revenge, suspense, fantasy, family")
elif cmd in commands:
    commands[cmd]()
else:
    print("Unknown: {}".format(cmd))
print("")
print("Powered by BytesAgain | bytesagain.com")
PYEOF
}
run_python "$CMD" $INPUT
