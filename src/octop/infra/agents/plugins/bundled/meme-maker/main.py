"""Meme images via memegen.link."""

from __future__ import annotations

import json
from typing import Any

import httpx
from harness_agent.plugins import PluginContext

_TEMPLATES: tuple[tuple[str, str, str], ...] = (
    ("doge", "Doge", "经典柴犬"),
    ("buzz", "Buzz Lightyear", "巴斯光年"),
    ("drake", "Drake Hotline Bling", "德雷克二选一"),
    ("success", "Success Kid", "成功小孩"),
    ("distracted", "Distracted Boyfriend", "分心男友"),
)


def _payload(data: dict[str, Any], text: str, renderer: str = "meme_maker_card") -> str:
    return json.dumps(
        {"octop_ui": {"renderer": renderer, "version": 1}, "data": data, "text": text},
        ensure_ascii=False,
    )


def _encode_segment(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return "_"
    out: list[str] = []
    for ch in raw:
        if ch == "-":
            out.append("--")
        elif ch == "_":
            out.append("__")
        elif ch == " ":
            out.append("_")
        elif ch == "?":
            out.append("~q")
        elif ch == "&":
            out.append("~a")
        elif ch == "#":
            out.append("~h")
        elif ch == "%":
            out.append("~p")
        else:
            out.append(ch)
    return "".join(out)


async def make_meme(template: str = "doge", top: str = "", bottom: str = "") -> str:
    """Build a meme image URL from template id and top/bottom text."""
    tpl = (template or "doge").strip().lower()
    top_seg = _encode_segment(top)
    bottom_seg = _encode_segment(bottom)
    image_url = f"https://api.memegen.link/images/{tpl}/{top_seg}/{bottom_seg}.png"
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            resp = client.head(image_url)
            if resp.status_code >= 400:
                resp = client.get(image_url)
            if resp.status_code >= 400:
                return _payload(
                    {"error": f"HTTP {resp.status_code}", "template": tpl},
                    f"模板「{tpl}」可能不存在。",
                )
    except Exception as exc:
        return _payload({"error": str(exc), "template": tpl}, f"梗图生成失败：{exc}")
    data = {"template": tpl, "top": top, "bottom": bottom, "image_url": image_url}
    return _payload(data, f"梗图 {tpl}：{image_url}")


async def list_meme_templates() -> str:
    """List built-in meme template ids."""
    items = [{"id": t[0], "name": t[1], "hint": t[2]} for t in _TEMPLATES]
    data = {"items": items}
    lines = [f"{r['id']} — {r['name']}" for r in items]
    return _payload(data, "可用模板：\n" + "\n".join(lines), renderer="meme_templates_list")


def setup(ctx: PluginContext) -> None:
    ctx.tool(
        "make_meme",
        make_meme,
        description="生成梗图。template 如 doge/drake；top/bottom 为上下文案。",
    )
    ctx.tool(
        "list_meme_templates",
        list_meme_templates,
        description="列出内置 memegen 模板 id。",
    )
