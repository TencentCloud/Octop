"""Direct (non-ACP) driver for Code Console coding CLIs.

Octop's Code Console used to delegate turns to ``harness_agent.acp``. That
layer drops ``agent_thought_chunk`` updates, so the reasoning chain never
reached the UI. This module talks to the very same CLIs (``opencode acp``,
``codebuddy --acp``, ...) over stdio JSON-RPC **directly**, and forwards every
session update — including thoughts — to the caller.

The ACP integration itself is untouched and remains available for agents;
this is only the Code Console transport (selectable via ``OCTOP_CODE_DRIVER``).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = 1
_START_TIMEOUT = 120.0
_READ_TIMEOUT = 600.0

PermissionHandler = Callable[[dict[str, Any]], Awaitable[str]]


class DirectAgentError(RuntimeError):
    """Raised when the CLI subprocess cannot be driven."""


def _text_of(content: Any) -> str:
    """Extract plain text from an ACP content block (or list of blocks)."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(_text_of(item) for item in content)
    if isinstance(content, dict):
        if content.get("type") == "text":
            return str(content.get("text") or "")
        # nested content (e.g. {"type":"content","content":{...}})
        for key in ("content", "text"):
            if key in content:
                return _text_of(content[key])
    text = getattr(content, "text", None)
    if isinstance(text, str):
        return text
    return ""


