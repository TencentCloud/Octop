"""Private loopback control channel for the local CLI (filesystem trust boundary)."""

from __future__ import annotations

import asyncio
import hmac
import json
import os
import secrets
import socket
import tempfile
import time
from collections.abc import Iterator
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, Any

from octop.i18n import tr

if TYPE_CHECKING:
    from octop.infra.server import OctopServer

ENDPOINT = "memory-slim-control.json"


class MemorySlimControl:
    def __init__(self, server: OctopServer) -> None:
        self.root = server.paths.root
        self.server = server
        self.token = secrets.token_hex(32)
        self.listener: asyncio.Server | None = None
        self._clients: set[asyncio.Task[Any]] = set()
        self._closing = False

    async def start(self) -> None:
        self.listener = await asyncio.start_server(self._handle, "127.0.0.1", 0, limit=8192)
        port = self.listener.sockets[0].getsockname()[1]
        with tempfile.NamedTemporaryFile(mode="w", dir=self.root, delete=False) as stream:
            temp = Path(stream.name)
            json.dump({"port": port, "token": self.token, "pid": os.getpid()}, stream)
        temp.replace(self.root / ENDPOINT)

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        if task is not None:
            self._clients.add(task)
        try:
            request = json.loads(await asyncio.wait_for(reader.readline(), timeout=5))
            token = request.get("token")
            if not isinstance(token, str) or not hmac.compare_digest(token, self.token):
                raise ValueError("Invalid local control token")
            locale = request.get("locale", "en")
            locale = locale if isinstance(locale, str) else "en"
            if self._closing:
                return
            runtime = self.server.app_runtime
            if runtime is None:
                raise ValueError(tr("memory_slim.not_ready", locale))
            coordinator = runtime.agent_registry.memory_slim
            operation = request.get("operation", "slim")
            if operation == "list":
                response = {
                    "phase": "agents",
                    "agents": coordinator.list_agents(locale=locale),
                }
                writer.write((json.dumps(response, ensure_ascii=False) + "\n").encode())
                await writer.drain()
                return
            if operation != "slim":
                raise ValueError("Unknown memory control operation")
            agent_id = request.get("agent_id")
            if not isinstance(agent_id, str) or not agent_id or len(agent_id) > 256:
                raise ValueError("agent_id is required")
            coordinator.start(agent_id, locale=locale)
            started = time.monotonic()
            state = coordinator.state
            previous = ""
            while True:
                status = dict(state)
                status["elapsed_seconds"] = int(time.monotonic() - started)
                encoded = json.dumps(status, ensure_ascii=False)
                if encoded != previous:
                    writer.write((encoded + "\n").encode())
                    await writer.drain()
                    previous = encoded
                if status.get("phase") in {"done", "failed"}:
                    break
                await asyncio.sleep(0.25)
        except (ConnectionError, asyncio.CancelledError):
            # Disconnecting the CLI must not cancel a running database operation.
            pass
        except Exception as exc:
            writer.write((json.dumps({"phase": "failed", "error": str(exc)}) + "\n").encode())
            with suppress(ConnectionError):
                await writer.drain()
        finally:
            writer.close()
            if task is not None:
                self._clients.discard(task)

    async def close(self) -> None:
        self._closing = True
        if self.listener is not None:
            self.listener.close()
            await self.listener.wait_closed()
        for task in tuple(self._clients):
            task.cancel()
        if self._clients:
            await asyncio.gather(*self._clients, return_exceptions=True)
        path = self.root / ENDPOINT
        try:
            if json.loads(path.read_text()).get("token") == self.token:
                path.unlink()
        except (OSError, ValueError):
            pass


def request_memory_slim(
    root: Path, agent_id: str, *, locale: str = "en"
) -> Iterator[dict[str, Any]]:
    """Stream progress from an already running host; never starts another Octop."""
    yield from _request_control(root, {"agent_id": agent_id, "locale": locale})


def list_memory_slim_agents(root: Path, *, locale: str = "en") -> list[dict[str, str]]:
    """Read-only discovery through the authenticated running host."""
    for status in _request_control(root, {"operation": "list", "locale": locale}):
        if status["phase"] == "failed":
            raise RuntimeError(status["error"])
        agents: list[dict[str, str]] = status["agents"]
        return agents
    raise RuntimeError("Octop returned no agent list")


def _request_control(root: Path, request: dict[str, str]) -> Iterator[dict[str, Any]]:
    endpoint = json.loads((root / ENDPOINT).read_text())
    with socket.create_connection(("127.0.0.1", int(endpoint["port"])), timeout=5) as sock:
        sock.sendall((json.dumps({"token": endpoint["token"], **request}) + "\n").encode())
        sock.settimeout(None)
        with sock.makefile("r", encoding="utf-8") as stream:
            for line in stream:
                status = json.loads(line)
                yield status
                if status.get("phase") in {"done", "failed", "agents"}:
                    return
    raise RuntimeError("Octop disconnected; check the dashboard before retrying maintenance")
