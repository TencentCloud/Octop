"""tests/unit/api/test_plugin_install_off_loop.py

``POST /plugins/install`` (URL) and ``POST /plugins/upload`` (archive) hand their
work to :class:`PluginManager`, which downloads the archive with
``urllib.request.urlretrieve`` and extracts/copies it with ``zipfile`` +
``shutil.copytree``. That work is blocking, so the request handlers must run it
off the event loop — exactly what the sibling ``POST /plugins/market/{id}/install``
handler already does via ``loop.run_in_executor``.

The probes below record ``threading.get_ident()`` inside the manager call and
assert it is not the thread driving the event loop.
"""

from __future__ import annotations

import asyncio
import io
import threading
from collections.abc import Callable, Coroutine
from types import SimpleNamespace
from typing import Any

from fastapi import UploadFile

from octop.api.routers import plugins as plugins_router


def _loaded_plugin() -> SimpleNamespace:
    return SimpleNamespace(
        manifest=SimpleNamespace(id="echo-tool", version="1.0.0", name="Echo", kind="tool")
    )


class _StubManager:
    """Records the thread each blocking install entry point ran on."""

    def __init__(self) -> None:
        self.thread_ids: list[int] = []

    def install_url(self, url: str, *, force: bool = False) -> Any:
        self.thread_ids.append(threading.get_ident())
        return _loaded_plugin()

    def install_archive(self, archive: Any, *, force: bool = False) -> Any:
        self.thread_ids.append(threading.get_ident())
        return _loaded_plugin()


class _FakeServer:
    """Minimal stand-in for ``OctopServer`` (no app runtime → no reload step)."""

    app_runtime = None

    def __init__(self, manager: _StubManager) -> None:
        self.plugin_manager = manager


def _run(call: Callable[[], Coroutine[Any, Any, Any]]) -> tuple[Any, int]:
    """Await *call* on a fresh loop; return its result and the loop's thread id."""
    loop_thread: list[int] = []

    async def _main() -> Any:
        loop_thread.append(threading.get_ident())
        return await call()

    return asyncio.run(_main()), loop_thread[0]


def test_install_plugin_runs_blocking_install_off_event_loop(
    monkeypatch: Any,
) -> None:
    stub = _StubManager()
    server = _FakeServer(stub)
    monkeypatch.setattr(plugins_router, "_plugin_manager", lambda _server: stub)
    body = plugins_router.PluginInstallBody(url="https://example.com/echo-tool.zip")

    result, loop_thread = _run(
        lambda: plugins_router.install_plugin(body=body, server=server, _user=None)
    )

    assert result["id"] == "echo-tool"
    assert stub.thread_ids, "install_url was never called"
    assert stub.thread_ids[0] != loop_thread, "install_url ran on the event loop thread"


def test_upload_plugin_runs_blocking_extract_off_event_loop(
    monkeypatch: Any,
) -> None:
    stub = _StubManager()
    server = _FakeServer(stub)
    monkeypatch.setattr(plugins_router, "_plugin_manager", lambda _server: stub)
    upload = UploadFile(file=io.BytesIO(b"PK\x03\x04zip-ish"), filename="echo-tool.zip")

    result, loop_thread = _run(
        lambda: plugins_router.upload_plugin(file=upload, force=False, server=server, _user=None)
    )

    assert result["id"] == "echo-tool"
    assert stub.thread_ids, "install_archive was never called"
    assert stub.thread_ids[0] != loop_thread, "install_archive ran on the event loop thread"
