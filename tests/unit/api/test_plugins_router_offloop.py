"""The plugin install routes must not run their work on the event loop.

``PluginManager.install_url`` performs a synchronous
``urllib.request.urlretrieve`` (with no timeout), and ``load_installed`` /
``install_archive`` unzip archives and import plugin code. Calling them inline
inside the async routes freezes the event loop for the whole download /
install, stalling every other request and websocket on the server.

``install_market_plugin`` already offloads its install to the default executor;
these tests pin the same behaviour for the three routes that still called the
manager inline.
"""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

from octop.api.routers import plugins as plugins_router

_BLOCK_SECONDS = 0.3
_LAG_LIMIT = 0.25


def _loaded() -> SimpleNamespace:
    manifest = SimpleNamespace(id="demo", version="1.0.0", name="Demo", kind="tool")
    return SimpleNamespace(manifest=manifest)


def _blocking_server() -> SimpleNamespace:
    """A server whose plugin manager blocks the calling thread on every call."""

    def _block(*_args: object, **_kwargs: object) -> SimpleNamespace:
        time.sleep(_BLOCK_SECONDS)
        return _loaded()

    def _block_list(*_args: object, **_kwargs: object) -> list[SimpleNamespace]:
        time.sleep(_BLOCK_SECONDS)
        return [_loaded()]

    mgr = SimpleNamespace(
        install_url=_block,
        install_archive=_block,
        load_installed=_block_list,
    )
    return SimpleNamespace(plugin_manager=mgr, app_runtime=None)


async def _loop_lag_after_task_starts(task: asyncio.Task[object]) -> float:
    """Measure how long the loop stayed frozen once ``task`` begins running."""
    start = asyncio.get_running_loop().time()

    async def _probe() -> float:
        await asyncio.sleep(0.05)
        return asyncio.get_running_loop().time() - start

    lag = await asyncio.create_task(_probe())
    await task
    return lag


class _FakeUpload:
    async def read(self) -> bytes:
        return b"PK\x03\x04 demo"


async def test_install_url_does_not_block_the_event_loop() -> None:
    server = _blocking_server()
    body = plugins_router.PluginInstallBody(url="https://example.com/plugin.zip")
    task = asyncio.create_task(plugins_router.install_plugin(body=body, server=server, _user=None))
    lag = await _loop_lag_after_task_starts(task)
    assert lag < _LAG_LIMIT, "install_plugin ran inline and froze the event loop"


async def test_reload_plugins_does_not_block_the_event_loop() -> None:
    server = _blocking_server()
    task = asyncio.create_task(plugins_router.reload_plugins(server=server, _user=None))
    lag = await _loop_lag_after_task_starts(task)
    assert lag < _LAG_LIMIT, "reload_plugins ran inline and froze the event loop"


async def test_upload_plugin_does_not_block_the_event_loop() -> None:
    server = _blocking_server()
    task = asyncio.create_task(
        plugins_router.upload_plugin(file=_FakeUpload(), force=False, server=server, _user=None)
    )
    lag = await _loop_lag_after_task_starts(task)
    assert lag < _LAG_LIMIT, "upload_plugin ran inline and froze the event loop"
