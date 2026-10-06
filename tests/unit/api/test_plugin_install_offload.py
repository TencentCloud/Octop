"""Installing a plugin must not run the download/unpack on the event loop."""

from __future__ import annotations

import asyncio
import io
import threading
from types import SimpleNamespace

import pytest

from octop.api.routers import plugins as plugins_router


class _Manager:
    def __init__(self):
        self.threads: list[int] = []

    def install_url(self, url):
        self.threads.append(threading.get_ident())
        return SimpleNamespace(manifest=SimpleNamespace(id="x", version="1", name="n", kind="tool"))

    def install_archive(self, path, force=False):
        self.threads.append(threading.get_ident())
        return SimpleNamespace(manifest=SimpleNamespace(id="x", version="1", name="n", kind="tool"))


class _Upload:
    def __init__(self, raw: bytes):
        self._raw = raw

    async def read(self) -> bytes:
        return self._raw


def _server(mgr):
    return SimpleNamespace(app_runtime=None, plugin_manager=mgr)


@pytest.mark.parametrize("entry", ["url", "archive"])
def test_the_install_runs_off_the_event_loop(entry, monkeypatch):
    mgr = _Manager()
    monkeypatch.setattr(plugins_router, "_plugin_manager", lambda server: mgr)
    seen: dict[str, int] = {}

    async def _go():
        seen["loop"] = threading.get_ident()
        if entry == "url":
            await plugins_router.install_plugin(
                body=SimpleNamespace(url="https://example.invalid/p.zip"),
                server=_server(mgr),
                _user=None,
            )
        else:
            await plugins_router.upload_plugin(
                file=_Upload(b"PK\x03\x04"),
                force=False,
                server=_server(mgr),
                _user=None,
            )

    asyncio.run(_go())

    assert mgr.threads, "the manager was never called"
    assert seen["loop"] not in mgr.threads, f"{entry} install ran on the event loop thread"
