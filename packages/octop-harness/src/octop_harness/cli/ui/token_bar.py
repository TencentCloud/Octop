"""Token usage progress bar renderer for the terminal."""

from __future__ import annotations


def format_token_bar(
    input_tokens: int,
    output_tokens: int,
    max_tokens: int,
    elapsed: float,
) -> str:
    """Format a compact token usage progress bar with Rich markup.

    Output format::

        [2.1s] ◑ 28% ████░░░░ 36k/128k

    Color coding:
        - <50%: green
        - 50-80%: yellow
        - >80%: red

    Args:
        input_tokens: Number of input/prompt tokens used this turn.
        output_tokens: Number of output/completion tokens this turn.
        max_tokens: Total context window size.
        elapsed: Wall-clock seconds for the turn.

    Returns:
        A Rich-markup formatted string ready for ``console.print()``.
    """
    total = input_tokens + output_tokens
    if max_tokens <= 0:
        max_tokens = 128_000

    pct = min(total / max_tokens, 1.0)
    pct_int = int(pct * 100)

    # Progress ring emoji: 4 stages
    if pct < 0.25:
        ring = "◔"  # ◔
    elif pct < 0.50:
        ring = "◑"  # ◑
    elif pct < 0.75:
        ring = "◕"  # ◕
    else:
        ring = "●"  # ●

    # Bar: 8 chars wide
    bar_width = 8
    filled = int(bar_width * pct)
    bar = "█" * filled + "░" * (bar_width - filled)

    # Token count with k suffix
    total_k = _format_k(total)
    max_k = _format_k(max_tokens)

    # Color based on percentage
    if pct < 0.50:
        color = "green"
    elif pct < 0.80:
        color = "yellow"
    else:
        color = "red"

    return f"[dim]\\[{elapsed:.1f}s][/] [{color}]{ring} {pct_int}% {bar}[/] [dim]{total_k}/{max_k}[/]"


def format_token_bar_minimal(
    input_tokens: int,
    output_tokens: int,
    elapsed: float,
) -> str:
    """Format a minimal token usage line (when max_tokens is unknown).

    Output format::

        [2.1s] ↑1.2k ↓0.5k

    Args:
        input_tokens: Number of input/prompt tokens.
        output_tokens: Number of output/completion tokens.
        elapsed: Wall-clock seconds.

    Returns:
        A Rich-markup formatted string.
    """
    in_k = _format_k(input_tokens)
    out_k = _format_k(output_tokens)
    return f"[dim]\\[{elapsed:.1f}s] ↑{in_k} ↓{out_k}[/]"


def format_token_bar_plain(
    input_tokens: int,
    output_tokens: int,
    max_tokens: int,
    elapsed: float,
) -> str:
    """Format a plain-text token bar (no Rich markup).

    Suitable for prompt_toolkit toolbars and non-Rich contexts.

    Output format::

        [2.1s] ◑ 29% ██░░░░░░ 38k/128k
    """
    total = input_tokens + output_tokens
    if max_tokens <= 0:
        max_tokens = 128_000

    pct = min(total / max_tokens, 1.0)
    pct_int = int(pct * 100)

    if pct < 0.25:
        ring = "◔"
    elif pct < 0.50:
        ring = "◑"
    elif pct < 0.75:
        ring = "◕"
    else:
        ring = "●"

    bar_width = 8
    filled = int(bar_width * pct)
    bar = "█" * filled + "░" * (bar_width - filled)

    total_k = _format_k(total)
    max_k = _format_k(max_tokens)

    return f"[{elapsed:.1f}s] {ring} {pct_int}% {bar} {total_k}/{max_k}"


def _format_k(n: int) -> str:
    """Format a number with k suffix for thousands."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}k"
    return str(n)


__all__ = ["format_token_bar", "format_token_bar_minimal"]
