"""Spawn the Node helper to convert one Office snapshot into a PDF."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from octop.infra.errors import ErrorCode, OctopError
from octop.infra.office_preview.limits import CONVERT_TIMEOUT_SECONDS, MAX_OUTPUT_BYTES
from octop.infra.office_preview.runtime import RuntimeProbe, probe_runtime

logger = logging.getLogger(__name__)

_PDF_MAGIC = b"%PDF"


@dataclass(frozen=True)
class HelperConvertResult:
    pdf: bytes
    missing_fonts: tuple[str, ...]


def _kill_process_tree(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None or proc.pid is None:
        return
    if sys.platform != "win32" and os.name == "posix":
        with suppress(ProcessLookupError, PermissionError, OSError):
            os.killpg(proc.pid, signal.SIGKILL)
    with suppress(ProcessLookupError):
        proc.kill()


def _parse_helper_stdout(raw: bytes) -> tuple[bool, list[str]]:
    text = raw.decode("utf-8", errors="replace").strip()
    if not text:
        return False, []
    try:
        payload = json.loads(text.splitlines()[-1])
    except json.JSONDecodeError:
        return False, []
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        return False, []
    fonts_raw = payload.get("missingFonts") or []
    fonts: list[str] = []
    if isinstance(fonts_raw, list):
        for item in fonts_raw:
            if isinstance(item, str) and item.strip():
                fonts.append(item.strip())
    return True, fonts


async def convert_with_helper(
    input_path: Path,
    output_path: Path,
    *,
    probe: RuntimeProbe | None = None,
    timeout: float = CONVERT_TIMEOUT_SECONDS,
    cancel_event: asyncio.Event | None = None,
) -> HelperConvertResult:
    """Run ``node convert.mjs <input> <output>`` and return PDF bytes."""
    runtime = probe if probe is not None else await asyncio.to_thread(probe_runtime)
    if not runtime.available or runtime.node_bin is None or runtime.helper_dir is None:
        raise OctopError(
            ErrorCode.OFFICE_PREVIEW_UNAVAILABLE,
            "office preview runtime is not installed",
        )
    script = runtime.helper_dir / "convert.mjs"
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(runtime.helper_dir),
        "NODE_PATH": str(runtime.helper_dir / "node_modules"),
    }
    kwargs: dict[str, Any] = {
        "stdout": asyncio.subprocess.PIPE,
        "stderr": asyncio.subprocess.PIPE,
        "cwd": str(runtime.helper_dir),
        "env": env,
    }
    if os.name == "posix":
        kwargs["start_new_session"] = True
    elif sys.platform == "win32":
        import subprocess

        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

    proc = await asyncio.create_subprocess_exec(
        runtime.node_bin,
        str(script),
        str(input_path),
        str(output_path),
        **kwargs,
    )

    async def _wait() -> tuple[bytes, bytes]:
        stdout, stderr = await proc.communicate()
        return stdout, stderr

    wait_task = asyncio.create_task(_wait())
    cancel_task: asyncio.Task[None] | None = None
    if cancel_event is not None:

        async def _watch_cancel() -> None:
            await cancel_event.wait()

        cancel_task = asyncio.create_task(_watch_cancel())

    try:
        waiters: set[asyncio.Task[object]] = {wait_task}
        if cancel_task is not None:
            waiters.add(cancel_task)
        done, _pending = await asyncio.wait(
            waiters, timeout=timeout, return_when=asyncio.FIRST_COMPLETED
        )
        if cancel_task is not None and cancel_task in done:
            _kill_process_tree(proc)
            wait_task.cancel()
            raise asyncio.CancelledError
        if wait_task not in done:
            _kill_process_tree(proc)
            wait_task.cancel()
            raise OctopError(
                ErrorCode.OFFICE_PREVIEW_TIMEOUT,
                "office preview conversion timed out",
            )
        stdout, stderr = wait_task.result()
    except asyncio.CancelledError:
        _kill_process_tree(proc)
        wait_task.cancel()
        raise
    finally:
        if cancel_task is not None:
            cancel_task.cancel()
        if proc.returncode is None:
            _kill_process_tree(proc)
            with suppress(TimeoutError, asyncio.TimeoutError):
                await asyncio.wait_for(proc.wait(), timeout=5)

    if stderr:
        logger.debug("office preview helper stderr discarded (%s bytes)", len(stderr))

    ok, fonts = _parse_helper_stdout(stdout)
    if proc.returncode not in (0, None) or not ok:
        raise OctopError(
            ErrorCode.OFFICE_PREVIEW_CORRUPT,
            "office document could not be converted",
        )
    if not output_path.is_file():
        raise OctopError(
            ErrorCode.OFFICE_PREVIEW_FAILED,
            "office preview conversion produced no output",
        )
    size = output_path.stat().st_size
    if size > MAX_OUTPUT_BYTES:
        raise OctopError(
            ErrorCode.OFFICE_PREVIEW_TOO_LARGE,
            "office preview PDF exceeds the size limit",
        )
    pdf = output_path.read_bytes()
    if not pdf.startswith(_PDF_MAGIC):
        raise OctopError(
            ErrorCode.OFFICE_PREVIEW_FAILED,
            "office preview conversion produced invalid PDF",
        )
    return HelperConvertResult(pdf=pdf, missing_fonts=tuple(fonts[:16]))
