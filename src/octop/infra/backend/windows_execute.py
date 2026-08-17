"""Windows harness ``execute`` compat: native GBK output + drive-path rewriting.

Two Windows-only defects in the third-party harness stack make agent shell
commands unusable on Chinese Windows; this module monkeypatches both. Applied
idempotently at import by :func:`apply` — see ``octop.infra.backend.__init__``.

1. **Encoding crash** — deepagents :class:`LocalShellBackend.execute` runs
   subprocesses with ``text=True`` (strict decode). On a server launched under
   ``PYTHONUTF8=1`` the pipe is decoded as strict UTF-8; Chinese-Windows
   native tools (``cmd`` builtins like ``dir``, git, ffmpeg, curl) emit
   GBK/CP936 bytes, so the pipe reader thread raises ``UnicodeDecodeError``,
   the whole output is dropped, and the agent sees ``<no output>`` with a
   spurious non-zero exit code — the exact confusion that sends agents into an
   endless self-diagnosis loop. Fixed with a bytes-mode reader +
   ``errors="replace"`` decode: Python children inherit ``PYTHONUTF8=1`` and
   emit UTF-8 (decodes cleanly); non-UTF-8 bytes degrade to U+FFFD instead of
   dropping the entire stream.

2. **Drive-path rewriting** — harness_agent ``BubbledLocalShellBackend``
   rewrites absolute path tokens in ``execute`` commands onto ``root_dir`` for
   virtual-mode filesystem alignment. Its tokenizer regex treats the ``/``
   after a drive letter as the start of a virtual path, so ``C:/Users/...``
   becomes ``C:'<root>'\\Users\\...`` and every absolute Windows path fails
   with "file not found". The bare-token lookbehind is tightened to also
   exclude ``:`` (and ``\\``), leaving ``C:\\...`` / ``C:/...`` untouched while
   genuine virtual paths (``cat /AGENTS.md``) still map onto ``root_dir``.
"""

from __future__ import annotations

import os
import re
import subprocess

from deepagents.backends.local_shell import LocalShellBackend
from deepagents.backends.protocol import ExecuteResponse

_APPLIED = False


def _patched_execute(
    self: LocalShellBackend,
    command: str,
    *,
    timeout: int | None = None,
) -> ExecuteResponse:
    """Mirror deepagents ``LocalShellBackend.execute`` with tolerant decoding.

    Kept as a self-contained copy (rather than a wrapper) because the original
    builds ``subprocess.run(..., text=True)`` inline and there is no hook to
    pass ``errors`` through. Mirrors deepagents 0.6.x behaviour exactly; only
    the reader differs (bytes mode + ``errors="replace"``).
    """
    if not command or not isinstance(command, str):
        return ExecuteResponse(
            output="Error: Command must be a non-empty string.",
            exit_code=1,
            truncated=False,
        )

    effective_timeout = timeout if timeout is not None else self._default_timeout
    if effective_timeout <= 0:
        msg = f"timeout must be positive, got {effective_timeout}"
        raise ValueError(msg)

    try:
        result = subprocess.run(  # noqa: S602
            command,
            check=False,
            shell=True,  # Intentional: designed for LLM-controlled shell execution
            capture_output=True,
            stdin=subprocess.DEVNULL,  # Prevent hanging on commands that read stdin
            # bytes mode: the reader thread does no decoding, so native
            # GBK/CP936 output on Chinese Windows can never crash it.
            env=self._env,
            cwd=str(self.cwd),
            timeout=effective_timeout,
        )

        stdout = _decode_stream(result.stdout)
        stderr = _decode_stream(result.stderr)

        # Combine stdout and stderr; prefix each stderr line for attribution.
        output_parts = []
        if stdout:
            output_parts.append(stdout)
        if stderr:
            stderr_lines = stderr.strip().split("\n")
            output_parts.extend(f"[stderr] {line}" for line in stderr_lines)

        output = "\n".join(output_parts) if output_parts else "<no output>"

        truncated = False
        if len(output) > self._max_output_bytes:
            output = output[: self._max_output_bytes]
            output += f"\n\n... Output truncated at {self._max_output_bytes} bytes."
            truncated = True

        if result.returncode != 0:
            output = f"{output.rstrip()}\n\nExit code: {result.returncode}"

        return ExecuteResponse(
            output=output,
            exit_code=result.returncode,
            truncated=truncated,
        )
    except subprocess.TimeoutExpired:
        if timeout is not None:
            msg = (
                f"Error: Command timed out after {effective_timeout} seconds "
                "(custom timeout). The command may be stuck or require more time."
            )
        else:
            msg = (
                f"Error: Command timed out after {effective_timeout} seconds. "
                "For long-running commands, re-run using the timeout parameter."
            )
        return ExecuteResponse(output=msg, exit_code=124, truncated=False)
    except Exception as e:  # noqa: BLE001
        # Broad exception catch is intentional: return a consistent
        # ExecuteResponse rather than propagating exceptions.
        return ExecuteResponse(
            output=f"Error executing command ({type(e).__name__}): {e}",
            exit_code=1,
            truncated=False,
        )


def _decode_stream(data: bytes) -> str:
    """Decode subprocess bytes, mirroring ``text=True`` universal-newlines.

    ``subprocess.run(..., text=True)`` (as the original deepagents
    implementation uses) reads through a ``TextIOWrapper`` with universal
    newlines, so CRLF output from Windows native tools arrives as ``\\n``.
    Decoding raw bytes preserves ``\\r\\n``; normalize to match, while
    ``errors="replace"`` keeps non-UTF-8 GBK/CP936 bytes from crashing the
    reader thread (they degrade to U+FFFD instead of dropping the stream).
    """
    if not data:
        return ""
    text = data.decode("utf-8", errors="replace")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _patch_drive_path_rewriting() -> bool:
    """Stop harness_agent from rewriting Windows drive paths in commands.

    Tightens the bare-token lookbehind in ``_ABS_TOKEN_RE`` so a ``/`` right
    after a drive letter (``C:/…``) or a backslash (``C:\\…``) is not treated
    as the start of a virtual absolute path. Genuine virtual paths still map.
    """
    from harness_agent.backends import bwrap_shell  # local import: lazy

    pattern = bwrap_shell._ABS_TOKEN_RE.pattern
    old = r"(?<![\w/.])"
    new = r"(?<![\w/:.\\])"
    if new in pattern:
        return True
    if old not in pattern:
        # Unexpected harness_agent version: leave the regex untouched rather
        # than risk a wrong rewrite.
        return False
    bwrap_shell._ABS_TOKEN_RE = re.compile(pattern.replace(old, new))
    return True


def apply() -> bool:
    """Apply Windows harness ``execute`` compatibility patches.

    Idempotent: returns True when a patch was applied and False when nothing
    changed (already applied, or non-Windows where native output is UTF-8 and
    the original readers are correct).
    """
    global _APPLIED
    if _APPLIED:
        return False
    if os.name != "nt":
        return False
    LocalShellBackend.execute = _patched_execute  # type: ignore[method-assign]
    _patch_drive_path_rewriting()
    _APPLIED = True
    return True


__all__ = ["apply"]
