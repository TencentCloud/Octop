"""Instance-scoped CLI device authorization (Agent Mail, DingTalk), without exposing tokens."""

from __future__ import annotations

import asyncio
import json
import os
import re
import signal
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from functools import partial
from typing import Any, Literal, TypedDict
from urllib.parse import parse_qs, urlsplit
from weakref import WeakValueDictionary

from octop.i18n import tr
from octop.infra.connectors.gateway.adapters import agently_cli, dingtalk_cli
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


def _agently_status(payload: dict[str, Any]) -> AuthStatus:
    data = payload.get("data")
    if payload.get("ok") is not True or not isinstance(data, dict):
        raise ValueError("invalid agently auth response")
    if data.get("token_status") == "expired":
        return "expired"
    return "authorized" if data.get("logged_in") is True else "idle"


def _dingtalk_status(payload: dict[str, Any]) -> AuthStatus:
    if payload.get("success") is not True:
        raise ValueError("invalid dws auth response")
    return "authorized" if payload.get("authenticated") is True else "idle"


@dataclass(frozen=True)
class _Spec:
    binary: str
    prepare_env: Callable[[dict[str, Any]], dict[str, str]]
    login: tuple[str, ...]
    status: tuple[str, ...]
    parse_status: Callable[[dict[str, Any]], AuthStatus]
    logout: tuple[str, ...]
    # None: the CLI has no refresh command; its status call refreshes the grant.
    refresh: tuple[str, ...] | None
    hosts: tuple[str, ...]
    i18n: str


_SPECS: dict[str, _Spec] = {
    "agently-cli": _Spec(
        binary="agently-cli",
        prepare_env=agently_cli.prepare_env,
        login=("auth", "login"),
        status=("auth", "status"),
        parse_status=_agently_status,
        logout=("auth", "logout"),
        refresh=("auth", "refresh"),
        hosts=("agent.qq.com",),
        i18n="connector.agently",
    ),
    "dingtalk-cli": _Spec(
        binary="dws",
        prepare_env=dingtalk_cli.prepare_env,
        login=("auth", "login", "--device", "--no-browser"),
        status=("auth", "status", "--format", "json"),
        parse_status=_dingtalk_status,
        logout=("auth", "logout"),
        refresh=None,
        hosts=("login.dingtalk.com", "login.dingtalk.io"),
        i18n="connector.dingtalk",
    ),
}


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


def _key(kind: str, creds: dict[str, Any]) -> str:
    return str(
        PathLayout.from_env().connector_cli_instance_dir(kind, resolve_cli_config_key(creds))
    )


def _result(
    status: AuthStatus,
    *,
    session: _Login | None = None,
    error_key: str | None = None,
    locale: str = "en",
    i18n: str = "connector.agently",
) -> AuthResult:
    error_key = error_key or (session.error_key if session else None)
    return {
        "status": status,
        "verification_url": session.verification_url if session and status == "pending" else None,
        "user_code": session.user_code if session and status == "pending" else None,
        "expires_at": session.expires_at if session and status == "pending" else None,
        "error": tr(f"{i18n}.{error_key}", locale) if error_key else None,
    }


def _prepare(spec: _Spec, creds: dict[str, Any]) -> tuple[str, dict[str, str]]:
    try:
        binary = resolve_binary(spec.binary)
    except ValueError as exc:
        raise FileNotFoundError from exc
    return binary, spec.prepare_env(creds)


async def _spawn(
    spec: _Spec, creds: dict[str, Any], args: tuple[str, ...]
) -> asyncio.subprocess.Process:
    binary, env = await asyncio.get_running_loop().run_in_executor(
        None, partial(_prepare, spec, creds)
    )
    return await asyncio.create_subprocess_exec(
        binary,
        *args,
        env=env,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT if args == spec.login else asyncio.subprocess.PIPE,
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


async def _command(spec: _Spec, creds: dict[str, Any], args: tuple[str, ...]) -> str:
    process = await _spawn(spec, creds, args)
    try:
        output, _ = await asyncio.wait_for(process.communicate(), _COMMAND_TIMEOUT)
        if process.returncode != 0:
            raise ValueError("cli auth failed")
        return output.decode("utf-8", errors="replace")
    finally:
        await stop_process(process)


async def _status(spec: _Spec, creds: dict[str, Any]) -> AuthStatus:
    text = await _command(spec, creds, spec.status)
    # Status can include a diagnostic line before its JSON response.
    payload = json.loads(text[text.index("{") :])
    if not isinstance(payload, dict):
        raise ValueError("invalid cli auth response")
    return spec.parse_status(payload)


def _read_verification_url(line: str, session: _Login, hosts: tuple[str, ...]) -> None:
    for match in _URL.finditer(line):
        url = match.group().rstrip(",;)")
        parsed = urlsplit(url)
        host = parsed.hostname or ""
        query = parse_qs(parsed.query)
        if (
            any(host == h or host.endswith(f".{h}") for h in hosts)
            and not parsed.username
            and not parsed.password
            and not {"access_token", "refresh_token", "device_code"}.intersection(query)
        ):
            session.verification_url = url
            session.user_code = (query.get("user_code") or query.get("userCode") or [""])[0] or None
            session.ready.set()
            return


async def _login(spec: _Spec, creds: dict[str, Any], session: _Login) -> None:
    process: asyncio.subprocess.Process | None = None
    try:
        async with asyncio.timeout(_LOGIN_TIMEOUT):
            process = await _spawn(spec, creds, spec.login)
            assert process.stdout is not None
            while line := await process.stdout.readline():
                if session.verification_url is None:
                    _read_verification_url(
                        line.decode("utf-8", errors="replace"), session, spec.hosts
                    )
            if await process.wait() != 0 or await _status(spec, creds) != "authorized":
                raise ValueError("cli login did not authorize")
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


async def authorize(
    creds: dict[str, Any],
    action: AuthAction,
    *,
    kind: str = "agently-cli",
    locale: str = "en",
) -> AuthResult:
    spec = _SPECS[kind]
    result = partial(_result, locale=locale, i18n=spec.i18n)
    disconnect = action == "disconnect"
    if disconnect:
        action = "logout"
    key = _key(kind, creds)
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
            return result(session.status, session=session)
        if action == "start":
            await _cancel(key)
            session = _Login()
            _sessions[key] = session
            session.task = asyncio.create_task(_login(spec, dict(creds), session))
            with suppress(TimeoutError):
                await asyncio.wait_for(session.ready.wait(), _START_WAIT)
            return result(session.status, session=session)
        if action in {"logout", "refresh"}:
            await _cancel(key)
        try:
            if action == "logout":
                await _command(spec, creds, spec.logout)
            if action == "refresh" and spec.refresh is not None:
                await _command(spec, creds, spec.refresh)
            status = await _status(spec, creds)
            if action == "refresh" and status != "authorized":
                raise ValueError("cli refresh did not authorize")
            if action == "logout" and status != "idle":
                raise ValueError("cli logout did not clear authorization")
            return result(status, error_key="login_expired" if status == "expired" else None)
        except FileNotFoundError:
            if disconnect:
                return result("idle")
            return result("error", error_key="cli_missing")
        except Exception:
            error_key = f"{action}_failed" if action in {"logout", "refresh"} else "login_failed"
            return result("error", error_key=error_key)
