"""Git queries and operations for agent workspaces."""

from octop.infra.git.binary import MIN_GIT_VERSION, GitBinary, resolve_git_binary
from octop.infra.git.message import (
    build_commit_message_prompt,
    generate_commit_message,
    validate_commit_message,
)
from octop.infra.git.repo import (
    GitCommit,
    GitFileChange,
    GitStatusSnapshot,
    commit_paths,
    discard_paths,
    get_diff,
    get_history,
    get_log,
    get_status,
    push_branch,
    stage_paths,
    unstage_paths,
    workspace_is_repo,
)
from octop.infra.git.target import (
    GitTarget,
    HostGitTarget,
    SandboxGitTarget,
    spec_uses_docker,
)

__all__ = [
    "GitBinary",
    "GitCommit",
    "GitFileChange",
    "GitStatusSnapshot",
    "GitTarget",
    "HostGitTarget",
    "MIN_GIT_VERSION",
    "SandboxGitTarget",
    "build_commit_message_prompt",
    "commit_paths",
    "discard_paths",
    "generate_commit_message",
    "get_diff",
    "get_history",
    "get_log",
    "get_status",
    "push_branch",
    "resolve_git_binary",
    "spec_uses_docker",
    "stage_paths",
    "unstage_paths",
    "validate_commit_message",
    "workspace_is_repo",
]
