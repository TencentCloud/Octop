"""Session title generation (2026-09-06, absorbed from openresearch-cli's
one-shot title grading).

Octop used to store the full first user message as the thread title — a long
blob in Recents. This module generates a concise <=6-word title with a cheap
one-shot model call (30s budget, no tools, single system line), sanitized
before persisting. Generation is async and never blocks the turn; on failure
(failed call, timeout, upstream rate limit) the caller falls back to a
truncated first line. ``set_title_if_null`` is idempotent, so a title that was
not generated yet is retried on the next turn.

The model call goes straight to the provider via httpx (OpenAI-compatible
chat.completions) — deliberately bypassing the harness, since titling needs
neither tools nor memory.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: Input cap fed to the model (a title only needs the opening intent).
_TITLE_INPUT_CAP = 2000
#: Longest title we store — must stay aligned with the persistence path
#: (``ThreadRepo.clip_thread_title`` default ``max_len=40``, which also appends
#: ``…`` when shortened). A larger cap here would be misleading: the stored
#: title is re-clipped to 40 on write regardless.
_TITLE_MAX_CHARS = 40
#: One-shot budget — generous for a cold provider, short enough that a wedged
#: call does not linger (the fallback title is already acceptable).
_TITLE_TIMEOUT_SECONDS = 30

_TITLE_PROMPT = (
    "Generate a short title for a chat session that starts with the user "
    "message below. At most 6 words. Reply with the title text ONLY — no "
    "quotes, no trailing punctuation, no explanation, nothing else.\n\n"
    "User message:\n{input}"
)


def _sanitize_title(raw: str) -> str | None:
    """Model output -> usable title; defensive: strip wrapping quotes, trailing
    periods (twice — once outside the quotes, once inside after unquoting),
    and blank leading lines. Mirrors openresearch title.rs."""
    line = next((line_.strip() for line_ in raw.splitlines() if line_.strip()), None)
    if not line:
        return None
    # Trailing periods twice: first strips a period *outside* the quotes
    # ("Fix the redirect".), the second one *inside* them once quotes are gone.
    line = line.rstrip(".").strip()
    line = line.strip("'\"\u201c\u201d\u2018\u2019")
    line = line.rstrip(".").strip()
    title = " ".join(line.split())
    if not title:
        return None
    return title[:_TITLE_MAX_CHARS]


def _fallback_title(text: str) -> str:
    """Fallback when the model call is unavailable: first non-empty line,
    truncated to the title cap."""
    first_line = next((line_.strip() for line_ in text.splitlines() if line_.strip()), text.strip())
    return first_line[:_TITLE_MAX_CHARS]


async def _call_model(
    text: str,
    *,
    base_url: str,
    api_key: str,
    model_id: str,
) -> str | None:
    """OpenAI-compatible chat.completions, one shot, no streaming."""
    import httpx

    url = base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": "You generate short chat titles."},
            {"role": "user", "content": _TITLE_PROMPT.format(input=text[:_TITLE_INPUT_CAP])},
        ],
        "max_tokens": 60,
        "temperature": 0.3,
        "stream": False,
    }
    async with httpx.AsyncClient(timeout=_TITLE_TIMEOUT_SECONDS) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
    content = (data.get("choices") or [{}])[0].get("message", {}).get("content")
    return content if isinstance(content, str) else None


async def generate_title_async(
    text: str,
    *,
    base_url: str,
    api_key: str,
    model_id: str,
) -> str | None:
    """Generate a title: one-shot model call -> sanitize. Returns None on any
    failure so the caller falls back to a truncated line."""
    try:
        raw = await _call_model(text, base_url=base_url, api_key=api_key, model_id=model_id)
        if not raw:
            return None
        return _sanitize_title(raw)
    except Exception as exc:  # noqa: BLE001 - titling must never break the turn
        logger.debug("title generation failed (fallback): %s", exc)
        return None


__all__ = [
    "generate_title_async",
    "_sanitize_title",
    "_fallback_title",
    "_TITLE_MAX_CHARS",
]
