"""Slack-off calendar: weekend / holiday countdown (China mainland holidays)."""

from __future__ import annotations

import json
import random
from datetime import date
from typing import Any

from harness_agent.plugins import PluginContext

# (start, end inclusive, name)
_HOLIDAYS: list[tuple[date, date, str]] = [
    (date(2025, 10, 1), date(2025, 10, 8), "国庆中秋"),
    (date(2026, 1, 1), date(2026, 1, 3), "元旦"),
    (date(2026, 2, 15), date(2026, 2, 23), "春节"),
    (date(2026, 4, 4), date(2026, 4, 6), "清明"),
    (date(2026, 5, 1), date(2026, 5, 5), "劳动节"),
    (date(2026, 6, 19), date(2026, 6, 21), "端午"),
    (date(2026, 9, 25), date(2026, 9, 27), "中秋"),
    (date(2026, 10, 1), date(2026, 10, 7), "国庆"),
]

_DO = ("多喝水", "站起来活动", "把待办写成三条", "听一首歌缓一缓", "回复重要消息")
_DONT = ("连续开会不喝水", "假装很忙刷短视频", "把锅甩给周五的自己", "空腹喝咖啡续命")


def _payload(data: dict[str, Any], text: str) -> str:
    return json.dumps(
        {
            "octop_ui": {"renderer": "slack_calendar_card", "version": 1},
            "data": data,
            "text": text,
        },
        ensure_ascii=False,
    )


def _days_until_weekend(today: date) -> int:
    return (5 - today.weekday()) % 7


def _next_holiday(today: date) -> tuple[str, int] | None:
    best: tuple[str, int] | None = None
    for start, end, name in _HOLIDAYS:
        if end < today:
            continue
        if start <= today <= end:
            return (f"{name}假期中", 0)
        delta = (start - today).days
        if best is None or delta < best[1]:
            best = (name, delta)
    return best


async def slack_calendar() -> str:
    """Today's fish-touching calendar card."""
    today = date.today()
    to_weekend = _days_until_weekend(today)
    holiday = _next_holiday(today)
    weekday = "一二三四五六日"[today.weekday()]
    do = random.choice(_DO)
    dont = random.choice(_DONT)
    data = {
        "date": today.isoformat(),
        "weekday": weekday,
        "days_to_weekend": to_weekend,
        "holiday_name": holiday[0] if holiday else None,
        "days_to_holiday": holiday[1] if holiday else None,
        "do": do,
        "dont": dont,
    }
    parts = [f"今天周{weekday}"]
    if to_weekend == 0:
        parts.append("已到周末，合法摸鱼")
    else:
        parts.append(f"距周末还有 {to_weekend} 天")
    if holiday:
        if holiday[1] == 0:
            parts.append(holiday[0])
        else:
            parts.append(f"距{holiday[0]}还有 {holiday[1]} 天")
    parts.append(f"宜：{do}；忌：{dont}")
    return _payload(data, " · ".join(parts))


def setup(ctx: PluginContext) -> None:
    ctx.tool(
        "slack_calendar",
        slack_calendar,
        description="摸鱼日历：距周末/节假日倒计时与今日宜忌。无需参数。",
    )
