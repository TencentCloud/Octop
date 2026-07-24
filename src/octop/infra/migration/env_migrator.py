"""Migrate environment variable scaffolding from a LightClaw export.

LightClaw exports only the key names (values are intentionally stripped for
security).  This module notes the keys present in the export and writes an
env scaffold into Octop's env file so the user knows which keys to fill in.

Existing Octop env values are preserved.  Missing keys get an empty value.
"""

from __future__ import annotations

import logging
from pathlib import Path

from octop.infra.migration.archive_reader import ArchiveReader
from octop.infra.migration.report import MigrationReport
from octop.infra.utils.env_file import load_env_file, save_env_file

logger = logging.getLogger(__name__)


def migrate_env(
    reader: ArchiveReader,
    env_file_path: Path,
    report: MigrationReport,
) -> None:
    """Read the env scaffold from *reader* and note keys in *report*.

    The Octop env file is *not* modified automatically — env values must be
    filled in by the user after import.  We do record the key names so the
    importer UI can display a checklist.

    Args:
        reader: Open archive reader.
        env_file_path: Path to the Octop ``env`` file (``~/.octop/env``).
        report: Migration report to update.
    """
    env_text = reader.read_text("env")
    if not env_text:
        # No env section in archive
        report.env_keys_noted = []
        return

    # Parse the scaffold (values are all empty by design)
    keys: list[str] = []
    for line in env_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key:
                keys.append(key)

    report.env_keys_noted = keys
    logger.info("Env scaffold: %d keys noted from export (values not imported)", len(keys))

    if not keys:
        return

    # Merge: load existing Octop env, add new keys with empty value if absent.
    existing = load_env_file(env_file_path) if env_file_path.is_file() else {}
    added = 0
    for key in keys:
        if key not in existing:
            existing[key] = ""
            added += 1
    if added:
        save_env_file(env_file_path, existing)
        logger.info("Env scaffold: added %d new empty keys to %s", added, env_file_path)
