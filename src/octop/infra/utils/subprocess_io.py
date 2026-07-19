"""Cross-platform non-blocking reads from subprocess stdout pipes."""

from __future__ import annotations

import json
import os
from typing import IO, Any


def read_available_bytes(stream: IO[bytes]) -> bytes:
    """Read whatever is currently buffered on *stream* without blocking."""
    if stream is None:
        return b""
    if os.name == "nt":
        from octop.infra.utils.subprocess_io_win import read_available_windows

        return read_available_windows(stream)
    from octop.infra.utils.posix_compat import read_available_posix

    return read_available_posix(stream)


def parse_json_lines(raw: bytes) -> list[dict[str, Any]]:
    """Decode newline-delimited JSON objects from subprocess stdout."""
    lines: list[dict[str, Any]] = []
    if not raw:
        return lines
    text = raw.decode("utf-8", errors="replace")
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            lines.append({"action": "log", "level": "info", "step": "raw", "message": line})
        else:
            if isinstance(parsed, dict):
                lines.append(parsed)
            else:
                lines.append({"action": "log", "level": "info", "step": "raw", "message": line})
    return lines


def parse_subprocess_json_lines(proc: Any) -> list[dict[str, Any]]:
    """Non-blocking read of stdout JSON lines from a running subprocess."""
    if proc.stdout is None:
        return []
    return parse_json_lines(read_available_bytes(proc.stdout))
