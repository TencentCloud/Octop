"""Windows desktop entry point for the packaged Octop app."""

from __future__ import annotations

import argparse
import asyncio
import os
import socket
import sys
import threading
import traceback
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_HOST = "127.0.0.1"
DEFAULT_WIDTH = 1280
DEFAULT_HEIGHT = 860
DEFAULT_MIN_WIDTH = 1024
DEFAULT_MIN_HEIGHT = 700
DEFAULT_STARTUP_TIMEOUT_SECONDS = 60.0


class DesktopStartupError(RuntimeError):
    """Raised when the embedded HTTP server cannot start."""


def find_available_port(host: str = DEFAULT_HOST) -> int:
    """Reserve a local TCP port briefly and return the selected port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        port = sock.getsockname()[1]
    return int(port)


@dataclass
class DesktopServer:
    """Run the Octop FastAPI server in a background thread for WebView."""

    host: str = DEFAULT_HOST
    port: int = 0
    log_level: str = "info"
    startup_timeout_seconds: float = DEFAULT_STARTUP_TIMEOUT_SECONDS
    _ready: threading.Event = field(default_factory=threading.Event, init=False)
    _thread: threading.Thread | None = field(default=None, init=False)
    _loop: asyncio.AbstractEventLoop | None = field(default=None, init=False)
    _uvicorn_server: Any | None = field(default=None, init=False)
    _startup_error: BaseException | None = field(default=None, init=False)

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}/"

    def start(self) -> str:
        if self._thread is not None:
            return self.url

        if self.port <= 0:
            self.port = find_available_port(self.host)

        self._thread = threading.Thread(
            target=self._thread_main,
            name="octop-desktop-server",
            daemon=True,
        )
        self._thread.start()

        if not self._ready.wait(self.startup_timeout_seconds):
            self.stop()
            raise DesktopStartupError(
                f"Octop desktop server did not start within "
                f"{self.startup_timeout_seconds:.0f} seconds"
            )
        if self._startup_error is not None:
            raise DesktopStartupError(
                "Octop desktop server failed to start"
            ) from self._startup_error
        return self.url

    def stop(self) -> None:
        loop = self._loop
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(self._request_uvicorn_shutdown)
        elif self._uvicorn_server is not None:
            self._request_uvicorn_shutdown()

        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=20)

    def _request_uvicorn_shutdown(self) -> None:
        if self._uvicorn_server is not None:
            self._uvicorn_server.should_exit = True

    def _thread_main(self) -> None:
        try:
            asyncio.run(self._run_async())
        except BaseException as exc:  # noqa: BLE001 - bridge failure back to main thread
            _write_startup_error(exc)
            self._startup_error = exc
            self._ready.set()

    async def _run_async(self) -> None:
        import uvicorn

        from octop.api.app import build_app
        from octop.infra.server import OctopServer

        # Desktop mode is bound to loopback and has no visible terminal. Avoid
        # writing a first-run wizard password file that users cannot discover.
        os.environ.setdefault("OCTOP_REQUIRE_SETUP_PASSWORD", "0")

        self._loop = asyncio.get_running_loop()
        octop_server = OctopServer()
        await octop_server.start()
        app = build_app(octop_server)
        config = uvicorn.Config(
            app,
            host=self.host,
            port=self.port,
            log_level=self.log_level,
            log_config=None,
            access_log=False,
            workers=1,
            reload=False,
        )
        self._uvicorn_server = uvicorn.Server(config)
        serve_task = asyncio.create_task(self._uvicorn_server.serve())

        try:
            await self._wait_until_started(serve_task)
            await serve_task
        finally:
            await octop_server.stop()
            self._loop = None

    async def _wait_until_started(self, serve_task: asyncio.Task[None]) -> None:
        if self._uvicorn_server is None:
            raise DesktopStartupError("uvicorn server was not initialized")
        deadline = asyncio.get_running_loop().time() + max(1.0, float(self.startup_timeout_seconds))
        while not self._uvicorn_server.started:
            if serve_task.done():
                await serve_task
            if asyncio.get_running_loop().time() >= deadline:
                raise DesktopStartupError("Timed out waiting for uvicorn startup")
            await asyncio.sleep(0.05)
        self._ready.set()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Octop as a local desktop app.")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Local bind host.")
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="Local bind port. Defaults to a random available port.",
    )
    parser.add_argument("--log-level", default="info", help="uvicorn log level.")
    parser.add_argument(
        "--startup-timeout",
        type=float,
        default=DEFAULT_STARTUP_TIMEOUT_SECONDS,
        help="Seconds to wait for the embedded backend to start.",
    )
    parser.add_argument(
        "--no-window",
        action="store_true",
        help="Start only the local backend; useful for Windows installer smoke tests.",
    )
    parser.add_argument(
        "--print-url",
        action="store_true",
        help="Print the local URL after startup.",
    )
    parser.add_argument(
        "--debug-webview",
        action="store_true",
        help="Enable PyWebView debug mode.",
    )
    return parser


def _write_startup_error(exc: BaseException) -> None:
    home = os.environ.get("OCTOP_HOME")
    root = Path(home) if home else Path.home() / ".octop"
    log_dir = root / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "desktop-startup-error.log").write_text(
            "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
            encoding="utf-8",
        )
    except OSError:
        return


def _run_without_window(server: DesktopServer, *, print_url: bool) -> int:
    if print_url:
        print(server.url, flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        return 0
    finally:
        server.stop()
    return 0


def _run_webview(server: DesktopServer, *, debug: bool) -> int:
    try:
        import webview
    except ImportError as exc:
        server.stop()
        raise DesktopStartupError(
            "PyWebView is not installed. Install Octop with the 'windows-desktop' extra."
        ) from exc

    webview.create_window(
        "Octop",
        server.url,
        width=DEFAULT_WIDTH,
        height=DEFAULT_HEIGHT,
        min_size=(DEFAULT_MIN_WIDTH, DEFAULT_MIN_HEIGHT),
    )
    try:
        webview.start(debug=debug)
    finally:
        server.stop()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    server = DesktopServer(
        host=args.host,
        port=args.port,
        log_level=args.log_level,
        startup_timeout_seconds=args.startup_timeout,
    )
    try:
        server.start()
        if args.no_window:
            return _run_without_window(server, print_url=args.print_url)
        return _run_webview(server, debug=args.debug_webview)
    except DesktopStartupError as exc:
        print(f"Octop desktop failed to start: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
