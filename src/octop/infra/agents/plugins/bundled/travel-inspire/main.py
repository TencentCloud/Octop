"""Travel destination inspiration — local."""

from __future__ import annotations

import hashlib
import json
import random
from datetime import date
from typing import Any

from harness_agent.plugins import PluginContext

_DESTINATIONS: tuple[dict[str, Any], ...] = (
    {
        "city": "京都",
        "country": "日本",
        "blurb": "庭园、神社与和食，适合慢行。",
        "best_season": "3–5 月、10–11 月",
        "tags": ["city", "food", "nature"],
    },
    {
        "city": "皇后镇",
        "country": "新西兰",
        "blurb": "湖泊与雪山，户外运动天堂。",
        "best_season": "12–2 月（南半球夏）",
        "tags": ["nature", "sea"],
    },
    {
        "city": "里斯本",
        "country": "葡萄牙",
        "blurb": "电车、海风和蛋挞，物价友好。",
        "best_season": "4–6 月、9–10 月",
        "tags": ["city", "sea", "food"],
    },
    {
        "city": "清迈",
        "country": "泰国",
        "blurb": "夜市、寺庙与咖啡，轻松度假。",
        "best_season": "11–2 月",
        "tags": ["food", "city", "nature"],
    },
    {
        "city": "雷克雅未克",
        "country": "冰岛",
        "blurb": "极光、温泉与黑沙滩。",
        "best_season": "9–3 月看极光；6–8 月环岛",
        "tags": ["nature", "sea"],
    },
    {
        "city": "巴塞罗那",
        "country": "西班牙",
        "blurb": "高迪建筑与 tapas 小馆。",
        "best_season": "5–6 月、9 月",
        "tags": ["city", "food", "sea"],
    },
    {
        "city": "桂林",
        "country": "中国",
        "blurb": "漓江山水，适合竹筏与骑行。",
        "best_season": "4–10 月",
        "tags": ["nature"],
    },
    {
        "city": "马尔代夫",
        "country": "马尔代夫",
        "blurb": "水上屋与潜水，纯海岛放松。",
        "best_season": "11–4 月",
        "tags": ["sea"],
    },
    {
        "city": "成都",
        "country": "中国",
        "blurb": "火锅、茶馆与大熊猫基地。",
        "best_season": "3–5 月、9–11 月",
        "tags": ["food", "city"],
    },
    {
        "city": "温哥华",
        "country": "加拿大",
        "blurb": "山海与城市公园并存。",
        "best_season": "6–9 月",
        "tags": ["nature", "city", "sea"],
    },
    {
        "city": "伊斯坦布尔",
        "country": "土耳其",
        "blurb": "欧亚交汇，市集与清真寺。",
        "best_season": "4–5 月、9–10 月",
        "tags": ["city", "food"],
    },
    {
        "city": "大堡礁",
        "country": "澳大利亚",
        "blurb": "潜水与海岛跳岛。",
        "best_season": "6–10 月",
        "tags": ["sea", "nature"],
    },
)


def _payload(data: dict[str, Any], text: str) -> str:
    return json.dumps(
        {"octop_ui": {"renderer": "travel_inspire_card", "version": 1}, "data": data, "text": text},
        ensure_ascii=False,
    )


def _filter_mood(mood: str) -> list[dict[str, Any]]:
    key = (mood or "").strip().lower()
    if not key:
        return list(_DESTINATIONS)
    return [d for d in _DESTINATIONS if key in d.get("tags", [])] or list(_DESTINATIONS)


async def travel_inspire(mood: str = "") -> str:
    """Pick a destination; optional mood tag: sea, city, nature, food."""
    pool = _filter_mood(mood)
    seed = f"{date.today().isoformat()}|{mood.strip().lower()}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    rng = random.Random(int(digest[:16], 16))
    pick = rng.choice(pool)
    data = {**pick, "mood": (mood or "").strip()}
    text = f"推荐：{pick['city']}（{pick['country']}）— {pick['blurb']} 最佳：{pick['best_season']}"
    return _payload(data, text)


def setup(ctx: PluginContext) -> None:
    ctx.tool(
        "travel_inspire",
        travel_inspire,
        description="旅行目的地灵感。mood 可选 sea/city/nature/food 过滤标签。",
    )
