"""TurnRequest / TurnOutcome —— 与 nong_gateway.hosts 同形状（避免循环依赖）。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TurnRequest:
    session: str
    text: str
    title: str = ""
    media: list = field(default_factory=list)


@dataclass
class TurnOutcome:
    ok: bool
    text: str = ""
    error: str = ""
