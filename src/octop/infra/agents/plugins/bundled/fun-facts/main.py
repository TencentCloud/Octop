"""Random Chinese fun facts and jokes — local."""

from __future__ import annotations

import json
import random
from typing import Any

from harness_agent.plugins import PluginContext

_FACTS = (
    "蜂鸟是唯一可以倒飞的鸟类。",
    "章鱼有三颗心脏，血液是蓝色的。",
    "香蕉在植物学上属于浆果，草莓却不是。",
    "一天有大约 86400 秒，闰秒偶尔会让它多一秒。",
    "北极熊的皮肤其实是黑色的，毛是透明中空的。",
    "人类 DNA 与香蕉约有 60% 相似（编码蛋白部分）。",
    "月球每年远离地球约 3.8 厘米。",
    "蜗牛可以睡三年不醒。",
    "闪电温度可比太阳表面还高。",
    "企鹅求偶时会送一颗小石头当「礼物」。",
    "河马分泌的红色液体常被误认为血，其实是防晒黏液。",
    "猫的对称瞳孔能在弱光下看清猎物。",
    "世界上最长的地名之一在新西兰：Taumatawhakatangihangakoauauotamateapokaiwhenuakitanatahu。",
    "真空中的光速约为 299792458 米/秒。",
    "竹子在合适条件下一天可长高近一米。",
    "海豚睡觉时会闭一只眼，半个大脑休息。",
    "蜂蜜几乎不会变质，考古曾发现仍可食用的古蜂蜜。",
)

_JOKES = (
    "程序员买瓜：这瓜保熟吗？老板：编译过。程序员：那是 C 瓜。",
    "我问 AI 会不会取代我，它说：「先帮我把 bug 修完。」",
    "产品经理：「就改一行代码。」工程师：「哪一行？第几行宇宙？」",
    "今日运势：宜提交，忌 force push。",
    "后端：接口好了。前端：格式不对。后端：你缓存清了吗？前端：我电脑重启了。",
    "运维：服务挂了。开发：我本地没问题啊。运维：生产环境不是本地。",
    "学渣：老师我会背公式。学霸：你会推导吗？学渣：我会搜。",
    "猫走进会议室：这个需求，我爪绝。",
    "减肥计划：从明天开始。明天：从后天开始。",
    "我：早点睡。Also 我：再看一集。",
    "老板：要有大局观。我：大局观能报销吗？",
    "文档写着「此处略」。我：人生也略过了。",
)


def _payload(data: dict[str, Any], text: str) -> str:
    return json.dumps(
        {"octop_ui": {"renderer": "fun_facts_card", "version": 1}, "data": data, "text": text},
        ensure_ascii=False,
    )


async def random_fun_fact(kind: str = "fact") -> str:
    """Return a random fact or joke. kind: fact | joke."""
    key = (kind or "fact").strip().lower()
    if key.startswith("j"):
        pool, label = _JOKES, "joke"
    else:
        pool, label = _FACTS, "fact"
    body = random.choice(pool)
    data = {"kind": label, "content": body}
    return _payload(data, body)


def setup(ctx: PluginContext) -> None:
    ctx.tool(
        "random_fun_fact",
        random_fun_fact,
        description="随机冷知识或笑话。kind 为 fact 或 joke。",
    )
