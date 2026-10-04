"""Adapt deepagents_backends-style backends to the current harness protocol.

``deepagents_backends`` 0.2 still implements the older surface: ``read()``
returns a formatted ``str``, and listing lives on ``ls_info`` / ``als_info``.
Current ``octop-harness`` / ``BackendWorkspace`` expects ``ReadResult`` /
``LsResult`` and calls ``ls`` / ``als``. Without this wrap, expert start on
S3 raises ``'str' object has no attribute 'error'`` and Admin tree listing
raises ``NotImplementedError``.
"""

from __future__ import annotations

import asyncio
from typing import Any


def is_adapted_backend(backend: Any) -> bool:
    """True when *backend* is the protocol wrap applied by :func:`adapt_backend_protocol`."""
    return isinstance(backend, _LegacyProtocolBackend)


def adapt_backend_protocol(backend: Any) -> Any:
    """Return *backend*, wrapped when it only implements the older protocol."""
    if isinstance(backend, _LegacyProtocolBackend):
        return backend
    if not _needs_adapt(backend):
        return backend
    return _LegacyProtocolBackend(backend)


def _needs_adapt(backend: Any) -> bool:
    try:
        from deepagents.backends.protocol import BackendProtocol
    except ImportError:
        return False
    ls = getattr(type(backend), "ls", None)
    return ls is getattr(BackendProtocol, "ls", None)


class _LegacyProtocolBackend:
    """Delegate to an older backend while exposing ``ls`` / ``ReadResult``."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def ls(self, path: str) -> Any:
        from deepagents.backends.protocol import LsResult

        ls_info = getattr(self._inner, "ls_info", None)
        if callable(ls_info):
            return LsResult(entries=list(ls_info(path) or []))
        raise NotImplementedError

    async def als(self, path: str) -> Any:
        from deepagents.backends.protocol import LsResult

        als_info = getattr(self._inner, "als_info", None)
        if callable(als_info):
            entries = await als_info(path)
            return LsResult(entries=list(entries or []))
        return await asyncio.to_thread(self.ls, path)

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> Any:
        from deepagents.backends.protocol import ReadResult

        result = self._inner.read(file_path, offset, limit)
        if isinstance(result, str):
            if result.startswith("Error"):
                return ReadResult(error=result)
            return ReadResult(file_data={"content": result, "encoding": "utf-8"})
        return result

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)
