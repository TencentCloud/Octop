"""Telegram 表格渲染补丁：把 Markdown 表格转为列对齐的代码块。

Telegram Bot API 没有表格语法，GFM 竖线表格在比例字体下排版错乱。
这里在发送前把表格重排为列对齐的 ``` 代码块（Telegram 内为 <pre> 等宽
渲染），再交给 gateway 官方的 markdown_to_telegram_html 处理。

install() 会同时重绑 ``octop_gateway.channels.telegram.format_html`` 与
``...telegram.channel`` 两个模块里的 markdown_to_telegram_html ——后者是
from-import 绑定，只改前者不生效。
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable

_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_ROW_SPLIT_RE = re.compile(r"(?<!\\)\|")
_SEPARATOR_CELL_RE = re.compile(r"^:?\-{2,}:?$")
_PLACEHOLDER = "\x00TBL{}\x00"


def _display_width(text: str) -> int:
    """CJK 等全宽字符按 2 列计，与等宽字体实际占位一致。"""
    return sum(2 if unicodedata.east_asian_width(char) in "WF" else 1 for char in text)


def _pad(text: str, width: int, align: str) -> str:
    gap = width - _display_width(text)
    if gap <= 0:
        return text
    if align == "right":
        return " " * gap + text
    if align == "center":
        left = gap // 2
        return " " * left + text + " " * (gap - left)
    return text + " " * gap


def _split_row(line: str) -> list[str]:
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|"):
        body = body[:-1]
    return [cell.replace("\\|", "|").strip() for cell in _ROW_SPLIT_RE.split(body)]


def _is_separator_row(cells: list[str]) -> bool:
    return bool(cells) and all(_SEPARATOR_CELL_RE.match(cell) for cell in cells if cell != "")


def _alignments(cells: list[str]) -> list[str]:
    result = []
    for cell in cells:
        left = cell.startswith(":")
        right = cell.endswith(":")
        if left and right:
            result.append("center")
        elif right:
            result.append("right")
        else:
            result.append("left")
    return result


def _render_table(rows: list[list[str]]) -> str:
    header, separator = rows[0], rows[1]
    columns = len(header)
    aligns = _alignments(separator)
    while len(aligns) < columns:
        aligns.append("left")
    # 分隔行只用于列对齐方式，不参与渲染
    body = [row + [""] * (columns - len(row)) for row in [header, *rows[2:]]]
    body = [row[:columns] for row in body]
    widths = [max(_display_width(row[col]) for row in body) for col in range(columns)]
    lines = []
    for row_index, row in enumerate(body):
        line = " | ".join(_pad(row[col], widths[col], aligns[col]) for col in range(columns))
        lines.append(line.rstrip() if row_index > 0 else line)
        if row_index == 0:
            lines.append("-+-".join("-" * width for width in widths))
    return "```\n" + "\n".join(lines) + "\n```"


def convert_markdown_tables(
    text: str, *, renderer: Callable[[list[list[str]]], str] = _render_table
) -> str:
    """把文本中的 GFM 表格经 renderer 重渲染；代码围栏内的内容不动。"""
    if "|" not in text:
        return text

    fences: list[str] = []

    def _stash(match: re.Match[str]) -> str:
        placeholder = _PLACEHOLDER.format(len(fences))
        fences.append(match.group(0))
        return placeholder

    masked = _FENCE_RE.sub(_stash, text)

    lines = masked.split("\n")
    result: list[str] = []
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        if stripped.startswith("|") and stripped.endswith("|") and "|" in stripped[1:-1]:
            block: list[list[str]] = []
            while index < len(lines):
                stripped = lines[index].strip()
                if not (stripped.startswith("|") and stripped.endswith("|")):
                    break
                block.append(_split_row(stripped))
                index += 1
            if len(block) >= 2 and _is_separator_row(block[1]):
                result.append(renderer(block))
            else:
                result.extend(lines[index - len(block) : index])
        else:
            result.append(lines[index])
            index += 1

    converted = "\n".join(result)
    for position, fence in enumerate(fences):
        converted = converted.replace(_PLACEHOLDER.format(position), fence)
    return converted


def has_gfm_table(text: str) -> bool:
    """文本是否含代码围栏外的 GFM 表格（决定能否走原生 rich message）。"""
    return convert_markdown_tables(text, renderer=lambda rows: "") != text


def install() -> None:
    """两层策略：表格优先原生 sendRichMessage，失败回退代码块渲染。

    - 包装 TelegramChannel._send_text：含 GFM 表格的消息整条经
      Bot API 10.1 ``sendRichMessage``（rich_message.markdown）发送，
      客户端原生渲染表格；任何失败回退原发送路径（代码块对齐方案）。
    - 保留 markdown_to_telegram_html 包裹：回退路径仍把表格转代码块。
    重复调用安全。
    """
    try:
        from octop_gateway.channels.telegram import channel as gateway_channel
        from octop_gateway.channels.telegram import format_html as gateway_format_html
        from octop_gateway.channels.telegram.channel import TelegramChannel
    except ImportError:  # gateway 未安装时静默跳过
        return

    if getattr(gateway_format_html.markdown_to_telegram_html, "__wrapped_base__", None):
        return

    base = gateway_format_html.markdown_to_telegram_html

    def markdown_to_telegram_html(text: str) -> str:
        return base(convert_markdown_tables(text)) if text else text

    markdown_to_telegram_html.__wrapped_base__ = base  # type: ignore[attr-defined]
    gateway_format_html.markdown_to_telegram_html = markdown_to_telegram_html
    gateway_channel.markdown_to_telegram_html = markdown_to_telegram_html

    base_send_text = TelegramChannel._send_text

    async def send_text(self, subject, text):  # type: ignore[no-untyped-def]
        if text and self._app and has_gfm_table(text):
            chat_id = subject.metadata.get("chat_id") if subject else None
            try:
                await self._app.bot._post(
                    "sendRichMessage",
                    {
                        "chat_id": int(chat_id) if chat_id else int(subject.subject_id),
                        "rich_message": {"markdown": text},
                    },
                )
                return
            except Exception:  # noqa: BLE001 任何失败都回退到代码块方案
                pass
        return await base_send_text(self, subject, text)

    send_text.__wrapped_base__ = base_send_text  # type: ignore[attr-defined]
    TelegramChannel._send_text = send_text  # type: ignore[method-assign]
