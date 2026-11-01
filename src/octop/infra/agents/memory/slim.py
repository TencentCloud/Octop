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
        self._remove_directories = False
        self._storage_states: dict[str, dict[str, Any]] = {}

    def status(self, agent_id: str) -> dict[str, Any] | None:
        if agent_id in self._chat_states:
            return {**self._chat_states[agent_id], "kind": "memory_slim"}
        return {**self.state, "kind": "memory_slim"} if agent_id == self.agent_id else None

    @property
    def busy(self) -> bool:
        return self.task is not None and not self.task.done()

    def storage_status(self, agent_id: str) -> dict[str, Any]:
        """Keep each expert's last page job visible across navigation."""
        return {"busy": self.busy, "job": self._storage_states.get(agent_id)}

    def _storage_target(self, agent_id: str, locale: str) -> tuple[Any, str | None]:
        from octop.infra.agents.memory.storage import sqlite_store_is_shared

        kind = self._memory_kind(agent_id, locale)
        memory = self._agent_manager.get_agent(agent_id)._memory_runtime.memory
        assert memory is not None  # Validated by _memory_kind without yielding.
        if kind == "postgres":
            from octop.infra.agents.memory.thread_cleanup import memory_namespace

            namespace = memory.backend._ns
            if namespace != memory_namespace(agent_id):
                raise ValueError(tr("memory_storage.namespace_mismatch", locale))
            # Agent IDs differing only by case/punctuation can normalize to the
            # same memory namespace. Refuse rather than touching shared data.
            if any(
                row.agent_id != agent_id and memory_namespace(row.agent_id) == namespace
                for row in self._agent_manager._repos.agent_repo.list_all(include_disabled=True)
            ):
                return memory, "shared_namespace"
            return memory, None
        if sqlite_store_is_shared(self._agent_manager, agent_id, memory):
            return memory, "shared_sqlite"
        try:
            self._require_memory(agent_id, locale)
        except ValueError:
            return memory, "incompatible"
        return memory, None

    async def inspect_storage(self, agent_id: str, *, locale: str = "en") -> dict[str, Any]:
        from functools import partial

        from octop.infra.agents.memory.storage import inspect_storage

        self._check_ready(locale)
        memory, blocked_reason = self._storage_target(agent_id, locale)
        return await asyncio.get_running_loop().run_in_executor(
            None, partial(inspect_storage, memory, blocked_reason=blocked_reason)
        )

    def start_current(self, agent_id: str, owner_id: int, *, locale: str = "en") -> dict[str, Any]:
        """Page action: this expert's SQLite file or PostgreSQL namespace."""
        self._check_ready(locale)
        self._assert_owner(agent_id, owner_id, locale)
        _memory, reason = self._storage_target(agent_id, locale)
        if reason:
            raise ValueError(tr(f"memory_storage.{reason}", locale))
        self._chat_owner = None
        self._chat_states = {}
        self.agent_id = agent_id
        self.state = {
            "job_id": uuid.uuid4().hex,
            "scope": "agent",
            "backend": self._memory_kind(agent_id, locale),
            "phase": "waiting",
            "started_at": time.time(),
            "updated_at": time.time(),
        }
        self._storage_states[agent_id] = self.state
        self.task = asyncio.create_task(
            self._run(agent_id, locale, owner_id=owner_id, current_only=True)
        )
        return self.storage_status(agent_id)

    async def backups(self, agent_id: str, *, locale: str = "en") -> list[dict[str, Any]]:
        from octop.infra.agents.memory.sqlite_restore import list_backups

        memory, reason = self._storage_target(agent_id, locale)
        if self._memory_kind(agent_id, locale) != "sqlite" or reason:
            return []
        path = Path(memory.backend._db_path).expanduser().resolve(strict=True)
        return await asyncio.to_thread(list_backups, path)

    async def delete_backup(
        self, agent_id: str, owner_id: int, backup_id: str, *, locale: str = "en"
    ) -> None:
        from octop.infra.agents.memory.sqlite_restore import delete_backup

        self._check_ready(locale)
        self._assert_owner(agent_id, owner_id, locale)
        memory, reason = self._storage_target(agent_id, locale)
        if self._memory_kind(agent_id, locale) != "sqlite" or reason:
            raise ValueError(tr("memory_storage.delete_sqlite_only", locale))
        path = Path(memory.backend._db_path).expanduser().resolve(strict=True)
        # Reserve the same coordinator slot as maintenance/restore before yielding.
        # Shield keeps deletion tracked even if the HTTP client disconnects.
        self.task = asyncio.create_task(asyncio.to_thread(delete_backup, path, backup_id, locale))
        await asyncio.shield(self.task)

    def start_restore(
        self, agent_id: str, owner_id: int, backup_id: str, *, locale: str = "en"
    ) -> dict[str, Any]:
        from octop.infra.agents.memory.sqlite_restore import backup_path

        self._check_ready(locale)
        self._assert_owner(agent_id, owner_id, locale)
        memory, reason = self._storage_target(agent_id, locale)
        if self._memory_kind(agent_id, locale) != "sqlite" or reason:
            raise ValueError(tr("memory_storage.restore_sqlite_only", locale))
        path = Path(memory.backend._db_path).expanduser().resolve(strict=True)
        backup_path(path, backup_id, locale)
        self._chat_owner = None
        self._chat_states = {}
        self.agent_id = agent_id
        self.state = {
            "job_id": uuid.uuid4().hex,
            "scope": "agent",
            "backend": "sqlite",
            "operation": "restore",
            "phase": "waiting",
            "started_at": time.time(),
            "updated_at": time.time(),
            "restored_backup_id": backup_id,
        }
        self._storage_states[agent_id] = self.state
        self.task = asyncio.create_task(
            self._run_restore(agent_id, owner_id, path, backup_id, locale)
        )
        return self.storage_status(agent_id)

    async def _run_restore(
        self, agent_id: str, owner_id: int, path: Path, backup_id: str, locale: str
    ) -> None:
        from octop.infra.agents.memory.sqlite_restore import restore_sqlite

        registry = self._agent_manager
        reserved = False
        try:
            deadline = time.monotonic() + 120
            while agent_id in registry._reclaim_holds or not registry.try_begin_history_backfill(
                agent_id
            ):
                if time.monotonic() >= deadline:
                    raise ValueError(tr("memory_slim.wait_timeout", locale))
                await asyncio.sleep(0.25)
            reserved = True
            self._assert_owner(agent_id, owner_id, locale)
            memory, reason = self._storage_target(agent_id, locale)
            if reason or Path(memory.backend._db_path).expanduser().resolve(strict=True) != path:
                raise ValueError(tr("memory_storage.restore_changed", locale))
            self._update({"phase": "draining"})
            loop = asyncio.get_running_loop()

            def progress(values: dict[str, Any]) -> None:
                loop.call_soon_threadsafe(self._update, values)

            def operation() -> dict[str, Any]:
                from octop.infra.agents.memory.storage import sqlite_store_is_shared

                self._assert_owner(agent_id, owner_id, locale)
                if sqlite_store_is_shared(registry, agent_id, memory):
                    raise ValueError(tr("memory_storage.shared_sqlite", locale))
                result = restore_sqlite(
                    path, str(memory.backend._ns), backup_id, locale=locale, progress=progress
                )
                progress({"phase": "restarting", "report": result})
                return result

            result = await registry.restore_memory_store(agent_id, memory, operation, locale=locale)
            self._update({"phase": "done", "report": result})
        except asyncio.CancelledError:
            self._update({"phase": "failed", "error": tr("memory_slim.interrupted", locale)})
            raise
        except Exception as exc:
            logger.exception("Memory restore failed for agent=%s", agent_id)
            self._update(
                {
                    "phase": "failed",
                    "error": tr("memory_slim.error_detail", locale, detail=str(exc)),
                }
            )
        finally:
            if reserved:
                registry.end_history_backfill(agent_id)

    def list_agents(self, *, locale: str = "en") -> list[dict[str, str]]:
        """List compatible live agents without opening another memory connection."""
        if self._closing:
            raise ValueError(tr("memory_slim.not_ready", locale))
        self._require_live_support(locale)
        registry = self._agent_manager
        result = []
        for row in registry.list_rows():
            try:
                self._memory_kind(row.agent_id, locale)
            except ValueError:
                continue
            result.append({"agent_id": row.agent_id, "name": row.name})
        return result

    @staticmethod
    def _require_live_support(locale: str) -> None:
        from octop_memory.application import checkpoint_maintenance

        if not callable(getattr(checkpoint_maintenance, "slim_live_checkpoints", None)):
            raise ValueError(tr("memory_slim.upgrade", locale))

    def _require_memory(self, agent_id: str, locale: str) -> Any:
        from octop_memory.storage.backends.sqlite import SqliteMemoryBackend
        from octop_memory.storage.backends.sqlite_checkpoint import CompactSqliteSaver

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

    def _memory_kind(self, agent_id: str, locale: str) -> str:
        """``sqlite`` or ``postgres`` when the live agent has a memory store."""
        try:
            agent = self._agent_manager.get_agent(agent_id)
        except OctopError as exc:
            raise ValueError(tr("memory_slim.agent_not_running", locale)) from exc
        memory = getattr(getattr(agent, "_memory_runtime", None), "memory", None)
        if memory is None:
            raise ValueError(tr("memory_slim.memory_disabled", locale))
        backend = type(getattr(memory, "backend", None)).__name__
        if backend == "SqliteMemoryBackend":
            return "sqlite"
        if backend == "PostgresMemoryBackend":
            return "postgres"
        raise ValueError(tr("memory_slim.backend_unsupported", locale, backend=backend))

    def _check_ready(self, locale: str) -> None:
        if self.task is not None and not self.task.done():
            raise ValueError(tr("memory_slim.busy", locale))
        if self._closing:
            raise ValueError(tr("memory_slim.not_ready", locale))

    def orphan_directories(self) -> list[str]:
        """Host directories whose names match no current agent. Does not delete."""
        from octop.infra.agents.memory.thread_cleanup import list_deleted_agent_dirs

        repos = getattr(self._agent_manager, "_repos", None)
        paths = getattr(self._agent_manager, "_paths", None)
        if repos is None or paths is None:
            return []
        live_ids = {str(row.agent_id) for row in repos.agent_repo.list_all(include_disabled=True)}
        return [str(path) for path in list_deleted_agent_dirs(paths, live_ids)]

    def start(self, agent_id: str, *, locale: str = "en", remove_directories: bool = False) -> None:
        self._check_ready(locale)
        self._chat_owner = None
        self._chat_states = {}
        self._remove_directories = remove_directories
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
            self._memory_kind(agent_id, locale)
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
        self,
        agent_id: str,
        user_id: int,
        *,
        all_agents: bool = False,
        locale: str = "en",
        remove_directories: bool = False,
    ) -> int:
        """Start a host-owned queue limited to the authenticated user's own agents."""
        self._check_ready(locale)
        targets = [
            row["agent_id"]
            for row in self.preview_chat(agent_id, user_id, all_agents=all_agents, locale=locale)
        ]
        self._chat_owner = user_id
        self._remove_directories = remove_directories
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

    async def _run(
        self, agent_id: str, locale: str, *, owner_id: int | None = None, current_only: bool = False
    ) -> None:
        registry = self._agent_manager
        reserved = False
        try:
            deadline = time.monotonic() + 120
            while not registry.try_begin_history_backfill(agent_id):
                if time.monotonic() >= deadline:
                    raise ValueError(tr("memory_slim.wait_timeout", locale))
                await asyncio.sleep(0.25)
            reserved = True
            if owner_id is not None:
                self._assert_owner(agent_id, owner_id, locale)
            from octop.infra.agents.memory.thread_cleanup import (  # noqa: PLC0415
                sweep_deleted_residuals,
            )

            sweep: dict[str, Any] = {}
            if current_only:
                # Recheck after waiting: ownership/backend/config may have changed.
                _memory, reason = self._storage_target(agent_id, locale)
                if reason:
                    raise ValueError(tr(f"memory_storage.{reason}", locale))
            else:
                sweep = await asyncio.to_thread(
                    sweep_deleted_residuals,
                    registry,
                    remove_directories=self._remove_directories,
                )
                self._update({"phase": "sweeping", "sweep": sweep})
            if self._memory_kind(agent_id, locale) == "postgres":
                if current_only:
                    await self._run_postgres(_memory, locale)
                else:
                    self._update({"phase": "done", "sweep": sweep, "dedup_skipped": True})
                return
            from octop_memory.application import checkpoint_maintenance

            slim_live_checkpoints = getattr(checkpoint_maintenance, "slim_live_checkpoints", None)
            if not callable(slim_live_checkpoints):
                raise ValueError(tr("memory_slim.upgrade", locale))

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
            def maintain() -> dict[str, Any]:
                from octop.infra.agents.memory.storage import inspect_storage

                before = inspect_storage(memory, blocked_reason=None) if current_only else None
                if before and not before["maintenance_supported"]:
                    raise ValueError(tr("memory_storage.shared_sqlite", locale))
                result: dict[str, Any] = slim_live_checkpoints(
                    path, backup=backup, progress=progress
                )
                if before is not None:
                    result["inspection_before"] = before
                    result["inspection_after"] = inspect_storage(memory, blocked_reason=None)
                return result

            worker = asyncio.create_task(asyncio.to_thread(maintain))
            try:
                report = await asyncio.shield(worker)
            except asyncio.CancelledError:
                await worker
                raise
            self._update({"phase": "done", "report": report, "sweep": sweep})
        except asyncio.CancelledError:
            self._update({"phase": "failed", "error": tr("memory_slim.interrupted", locale)})
            raise
        except Exception as exc:
            if self.state.get("backup_path") and not Path(self.state["backup_path"]).is_file():
                self.state.pop("backup_path", None)
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

    async def _run_postgres(self, memory: Any, locale: str) -> None:
        from functools import partial

        from octop.infra.agents.memory.postgres_storage import maintain_postgres_storage

        backup = (
            self._agent_manager._paths.root
            / "backups"
            / "memory-maintenance"
            / f"{self.state['job_id']}.jsonl"
        )
        loop = asyncio.get_running_loop()

        def progress(values: dict[str, Any]) -> None:
            loop.call_soon_threadsafe(self._update, values)

        worker = loop.run_in_executor(
            None,
            partial(
                maintain_postgres_storage,
                memory.backend,
                backup=backup,
                progress=progress,
                locale=locale,
            ),
        )
        try:
            report = await asyncio.shield(worker)
        except asyncio.CancelledError:
            await worker
            raise
        self._update({"phase": "done", "report": report, "scanned": report["total_deleted"]})

    async def close(self) -> None:
        self._closing = True
        if self.task is not None and not self.task.done():
            if self.state.get("phase") == "waiting":
                self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task
