"""Filesystem layout for ``~/.agentbuddy/``."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PathLayout:
    root: Path

    @classmethod
    def from_env(cls) -> PathLayout:
        """Resolve install root from ``AGENTBUDDY_HOME`` or ``~/.agentbuddy``.

        ``OCTOP_HOME`` is accepted as a legacy fallback; the new name wins
        when both are set.
        """
        raw = (
            os.environ.get("AGENTBUDDY_HOME", "").strip()
            or os.environ.get("OCTOP_HOME", "").strip()
        )
        if raw:
            return cls(Path(raw).expanduser())
        return cls(Path.home() / ".agentbuddy")

    @property
    def wizard_password_file(self) -> Path:
        """Initial wizard password file: ``~/.agentbuddy/agentbuddy-login.txt`` (or under ``$AGENTBUDDY_HOME``)."""
        return self.root / "agentbuddy-login.txt"

    @property
    def db(self) -> Path:
        return self.root / "agentbuddy.db"

    @property
    def logs_dir(self) -> Path:
        """Structured runtime logs: ``~/.agentbuddy/logs/``."""
        return self.root / "logs"

    @property
    def log(self) -> Path:
        return self.logs_dir / "agentbuddy.log"

    def ensure_logs_dir(self) -> Path:
        """Create the logs directory and return it."""
        out = self.logs_dir
        out.mkdir(parents=True, exist_ok=True)
        return out

    def ensure_log(self) -> Path:
        """Create the logs directory and return ``agentbuddy.log``."""
        self.ensure_logs_dir()
        return self.log

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
        """Global agents directory: ~/.agentbuddy/agents/"""
        return self.root / "agents"

    @property
    def expert_market_dir(self) -> Path:
        """Cached SkillHub expert templates: ``~/.agentbuddy/expert_market/``."""
        return self.root / "expert_market"

    @property
    def published_experts_dir(self) -> Path:
        """User-published expert snapshots: ``~/.agentbuddy/published_experts/``."""
        return self.root / "published_experts"

    @property
    def skill_packages_dir(self) -> Path:
        """Global skill package content: ``~/.agentbuddy/skill-packages/``."""
        return self.root / "skill-packages"

    @property
    def knowledge_dir(self) -> Path:
        """Global knowledge base files: ``~/.agentbuddy/knowledge/``."""
        return self.root / "knowledge"

    def agent_workspace(self, agent_id: str) -> Path:
        """Global agent workspace: ~/.agentbuddy/agents/<agent_id>/"""
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
        """User-editable command guard rules: ``~/.agentbuddy/security/tool_guard/``."""
        return self.root / "security" / "tool_guard"

    @property
    def tool_guard_rules_file(self) -> Path:
        return self.tool_guard_rules_dir / "dangerous_shell_commands.yaml"

    @property
    def backups_dir(self) -> Path:
        """Stored system backup archives: ``~/.agentbuddy/backups/``."""
        return self.root / "backups"

    def ensure_backups_dir(self) -> Path:
        out = self.backups_dir
        out.mkdir(parents=True, exist_ok=True)
        return out

    def backup_file(self, filename: str) -> Path:
        """Resolve a backup archive path under :attr:`backups_dir` (basename only)."""
        return self.backups_dir / Path(filename).name

    @property
    def user_avatars_dir(self) -> Path:
        """Uploaded user portraits: ``~/.agentbuddy/avatars/users/``."""
        return self.root / "avatars" / "users"

    @property
    def role_avatars_dir(self) -> Path:
        """Uploaded role portraits: ``~/.agentbuddy/avatars/roles/``."""
        return self.root / "avatars" / "roles"

    @property
    def group_avatars_dir(self) -> Path:
        """Uploaded user-group portraits: ``~/.octop/avatars/groups/``."""
        return self.root / "avatars" / "groups"

    @property
    def ssl_dir(self) -> Path:
        """TLS certificates and ACME account keys: ``~/.agentbuddy/ssl/``."""
        return self.root / "ssl"

    def ensure_ssl_dir(self) -> Path:
        out = self.ssl_dir
        out.mkdir(parents=True, exist_ok=True)
        return out

    @property
    def connector_cli_dir(self) -> Path:
        """Per-instance CLI config roots: ``~/.agentbuddy/connector-cli/``."""
        return self.root / "connector-cli"

    def connector_cli_instance_dir(self, kind: str, instance_key: str) -> Path:
        """Isolated config dir for one connector CLI instance."""
        safe_kind = Path(kind).name
        safe_key = (
            "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in instance_key)[:80]
            or "default"
        )
        return self.connector_cli_dir / safe_kind / safe_key

    def ensure_connector_cli_instance_dir(self, kind: str, instance_key: str) -> Path:
        out = self.connector_cli_instance_dir(kind, instance_key)
        out.mkdir(parents=True, exist_ok=True)
        return out
