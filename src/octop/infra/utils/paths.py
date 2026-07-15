"""Filesystem layout for ``~/.octop/``."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PathLayout:
    root: Path

    @classmethod
    def from_env(cls) -> PathLayout:
        """Resolve install root from ``OCTOP_HOME`` or ``~/.octop``."""
        raw = os.environ.get("OCTOP_HOME", "").strip()
        if raw:
            return cls(Path(raw).expanduser())
        return cls(Path.home() / ".octop")

    @property
    def db(self) -> Path:
        return self.root / "octop.db"

    @property
    def logs_dir(self) -> Path:
        """Structured runtime logs: ``~/.octop/logs/``."""
        return self.root / "logs"

    @property
    def log(self) -> Path:
        return self.logs_dir / "octop.log"

    def ensure_logs_dir(self) -> Path:
        """Create the logs directory and return it."""
        out = self.logs_dir
        out.mkdir(parents=True, exist_ok=True)
        return out

    @property
    def config(self) -> Path:
        return self.root / "config.json"

    @property
    def users_dir(self) -> Path:
        return self.root / "users"

    def user_dir(self, username: str) -> Path:
        return self.users_dir / username

    @property
    def agents_dir(self) -> Path:
        """Global agents directory: ~/.octop/agents/"""
        return self.root / "agents"

    def agent_workspace(self, agent_id: str) -> Path:
        """Global agent workspace: ~/.octop/agents/<agent_id>/"""
        return self.agents_dir / agent_id

    def ensure_agent_workspace(self, agent_id: str) -> Path:
        """Global agent workspace, mkdir -p."""
        out = self.agent_workspace(agent_id)
        out.mkdir(parents=True, exist_ok=True)
        return out

    def ensure_root(self) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        return self.root

    @property
    def plugins_dir(self) -> Path:
        return self.root / "plugins"

    @property
    def tool_guard_rules_dir(self) -> Path:
        """User-editable command guard rules: ``~/.octop/security/tool_guard/``."""
        return self.root / "security" / "tool_guard"

    @property
    def tool_guard_rules_file(self) -> Path:
        return self.tool_guard_rules_dir / "dangerous_shell_commands.yaml"

    @property
    def backups_dir(self) -> Path:
        """Stored system backup archives: ``~/.octop/backups/``."""
        return self.root / "backups"

    def ensure_backups_dir(self) -> Path:
        out = self.backups_dir
        out.mkdir(parents=True, exist_ok=True)
        return out

    def backup_file(self, filename: str) -> Path:
        """Resolve a backup archive path under :attr:`backups_dir` (basename only)."""
        return self.backups_dir / Path(filename).name

    @property
    def ssl_dir(self) -> Path:
        """TLS certificates and ACME account keys: ``~/.octop/ssl/``."""
        return self.root / "ssl"

    def ensure_ssl_dir(self) -> Path:
        out = self.ssl_dir
        out.mkdir(parents=True, exist_ok=True)
        return out
