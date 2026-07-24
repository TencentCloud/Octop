"""Import result report for LightClaw → Octop migration."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MigrationReport:
    """Collects per-phase outcomes of an import operation."""

    # Agent
    agent_id: str = ""
    agent_created: bool = False

    # Workspace files (identity md + skills + misc)
    workspace_files_written: int = 0
    workspace_files_skipped: int = 0
    # Identity files written (SOUL.md, USER.md, AGENTS.md, etc.)
    identity_files_written: list[str] = field(default_factory=list)
    # Skills imported (workspace/skills/<name>/ directories found and written)
    skills_imported: int = 0

    # Uploads
    uploads_written: int = 0
    uploads_skipped: int = 0

    # Cron jobs
    cron_jobs_imported: int = 0
    cron_jobs_skipped: int = 0

    # Chat history (session JSONL → threads + sessions)
    sessions_imported: int = 0
    sessions_skipped: int = 0

    # Warnings / errors accumulated during import
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "agent_created": self.agent_created,
            "workspace_files_written": self.workspace_files_written,
            "workspace_files_skipped": self.workspace_files_skipped,
            "identity_files_written": self.identity_files_written,
            "skills_imported": self.skills_imported,
            "uploads_written": self.uploads_written,
            "uploads_skipped": self.uploads_skipped,
            "cron_jobs_imported": self.cron_jobs_imported,
            "cron_jobs_skipped": self.cron_jobs_skipped,
            "sessions_imported": self.sessions_imported,
            "sessions_skipped": self.sessions_skipped,
            "warnings": self.warnings,
            "errors": self.errors,
        }
