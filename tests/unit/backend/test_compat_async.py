"""Legacy async operations must reuse protocol adaptation and the worker loop."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from deepagents.backends.protocol import BackendProtocol, EditResult, ReadResult, WriteResult

from octop.infra.backend import compat


class _LoopBoundLegacy:
    ls = BackendProtocol.ls

    def __init__(self) -> None:
        self.loop: asyncio.AbstractEventLoop | None = None
        self.files: dict[str, list[str]] = {}
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self.updates: list[bool] = []

    def _check_loop(self) -> None:
        assert asyncio.get_running_loop() is self.loop, "legacy I/O ran on the wrong loop"

    async def als_info(self, path: str) -> list[dict[str, object]]:
        if self.loop is None:
            self.loop = asyncio.get_running_loop()
        self._check_loop()
        return [{"path": path, "is_dir": True}]

    async def _get_file_data(self, path: str) -> dict[str, object] | None:
        self._check_loop()
        return {"content": list(self.files[path])} if path in self.files else None

    async def _exists(self, path: str) -> bool:
        self._check_loop()
        return path in self.files

    async def _put_file_data(
        self, path: str, data: dict[str, Any], *, update_modified: bool
    ) -> None:
        self._check_loop()
        self.files[path] = list(data["content"])
        self.updates.append(update_modified)

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        raise AssertionError("legacy sync read must not run")

    async def aread(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        self._check_loop()
        if file_path == "/missing.md":
            return f"Error: File '{file_path}' not found"
        return f"legacy formatted text: {offset}:{limit}"

    async def awrite(self, file_path: str, content: str) -> Any:
        self._check_loop()
        raise AssertionError("write must use the raw-data adapter")

    async def aedit(
        self, file_path: str, old_string: str, new_string: str, replace_all: bool = False
    ) -> Any:
        self._check_loop()
        raise AssertionError("edit must use the raw-data adapter")

    async def agrep(self, *args: Any, **kwargs: Any) -> list[dict[str, object]]:
        self._check_loop()
        self.calls.append(("grep", args, kwargs))
        return [{"path": "/notes.md", "line": "matched"}]

    async def aglob(self, *args: Any, **kwargs: Any) -> list[dict[str, object]]:
        self._check_loop()
        self.calls.append(("glob", args, kwargs))
        return [{"path": "/notes.md", "is_dir": False}]

    async def aupload_files(self, *args: Any, **kwargs: Any) -> list[dict[str, object]]:
        self._check_loop()
        self.calls.append(("upload_files", args, kwargs))
        return [{"path": "/notes.md", "error": None}]


@pytest.fixture
def backend() -> Iterator[tuple[_LoopBoundLegacy, Any]]:
    inner = _LoopBoundLegacy()
    wrapped = compat.adapt_backend_protocol(inner)
    # Bind the backend first; concurrent worker initialization is a separate issue.
    wrapped.ls("/")
    try:
        yield inner, wrapped
    finally:
        loop = wrapped._loop
        thread = wrapped._thread

        async def drain() -> None:
            pending = asyncio.all_tasks() - {asyncio.current_task()}
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            await loop.shutdown_asyncgens()

        asyncio.run_coroutine_threadsafe(drain(), loop).result(timeout=2)
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=2)
        assert not thread.is_alive()
        loop.close()


async def test_async_read_returns_raw_sliced_content_and_missing_error(
    backend: tuple[_LoopBoundLegacy, Any],
) -> None:
    inner, wrapped = backend
    assert inner.loop is not asyncio.get_running_loop()
    inner.files["/notes.md"] = ["first", "第二行", "third"]

    result = await wrapped.aread("/notes.md", offset=1, limit=1)
    assert isinstance(result, ReadResult)
    assert result.error is None
    assert result.file_data == {"content": "第二行", "encoding": "utf-8"}
    full = await wrapped.aread("/notes.md")
    assert full.file_data == {"content": "first\n第二行\nthird", "encoding": "utf-8"}
    missing = await wrapped.aread("/missing.md")
    assert isinstance(missing, ReadResult)
    assert missing.error == "Error: File '/missing.md' not found"


async def test_async_write_preserves_duplicate_write_protection(
    backend: tuple[_LoopBoundLegacy, Any],
) -> None:
    inner, wrapped = backend
    result = await wrapped.awrite(file_path="/notes.md", content="first\nsecond")
    assert isinstance(result, WriteResult)
    assert result.error is None
    assert result.path == "/notes.md"
    duplicate = await wrapped.awrite("/notes.md", "must not overwrite")
    assert isinstance(duplicate, WriteResult)
    assert duplicate.error is not None
    assert inner.files["/notes.md"] == ["first", "second"]
    assert inner.updates == [False]


async def test_async_edit_persists_replacements_and_handles_missing_files(
    backend: tuple[_LoopBoundLegacy, Any],
) -> None:
    inner, wrapped = backend
    inner.files["/notes.md"] = ["hello hello"]
    ambiguous = await wrapped.aedit("/notes.md", "hello", "updated")
    assert ambiguous.error is not None
    assert inner.files["/notes.md"] == ["hello hello"]
    result = await wrapped.aedit("/notes.md", "hello", "updated", replace_all=True)
    assert isinstance(result, EditResult)
    assert result.error is None
    assert result.occurrences == 2
    assert inner.files["/notes.md"] == ["updated updated"]
    assert inner.updates == [True]
    missing = await wrapped.aedit("/missing.md", "old", "new")
    assert isinstance(missing, EditResult)
    assert missing.error == "Error: File '/missing.md' not found"


@pytest.mark.parametrize(
    ("method", "args", "kwargs", "expected"),
    [
        (
            "grep",
            ("needle",),
            {"path": "/docs", "glob": "*.md"},
            [{"path": "/notes.md", "line": "matched"}],
        ),
        (
            "glob",
            ("*.md",),
            {"path": "/docs"},
            [{"path": "/notes.md", "is_dir": False}],
        ),
        (
            "upload_files",
            (),
            {"files": [("/notes.md", b"content\x00")]},
            [{"path": "/notes.md", "error": None}],
        ),
    ],
)
async def test_async_search_and_upload_keep_worker_loop_and_arguments(
    backend: tuple[_LoopBoundLegacy, Any],
    method: str,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    expected: list[dict[str, object]],
) -> None:
    inner, wrapped = backend
    result = await getattr(wrapped, f"a{method}")(*args, **kwargs)
    assert result == expected
    assert inner.calls == [(method, args, kwargs)]


async def test_async_read_without_raw_access_adapts_legacy_text(
    backend: tuple[_LoopBoundLegacy, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    inner, wrapped = backend
    monkeypatch.setattr(inner, "_get_file_data", None)
    result = await wrapped.aread("/notes.md", 2, 3)
    assert isinstance(result, ReadResult)
    assert result.file_data == {"content": "legacy formatted text: 2:3", "encoding": "utf-8"}
    missing = await wrapped.aread("/missing.md")
    assert missing.error == "Error: File '/missing.md' not found"


async def test_async_operations_keep_worker_timeout(
    backend: tuple[_LoopBoundLegacy, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    inner, wrapped = backend

    async def hung_grep(pattern: str) -> None:
        inner._check_loop()
        await asyncio.sleep(10)

    monkeypatch.setattr(inner, "agrep", hung_grep)
    monkeypatch.setattr(compat, "_BACKEND_IO_TIMEOUT", 0.05)
    with pytest.raises(TimeoutError, match="backend I/O timed out"):
        await asyncio.wait_for(wrapped.agrep("needle"), timeout=2)
    assert (await wrapped.als("/")).error is None
