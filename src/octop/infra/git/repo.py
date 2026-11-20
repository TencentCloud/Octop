"""Git queries and operations through a workspace execution target.

The target is either a host subprocess (local workspace) or the harness
backend's ``execute`` inside a docker sandbox, so git always runs next to the
files it operates on. Read queries pin ``--no-optional-locks -c
core.fsmonitor=`` so a repository's own config cannot execute helper scripts
through Octop's background refreshes; user-initiated write operations run
without that override.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from octop.infra.errors import ErrorCode, OctopError
from octop.infra.git.target import GitTarget

_READ_ONLY_ARGS = ["--no-optional-locks", "-c", "core.fsmonitor="]
_STATUS_TIMEOUT_S = 60.0
_DIFF_TIMEOUT_S = 30.0
_LOG_TIMEOUT_S = 30.0
_WRITE_TIMEOUT_S = 60.0
_PUSH_TIMEOUT_S = 180.0
_HISTORY_TIMEOUT_S = 60.0
_STATUS_MAX_BYTES = 8 * 1024 * 1024
_DIFF_MAX_BYTES = 2 * 1024 * 1024
_LOG_MAX_BYTES = 1024 * 1024
_HISTORY_MAX_BYTES = 4 * 1024 * 1024
_PUSH_MAX_BYTES = 2 * 1024 * 1024
_SMALL_MAX_BYTES = 64 * 1024
_UNTRACKED_SAMPLE_BYTES = 1024 * 1024
_LOG_MAX_LIMIT = 200

_STATUS_NAMES = {
    "M": "modified",
    "A": "added",
    "D": "deleted",
    "R": "renamed",
    "C": "copied",
    "T": "typechange",
}


@dataclass
class GitFileChange:
    path: str
    status: str
    staged: bool
    added: int | None = None
    removed: int | None = None
    orig_path: str | None = None


@dataclass
class GitCommit:
    sha: str
    short: str
    author: str
    date: str
    subject: str


@dataclass
class GitStatusSnapshot:
    is_repo: bool
    git_available: bool
    branch: str | None = None
    upstream: str | None = None
    ahead: int = 0
    behind: int = 0
    head_short: str | None = None
    files: list[GitFileChange] = field(default_factory=list)
    added: int = 0
    removed: int = 0


@dataclass
class _PorcelainEntry:
    path: str
    xy: str = ""
    orig: str | None = None
    unmerged: bool = False
    untracked: bool = False


@dataclass
class _PorcelainInfo:
    branch: str | None = None
    head_short: str | None = None
    upstream: str | None = None
    ahead: int = 0
    behind: int = 0
    entries: list[_PorcelainEntry] = field(default_factory=list)


def workspace_is_repo(target: GitTarget) -> bool:
    return target.exists(".git")


def _ensure_repo(target: GitTarget) -> None:
    if not workspace_is_repo(target):
        raise OctopError(ErrorCode.NOT_FOUND, "workspace is not a git repository")


def _normalize_repo_path(raw: str) -> str:
    text = str(raw or "").strip().replace("\\", "/").lstrip("/")
    parts = [part for part in text.split("/") if part not in ("", ".")]
    if not parts or any(part == ".." for part in parts):
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, f"invalid git path {raw!r}")
    return "/".join(parts)


async def _run_git(
    target: GitTarget,
    args: list[str],
    *,
    timeout: float,
    max_bytes: int,
    read_query: bool = False,
    check: bool = True,
) -> tuple[int, bytes, bytes]:
    if not await target.probe():
        raise OctopError(ErrorCode.WORKSPACE_OP_UNSUPPORTED, "git is not installed")
    full = [*args]
    if read_query:
        full = [*_READ_ONLY_ARGS, *args]
    try:
        code, stdout, stderr = await target.run(full, timeout=timeout, max_bytes=max_bytes)
    except TimeoutError:
        raise OctopError(
            ErrorCode.INTERNAL_ERROR, f"git {args[0]} timed out after {timeout:.0f}s"
        ) from None
    except FileNotFoundError:
        raise OctopError(ErrorCode.WORKSPACE_OP_UNSUPPORTED, "git is not installed") from None
    if check and code != 0:
        detail = stderr.decode("utf-8", "replace").strip()
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, detail[:400] or f"git {args[0]} failed")
    return code, stdout[:max_bytes], stderr[:max_bytes]


def _parse_status_porcelain(stdout: bytes) -> _PorcelainInfo:
    tokens = stdout.decode("utf-8", "surrogateescape").split("\0")
    info = _PorcelainInfo()
    i = 0
    while i < len(tokens):
        token = tokens[i]
        i += 1
        if not token:
            continue
        if token.startswith("# branch.head "):
            value = token[len("# branch.head ") :]
            info.branch = None if value == "(detached)" else value
        elif token.startswith("# branch.oid "):
            info.head_short = token[len("# branch.oid ") :][:8] or None
        elif token.startswith("# branch.upstream "):
            info.upstream = token[len("# branch.upstream ") :]
        elif token.startswith("# branch.ab "):
            for piece in token[len("# branch.ab ") :].split():
                if piece.startswith("+"):
                    info.ahead = int(piece[1:] or 0)
                elif piece.startswith("-"):
                    info.behind = int(piece[1:] or 0)
        elif token.startswith("? "):
            info.entries.append(_PorcelainEntry(path=token[2:], untracked=True))
        elif token.startswith("! "):
            continue
        elif token.startswith("1 "):
            fields = token.split(" ", 8)
            if len(fields) >= 9:
                info.entries.append(_PorcelainEntry(xy=fields[1], path=fields[8]))
        elif token.startswith("2 "):
            fields = token.split(" ", 9)
            if len(fields) >= 10:
                orig = tokens[i] if i < len(tokens) else None
                i += 1
                info.entries.append(_PorcelainEntry(xy=fields[1], path=fields[9], orig=orig))
        elif token.startswith("u "):
            fields = token.split(" ", 10)
            if len(fields) >= 11:
                info.entries.append(_PorcelainEntry(xy=fields[1], path=fields[10], unmerged=True))
    return info


def _parse_numstat(stdout: bytes) -> dict[str, tuple[int | None, int | None]]:
    tokens = stdout.decode("utf-8", "surrogateescape").split("\0")
    stats: dict[str, tuple[int | None, int | None]] = {}
    i = 0
    while i < len(tokens):
        token = tokens[i]
        i += 1
        if not token:
            continue
        parts = token.split("\t")
        added = int(parts[0]) if parts and parts[0].isdigit() else None
        removed = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
        if len(parts) >= 3 and parts[2]:
            stats[parts[2]] = (added, removed)
            continue
        if i + 2 <= len(tokens):
            i += 2
            new_path = tokens[i - 1]
            if new_path:
                stats[new_path] = (added, removed)
    return stats


def _untracked_added_lines(target: GitTarget, rel: str) -> int | None:
    if rel.endswith("/"):
        return None
    text = target.read_text(rel)
    if text is None:
        return None
    sample = text[:_UNTRACKED_SAMPLE_BYTES]
    if "\x00" in sample[:8192]:
        return None
    return len(sample.splitlines())


async def get_status(target: GitTarget) -> GitStatusSnapshot:
    available = await target.probe()
    if not workspace_is_repo(target):
        return GitStatusSnapshot(is_repo=False, git_available=available)
    if not available:
        return GitStatusSnapshot(is_repo=True, git_available=False)
    _, status_out, _ = await _run_git(
        target,
        # -uall lists untracked files individually (not collapsed dirs) so
        # per-file line counts and file-level focus both work.
        ["status", "--porcelain=v2", "--branch", "-z", "-uall"],
        timeout=_STATUS_TIMEOUT_S,
        max_bytes=_STATUS_MAX_BYTES,
        read_query=True,
    )
    _, unstaged_out, _ = await _run_git(
        target,
        ["diff", "--numstat", "-z"],
        timeout=_STATUS_TIMEOUT_S,
        max_bytes=_STATUS_MAX_BYTES,
        read_query=True,
    )
    _, staged_out, _ = await _run_git(
        target,
        ["diff", "--cached", "--numstat", "-z"],
        timeout=_STATUS_TIMEOUT_S,
        max_bytes=_STATUS_MAX_BYTES,
        read_query=True,
    )
    info = _parse_status_porcelain(status_out)
    unstaged_stats = _parse_numstat(unstaged_out)
    staged_stats = _parse_numstat(staged_out)
    files: list[GitFileChange] = []
    for entry in info.entries:
        if entry.untracked:
            files.append(
                GitFileChange(
                    path=entry.path,
                    status="untracked",
                    staged=False,
                    added=_untracked_added_lines(target, entry.path),
                )
            )
            continue
        if entry.unmerged or "U" in entry.xy or entry.xy in ("AA", "DD"):
            files.append(GitFileChange(path=entry.path, status="conflicted", staged=False))
            continue
        index_status = entry.xy[0] if entry.xy else "."
        worktree_status = entry.xy[1] if len(entry.xy) > 1 else "."
        if index_status != ".":
            added, removed = staged_stats.get(entry.path, (None, None))
            files.append(
                GitFileChange(
                    path=entry.path,
                    status=_STATUS_NAMES.get(index_status, "modified"),
                    staged=True,
                    added=added,
                    removed=removed,
                    orig_path=entry.orig,
                )
            )
        if worktree_status != ".":
            added, removed = unstaged_stats.get(entry.path, (None, None))
            files.append(
                GitFileChange(
                    path=entry.path,
                    status=_STATUS_NAMES.get(worktree_status, "modified"),
                    staged=False,
                    added=added,
                    removed=removed,
                )
            )
    snapshot = GitStatusSnapshot(
        is_repo=True,
        git_available=True,
        branch=info.branch,
        upstream=info.upstream,
        ahead=info.ahead,
        behind=info.behind,
        head_short=info.head_short,
        files=files,
    )
    snapshot.added = sum(f.added for f in files if f.added is not None)
    snapshot.removed = sum(f.removed for f in files if f.removed is not None)
    return snapshot


async def _is_tracked(target: GitTarget, rel: str) -> bool:
    code, _, _ = await _run_git(
        target,
        ["ls-files", "--error-unmatch", "--", rel],
        timeout=_DIFF_TIMEOUT_S,
        max_bytes=_SMALL_MAX_BYTES,
        read_query=True,
        check=False,
    )
    return code == 0


async def get_diff(target: GitTarget, raw_path: str, *, staged: bool) -> dict[str, object]:
    _ensure_repo(target)
    rel = _normalize_repo_path(raw_path)
    if staged:
        _, out, _ = await _run_git(
            target,
            # --no-ext-diff keeps the output a unified diff even when the
            # user configures an external diff driver (e.g. difftastic).
            ["diff", "--no-ext-diff", "--cached", "--", rel],
            timeout=_DIFF_TIMEOUT_S,
            max_bytes=_DIFF_MAX_BYTES,
            read_query=True,
            check=False,
        )
    else:
        _, out, _ = await _run_git(
            target,
            ["diff", "--no-ext-diff", "--", rel],
            timeout=_DIFF_TIMEOUT_S,
            max_bytes=_DIFF_MAX_BYTES,
            read_query=True,
            check=False,
        )
        if not out.strip() and not await _is_tracked(target, rel):
            if target.read_text(rel) is None:
                raise OctopError(ErrorCode.NOT_FOUND, f"cannot diff {rel!r}: not a file")
            _, out, _ = await _run_git(
                target,
                ["diff", "--no-ext-diff", "--no-index", "--", os.devnull, rel],
                timeout=_DIFF_TIMEOUT_S,
                max_bytes=_DIFF_MAX_BYTES,
                read_query=True,
                check=False,
            )
    text = out.decode("utf-8", "replace")
    return {"path": rel, "diff": text, "truncated": len(out) >= _DIFF_MAX_BYTES}


async def get_log(target: GitTarget, limit: int = 30) -> list[GitCommit]:
    _ensure_repo(target)
    bounded = max(1, min(int(limit), _LOG_MAX_LIMIT))
    _, out, _ = await _run_git(
        target,
        ["log", f"-n{bounded}", "--pretty=format:%H%x1f%h%x1f%an%x1f%aI%x1f%s%x1e"],
        timeout=_LOG_TIMEOUT_S,
        max_bytes=_LOG_MAX_BYTES,
        read_query=True,
    )
    commits: list[GitCommit] = []
    for record in out.decode("utf-8", "replace").split("\x1e"):
        record = record.strip("\n")
        if not record.strip():
            continue
        parts = record.split("\x1f")
        if len(parts) < 5:
            continue
        commits.append(
            GitCommit(
                sha=parts[0],
                short=parts[1],
                author=parts[2],
                date=parts[3],
                subject=parts[4],
            )
        )
    return commits


async def stage_paths(target: GitTarget, paths: list[str]) -> None:
    _ensure_repo(target)
    rels = [_normalize_repo_path(p) for p in paths]
    await _run_git(
        target,
        ["add", "--", *rels],
        timeout=_WRITE_TIMEOUT_S,
        max_bytes=_SMALL_MAX_BYTES,
    )


async def unstage_paths(target: GitTarget, paths: list[str]) -> None:
    _ensure_repo(target)
    rels = [_normalize_repo_path(p) for p in paths]
    await _run_git(
        target,
        ["restore", "--staged", "--", *rels],
        timeout=_WRITE_TIMEOUT_S,
        max_bytes=_SMALL_MAX_BYTES,
    )


async def discard_paths(target: GitTarget, paths: list[str]) -> None:
    _ensure_repo(target)
    rels = [_normalize_repo_path(p) for p in paths]
    tracked: list[str] = []
    untracked: list[str] = []
    for rel in rels:
        (tracked if await _is_tracked(target, rel) else untracked).append(rel)
    if tracked:
        await _run_git(
            target,
            ["restore", "--", *tracked],
            timeout=_WRITE_TIMEOUT_S,
            max_bytes=_SMALL_MAX_BYTES,
        )
    for rel in untracked:
        try:
            target.delete(rel)
        except Exception as exc:  # noqa: BLE001 - report per-file failure
            raise OctopError(ErrorCode.INTERNAL_ERROR, f"cannot discard {rel!r}: {exc}") from exc


async def commit_paths(
    target: GitTarget, message: str, *, include_unstaged: bool = False
) -> dict[str, str]:
    _ensure_repo(target)
    text = str(message or "").strip()
    if not text:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "empty commit message")
    if include_unstaged:
        await _run_git(
            target,
            ["add", "-A"],
            timeout=_WRITE_TIMEOUT_S,
            max_bytes=_SMALL_MAX_BYTES,
        )
    await _run_git(
        target,
        ["commit", "-m", text],
        timeout=_WRITE_TIMEOUT_S,
        max_bytes=_SMALL_MAX_BYTES,
    )
    _, out, _ = await _run_git(
        target,
        ["rev-parse", "--short", "HEAD"],
        timeout=_DIFF_TIMEOUT_S,
        max_bytes=_SMALL_MAX_BYTES,
        read_query=True,
    )
    return {"commit": out.decode("utf-8", "replace").strip()}


async def push_branch(target: GitTarget) -> dict[str, object]:
    """Push the current branch; set upstream on first push (never forces)."""
    _ensure_repo(target)
    _, out, _ = await _run_git(
        target,
        ["rev-parse", "--abbrev-ref", "HEAD"],
        timeout=_DIFF_TIMEOUT_S,
        max_bytes=_SMALL_MAX_BYTES,
        read_query=True,
    )
    branch = out.decode("utf-8", "replace").strip()
    if not branch or branch == "HEAD":
        raise OctopError(ErrorCode.GIT_PUSH_DETACHED, "cannot push while HEAD is detached")

    code, upstream_out, _ = await _run_git(
        target,
        ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
        timeout=_DIFF_TIMEOUT_S,
        max_bytes=_SMALL_MAX_BYTES,
        read_query=True,
        check=False,
    )
    upstream = upstream_out.decode("utf-8", "replace").strip() if code == 0 else ""

    if upstream:
        args = ["push"]
        remote = upstream.split("/", 1)[0]
    else:
        args = ["push", "--set-upstream", "origin", branch]
        remote = "origin"

    _, push_out, _ = await _run_git(
        target,
        args,
        timeout=_PUSH_TIMEOUT_S,
        max_bytes=_PUSH_MAX_BYTES,
    )
    output = push_out.decode("utf-8", "replace").strip()
    return {
        "branch": branch,
        "remote": remote,
        "upstream": upstream or f"{remote}/{branch}",
        "set_upstream": not upstream,
        "output": output[-2000:],
    }


async def get_history(target: GitTarget, limit: int = 50) -> list[dict[str, object]]:
    """``git log --graph`` rows with commit metadata and signature status.

    Graph connector lines (no commit on them) are returned with ``sha=None``
    so the renderer can keep merge lanes intact. ``signature`` follows git's
    ``%G?``: G good, B bad, U unknown validity, X/Y expired, R revoked,
    E missing key, N unsigned.
    """
    _ensure_repo(target)
    bounded = max(1, min(int(limit), 200))
    _, out, _ = await _run_git(
        target,
        [
            "log",
            f"-n{bounded}",
            "--graph",
            "--date=iso-strict",
            "--pretty=format:%x1f%H%x1f%h%x1f%an%x1f%cn%x1f%aI%x1f%D%x1f%G?%x1f%GS%x1f%s",
        ],
        timeout=_HISTORY_TIMEOUT_S,
        max_bytes=_HISTORY_MAX_BYTES,
        read_query=True,
    )
    rows: list[dict[str, object]] = []
    for line in out.decode("utf-8", "replace").split("\n"):
        if not line.strip():
            continue
        if "\x1f" not in line:
            rows.append({"graph": line.rstrip(), "sha": None})
            continue
        graph, rest = line.split("\x1f", 1)
        fields = rest.split("\x1f")
        if len(fields) < 9:
            continue
        rows.append(
            {
                "graph": graph.rstrip(),
                "sha": fields[0],
                "short": fields[1],
                "author": fields[2],
                "committer": fields[3],
                "date": fields[4],
                "refs": fields[5],
                "signature": fields[6],
                "signer": fields[7],
                "subject": fields[8],
            }
        )
    return rows
