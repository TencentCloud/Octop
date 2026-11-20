"""Git execution targets: host subprocess or docker-sandbox container."""

from __future__ import annotations

import asyncio
import os
import shlex
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from octop.infra.git.binary import GitBinary


@runtime_checkable
class GitTarget(Protocol):
    """Runs git and reads workspace files for one agent workspace."""

    available: bool

    async def probe(self) -> bool: ...

    async def run(
        self, args: list[str], *, timeout: float, max_bytes: int
    ) -> tuple[int, bytes, bytes]: ...

    def exists(self, rel: str) -> bool: ...

    def read_text(self, rel: str) -> str | None: ...

    def delete(self, rel: str) -> None: ...


class HostGitTarget:
    """Local workspace: git runs as a subprocess with the workspace as cwd."""

    def __init__(self, ws_dir: Path, binary: GitBinary | None) -> None:
        self._ws_dir = ws_dir
        self._binary = binary
        self.available = binary is not None

    async def probe(self) -> bool:
        return self.available

    async def run(
        self, args: list[str], *, timeout: float, max_bytes: int
    ) -> tuple[int, bytes, bytes]:
        if self._binary is None:
            raise FileNotFoundError("git is not installed")
        env = dict(os.environ)
        env["GIT_TERMINAL_PROMPT"] = "0"
        proc = await asyncio.create_subprocess_exec(
            self._binary.path,
            *args,
            cwd=str(self._ws_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            raise
        return proc.returncode or 0, stdout[:max_bytes], stderr[:max_bytes]

    def exists(self, rel: str) -> bool:
        return (self._ws_dir / rel).exists()

    def read_text(self, rel: str) -> str | None:
        try:
            return (self._ws_dir / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

    def delete(self, rel: str) -> None:
        target = self._ws_dir / rel
        if target.is_dir():
            import shutil

            shutil.rmtree(target)
        elif target.exists() or target.is_symlink():
            target.unlink()


class SandboxGitTarget:
    """Docker sandbox: git runs inside the container via the harness backend."""

    def __init__(self, workspace: Any) -> None:
        self._ws = workspace
        self._backend = workspace.backend
        self.available = callable(getattr(self._backend, "execute", None))
        self._probed: bool | None = None

    async def probe(self) -> bool:
        """Check that git exists inside the sandbox image (default images may
        not ship it); the result is cached for the target's lifetime."""
        if self._probed is not None:
            return self._probed
        if not self.available:
            self._probed = False
            return False
        try:
            code, out, _ = await self.run(["--version"], timeout=10.0, max_bytes=4096)
            self._probed = code == 0 and b"git version" in out
        except Exception:  # noqa: BLE001 - probe failure means unavailable
            self._probed = False
        self.available = bool(self._probed)
        return self.available

    async def run(
        self, args: list[str], *, timeout: float, max_bytes: int
    ) -> tuple[int, bytes, bytes]:
        command = "GIT_TERMINAL_PROMPT=0 git " + shlex.join(args)
        response = await asyncio.to_thread(self._backend.execute, command, timeout=int(timeout))
        output = str(getattr(response, "output", "") or "")
        encoded = output.encode("utf-8", "replace")
        stderr = b"" if getattr(response, "exit_code", 0) == 0 else encoded
        return int(getattr(response, "exit_code", 1) or 0), encoded[:max_bytes], stderr[:max_bytes]

    def exists(self, rel: str) -> bool:
        return bool(self._ws.exists(rel))

    def read_text(self, rel: str) -> str | None:
        try:
            value = self._ws.read_text(rel)
        except Exception:  # noqa: BLE001 - unreadable is reported as missing
            return None
        return value if isinstance(value, str) else None

    def delete(self, rel: str) -> None:
        self._ws.delete(rel)


def spec_uses_docker(spec: Any) -> bool:
    """True when the harness backend spec routes to a docker sandbox."""
    if not isinstance(spec, dict):
        return False
    kind = str(spec.get("type") or "").strip().lower()
    if kind in ("docker", "docker_sandbox"):
        return True
    if kind == "composite":
        children = [spec.get("default"), *(spec.get("routes") or {}).values()]
        return any(spec_uses_docker(child) for child in children if child)
    return False


__all__ = [
    "GitTarget",
    "HostGitTarget",
    "SandboxGitTarget",
    "spec_uses_docker",
]
