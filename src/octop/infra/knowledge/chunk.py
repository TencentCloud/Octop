"""Fixed-size, overlapping character chunking for knowledge documents."""

from __future__ import annotations


def chunk_text(text: str, *, size: int = 800, overlap: int = 120) -> list[str]:
    """Split non-empty text into stable overlapping character windows."""
    if size <= 0:
        raise ValueError("size must be positive")
    if overlap < 0 or overlap >= size:
        raise ValueError("overlap must be non-negative and smaller than size")
    content = text.strip()
    if not content:
        return []
    step = size - overlap
    chunks: list[str] = []
    for start in range(0, len(content), step):
        chunks.append(content[start : start + size])
        if start + size >= len(content):
            break
    return chunks
