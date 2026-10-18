"""Process-start patches for deepagents grep.

Two separate paths, installed together:

* Python fallback (issue #2101). ``_python_search`` walks ``root_dir`` (often
  ``/``) and reads files with unbounded ``readline()``. Pseudo-files such as
  ``/proc/<pid>/pagemap`` report ``st_size == 0`` but yield unlimited content
  with no newline, so one read can grow RSS until the host OOMs. The
  replacement skips POSIX virtual filesystems and caps reads. It already
  decodes file bytes as UTF-8. ``LocalShellBackend`` inherits the method, so a
  class-level patch covers agent tools and the workspace API.
* ripgrep (issue #1959). When ``rg`` is installed, ``grep`` uses it first and
  never reaches the Python fallback. ``_ripgrep_search`` runs ``rg --json``
  with ``text=True`` and no ``encoding``, so a Chinese Windows host decodes
  that UTF-8 stream as cp936 and the turn dies. A ``subprocess`` stand-in
  forces UTF-8 for ripgrep only.

deepagents itself is not modified.
"""

from __future__ import annotations

import logging
import os
import stat
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from deepagents.backends.protocol import DEFAULT_GREP_TIMEOUT
from deepagents.backends.utils import compile_grep_include_glob

logger = logging.getLogger(__name__)

# UI denylist also includes /etc and /root; those stay searchable. Only skip
# mounts whose regular files can emit unbounded content despite st_size == 0.
_VIRTUAL_FS_PREFIXES_POSIX = ("/proc", "/sys", "/dev")
_VIRTUAL_FS_NAMES = frozenset({"proc", "sys", "dev"})

_READ_CHUNK_BYTES = 64 * 1024
_MAX_LINE_BYTES = 1024 * 1024
_RIPGREP_NAMES = frozenset({"rg", "rg.exe"})

_PYTHON_SEARCH_INSTALLED = False
_RIPGREP_UTF8_INSTALLED = False


class _ReadStatus:
    __slots__ = ("decode_partial", "hit_deadline")

    def __init__(self) -> None:
        self.hit_deadline = False
        self.decode_partial = False


def _posix_logical_path(path: Path) -> str:
    """``as_posix()`` with macOS ``/private/{proc,sys,dev}`` stripped."""
    text = path.as_posix()
    if text == "/private" or text.startswith("/private/"):
        return text[len("/private") :] or "/"
    return text


def is_virtual_fs_path(path: Path) -> bool:
    """True for POSIX ``/proc``, ``/sys``, ``/dev`` (and macOS ``/private`` aliases)."""
    if os.name != "posix":
        return False
    text = _posix_logical_path(path)
    return any(
        text == prefix or text.startswith(f"{prefix}/") for prefix in _VIRTUAL_FS_PREFIXES_POSIX
    )


def _safe_detail(backend: Any, exc: Exception) -> str:
    if isinstance(exc, OSError):
        detail = exc.strerror
    else:
        detail = getattr(exc, "reason", None)
        if detail is None and not getattr(backend, "virtual_mode", False):
            detail = str(exc)
    return f"{type(exc).__name__}: {detail}" if detail else type(exc).__name__


def _display_or_name(backend: Any, path: Path) -> str:
    display = getattr(backend, "_display_path", None)
    if callable(display):
        try:
            return str(display(path))
        except (OSError, RuntimeError, ValueError):
            pass
    return path.name or "/"


def _resolved_is_virtual_fs(path: str) -> bool:
    try:
        return is_virtual_fs_path(Path(os.path.realpath(path)))
    except OSError:
        return False


