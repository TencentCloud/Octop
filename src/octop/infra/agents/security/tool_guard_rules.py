from __future__ import annotations

import contextlib
import logging
import os
import stat
import tempfile
from pathlib import Path

from octop_harness.security.tool_guard.rule_guardian import (
    list_guard_rule_catalog,
    read_bundled_rules_yaml,
    validate_rules_yaml,
)

from octop.infra.utils.paths import PathLayout

logger = logging.getLogger(__name__)


def _default_file_mode() -> int:
    """The mode a plain ``write_text`` produced (``0o666 & ~umask``).

    ``mkstemp`` would otherwise leave 0600 and silently tighten the permissions
    of a rules file that existed before this write path became atomic.
    """
    if os.name != "posix":
        return 0o644
    mask = os.umask(0o022)
    os.umask(mask)
    return 0o666 & ~mask


def _write_rules_text(path: Path, text: str) -> None:
    """Replace ``path`` via temp file + ``os.replace``.

    The runtime reads this file with ``load_rules_from_yaml``, which turns an
    unparseable file into an empty rule list, so a torn write does not fail
    loudly: it silently disables the dangerous-command guard until the next
    reload or edit. ``write_text`` truncates first, so a full disk, a kill, or
    a power loss mid-save leaves exactly that unparseable file behind. Writing
    through a unique temp file means readers see either the old rules or the
    new rules, never a mix.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_mode: int | None = None
    if os.name == "posix" and path.exists():
        existing_mode = stat.S_IMODE(path.stat().st_mode)
    fd, tmp_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        if os.name == "posix":
            os.chmod(
                tmp_name,
                _default_file_mode() if existing_mode is None else existing_mode,
            )
        os.replace(tmp_name, path)
    except BaseException:  # also covers KeyboardInterrupt / SystemExit
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise


class ToolGuardRulesStore:
    """Manage the on-disk YAML rule file used at agent runtime."""

    def __init__(self, *, paths: PathLayout) -> None:
        self._paths = paths

    @property
    def rules_dir(self) -> Path:
        return self._paths.tool_guard_rules_dir

    @property
    def rules_file(self) -> Path:
        return self._paths.tool_guard_rules_file

    def display_path(self) -> str:
        return f"~/.octop/security/tool_guard/{self.rules_file.name}"

    def ensure_seeded(self) -> None:
        self.rules_dir.mkdir(parents=True, exist_ok=True)
        if not self.rules_file.is_file():
            _write_rules_text(self.rules_file, read_bundled_rules_yaml())
            logger.info("Seeded tool guard rules at %s", self.rules_file)

    def read_text(self) -> str:
        self.ensure_seeded()
        return self.rules_file.read_text(encoding="utf-8")

    def save_text(self, content: str) -> tuple[int, list[str]]:
        rules, errors = validate_rules_yaml(content)
        if errors:
            return 0, errors
        self.ensure_seeded()
        _write_rules_text(self.rules_file, content)
        return len(rules), []

    def reset_to_bundled(self) -> str:
        text = read_bundled_rules_yaml()
        self.ensure_seeded()
        _write_rules_text(self.rules_file, text)
        return text

    def list_catalog(self) -> list[dict[str, object]]:
        self.ensure_seeded()
        return list_guard_rule_catalog(rules_dir=self.rules_dir)
