"""出站消息体增强：把回复文本里的 @提及 编码成元宝的结构化 at 元素。

为什么：agent 回复里手打的 "@元宝" / "@分身助手" 是纯文本，App 端不解析为真 at
（用户实测："它 at 元宝没有效果"——其实元宝 App 对纯文本 @ 也会接，但不稳定、
且 mentions 字段为空）。2026-09-17 抓帧拿到真 at 的结构（入站）：

    {"elem_type": 1002, "text": "@元宝", "user_id": "szUvRH8s…=", "content": ""}

出站按对称结构编码：TIMCustomElem(msg_content.data=上述 JSON) + 后续 TIMTextElem。
文本里 "@名字" 的每个出现位置替换为一个 at 元素 + 其后文本段。

user_id 从哪来：入站帧里见过的 (名字 → user_id) 映射（bridge 的学自己的名字机制同款）。
配置 mentionTargets: {"元宝": "szUvRH8s…=", "分身助手": "bot_63d0…"}——静态配；
动态学到的（入站帧里 at 过的名字）优先于静态配置。
"""

from __future__ import annotations

import json
import re
from typing import Callable

MSG_TYPE_TEXT = "TIMTextElem"
MSG_TYPE_CUSTOM = "TIMCustomElem"
ELEM_TYPE_AT = 1002

YuanbaoMessageBody = list   # 元素为 dict 的消息体序列


def _encode_text_part(text: str) -> list:
    return [{"msg_type": MSG_TYPE_TEXT, "msg_content": {"text": text}}]

# 匹配 @名字（名字允许中文/字母/数字/下划线/连字符，非贪婪到空白或标点）
AT_MENTION_RE = re.compile(r"@([\w\u4e00-\u9fff\-]+)")


def _encode_at_element(name: str, user_id: str) -> dict:
    """按入站帧对称结构编一个 at 元素。text 约定为 "@名字"（与入站一致）。"""
    return {
        "msg_type": MSG_TYPE_CUSTOM,
        "msg_content": {"data": json.dumps({
            "elem_type": ELEM_TYPE_AT,
            "text": name,   # 平台帧 text=纯名字（@ 字符留在文本段，2026-09-17 抓帧）
            "user_id": user_id,
            "content": "",
        }, ensure_ascii=False, separators=(",", ":"))},
    }


def encode_text_with_mentions(text: str, targets: dict[str, str]) -> YuanbaoMessageBody:
    """把文本里的 @<已知名字> 编成结构化 at 元素序列。

    targets: {名字: user_id}。未知的 @（不在 targets 里）保持纯文本不动。
    纯文本路径（targets 空或无命中）与 encode_text_body 完全等价。
    """
    if not targets:
        return _encode_text_part(text)
    parts: YuanbaoMessageBody = []
    pos = 0
    encoded = False
    for m in AT_MENTION_RE.finditer(text):
        name = m.group(1)
        uid = targets.get(name)
        if not uid:
            continue
        before = text[pos:m.end()]     # 平台实测矩阵（2026-09-18）：
                                       #  全名版 → at 元素**到达**（唯一有效），App 或渲染成重复名
                                       #  只留 @ / 无 @ → 元素被平台剥（文本照发）
                                       # 结论：**必须保留全名**——平台校验 TXT 与 AT 的配对。
        if before:
            parts.extend(_encode_text_part(before))
        parts.append(_encode_at_element(name, uid))
        pos = m.end()          # @名字 整段被 at 元素替代（App 端自己渲染 @）
        encoded = True
    if not encoded:
        return _encode_text_part(text)
    tail = text[pos:]
    if tail:
        parts.extend(_encode_text_part(tail))
    return parts


def build_targets(static: dict[str, str] | None,
                  learned: Callable[[], dict[str, str]] | None = None) -> dict[str, str]:
    """合并静态配置与运行期学到的映射（学到的优先：动态更新不用改配置）。"""
    out: dict[str, str] = {}
    for k, v in (static or {}).items():
        if k and v:
            out[str(k)] = str(v)
    try:
        for k, v in (learned() if learned else {}).items():
            if k and v:
                out[str(k)] = str(v)
    except Exception:
        pass
    return out
