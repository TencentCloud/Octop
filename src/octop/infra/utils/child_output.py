"""Decode captured child-process output without trusting the locale.

Python 3.11+ text mode (``text=True`` without ``encoding``) decodes pipes with
``locale.getencoding()`` inside the reader thread, and it emits
``EncodingWarning`` under ``-X warn_default_encoding``. On a Chinese Windows
host that encoding is GBK. UTF-8 bytes from uv, pip, or Python then raise
``UnicodeDecodeError``, and the caller never receives the return code. cp1252
(the usual GitHub-hosted Windows locale) often decodes those same bytes
without raising, so the text is silently wrong.

Use this helper for diagnostic streams. Callers that parse a version, JSON
payload, or other structured result must decode that payload as strict UTF-8
and fail closed. Replacement characters are only the last step here, after
strict UTF-8, the locale code page, and GBK.
"""

from __future__ import annotations

import locale


def decode_child_output(data: bytes | str | None) -> str:
    """Decode one captured stream. Never raises."""
    if not data:
        return ""
    if isinstance(data, str):
        return data
    seen: set[str] = set()
    for encoding in ("utf-8", locale.getencoding(), "gbk"):
        if not encoding or encoding.lower() in seen:
            continue
        seen.add(encoding.lower())
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")
