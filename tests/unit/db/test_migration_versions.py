"""Guard the migration filename ↔ schema-version contract.

A migration filed as ``NNN_*.sql`` must bump ``_schema_version`` to ``NNN``.
Renaming a file without updating the statement inside it silently rewinds the
watermark, which then skips every later migration on an existing install.
"""

from __future__ import annotations

import re

import pytest

from octop.infra.db.migrate import _discover

_VERSION_STMT = re.compile(r"(?im)^\s*UPDATE\s+_schema_version\s+SET\s+version\s*=\s*(\d+)\s*;")

# 001 seeds the table with INSERT; 018 is applied by run_migrations helpers.
_SKIP_VERSIONS = frozenset({1})


@pytest.mark.parametrize(
    ("dialect",),
    [("sqlite",), ("postgresql",)],
)
def test_migration_declares_matching_version(dialect: str) -> None:
    discovered = _discover(dialect)
    assert discovered, f"no migrations discovered for {dialect}"

    for version, path in discovered:
        if version in _SKIP_VERSIONS:
            continue
        found = _VERSION_STMT.findall(path.read_text(encoding="utf-8"))
        assert found, f"{path.name} never updates _schema_version"
        wrong = sorted({int(v) for v in found if int(v) != version})
        assert not wrong, (
            f"{path.name} writes schema version {wrong} but is filed as {version:03d}; "
            "rename the file or fix the UPDATE to keep them in sync"
        )
