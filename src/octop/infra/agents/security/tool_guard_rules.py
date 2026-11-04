from __future__ import annotations

import logging
from pathlib import Path

from octop_harness.security.tool_guard.rule_guardian import (
    list_guard_rule_catalog,
    read_bundled_rules_yaml,
    validate_rules_yaml,
)

from octop.infra.db.repos.settings import SettingsRepo
from octop.infra.utils.paths import PathLayout

logger = logging.getLogger(__name__)

TOOL_GUARD_YAML = "tool_guard.dangerous_shell_commands"


class ToolGuardRulesStore:
    """Manage the command-guard YAML stored in the control plane.

    Harness still reads a directory. :meth:`ensure_seeded` rewrites that cache
    from the settings row so the next agent start or reload sees the shared text.
    """

    def __init__(self, *, paths: PathLayout, settings: SettingsRepo) -> None:
        self._paths = paths
        self._settings = settings

    @property
    def rules_dir(self) -> Path:
        return self._paths.tool_guard_rules_dir

    @property
    def rules_file(self) -> Path:
        return self._paths.tool_guard_rules_file

    def display_path(self) -> str:
        return f"~/.octop/security/tool_guard/{self.rules_file.name}"

    def ensure_seeded(self) -> None:
        text = self._settings.get(TOOL_GUARD_YAML)
        if text is None:
            legacy = self.rules_file
            if legacy.is_file():
                text = legacy.read_text(encoding="utf-8")
            else:
                text = read_bundled_rules_yaml()
            self._settings.set(TOOL_GUARD_YAML, text)
            logger.info("Seeded tool guard rules into control-plane settings")
        self._write_cache(text)

    def read_text(self) -> str:
        self.ensure_seeded()
        return self._settings.get(TOOL_GUARD_YAML) or ""

    def save_text(self, content: str) -> tuple[int, list[str]]:
        rules, errors = validate_rules_yaml(content)
        if errors:
            return 0, errors
        self._settings.set(TOOL_GUARD_YAML, content)
        self._write_cache(content)
        return len(rules), []

    def reset_to_bundled(self) -> str:
        text = read_bundled_rules_yaml()
        self._settings.set(TOOL_GUARD_YAML, text)
        self._write_cache(text)
        return text

    def list_catalog(self) -> list[dict[str, object]]:
        self.ensure_seeded()
        return list_guard_rule_catalog(rules_dir=self.rules_dir)

    def _write_cache(self, text: str) -> None:
        self.rules_dir.mkdir(parents=True, exist_ok=True)
        self.rules_file.write_text(text, encoding="utf-8")
