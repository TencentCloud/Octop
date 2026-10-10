"""Git worktree manager for Code Console sessions (S5).

Each coding session is bound to a dedicated git worktree under
``/var/lib/octop/worktrees`` so agents can edit files without touching the
user's main checkout. Worktrees are never allowed to point at ``/mnt`` (host
passthrough) — that path is rejected at creation time.

The manager exposes ``diff_patch`` so the UI can show a review-and-commit
surface before the user closes the session.
"""

from __future__ import annotations

import logging
import os
import subprocess
import uuid

from octop.infra.db.repos.coding_worktrees import WorktreeRepo, WorktreeRow

logger = logging.getLogger(__name__)

WORKTREE_ROOT = "/data/.octop/worktrees"
FORBIDDEN_PREFIXES = ("/mnt", "/mnt/")


def _is_path_allowed(path: str) -> bool:
    norm = os.path.normpath(path)
    return not (norm == "/mnt" or norm.startswith("/mnt/"))


class WorktreeManager:
    def __init__(self, worktree_repo: WorktreeRepo) -> None:
        self._repo = worktree_repo

    def _run(self, *args: str, cwd: str | None = None) -> subprocess.CompletedProcess[str]:
        # Worktrees are chown'd to the sandbox 'agent' user, so git sees a
        # different owner than the octop process (root). Bypass the ownership
        # safety check for these directories.
        return subprocess.run(
            ["git", "-c", "safe.directory=*", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=60,
        )

    def create(
        self,
        *,
        session_id: str,
        repository_path: str,
        branch: str | None = None,
    ) -> WorktreeRow:
        """Create a git worktree for the session.

        ``repository_path`` is the main checkout to branch from. The worktree
        lives under ``WORKTREE_ROOT`` and is rejected if it would resolve to
        ``/mnt``.
        """
        if not _is_path_allowed(repository_path):
            raise ValueError(f"repository path not allowed: {repository_path}")

        existing = self._repo.by_session(session_id)
        if existing is not None:
            return existing

        os.makedirs(WORKTREE_ROOT, exist_ok=True)
        worktree_id = f"wt_{uuid.uuid4().hex[:12]}"
        wt_path = os.path.join(WORKTREE_ROOT, f"{session_id}__{worktree_id}")
        branch = branch or f"octop/session/{session_id}"

        # git worktree add -b <branch> <path>
        r = self._run("worktree", "add", "-b", branch, wt_path, cwd=repository_path)
        if r.returncode != 0:
            # Fall back: branch may already exist (session resumed).
            r2 = self._run("worktree", "add", "--detach", wt_path, cwd=repository_path)
            if r2.returncode != 0:
                raise RuntimeError(
                    f"git worktree add failed: {r.stderr or r.stdout} / {r2.stderr or r2.stdout}"
                )

        row = self._repo.create(
            worktree_id=worktree_id,
            session_id=session_id,
            branch=branch,
            path=wt_path,
        )
        logger.info("worktree %s created at %s for session %s", worktree_id, wt_path, session_id)
        return row

    def get(self, session_id: str) -> WorktreeRow | None:
        return self._repo.by_session(session_id)

    def diff_patch(self, session_id: str) -> str:
        """Return the unified diff of all changes in the session worktree."""
        row = self._repo.by_session(session_id)
        if row is None:
            return ""
        r = self._run("diff", "HEAD", cwd=row.path)
        # also include untracked files
        r2 = self._run("ls-files", "--others", "--exclude-standard", cwd=row.path)
        patch = r.stdout or ""
        if r2.stdout.strip():
            for f in r2.stdout.strip().splitlines():
                full = os.path.join(row.path, f)
                if os.path.isfile(full):
                    patch += f"\n--- /dev/null\n+++ b/{f}\n"
                    try:
                        with open(full, encoding="utf-8", errors="replace") as fh:
                            content = fh.read()
                        patch += "".join(f"+{line}\n" for line in content.splitlines())
                    except OSError:
                        pass
        return patch

    def remove(self, session_id: str) -> None:
        row = self._repo.by_session(session_id)
        if row is None:
            return
        # git worktree remove --force
        try:
            self._run("worktree", "remove", "--force", row.path)
        except Exception:  # noqa: BLE001
            logger.exception("git worktree remove failed for %s", session_id)
        # cleanup the directory in case git left it
        try:
            import shutil

            if os.path.isdir(row.path):
                shutil.rmtree(row.path, ignore_errors=True)
        except Exception:  # noqa: BLE001
            pass
        self._repo.update_status(row.worktree_id, "removed")
