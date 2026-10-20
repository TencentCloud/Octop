"""Token / char budget allocator (D45-A static char proxy).

Charge model:
- Chinese / CJK characters: 2 chars per token (Unicode block U+4E00-U+9FFF
  approximately covers CJK Unified Ideographs).
- ASCII / Latin / digit characters: 4 chars per token.
- Mixed text: per-character classification, then sum.

This is a static proxy. The real LLM tokenizer will disagree by
±10-20%, but on the recall path we only need to decide which atoms
fit into the budget; a coarse over-estimate is fine because we set
a defensive default total budget (1500 tokens) well below the
host's actual prompt window.

The allocator also supports the D18 bucket split (atoms 70% / quotes
20% / reserved page headlines 10%). The current gather path charges
atom and raw snippets; the page-headline bucket remains reserved.
Caller pushes snippets in priority order (post-rerank), and the
allocator stops accepting once bucket caps are reached.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# ---------------------------------------------------------------------------
# Char-to-token estimation (D45-A)
# ---------------------------------------------------------------------------

CHARS_PER_TOKEN_CJK = 2
"""Roughly 2 Chinese / Japanese / Korean characters per token."""

CHARS_PER_TOKEN_ASCII = 4
"""Roughly 4 ASCII / Latin characters per token."""

# CJK Unified Ideographs block (covers most Chinese, plus shared Han chars
# used in Japanese kanji / Korean hanja). We deliberately keep this narrow:
# Hiragana / Katakana / Hangul could also be added, but the dogfood data
# is overwhelmingly Chinese + English so we don't optimise for them yet.
_CJK_START = 0x4E00
_CJK_END = 0x9FFF


def estimate_tokens(text: str) -> int:
    """Estimate prompt-token count for ``text`` using the static char proxy.

    Mixed-language strings are handled by summing CJK chars / 2 and
    ASCII chars / 4 separately, then ``ceil``ing each bucket. Returns
    an integer >= 0; empty input returns 0.
    """
    if not text:
        return 0
    cjk = 0
    other = 0
    for ch in text:
        cp = ord(ch)
        if _CJK_START <= cp <= _CJK_END:
            cjk += 1
        else:
            other += 1
    # Round up each bucket so we don't under-estimate.
    cjk_tokens = (cjk + CHARS_PER_TOKEN_CJK - 1) // CHARS_PER_TOKEN_CJK
    other_tokens = (other + CHARS_PER_TOKEN_ASCII - 1) // CHARS_PER_TOKEN_ASCII
    return cjk_tokens + other_tokens


# ---------------------------------------------------------------------------
# Budget allocator (D18)
# ---------------------------------------------------------------------------

BudgetBucket = Literal["atom", "quote", "page_headline", "raw"]
"""Which budget bucket a snippet draws from. ``raw`` is a fallback bucket
shared with ``atom`` (no separate cap). ``page_headline`` is reserved
until page gathering is implemented."""

DEFAULT_TOTAL_TOKENS = 1500
"""Soft default budget. Adapters can override; set this conservatively
because we'd rather under-recall than blow the host's prompt window."""

DEFAULT_SHARES: dict[BudgetBucket, float] = {
    "atom": 0.70,
    "quote": 0.20,
    "page_headline": 0.10,
    "raw": 0.70,  # raw shares the atom bucket — see _bucket_cap
}
"""Fraction of total tokens each bucket may consume. ``atom`` and
``raw`` deliberately share the 70% slice — raw is a fallback used
only when atom comes back light, never alongside competing atom hits.
"""


@dataclass
class BudgetState:
    """Live token-tracking state for a single recall call.

    Initialise via :func:`make_budget_state`; mutate via
    :meth:`try_charge`. The dict :attr:`bucket_used` is exposed for
    debug rendering by the CLI / dogfood scripts.
    """

    total_tokens: int
    bucket_caps: dict[BudgetBucket, int]
    bucket_used: dict[BudgetBucket, int] = field(default_factory=dict)

    @property
    def total_used(self) -> int:
        # ``raw`` and ``atom`` share, so summing the two would double-count.
        # We track per-bucket and compute the effective total via dedup.
        atom_or_raw = max(self.bucket_used.get("atom", 0), self.bucket_used.get("raw", 0))
        return atom_or_raw + self.bucket_used.get("quote", 0) + self.bucket_used.get("page_headline", 0)

    def try_charge(self, bucket: BudgetBucket, tokens: int) -> bool:
        """Attempt to consume ``tokens`` from ``bucket``.

        Returns ``True`` and mutates state on success; returns ``False``
        and leaves state unchanged if the charge would breach either
        the bucket cap or the total budget.

        Atomic at the per-call level — never partially charges.
        """
        if tokens < 0:
            raise ValueError(f"tokens must be non-negative, got {tokens}")
        if tokens == 0:
            return True
        cap = self.bucket_caps.get(bucket)
        if cap is None:
            raise ValueError(f"unknown budget bucket: {bucket!r}")
        used = self.bucket_used.get(bucket, 0)
        if used + tokens > cap:
            return False
        # raw / atom share — also enforce total
        if self.total_used + tokens > self.total_tokens:
            return False
        self.bucket_used[bucket] = used + tokens
        return True


def make_budget_state(
    *,
    total_tokens: int = DEFAULT_TOTAL_TOKENS,
    shares: dict[BudgetBucket, float] | None = None,
) -> BudgetState:
    """Build a fresh :class:`BudgetState` for one recall call.

    ``shares`` lets callers override the default 70/20/10 split. The
    map's values do NOT need to sum to 1.0 — buckets are independent
    caps that share the same total. The 70% atom/raw share is intentional.
    """
    use_shares = dict(DEFAULT_SHARES) if shares is None else shares
    caps: dict[BudgetBucket, int] = {b: int(total_tokens * frac) for b, frac in use_shares.items()}
    return BudgetState(total_tokens=total_tokens, bucket_caps=caps, bucket_used={})


__all__ = [
    "CHARS_PER_TOKEN_ASCII",
    "CHARS_PER_TOKEN_CJK",
    "DEFAULT_SHARES",
    "DEFAULT_TOTAL_TOKENS",
    "BudgetBucket",
    "BudgetState",
    "estimate_tokens",
    "make_budget_state",
]
