#!/usr/bin/env python3
"""Search Markdown files under the Octop repository docs/ directory."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def repo_root() -> Path:
    # This file lives at .cursor/skills/octop-wiki/scripts/search_docs.py.
    return Path(__file__).resolve().parents[4]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", nargs="?", default="", help="Keywords to find in docs/")
    parser.add_argument("--limit", type=int, default=8)
    return parser.parse_args()


def terms_in(query: str) -> list[str]:
    return [part.casefold() for part in re.findall(r"[\w.-]+", query) if len(part) > 1]


def heading_text(markdown: str) -> str:
    lines = []
    for line in markdown.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            lines.append(stripped)
    return "\n".join(lines)


def score_document(path: Path, docs: Path, query: str, terms: list[str]) -> tuple[int, list[str]] | None:
    text = path.read_text(encoding="utf-8")
    folded = text.casefold()
    relative = path.relative_to(docs).as_posix().casefold()
    headings = heading_text(text).casefold()
    phrase = query.casefold().strip()
    score = 0
    if phrase and phrase in relative:
        score += 24
    if phrase and phrase in headings:
        score += 16
    if phrase and phrase in folded:
        score += 8
    for term in terms:
        if term in relative:
            score += 8
        if term in headings:
            score += 5
        score += min(folded.count(term), 6)
    if score <= 0:
        return None

    snippets: list[str] = []
    for number, line in enumerate(text.splitlines(), start=1):
        folded_line = line.casefold()
        if (phrase and phrase in folded_line) or any(term in folded_line for term in terms):
            snippets.append(f"L{number}: {line.strip()[:200]}")
        if len(snippets) == 3:
            break
    return score, snippets


def main() -> int:
    args = parse_args()
    if args.limit < 1:
        print("--limit must be positive", file=sys.stderr)
        return 2
    terms = terms_in(args.query)
    if not terms:
        print("Give a query with letters or numbers.", file=sys.stderr)
        return 2

    docs = (repo_root() / "docs").resolve()
    if not docs.is_dir():
        print(f"docs directory not found: {docs}", file=sys.stderr)
        return 2

    matches: list[tuple[int, Path, list[str]]] = []
    for path in sorted(docs.rglob("*.md")):
        scored = score_document(path, docs, args.query, terms)
        if scored is None:
            continue
        score, snippets = scored
        matches.append((score, path.relative_to(docs), snippets))
    matches.sort(key=lambda item: (-item[0], item[1].as_posix()))
    if not matches:
        print(f"No matches for: {args.query}")
        return 1

    for score, relative, snippets in matches[: args.limit]:
        print(f"[{score:>3}] docs/{relative.as_posix()}")
        for snippet in snippets:
            print(f"    {snippet}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
