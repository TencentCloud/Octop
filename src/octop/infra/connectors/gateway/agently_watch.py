"""One official CLI long connection per mailbox; fan out only new message IDs."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from functools import partial
from typing import Any

from octop.infra.connectors.gateway.adapters.agently_cli import prepare_env
from octop.infra.connectors.gateway.agently_auth import stop_process
from octop.infra.connectors.gateway.cli_runner import resolve_binary

logger = logging.getLogger(__name__)
MailCallback = Callable[[str], Awaitable[None]]


@dataclass
class _Watch:
    callbacks: dict[str, MailCallback] = field(default_factory=dict)
    task: asyncio.Task[None] | None = None
    # Bounded replay suppression across reconnects during this subscription.
    seen: deque[str] = field(default_factory=lambda: deque(maxlen=4096))
    delivery_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class AgentlyWatchManager:
    def __init__(self) -> None:
        self._watches: dict[str, _Watch] = {}
        self._deliveries: set[asyncio.Task[None]] = set()

    def subscribe(
        self, instance_id: str, cron_id: str, creds: dict[str, Any], callback: MailCallback
    ) -> None:
        watch = self._watches.get(instance_id)
        if watch is None:
            watch = _Watch()
            self._watches[instance_id] = watch
            watch.task = asyncio.create_task(self._listen(instance_id, creds, watch))
        watch.callbacks[cron_id] = callback

    async def unsubscribe(self, cron_id: str) -> None:
        for instance_id, watch in list(self._watches.items()):
            watch.callbacks.pop(cron_id, None)
            if not watch.callbacks:
                del self._watches[instance_id]
                if watch.task is not None:
                    watch.task.cancel()
                    await asyncio.gather(watch.task, return_exceptions=True)

    async def close(self) -> None:
        watches, self._watches = self._watches, {}
        tasks = [w.task for w in watches.values() if w.task is not None]
        tasks.extend(self._deliveries)
        for watch in watches.values():
            watch.callbacks.clear()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def stop_instance(self, instance_id: str) -> None:
        watch = self._watches.get(instance_id)
        for cron_id in list(watch.callbacks if watch else []):
            await self.unsubscribe(cron_id)

    def has_job(self, cron_id: str) -> bool:
        return any(cron_id in watch.callbacks for watch in self._watches.values())

    async def _listen(self, instance_id: str, creds: dict[str, Any], watch: _Watch) -> None:
        while True:
            process = None
            try:
                loop = asyncio.get_running_loop()
                binary = await loop.run_in_executor(None, resolve_binary, "agently-cli")
                env = await loop.run_in_executor(None, partial(prepare_env, creds))
                process = await asyncio.create_subprocess_exec(
                    binary,
                    "message",
                    "+watch",
                    env=env,
                    stdin=asyncio.subprocess.DEVNULL,
                    stdout=asyncio.subprocess.PIPE,
                    # Terminal diagnostics can contain account data; never publish them.
                    stderr=asyncio.subprocess.DEVNULL,
                    start_new_session=os.name == "posix",
                    limit=4 * 1024 * 1024,
                )
                assert process.stdout is not None
                async for line in process.stdout:
                    await self._dispatch(watch, line)
                await process.wait()
                logger.warning(
                    "Agent Mail watch ended for %s (exit %s)", instance_id, process.returncode
                )
            except (OSError, ValueError):
                logger.warning("Agent Mail watch unavailable for %s", instance_id)
            finally:
                if process is not None:
                    await stop_process(process)
            # The CLI retries transient errors itself. Restart terminal failures slowly
            # so reauthorization/CLI installation recovers without model polling.
            await asyncio.sleep(60)

    async def _dispatch(self, watch: _Watch, line: bytes) -> None:
        try:
            payload = json.loads(line)
        except (ValueError, UnicodeError):
            return
        message = payload.get("message") if isinstance(payload, dict) else None
        message_id = message.get("message_id") if isinstance(message, dict) else None
        if not isinstance(message_id, str) or not re.fullmatch(
            r"msg_[A-Za-z0-9_-]{1,200}", message_id
        ):
            return
        if message_id in watch.seen:
            return
        watch.seen.append(message_id)
        # A running job may disable itself. Keep model execution separate from
        # the listener being cancelled, and serialize deliveries per mailbox.
        task = asyncio.create_task(self._deliver(watch, message_id, list(watch.callbacks.items())))
        self._deliveries.add(task)
        task.add_done_callback(self._deliveries.discard)

    async def _deliver(
        self, watch: _Watch, message_id: str, callbacks: list[tuple[str, MailCallback]]
    ) -> None:
        async with watch.delivery_lock:
            for cron_id, callback in callbacks:
                if watch.callbacks.get(cron_id) is not callback:
                    continue
                try:
                    await callback(message_id)
                except Exception:
                    logger.exception("Agent Mail event delivery failed for job %s", cron_id)
