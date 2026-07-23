"""Main orchestrator: import a LightClaw migration archive into Octop.

Phases (in order):
  1. Validate archive + parse manifest.
  2. Create or find the target Octop agent.
  3. Import workspace files directly to disk (agent not yet running).
  4. Import uploaded files into agent inbound/.
  5. Import cron jobs.
  6. Import conversation sessions (JSONL + thread/session DB rows).
  7. Note env key scaffold (no values imported).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from octop.infra.gateway.threads import ThreadRegistry
from octop.infra.migration.archive_reader import ArchiveReader
from octop.infra.migration.field_mapping import (
    build_octop_cron_trigger,
    extract_disabled_skills,
    extract_job_prompt,
)
from octop.infra.migration.memory_migrator import migrate_sessions
from octop.infra.migration.report import MigrationReport
from octop.infra.migration.uploads_migrator import migrate_uploads
from octop.infra.utils.paths import PathLayout
from octop.infra.utils.ulid import new_cron_id, new_short_id

if TYPE_CHECKING:
    from octop.infra.db.repos.agents import AgentRepo
    from octop.infra.db.repos.cron import CronJobRepo
    from octop.infra.db.repos.sessions import SessionRepo
    from octop.infra.db.repos.threads import ThreadRepo
    from octop.infra.db.repos.users import UserRepo

logger = logging.getLogger(__name__)

# Workspace files that are always safe to overwrite (core memory/soul files).
_ALWAYS_OVERWRITE_PATTERNS = frozenset(
    {
        "SOUL.md",
        "MEMORY.md",
        "USER.md",
        "AGENTS.md",
        "DAILY_TALK.md",
    }
)

# Skip writing these workspace paths into the agent workspace.
_WORKSPACE_SKIP_PREFIXES = (
    "sessions/",
    "uploads/",
    "models/",
    "embedding_cache/",
)


def _new_cron_id() -> str:
    return new_cron_id()


def _should_skip_workspace_path(rel_path: str) -> bool:
    for prefix in _WORKSPACE_SKIP_PREFIXES:
        if rel_path.startswith(prefix):
            return True
    return rel_path.endswith(".db")


async def run_import(
    zip_bytes: bytes,
    *,
    user_id: int,
    paths: PathLayout,
    agent_repo: AgentRepo,
    cron_repo: CronJobRepo,
    thread_repo: ThreadRepo,
    session_repo: SessionRepo,
    user_repo: UserRepo,
    agent_name: str | None = None,
) -> MigrationReport:
    """Run a full LightClaw → Octop import.

    Args:
        zip_bytes: Raw bytes of the migration archive.
        user_id: Octop user ID to own the imported agent/resources.
        paths: PathLayout for locating ``~/.octop/``.
        *_repo: Repo instances from SharedServices.
        agent_name: Override agent display name (defaults to "迁移自 LightClaw").

    Returns:
        :class:`MigrationReport` summarising what was imported.
    """
    report = MigrationReport()

    try:
        reader = ArchiveReader(zip_bytes)
        reader.open()
    except ValueError as exc:
        report.error(f"Archive validation failed: {exc}")
        return report

    with reader:
        # ----------------------------------------------------------------
        # Phase 1: Validate + manifest — reader already open, skip re-open
        # ----------------------------------------------------------------
        try:
            manifest = reader.validate()
        except ValueError as exc:
            report.error(f"Archive validation failed: {exc}")
            return report

        # ----------------------------------------------------------------
        # Phase 2: Create / find agent
        # Parse config/lightclaw.json to extract default_model and
        # the list of disabled skills for config_json.
        # ----------------------------------------------------------------
        lc_config: dict[str, Any] = reader.read_json("config/lightclaw.json") or {}

        display_name = agent_name or manifest.agent_name or "迁移自 LightClaw"

        new_agent_id = new_short_id()
        for _ in range(15):
            if agent_repo.get(new_agent_id) is None:
                break
            new_agent_id = new_short_id()
        description = manifest.agent_description or "迁移自 LightClaw"

        default_model = None

        # Build the set of explicitly-disabled skill names so Phase 3 can skip
        # their workspace directories entirely.
        disabled_skills: frozenset[str] = frozenset(extract_disabled_skills(lc_config))

        try:
            agent_repo.create(
                agent_id=new_agent_id,
                user_id=user_id,
                name=display_name,
                description=description,
                default_model=default_model,
            )
            report.agent_id = new_agent_id
            report.agent_created = True
        except Exception:
            logger.exception("Failed to create agent during import")
            report.error("Failed to create agent row")
            return report

        # ----------------------------------------------------------------
        # Phase 3: Workspace files
        #
        # Agent has not started yet — write directly to the workspace
        # directory on disk.  BackendWorkspace.aupload_bytes() resolves
        # paths via Path.resolve() which changes /tmp → /private/tmp on
        # macOS, causing root_dir mismatch inside the filesystem backend
        # and writing files to a mirrored host-path subtree inside the
        # workspace dir.  Plain Path.write_bytes() is simpler and correct
        # here because the destination is always a local filesystem path.
        # ----------------------------------------------------------------
        workspace_dir = paths.ensure_agent_workspace(new_agent_id)

        ws_written = 0
        ws_skipped = 0
        # Track which identity files were written and how many unique skills dirs.
        identity_files: list[str] = []
        skills_dirs: set[str] = set()

        for member_name, raw_bytes in reader.iter_prefix("workspace/"):
            rel_path = member_name[len("workspace/") :]
            if not rel_path:
                continue
            if _should_skip_workspace_path(rel_path):
                ws_skipped += 1
                continue
            # Skip skills that were explicitly disabled in LightClaw.
            # rel_path format: "skills/<name>/..." — extract <name> from parts[1].
            if rel_path.startswith("skills/"):
                parts = rel_path.split("/")
                skill_name = parts[1] if len(parts) >= 2 else ""
                if skill_name and skill_name in disabled_skills:
                    ws_skipped += 1
                    continue
            try:
                dest = workspace_dir / rel_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(raw_bytes)
                ws_written += 1
                # Track identity files at workspace root.
                if rel_path in _ALWAYS_OVERWRITE_PATTERNS:
                    identity_files.append(rel_path)
                # Track unique enabled skills dirs (skills/<name>/...).
                if rel_path.startswith("skills/"):
                    parts = rel_path.split("/")
                    if len(parts) >= 2 and parts[1]:
                        skills_dirs.add(parts[1])
            except Exception:
                logger.exception("Failed to write workspace file %s", rel_path)
                report.warn(f"Could not write workspace file {rel_path!r}")
                ws_skipped += 1

        report.workspace_files_written = ws_written
        report.workspace_files_skipped = ws_skipped
        report.identity_files_written = identity_files
        report.skills_imported = len(skills_dirs)

        # ----------------------------------------------------------------
        # Phase 4: Uploads
        # Same reasoning as Phase 3: write directly to disk via
        # migrate_uploads which accepts a DiskWorkspace-like adapter.
        # ----------------------------------------------------------------
        await migrate_uploads(reader, workspace_dir, report)

        # ----------------------------------------------------------------
        # Phase 5: Cron jobs
        # ----------------------------------------------------------------
        jobs_config: dict[str, Any] = reader.read_json("config/jobs.json") or {}
        jobs_list = jobs_config.get("jobs", [])
        if isinstance(jobs_list, list):
            cron_imported = 0
            cron_skipped = 0
            for job in jobs_list:
                if not isinstance(job, dict):
                    cron_skipped += 1
                    continue
                job_id = str(job.get("id") or "")
                schedule = job.get("schedule", {})
                if not (job_id and schedule):
                    cron_skipped += 1
                    continue
                prompt = extract_job_prompt(job)
                if not prompt:
                    # All extraction paths returned empty; skip with a visible warning.
                    report.warn(f"Cron job {job_id!r} has no extractable prompt — skipped")
                    cron_skipped += 1
                    continue
                trigger = build_octop_cron_trigger(schedule)
                cron_id = _new_cron_id()
                cron_session_key = ThreadRegistry.make_key(
                    agent_id=new_agent_id,
                    channel_type="dashboard",
                    channel_subject_id=str(user_id),
                    channel_chat_type="dm",
                )
                try:
                    cron_repo.create(
                        cron_id=cron_id,
                        agent_id=new_agent_id,
                        user_id=user_id,
                        trigger=trigger,
                        prompt=prompt,
                        session_key=cron_session_key,
                        fresh_thread=False,
                    )
                    cron_imported += 1
                except Exception:
                    logger.exception("Failed to import cron job %s", job_id)
                    report.warn(f"Could not import cron job {job_id!r}")
                    cron_skipped += 1
            report.cron_jobs_imported = cron_imported
            report.cron_jobs_skipped = cron_skipped

        # ----------------------------------------------------------------
        # Phase 6: Sessions (conversation history)
        # ----------------------------------------------------------------
        await migrate_sessions(
            reader,
            agent_id=new_agent_id,
            user_id=user_id,
            workspace_dir=workspace_dir,
            thread_repo=thread_repo,
            session_repo=session_repo,
            report=report,
        )

    return report
