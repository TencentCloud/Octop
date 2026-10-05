"""Tests for deepagents_backends protocol adaptation."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from deepagents.backends.protocol import BackendProtocol, ReadResult

from octop.infra.backend.compat import adapt_backend_protocol, is_adapted_backend


class _LegacyRemote:
    """Mirrors deepagents_backends: default ``ls``, listing via ``ls_info``."""

    ls = BackendProtocol.ls

    def ls_info(self, path: str) -> list[dict[str, object]]:
        return [{"path": f"{path.rstrip('/')}/a.txt", "is_dir": False}]

    async def als_info(self, path: str) -> list[dict[str, object]]:
        return self.ls_info(path)

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        del offset, limit
        if file_path.endswith("missing"):
            return f"Error: File '{file_path}' not found"
        return "hello"


def test_is_adapted_backend() -> None:
    raw = _LegacyRemote()
    wrapped = adapt_backend_protocol(raw)
    assert is_adapted_backend(wrapped)
    assert not is_adapted_backend(raw)
    modern = SimpleNamespace(ls=lambda path: path)
    assert not is_adapted_backend(adapt_backend_protocol(modern))


@pytest.mark.asyncio
async def test_adapt_legacy_ls_and_read() -> None:
    wrapped = adapt_backend_protocol(_LegacyRemote())
    listed = await wrapped.als("/")
    assert listed.error is None
    assert listed.entries == [{"path": "/a.txt", "is_dir": False}]

    ok = wrapped.read("/hello.txt")
    assert isinstance(ok, ReadResult)
    assert ok.error is None
    assert ok.file_data == {"content": "hello", "encoding": "utf-8"}

    missing = wrapped.read("/missing")
    assert missing.error == "Error: File '/missing' not found"


def test_adapt_skips_backends_that_implement_ls() -> None:
    modern = SimpleNamespace(ls=lambda path: path)
    assert adapt_backend_protocol(modern) is modern


def test_adapt_skips_modern_ls_even_if_als_info_exists() -> None:
    class _Modern:
        def ls(self, path: str) -> object:
            return path

        async def als_info(self, path: str) -> list[dict[str, object]]:
            raise AssertionError("modern ls must not be wrapped")

        def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> object:
            del file_path, offset, limit
            return object()

    modern = _Modern()
    assert adapt_backend_protocol(modern) is modern


def test_adapt_wraps_when_read_returns_str() -> None:
    class _StringRead:
        def ls(self, path: str) -> None:
            raise NotImplementedError

        def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
            del offset, limit
            return f"body:{file_path}"

    wrapped = adapt_backend_protocol(_StringRead())
    assert is_adapted_backend(wrapped)
    ok = wrapped.read("/hello.txt")
    assert ok.error is None
    assert ok.file_data == {"content": "body:/hello.txt", "encoding": "utf-8"}


def test_adapt_read_uses_raw_file_data() -> None:
    class _Stored:
        ls = BackendProtocol.ls

        async def _get_file_data(self, path: str) -> dict[str, object]:
            return {"content": ["---", "summary: test"]}

        def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
            del file_path, offset, limit
            return "  1  ---\n  2  summary: test"

    wrapped = adapt_backend_protocol(_Stored())
    result = wrapped.read("/AGENTS.md")
    assert result.error is None
    assert result.file_data == {"content": "---\nsummary: test", "encoding": "utf-8"}


class _StoredFiles:
    ls = BackendProtocol.ls

    def __init__(self) -> None:
        self.files: dict[str, list[str]] = {}

    async def _exists(self, path: str) -> bool:
        return path in self.files

    async def _get_file_data(self, path: str) -> dict[str, object] | None:
        lines = self.files.get(path)
        if lines is None:
            return None
        return {"content": list(lines)}

    async def _put_file_data(self, path: str, data: dict[str, object], **_: object) -> None:
        content = data.get("content", [])
        self.files[path] = list(content) if isinstance(content, list) else str(content).splitlines()


def test_adapt_write_and_edit_use_current_result_types() -> None:
    inner = _StoredFiles()
    wrapped = adapt_backend_protocol(inner)
    written = wrapped.write("/MEMORY.md", "hello")
    assert written.error is None
    assert written.path == "/MEMORY.md"
    assert wrapped.write("/MEMORY.md", "again").error is not None
    edited = wrapped.edit("/MEMORY.md", "hello", "hello world")
    assert edited.error is None
    assert edited.occurrences == 1
    assert inner.files["/MEMORY.md"] == ["hello world"]
    missing = wrapped.edit("/missing.md", "a", "b")
    assert missing.error == "Error: File '/missing.md' not found"


def test_adapt_mkdir_path_is_noop() -> None:
    wrapped = adapt_backend_protocol(_LegacyRemote())
    wrapped.mkdir_path("/.octop")


@pytest.mark.asyncio
async def test_adapt_sync_reads_share_one_loop() -> None:
    """Postgres/S3 sync read must not spawn a new loop per call (pool would hang)."""
    wrapped = adapt_backend_protocol(_LegacyRemote())
    first = wrapped.read("/hello.txt")
    second = wrapped.read("/hello.txt")
    assert first.error is None
    assert second.error is None


def test_adapted_read_is_safe_for_harness_exists_check() -> None:
    from octop_harness.backends.utils import backend_file_exists

    wrapped = adapt_backend_protocol(_LegacyRemote())
    assert backend_file_exists(wrapped, "/hello.txt") is True
    assert backend_file_exists(wrapped, "/missing") is False


@pytest.mark.asyncio
async def test_adapt_write_edit_list_share_one_loop() -> None:
    class _Stored(_StoredFiles):
        def ls_info(self, path: str) -> list[dict[str, object]]:
            del path
            return [{"path": name, "is_dir": False} for name in self.files]

    inner = _Stored()
    wrapped = adapt_backend_protocol(inner)
    assert wrapped.write("/MEMORY.md", "hello").error is None
    assert wrapped.edit("/MEMORY.md", "hello", "hello world").occurrences == 1
    listed = await wrapped.als("/")
    assert listed.error is None
    assert listed.entries == [{"path": "/MEMORY.md", "is_dir": False}]


def test_adapt_grep_uses_worker_not_sync_inner() -> None:
    class _LegacyGrep(_LegacyRemote):
        def grep(self, *args: object, **kwargs: object) -> object:
            raise AssertionError("sync grep must not run (run_async_safely)")

        async def agrep(self, pattern: str, path: str = "/") -> list[dict[str, object]]:
            del path
            return [{"path": "/a.txt", "line": pattern}]

    wrapped = adapt_backend_protocol(_LegacyGrep())
    assert wrapped.grep("hello") == [{"path": "/a.txt", "line": "hello"}]


@pytest.mark.asyncio
async def test_adapt_als_info_uses_worker() -> None:
    class _Legacy(_LegacyRemote):
        def ls_info(self, path: str) -> list[dict[str, object]]:
            raise AssertionError("sync ls_info must not run on the server loop")

        async def als_info(self, path: str) -> list[dict[str, object]]:
            return [{"path": f"{path.rstrip('/')}/a.txt", "is_dir": False}]

    wrapped = adapt_backend_protocol(_Legacy())
    listed = await wrapped.als_info("/")
    assert listed == [{"path": "/a.txt", "is_dir": False}]


@pytest.mark.asyncio
async def test_adapt_download_uses_worker() -> None:
    class _Legacy(_LegacyRemote):
        def download_files(self, paths: list[str]) -> object:
            raise AssertionError("sync download_files must not run")

        async def adownload_files(self, paths: list[str]) -> list[dict[str, object]]:
            return [{"path": paths[0], "content": b"ok"}]

    wrapped = adapt_backend_protocol(_Legacy())
    rows = await wrapped.adownload_files(["/a.txt"])
    assert rows == [{"path": "/a.txt", "content": b"ok"}]


def test_adapt_s3_list_falls_back_to_v1(monkeypatch: pytest.MonkeyPatch) -> None:
    import octop.infra.backend.compat as compat

    class _S3:
        ls = BackendProtocol.ls
        _bucket = "bucket"

        def _s3_key(self, path: str) -> str:
            return path

        async def als_info(self, path: str) -> list[dict[str, object]]:
            del path
            exc = Exception("not implemented")
            exc.response = {"Error": {"Code": "NotImplemented"}}  # type: ignore[attr-defined]
            raise exc

    async def fake_v1(backend: object, path: str) -> list[dict[str, object]]:
        del backend
        return [{"path": f"{path.rstrip('/')}/via-v1", "is_dir": False}]

    monkeypatch.setattr(compat, "_s3_als_info_v1", fake_v1)
    wrapped = compat.adapt_backend_protocol(_S3())
    listed = wrapped.ls("/")
    assert listed.entries == [{"path": "/via-v1", "is_dir": False}]


def test_adapt_run_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
    import octop.infra.backend.compat as compat

    class _Hung(_LegacyRemote):
        async def als_info(self, path: str) -> list[dict[str, object]]:
            del path
            await asyncio.sleep(10)
            return []

    monkeypatch.setattr(compat, "_BACKEND_IO_TIMEOUT", 0.05)
    wrapped = compat.adapt_backend_protocol(_Hung())
    with pytest.raises(TimeoutError, match="backend I/O timed out"):
        wrapped.ls("/")
