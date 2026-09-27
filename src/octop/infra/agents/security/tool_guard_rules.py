from __future__ import annotations

import logging
from pathlib import Path

from octop_harness.security.tool_guard.rule_guardian import (
    list_guard_rule_catalog,
    read_bundled_rules_yaml,
    validate_rules_yaml,
)

from octop.infra.utils.paths import PathLayout

logger = logging.getLogger(__name__)


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
            self.rules_file.write_text(read_bundled_rules_yaml(), encoding="utf-8")
            logger.info("Seeded tool guard rules at %s", self.rules_file)

    def read_text(self) -> str:
        self.ensure_seeded()
        return self.rules_file.read_text(encoding="utf-8")

    def save_text(self, content: str) -> tuple[int, list[str]]:
        rules, errors = validate_rules_yaml(content)
        if errors:
            return 0, errors
        self.ensure_seeded()
        self.rules_file.write_text(content, encoding="utf-8")
        return len(rules), []

    def reset_to_bundled(self) -> str:
        text = read_bundled_rules_yaml()
        self.ensure_seeded()
        self.rules_file.write_text(text, encoding="utf-8")
        return text

    def list_catalog(self) -> list[dict[str, object]]:
        self.ensure_seeded()
        return list_guard_rule_catalog(rules_dir=self.rules_dir)
