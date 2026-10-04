"""Tests for deepagents_backends protocol adaptation."""

from __future__ import annotations

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


def test_adapted_read_is_safe_for_harness_exists_check() -> None:
    from octop_harness.backends.utils import backend_file_exists

    wrapped = adapt_backend_protocol(_LegacyRemote())
    assert backend_file_exists(wrapped, "/hello.txt") is True
    assert backend_file_exists(wrapped, "/missing") is False
