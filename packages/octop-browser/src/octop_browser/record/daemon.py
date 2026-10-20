"""Local daemon for long-lived browser recording sessions."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from octop_browser.record.models import PrivacySettings
from octop_browser.record.recorder import RecordController, RecordSession
from octop_browser.record.settings import settings


class RecordDaemon:
    def __init__(self) -> None:
        self.controller = RecordController()
        self.active: RecordSession | None = None
        self.active_name: str | None = None
        self.server: asyncio.AbstractServer | None = None

    async def handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            raw = await reader.readline()
            request = json.loads(raw.decode("utf-8")) if raw else {}
            response = await self.dispatch(request)
        except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-except
            response = {"ok": False, "error": str(exc)}
        writer.write((json.dumps(response, ensure_ascii=False) + "\n").encode("utf-8"))
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    async def dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        command = request.get("command")
        if command == "ping":
            return {"ok": True, "active": self._active_info()}
        if command == "start":
            if self.active is not None:
                return {
                    "ok": False,
                    "error": "A recording is already active",
                    "active": self._active_info(),
                }
            privacy = PrivacySettings(
                input_policy=request.get("privacy", "mask-sensitive"),
                url_query_policy="mask-sensitive",
                screenshot_policy=request.get("screenshots", "off"),
            )
            session, data = await self.controller.start_in_process(
                profile=request.get("profile", "default"),
                privacy=privacy,
                name=request.get("name"),
            )
            self.active = session
            self.active_name = request.get("name")
            data["daemon"] = True
            return data
        if command == "stop":
            if self.active is None:
                return {"ok": False, "error": "No active recording"}
            rec_id = request.get("recording_id")
            if rec_id and rec_id != self.active.manifest.recording_id:
                return {
                    "ok": False,
                    "error": f"Active recording is {self.active.manifest.recording_id}, not {rec_id}",
                }
            data = await self.active.stop(
                generate_steps=bool(request.get("generate_steps", True)),
                skill_name=request.get("name") or self.active_name,
            )
            await self.active.close()
            self.active = None
            self.active_name = None
            data["ok"] = True
            return data
        if command == "status":
            return {"ok": True, "active": self._active_info()}
        if command == "shutdown":
            if self.active is not None:
                await self.active.stop(generate_steps=True, skill_name=self.active_name)
                await self.active.close()
                self.active = None
            asyncio.get_running_loop().call_soon(self._close_server)
            return {"ok": True, "shutdown": True}
        return {"ok": False, "error": f"Unknown command: {command}"}

    def _active_info(self) -> dict[str, Any] | None:
        if self.active is None:
            return None
        return {
            "recordingId": self.active.manifest.recording_id,
            "profile": self.active.manifest.profile,
            "startUrl": self.active.manifest.target.start_url,
            "events": self.active.manifest.stats.events,
        }

    def _close_server(self) -> None:
        if self.server is not None:
            self.server.close()

    async def run(self) -> None:
        sock = socket_path()
        sock.parent.mkdir(parents=True, exist_ok=True)
        try:
            sock.unlink()
        except FileNotFoundError:
            pass
        self.server = await asyncio.start_unix_server(self.handle, path=str(sock))
        pid_path().write_text(str(os.getpid()), encoding="utf-8")
        try:
            async with self.server:
                await self.server.serve_forever()
        except asyncio.CancelledError:
            pass
        finally:
            try:
                sock.unlink()
            except FileNotFoundError:
                pass
            try:
                pid_path().unlink()
            except FileNotFoundError:
                pass


def socket_path() -> Path:
    return settings.base_dir / "daemon.sock"


def pid_path() -> Path:
    return settings.base_dir / "daemon.pid"


async def send_request(request: dict[str, Any], timeout: float = 5.0) -> dict[str, Any]:
    """Send one JSON request to the record daemon and return its reply.

    When the daemon is not reachable this returns the standard
    ``{"ok": False, "error": ...}`` envelope instead of leaking a raw
    ``[Errno 2] No such file or directory`` from the unix socket, so CLI and
    MCP callers can surface an actionable message.
    """
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_unix_connection(str(socket_path())), timeout=timeout
        )
    except (OSError, asyncio.TimeoutError):
        return {
            "ok": False,
            "error": (
                "Record daemon is not running. Start it with "
                "`octop-browser record daemon-start`."
            ),
        }
    writer.write((json.dumps(request, ensure_ascii=False) + "\n").encode("utf-8"))
    await writer.drain()
    raw = await asyncio.wait_for(reader.readline(), timeout=timeout)
    writer.close()
    await writer.wait_closed()
    return dict(json.loads(raw.decode("utf-8")))


async def is_running() -> bool:
    try:
        response = await send_request({"command": "ping"}, timeout=1.0)
        return bool(response.get("ok"))
    except Exception:  # pylint: disable=broad-except
        return False


def start_daemon_process() -> dict[str, Any]:
    settings.base_dir.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-m", "octop_browser.record.daemon"]
    kwargs: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if hasattr(os, "setsid"):
        kwargs["start_new_session"] = True
    proc = subprocess.Popen(cmd, **kwargs)  # noqa: S603
    return {"ok": True, "pid": proc.pid, "socket": str(socket_path())}


async def ensure_daemon() -> dict[str, Any]:
    if await is_running():
        return {"ok": True, "alreadyRunning": True, "socket": str(socket_path())}
    data = start_daemon_process()
    for _ in range(30):
        await asyncio.sleep(0.1)
        if await is_running():
            return data
    return {"ok": False, "error": "Daemon did not start", **data}


async def main() -> None:
    await RecordDaemon().run()


if __name__ == "__main__":
    asyncio.run(main())
