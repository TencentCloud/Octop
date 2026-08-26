"""Tic-tac-toe and number guessing — state is passed in tool args."""

from __future__ import annotations

import json
import random
from typing import Any

from harness_agent.plugins import PluginContext

_WINS = (
    (0, 1, 2),
    (3, 4, 5),
    (6, 7, 8),
    (0, 3, 6),
    (1, 4, 7),
    (2, 5, 8),
    (0, 4, 8),
    (2, 4, 6),
)


def _payload(data: dict[str, Any], text: str) -> str:
    return json.dumps(
        {"octop_ui": {"renderer": "mini_game_card", "version": 1}, "data": data, "text": text},
        ensure_ascii=False,
    )


def _winner(board: str) -> str:
    for a, b, c in _WINS:
        if board[a] != "." and board[a] == board[b] == board[c]:
            return board[a]
    if "." not in board:
        return "draw"
    return ""


async def tic_tac_toe(board: str = ".........", play_as: str = "X") -> str:
    """Render a tic-tac-toe board. board is 9 chars of .XO."""
    raw = (board or ".........")[:9].ljust(9, ".")
    cleaned = "".join(ch if ch in "XO." else "." for ch in raw)
    mark = (play_as or "X").strip().upper()
    if mark not in {"X", "O"}:
        mark = "X"
    result = _winner(cleaned)
    data = {"kind": "tictactoe", "board": cleaned, "play_as": mark, "result": result}
    if result == "draw":
        text = "井字棋：平局。"
    elif result:
        text = f"井字棋：{result} 获胜。"
    else:
        text = f"井字棋棋盘 {cleaned}，轮到 {mark}。"
    return _payload(data, text)


async def guess_number(
    low: int = 1,
    high: int = 100,
    guess: int | None = None,
    secret: int | None = None,
) -> str:
    """Compare guess against secret. Never echo secret in data or text."""
    lo = int(low or 1)
    hi = int(high or 100)
    if lo >= hi:
        lo, hi = 1, 100
    target = int(secret) if secret is not None else random.randint(lo, hi)
    if guess is None:
        return _payload(
            {"kind": "guess", "low": lo, "high": hi, "hint": "start"},
            f"我想了一个 {lo} 到 {hi} 之间的整数，请猜。",
        )
    n = int(guess)
    if n < target:
        hint = "low"
        text = f"{n} 太小了，再往大猜（{lo}–{hi}）。"
    elif n > target:
        hint = "high"
        text = f"{n} 太大了，再往小猜（{lo}–{hi}）。"
    else:
        hint = "equal"
        text = f"猜中了：{n}。"
    return _payload(
        {"kind": "guess", "low": lo, "high": hi, "guess": n, "hint": hint},
        text,
    )


def setup(ctx: PluginContext) -> None:
    ctx.tool(
        "tic_tac_toe",
        tic_tac_toe,
        description=(
            "井字棋。board 为 9 个字符（.XO），play_as 为 X 或 O。"
            "用户下子后把更新后的 board 再传入。"
        ),
    )
    ctx.tool(
        "guess_number",
        guess_number,
        description=(
            "猜数字。先不传 guess 开始游戏；之后传入 guess。"
            "请在多轮中自己记住 secret 并作为参数传入，不要把 secret 告诉用户。"
        ),
    )
