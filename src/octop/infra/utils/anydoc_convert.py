"""Extract Markdown text from office binaries via ``firecrawl-anydoc``.

Used by knowledge-base indexing and chat attachment enrichment for formats
that Octop does not parse with dedicated libraries (notably OLE ``.wps`` /
``.doc``). Detection prefers file bytes over the extension so mislabeled
WPS Writer documents still convert.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Extensions we deliberately route through anydoc (even when other parsers exist).
ANYDOC_EXTENSIONS = frozenset({".wps", ".doc"})

# Keep chat prompts bounded; knowledge indexing uses the full extract.
CHAT_INLINE_MAX_CHARS = 100_000


def prefers_anydoc(*, filename: str = "", media_type: str = "") -> bool:
    """True when chat/KB should try anydoc for this name or MIME."""
    suffix = Path(filename or "").suffix.lower()
    if suffix in ANYDOC_EXTENSIONS:
        return True
    mime = (media_type or "").split(";", 1)[0].strip().lower()
    return mime in {
        "application/msword",
        "application/wps-office.wps",
        "application/kswps",
        "application/vnd.wps-office.wps",
        "application/vnd.ms-works",
        "application/x-msword",
    }


def extract_markdown(data: bytes, *, filename: str = "") -> str:
    """Convert *data* to Markdown. Returns ``\"\"`` when conversion is unsuitable."""
    if not data:
        return ""
    try:
        import anydoc
    except ImportError:
        logger.warning("firecrawl-anydoc is not installed; skipping document extract")
        return ""

    suffix = Path(filename or "").suffix.lower()
    detected: str | None = None
    try:
        detected = anydoc.format_from_bytes(data)
    except Exception:
        logger.debug("anydoc format detection failed for %s", filename or "<bytes>", exc_info=True)

    # Official tables omit .wps; OLE WPS Writer files detect as ``doc``.
    if (
        detected is None
        and suffix not in ANYDOC_EXTENSIONS
        and not prefers_anydoc(filename=filename)
    ):
        return ""

    try:
        markdown = anydoc.to_markdown_bytes(data)
    except Exception:
        logger.info("anydoc failed to convert %s", filename or "<bytes>", exc_info=True)
        return ""

    if not isinstance(markdown, str):
        return ""
    return markdown.strip()


def extract_markdown_file(path: Path) -> str:
    """Read *path* and convert with :func:`extract_markdown`."""
    return extract_markdown(path.read_bytes(), filename=path.name)


def truncate_for_chat(text: str, *, max_chars: int = CHAT_INLINE_MAX_CHARS) -> str:
    """Trim long extracts so chat turns stay within a reasonable prompt budget."""
    body = (text or "").strip()
    if max_chars <= 0 or len(body) <= max_chars:
        return body
    return body[: max_chars - 1].rstrip() + "…"
