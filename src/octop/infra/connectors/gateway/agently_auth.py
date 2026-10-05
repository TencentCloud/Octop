"""Instance-scoped Agent Mail device authorization, without exposing CLI tokens."""

from __future__ import annotations

import asyncio
import json
import os
import re
import signal
import time
from contextlib import suppress
from dataclasses import dataclass, field
from functools import partial
from typing import Any, Literal, TypedDict
from urllib.parse import parse_qs, urlsplit
from weakref import WeakValueDictionary

from octop.i18n import tr
from octop.infra.connectors.gateway.adapters.agently_cli import prepare_env
from octop.infra.connectors.gateway.cli_dirs import resolve_cli_config_key
from octop.infra.connectors.gateway.cli_runner import resolve_binary
from octop.infra.utils.paths import PathLayout
from octop.infra.utils.posix_compat import killpg, sigkill

AuthAction = Literal["start", "status", "logout", "refresh", "disconnect"]
AuthStatus = Literal["idle", "pending", "authorized", "expired", "error"]
_LOGIN_TIMEOUT = 600.0
_COMMAND_TIMEOUT = 30.0
_START_WAIT = 3.0
_URL = re.compile(r'https://[^\s<>"\x1b]+')


class AuthResult(TypedDict):
    status: AuthStatus
    verification_url: str | None
    user_code: str | None
    expires_at: int | None
    error: str | None


@dataclass
class _Login:
    status: AuthStatus = "pending"
    verification_url: str | None = None
    user_code: str | None = None
    expires_at: int = field(default_factory=lambda: int(time.time() + _LOGIN_TIMEOUT))
    error_key: str | None = None
    ready: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task[None] | None = None


# The CLI persists grants; device flows and their latest result live in memory.
_sessions: dict[str, _Login] = {}
_locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()


def _key(creds: dict[str, Any]) -> str:
    return str(
        PathLayout.from_env().connector_cli_instance_dir(
            "agently-cli", resolve_cli_config_key(creds)
        )
    )


def _result(
    status: AuthStatus,
    *,
    session: _Login | None = None,
    error_key: str | None = None,
    locale: str = "en",
) -> AuthResult:
    error_key = error_key or (session.error_key if session else None)
    return {
        "status": status,
        "verification_url": session.verification_url if session and status == "pending" else None,
        "user_code": session.user_code if session and status == "pending" else None,
        "expires_at": session.expires_at if session and status == "pending" else None,
        "error": tr(f"connector.agently.{error_key}", locale) if error_key else None,
    }


def _prepare(creds: dict[str, Any]) -> tuple[str, dict[str, str]]:
    try:
        binary = resolve_binary("agently-cli")
    except ValueError as exc:
        raise FileNotFoundError from exc
    return binary, prepare_env(creds)


async def _spawn(creds: dict[str, Any], command: str) -> asyncio.subprocess.Process:
    binary, env = await asyncio.get_running_loop().run_in_executor(None, partial(_prepare, creds))
    return await asyncio.create_subprocess_exec(
        binary,
        "auth",
        command,
        env=env,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT if command == "login" else asyncio.subprocess.PIPE,
        start_new_session=os.name == "posix",
    )


