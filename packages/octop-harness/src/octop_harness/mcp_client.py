"""Task-owned persistent MCP sessions for hosts that need state across calls."""

from __future__ import annotations

import asyncio
from typing import Any, cast

from langchain_mcp_adapters.sessions import Connection, create_session

from octop_harness.runtime_env import merge_host_stdio_env


class ManagedMCPClient:
    """Own one MCP session in a dedicated task; callers may use different tasks.

    AnyIO transports must open and close in the same task. Requests are serialized
    through that owner and return unmodified SDK results. Use ``async with`` or
    await ``aclose()``. Construct a new client after close or transport failure.
    Writes are never automatically replayed.
    """

    def __init__(self, connection: dict[str, Any]) -> None:
        self._connection = dict(connection)
        if self._connection.get("transport") == "stdio":
            self._connection["env"] = merge_host_stdio_env(self._connection.get("env") or {})
        self._queue: asyncio.Queue[tuple[str, dict[str, Any], asyncio.Future[Any]] | None] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None
        self._ready: asyncio.Future[None] | None = None
        self._closed = False
        self.instructions: str | None = None

    async def __aenter__(self) -> ManagedMCPClient:
        try:
            await self._start()
        except BaseException:
            await self.aclose()
            raise
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def _start(self) -> None:
        if self._closed:
            raise RuntimeError("MCP client is closed")
        if self._task is None:
            self._ready = asyncio.get_running_loop().create_future()
            self._task = asyncio.create_task(self._serve())
        assert self._ready is not None
        await asyncio.shield(self._ready)
        if self._task.done():
            raise RuntimeError("MCP session disconnected")

    async def _serve(self) -> None:
        assert self._ready is not None
        active: asyncio.Future[Any] | None = None
        try:
            async with create_session(cast(Connection, self._connection)) as session:
                async with asyncio.timeout(20):
                    initialized = await session.initialize()
                self.instructions = initialized.instructions
                self._ready.set_result(None)
                while (request := await self._queue.get()) is not None:
                    method, arguments, result = request
                    active = result
                    if result.cancelled():
                        continue
                    try:
                        async with asyncio.timeout(30):
                            value = await getattr(session, method)(**arguments)
                    except Exception as exc:
                        if not result.done():
                            result.set_exception(exc)
                    else:
                        if not result.done():
                            result.set_result(value)
        except BaseException as exc:
            if not self._ready.done():
                self._ready.set_exception(exc)
        finally:
            if active is not None and not active.done():
                active.set_exception(RuntimeError("MCP session disconnected"))
            while not self._queue.empty():
                pending = self._queue.get_nowait()
                if pending is not None and not pending[2].done():
                    pending[2].set_exception(RuntimeError("MCP session disconnected"))

    async def _request(self, method: str, **arguments: Any) -> Any:
        await self._start()
        result = asyncio.get_running_loop().create_future()
        self._queue.put_nowait((method, arguments, result))
        return await result

    async def get_tools(self) -> Any:
        """List tool definitions with their original JSON Schemas."""
        return await self._request("list_tools")

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Return the full CallToolResult, including structured content and errors."""
        return await self._request("call_tool", name=name, arguments=arguments)

    async def list_resources(self, cursor: str | None = None) -> Any:
        """List resources, optionally continuing a server-provided cursor."""
        return await self._request("list_resources", cursor=cursor)

    async def read_resource(self, uri: str) -> Any:
        """Read a resource by URI."""
        return await self._request("read_resource", uri=uri)

    async def aclose(self) -> None:
        """Close in the owner task; repeated calls are harmless."""
        if not self._closed:
            self._closed = True
            self._queue.put_nowait(None)
        if self._task is not None:
            await asyncio.shield(self._task)
