"""Install the external Office engine after HTTP startup, outside the server process."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from contextlib import suppress

from octop.infra.office_preview.runtime import install_runtime, probe_runtime, runtime_dir
from octop.infra.utils.paths import PathLayout

logger = logging.getLogger(__name__)


async def ensure_office_preview_runtime(paths: PathLayout) -> None:
    """Best-effort bootstrap; never block HTTP startup or a preview request."""
    try:
        probe = await asyncio.get_running_loop().run_in_executor(None, probe_runtime, paths)
        if probe.available:
            return
        if probe.reason not in {"helper_missing", "kit_missing"}:
            logger.warning("Office preview auto-install skipped: %s", probe.reason)
            return
        logger.info("Installing Office preview runtime in the background")
        env = dict(os.environ, OCTOP_HOME=str(paths.root))
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "octop.infra.office_preview.bootstrap",
            env=env,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            start_new_session=os.name == "posix",
        )
        try:
            async with asyncio.timeout(630):
                returncode = await proc.wait()
        finally:
            if proc.returncode is None:
                if sys.platform != "win32" and os.name == "posix":
                    with suppress(ProcessLookupError):
                        os.killpg(proc.pid, signal.SIGKILL)
                else:
                    # npm can spawn native installers; stop the entire child tree.
                    with suppress(OSError):
                        killer = await asyncio.create_subprocess_exec(
                            "taskkill",
                            "/PID",
                            str(proc.pid),
                            "/T",
                            "/F",
                            stdout=asyncio.subprocess.DEVNULL,
                            stderr=asyncio.subprocess.DEVNULL,
                        )
                        await killer.wait()
                    with suppress(ProcessLookupError):
                        proc.kill()
                await proc.wait()
        if returncode != 0:
            logger.warning(
                "Office preview auto-install failed; retry with octop office-preview install"
            )
            return
        logger.info("Office preview runtime is ready")
    except (OSError, RuntimeError, TimeoutError):
        logger.warning(
            "Office preview auto-install failed; retry with octop office-preview install"
        )


def _install_if_missing(paths: PathLayout) -> None:
    """Serialize workers with an OS lock that is released even if a process exits."""
    dest = runtime_dir(paths)
    dest.mkdir(parents=True, exist_ok=True)
    with (dest / ".install.lock").open("a+b") as lock:
        if sys.platform == "win32":
            import msvcrt

            lock.write(b"\0")
            lock.flush()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        if not probe_runtime(paths).available:
            install_runtime(paths=paths)


if __name__ == "__main__":
    _install_if_missing(PathLayout.from_env())
