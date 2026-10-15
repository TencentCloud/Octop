"""Durable generation tracking, independent of model and brief MCP sessions."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Any

from octop.infra.connectors.open_design import _new_client, connection_spec, result_payload
from octop.infra.errors import ErrorCode, OctopError

_LOG = logging.getLogger(__name__)

_TERMINAL = {"succeeded", "failed", "canceled", "cancelled"}


class OpenDesignTasks:
    def __init__(self, service: Any, repos: Any) -> None:
        self.service, self.repos = service, repos
        self._worker: asyncio.Task[None] | None = None
        self._wake = asyncio.Event()
        self._limit = asyncio.Semaphore(4)
        self._instance_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._subscribers: dict[tuple[int, str, str], set[asyncio.Queue[None]]] = defaultdict(set)

    async def start(self) -> None:
        if self._worker is None:
            await asyncio.to_thread(self._import_legacy)
            self._worker = asyncio.create_task(self._run(), name="open-design-tasks")

    async def stop(self) -> None:
        if self._worker:
            self._worker.cancel()
            with suppress(asyncio.CancelledError):
                await self._worker
            self._worker = None

    def _import_legacy(self) -> None:
        for key, value in self.repos.settings_repo.list_prefix("open_design:task:"):
            try:
                _, _, user, instance, agent, thread = key.split(":", 5)
                state = json.loads(value)
                if not state.get("project") or not state.get("requestId"):
                    continue
                owner = self.repos.thread_repo.get(thread)
                if owner is None or owner.user_id != int(user) or owner.agent_id != agent:
                    continue
                existing = self.repos.open_design_task_repo.list_thread(int(user), agent, thread)
                if any(
                    r["request_id"] == state["requestId"] and r["instance_id"] == instance
                    for r in existing
                ):
                    continue
                self.repos.open_design_task_repo.record(
                    user_id=int(user),
                    instance_id=instance,
                    agent_id=agent,
                    thread_id=thread,
                    state=state,
                )
            except (ValueError, TypeError):
                continue

    async def list_authorized(
        self, user_id: int, agent_id: str, thread_id: str
    ) -> list[dict[str, Any]]:
        thread = await asyncio.to_thread(self.repos.thread_repo.get, thread_id)
        agent = await asyncio.to_thread(self.repos.agent_repo.get, agent_id)
        if (
            thread is None
            or thread.user_id != user_id
            or thread.agent_id != agent_id
            or agent is None
            or (agent.user_id != user_id and not agent.is_shared and agent.user_id is not None)
        ):
            raise OctopError.localized(ErrorCode.NOT_FOUND)
        rows = await asyncio.to_thread(
            self.repos.open_design_task_repo.list_thread, user_id, agent_id, thread_id
        )
        anchors = await asyncio.to_thread(self._turn_anchors, thread_id, rows)
        return [
            {
                "anchor_message_ids": anchors.get(r["task_id"], []),
                **{
                    k: r[k]
                    for k in (
                        "task_id",
                        "instance_id",
                        "project",
                        "run_id",
                        "status",
                        "last_error",
                        "revision",
                        "created_at",
                        "updated_at",
                    )
                },
                "result": {
                    k: v for k, v in json.loads(r["result_json"]).items() if k != "_originUserSeq"
                },
            }
            for r in rows
        ]

    def _turn_anchors(self, thread_id: str, tasks: list[dict[str, Any]]) -> dict[str, list[str]]:
        anchors: dict[str, list[str]] = {}
        for task in tasks:
            origin = json.loads(task["result_json"]).get("_originUserSeq")
            if isinstance(origin, int) and origin > 0:
                anchors[task["task_id"]] = self.repos.thread_message_repo.assistant_ids_after_user(
                    thread_id, origin
                )
                continue
            if not task["run_id"]:
                continue
            for row in self.repos.thread_message_repo.tool_rows_containing(
                thread_id, task["run_id"]
            ):
                data = json.loads(row.message_json).get("data", {})
                name = str(data.get("name") or "")
                if name != "start_run" and not name.endswith("_start_run"):
                    continue
                content = data.get("content")
                blocks = content if isinstance(content, list) else [content]
                matched = False
                for block in blocks:
                    text = block.get("text") if isinstance(block, dict) else block
                    if not isinstance(text, str):
                        continue
                    try:
                        payload = json.loads(text)
                    except ValueError:
                        continue
                    if isinstance(payload, dict) and payload.get("runId") == task["run_id"]:
                        matched = True
                        break
                artifact = data.get("artifact")
                if isinstance(artifact, dict):
                    payload = artifact.get("structured_content", artifact)
                    matched = matched or (
                        isinstance(payload, dict) and payload.get("runId") == task["run_id"]
                    )
                if matched:
                    anchors[task["task_id"]] = self.repos.thread_message_repo.assistant_ids_in_turn(
                        thread_id, row.seq
                    )
                    break
        return anchors

    async def refresh_authorized(
        self, user_id: int, agent_id: str, thread_id: str, task_id: str
    ) -> None:
        rows = await self.list_authorized(user_id, agent_id, thread_id)
        if not any(r["task_id"] == task_id for r in rows):
            raise OctopError.localized(ErrorCode.NOT_FOUND)
        row = await asyncio.to_thread(self.repos.open_design_task_repo.get, task_id)
        if row is not None:
            await self.refresh(row, force=True)

    async def register(
        self,
        user_id: int,
        instance_id: str,
        agent_id: str,
        thread_id: str,
        state: dict[str, Any],
        payload: dict[str, Any] | None = None,
    ) -> None:
        if state.get("status") == "submitting":
            state = {
                **state,
                "origin_user_seq": await asyncio.to_thread(
                    self.repos.thread_message_repo.latest_user_seq, thread_id
                ),
            }
        row = await asyncio.to_thread(
            self.repos.open_design_task_repo.record,
            user_id=user_id,
            instance_id=instance_id,
            agent_id=agent_id,
            thread_id=thread_id,
            state=state,
        )
        if payload:
            await self._save(row, payload)
        self._notify(row)
        self._wake.set()

    async def reconcile(
        self, user_id: int, instance_id: str, agent_id: str, thread_id: str, state: dict[str, Any]
    ) -> None:
        rows = await asyncio.to_thread(
            self.repos.open_design_task_repo.list_thread, user_id, agent_id, thread_id
        )
        for row in rows:
            if row["instance_id"] == instance_id and row["request_id"] == state.get("requestId"):
                state["status"] = row["status"]
                if row["run_id"]:
                    state["runId"] = row["run_id"]
                return

    def _notify(self, row: dict[str, Any]) -> None:
        for queue in tuple(
            self._subscribers.get((row["user_id"], row["agent_id"], row["thread_id"]), ())
        ):
            if queue.empty():
                queue.put_nowait(None)

    @asynccontextmanager
    async def watch(
        self, user_id: int, agent_id: str, thread_id: str
    ) -> AsyncIterator[asyncio.Queue[None]]:
        key = (user_id, agent_id, thread_id)
        queue: asyncio.Queue[None] = asyncio.Queue(maxsize=1)
        self._subscribers[key].add(queue)
        try:
            yield queue
        finally:
            self._subscribers[key].discard(queue)
            if not self._subscribers[key]:
                del self._subscribers[key]

    async def _save(self, row: dict[str, Any], payload: dict[str, Any]) -> None:
        status = str(payload.get("status") or "queued")
        if status not in _TERMINAL | {"queued", "running"}:
            status = "running"
        result = {
            k: payload[k]
            for k in ("previewUrl", "agentMessage", "artifactRef", "entryFile", "project")
            if k in payload
        }
        result["upstreamStatus"] = str(payload.get("status") or "queued")
        origin = json.loads(row["result_json"]).get("_originUserSeq")
        if origin is not None:
            result["_originUserSeq"] = origin
        if isinstance(result.get("agentMessage"), str):
            result["agentMessage"] = result["agentMessage"][:8000]
        error = str(payload.get("error") or "")[:2000] or None
        await asyncio.to_thread(
            self.repos.open_design_task_repo.update,
            row["task_id"],
            status=status,
            result=result,
            error=error,
            failures=0,
            next_check=int(time.time()) + 30,
        )
        self._notify(row)

    async def refresh(self, row: dict[str, Any], *, force: bool = False) -> None:
        async with self._instance_locks[row["instance_id"]], self._limit:
            latest = await asyncio.to_thread(self.repos.open_design_task_repo.get, row["task_id"])
            if (
                latest is None
                or (latest["status"] in _TERMINAL and not force)
                or not latest["run_id"]
            ):
                return
            row = latest
            visible = await asyncio.to_thread(
                self.service.list_user_instances,
                row["user_id"],
                active_only=True,
                with_credentials=True,
                include_shared=True,
            )
            agent = await asyncio.to_thread(self.repos.agent_repo.get, row["agent_id"])
            user = await asyncio.to_thread(self.repos.user_repo.get, row["user_id"])
            if (
                user is None
                or user.disabled
                or agent is None
                or (agent.user_id not in (None, row["user_id"]) and not agent.is_shared)
                or not any(
                    i.instance_id == row["instance_id"] and i.kind == "open-design" for i in visible
                )
            ):
                await asyncio.to_thread(
                    self.repos.open_design_task_repo.update,
                    row["task_id"],
                    status="paused",
                    result=json.loads(row["result_json"]),
                    error="access_revoked",
                    failures=0,
                    next_check=0,
                )
                self._notify(row)
                return
            try:
                creds = await asyncio.to_thread(self.service.decrypt, row["instance_id"])
                async with asyncio.timeout(25), _new_client(connection_spec(creds)) as client:
                    response = await client.call_tool("get_run", {"runId": row["run_id"]})
                if response.isError:
                    raise ValueError("upstream unavailable")
                payload = result_payload(response)
                # Avoid persisting a launcher credential if an upstream error echoes it.
                for value in creds.get("env", {}).values():
                    if len(value) >= 8 and payload.get("error"):
                        payload["error"] = str(payload["error"]).replace(value, "[redacted]")
                await self._save(row, payload)
            except (Exception, BaseExceptionGroup):
                failures = min(int(latest["failures"]) + 1, 4)
                await asyncio.to_thread(
                    self.repos.open_design_task_repo.update,
                    row["task_id"],
                    status=latest["status"] if latest["status"] in _TERMINAL else "unavailable",
                    result=json.loads(latest["result_json"]),
                    error="connection_unavailable",
                    failures=failures,
                    next_check=int(time.time()) + min(30 * 2**failures, 120),
                )
                self._notify(row)

    async def _run(self) -> None:
        while True:
            try:
                rows = await asyncio.to_thread(
                    self.repos.open_design_task_repo.due, int(time.time())
                )
                results = await asyncio.gather(
                    *(self.refresh(row) for row in rows), return_exceptions=True
                )
                if any(isinstance(result, BaseException) for result in results):
                    _LOG.warning("OpenDesign task refresh failed; retrying on the next scan")
            except Exception:
                _LOG.warning("OpenDesign task scan failed; retrying on the next scan")
            self._wake.clear()
            with suppress(TimeoutError):
                await asyncio.wait_for(self._wake.wait(), 5)