async def stop_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    # npm's launcher spawns the native CLI: terminate its entire process tree.
    if os.name == "posix":
        with suppress(ProcessLookupError):
            killpg(process.pid, signal.SIGTERM)
    else:
        killer = await asyncio.create_subprocess_exec(
            "taskkill",
            "/PID",
            str(process.pid),
            "/T",
            "/F",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await killer.wait()
    try:
        await asyncio.wait_for(process.wait(), 2.0)
    except TimeoutError:
        with suppress(ProcessLookupError):
            if os.name == "posix":
                killpg(process.pid, sigkill())
            else:
                process.kill()
        await process.wait()


async def _command(creds: dict[str, Any], command: str) -> dict[str, Any]:
    process = await _spawn(creds, command)
    try:
        output, _ = await asyncio.wait_for(process.communicate(), _COMMAND_TIMEOUT)
        if process.returncode != 0:
            raise ValueError("agently auth failed")
        # Status can include a diagnostic line before its JSON response.
        text = output.decode("utf-8", errors="replace")
        payload = json.loads(text[text.index("{") :])
        if not isinstance(payload, dict) or payload.get("ok") is not True:
            raise ValueError("invalid agently auth response")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise ValueError("invalid agently auth data")
        return data
    finally:
        await stop_process(process)


def _read_verification_url(line: str, session: _Login) -> None:
    for match in _URL.finditer(line):
        url = match.group().rstrip(",;)")
        parsed = urlsplit(url)
        host = parsed.hostname or ""
        query = parse_qs(parsed.query)
        if (
            (host == "agent.qq.com" or host.endswith(".agent.qq.com"))
            and not parsed.username
            and not parsed.password
            and not {"access_token", "refresh_token", "device_code"}.intersection(query)
        ):
            session.verification_url = url
            session.user_code = (query.get("user_code") or [""])[0] or None
            session.ready.set()
            return


def _auth_status(data: dict[str, Any]) -> AuthStatus:
    if data.get("token_status") == "expired":
        return "expired"
    return "authorized" if data.get("logged_in") is True else "idle"


async def _login(creds: dict[str, Any], session: _Login) -> None:
    process: asyncio.subprocess.Process | None = None
    try:
        async with asyncio.timeout(_LOGIN_TIMEOUT):
            process = await _spawn(creds, "login")
            assert process.stdout is not None
            while line := await process.stdout.readline():
                if session.verification_url is None:
                    _read_verification_url(line.decode("utf-8", errors="replace"), session)
            if (
                await process.wait() != 0
                or _auth_status(await _command(creds, "status")) != "authorized"
            ):
                raise ValueError("agently login did not authorize")
            session.status = "authorized"
    except TimeoutError:
        session.status, session.error_key = "expired", "login_expired"
    except FileNotFoundError:
        session.status, session.error_key = "error", "cli_missing"
    except Exception:
        # CLI output can contain tokens. Never return or log the raw exception/output.
        session.status, session.error_key = "error", "login_failed"
    finally:
        if process is not None:
            await stop_process(process)
        session.ready.set()


async def _cancel(key: str) -> None:
    session = _sessions.pop(key, None)
    if session is not None and session.task is not None:
        session.task.cancel()
        with suppress(asyncio.CancelledError):
            await session.task


async def close() -> None:
    """Reap unfinished login processes during server shutdown."""
    await asyncio.gather(*[_cancel(key) for key in list(_sessions)])


async def authorize(creds: dict[str, Any], action: AuthAction, *, locale: str = "en") -> AuthResult:
    disconnect = action == "disconnect"
    if disconnect:
        action = "logout"
    key = _key(creds)
    lock = _locks.setdefault(key, asyncio.Lock())
    async with lock:
        session = _sessions.get(key)
        if (
            action in {"start", "status"}
            and session is not None
            and (
                session.status == "pending"
                or (action == "status" and session.status != "authorized")
            )
        ):
            return _result(session.status, session=session, locale=locale)
        if action == "start":
            await _cancel(key)
            session = _Login()
            _sessions[key] = session
            session.task = asyncio.create_task(_login(dict(creds), session))
            with suppress(TimeoutError):
                await asyncio.wait_for(session.ready.wait(), _START_WAIT)
            return _result(session.status, session=session, locale=locale)
        if action in {"logout", "refresh"}:
            await _cancel(key)
        try:
            if action in {"logout", "refresh"}:
                await _command(creds, action)
            data = await _command(creds, "status")
            status = _auth_status(data)
            if action == "refresh" and status != "authorized":
                raise ValueError("agently refresh did not authorize")
            if action == "logout" and status != "idle":
                raise ValueError("agently logout did not clear authorization")
            return _result(
                status, error_key="login_expired" if status == "expired" else None, locale=locale
            )
        except FileNotFoundError:
            if disconnect:
                return _result("idle")
            return _result("error", error_key="cli_missing", locale=locale)
        except Exception:
            error_key = f"{action}_failed" if action in {"logout", "refresh"} else "login_failed"
            return _result("error", error_key=error_key, locale=locale)
