"""Capture state messages and stream-only content, including interrupted turns."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage, message_to_dict

from octop.infra.gateway.process.history_projection import TurnHistoryTracker, _role, message_input
from octop.infra.history.service import HistoryArchive
from octop.infra.history.store import dumps
from octop.infra.trajectory.projector import _tool_result_fields


class RecordingTracker(TurnHistoryTracker):
    def __init__(self, archive: HistoryArchive, turn: dict[str, Any], seeds: list[Any]) -> None:
        super().__init__(seed_messages=seeds)
        self.archive = archive
        self.turn = turn
        self.paused = False
        self.failed = False
        self.decode_failed = bool(turn.get("error"))
        self._parts: list[dict[str, Any]] = []
        self._assistant: dict[str, Any] | None = None
        self._saved_signatures: dict[int, bytes] = {}
        self._write_failure: Exception | None = None
        self._identified = False
        self._sources: set[str] = set()
        restored = False
        if turn["format"] == "v2":
            self._parts = [
                doc["value"]
                for doc in archive.store.documents(turn["thread_id"], "message", turn_id=turn["id"])
            ]
            restored = bool(self._parts)
            if not self._parts:
                for seed in seeds:
                    item = message_input(seed)
                    if item is not None:
                        self._parts.append(json.loads(item.message_json))
            for wire in self._parts:
                extra = wire["data"].get("additional_kwargs", {})
                if extra.get("history_source"):
                    self._sources.add(extra["history_source"])
                if extra.get("history_stream_id"):
                    self._identified = True
        self._indices = {id(part): index for index, part in enumerate(self._parts)}
        self._dirty: set[int] = set() if restored else set(self._indices.values())
        if restored:
            self._saved_signatures = {
                index: hashlib.sha256(dumps(self._wire(part)).encode()).digest()
                for index, part in enumerate(self._parts)
            }

    def _append_part(self, wire: dict[str, Any]) -> None:
        index = len(self._parts)
        self._parts.append(wire)
        self._indices[id(wire)] = index
        self._dirty.add(index)

    def _mark_changed(self, wire: dict[str, Any]) -> None:
        self._dirty.add(self._indices[id(wire)])

    def _ai(self, chunk: dict[str, Any]) -> dict[str, Any]:
        message_id = str(chunk.get("message_id") or "")
        source = str(chunk.get("checkpoint_ns") or chunk.get("node") or "")
        if source:
            self._sources.add(source)
        if message_id:
            self._identified = True
            self._assistant = next(
                (p for p in self._parts if p["type"] == "ai" and p["data"].get("id") == message_id),
                None,
            )
        elif (
            self._assistant is not None
            and self._assistant["data"].get("additional_kwargs", {}).get("history_source", "")
            != source
        ):
            self._assistant = None
        if self._assistant is None:
            self._assistant = message_to_dict(
                AIMessage(content="", id=f"{self.turn['id']}:stream:{len(self._parts)}")
            )
            if message_id:
                self._assistant["data"]["id"] = message_id
                self._assistant["data"].setdefault("additional_kwargs", {})["history_stream_id"] = (
                    message_id
                )
            self._assistant["data"].setdefault("additional_kwargs", {})["history_source"] = source
            self._append_part(self._assistant)
        self._mark_changed(self._assistant)
        return self._assistant["data"]  # type: ignore[no-any-return]

    def observe(self, chunk: dict[str, Any]) -> None:
        super().observe(chunk)
        kind = chunk.get("type")
        if kind in ("state_snapshot", "state_update"):
            from octop.infra.gateway.process.history_projection import (
                _chunk_messages,  # noqa: PLC0415
            )

            for msg in _chunk_messages(chunk):
                if _role(msg) != "system" and message_input(msg) is None:
                    self.decode_failed = True
        if kind == "hitl_required":
            self.paused = True
        if kind == "error":
            self.failed = True
        if self.turn["format"] != "v2":
            return
        if kind in ("state_snapshot", "state_update"):
            self._merge_state()
        if kind in ("token", "reasoning"):
            data = self._ai(chunk)
            text = str(chunk.get("content") or "")
            if kind == "token":
                content = data["content"]
                data["content"] = (
                    content + text
                    if isinstance(content, str)
                    else [*content, {"type": "text", "text": text}]
                )
            else:
                extra = data.setdefault("additional_kwargs", {})
                extra["reasoning_content"] = str(extra.get("reasoning_content") or "") + text
        elif kind == "tool_call_chunk":
            data = self._ai(chunk)
            calls = data.setdefault("tool_calls", [])
            call_id = str(chunk.get("id") or "")
            index = int(chunk.get("index") or 0)
            while len(calls) <= index:
                calls.append({"id": "", "name": "", "args": {}, "type": "tool_call"})
            call = calls[index]
            if call_id:
                call["id"] = call_id
            if chunk.get("name"):
                call["name"] = str(chunk["name"])
            args = chunk.get("args")
            # Keep incomplete arguments in their original form until JSON closes.
            extra = data.setdefault("additional_kwargs", {})
            fragments = extra.setdefault("history_tool_args", {})
            key = str(index)
            if isinstance(args, str):
                fragments[key] = str(fragments.get(key) or "") + args
                try:
                    parsed = json.loads(fragments[key])
                    if isinstance(parsed, dict):
                        call["args"] = parsed
                except ValueError:
                    pass
            elif isinstance(args, dict):
                call["args"] = args
        elif kind == "tool_result":
            raw = chunk.get("messages")
            wires: list[dict[str, Any]] = []
            if isinstance(raw, list):
                for msg in raw:
                    item = message_input(msg)
                    if item is not None:
                        wires.append(json.loads(item.message_json))
            if not wires:
                call_id, name, result = _tool_result_fields(chunk)
                wires = [
                    message_to_dict(
                        ToolMessage(
                            content=result if isinstance(result, (str, list)) else dumps(result),
                            name=name,
                            tool_call_id=call_id,
                            id=f"{self.turn['id']}:tool:{call_id}",
                        )
                    )
                ]
            for wire in wires:
                call_id = wire["data"].get("tool_call_id")
                existing = next(
                    (
                        p
                        for p in self._parts
                        if p["type"] == "tool" and p["data"].get("tool_call_id") == call_id
                    ),
                    None,
                )
                if existing is None:
                    self._append_part(wire)
                elif existing != wire:
                    existing.update(wire)
                    self._mark_changed(existing)
            self._assistant = None

    def _merge_state(self) -> None:
        raw = self._state_messages
        if not any(_role(message) in ("human", "user") for message in raw):
            raw = [*self.seed_messages, *raw]
        # Updates can revise an existing ID. Keep the latest version, in its
        # original position, instead of the legacy projection's first replay.
        by_key: dict[str, dict[str, Any]] = {}
        for message in raw:
            item = message_input(message)
            if item is not None:
                key = "id:" + item.message_id if item.message_id else "wire:" + item.message_json
                by_key[key] = json.loads(item.message_json)
        state = list(by_key.values())
        assistant_index = 0
        for wire in state:
            role, data = wire["type"], wire["data"]
            target = next(
                (p for p in self._parts if data.get("id") and p["data"].get("id") == data["id"]),
                None,
            )
            if target is None and role == "human":
                target = next((p for p in self._parts if p["type"] == "human"), None)
            if target is None and role == "tool":
                target = next(
                    (
                        p
                        for p in self._parts
                        if p["type"] == "tool"
                        and p["data"].get("tool_call_id") == data.get("tool_call_id")
                    ),
                    None,
                )
            if role == "ai":
                assistants = [p for p in self._parts if p["type"] == "ai"]
                if (
                    target is None
                    and not self._identified
                    and len(self._sources) <= 1
                    and assistant_index < len(assistants)
                ):
                    target = assistants[assistant_index]
                assistant_index += 1
            if target is None:
                self._append_part(wire)
                continue
            previous = target["data"]
            for key in ("reasoning_content", "history_source", "history_stream_id"):
                value = previous.get("additional_kwargs", {}).get(key)
                if value and not data.setdefault("additional_kwargs", {}).get(key):
                    # Final state may already carry the same visible thinking
                    # inline. Preserve its original representation only once.
                    content = data.get("content")
                    inline: list[str] = []
                    if key == "reasoning_content":
                        if isinstance(content, str):
                            inline = re.findall(
                                r"<think>([\s\S]*?)</think>", content, re.IGNORECASE
                            )
                        elif isinstance(content, list):
                            inline = [
                                str(
                                    block.get("thinking")
                                    or block.get("reasoning")
                                    or block.get("text")
                                    or ""
                                )
                                for block in content
                                if isinstance(block, dict)
                                and block.get("type") in ("thinking", "reasoning")
                            ]
                    if not inline or "".join(inline).strip() != str(value).strip():
                        data["additional_kwargs"][key] = value
            partial, final = previous.get("content"), data.get("content")
            if isinstance(partial, str) and isinstance(final, str) and partial.startswith(final):
                data["content"] = partial
            if target != wire:
                target.clear()
                target.update(wire)
                self._mark_changed(target)
        if len(self._sources) > 1 and not self._identified:
            self.decode_failed = True

    @staticmethod
    def _wire(part: dict[str, Any]) -> dict[str, Any]:
        wire: dict[str, Any] = json.loads(dumps(part))
        extra = wire["data"].get("additional_kwargs", {})
        fragments = extra.get("history_tool_args", {})
        for key, fragment in list(fragments.items()):
            try:
                if isinstance(json.loads(fragment), dict):
                    del fragments[key]
            except ValueError:
                pass
        if not fragments:
            extra.pop("history_tool_args", None)
        return wire

    def wires(self) -> list[dict[str, Any]]:
        return [self._wire(part) for part in self._parts]

    async def flush(self) -> None:
        """Commit changed messages before the caller forwards the current event."""
        if self.turn["format"] != "v2":
            return
        if self._write_failure is not None:
            raise self._write_failure
        try:
            cancelled: asyncio.CancelledError | None = None
            dirty = sorted(self._dirty)
            updates = []
            signatures = {}
            for index in dirty:
                wire = self._wire(self._parts[index])
                signature = hashlib.sha256(dumps(wire).encode()).digest()
                if signature != self._saved_signatures.get(index):
                    updates.append((index, wire))
                    signatures[index] = signature
            if updates:
                write = asyncio.create_task(
                    asyncio.to_thread(self.archive.save_message_updates, self.turn, updates)
                )
                while not write.done():
                    try:
                        await asyncio.shield(write)
                    except asyncio.CancelledError as exc:
                        # Executor writes cannot be cancelled. Even repeated
                        # cancellation must wait before releasing this turn.
                        cancelled = exc
                write.result()
                self._saved_signatures.update(signatures)
            self._dirty.difference_update(dirty)
            if cancelled is not None:
                raise cancelled
        except Exception as exc:
            self.failed = True
            self._write_failure = exc
            raise

    async def finish(self, *, completed: bool) -> None:
        if self._write_failure is None:
            await self.flush()
        status = (
            "failed"
            if self._write_failure is not None
            else "paused"
            if self.paused
            else "failed"
            if self.failed
            else "complete"
            if completed
            else "interrupted"
        )
        if status == "complete" and self.turn["format"] == "v2":
            wires = self.wires()
            has_answer = any(w["type"] == "ai" and not w["data"].get("tool_calls") for w in wires)
            calls = {
                c.get("id")
                for w in wires
                if w["type"] == "ai"
                for c in w["data"].get("tool_calls", [])
            }
            results = {w["data"].get("tool_call_id") for w in wires if w["type"] == "tool"}
            if (
                self.decode_failed
                or any(
                    w["data"].get("additional_kwargs", {}).get("history_tool_args") for w in wires
                )
                or not has_answer
                or not calls.issubset(results)
                or self.turn["thread_id"] in self.archive.trajectory_errors
            ):
                status = "partial"
        error = (
            "archive_write_failed"
            if self._write_failure is not None
            else (
                "capture_incomplete"
                if (
                    self.decode_failed
                    or status == "partial"
                    or self.turn["thread_id"] in self.archive.trajectory_errors
                )
                else None
            )
        )
        await asyncio.to_thread(self.archive.finish, self.turn["id"], status, error=error)


async def flush_tracker(tracker: TurnHistoryTracker | None) -> None:
    if isinstance(tracker, RecordingTracker):
        await tracker.flush()
