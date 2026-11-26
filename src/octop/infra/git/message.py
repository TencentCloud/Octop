"""AI-generated Conventional Commit messages for workspace changes."""

from __future__ import annotations

import asyncio
import re
from typing import Any

from octop.infra.errors import ErrorCode, OctopError
from octop.infra.git.repo import GitFileChange, get_diff, get_status
from octop.infra.git.target import GitTarget
from octop.infra.utils.llm_text import strip_thinking
from octop.infra.utils.locale import normalize_locale

MAX_PROMPT_FILES = 20
MAX_DIFF_FILES = 8
MAX_DIFF_CHARS = 12_000
MAX_DIFF_CHARS_PER_FILE = 2_000
MAX_COMMIT_MESSAGE_CHARS = 1_000
_TIMEOUT_SECONDS = 30.0

CONVENTIONAL_COMMIT_RE = re.compile(
    r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)"
    r"(\([^)]+\))?!?: .{1,100}$"
)

_SYSTEM_PROMPT = (
    "You write Git commit messages. Return only the commit message text, "
    "with no explanation, quotes or code fences."
)


def build_commit_message_prompt(
    *,
    branch: str | None,
    files: list[GitFileChange],
    diffs: list[dict[str, str]],
    locale: str,
) -> str:
    language = "Chinese" if normalize_locale(locale).startswith("zh") else "English"
    visible = files[:MAX_PROMPT_FILES]
    omitted = max(0, len(files) - len(visible))
    file_lines = [
        f"- {file.status} {file.path} (+{file.added or 0}/-{file.removed or 0})" for file in visible
    ]
    if omitted:
        file_lines.append(f"- ... {omitted} more files")

    diff_chunks: list[str] = []
    used = 0
    for diff in diffs[:MAX_DIFF_FILES]:
        patch = str(diff.get("patch") or "").strip()
        if not patch:
            continue
        remaining = MAX_DIFF_CHARS - used
        if remaining <= 0:
            break
        clipped = patch[: min(MAX_DIFF_CHARS_PER_FILE, remaining)]
        chunk = f"--- {diff.get('path', '')}\n{clipped}"
        diff_chunks.append(chunk)
        used += len(chunk)

    return "\n".join(
        [
            "Write exactly one Git commit message for the workspace changes below.",
            "Return only the commit message text.",
            "",
            "Hard requirements:",
            "- The first line must be a valid Conventional Commit subject.",
            "- Use one of: feat, fix, docs, style, refactor, perf, test, build, ci, chore, revert.",
            "- Keep the Conventional Commit type and optional scope in English.",
            f"- Write the subject and any body in {language}.",
            "- Keep the subject under 72 characters.",
            "- Do not explain your reasoning or repeat these instructions.",
            "",
            f"Current branch: {(branch or '').strip() or '(detached or unknown)'}",
            "",
            "Changed files:",
            "\n".join(file_lines) or "- (no file summary available)",
            "",
            "Diff excerpts:",
            "\n\n".join(diff_chunks)
            or "(diff unavailable; infer only from the changed file summary)",
        ]
    )


def validate_commit_message(raw: str) -> str:
    """Normalize model output and require a Conventional Commit subject."""
    text = str(raw or "").strip()
    fenced = re.match(r"^```(?:[a-zA-Z0-9_-]+)?\s*([\s\S]*?)\s*```$", text)
    if fenced:
        text = fenced.group(1)
    text = re.sub(r"^commit message:\s*", "", text, flags=re.IGNORECASE).strip()
    if (text.startswith('"') and text.endswith('"')) or (
        text.startswith("'") and text.endswith("'")
    ):
        text = text[1:-1]
    text = text.strip()[:MAX_COMMIT_MESSAGE_CHARS].strip()
    subject = text.splitlines()[0].strip() if text else ""
    if not text or not CONVENTIONAL_COMMIT_RE.match(subject):
        raise OctopError(
            ErrorCode.GIT_COMMIT_MESSAGE_INVALID,
            "model did not return a usable Conventional Commit message",
        )
    return text


async def generate_commit_message(
    *,
    models: Any,
    target: GitTarget,
    include_unstaged: bool,
    locale: str,
    default_model: str | None = None,
) -> str:
    status = await get_status(target)
    files = [f for f in status.files if f.staged or include_unstaged]
    if not files:
        raise OctopError(ErrorCode.GIT_NO_CHANGES, "there are no changes to commit")

    diffs: list[dict[str, str]] = []
    for change in files[:MAX_DIFF_FILES]:
        result = await get_diff(target, change.path, staged=change.staged)
        diffs.append({"path": change.path, "patch": str(result.get("diff") or "")})

    prompt = build_commit_message_prompt(
        branch=status.branch, files=files, diffs=diffs, locale=locale
    )
    access = models.get(default_model)
    try:
        raw = await asyncio.wait_for(
            access.ainvoke_text(prompt, system=_SYSTEM_PROMPT, timeout_s=_TIMEOUT_SECONDS),
            timeout=_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        raise OctopError(
            ErrorCode.GIT_COMMIT_MESSAGE_INVALID, "commit message generation timed out"
        ) from None
    except Exception:
        raise OctopError(
            ErrorCode.GIT_COMMIT_MESSAGE_INVALID, "commit message generation failed"
        ) from None
    return validate_commit_message(strip_thinking(raw or ""))


__all__ = [
    "build_commit_message_prompt",
    "generate_commit_message",
    "validate_commit_message",
]
