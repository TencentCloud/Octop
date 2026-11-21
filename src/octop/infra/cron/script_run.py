"""Run one cron script in the agent sandbox, or on the host when there is none."""

from __future__ import annotations

import asyncio
import contextlib
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from octop.infra.backend.resolver import backend_spec_supports_execution
from octop.infra.backend.shell_output import decode_child_output
from octop.infra.utils.ulid import new_ulid

SCRIPT_TIMEOUT_SECONDS = 120
_OUTPUT_LIMIT = 100_000
_SUFFIX = {"python": ".py", "bash": ".sh", "powershell": ".ps1"}


class ScriptRunError(Exception):
    """A script could not be started. ``code`` is ``interpreter_missing``, ``timeout``, or ``unreadable``."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class ScriptRunResult:
    exit_code: int
    stdout: str
    stderr: str


def _clip(text: str) -> str:
    if len(text) <= _OUTPUT_LIMIT:
        return text
    return text[:_OUTPUT_LIMIT]


def _sandbox_command(lang: str, path: str) -> str:
    quoted = _shell_quote(path)
    if lang == "python":
        return f"python3 {quoted}"
    if lang == "bash":
        return f"bash {quoted}"
    return (
        "if command -v pwsh >/dev/null 2>&1; then "
        f"pwsh -NoProfile -File {quoted}; "
        "elif command -v powershell >/dev/null 2>&1; then "
        f"powershell -NoProfile -File {quoted}; "
        "else exit 127; fi"
    )


def _shell_quote(path: str) -> str:
    import shlex

    return shlex.quote(path)


def _host_command(lang: str, script: Path) -> list[str]:
    if lang == "python":
        return [sys.executable, str(script)]
    if lang == "bash":
        for name in ("bash", "sh"):
            found = shutil.which(name)
            if found:
                return [found, str(script)]
        raise ScriptRunError("interpreter_missing", "bash")
    for name in ("pwsh", "powershell"):
        found = shutil.which(name)
        if found:
            return [found, "-NoProfile", "-File", str(script)]
    raise ScriptRunError("interpreter_missing", "powershell")


def _spec_uses_host_workspace(spec: Any) -> bool:
    """True when script files live on the host workspace directory."""
    if spec is None:
        return True
    if isinstance(spec, str):
        return spec in {"filesystem", "local", "local_shell"}
    if not isinstance(spec, dict):
        return False
    kind = str(spec.get("type") or "")
    if kind in {"", "filesystem", "local", "local_shell"}:
        return True
    if kind == "composite":
        return _spec_uses_host_workspace(spec.get("default"))
    return False


def _inside(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


async def run_cron_script(
    *,
    lang: str,
    source: str,
    body: str,
    path: str | None,
    workspace: Any,
    backend_spec: Any = None,
) -> ScriptRunResult:
    """Execute one script. Non-zero exits are returned, not raised."""
    backend = getattr(workspace, "backend", None)
    execute = getattr(backend, "execute", None)
    # Filesystem and object storage have no execute. Docker, OpenSandbox, and
    # the local shell do, and that is where the script must run.
    sandbox = callable(execute) and (
        backend_spec is None or backend_spec_supports_execution(backend_spec)
    )
    if sandbox:
        return await _run_via_execute(
            workspace,
            execute,
            lang=lang,
            source=source,
            body=body,
            path=path,
        )
    cwd = _host_cwd(workspace, backend_spec)
    return await _run_on_host(
        workspace,
        lang=lang,
        source=source,
        body=body,
        path=path,
        cwd=cwd,
    )


def _host_cwd(workspace: Any, spec: Any) -> Path | None:
    if not _spec_uses_host_workspace(spec):
        return None
    raw = getattr(workspace, "workspace_dir", None)
    if raw is None:
        return None
    path = Path(raw)
    return path if path.is_dir() else None


async def _run_via_execute(
    workspace: Any,
    execute: Any,
    *,
    lang: str,
    source: str,
    body: str,
    path: str | None,
) -> ScriptRunResult:
    cleanup: str | None = None
    if source == "file":
        target = path or ""
        exists = getattr(workspace, "aexists", None)
        if callable(exists) and not await exists(target):
            raise ScriptRunError("unreadable", target)
    else:
        target = f".octop/cron-scripts/{new_ulid()}{_SUFFIX.get(lang, '.txt')}"
        mkdir = getattr(workspace, "amkdir", None)
        if callable(mkdir):
            await mkdir(".octop/cron-scripts")
        await workspace.awrite_text(target, body)
        cleanup = target
    command = _sandbox_command(lang, target)
    try:
        result = await asyncio.to_thread(execute, command, timeout=SCRIPT_TIMEOUT_SECONDS)
    finally:
        if cleanup:
            delete = getattr(workspace, "adelete", None)
            if callable(delete):
                with contextlib.suppress(Exception):
                    await delete(cleanup)
    raw_code = getattr(result, "exit_code", None)
    exit_code = 0 if raw_code is None else int(raw_code)
    output = _clip(str(getattr(result, "output", "") or ""))
    if exit_code == 124:
        raise ScriptRunError("timeout", str(SCRIPT_TIMEOUT_SECONDS))
    if exit_code == 127:
        raise ScriptRunError("interpreter_missing", lang)
    return ScriptRunResult(exit_code=exit_code, stdout=output, stderr="")


async def _run_on_host(
    workspace: Any,
    *,
    lang: str,
    source: str,
    body: str,
    path: str | None,
    cwd: Path | None,
) -> ScriptRunResult:
    owned: Path | None = None
    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    work = cwd
    if work is None:
        temp_dir = tempfile.TemporaryDirectory(prefix="octop-cron-")
        work = Path(temp_dir.name)
    try:
        target = (
            _existing_workspace_file(work, path) if source == "file" and cwd is not None else None
        )
        if target is None:
            script_body = body if source != "file" else await _read_workspace(workspace, path or "")
            if temp_dir is None:
                temp_dir = tempfile.TemporaryDirectory(prefix="octop-cron-")
            owned = Path(temp_dir.name) / f"script{_SUFFIX.get(lang, '.txt')}"
            owned.write_text(script_body, encoding="utf-8")
            target = owned
        argv = _host_command(lang, target)
        process = await asyncio.create_subprocess_exec(
            *argv,
            cwd=str(work),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=SCRIPT_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            process.kill()
            await process.wait()
            raise ScriptRunError("timeout", str(SCRIPT_TIMEOUT_SECONDS)) from None
        return ScriptRunResult(
            exit_code=int(process.returncode or 0),
            stdout=_clip(decode_child_output(stdout)),
            stderr=_clip(decode_child_output(stderr)),
        )
    finally:
        if owned is not None:
            owned.unlink(missing_ok=True)
        if temp_dir is not None:
            temp_dir.cleanup()


def _existing_workspace_file(cwd: Path, path: str | None) -> Path | None:
    rel = (path or "").strip()
    if not rel:
        return None
    root = cwd.resolve()
    candidate = (root / PurePosixPath(rel)).resolve()
    if not _inside(root, candidate) or not candidate.is_file():
        return None
    return candidate


async def _read_workspace(workspace: Any, path: str) -> str:
    reader = getattr(workspace, "aread_text", None)
    if not callable(reader):
        raise ScriptRunError("unreadable", path)
    try:
        text = await reader(path)
    except Exception as exc:
        raise ScriptRunError("unreadable", path) from exc
    if not isinstance(text, str):
        raise ScriptRunError("unreadable", path)
    return text
