"""简单主题状态工具。页面样式由宿主前端插件加载器管理。"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from octop_harness.plugins import PluginContext

VERSION = "1.0.2"

_TEXT = (
    "简单主题已安装：对话、输入框、侧栏和设置页使用一致的简洁排版，"
    "浅色/深色跟随控制台外观。要临时关掉，到「插件」面板禁用 简单主题即可还原。"
)

def _payload(data: dict[str, Any], text: str) -> str:
    return json.dumps(
        {"octop_ui": {"renderer": "theme_card", "version": 1}, "data": data, "text": text},
        ensure_ascii=False,
    )


async def simple_theme_info() -> str:
    """查看 简单主题的状态，以及如何开关它。"""
    data = {
        "version": VERSION,
        "theme": "simple",
        "mode": "auto",
        "checked_at": datetime.now(tz=UTC).isoformat(),
    }
    return _payload(data, _TEXT)


def setup(ctx: PluginContext) -> None:
    ctx.tool(
        "simple_theme_info",
        simple_theme_info,
        description="查看 简单主题插件是否生效，以及如何关闭它（返回一张状态卡片）。",
    )