def _iter_capped_lines(
    path: Path,
    *,
    max_file_bytes: int,
    deadline: float,
    status: _ReadStatus,
) -> Iterator[tuple[int, str]]:
    """Yield UTF-8 lines with byte caps. Oversized files/lines are skipped."""
    buf = bytearray()
    total = 0
    line_num = 0
    decoded_any = False
    try:
        with path.open("rb") as handle:
            while True:
                if time.monotonic() > deadline:
                    status.hit_deadline = True
                    return
                chunk = handle.read(_READ_CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_file_bytes:
                    return
                buf.extend(chunk)
                while True:
                    newline_at = buf.find(b"\n")
                    if newline_at < 0:
                        if len(buf) > _MAX_LINE_BYTES:
                            return
                        break
                    raw = buf[:newline_at]
                    del buf[: newline_at + 1]
                    if raw.endswith(b"\r"):
                        raw = raw[:-1]
                    line_num += 1
                    yield line_num, raw.decode("utf-8")
                    decoded_any = True
            if buf:
                if len(buf) > _MAX_LINE_BYTES:
                    return
                line_num += 1
                yield line_num, buf.decode("utf-8")
    except UnicodeDecodeError:
        if decoded_any:
            status.decode_partial = True


def _virtual_path_for(backend: Any, fp: Path) -> str | None:
    if getattr(backend, "virtual_mode", False):
        to_virtual = getattr(backend, "_to_virtual_path", None)
        if not callable(to_virtual):
            return None
        try:
            return str(to_virtual(fp))
        except ValueError:
            logger.debug("Skipping grep result outside root: %s", fp)
            return None
        except (OSError, RuntimeError):
            logger.warning("Could not resolve grep result path: %s", fp, exc_info=True)
            return None
    return str(fp)


def _keep_walk_dir(dirpath: str, name: str) -> bool:
    child = os.path.join(dirpath, name)
    try:
        mode = os.lstat(child).st_mode
    except OSError:
        return False
    if not stat.S_ISLNK(mode) and name not in _VIRTUAL_FS_NAMES:
        return True
    return not _resolved_is_virtual_fs(child)


def _regular_file_size(path: Path) -> int | None:
    """Size of a searchable regular file, or None to skip.

    ``realpath`` only for symlinks, so a host-root walk does not resolve every
    file. Symlinks that land in ``/proc`` / ``/sys`` / ``/dev`` are skipped.
    """
    try:
        info = os.lstat(path)
    except OSError:
        return None
    if stat.S_ISLNK(info.st_mode):
        if _resolved_is_virtual_fs(os.fspath(path)):
            return None
        try:
            info = os.stat(path)
        except OSError:
            return None
    if not stat.S_ISREG(info.st_mode):
        return None
    return int(info.st_size)


def _safe_python_search(
    self: Any,
    pattern: str,
    base_full: Path,
    include_glob: str | None,
    *,
    max_count: int | None = None,
    timeout: int = DEFAULT_GREP_TIMEOUT,
) -> tuple[dict[str, list[tuple[int, str]]], bool, str | None]:
    """Octop replacement for ``FilesystemBackend._python_search``."""
    deadline = time.monotonic() + timeout
    glob_matcher = compile_grep_include_glob(include_glob) if include_glob else None
    total = 0
    results: dict[str, list[tuple[int, str]]] = {}
    file_errors: list[str] = []
    try:
        root = base_full if base_full.is_dir() else base_full.parent
    except OSError:
        return {}, False, None
    if _resolved_is_virtual_fs(os.fspath(root)):
        return {}, False, None

    max_file_bytes = int(getattr(self, "max_file_size_bytes", 10 * 1024 * 1024))

    def _log_timeout() -> None:
        logger.warning(
            "Grep of '%s' timed out after %ss with %d matching file(s); returning partial results",
            _display_or_name(self, base_full),
            timeout,
            len(results),
        )

    def _file_errors_msg() -> str | None:
        if not file_errors:
            return None
        return "One or more files could not be fully searched:\n" + "\n".join(file_errors)

    try:
        for dirpath, dirnames, filenames in os.walk(os.fspath(root), followlinks=False):
            if time.monotonic() > deadline:
                _log_timeout()
                return results, True, None
            dirnames[:] = [name for name in dirnames if _keep_walk_dir(dirpath, name)]
            for name in filenames:
                if time.monotonic() > deadline:
                    _log_timeout()
                    return results, True, None
                fp = Path(dirpath) / name
                size = _regular_file_size(fp)
                if size is None or size > max_file_bytes:
                    continue
                if glob_matcher is not None:
                    try:
                        rel_path = fp.relative_to(root).as_posix()
                    except ValueError:
                        continue
                    if not glob_matcher(rel_path):
                        continue
                virt_path = _virtual_path_for(self, fp)
                if virt_path is None:
                    continue
                try:
                    status = _ReadStatus()
                    for line_num, line in _iter_capped_lines(
                        fp, max_file_bytes=max_file_bytes, deadline=deadline, status=status
                    ):
                        if pattern not in line:
                            continue
                        if max_count is not None and total >= max_count:
                            return results, True, _file_errors_msg()
                        results.setdefault(virt_path, []).append((line_num, line))
                        total += 1
                    if status.hit_deadline:
                        _log_timeout()
                        return results, True, None
                    if status.decode_partial:
                        file_errors.append(f"- {virt_path}: UnicodeDecodeError")
                except (OSError, RuntimeError) as exc:
                    file_errors.append(f"- {virt_path}: {_safe_detail(self, exc)}")
                    logger.debug("Could not fully read %s in grep fallback", fp, exc_info=True)
    except (OSError, RuntimeError) as exc:
        msg = (
            f"Grep of '{_display_or_name(self, base_full)}' aborted after "
            f"{len(results)} matching file(s): {_safe_detail(self, exc)}"
        )
        logger.warning("%s", msg, exc_info=True)
        return results, False, msg

    return results, False, _file_errors_msg()


_safe_python_search.__octop_safe_grep__ = True  # type: ignore[attr-defined]


def _executable_name(exe: str) -> str:
    """Final path segment, accepting both POSIX and Windows separators."""
    return exe.replace("\\", "/").rsplit("/", 1)[-1].lower()


def _command_is_ripgrep(command: object) -> bool:
    if isinstance(command, (str, bytes)) or not isinstance(command, (list, tuple)):
        return False
    if not command:
        return False
    exe = command[0]
    if isinstance(exe, bytes):
        text = os.fsdecode(exe)
    elif isinstance(exe, str):
        text = exe
    else:
        return False
    return _executable_name(text) in _RIPGREP_NAMES


class _RipgrepSubprocess:
    """``subprocess`` stand-in used only by ``deepagents.backends.filesystem``."""

    __slots__ = ("_real",)

    def __init__(self, real: Any) -> None:
        self._real = real

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)

    def Popen(self, *args: Any, **kwargs: Any) -> Any:
        command = args[0] if args else kwargs.get("args")
        text_mode = bool(kwargs.get("text") or kwargs.get("universal_newlines"))
        if text_mode and _command_is_ripgrep(command):
            kwargs.setdefault("encoding", "utf-8")
            kwargs.setdefault("errors", "replace")
        return self._real.Popen(*args, **kwargs)


