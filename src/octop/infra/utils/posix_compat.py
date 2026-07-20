"""POSIX-only stdlib helpers for cross-platform mypy (CI runs on Windows).

Runtime callers must still guard with ``os.name == "posix"`` (or
:func:`octop.api.routers.terminal.terminal_supported`) before invoking
PTY/fcntl paths.  This module exists so Windows mypy does not require
``fcntl``, ``pty``, ``pwd``, or ``os.geteuid`` stubs on every call site.
"""

from __future__ import annotations

import errno
import os
import signal
import struct
from typing import IO, Any


def geteuid() -> int:
    fn = getattr(os, "geteuid", None)
    if fn is None:
        return -1
    return int(fn())


def getuid() -> int:
    fn = getattr(os, "getuid", None)
    if fn is None:
        return -1
    return int(fn())


def is_root() -> bool:
    return geteuid() == 0


def chown(path: str | os.PathLike[str], uid: int, gid: int = -1) -> None:
    fn = getattr(os, "chown", None)
    if fn is None:
        raise OSError("chown is not available on this platform")
    fn(path, uid, gid)


def getpwnam(name: str) -> Any:
    import pwd

    return pwd.getpwnam(name)


def getpwuid(uid: int) -> Any:
    import pwd

    return pwd.getpwuid(uid)


def killpg(pgid: int, sig: int) -> None:
    fn = getattr(os, "killpg", None)
    if fn is None:
        raise OSError("killpg is not available on this platform")
    fn(pgid, sig)


def getpgid(pid: int) -> int:
    fn = getattr(os, "getpgid", None)
    if fn is None:
        raise OSError("getpgid is not available on this platform")
    return int(fn(pid))


def setsid() -> int:
    fn = getattr(os, "setsid", None)
    if fn is None:
        raise OSError("setsid is not available on this platform")
    # macOS returns None from os.setsid(); Linux returns the new session id.
    # preexec_fn must not raise — wrapping None in int() aborts the child spawn.
    result = fn()
    return int(result) if result is not None else 0


def sigkill() -> int:
    return int(getattr(signal, "SIGKILL", signal.SIGTERM))


def read_available_posix(stream: IO[bytes]) -> bytes:
    import fcntl

    fd = stream.fileno()
    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
    try:
        return os.read(fd, 65536)
    except OSError as exc:
        if exc.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
            return b""
        raise
    finally:
        fcntl.fcntl(fd, fcntl.F_SETFL, flags)


def set_winsize(fd: int, cols: int, rows: int) -> None:
    import fcntl
    import termios

    winsize = struct.pack("HHHH", rows, cols, 0, 0)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)


def openpty() -> tuple[int, int]:
    import pty

    master_fd, slave_fd = pty.openpty()
    return int(master_fd), int(slave_fd)


def set_nonblock(fd: int) -> None:
    import fcntl

    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
