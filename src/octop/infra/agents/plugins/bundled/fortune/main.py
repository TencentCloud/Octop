"""Local dice, daily fortune, and lots — no network."""

from __future__ import annotations

import hashlib
import json
import random
import re
from datetime import date
from typing import Any

from harness_agent.plugins import PluginContext

_DICE_RE = re.compile(r"^\s*(\d+)\s*[dD]\s*(\d+)\s*$")
_FACES = {4, 6, 8, 10, 12, 20, 100}

_SUMMARIES = (
    "今日适合把难事拆小，完成一件就算赢。",
    "灵感在路上，先写下来再判断。",
    "少开会，多做；少刷，多睡。",
    "有人会帮你，但要先把问题说清楚。",
    "节奏宜慢不宜乱，检查比加速更重要。",
)

_DO = ("整理桌面", "给自己倒杯水", "把待办写成三条", "出门走十分钟", "回复积压消息")
_DONT = ("同时开五个任务", "熬夜翻盘", "把情绪发给所有人", "空着肚子做决定", "比较别人的高光")
_COLORS = ("朱红", "青绿", "月白", "墨蓝", "杏黄", "藤紫")
_LOTS = (
    ("上上签", "云开见月，所求可成。"),
    ("上签", "行稳致远，耐心自有回音。"),
    ("中签", "半晴半雨，进退皆须留余。"),
    ("下签", "暂避风头，修己以待时。"),
)


def _payload(data: dict[str, Any], text: str) -> str:
    return json.dumps(
        {"octop_ui": {"renderer": "fortune_card", "version": 1}, "data": data, "text": text},
        ensure_ascii=False,
    )


def _rng(seed: str) -> random.Random:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
    return random.Random(int(digest, 16))


async def roll_dice(notation: str = "1d6") -> str:
    """Roll N d M dice. notation like 2d20."""
    raw = (notation or "1d6").strip() or "1d6"
    match = _DICE_RE.match(raw)
    if match is None:
        return _payload(
            {"kind": "dice", "error": "invalid notation"},
            "骰子格式应为 NdM，例如 1d6、2d20。",
        )
    count = int(match.group(1))
    faces = int(match.group(2))
    if count < 1 or count > 20 or faces not in _FACES:
        return _payload(
            {"kind": "dice", "error": "out of range"},
            "骰子数量 1–20，面数仅支持 4/6/8/10/12/20/100。",
        )
    rolls = [random.randint(1, faces) for _ in range(count)]
    total = sum(rolls)
    data = {"kind": "dice", "notation": f"{count}d{faces}", "rolls": rolls, "total": total}
    return _payload(data, f"{count}d{faces} → {rolls} 合计 {total}")


async def daily_fortune(name: str = "") -> str:
    """Stable daily fortune for an optional name."""
    label = (name or "").strip()
    rng = _rng(f"{date.today().isoformat()}|{label.lower()}")
    score = rng.randint(40, 99)
    summary = rng.choice(_SUMMARIES)
    color = rng.choice(_COLORS)
    do = rng.choice(_DO)
    dont = rng.choice(_DONT)
    who = label or "你"
    data = {
        "kind": "fortune",
        "name": who,
        "score": score,
        "summary": summary,
        "lucky_color": color,
        "do": do,
        "dont": dont,
        "date": date.today().isoformat(),
    }
    text = f"{who} 今日运势 {score} 分 · {summary} 宜：{do}；忌：{dont}。"
    return _payload(data, text)


async def draw_lot() -> str:
    """Draw a random lot slip."""
    title, verse = random.choice(_LOTS)
    data = {"kind": "lot", "title": title, "verse": verse}
    return _payload(data, f"{title}：{verse}")


def setup(ctx: PluginContext) -> None:
    ctx.tool(
        "roll_dice",
        roll_dice,
        description="掷骰子。notation 为 NdM，例如 1d6、2d20。面数限 4/6/8/10/12/20/100。",
    )
    ctx.tool(
        "daily_fortune",
        daily_fortune,
        description="生成今日运势卡片。可选 name，同一人同一天结果稳定。",
    )
    ctx.tool(
        "draw_lot",
        draw_lot,
        description="抽一支签，返回上上/上/中/下签与短签文。无需参数。",
    )
