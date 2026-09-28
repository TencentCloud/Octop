# -*- coding: utf-8 -*-
"""Verify migration numbering after the 018 -> 019 renumber.

Run this after resolving the rebase onto upstream/develop. It catches the three
ways the renumber can be silently half-done:

  1. two migrations sharing a version number (``_discover`` raises at runtime,
     so this would break every DB operation, not just one test)
  2. a migration file whose *watermark* does not match its filename prefix
  3. the fixups that always follow a version bump -- the ``if version == N``
     branch, the idempotent helper, and the ~16 test assertions
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

REPO = Path(__file__).resolve().parents[3]
MIGRATIONS = REPO / "src/octop/infra/db/migrations"
MIGRATE_PY = REPO / "src/octop/infra/db/migrate.py"

EXPECTED_MAX = 19
PROJECT_FILES = ("019_projects.sql", "019_projects.pg.sql")

failures: list[str] = []


def ok(label: str, passed: bool, detail: str = "") -> None:
    if not passed:
        failures.append(label)
    print(f"  [{'OK ' if passed else 'FAIL'}] {label}{(' -- ' + detail) if detail else ''}")


def discover_versions() -> dict[tuple[int, str], list[str]]:
    """Group by (version, dialect) — ``_discover`` treats the pair as one migration."""
    seen: dict[tuple[int, str], list[str]] = {}
    for path in sorted(MIGRATIONS.iterdir()):
        m = re.match(r"^(\d{3})_.*\.sql$", path.name)
        if m:
            dialect = "postgresql" if path.name.endswith(".pg.sql") else "sqlite"
            seen.setdefault((int(m.group(1)), dialect), []).append(path.name)
    return seen


def main() -> int:
    print("1) one migration per (version, dialect)")
    versions = discover_versions()
    dupes = {k: names for k, names in versions.items() if len(names) > 1}
    ok("no duplicate version numbers", not dupes, str(dupes) if dupes else "")
    top = max((v for v, _ in versions), default=0)
    ok(f"max version is {EXPECTED_MAX}", top == EXPECTED_MAX, f"got {top}")

    print("2) the project migration pair exists and is numbered 019")
    for name in PROJECT_FILES:
        ok(f"{name} exists", (MIGRATIONS / name).exists())
    ok("no stale 018_projects file",
       not list(MIGRATIONS.glob("018_projects*")))

    print("3) watermark matches the filename prefix")
    for name in PROJECT_FILES:
        path = MIGRATIONS / name
        if not path.exists():
            ok(f"{name} watermark", False, "file missing")
            continue
        text = path.read_text(encoding="utf-8")
        m = re.search(r"UPDATE _schema_version SET version = (\d+);", text)
        ok(f"{name} sets version {EXPECTED_MAX}", bool(m) and int(m.group(1)) == EXPECTED_MAX,
           f"got {m.group(1) if m else 'none'}")

    print("4) migrate.py is wired to 019")
    src = MIGRATE_PY.read_text(encoding="utf-8")
    ok("helper reads 019_projects.pg.sql",
       '"019_projects.pg.sql"' in src)
    ok("watermark replace targets 19",
       '.replace(\n        "UPDATE _schema_version SET version = 19;", ""\n    )' in src
       or '"UPDATE _schema_version SET version = 19;"' in src)
    ok("sqlite branch is `if version == 19:`",
       re.search(r"if version == 19:", src) is not None)
    ok("`_ensure_projects_schema` is called in run_migrations",
       src.count("_ensure_projects_schema(db)") >= 2,
       f"calls={src.count('_ensure_projects_schema(db)')}")
    ok("upstream's user-role work survived the rebase",
       "_ensure_user_role_schema" in src or "if version == 18:" in src)

    print("5) schema-version assertions were re-bumped to 19")
    # Only ``tests/`` is scanned: the planning docs and this very script mention
    # the old numbers on purpose (they describe the renumber), so a whole-repo
    # grep reports them as false positives.
    files = subprocess.run(
        ["git", "grep", "-l", "-E", r"assert (v|version) == 18|schema_version\"\] == 18|runtime_schema_version\": 18", "--", "tests/"],
        cwd=REPO, capture_output=True, text=True, encoding="utf-8",
    ).stdout.split()
    ok("no test still asserts 18", not files, str(files) if files else "")
    hits = subprocess.run(
        ["git", "grep", "-c", "-E", r"assert (v|version) == 19|schema_version\"\] == 19|runtime_schema_version\": 19", "--", "tests/"],
        cwd=REPO, capture_output=True, text=True, encoding="utf-8",
    ).stdout
    print("     19-assertions per file:")
    for line in hits.splitlines():
        print(f"       {line}")

    print()
    if failures:
        print(f"{len(failures)} CHECK(S) FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("ALL PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
