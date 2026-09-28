# -*- coding: utf-8 -*-
"""Renumber the project migration from 018 to 019 after the rebase.

Upstream took 018 (`018_user_role`, schema v18), so ours becomes 019. Every
touch point is asserted before it is rewritten, and the script refuses to run if
it finds a leftover conflict marker.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

REPO = Path(r"D:\nancc\octop\Octop-develop")
MIGRATE = REPO / "src/octop/infra/db/migrate.py"
MIGRATIONS = REPO / "src/octop/infra/db/migrations"

changed: list[str] = []


def edit(path: Path, old: str, new: str, *, count: int = 1, required: bool = True) -> int:
    text = path.read_text(encoding="utf-8")
    n = text.count(old)
    if n == 0:
        if required:
            raise SystemExit(f"ABORT: {path.name}: pattern not found: {old!r}")
        return 0
    if count and n < count:
        raise SystemExit(f"ABORT: {path.name}: wanted {count}x {old!r}, found {n}")
    path.write_text(text.replace(old, new), encoding="utf-8", newline="")
    changed.append(f"{path.relative_to(REPO)}: {old!r} -> {new!r} (x{n})")
    return n


def main() -> int:
    print("0) no unmerged files")
    # ``^(=======$)`` also matches markdown setext underlines, so ask git
    # instead of grepping, then restrict the grep to source extensions.
    unmerged = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=U"],
        cwd=REPO, capture_output=True, text=True, encoding="utf-8",
    ).stdout.split()
    if unmerged:
        raise SystemExit(f"ABORT: unmerged files: {unmerged}")
    markers = subprocess.run(
        ["git", "grep", "-l", "-E", r"^(<<<<<<< |>>>>>>> )"],
        cwd=REPO, capture_output=True, text=True, encoding="utf-8",
    ).stdout.split()
    if markers:
        raise SystemExit(f"ABORT: conflict markers remain in {markers}")

    print("1) migration files: filename + internal watermark")
    for suffix in ("sql", "pg.sql"):
        path = MIGRATIONS / f"019_projects.{suffix}"
        if not path.exists():
            raise SystemExit(f"ABORT: missing {path.name} (rename first)")
        edit(path, "UPDATE _schema_version SET version = 18;",
             "UPDATE _schema_version SET version = 19;")

    print("2) migrate.py: helper reads the 019 pair")
    edit(MIGRATE, '"018_projects.pg.sql"', '"019_projects.pg.sql"')
    edit(MIGRATE, '"018_projects.sql"', '"019_projects.sql"')
    edit(MIGRATE, 'UPDATE _schema_version SET version = 18;', 'UPDATE _schema_version SET version = 19;')

    print("3) migrate.py: our sqlite branch becomes 19 (upstream keeps 18)")
    text = MIGRATE.read_text(encoding="utf-8")
    pattern = re.compile(
        r"if version == 18:\n        _ensure_projects_schema\(db\)"
    )
    if not pattern.search(text):
        raise SystemExit("ABORT: could not find our `if version == 18:` + _ensure_projects_schema branch")
    MIGRATE.write_text(
        pattern.sub("if version == 19:\n        _ensure_projects_schema(db)", text),
        encoding="utf-8", newline="",
    )
    changed.append("migrate.py: `if version == 18:` -> `if version == 19:` (projects)")

    if "if version == 18:\n            _ensure_user_role_schema(db)" not in MIGRATE.read_text(encoding="utf-8"):
        raise SystemExit("ABORT: upstream's `if version == 18:` + _ensure_user_role_schema is gone")
    print("      upstream's user_role branch kept at 18")

    print("4) test assertions 18 -> 19")
    hits = subprocess.run(
        ["git", "grep", "-l", "-E",
         r'assert (v|version) == 18|schema_version"\] == 18|runtime_schema_version": 18'],
        cwd=REPO, capture_output=True, text=True, encoding="utf-8",
    ).stdout.split()
    print(f"      {len(hits)} file(s): {hits}")
    total = 0
    for rel in hits:
        path = REPO / rel
        text = path.read_text(encoding="utf-8")
        new_text, n1 = re.subn(r"assert (v|version) == 18", r"assert \1 == 19", text)
        new_text, n2 = re.subn(r'schema_version"\] == 18', 'schema_version"] == 19', new_text)
        new_text, n3 = re.subn(r'runtime_schema_version": 18', 'runtime_schema_version": 19', new_text)
        path.write_text(new_text, encoding="utf-8", newline="")
        total += n1 + n2 + n3
        changed.append(f"{rel}: {n1 + n2 + n3} assertion(s)")
    print(f"      {total} assertion(s) re-bumped")

    left = subprocess.run(
        ["git", "grep", "-l", "-E",
         r'assert (v|version) == 18|schema_version"\] == 18|runtime_schema_version": 18'],
        cwd=REPO, capture_output=True, text=True, encoding="utf-8",
    ).stdout.split()
    if left:
        raise SystemExit(f"ABORT: assertions still at 18 in {left}")

    print("\n=== changes ===")
    for c in changed:
        print("  " + c)
    print("\nDONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
