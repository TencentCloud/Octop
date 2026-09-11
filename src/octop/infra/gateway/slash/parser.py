"""Slash command parsing that keeps filesystem paths out of the dispatcher."""

from __future__ import annotations

import re

from harness_agent.slash import SlashCommand
from harness_agent.slash import parse_slash as _parse_slash

# The harness parser stops the command name at the first non-word character, so
# ``/root/ddd`` would dispatch as ``/root``. Require the name to end at
# whitespace (or end of text) instead, leaving paths as plain chat text.
_COMMAND_RE = re.compile(r"^\s*/[a-zA-Z][\w-]*(?:\s[\s\S]*)?$")


def parse_slash(text: str | None) -> SlashCommand | None:
    """Parse *text* as a slash command, or return ``None`` for ordinary text."""
    if not text or not _COMMAND_RE.match(text):
        return None
    return _parse_slash(text)