def _install_python_search_fallback() -> None:
    global _PYTHON_SEARCH_INSTALLED
    if _PYTHON_SEARCH_INSTALLED:
        return
    from deepagents.backends.filesystem import FilesystemBackend

    current = FilesystemBackend._python_search
    if not getattr(current, "__octop_safe_grep__", False):
        FilesystemBackend._python_search = _safe_python_search  # type: ignore[method-assign]
        logger.info("installed safe python grep fallback (skip virtual fs, bound reads)")
    _PYTHON_SEARCH_INSTALLED = True


def _install_ripgrep_utf8_decoding() -> None:
    global _RIPGREP_UTF8_INSTALLED
    if _RIPGREP_UTF8_INSTALLED:
        return
    import deepagents.backends.filesystem as filesystem

    current = filesystem.subprocess  # type: ignore[attr-defined]
    if not isinstance(current, _RipgrepSubprocess):
        filesystem.subprocess = _RipgrepSubprocess(current)  # type: ignore[attr-defined, assignment]
        logger.info("installed ripgrep utf-8 decoding (ignore host locale)")
    _RIPGREP_UTF8_INSTALLED = True


def install_safe_grep_fallback() -> None:
    """Install the Python-search and ripgrep patches once per process."""
    _install_python_search_fallback()
    _install_ripgrep_utf8_decoding()
