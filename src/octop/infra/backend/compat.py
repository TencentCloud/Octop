"""Adapt deepagents_backends-style backends to the current harness protocol.

``deepagents_backends`` 0.2 still implements the older surface: ``read()``
returns a formatted ``str``, and listing lives on ``ls_info`` / ``als_info``.
Current ``octop-harness`` / ``BackendWorkspace`` expects ``ReadResult`` /
``LsResult`` and calls ``ls`` / ``als``. Without this wrap, expert start on
S3 raises ``'str' object has no attribute 'error'`` and Admin tree listing
raises ``NotImplementedError``.

Sync ``read`` / ``ls_info`` on those remotes call ``run_async_safely``, which
spawns a **new** event loop per call when the server loop is already running.
The postgres/S3 connection pool is then bound to a dead loop and the next
I/O hangs — ``octop run`` never finishes ``boot()`` and HTTP never comes up.
All inner async I/O therefore runs on one dedicated worker loop, with a
per-call timeout so one hung remote cannot block the process forever.

Wrap only backends that still use the Protocol default ``ls`` or whose
``read()`` is annotated to return ``str``. Having ``als_info`` alone is not
enough — a modern ``ls`` / ``ReadResult`` implementation must stay unwrapped.
"""

from __future__ import annotations

import asyncio
import inspect
import threading
from collections.abc import Coroutine
from concurrent.futures import Future
from typing import Any, cast

_REMOTE_SPEC_TYPES = frozenset({"s3", "postgres", "cos", "oss", "obs"})
# One hung List/Get must not pin the server loop (or ``boot()``) indefinitely.
_BACKEND_IO_TIMEOUT = 30.0


def is_adapted_backend(backend: Any) -> bool:
    """True when *backend* is the protocol wrap applied by :func:`adapt_backend_protocol`."""
    return isinstance(backend, _LegacyProtocolBackend)


def is_remote_backend_spec(spec: Any) -> bool:
    """True when *spec* is a remote object-store / postgres harness dict."""
    return isinstance(spec, dict) and str(spec.get("type") or "").lower() in _REMOTE_SPEC_TYPES


def adapt_backend_protocol(backend: Any) -> Any:
    """Return *backend*, wrapped when it only implements the older protocol."""
    if isinstance(backend, _LegacyProtocolBackend):
        return backend
    if not _needs_adapt(backend):
        return backend
    wrapped = _LegacyProtocolBackend(backend)
    _patch_s3_list_v1(backend)
    return wrapped


async def _s3_als_info_v1(backend: Any, path: str) -> list[Any]:
    prefix = path.lstrip("/")
    if prefix and not prefix.endswith("/"):
        prefix += "/"
    full_prefix = backend._s3_key(prefix)
    results: list[Any] = []
    async with backend._client() as client:
        paginator = client.get_paginator("list_objects")
        async for page in paginator.paginate(
            Bucket=backend._bucket,
            Prefix=full_prefix,
            Delimiter="/",
        ):
            for obj in page.get("Contents", []):
                results.append(
                    {
                        "path": backend._virtual_path(obj["Key"]),
                        "is_dir": False,
                        "size": obj.get("Size", 0),
                        "modified_at": (
                            obj["LastModified"].isoformat() if "LastModified" in obj else None
                        ),
                    }
                )
            for common in page.get("CommonPrefixes", []):
                results.append(
                    {
                        "path": backend._virtual_path(common["Prefix"]),
                        "is_dir": True,
                    }
                )
    results.sort(key=lambda item: str(item.get("path") or ""))
    return results


