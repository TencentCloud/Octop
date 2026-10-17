"""Helper for STUB commands that exist in --help but exit on use."""

from __future__ import annotations

import sys
from typing import NoReturn

EXIT_NOT_APPLICABLE = 2


def not_applicable(
    reason: str,
    *,
    suggestion: str | None = None,
    docs_url: str | None = None,
) -> NoReturn:
    """Print a uniform "not applicable for wkbuddy" error and exit 2."""
    lines = [f"\u274c Not applicable for wkbuddy: {reason}"]
    if suggestion:
        lines.append(f"   Suggestion: {suggestion}")
    if docs_url:
        lines.append(f"   See: {docs_url}")
    print("\n".join(lines), file=sys.stderr)
    sys.exit(EXIT_NOT_APPLICABLE)
