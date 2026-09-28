# -*- coding: utf-8 -*-
"""Normalize the working tree to LF for files whose *index* blob is LF.

Why this exists
---------------
The clone ran with Git for Windows' default ``core.autocrlf=true``, so 2451
tracked files were checked out as CRLF while their blobs in the index are LF.
Setting ``core.autocrlf=false`` afterwards does NOT rewrite an already-populated
working tree, and ``git status`` hides the mismatch behind the stat cache --
until you edit a file, at which point git re-reads it and reports the *entire*
file as changed.

If that is left alone, every file this fork touches gets committed with CRLF
while upstream stores LF, turning each rebase into a whole-file conflict.

Safety
------
* Only files reported by ``git ls-files --eol`` as ``i/lf`` + ``w/crlf`` are
  rewritten -- i.e. the index is authoritative and says LF.
* ``i/crlf`` files (16 upstream MBTI SVGs) are deliberately left untouched.
* Binary / unset (``-text``, ``none``) entries are skipped.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

REPO = Path(r"D:\nancc\octop\Octop-develop")


def eol_entries() -> list[tuple[str, str, str]]:
    out = subprocess.run(
        ["git", "ls-files", "--eol"],
        cwd=REPO,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout
    rows: list[tuple[str, str, str]] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        head = parts[0].split()
        if len(head) < 2:
            continue
        rows.append((head[0], head[1], parts[-1]))
    return rows


def main() -> int:
    rows = eol_entries()
    targets = [(i, w, p) for i, w, p in rows if i == "i/lf" and w == "w/crlf"]
    skipped_crlf = [(i, w, p) for i, w, p in rows if i == "i/crlf"]
    print(f"tracked files           : {len(rows)}")
    print(f"i/lf + w/crlf (convert) : {len(targets)}")
    print(f"i/crlf        (keep)    : {len(skipped_crlf)}")

    changed = already = missing = 0
    for _i, _w, rel in targets:
        path = REPO / rel
        if not path.is_file():
            missing += 1
            continue
        data = path.read_bytes()
        if b"\r\n" not in data:
            already += 1
            continue
        path.write_bytes(data.replace(b"\r\n", b"\n"))
        changed += 1

    print(f"\nconverted to LF : {changed}")
    print(f"already LF      : {already}")
    print(f"missing on disk : {missing}")

    # Re-check
    rows2 = eol_entries()
    left = [(i, w, p) for i, w, p in rows2 if i == "i/lf" and w == "w/crlf"]
    print(f"\nremaining i/lf + w/crlf : {len(left)}")
    for _i, _w, p in left[:10]:
        print(f"  {p}")
    kept = [(i, w, p) for i, w, p in rows2 if i == "i/crlf"]
    print(f"i/crlf preserved        : {len(kept)}")
    return 0 if not left else 1


if __name__ == "__main__":
    raise SystemExit(main())