def _patch_s3_list_v1(backend: Any) -> None:
    """Some MinIO/Ceph gates implement ListObjects but not ListObjectsV2."""
    if not callable(getattr(backend, "_s3_key", None)):
        return
    original = backend.als_info

    async def als_info(path: str) -> Any:
        if getattr(backend, "_octop_s3_list_v1", False):
            return await _s3_als_info_v1(backend, path)
        try:
            return await original(path)
        except Exception as exc:
            error = getattr(exc, "response", None)
            code = ""
            if isinstance(error, dict):
                code = str((error.get("Error") or {}).get("Code") or "")
            if code != "NotImplemented":
                raise
            backend._octop_s3_list_v1 = True
            return await _s3_als_info_v1(backend, path)

    backend.als_info = als_info


def _read_returns_str(backend: Any) -> bool:
    read = getattr(type(backend), "read", None)
    if not callable(read):
        return False
    ret = getattr(read, "__annotations__", {}).get("return")
    return ret is str or ret == "str"


def _needs_adapt(backend: Any) -> bool:
    try:
        from deepagents.backends.protocol import BackendProtocol
    except ImportError:
        return _read_returns_str(backend)
    ls = getattr(type(backend), "ls", None)
    if ls is getattr(BackendProtocol, "ls", None):
        return True
    return _read_returns_str(backend)


