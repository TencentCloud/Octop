"""Cron job delivery mode — shared domain type (no DB / gateway imports)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal

CronTaskType = Literal["text", "agent", "script"]
CronScriptLang = Literal["python", "bash", "powershell"]
CronScriptSource = Literal["inline", "file"]
DEFAULT_CRON_TASK_TYPE: CronTaskType = "agent"
CRON_PROMPT_MAX_LEN = 2000
CRON_SCRIPT_MAX_LEN = 65536
CRON_SCRIPT_PATH_MAX_LEN = 1024
CRON_NAME_MAX_LEN = 80
CRON_NAME_FALLBACK_LEN = 40
_CRON_TASK_TYPES = frozenset({"text", "agent", "script"})
_SCRIPT_LANGS = frozenset({"python", "bash", "powershell"})
_SCRIPT_SOURCES = frozenset({"inline", "file"})


def normalize_cron_task_type(value: str | None) -> CronTaskType:
    """Coerce unknown values to the default delivery mode."""
    if value in _CRON_TASK_TYPES:
        return value  # type: ignore[return-value]
    return DEFAULT_CRON_TASK_TYPE


def require_cron_task_type(value: str) -> CronTaskType:
    """Validate user/agent input for task_type."""
    if value not in _CRON_TASK_TYPES:
        raise ValueError("task_type must be 'text', 'agent', or 'script'")
    return value  # type: ignore[return-value]


def infer_script_lang(body: str) -> CronScriptLang:
    """Pick a language when the caller left ``script_lang`` empty.

    A shebang wins. PowerShell-looking text is recognized next. Everything
    else, including a bare ``print``, is Python.
    """
    text = body.lstrip()
    first = text.splitlines()[0].strip().lower() if text else ""
    if first.startswith("#!"):
        if "powershell" in first or "pwsh" in first:
            return "powershell"
        if "python" in first:
            return "python"
        return "bash"
    lowered = text.lower()
    if lowered.startswith(("write-", "param(", "$")):
        return "powershell"
    return "python"


def require_script_body(body: str) -> str:
    """Validate an inline script. Empty and over-long bodies are rejected."""
    text = body.strip()
    if not text:
        raise ValueError("script must not be empty")
    if len(text) > CRON_SCRIPT_MAX_LEN:
        raise ValueError(f"script must be at most {CRON_SCRIPT_MAX_LEN} characters")
    return text


def require_script_path(path: str) -> str:
    """Workspace-relative script path. Absolute paths and ``..`` are rejected."""
    text = path.strip().replace("\\", "/")
    if not text:
        raise ValueError("script path must not be empty")
    if len(text) > CRON_SCRIPT_PATH_MAX_LEN:
        raise ValueError(f"script path must be at most {CRON_SCRIPT_PATH_MAX_LEN} characters")
    pure = PurePosixPath(text)
    if pure.is_absolute() or any(part == ".." or ":" in part for part in pure.parts):
        raise ValueError("script path must stay inside the workspace")
    cleaned = pure.as_posix()
    if cleaned in {"", "."}:
        raise ValueError("script path must not be empty")
    return cleaned


@dataclass(frozen=True)
class CronTaskSpec:
    """Storage-ready task fields for one cron job."""

    task_type: CronTaskType
    prompt: str
    allow_all: bool
    script_lang: str | None
    script_source: str | None
    script_path: str | None


def normalize_cron_task(
    *,
    task_type: str,
    prompt: str,
    allow_all: bool = False,
    script_lang: str | None = None,
    script_source: str | None = None,
    script_path: str | None = None,
) -> CronTaskSpec:
    """Validate one job's task fields and drop values that do not apply."""
    kind = require_cron_task_type(task_type)
    if kind != "script":
        text = require_cron_prompt(prompt)
        return CronTaskSpec(
            task_type=kind,
            prompt=text,
            allow_all=bool(allow_all) if kind == "agent" else False,
            script_lang=None,
            script_source=None,
            script_path=None,
        )
    lang = (script_lang or "").strip().lower()
    if lang in {"", "null", "none"}:
        lang = infer_script_lang(prompt)
    if lang not in _SCRIPT_LANGS:
        raise ValueError("script_lang must be 'python', 'bash', or 'powershell'")
    source = (script_source or "").strip().lower()
    if not source:
        source = "file" if (script_path or "").strip() else "inline"
    if source not in _SCRIPT_SOURCES:
        raise ValueError("script_source must be 'inline' or 'file'")
    if source == "file":
        path = require_script_path(script_path or prompt)
        return CronTaskSpec(
            task_type="script",
            prompt=path,
            allow_all=False,
            script_lang=lang,
            script_source="file",
            script_path=path,
        )
    body = require_script_body(prompt)
    return CronTaskSpec(
        task_type="script",
        prompt=body,
        allow_all=False,
        script_lang=lang,
        script_source="inline",
        script_path=None,
    )


def require_cron_prompt(prompt: str) -> str:
    """Validate cron instruction length and non-empty content."""
    text = prompt.strip()
    if not text:
        raise ValueError("prompt must not be empty")
    if len(text) > CRON_PROMPT_MAX_LEN:
        raise ValueError(f"prompt must be at most {CRON_PROMPT_MAX_LEN} characters")
    return text


def default_cron_name(prompt: str, cron_id: str) -> str:
    """Build a readable fallback name from the prompt prefix, else *cron_id*."""
    for line in prompt.splitlines():
        text = " ".join(line.strip().split())
        if text:
            return text[:CRON_NAME_FALLBACK_LEN]
    return cron_id


def require_cron_name(name: str | None, *, prompt: str, cron_id: str) -> str:
    """Return a non-empty display name; blank input falls back to the prompt prefix."""
    text = (name or "").strip() or default_cron_name(prompt, cron_id)
    if len(text) > CRON_NAME_MAX_LEN:
        raise ValueError(f"name must be at most {CRON_NAME_MAX_LEN} characters")
    return text
