"""OctopMemory Hermes MemoryProvider plugin.

This module is intentionally importable outside Hermes so the core
provider behaviour can be tested in this repository. When loaded inside
Hermes, `agent.memory_provider.MemoryProvider` is used as the base class;
outside Hermes we fall back to a tiny local base for tests.
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from pathlib import Path
from typing import Any

try:  # pragma: no cover - exercised on a real Hermes install
    from agent.memory_provider import MemoryProvider
except ImportError:  # pragma: no cover - local test fallback

    class MemoryProvider:  # type: ignore[no-redef]
        pass


from octop_memory.adapters.bridge.handlers import Bridge
from octop_memory.application.config import MemoryRuntimeConfig
from octop_memory.application.host_files import DEFAULT_HOST_FILE_GLOBS, HostFilesIndex
from octop_memory.core import Memory
from octop_memory.pipeline.recall import recall_for_prompt

logger = logging.getLogger(__name__)

MEMORY_SEARCH_SCHEMA: dict[str, Any] = {
    "name": "memory_search",
    "description": (
        "Search OctopMemory for prior decisions, preferences, people, projects, and earlier conversations. "
        "Returns ranked snippets with virtual paths that can be read with memory_get."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "maxResults": {"type": "integer", "minimum": 1},
            "minScore": {"type": "number"},
            "corpus": {"type": "string", "enum": ["memory", "wiki", "all", "sessions"]},
        },
        "required": ["query"],
    },
}

MEMORY_GET_SCHEMA: dict[str, Any] = {
    "name": "memory_get",
    "description": "Read a specific OctopMemory path returned by memory_search.",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "from": {"type": "integer", "minimum": 1},
            "lines": {"type": "integer", "minimum": 1},
            "corpus": {"type": "string", "enum": ["memory", "wiki", "all"]},
        },
        "required": ["path"],
    },
}


class OctopMemoryProvider(MemoryProvider):
    """Hermes MemoryProvider backed by octop-memory."""

    def __init__(self) -> None:
        self._session_id = ""
        self._hermes_home: Path | None = None
        self._data_dir: Path | None = None
        self._memory: Memory | None = None
        self._bridge: Bridge | None = None
        self._host_files: HostFilesIndex | None = None
        self._config: dict[str, Any] = {}
        self._threads: list[threading.Thread] = []

    @property
    def name(self) -> str:
        return "octopmemory"

    def is_available(self) -> bool:
        return True

    def initialize(self, session_id: str, **kwargs: Any) -> None:
        self._session_id = session_id
        hermes_home = kwargs.get("hermes_home")
        if not isinstance(hermes_home, str) or not hermes_home:
            raise ValueError("OctopMemoryProvider.initialize requires hermes_home")
        self._hermes_home = Path(hermes_home).expanduser().resolve()
        self._data_dir = self._hermes_home / "octopmemory"
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._config = self._load_config()

        namespace = str(self._config.get("namespace") or "hermes__default")
        db_path = self._config.get("db_path") or str(self._data_dir / "memory.sqlite")
        bridge_cfg = self._bridge_config()
        self._memory = Memory(
            namespace=namespace,
            backend="sqlite",
            backend_config={"db_path": str(Path(str(db_path)).expanduser())},
        )
        self._host_files = self._build_host_files_index(db_path=Path(str(db_path)).expanduser(), namespace=namespace)
        self._bridge = Bridge(self._memory, host_files=self._host_files, config=bridge_cfg)

    def get_config_schema(self) -> list[dict[str, Any]]:
        return [
            {
                "key": "profile",
                "description": "OctopMemory profile",
                "default": "balanced",
                "choices": ["balanced", "low_latency", "proactive", "privacy", "archive", "eval"],
            },
            {
                "key": "namespace",
                "description": "Memory namespace",
                "default": "hermes__default",
            },
            {
                "key": "db_path",
                "description": "SQLite db path; leave empty for $HERMES_HOME/octopmemory/memory.sqlite",
                "default": "",
            },
            {
                "key": "recall.default_max_results",
                "description": "Default memory_search result limit",
                "default": "5",
            },
            {
                "key": "recall.default_corpus",
                "description": "Default memory_search corpus",
                "default": "all",
                "choices": ["all", "memory", "sessions", "wiki"],
            },
            {
                "key": "recall.raw_policy",
                "description": "Raw-event search policy",
                "default": "fallback",
                "choices": ["never", "fallback", "always"],
            },
            {
                "key": "recall.layer_order",
                "description": "Comma-separated ranking order for result layers",
                "default": "atom,page,raw",
            },
            {
                "key": "capture.include_roles",
                "description": "Comma-separated roles to store from Hermes turns",
                "default": "user,assistant",
            },
            {
                "key": "capture.min_message_chars",
                "description": "Minimum message length to store; Hermes defaults to 0",
                "default": "0",
            },
            {
                "key": "capture.include_tool_calls",
                "description": "Store tool call metadata in raw payloads",
                "default": "false",
                "choices": ["true", "false"],
            },
            {
                "key": "capture.include_tool_results",
                "description": "Store tool result messages when role=tool",
                "default": "false",
                "choices": ["true", "false"],
            },
            {
                "key": "capture.skip_memory_echo",
                "description": "Drop OctopMemory recall echoes from captured transcripts",
                "default": "true",
                "choices": ["true", "false"],
            },
            {
                "key": "capture.host_files_watcher",
                "description": "Index Hermes built-in markdown memories from $HERMES_HOME/memories",
                "default": "true",
                "choices": ["true", "false"],
            },
            {
                "key": "host_files_root",
                "description": "Markdown memory directory; leave empty for $HERMES_HOME/memories",
                "default": "",
            },
            {
                "key": "host_files_allow",
                "description": "Comma-separated topical markdown globs under host_files_root",
                "default": ",".join(DEFAULT_HOST_FILE_GLOBS),
            },
            {
                "key": "privacy.redact_secrets",
                "description": "Redact common API keys, tokens, secrets, and passwords before storing raw content",
                "default": "true",
                "choices": ["true", "false"],
            },
            {
                "key": "privacy.redact_patterns",
                "description": "Comma-separated regex patterns to redact before storing raw content",
                "default": "",
            },
            {
                "key": "privacy.store_raw_content",
                "description": (
                    "Store raw text content; false keeps metadata but replaces raw content with a placeholder"
                ),
                "default": "true",
                "choices": ["true", "false"],
            },
            {
                "key": "privacy.store_tool_payloads",
                "description": "Store tool payload fields beyond safe role metadata",
                "default": "false",
                "choices": ["true", "false"],
            },
        ]

    def save_config(self, values: dict[str, Any], hermes_home: str) -> None:
        path = Path(hermes_home).expanduser().resolve() / "octopmemory.json"
        existing = _read_json_object(path)
        merged = _deep_merge(existing, _normalize_config_values(values))
        path.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def system_prompt_block(self) -> str:
        return (
            "OctopMemory is available via `memory_search` and `memory_get`. "
            "Use it for prior decisions, preferences, people, projects, and earlier conversations."
        )

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        if not query or self._memory is None:
            return ""
        limit = int(self._config.get("prefetch_limit") or 5)
        result = recall_for_prompt(self._memory, query, limit=limit)
        if not result.snippets:
            return ""
        lines = ["## OctopMemory Recall"]
        for snip in result.snippets[:limit]:
            lines.append(f"- [{snip.layer} · {_snippet_path(snip)}] {snip.text}")
        return "\n".join(lines)

    def queue_prefetch(self, query: str, *, session_id: str = "") -> None:
        # Intentional no-op (matches the MemoryProvider base default). Hermes
        # calls queue_prefetch after a turn with that turn's message, and the
        # NEXT turn's prefetch runs with the *new* message — so a query-keyed
        # warm cache would essentially never hit. A useful background prefetch
        # would need session-scoped caching (cf. the honcho plugin), which buys
        # little here: recall is local SQLite FTS and prefetch is already fast.
        return None

    def sync_turn(
        self,
        user_content: str,
        assistant_content: str,
        *,
        session_id: str = "",
        messages: list[dict[str, Any]] | None = None,
    ) -> None:
        sid = session_id or self._session_id
        thread = threading.Thread(
            target=self._sync_turn_blocking,
            args=(sid, user_content, assistant_content, messages),
            daemon=True,
        )
        thread.start()
        self._threads.append(thread)

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        return [MEMORY_SEARCH_SCHEMA, MEMORY_GET_SCHEMA]

    def handle_tool_call(self, tool_name: str, args: dict[str, Any], **kwargs: Any) -> str:
        bridge = self._require_bridge()
        if tool_name == "memory_search":
            resp = bridge.handle({"jsonrpc": "2.0", "id": 1, "method": "memory_search", "params": args})
            return json.dumps(_unwrap(resp), ensure_ascii=False)
        if tool_name == "memory_get":
            resp = bridge.handle({"jsonrpc": "2.0", "id": 1, "method": "memory_get", "params": args})
            return json.dumps(_unwrap(resp), ensure_ascii=False)
        raise ValueError(f"Unknown tool: {tool_name}")

    def on_pre_compress(self, messages: list[dict[str, Any]]) -> str:
        content = _render_messages(messages)
        if content:
            self._write_raw("compaction", content, {"source": "on_pre_compress"})
            return "OctopMemory captured pre-compression context."
        return ""

    def on_memory_write(
        self,
        action: str,
        target: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        payload = {"action": action, "target": target, **(metadata or {})}
        self._write_raw("host_memory_write", content, payload)

    def on_session_switch(self, new_session_id: str, **kwargs: Any) -> None:
        self._session_id = new_session_id

    def shutdown(self) -> None:
        for thread in list(self._threads):
            thread.join(timeout=5.0)
        self._threads.clear()
        if self._host_files is not None:
            self._host_files.stop()
            self._host_files = None
            if self._memory is not None:
                self._bridge = Bridge(self._memory, config=self._bridge_config())

    def _sync_turn_blocking(
        self,
        session_id: str,
        user_content: str,
        assistant_content: str,
        messages: list[dict[str, Any]] | None,
    ) -> None:
        payload_base = {"messages_count": len(messages or [])}
        self._capture_events(
            session_id=session_id,
            events=[
                {
                    "id": _event_id(),
                    "event_type": "user_message",
                    "content": str(user_content),
                    "payload": {"role": "user", **payload_base},
                },
                {
                    "id": _event_id(),
                    "event_type": "assistant_message",
                    "content": str(assistant_content),
                    "payload": {"role": "assistant", **payload_base},
                },
            ],
        )

    def _write_raw(self, event_type: str, content: str, payload: dict[str, Any]) -> None:
        self._capture_events(
            session_id=self._session_id or None,
            events=[
                {
                    "id": _event_id(),
                    "event_type": event_type,
                    "content": content,
                    "payload": payload,
                }
            ],
        )

    def _capture_events(self, *, session_id: str | None, events: list[dict[str, Any]]) -> dict[str, Any]:
        resp = self._require_bridge().handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "capture",
                "params": {
                    "host": "hermes",
                    "session_id": session_id,
                    "thread_id": None,
                    "user": None,
                    "events": events,
                },
            }
        )
        result = _unwrap(resp)
        if isinstance(result, dict):
            return result
        raise RuntimeError(f"Unexpected OctopMemory capture response: {result!r}")

    def _load_config(self) -> dict[str, Any]:
        assert self._hermes_home is not None
        path = self._hermes_home / "octopmemory.json"
        if not path.exists():
            return {"profile": "balanced", "namespace": "hermes__default"}
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            logger.warning("Ignoring invalid OctopMemory config: %s", path)
            return {"profile": "balanced", "namespace": "hermes__default"}
        return loaded if isinstance(loaded, dict) else {"profile": "balanced", "namespace": "hermes__default"}

    def _bridge_config(self) -> MemoryRuntimeConfig:
        capture_cfg: dict[str, Any] = {"min_message_chars": 0, "host_files_watcher": True}
        if isinstance(self._config.get("capture"), dict):
            capture_cfg.update(self._config["capture"])
        return MemoryRuntimeConfig(
            profile=self._config.get("profile") if isinstance(self._config.get("profile"), str) else None,
            mode="self-hosted",
            recall=self._config.get("recall") if isinstance(self._config.get("recall"), dict) else {},
            capture=capture_cfg,
            privacy=self._config.get("privacy") if isinstance(self._config.get("privacy"), dict) else {},
        )

    def _build_host_files_index(self, *, db_path: Path, namespace: str) -> HostFilesIndex | None:
        capture_cfg = self._bridge_config().capture
        if capture_cfg.get("host_files_watcher") is False:
            return None
        assert self._hermes_home is not None
        raw_root = self._config.get("host_files_root")
        root = Path(raw_root).expanduser() if isinstance(raw_root, str) and raw_root else self._hermes_home / "memories"
        index = HostFilesIndex(db_path=db_path, namespace=namespace, include_globs=_host_files_allow(self._config))
        index.scan_once(root)
        index.start_polling(root, interval=30.0)
        return index

    def _require_memory(self) -> Memory:
        if self._memory is None:
            raise RuntimeError("OctopMemoryProvider is not initialized")
        return self._memory

    def _require_bridge(self) -> Bridge:
        if self._bridge is None:
            raise RuntimeError("OctopMemoryProvider is not initialized")
        return self._bridge


def register(ctx: Any) -> None:
    ctx.register_memory_provider(OctopMemoryProvider())


def _unwrap(resp: dict[str, Any]) -> Any:
    if "error" in resp:
        return resp["error"]
    return resp.get("result")


def _event_id() -> str:
    return f"evt_{uuid.uuid4().hex[:12]}"


def _snippet_path(snip: Any) -> str:
    layer = getattr(snip, "layer", "raw")
    source_id = getattr(snip, "source_id", "")
    timestamp_iso = getattr(snip, "timestamp_iso", "")
    if layer == "atom":
        return f"atom/{source_id}.md"
    date = timestamp_iso[:10] if isinstance(timestamp_iso, str) and len(timestamp_iso) >= 10 else "unknown"
    return f"raw/{date}/{source_id}.md"


def _render_messages(messages: list[dict[str, Any]]) -> str:
    rendered: list[str] = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if isinstance(content, str) and content.strip():
            rendered.append(f"{role}: {content}")
    return "\n".join(rendered)


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _normalize_config_values(values: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in values.items():
        if value is None or value == "":
            continue
        coerced = _coerce_config_value(key, value)
        _set_dotted(normalized, key, coerced)
    return normalized


def _set_dotted(target: dict[str, Any], key: str, value: Any) -> None:
    parts = key.split(".")
    current = target
    for part in parts[:-1]:
        existing = current.get(part)
        if not isinstance(existing, dict):
            existing = {}
            current[part] = existing
        current = existing
    current[parts[-1]] = value


def _coerce_config_value(key: str, value: Any) -> Any:
    if key in {
        "recall.default_max_results",
        "capture.min_message_chars",
    }:
        return int(value)
    if key in {
        "capture.include_tool_calls",
        "capture.include_tool_results",
        "capture.skip_memory_echo",
        "privacy.redact_secrets",
        "privacy.store_raw_content",
        "privacy.store_tool_payloads",
    }:
        return _coerce_bool(value)
    if key in {
        "recall.layer_order",
        "capture.include_roles",
        "privacy.redact_patterns",
        "host_files_allow",
    }:
        return _coerce_str_list(value)
    return value


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False
    return bool(value)


def _coerce_str_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return [str(value)]


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _host_files_allow(config: dict[str, Any]) -> list[str]:
    value = config.get("host_files_allow")
    if value is None:
        return list(DEFAULT_HOST_FILE_GLOBS)
    return _coerce_str_list(value)


__all__ = ["MEMORY_GET_SCHEMA", "MEMORY_SEARCH_SCHEMA", "OctopMemoryProvider", "register"]
