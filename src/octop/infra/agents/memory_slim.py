"""Manual checkpoint maintenance owned by the running host, not a second runtime."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, Any

from octop.i18n import tr
from octop.infra.errors import OctopError

if TYPE_CHECKING:
    from octop.infra.agents.manager import AgentManager

logger = logging.getLogger(__name__)


class MemorySlimCoordinator:
    """One maintenance job per host; graph admission uses the existing idle reservation."""

    def __init__(self, agent_manager: AgentManager) -> None:
        self._agent_manager = agent_manager
        self.task: asyncio.Task[None] | None = None
        self.agent_id: str | None = None
        self.state: dict[str, Any] = {}
        self._chat_owner: int | None = None
        self._chat_states: dict[str, dict[str, Any]] = {}
        self._chat_phase = "idle"
        self._closing = False

    def status(self, agent_id: str) -> dict[str, Any] | None:
        if agent_id in self._chat_states:
            return {**self._chat_states[agent_id], "kind": "memory_slim"}
        return {**self.state, "kind": "memory_slim"} if agent_id == self.agent_id else None

    def list_agents(self, *, locale: str = "en") -> list[dict[str, str]]:
        """List compatible live agents without opening another memory connection."""
        if self._closing:
            raise ValueError(tr("memory_slim.not_ready", locale))
        self._require_live_support(locale)
        registry = self._agent_manager
        result = []
        for row in registry.list_rows():
            try:
                self._require_memory(row.agent_id, locale)
            except ValueError:
                continue
            result.append({"agent_id": row.agent_id, "name": row.name})
        return result

    @staticmethod
    def _require_live_support(locale: str) -> None:
        from harness_memory.application import checkpoint_maintenance

        if not callable(getattr(checkpoint_maintenance, "slim_live_checkpoints", None)):
            raise ValueError(tr("memory_slim.upgrade", locale))

    def _require_memory(self, agent_id: str, locale: str) -> Any:
        from harness_memory.storage.backends.sqlite import SqliteMemoryBackend
        from harness_memory.storage.backends.sqlite_checkpoint import CompactSqliteSaver

        try:
            agent = self._agent_manager.get_agent(agent_id)
        except OctopError as exc:
            raise ValueError(tr("memory_slim.agent_not_running", locale)) from exc
        memory = getattr(getattr(agent, "_memory_runtime", None), "memory", None)
        if memory is None:
            raise ValueError(tr("memory_slim.memory_disabled", locale))
        if not isinstance(memory.backend, SqliteMemoryBackend):
            backend = type(memory.backend).__name__
            if backend == "PostgresMemoryBackend":
                raise ValueError(
                    tr("memory_slim.postgres_unsupported", locale, backend="PostgreSQL")
                )
            raise ValueError(tr("memory_slim.backend_unsupported", locale, backend=backend))
        saver = getattr(memory, "_checkpointer", None)
        if not isinstance(saver, CompactSqliteSaver) or not hasattr(saver.codec, "with_connection"):
            raise ValueError(tr("memory_slim.incompatible", locale))
        self._require_live_support(locale)
        return memory

    def _check_ready(self, locale: str) -> None:
        if self.task is not None and not self.task.done():
            raise ValueError(tr("memory_slim.busy", locale))
        if self._closing:
            raise ValueError(tr("memory_slim.not_ready", locale))

    def start(self, agent_id: str, *, locale: str = "en") -> None:
        self._check_ready(locale)
        self._chat_owner = None
        self._chat_states = {}
        self.agent_id = agent_id
        self.state = {"phase": "waiting", "started_at": time.time(), "updated_at": time.time()}
        self.task = asyncio.create_task(self._run(agent_id, locale))

    def _assert_owner(self, agent_id: str, user_id: int, locale: str) -> None:
        if self._closing:
            raise ValueError(tr("memory_slim.not_ready", locale))
        row = self._agent_manager.get_row(agent_id)
        if user_id <= 0 or row is None or row.user_id != user_id:
            raise ValueError(tr("memory_slim.forbidden", locale))

    def preview_chat(
        self, agent_id: str, user_id: int, *, all_agents: bool = False, locale: str = "en"
    ) -> list[dict[str, str]]:
        """List the user's eligible targets without scheduling or touching memory files."""
        if self._closing:
            raise ValueError(tr("memory_slim.not_ready", locale))
        registry = self._agent_manager
        if user_id <= 0:
            raise ValueError(tr("memory_slim.forbidden", locale))
        if not all_agents:
            self._assert_owner(agent_id, user_id, locale)
            # Diagnose the requested agent before filtering the global list.
            self._require_memory(agent_id, locale)
        owned = {row.agent_id for row in registry.list_agents(user_id)}
        targets = [
            row
            for row in self.list_agents(locale=locale)
            if row["agent_id"] in owned and (all_agents or row["agent_id"] == agent_id)
        ]
        if not targets:
            raise ValueError(tr("memory_slim.no_agents", locale))
        return targets

    def start_chat(
        self, agent_id: str, user_id: int, *, all_agents: bool = False, locale: str = "en"
    ) -> int:
        """Start a host-owned queue limited to the authenticated user's own agents."""
        self._check_ready(locale)
        targets = [
            row["agent_id"]
            for row in self.preview_chat(agent_id, user_id, all_agents=all_agents, locale=locale)
        ]
        self._chat_owner = user_id
        self._chat_states = {aid: {"phase": "queued"} for aid in targets}
        self._chat_phase = "running"
        self.agent_id = targets[0]
        self.state = self._chat_states[targets[0]]
        self.task = asyncio.create_task(self._run_chat(targets, user_id, locale))
        return len(targets)

    def chat_status(self, agent_id: str, user_id: int, *, locale: str = "en") -> dict[str, Any]:
        if self._chat_owner == user_id:
            states = self._chat_states
            phase = self._chat_phase
        else:
            self._assert_owner(agent_id, user_id, locale)
            state = self.status(agent_id)
            states = {agent_id: state} if state is not None else {}
            phase = str(state["phase"]) if state is not None else "idle"
        # Ownership may have changed since the request was accepted.
        for aid in states:
            self._assert_owner(aid, user_id, locale)
        return {
            "phase": phase,
            "agents": [{"agent_id": aid, **state} for aid, state in states.items()],
        }

    async def _run_chat(self, targets: list[str], user_id: int, locale: str) -> None:
        try:
            for aid in targets:
                if self._closing:
                    break
                self.agent_id = aid
                self.state = self._chat_states[aid]
                self._update({"phase": "waiting", "started_at": time.time()})
                try:
                    self._assert_owner(aid, user_id, locale)
                except ValueError as exc:
                    self._update({"phase": "failed", "error": str(exc)})
                    break
                await self._run(aid, locale, owner_id=user_id)
                if self.state.get("phase") != "done":
                    break
            self._chat_phase = (
                "done"
                if all(s["phase"] == "done" for s in self._chat_states.values())
                else "failed"
            )
        finally:
            if self._chat_phase == "running":
                self._chat_phase = "failed"
            for state in self._chat_states.values():
                if state["phase"] == "queued":
                    state["phase"] = "skipped"

    def _update(self, values: dict[str, Any]) -> None:
        self.state.update(values, updated_at=time.time())

    async def _run(self, agent_id: str, locale: str, *, owner_id: int | None = None) -> None:
        registry = self._agent_manager
        reserved = False
        try:
            from harness_memory.application import checkpoint_maintenance

            slim_live_checkpoints = getattr(checkpoint_maintenance, "slim_live_checkpoints", None)
            if not callable(slim_live_checkpoints):
                raise ValueError(tr("memory_slim.upgrade", locale))

            deadline = time.monotonic() + 120
            while not registry.try_begin_history_backfill(agent_id):
                if time.monotonic() >= deadline:
                    raise ValueError(tr("memory_slim.wait_timeout", locale))
                await asyncio.sleep(0.25)
            reserved = True
            if owner_id is not None:
                self._assert_owner(agent_id, owner_id, locale)
            memory = self._require_memory(agent_id, locale)
            # Ask the live saver for its actual file; never infer a path from agent_id.
            # Its connection may be busy, so use the existing backend's configured path.
            path = Path(memory.backend._db_path).expanduser().resolve(strict=True)
            backup = path.with_name(f"{path.name}.before-slim.{uuid.uuid4().hex}.bak")
            self._update(
                {
                    "phase": "backing_up",
                    "backup_path": str(backup),
                    "file_bytes": path.stat().st_size,
                }
            )
            loop = asyncio.get_running_loop()

            def progress(values: dict[str, Any]) -> None:
                loop.call_soon_threadsafe(self._update, values)

            # Joining the worker before releasing the gate is essential: cancelling
            # an asyncio to_thread await does not stop the SQLite operation.
            worker = asyncio.create_task(
                asyncio.to_thread(slim_live_checkpoints, path, backup=backup, progress=progress)
            )
            try:
                report = await asyncio.shield(worker)
            except asyncio.CancelledError:
                await worker
                raise
            self._update({"phase": "done", "report": report})
        except asyncio.CancelledError:
            self._update({"phase": "failed", "error": tr("memory_slim.interrupted", locale)})
            raise
        except Exception as exc:
            logger.exception("Memory maintenance failed for agent=%s", agent_id)
            self._update(
                {
                    "phase": "failed",
                    "error": tr("memory_slim.error_detail", locale, detail=str(exc)),
                }
            )
        finally:
            if reserved:
                registry.end_history_backfill(agent_id)

    async def close(self) -> None:
        self._closing = True
        if self.task is not None and not self.task.done():
            if self.state.get("phase") == "waiting":
                self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task
