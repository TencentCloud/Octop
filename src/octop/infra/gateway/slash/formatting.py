"""Format helpers for slash /status output."""

from __future__ import annotations

import time
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def format_unix_datetime(ts: int, timezone: str) -> str:
    """Format unix seconds as ``YYYY-MM-DD HH:MM:SS`` in *timezone*."""
    try:
        tz = ZoneInfo(timezone)
    except ZoneInfoNotFoundError:
        tz = ZoneInfo("UTC")
    return datetime.fromtimestamp(int(ts), tz=tz).strftime("%Y-%m-%d %H:%M:%S")


def format_duration(seconds: int) -> str:
    """Human-readable uptime like ``2d 3h 15m``."""
    if seconds < 0:
        seconds = 0
    days, rem = divmod(seconds, 86_400)
    hours, rem = divmod(rem, 3_600)
    minutes, _ = divmod(rem, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes or not parts:
        parts.append(f"{minutes}m")
    return " ".join(parts)


def server_uptime_label(started_at: int | None) -> str:
    if started_at is None:
        return "unknown"
    return format_duration(int(time.time()) - started_at)


def markdown_kv_block(title: str, rows: list[tuple[str, str]]) -> str:
    """Markdown bullet list — renders with line breaks in chat UIs."""
    lines = [f"**{title}**", ""]
    lines.extend(f"- **{key}**: {value}" for key, value in rows)
    return "\n".join(lines)


def markdown_grouped_list(title: str, sections: list[tuple[str, list[str]]]) -> str:
    """Title plus multiple titled bullet sections (for categorized /help)."""
    lines = [f"**{title}**", ""]
    for i, (section_title, bullets) in enumerate(sections):
        if i > 0:
            lines.append("")
        lines.append(f"**{section_title}**")
        lines.extend(f"- {item}" for item in bullets)
    return "\n".join(lines)


def markdown_bullets(title: str, bullets: list[str]) -> str:
    lines = [f"**{title}**", ""]
    lines.extend(f"- {item}" for item in bullets)
    return "\n".join(lines)
