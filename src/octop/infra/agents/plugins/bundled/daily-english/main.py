"""Daily English vocabulary — local, date-seeded."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any

from harness_agent.plugins import PluginContext

_VOCAB: tuple[tuple[str, str, str, str], ...] = (
    (
        "serendipity",
        "/ˌserənˈdɪpəti/",
        "意外发现珍奇事物的能力",
        "Finding that café was pure serendipity.",
    ),
    (
        "resilience",
        "/rɪˈzɪliəns/",
        "韧性；恢复力",
        "Her resilience after setbacks inspired the team.",
    ),
    ("ambiguous", "/æmˈbɪɡjuəs/", "模糊的；歧义的", "The email was ambiguous about the deadline."),
    (
        "meticulous",
        "/məˈtɪkjələs/",
        "一丝不苟的",
        "He kept meticulous notes during the experiment.",
    ),
    ("pragmatic", "/præɡˈmætɪk/", "务实的", "We need a pragmatic plan, not ideals only."),
    ("eloquent", "/ˈeləkwənt/", "雄辩的", "She gave an eloquent speech at the ceremony."),
    ("obsolete", "/ˌɒbsəˈliːt/", "过时的", "Floppy disks are largely obsolete now."),
    ("hypothesis", "/haɪˈpɒθəsɪs/", "假设", "We tested the hypothesis with fresh data."),
    ("diligent", "/ˈdɪlɪdʒənt/", "勤奋的", "Diligent practice beats talent alone."),
    ("inevitable", "/ɪnˈevɪtəbl/", "不可避免的", "Change is inevitable in any startup."),
    ("authentic", "/ɔːˈθentɪk/", "真实的；正宗的", "Authentic feedback helps you grow."),
    ("curiosity", "/ˌkjʊəriˈɒsəti/", "好奇心", "Curiosity drives good research questions."),
    ("gratitude", "/ˈɡrætɪtjuːd/", "感激", "Express gratitude before you ask for more."),
    ("navigate", "/ˈnævɪɡeɪt/", "导航；应对", "Learn to navigate uncertainty calmly."),
    ("compromise", "/ˈkɒmprəmaɪz/", "妥协；折中", "Sometimes compromise keeps teams moving."),
    ("perspective", "/pəˈspektɪv/", "视角", "Try her perspective before you decide."),
    ("sustainable", "/səˈsteɪnəbl/", "可持续的", "Sustainable habits beat short bursts."),
    ("intricate", "/ˈɪntrɪkət/", "复杂精细的", "The watch has an intricate mechanism."),
    ("versatile", "/ˈvɜːsətaɪl/", "多用途的", "Python is versatile for automation."),
    ("empathy", "/ˈempəθi/", "共情", "Empathy improves difficult conversations."),
    ("concise", "/kənˈsaɪs/", "简洁的", "Keep the summary concise and clear."),
    ("deliberate", "/dɪˈlɪbərət/", "审慎的；故意的", "Make deliberate choices about scope."),
    ("fragment", "/ˈfræɡmənt/", "碎片；片段", "Break the problem into small fragments."),
    ("innovative", "/ˈɪnəveɪtɪv/", "创新的", "The team proposed an innovative fix."),
    ("tenacious", "/təˈneɪʃəs/", "顽强的", "Tenacious effort wins long projects."),
    ("priority", "/praɪˈɒrəti/", "优先级", "Set one priority for this week."),
    ("relevant", "/ˈreləvənt/", "相关的", "Only cite relevant sources."),
    ("threshold", "/ˈθreʃhəʊld/", "阈值；门槛", "Cross the error threshold and alert."),
    ("volatile", "/ˈvɒlətaɪl/", "易变的", "Markets can be volatile near news."),
    ("wholesome", "/ˈhəʊlsəm/", "有益健康的", "A wholesome routine includes sleep."),
)


def _payload(data: dict[str, Any], text: str) -> str:
    return json.dumps(
        {"octop_ui": {"renderer": "daily_english_card", "version": 1}, "data": data, "text": text},
        ensure_ascii=False,
    )


def _pick_index(seed: str) -> int:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % len(_VOCAB)


def _find_word(word: str) -> tuple[str, str, str, str] | None:
    key = word.strip().lower()
    for entry in _VOCAB:
        if entry[0].lower() == key:
            return entry
    return None


async def daily_english(word: str = "") -> str:
    """Return daily word or lookup a word from the built-in list."""
    custom = (word or "").strip()
    if custom:
        entry = _find_word(custom)
        if entry is None:
            return _payload({"error": "not found", "word": custom}, f"词库中未找到「{custom}」。")
        w, phonetic, zh, example = entry
        data = {
            "word": w,
            "phonetic": phonetic,
            "meaning_zh": zh,
            "example": example,
            "daily": False,
        }
        return _payload(data, f"{w} {phonetic} — {zh}\n例句：{example}")
    idx = _pick_index(date.today().isoformat())
    w, phonetic, zh, example = _VOCAB[idx]
    data = {
        "word": w,
        "phonetic": phonetic,
        "meaning_zh": zh,
        "example": example,
        "daily": True,
        "date": date.today().isoformat(),
    }
    return _payload(data, f"今日单词 {w} {phonetic} — {zh}")


def setup(ctx: PluginContext) -> None:
    ctx.tool(
        "daily_english",
        daily_english,
        description="每日英语一词；word 为空则按日期稳定选词，可传单词查内置词库。",
    )
