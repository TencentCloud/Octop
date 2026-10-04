from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

from octop_harness.security.tool_guard.rule_guardian import (
    list_guard_rule_catalog,
    read_bundled_rules_yaml,
    validate_rules_yaml,
)

from octop.infra.utils.paths import PathLayout

logger = logging.getLogger(__name__)


def _write_text_atomically(path: Path, content: str) -> None:
    """Publish text through a temporary file so a partial write cannot survive."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
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
            _write_text_atomically(self.rules_file, read_bundled_rules_yaml())
            logger.info("Seeded tool guard rules at %s", self.rules_file)

    def read_text(self) -> str:
        self.ensure_seeded()
        return self.rules_file.read_text(encoding="utf-8")

    def save_text(self, content: str) -> tuple[int, list[str]]:
        rules, errors = validate_rules_yaml(content)
        if errors:
            return 0, errors
        self.ensure_seeded()
        _write_text_atomically(self.rules_file, content)
        return len(rules), []

    def reset_to_bundled(self) -> str:
        text = read_bundled_rules_yaml()
        self.ensure_seeded()
        _write_text_atomically(self.rules_file, text)
        return text

    def list_catalog(self) -> list[dict[str, object]]:
        self.ensure_seeded()
        return list_guard_rule_catalog(rules_dir=self.rules_dir)
