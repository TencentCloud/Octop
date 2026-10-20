"""Host ``LocalShellBackend`` with conservative virtual-path translation.

Used when a bubblewrap jail is unavailable (macOS, missing ``bwrap``, or a
host-rooted backend). Agent tool entry paths stay rootfs-shaped; this backend
maps credible virtual command and environment paths onto ``root_dir`` and
runs from the host workspace.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from deepagents.backends import LocalShellBackend
from deepagents.backends.protocol import ExecuteResponse

from octop_harness.runtime_env import resolve_local_execute_env

# Quoted absolute path, or bare absolute token (heuristic; not a full shell parser).
# Bare tokens stop at ``:`` so path-list values are considered segment-wise.
_ABS_TOKEN_RE = re.compile(r"""(?P<q>['"])(?P<quoted>/[^'"]*)(?P=q)|(?<![\w/.])(?P<bare>/(?:[^\s"';&|<>():]+))""")


def _expand_local_path(path: Path | str) -> Path:
    return Path(os.path.expandvars(str(path))).expanduser().resolve()


def is_host_root(root: Path | str) -> bool:
    """Return True when *root* resolves to the host filesystem root."""
    try:
        return _expand_local_path(root) == Path("/").resolve()
    except OSError:
        return str(root) in {"/", ""}


def _path_already_under_root(path: str, root: Path) -> bool:
    root_text = str(root)
    if path == root_text or path.startswith(root_text + os.sep):
        return True
    try:
        Path(path).expanduser().resolve().relative_to(root)
        return True
    except (OSError, ValueError):
        return False


def _path_exists(path: Path) -> bool:
    """Like ``Path.exists()``, but treat permission errors as missing."""
    try:
        return path.exists()
    except OSError:
        return False


def _is_under(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def map_virtual_abs_path(
    path: str,
    root_dir: Path | str,
    *,
    workspace_dir: Path | str | None = None,
) -> str:
    """Map one credible virtual absolute path onto ``root_dir``.

    Existing host paths (toolchains, ``/tmp``, user-supplied host paths) win.
    Otherwise mapping is allowed when the target is inside the configured
    workspace or an existing ancestor proves that the virtual tree exists.
    """
    if not path.startswith("/") or path.startswith("//"):
        return path

    root = _expand_local_path(root_dir)
    host_path = Path(path)
    if is_host_root(root) or _path_already_under_root(path, root) or _path_exists(host_path):
        return path

    mapped = (root / path.lstrip("/")).resolve()
    workspace = _expand_local_path(workspace_dir) if workspace_dir is not None else None
    if workspace is not None and _is_under(mapped, workspace):
        return str(mapped)

    # Preserve host-owned top-level trees such as /usr and /tmp even when the
    # final entry does not exist. A configured workspace remains stronger proof.
    host_parts = host_path.parts
    if len(host_parts) > 1 and _path_exists(Path(host_parts[0], host_parts[1])):
        return path

    probe = mapped
    has_mapped_ancestor = False
    while probe != root and _is_under(probe, root):
        if _path_exists(probe):
            has_mapped_ancestor = True
            break
        probe = probe.parent
    return str(mapped) if has_mapped_ancestor else path


def _map_path_list(
    value: str,
    root_dir: Path | str,
    *,
    workspace_dir: Path | str | None,
) -> str:
    separator = os.pathsep
    if separator not in value:
        return map_virtual_abs_path(value, root_dir, workspace_dir=workspace_dir)
    return separator.join(
        map_virtual_abs_path(part, root_dir, workspace_dir=workspace_dir) if part.startswith("/") else part
        for part in value.split(separator)
    )


def _quote_mapped_bare_path(mapped: str, root_dir: Path | str) -> str:
    """Quote only the root prefix so shell globs in the virtual suffix still expand."""
    root = str(_expand_local_path(root_dir))
    if os.name == "nt":
        return subprocess.list2cmdline([mapped])
    if mapped.startswith(root):
        return shlex.quote(root) + mapped[len(root) :]
    return shlex.quote(mapped)


def rewrite_virtual_paths_in_command(
    command: str,
    root_dir: Path | str,
    *,
    workspace_dir: Path | str | None = None,
) -> str:
    """Conservatively translate virtual absolute command paths for host execute."""

    def replace(match: re.Match[str]) -> str:
        raw = match.group("quoted")
        if raw is not None:
            mapped = _map_path_list(raw, root_dir, workspace_dir=workspace_dir)
            if mapped == raw:
                return match.group(0)
            quote = match.group("q")
            if quote in mapped:
                return match.group(0)
            return f"{quote}{mapped}{quote}"

        raw = match.group("bare")
        assert raw is not None
        mapped = map_virtual_abs_path(raw, root_dir, workspace_dir=workspace_dir)
        if mapped == raw:
            return raw
        return _quote_mapped_bare_path(mapped, root_dir)

    return _ABS_TOKEN_RE.sub(replace, command)


def map_virtual_paths_in_env(
    env: dict[str, str],
    root_dir: Path | str,
    *,
    workspace_dir: Path | str | None = None,
) -> dict[str, str]:
    """Return an env copy with credible virtual absolute path values translated."""
    return {
        key: _map_path_list(value, root_dir, workspace_dir=workspace_dir) if value.startswith("/") else value
        for key, value in env.items()
    }


def present_host_paths_in_output(text: str, root_dir: Path | str) -> str:
    """Present paths under the host mount as agent-facing virtual paths."""
    if not text:
        return text
    root = str(_expand_local_path(root_dir))
    if is_host_root(root):
        return text
    replaced = text.replace(root + os.sep, "/")
    return re.sub(rf"{re.escape(root)}(?=$|[\s'\"),:;])", "/", replaced)


def format_execute_result(
    result: subprocess.CompletedProcess[str],
    *,
    max_output_bytes: int,
) -> ExecuteResponse:
    """Match deepagents ``LocalShellBackend.execute`` stdout/stderr formatting."""
    output_parts: list[str] = []
    if result.stdout:
        output_parts.append(result.stdout)
    if result.stderr:
        stderr_lines = result.stderr.strip().split("\n")
        output_parts.extend(f"[stderr] {line}" for line in stderr_lines)

    output = "\n".join(output_parts) if output_parts else "<no output>"

    truncated = False
    if len(output) > max_output_bytes:
        output = output[:max_output_bytes]
        output += f"\n\n... Output truncated at {max_output_bytes} bytes."
        truncated = True

    if result.returncode != 0:
        output = f"{output.rstrip()}\n\nExit code: {result.returncode}"

    return ExecuteResponse(
        output=output,
        exit_code=result.returncode,
        truncated=truncated,
    )


class HarnessLocalShellBackend(LocalShellBackend):
    """Host shell with workspace cwd and conservative virtual-path translation."""

    def __init__(
        self,
        root_dir: str | Path | None = None,
        *,
        workspace_dir: str | Path | None = None,
        virtual_mode: bool | None = None,
        env: dict[str, str] | None = None,
        inherit_env: bool = True,
        explicit_virtual_paths: bool = False,
        **kwargs: Any,
    ) -> None:
        self._explicit_virtual_paths = explicit_virtual_paths
        self._extra_env = {str(k): str(v) for k, v in dict(env or {}).items()}
        self._inherit_live = inherit_env
        expanded_root = _expand_local_path(root_dir) if root_dir is not None else None
        super().__init__(
            root_dir=expanded_root,
            virtual_mode=True if virtual_mode is None else virtual_mode,
            env=env,
            inherit_env=inherit_env,
            **kwargs,
        )
        self._workspace_dir = _expand_local_path(workspace_dir) if workspace_dir is not None else None
        self._workspace_dotenv_reader: Callable[[], dict[str, str]] | None = None

    def set_workspace_dotenv_reader(
        self,
        reader: Callable[[], dict[str, str]] | None,
    ) -> None:
        """Optional BackendWorkspace-backed reader for workspace ``.env``."""
        self._workspace_dotenv_reader = reader

    def _refresh_execute_env(self) -> None:
        self._env = resolve_local_execute_env(
            inherit=self._inherit_live,
            extra=self._extra_env,
            workspace_dir=self._workspace_dir,
            workspace_reader=self._workspace_dotenv_reader,
        )

    def _host_execute_cwd(self) -> Path:
        if self._workspace_dir is not None and self._workspace_dir.is_dir():
            return self._workspace_dir
        return Path(self.cwd)

    def _present_execute_response(self, response: ExecuteResponse) -> ExecuteResponse:
        if not self.virtual_mode or is_host_root(self.cwd):
            return response
        output = present_host_paths_in_output(str(response.output or ""), self.cwd)
        if output == response.output:
            return response
        return ExecuteResponse(
            output=output,
            exit_code=response.exit_code,
            truncated=response.truncated,
        )

    def _execute_on_host(
        self,
        command: str,
        *,
        timeout: int | None,
    ) -> ExecuteResponse:
        effective_timeout = timeout if timeout is not None else self._default_timeout
        if effective_timeout <= 0:
            return ExecuteResponse(
                output=f"Error: timeout must be positive, got {effective_timeout}",
                exit_code=1,
                truncated=False,
            )
        try:
            result = subprocess.run(
                command,
                check=False,
                shell=True,
                capture_output=True,
                stdin=subprocess.DEVNULL,
                text=True,
                timeout=effective_timeout,
                env=self._env,
                cwd=str(self._host_execute_cwd()),
            )
            return format_execute_result(result, max_output_bytes=self._max_output_bytes)
        except subprocess.TimeoutExpired:
            if timeout is not None:
                detail = f"{effective_timeout} seconds (custom timeout)"
            else:
                detail = f"{effective_timeout} seconds"
            return ExecuteResponse(
                output=(f"Error: Command timed out after {detail}. The command may be stuck or require more time."),
                exit_code=124,
                truncated=False,
            )
        except Exception as exc:  # shell boundary: any failure becomes a tool error; pylint: disable=broad-except
            return ExecuteResponse(
                output=f"Error executing command ({type(exc).__name__}): {exc}",
                exit_code=1,
                truncated=False,
            )

    def execute(
        self,
        command: str,
        *,
        timeout: int | None = None,
    ) -> ExecuteResponse:
        if not command or not isinstance(command, str):
            return super().execute(command, timeout=timeout)
        self._refresh_execute_env()
        if self._explicit_virtual_paths:
            return self._execute_on_host(command, timeout=timeout)
        if self.virtual_mode and not is_host_root(self.cwd):
            command = rewrite_virtual_paths_in_command(
                command,
                self.cwd,
                workspace_dir=self._workspace_dir,
            )
            self._env = map_virtual_paths_in_env(
                self._env,
                self.cwd,
                workspace_dir=self._workspace_dir,
            )
        return self._present_execute_response(self._execute_on_host(command, timeout=timeout))


__all__ = [
    "HarnessLocalShellBackend",
    "is_host_root",
    "map_virtual_abs_path",
    "map_virtual_paths_in_env",
    "present_host_paths_in_output",
    "rewrite_virtual_paths_in_command",
]
