"""What to eat — local meal suggestions."""

from __future__ import annotations

import hashlib
import json
import random
from datetime import date
from typing import Any

from harness_agent.plugins import PluginContext

_MEALS: dict[str, tuple[str, ...]] = {
    "breakfast": ("豆浆油条", "小笼包", "粥配咸菜", "三明治", "燕麦酸奶"),
    "lunch": ("黄焖鸡", "兰州拉面", "麻辣香锅", "轻食沙拉", "咖喱饭", "盖浇饭"),
    "dinner": ("火锅", "烧烤", "寿司", "家常菜三素一荤", "披萨", "越南粉"),
    "snack": ("奶茶", "鸡排", "水果拼盘", "关东煮", "冰淇淋"),
}

_SPICY = ("重庆小面", "水煮鱼", "新疆炒米粉", "湘菜小炒", "麻辣烫")
_MILD = ("粤式烧腊", "日式定食", "苏式汤面", "泰式冬阴功（微辣）", "意大利面")


def _payload(data: dict[str, Any], text: str) -> str:
    return json.dumps(
        {"octop_ui": {"renderer": "what_to_eat_card", "version": 1}, "data": data, "text": text},
        ensure_ascii=False,
    )


async def what_to_eat(meal: str = "lunch", spicy: bool | None = None) -> str:
    """Suggest a dish. meal: breakfast/lunch/dinner/snack; spicy True/False optional."""
    key = (meal or "lunch").strip().lower()
    pool = list(_MEALS.get(key, _MEALS["lunch"]))
    if spicy is True:
        pool = list(_SPICY) + pool
    elif spicy is False:
        pool = list(_MILD) + pool
    seed = f"{date.today().isoformat()}|{key}|{spicy}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    rng = random.Random(int(digest[:16], 16))
    dish = rng.choice(pool)
    data = {"meal": key, "dish": dish, "spicy": spicy}
    return _payload(data, f"{key} 推荐：{dish}")


def setup(ctx: PluginContext) -> None:
    ctx.tool(
        "what_to_eat",
        what_to_eat,
        description="随机推荐吃什么。meal 为 breakfast/lunch/dinner/snack；spicy 可选偏辣/偏淡。",
    )
