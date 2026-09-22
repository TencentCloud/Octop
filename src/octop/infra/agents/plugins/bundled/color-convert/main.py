"""Color format conversion — local."""

from __future__ import annotations

import json
import re
from typing import Any

from harness_agent.plugins import PluginContext

_HEX3 = re.compile(r"^#([0-9a-fA-F]{3})$")
_HEX6 = re.compile(r"^#([0-9a-fA-F]{6})$")
_RGB = re.compile(r"^\s*rgb\s*\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)\s*$", re.I)
_CSV = re.compile(r"^\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*$")


def _payload(data: dict[str, Any], text: str) -> str:
    return json.dumps(
        {"octop_ui": {"renderer": "color_convert_card", "version": 1}, "data": data, "text": text},
        ensure_ascii=False,
    )


def _clamp(v: int) -> int:
    return max(0, min(255, v))


def _parse(value: str) -> tuple[int, int, int]:
    raw = (value or "").strip()
    m = _HEX6.match(raw)
    if m:
        h = m.group(1)
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    m = _HEX3.match(raw)
    if m:
        h = m.group(1)
        return int(h[0] * 2, 16), int(h[1] * 2, 16), int(h[2] * 2, 16)
    m = _RGB.match(raw) or _CSV.match(raw)
    if m:
        return _clamp(int(m.group(1))), _clamp(int(m.group(2))), _clamp(int(m.group(3)))
    raise ValueError("无法解析颜色，支持 #RGB、#RRGGBB、rgb(r,g,b) 或 r,g,b")


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02x}{g:02x}{b:02x}".upper()


def _rgb_to_hsl(r: int, g: int, b: int) -> tuple[float, float, float]:
    rf, gf, bf = r / 255.0, g / 255.0, b / 255.0
    mx, mn = max(rf, gf, bf), min(rf, gf, bf)
    lum = (mx + mn) / 2.0
    if mx == mn:
        return 0.0, 0.0, lum * 100.0
    d = mx - mn
    s = d / (2.0 - mx - mn) if lum > 0.5 else d / (mx + mn)
    if mx == rf:
        h = (gf - bf) / d + (6.0 if gf < bf else 0.0)
    elif mx == gf:
        h = (bf - rf) / d + 2.0
    else:
        h = (rf - gf) / d + 4.0
    return h * 60.0, s * 100.0, lum * 100.0


async def convert_color(value: str) -> str:
    """Convert #hex or rgb(...) to hex, rgb, and hsl."""
    try:
        r, g, b = _parse(value)
    except ValueError as exc:
        return _payload({"error": str(exc), "input": value}, str(exc))
    hue, sat, lum_pct = _rgb_to_hsl(r, g, b)
    hexv = _rgb_to_hex(r, g, b)
    data = {
        "input": value,
        "hex": hexv,
        "rgb": {"r": r, "g": g, "b": b},
        "hsl": {"h": round(hue, 1), "s": round(sat, 1), "l": round(lum_pct, 1)},
    }
    text = f"{hexv} · rgb({r},{g},{b}) · hsl({data['hsl']['h']},{data['hsl']['s']}%,{data['hsl']['l']}%)"
    return _payload(data, text)


def setup(ctx: PluginContext) -> None:
    ctx.tool(
        "convert_color",
        convert_color,
        description="颜色格式转换。value 可为 #RGB、#RRGGBB、rgb(r,g,b) 或 r,g,b。",
    )
