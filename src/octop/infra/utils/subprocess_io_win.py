"""Windows-only non-blocking pipe reads (typed separately for mypy)."""

from __future__ import annotations

import ctypes
import msvcrt
from ctypes import wintypes
from typing import IO

_kernel32 = ctypes.windll.kernel32


def read_available_windows(stream: IO[bytes]) -> bytes:
    handle = msvcrt.get_osfhandle(stream.fileno())
    avail = wintypes.DWORD()
    ok = _kernel32.PeekNamedPipe(
        handle,
        None,
        0,
        None,
        ctypes.byref(avail),
        None,
    )
    if not ok or avail.value == 0:
        return b""
    return stream.read(avail.value)
