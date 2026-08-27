"""Pomodoro and countdown cards — timing runs in the Dashboard UI."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from harness_agent.plugins import PluginContext


def _payload(data: dict[str, Any], text: str) -> str:
    return json.dumps(
        {"octop_ui": {"renderer": "timer_card", "version": 1}, "data": data, "text": text},
        ensure_ascii=False,
    )


async def start_pomodoro(minutes: int = 25, label: str = "专注") -> str:
    """Start a focus timer. The chat card counts down locally."""
    mins = max(1, min(int(minutes or 25), 180))
    title = (label or "专注").strip() or "专注"
    started = datetime.now(tz=UTC).isoformat()
    data = {
        "kind": "pomodoro",
        "label": title,
        "duration_sec": mins * 60,
        "started_at": started,
        "paused": False,
    }
    return _payload(data, f"已开始 {mins} 分钟番茄钟：{title}")


async def start_countdown(title: str, target_iso: str) -> str:
    """Count down to an ISO-8601 datetime."""
    name = (title or "").strip() or "倒数"
    raw = (target_iso or "").strip()
    if not raw:
        return _payload({"kind": "countdown", "error": "target required"}, "请提供 target_iso。")
    try:
        datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return _payload(
            {"kind": "countdown", "error": "invalid datetime"},
            "target_iso 需要 ISO 时间，例如 2026-12-31T18:00:00+08:00。",
        )
    data = {"kind": "countdown", "title": name, "target_iso": raw}
    return _payload(data, f"倒数「{name}」目标 {raw}")


def setup(ctx: PluginContext) -> None:
    ctx.tool(
        "start_pomodoro",
        start_pomodoro,
        description="开始番茄钟。minutes 默认 25（1–180），label 为显示名称。",
    )
    ctx.tool(
        "start_countdown",
        start_countdown,
        description="倒数到某个时间。title 为标题，target_iso 为 ISO 日期时间。",
    )