class DirectAgent:
    """Long-lived stdio JSON-RPC session with a coding CLI."""

    def __init__(
        self,
        *,
        command: list[str],
        cwd: str,
        env: dict[str, str] | None = None,
        runner: str = "",
    ) -> None:
        self.command = list(command)
        self.cwd = cwd or "/workspace"
        self.env = dict(env or {})
        self.runner = runner
        self.session_id: str | None = None
        self._proc: asyncio.subprocess.Process | None = None
        self._inbox: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._pending: dict[Any, asyncio.Future[dict[str, Any]]] = {}
        self._reader: asyncio.Task[None] | None = None
        self._err_reader: asyncio.Task[None] | None = None
        self._id = 0
        self._closed = False
        self._stderr_tail: list[str] = []

    async def _drain_stderr(self) -> None:
        """Keep the last stderr lines around for diagnostics."""
        proc = self._proc
        if proc is None or proc.stderr is None:
            return
        try:
            while True:
                line = await proc.stderr.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").rstrip()
                if text:
                    self._stderr_tail.append(text[:400])
                    if len(self._stderr_tail) > 40:
                        self._stderr_tail = self._stderr_tail[-40:]
                    logger.debug("direct agent stderr: %s", text[:200])
        except asyncio.CancelledError:
            return
        except Exception:  # noqa: BLE001
            return

    @property
    def stderr_tail(self) -> str:
        return "\n".join(self._stderr_tail[-15:])

    # ------------------------------------------------------------------ #
    # lifecycle
    # ------------------------------------------------------------------ #
    async def start(self) -> None:
        env = dict(os.environ)
        env.update(self.env)
        try:
            self._proc = await asyncio.create_subprocess_exec(
                *self.command,
                cwd=self.cwd,
                env=env,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise DirectAgentError(f"command not found: {self.command[0]}") from exc
        self._reader = asyncio.create_task(self._read_loop())
        self._err_reader = asyncio.create_task(self._drain_stderr())
        init = await self._request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "clientCapabilities": {},
                "clientInfo": {"name": "octop-code-console", "version": "1"},
            },
            timeout=_START_TIMEOUT,
        )
        logger.info(
            "direct agent %s initialized: %s",
            self.runner,
            json.dumps(init, ensure_ascii=False)[:200],
        )
        await self._notify("initialized", {})
        res = await self._request(
            "session/new",
            {"cwd": self.cwd, "mcpServers": []},
            timeout=_START_TIMEOUT,
        )
        self.session_id = str(res.get("sessionId") or res.get("session_id") or "")
        if not self.session_id:
            raise DirectAgentError("session/new returned no sessionId")

    async def close(self) -> None:
        self._closed = True
        for task in (self._reader, self._err_reader):
            if task is not None:
                task.cancel()
        self._reader = None
        self._err_reader = None
        proc = self._proc
        self._proc = None
        if proc is None:
            return
        try:
            if proc.returncode is None:
                proc.terminate()
        except ProcessLookupError:  # noqa: PERF203
            pass
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except (TimeoutError, ProcessLookupError):
            try:
                proc.kill()
            except ProcessLookupError:
                pass

    # ------------------------------------------------------------------ #
    # transport
    # ------------------------------------------------------------------ #
    async def _read_loop(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        try:
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                raw = line.decode("utf-8", errors="replace").strip()
                if not raw:
                    continue
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    logger.debug("direct agent non-JSON line: %s", raw[:200])
                    continue
                if not isinstance(msg, dict):
                    continue
                key = msg.get("id")
                if key is not None and ("result" in msg or "error" in msg):
                    fut = self._pending.pop(key, None)
                    if fut is not None and not fut.done():
                        fut.set_result(msg)
                    else:
                        # Late/unsolicited response (e.g. session/prompt result,
                        # which the turn loop consumes from the inbox).
                        await self._inbox.put(msg)
                    continue
                await self._inbox.put(msg)
        except asyncio.CancelledError:
            return
        except Exception:  # noqa: BLE001
            logger.exception("direct agent reader stopped")

    async def _send(self, obj: dict[str, Any]) -> None:
        proc = self._proc
        if proc is None or proc.stdin is None:
            raise DirectAgentError("agent process is not running")
        data = (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")
        proc.stdin.write(data)
        await proc.stdin.drain()

    async def _notify(self, method: str, params: dict[str, Any]) -> None:
        await self._send({"jsonrpc": "2.0", "method": method, "params": params})

    async def _request(
        self,
        method: str,
        params: dict[str, Any],
        *,
        timeout: float = _READ_TIMEOUT,
    ) -> dict[str, Any]:
        self._id += 1
        rid = self._id
        fut: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[rid] = fut
        await self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        try:
            msg = await asyncio.wait_for(fut, timeout=timeout)
        except TimeoutError:
            self._pending.pop(rid, None)
            tail = self.stderr_tail
            suffix = f" | stderr: {tail}" if tail else ""
            raise DirectAgentError(
                f"{method} timed out after {timeout:.0f}s{suffix}"
            ) from None
        if "error" in msg:
            err = msg["error"]
            raise DirectAgentError(f"{method} failed: {err}")
        result = msg.get("result")
        return result if isinstance(result, dict) else {}

    # ------------------------------------------------------------------ #
    # turns
    # ------------------------------------------------------------------ #
    async def prompt(
        self,
        text: str,
        *,
        on_event: Callable[[dict[str, Any]], Awaitable[None]],
        on_permission: PermissionHandler | None = None,
        prompt_id: Any = None,
        timeout: float = _READ_TIMEOUT,
    ) -> dict[str, Any]:
        """Run one turn, streaming events until the CLI answers the prompt."""
        if self.session_id is None:
            raise DirectAgentError("session not started")
        rid = prompt_id if prompt_id is not None else self._next_id()
        await self._send(
            {
                "jsonrpc": "2.0",
                "id": rid,
                "method": "session/prompt",
                "params": {
                    "sessionId": self.session_id,
                    "prompt": [{"type": "text", "text": text}],
                },
            }
        )
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise DirectAgentError("prompt timed out")
            try:
                msg = await asyncio.wait_for(self._inbox.get(), timeout=remaining)
            except TimeoutError:
                raise DirectAgentError("prompt timed out") from None

            method = str(msg.get("method") or "")
            if msg.get("id") is not None and method == "" and "params" in msg:
                # server -> client request (permissions, fs, terminals...)
                await self._handle_request(msg, on_permission)
                continue
            if method.startswith("session/update") or method == "session/update":
                for event in self._events_from_update(msg.get("params") or {}):
                    await on_event(event)
                continue
            if msg.get("id") == rid:
                if "error" in msg:
                    raise DirectAgentError(f"prompt failed: {msg['error']}")
                result = msg.get("result") or {}
                return result if isinstance(result, dict) else {}
            # anything else (unknown notification) is ignored on purpose

    async def _handle_request(
        self,
        msg: dict[str, Any],
        on_permission: PermissionHandler | None,
    ) -> None:
        method = str(msg.get("method") or "")
        rid = msg.get("id")
        params = msg.get("params") or {}
        if "request_permission" in method:
            if on_permission is None:
                # No handler: auto-pick the first non-deny option if present.
                option_id = _first_option_id(params)
            else:
                option_id = await on_permission(params)
            await self._send(
                {
                    "jsonrpc": "2.0",
                    "id": rid,
                    "result": {"outcome": {"outcome": "selected", "optionId": option_id}},
                }
            )
            return
        # Unsupported server request -> answer with a generic error.
        await self._send(
            {
                "jsonrpc": "2.0",
                "id": rid,
                "error": {"code": -32601, "message": f"unsupported request {method}"},
            }
        )

    async def cancel(self) -> None:
        if self.session_id is None:
            return
        try:
            await self._notify("session/cancel", {"sessionId": self.session_id})
        except Exception:  # noqa: BLE001
            logger.debug("cancel notification failed", exc_info=True)

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    # ------------------------------------------------------------------ #
    # event translation
    # ------------------------------------------------------------------ #
    def _events_from_update(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        update = params.get("update")
        if isinstance(update, str):
            # Some CLIs send the update payload flattened into params.
            update = params
        if not isinstance(update, dict):
            return []
        kind = str(update.get("sessionUpdate") or update.get("type") or "")
        if not kind:
            return []

        if kind == "agent_message_chunk":
            text = _text_of(update.get("content"))
            return [{"type": "text_delta", "text": text}] if text else []

        if kind == "agent_thought_chunk":
            text = _text_of(update.get("content"))
            return [{"type": "thought", "text": text}] if text else []

        if kind == "tool_call":
            return [
                {
                    "type": "tool_start",
                    "call_id": str(update.get("toolCallId") or update.get("id") or ""),
                    "title": str(update.get("title") or update.get("name") or "tool"),
                    "kind": str(update.get("kind") or "other"),
                    "detail": _tool_detail(update),
                    "status": str(update.get("status") or "pending"),
                }
            ]

        if kind == "tool_call_update":
            return [
                {
                    "type": "tool_update",
                    "call_id": str(update.get("toolCallId") or update.get("id") or ""),
                    "title": str(update.get("title") or "") or None,
                    "kind": str(update.get("kind") or "") or None,
                    "detail": _tool_detail(update),
                    "status": str(update.get("status") or ""),
                }
            ]

        if kind == "plan":
            return []
        return []


def _tool_detail(update: dict[str, Any]) -> str:
    raw = update.get("content") or update.get("rawInput") or update.get("rawOutput")
    text = _text_of(raw)
    if text:
        return text
    for key in ("title", "locations"):
        value = update.get(key)
        if value:
            return json.dumps(value, ensure_ascii=False)[:400]
    return ""


def _first_option_id(params: dict[str, Any]) -> str:
    options = params.get("options") or []
    for opt in options:
        if isinstance(opt, dict):
            kind = str(opt.get("kind") or "")
            if kind != "reject":
                return str(opt.get("optionId") or opt.get("id") or "")
    if options and isinstance(options[0], dict):
        return str(options[0].get("optionId") or options[0].get("id") or "")
    return ""


def permission_view(params: dict[str, Any]) -> dict[str, Any]:
    """Normalise a ``session/request_permission`` request for the UI."""
    tool = params.get("toolCall") or params.get("tool_call") or {}
    if not isinstance(tool, dict):
        tool = {}
    options: list[dict[str, str]] = []
    for opt in params.get("options") or []:
        if isinstance(opt, dict):
            options.append(
                {
                    "id": str(opt.get("optionId") or opt.get("id") or ""),
                    "name": str(opt.get("name") or opt.get("label") or opt.get("optionId") or ""),
                    "kind": str(opt.get("kind") or ""),
                }
            )
    return {
        "tool_name": str(tool.get("title") or tool.get("name") or tool.get("toolName") or ""),
        "tool_kind": str(tool.get("kind") or ""),
        "title": str(params.get("title") or tool.get("title") or ""),
        "detail": str(params.get("description") or _tool_detail(tool) or ""),
        "options": options,
    }


def new_request_id() -> str:
    return f"dreq_{uuid.uuid4().hex[:12]}"
