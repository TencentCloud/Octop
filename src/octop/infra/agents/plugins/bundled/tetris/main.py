"""Start an in-chat Tetris board. Gameplay runs in the Dashboard UI."""

from __future__ import annotations

import json

from harness_agent.plugins import PluginContext


async def start_tetris() -> str:
    """Open a playable Tetris card. The user clicks the card, then uses keys or buttons."""
    return json.dumps(
        {
            "octop_ui": {"renderer": "tetris_game", "version": 1},
            "data": {"kind": "tetris"},
            "text": "俄罗斯方块已开始。点击卡片后用 ← → 移动、↑ 或空格旋转、↓ 加速、空格硬降。",
        },
        ensure_ascii=False,
    )


def setup(ctx: PluginContext) -> None:
    ctx.tool(
        "start_tetris",
        start_tetris,
        description=(
            "在聊天中打开可玩的俄罗斯方块。用户说要玩俄罗斯方块、tetris、方块游戏时调用。"
            "无需参数；游戏在卡片内进行，不必再调用工具。"
        ),
    )
