"""Generate a QR code PNG data URL with segno."""

from __future__ import annotations

import base64
import json
from io import BytesIO
from typing import Any

import segno
from harness_agent.plugins import PluginContext

_MAX_LEN = 2048


def _payload(data: dict[str, Any], text: str) -> str:
    return json.dumps(
        {"octop_ui": {"renderer": "qrcode_card", "version": 1}, "data": data, "text": text},
        ensure_ascii=False,
    )


async def make_qrcode(content: str, scale: int = 8) -> str:
    """Encode text or a URL as a QR code image."""
    text = (content or "").strip()
    if not text:
        return _payload({"error": "content is required"}, "请提供要编码的文本或链接。")
    if len(text) > _MAX_LEN:
        return _payload(
            {"error": "too long"},
            f"内容过长（最多 {_MAX_LEN} 字符）。",
        )
    scale_n = max(2, min(int(scale or 8), 16))
    buf = BytesIO()
    segno.make(text, error="m").save(buf, kind="png", scale=scale_n)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    data_url = f"data:image/png;base64,{b64}"
    preview = text if len(text) <= 80 else text[:77] + "..."
    return _payload(
        {"content": text, "image_data_url": data_url},
        f"已生成二维码（{len(text)} 字符）：{preview}",
    )


def setup(ctx: PluginContext) -> None:
    ctx.tool(
        "make_qrcode",
        make_qrcode,
        description="把文本或 URL 生成二维码。参数 content 必填，scale 为像素倍率（2–16，默认 8）。",
    )
