"""YAML regex rule guardian for shell tool parameters."""

from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path
from typing import Any

import yaml

from octop_harness.security.tool_guard.models import (
    GuardFinding,
    GuardSeverity,
    GuardThreatCategory,
)

logger = logging.getLogger(__name__)

_DEFAULT_RULES_DIR = Path(__file__).resolve().parent / "rules"
_DEFAULT_RULE_FILES = ("dangerous_shell_commands.yaml",)


class GuardRule:
    """A single regex-based guard detection rule."""

    __slots__ = (
        "category",
        "compiled_exclude_patterns",
        "compiled_patterns",
        "description",
        "exclude_patterns",
        "id",
        "params",
        "patterns",
        "remediation",
        "severity",
        "tools",
    )

    def __init__(self, rule_data: dict[str, Any]) -> None:
        self.id: str = rule_data["id"]
        raw_tool = rule_data.get("tool", rule_data.get("tools", []))
        if isinstance(raw_tool, str):
            self.tools: list[str] = [raw_tool] if raw_tool else []
        else:
            self.tools = list(raw_tool or [])
        raw_params = rule_data.get("params", rule_data.get("param", []))
        if isinstance(raw_params, str):
            self.params: list[str] = [raw_params] if raw_params else []
        else:
            self.params = list(raw_params or [])
        self.category = GuardThreatCategory(rule_data["category"])
        self.severity = GuardSeverity(rule_data["severity"])
        self.patterns: list[str] = rule_data.get("patterns", [])
        self.exclude_patterns: list[str] = rule_data.get("exclude_patterns", [])
        self.description: str = rule_data.get("description", "")
        self.remediation: str = rule_data.get("remediation", "")
        self.compiled_patterns: list[re.Pattern[str]] = []
        for pat in self.patterns:
            try:
                self.compiled_patterns.append(re.compile(pat, re.IGNORECASE))
            except re.error as exc:
                logger.warning("Bad regex in guard rule %s: %s", self.id, exc)
        self.compiled_exclude_patterns: list[re.Pattern[str]] = []
        for pat in self.exclude_patterns:
            try:
                self.compiled_exclude_patterns.append(re.compile(pat, re.IGNORECASE))
            except re.error as exc:
                logger.warning("Bad exclude regex in guard rule %s: %s", self.id, exc)

    def applies_to_tool(self, tool_name: str) -> bool:
        if not self.tools:
            return True
        return tool_name in self.tools

    def applies_to_param(self, param_name: str) -> bool:
        if not self.params:
            return True
        return param_name in self.params

    def match(self, value: str) -> tuple[re.Match[str] | None, str | None]:
        if any(ep.search(value) for ep in self.compiled_exclude_patterns):
            return None, None
        for pattern in self.compiled_patterns:
            m = pattern.search(value)
            if m:
                return m, pattern.pattern
        return None, None


def bundled_rules_yaml_path() -> Path:
    """Path to the shipped ``dangerous_shell_commands.yaml``."""
    return _DEFAULT_RULES_DIR / _DEFAULT_RULE_FILES[0]


def read_bundled_rules_yaml() -> str:
    """Return the bundled rules file as text (for seeding user copies)."""
    return bundled_rules_yaml_path().read_text(encoding="utf-8")


def validate_rules_yaml(content: str) -> tuple[list[GuardRule], list[str]]:
    """Parse and validate YAML rule definitions. Returns ``(rules, errors)``."""
    errors: list[str] = []
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        return [], [str(exc)]
    if data is None:
        return [], ["YAML document is empty"]
    if not isinstance(data, list):
        return [], ["Root must be a YAML list of rules"]
    rules: list[GuardRule] = []
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            errors.append(f"Rule #{index + 1}: expected a mapping")
            continue
        try:
            rules.append(GuardRule(item))
        except (KeyError, TypeError, ValueError) as exc:
            rule_id = item.get("id", index + 1)
            errors.append(f"Rule {rule_id}: {exc}")
    return rules, errors


def load_rules_from_yaml(yaml_path: Path) -> list[GuardRule]:
    try:
        with yaml_path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, list):
            return []
        rules: list[GuardRule] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            try:
                rules.append(GuardRule(item))
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning("Skipping invalid rule %r in %s: %s", item.get("id"), yaml_path, exc)
        return rules
    except (OSError, yaml.YAMLError) as exc:
        logger.warning("Failed to load guard rules from %s: %s", yaml_path, exc)
        return []


def load_rules_from_directory(rules_dir: Path | None = None) -> list[GuardRule]:
    directory = rules_dir or _DEFAULT_RULES_DIR
    if not directory.is_dir():
        logger.warning("Guard rules directory not found: %s", directory)
        return []
    rules: list[GuardRule] = []
    for filename in _DEFAULT_RULE_FILES:
        yaml_file = directory / filename
        if yaml_file.is_file():
            rules.extend(load_rules_from_yaml(yaml_file))
    return rules


class RuleBasedToolGuardian:
    """Match tool parameter strings against bundled YAML regex rules."""

    name = "rule_based_tool_guardian"

    def __init__(self, *, rules_dir: Path | None = None) -> None:
        self._rules_dir = rules_dir
        self._rules: list[GuardRule] = load_rules_from_directory(rules_dir)

    @property
    def rule_count(self) -> int:
        return len(self._rules)

    def reload(self) -> None:
        self._rules = load_rules_from_directory(self._rules_dir)

    def guard(self, tool_name: str, params: dict[str, Any]) -> list[GuardFinding]:
        findings: list[GuardFinding] = []
        applicable = [r for r in self._rules if r.applies_to_tool(tool_name)]
        if not applicable:
            return findings
        for param_name, param_value in params.items():
            value_str = str(param_value) if param_value is not None else ""
            if not value_str:
                continue
            for rule in applicable:
                if not rule.applies_to_param(param_name):
                    continue
                m, pattern_str = rule.match(value_str)
                if not m:
                    continue
                start = max(0, m.start() - 40)
                end = min(len(value_str), m.end() + 40)
                findings.append(
                    GuardFinding(
                        id=str(uuid.uuid4()),
                        rule_id=rule.id,
                        category=rule.category,
                        severity=rule.severity,
                        title=rule.description or rule.id,
                        description=(f"Rule {rule.id} matched parameter '{param_name}' of tool '{tool_name}'."),
                        tool_name=tool_name,
                        param_name=param_name,
                        matched_pattern=pattern_str,
                        snippet=value_str[start:end],
                        remediation=rule.remediation,
                        guardian=self.name,
                    )
                )
        return findings


def list_guard_rule_catalog(*, rules_dir: Path | None = None) -> list[dict[str, Any]]:
    """Return built-in guard rules for admin UIs (read-only catalog)."""
    rules = load_rules_from_directory(rules_dir)
    return [
        {
            "id": rule.id,
            "tools": list(rule.tools),
            "params": list(rule.params),
            "category": rule.category.value,
            "severity": rule.severity.value,
            "description": rule.description,
            "remediation": rule.remediation,
            "patterns": list(rule.patterns),
            "exclude_patterns": list(rule.exclude_patterns),
        }
        for rule in rules
    ]


__all__ = [
    "GuardRule",
    "RuleBasedToolGuardian",
    "bundled_rules_yaml_path",
    "list_guard_rule_catalog",
    "load_rules_from_directory",
    "read_bundled_rules_yaml",
    "validate_rules_yaml",
]