class _LegacyProtocolBackend:
    """Delegate to an older backend while exposing ``ls`` / ``ReadResult``."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()

    def _worker_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is not None:
            return self._loop

        def _runner() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop
            self._ready.set()
            loop.run_forever()

        self._thread = threading.Thread(
            target=_runner,
            name="octop-backend-loop",
            daemon=True,
        )
        self._thread.start()
        if not self._ready.wait(timeout=5):
            raise RuntimeError("backend worker loop failed to start")
        if self._loop is None:
            raise RuntimeError("backend worker loop failed to start")
        return self._loop

    def _run(self, value: Any) -> Any:
        if not inspect.isawaitable(value):
            return value
        fut: Future[Any] = asyncio.run_coroutine_threadsafe(
            cast(Coroutine[Any, Any, Any], value),
            self._worker_loop(),
        )
        try:
            return fut.result(timeout=_BACKEND_IO_TIMEOUT)
        except TimeoutError:
            fut.cancel()
            raise TimeoutError(f"backend I/O timed out after {_BACKEND_IO_TIMEOUT:.0f}s") from None

    def _call_via_worker(self, sync_name: str, async_name: str, *args: Any, **kwargs: Any) -> Any:
        async_fn = getattr(self._inner, async_name, None)
        if callable(async_fn):
            return self._run(async_fn(*args, **kwargs))
        sync_fn = getattr(self._inner, sync_name, None)
        if not callable(sync_fn):
            raise AttributeError(sync_name)
        return self._run(sync_fn(*args, **kwargs))

    def ls_info(self, path: str) -> Any:
        als_info = getattr(self._inner, "als_info", None)
        if callable(als_info):
            return self._run(als_info(path))
        ls_info = getattr(self._inner, "ls_info", None)
        if callable(ls_info):
            return self._run(ls_info(path))
        raise NotImplementedError

    async def als_info(self, path: str) -> Any:
        inner = getattr(self._inner, "als_info", None)
        if callable(inner):
            return await asyncio.to_thread(self._run, inner(path))
        return await asyncio.to_thread(self.ls_info, path)

    def ls(self, path: str) -> Any:
        from deepagents.backends.protocol import LsResult

        return LsResult(entries=list(self.ls_info(path) or []))

    async def als(self, path: str) -> Any:
        from deepagents.backends.protocol import LsResult

        entries = await self.als_info(path)
        return LsResult(entries=list(entries or []))

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> Any:
        from deepagents.backends.protocol import ReadResult

        # Prefer raw stored lines. ``aread`` returns cat-style numbered text,
        # which ``backend_write_force`` then feeds back into ``edit`` and fails.
        get_data = getattr(self._inner, "_get_file_data", None)
        if callable(get_data):
            data = self._run(get_data(file_path))
            if data is None:
                return ReadResult(error=f"Error: File '{file_path}' not found")
            lines = data.get("content", [])
            if not isinstance(lines, list):
                lines = str(lines).splitlines()
            selected = lines[offset : offset + limit]
            return ReadResult(file_data={"content": "\n".join(selected), "encoding": "utf-8"})

        aread = getattr(self._inner, "aread", None)
        if callable(aread):
            result = self._run(aread(file_path, offset, limit))
        else:
            result = self._inner.read(file_path, offset, limit)
        if isinstance(result, str):
            if result.startswith("Error"):
                return ReadResult(error=result)
            return ReadResult(file_data={"content": result, "encoding": "utf-8"})
        return result

    def write(self, file_path: str, content: str) -> Any:
        from datetime import UTC, datetime

        from deepagents.backends.protocol import WriteResult

        exists = getattr(self._inner, "_exists", None)
        put_data = getattr(self._inner, "_put_file_data", None)
        if callable(exists) and callable(put_data):
            if self._run(exists(file_path)):
                return WriteResult(
                    error=(
                        f"Cannot write to {file_path} because it already exists. "
                        "Read and then make an edit, or write to a new path."
                    )
                )
            now = datetime.now(UTC).isoformat()
            data = {
                "content": content.splitlines(),
                "created_at": now,
                "modified_at": now,
            }
            try:
                self._run(put_data(file_path, data, update_modified=False))
            except TypeError:
                self._run(put_data(file_path, data))
            return WriteResult(path=file_path)
        awrite = getattr(self._inner, "awrite", None)
        if callable(awrite):
            return self._run(awrite(file_path, content))
        return self._inner.write(file_path, content)

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> Any:
        from deepagents.backends.protocol import EditResult
        from deepagents.backends.utils import perform_string_replacement

        get_data = getattr(self._inner, "_get_file_data", None)
        put_data = getattr(self._inner, "_put_file_data", None)
        if callable(get_data) and callable(put_data):
            data = self._run(get_data(file_path))
            if data is None:
                return EditResult(error=f"Error: File '{file_path}' not found")
            content = "\n".join(data.get("content", []))
            result = perform_string_replacement(content, old_string, new_string, replace_all)
            if isinstance(result, str):
                return EditResult(error=result)
            new_content, occurrences = result
            data["content"] = new_content.splitlines()
            try:
                self._run(put_data(file_path, data, update_modified=True))
            except TypeError:
                self._run(put_data(file_path, data))
            return EditResult(path=file_path, occurrences=int(occurrences))
        aedit = getattr(self._inner, "aedit", None)
        if callable(aedit):
            return self._run(aedit(file_path, old_string, new_string, replace_all))
        return self._inner.edit(file_path, old_string, new_string, replace_all)

    def mkdir_path(self, path: str) -> None:
        """Object-store / postgres prefixes have no real directories."""
        inner = getattr(self._inner, "mkdir_path", None)
        if callable(inner):
            inner(path)

    def grep(self, *args: Any, **kwargs: Any) -> Any:
        return self._call_via_worker("grep", "agrep", *args, **kwargs)

    def glob(self, *args: Any, **kwargs: Any) -> Any:
        return self._call_via_worker("glob", "aglob", *args, **kwargs)

    def upload_files(self, *args: Any, **kwargs: Any) -> Any:
        return self._call_via_worker("upload_files", "aupload_files", *args, **kwargs)

    def download_files(self, *args: Any, **kwargs: Any) -> Any:
        return self._call_via_worker("download_files", "adownload_files", *args, **kwargs)

    async def adownload_files(self, *args: Any, **kwargs: Any) -> Any:
        inner = getattr(self._inner, "adownload_files", None)
        if callable(inner):
            return await asyncio.to_thread(self._run, inner(*args, **kwargs))
        download = getattr(self._inner, "download_files", None)
        if not callable(download):
            raise AttributeError("adownload_files")
        return await asyncio.to_thread(self._run, download(*args, **kwargs))

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)
