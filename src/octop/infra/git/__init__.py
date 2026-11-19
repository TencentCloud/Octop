"""Git queries and operations for agent workspaces (local repositories)."""

from octop.infra.git.repo import (
    GitCommit,
    GitFileChange,
    GitStatusSnapshot,
    commit_paths,
    discard_paths,
    get_diff,
    get_log,
    get_status,
    git_available,
    stage_paths,
    unstage_paths,
    workspace_is_repo,
)

__all__ = [
    "GitCommit",
    "GitFileChange",
    "GitStatusSnapshot",
    "commit_paths",
    "discard_paths",
    "get_diff",
    "get_log",
    "get_status",
    "git_available",
    "stage_paths",
    "unstage_paths",
    "workspace_is_repo",
]
