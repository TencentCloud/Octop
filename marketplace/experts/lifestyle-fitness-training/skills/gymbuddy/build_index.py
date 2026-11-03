"""
Chunk markdown files under data/knowledge/ by level-2 headings (## ...).
Writes data/index/knowledge_chunks.jsonl for quick section → file lookup (no embeddings).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
KNOWLEDGE_DIR = ROOT / "data" / "knowledge"
OUT_DIR = ROOT / "data" / "index"
OUT_FILE = OUT_DIR / "knowledge_chunks.jsonl"


def _split_by_h2(md: str) -> list[tuple[str, str]]:
    """Return list of (heading_text_without_hashes, body_including_subsections)."""
    lines = md.splitlines()
    chunks: list[tuple[str, list[str]]] = []
    current_title = ""
    current_body: list[str] = []

    heading_re = re.compile(r"^##\s+(.+)$")

    for line in lines:
        m = heading_re.match(line)
        if m:
            if current_title or current_body:
                chunks.append((current_title, current_body[:]))
            current_title = m.group(1).strip()
            current_body = []
        else:
            current_body.append(line)

    if current_title or current_body:
        chunks.append((current_title, current_body[:]))

    return [(t, "\n".join(b).strip()) for t, b in chunks if t or "\n".join(b).strip()]


def main() -> None:
    if not KNOWLEDGE_DIR.is_dir():
        raise SystemExit(f"Missing directory: {KNOWLEDGE_DIR}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    records_written = 0

    with OUT_FILE.open("w", encoding="utf-8") as out:
        for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            rel = path.relative_to(ROOT).as_posix()
            sections = _split_by_h2(text)
            if not sections:
                rec = {
                    "source": rel,
                    "section": "",
                    "preview": text[:500].replace("\n", " ").strip(),
                }
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                records_written += 1
                continue
            for title, body in sections:
                preview = body[:800].replace("\n", " ").strip() if body else ""
                rec = {
                    "source": rel,
                    "section": title,
                    "preview": preview,
                }
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                records_written += 1

    print(f"Wrote {records_written} lines to {OUT_FILE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
