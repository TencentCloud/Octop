"""QQ/微信表格渲染补丁：把 Markdown 表格降维为键值列表。

这两个通道没有可靠的等宽渲染（微信 iLink 是纯文本，QQ 官方 bot 的
markdown 子集不保证 GFM 表格/代码块），列对齐在比例字体下必然错乱。
比例字体下唯一可靠的表格呈现方式是逐行键值化，因此把表格重写为
"- 列名=值 | 列名=值" 的列表行，行内可自由折行、无跨行对齐依赖。

所有文本出站路径都经过 BaseChannel._send_text（push/reply 同样），
QQ 的 _send_content 另有一条文本旁路，一并包裹。
"""

from __future__ import annotations

from octop.infra.gateway.channels.telegram_table_format import convert_markdown_tables

_MARK = "__octop_table_plain__"


def _render_plain_rows(rows: list[list[str]]) -> str:
    """表格 → 键值列表行：表头带入每个字段，跳过空值。"""
    header = rows[0]
    columns = len(header)
    lines = []
    for row in rows[2:]:
        row = (row + [""] * columns)[:columns]
        fields = [f"{header[col]}={row[col]}" for col in range(columns) if row[col] != ""]
        if fields:
            lines.append("- " + " | ".join(fields))
    return chr(10).join(lines)


def convert_tables_to_plain(text: str) -> str:
    """把文本中的 GFM 表格转换为键值列表；代码围栏内的内容不动。"""
    return convert_markdown_tables(text, renderer=_render_plain_rows)


def install() -> None:
    """包裹 QQ/微信通道的文本发送；重复调用安全。"""
    try:
        from octop_gateway.channels.qq.channel import QQChannel
        from octop_gateway.channels.weixin.channel import WeixinChannel
        from octop_gateway.models import TextContent
    except ImportError:  # 通道模块不存在时静默跳过
        return

    if getattr(QQChannel._send_text, _MARK, False):
        return

    base_qq_send_text = QQChannel._send_text

    async def qq_send_text(self, subject, text):  # type: ignore[no-untyped-def]
        return await base_qq_send_text(
            self, subject, convert_tables_to_plain(text) if text else text
        )

    qq_send_text.__octop_table_plain__ = True  # type: ignore[attr-defined]
    QQChannel._send_text = qq_send_text  # type: ignore[method-assign]

    base_qq_send_content = QQChannel._send_content

    async def qq_send_content(self, subject, parts):  # type: ignore[no-untyped-def]
        parts = [
            part.model_copy(update={"text": convert_tables_to_plain(part.text)})
            if isinstance(part, TextContent) and part.text
            else part
            for part in parts
        ]
        return await base_qq_send_content(self, subject, parts)

    qq_send_content.__octop_table_plain__ = True  # type: ignore[attr-defined]
    QQChannel._send_content = qq_send_content  # type: ignore[method-assign]

    base_weixin_send_text = WeixinChannel._send_text

    async def weixin_send_text(self, subject, text):  # type: ignore[no-untyped-def]
        return await base_weixin_send_text(
            self, subject, convert_tables_to_plain(text) if text else text
        )

    weixin_send_text.__octop_table_plain__ = True  # type: ignore[attr-defined]
    WeixinChannel._send_text = weixin_send_text  # type: ignore[method-assign]
