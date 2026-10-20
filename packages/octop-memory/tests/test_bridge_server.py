"""End-to-end tests for the bridge JSON-RPC server.

We drive the server with in-memory pipes (``StringIO``) so no
subprocess is needed. Each test composes a ``Memory`` instance pointed
at a temp SQLite file, wraps it in a :class:`Bridge`, and either:

1. Calls ``bridge.handle(req)`` directly for unit-style assertions, or
2. Pumps lines through ``serve(...)`` to validate the line-framed
   wire format.
"""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from octop_memory.adapters.bridge import PROTOCOL_VERSION
from octop_memory.adapters.bridge.handlers import (
    ERR_HOST_FILE_UNAVAILABLE,
    ERR_INVALID_PARAMS,
    ERR_METHOD_NOT_FOUND,
    ERR_PATH_INVALID,
    ERR_PATH_NOT_FOUND,
    Bridge,
)
from octop_memory.adapters.bridge.server import serve
from octop_memory.application.config import MemoryRuntimeConfig
from octop_memory.application.host_files import HostFilesIndex
from octop_memory.core import Memory
from octop_memory.types import RawEvent

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def memory(tmp_path: Path) -> Memory:
    db_path = tmp_path / "bridge.sqlite"
    return Memory(
        namespace="test_bridge",
        backend="sqlite",
        backend_config={"db_path": str(db_path)},
    )


@pytest.fixture
def bridge(memory: Memory) -> Bridge:
    return Bridge(memory)


# ---------------------------------------------------------------------------
# Protocol-level tests
# ---------------------------------------------------------------------------


class TestEnvelope:
    def test_handshake(self, bridge: Bridge) -> None:
        resp = bridge.handle({"jsonrpc": "2.0", "id": 1, "method": "handshake", "params": {}})
        assert resp["id"] == 1
        assert resp["result"]["protocol_version"] == PROTOCOL_VERSION
        assert resp["result"]["namespace"] == "test_bridge"

    def test_stats_empty(self, bridge: Bridge) -> None:
        resp = bridge.handle({"jsonrpc": "2.0", "id": 1, "method": "stats", "params": {}})
        result = resp["result"]
        assert result["namespace"] == "test_bridge"
        assert result["counts"]["raw_events"] == 0
        assert result["counts"]["atoms"] == 0
        assert result["counts"]["entities"] == 0
        assert result["config"]["recall"]["default_corpus"] == "all"
        assert result["host_files"] is None

    def test_unknown_method(self, bridge: Bridge) -> None:
        resp = bridge.handle({"jsonrpc": "2.0", "id": 7, "method": "nope", "params": {}})
        assert resp["error"]["code"] == ERR_METHOD_NOT_FOUND

    def test_missing_method(self, bridge: Bridge) -> None:
        resp = bridge.handle({"jsonrpc": "2.0", "id": 7})
        assert resp["error"]["code"] != 0
        assert "missing 'method'" in resp["error"]["message"]

    def test_invalid_params_type(self, bridge: Bridge) -> None:
        resp = bridge.handle({"jsonrpc": "2.0", "id": 7, "method": "memory_search", "params": "notdict"})
        assert resp["error"]["code"] == ERR_INVALID_PARAMS


class TestServeLoop:
    def test_pump_two_requests(self, bridge: Bridge) -> None:
        stdin = io.StringIO(
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "handshake", "params": {}})
            + "\n"
            + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "handshake", "params": {}})
            + "\n"
        )
        stdout = io.StringIO()
        serve(bridge, stdin=stdin, stdout=stdout)
        lines = [line for line in stdout.getvalue().split("\n") if line]
        assert len(lines) == 2
        assert json.loads(lines[0])["id"] == 1
        assert json.loads(lines[1])["id"] == 2

    def test_blank_lines_ignored(self, bridge: Bridge) -> None:
        stdin = io.StringIO(
            "\n\n" + json.dumps({"jsonrpc": "2.0", "id": 1, "method": "handshake", "params": {}}) + "\n"
        )
        stdout = io.StringIO()
        serve(bridge, stdin=stdin, stdout=stdout)
        lines = [line for line in stdout.getvalue().split("\n") if line]
        assert len(lines) == 1


# ---------------------------------------------------------------------------
# memory_search
# ---------------------------------------------------------------------------


class TestMemorySearch:
    def test_empty_query_rejected(self, bridge: Bridge) -> None:
        resp = bridge.handle({"jsonrpc": "2.0", "id": 1, "method": "memory_search", "params": {"query": ""}})
        assert resp["error"]["code"] == ERR_INVALID_PARAMS

    def test_no_matches_returns_empty(self, bridge: Bridge) -> None:
        resp = bridge.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "memory_search",
                "params": {"query": "no such content"},
            }
        )
        assert resp["result"]["hits"] == []
        assert resp["result"]["empty_reason"] == "no_matches"

    def test_finds_raw_event(self, bridge: Bridge, memory: Memory) -> None:
        # Use enough content that the recall layer doesn't skip it.
        memory.add_raw_batch(
            [
                RawEvent(
                    id="evt_1",
                    host="openclaw",
                    session_id="s",
                    thread_id="t",
                    user="alice",
                    timestamp=datetime(2026, 6, 4, tzinfo=UTC),
                    event_type="user_message",
                    content="Hermes adapter uses the MemoryProvider abstract base class as its plugin contract.",
                    payload={"role": "user"},
                )
            ]
        )
        resp = bridge.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "memory_search",
                "params": {"query": "Hermes adapter MemoryProvider", "maxResults": 5},
            }
        )
        hits = resp["result"]["hits"]
        assert len(hits) >= 1
        # Path is projected onto raw/<date>/<id>.md
        assert hits[0]["path"].startswith("raw/2026-06-04/evt_1")


# ---------------------------------------------------------------------------
# memory_get
# ---------------------------------------------------------------------------


class TestMemoryGet:
    def test_invalid_path_string(self, bridge: Bridge) -> None:
        resp = bridge.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "memory_get",
                "params": {"path": "garbage"},
            }
        )
        assert resp["error"]["code"] == ERR_PATH_INVALID

    def test_atom_not_found(self, bridge: Bridge) -> None:
        resp = bridge.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "memory_get",
                "params": {"path": "atom/missing.md"},
            }
        )
        assert resp["error"]["code"] == ERR_PATH_NOT_FOUND

    def test_raw_get_returns_excerpt(self, bridge: Bridge, memory: Memory) -> None:
        memory.add_raw_batch(
            [
                RawEvent(
                    id="evt_1",
                    host="openclaw",
                    session_id="s",
                    thread_id="t",
                    user="alice",
                    timestamp=datetime(2026, 6, 4, 10, 30, tzinfo=UTC),
                    event_type="user_message",
                    content="line1\nline2\nline3",
                    payload={"role": "user"},
                )
            ]
        )
        resp = bridge.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "memory_get",
                "params": {"path": "raw/2026-06-04/evt_1.md"},
            }
        )
        result = resp["result"]
        assert result["kind"] == "raw"
        assert "line1" in result["excerpt"]
        assert "line2" in result["excerpt"]
        assert result["truncated"] is False

    def test_raw_get_with_line_range(self, bridge: Bridge, memory: Memory) -> None:
        # Render produces a YAML front-matter block + body, so line
        # numbers are non-trivial. We use a plain content string to
        # keep the test predictable.
        memory.add_raw_batch(
            [
                RawEvent(
                    id="evt_1",
                    host="openclaw",
                    session_id="s",
                    thread_id="t",
                    user="alice",
                    timestamp=datetime(2026, 6, 4, 10, 30, tzinfo=UTC),
                    event_type="user_message",
                    content="\n".join(f"line{i}" for i in range(1, 21)),  # 20 lines
                    payload={"role": "user"},
                )
            ]
        )
        resp = bridge.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "memory_get",
                "params": {"path": "raw/2026-06-04/evt_1.md", "from": 1, "lines": 5},
            }
        )
        result = resp["result"]
        assert result["truncated"] is True
        assert result["continuation"]["from"] == 6

    def test_host_file_path_unavailable_when_index_off(self, bridge: Bridge) -> None:
        # When Bridge is built without a HostFilesIndex (Wave A
        # behaviour, also the default for tests that don't opt in)
        # host paths surface as ERR_HOST_FILE_UNAVAILABLE.
        resp = bridge.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "memory_get",
                "params": {"path": "memory/2026-06-04.md"},
            }
        )
        assert resp["error"]["code"] == ERR_HOST_FILE_UNAVAILABLE


# ---------------------------------------------------------------------------
# host_files integration (Wave C)
# ---------------------------------------------------------------------------


class TestHostFilesIntegration:
    """Bridge wired with a HostFilesIndex serves real-file paths."""

    @pytest.fixture
    def workspace(self, tmp_path: Path) -> Path:
        ws = tmp_path / "ws"
        (ws / "memory").mkdir(parents=True)
        return ws

    @pytest.fixture
    def host_files(self, tmp_path: Path) -> HostFilesIndex:
        idx = HostFilesIndex(db_path=tmp_path / "hf.sqlite", namespace="hf_ns")
        yield idx
        idx.stop()

    @pytest.fixture
    def bridge_with_hf(
        self,
        memory: Memory,
        host_files: HostFilesIndex,
        workspace: Path,
    ) -> Bridge:
        # Seed a couple of host files synchronously (no polling thread).
        (workspace / "MEMORY.md").write_text("User prefers dark mode and Pacific timezone.", encoding="utf-8")
        (workspace / "memory" / "2026-06-04.md").write_text(
            "Decision: Hermes adapter follows MemoryProvider contract.\nReasoning: keeps the same ABC across hosts.",
            encoding="utf-8",
        )
        (workspace / "topics").mkdir()
        (workspace / "topics" / "billing.md").write_text("Billing topic file cites renewal policy.", encoding="utf-8")
        host_files.scan_once(workspace)
        return Bridge(memory, host_files=host_files)

    def test_memory_get_host_file(self, bridge_with_hf: Bridge) -> None:
        resp = bridge_with_hf.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "memory_get",
                "params": {"path": "memory/2026-06-04.md"},
            }
        )
        result = resp["result"]
        assert result["kind"] == "host_daily"
        assert "Hermes adapter" in result["excerpt"]
        assert result["metadata"]["path"] == "memory/2026-06-04.md"
        assert "size" in result["metadata"]

    def test_memory_get_host_root(self, bridge_with_hf: Bridge) -> None:
        resp = bridge_with_hf.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "memory_get",
                "params": {"path": "MEMORY.md"},
            }
        )
        result = resp["result"]
        assert result["kind"] == "host_root"
        assert "dark mode" in result["excerpt"]

    def test_memory_get_topical_host_file(self, bridge_with_hf: Bridge) -> None:
        resp = bridge_with_hf.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "memory_get",
                "params": {"path": "topics/billing.md"},
            }
        )
        result = resp["result"]
        assert result["kind"] == "host_file"
        assert "renewal policy" in result["excerpt"]

    def test_memory_get_host_file_not_indexed(self, bridge_with_hf: Bridge) -> None:
        # Asking for a real-file path the index has never seen → 404
        # (not the "watcher off" error, which is for missing index).
        resp = bridge_with_hf.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "memory_get",
                "params": {"path": "memory/2099-01-01.md"},
            }
        )
        assert resp["error"]["code"] == ERR_PATH_NOT_FOUND

    def test_memory_search_includes_host_files(self, bridge_with_hf: Bridge, memory: Memory) -> None:
        # Seed an atom-eligible raw event so we have both layers.
        memory.add_raw_batch(
            [
                RawEvent(
                    id="evt_aux",
                    host="openclaw",
                    session_id=None,
                    thread_id=None,
                    user=None,
                    timestamp=datetime(2026, 6, 4, tzinfo=UTC),
                    event_type="user_message",
                    content="Hermes adapter discussion that should rank somewhere.",
                    payload={"role": "user"},
                )
            ]
        )
        resp = bridge_with_hf.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "memory_search",
                "params": {"query": "Hermes adapter", "maxResults": 5},
            }
        )
        hits = resp["result"]["hits"]
        layers = {h["layer"] for h in hits}
        # Host file layer must be among the hits — we dropped a file
        # whose body contains "Hermes adapter".
        assert "host_file" in layers
        host_paths = {h["path"] for h in hits if h["layer"] == "host_file"}
        assert "memory/2026-06-04.md" in host_paths

    def test_memory_search_corpus_filter(self, bridge_with_hf: Bridge) -> None:
        # corpus="memory" should still include host files (treated as
        # part of the memory corpus); corpus="sessions" is host-only.
        resp = bridge_with_hf.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "memory_search",
                "params": {"query": "Hermes", "corpus": "sessions"},
            }
        )
        hits = resp["result"]["hits"]
        assert all(h["layer"] == "host_file" for h in hits)

    def test_stats_includes_host_files(self, bridge_with_hf: Bridge) -> None:
        resp = bridge_with_hf.handle({"jsonrpc": "2.0", "id": 1, "method": "stats", "params": {}})
        host_stats = resp["result"]["host_files"]
        assert host_stats["indexed"] == 3
        assert host_stats["root"] is not None
        assert host_stats["last_scan_iso"] is not None

    def test_reindex_scans_host_files(self, bridge_with_hf: Bridge, workspace: Path) -> None:
        (workspace / "memory" / "2026-06-05.md").write_text("New Hermes reindex note", encoding="utf-8")
        resp = bridge_with_hf.handle({"jsonrpc": "2.0", "id": 1, "method": "reindex", "params": {}})
        result = resp["result"]
        assert result["scanned"] >= 3
        assert result["indexed"] >= 1
        search = bridge_with_hf.handle(
            {"jsonrpc": "2.0", "id": 2, "method": "memory_search", "params": {"query": "reindex note"}}
        )
        assert any(h["path"] == "memory/2026-06-05.md" for h in search["result"]["hits"])

    def test_reindex_without_host_files_errors(self, bridge: Bridge) -> None:
        resp = bridge.handle({"jsonrpc": "2.0", "id": 1, "method": "reindex", "params": {}})
        assert resp["error"]["code"] == ERR_INVALID_PARAMS

    def test_host_files_policy_off_excludes_host_files(
        self,
        memory: Memory,
        host_files: HostFilesIndex,
        workspace: Path,
    ) -> None:
        (workspace / "memory" / "2026-06-04.md").write_text("Hermes host file only", encoding="utf-8")
        host_files.scan_once(workspace)
        bridge = Bridge(
            memory,
            host_files=host_files,
            config=MemoryRuntimeConfig(recall={"host_files_policy": "off"}),
        )
        resp = bridge.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "memory_search",
                "params": {"query": "Hermes", "maxResults": 5},
            }
        )
        assert all(h["layer"] != "host_file" for h in resp["result"]["hits"])

    def test_host_files_policy_only_returns_only_host_files(
        self,
        memory: Memory,
        host_files: HostFilesIndex,
        workspace: Path,
    ) -> None:
        memory.add_raw_batch(
            [
                RawEvent(
                    id="evt_raw",
                    host="openclaw",
                    session_id=None,
                    thread_id=None,
                    user=None,
                    timestamp=datetime(2026, 6, 4, tzinfo=UTC),
                    event_type="user_message",
                    content="Hermes raw event should be filtered out by host-files-only policy.",
                    payload={"role": "user"},
                )
            ]
        )
        (workspace / "memory" / "2026-06-04.md").write_text("Hermes host file only", encoding="utf-8")
        host_files.scan_once(workspace)
        bridge = Bridge(
            memory,
            host_files=host_files,
            config=MemoryRuntimeConfig(recall={"host_files_policy": "only"}),
        )
        resp = bridge.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "memory_search",
                "params": {"query": "Hermes", "maxResults": 5},
            }
        )
        hits = resp["result"]["hits"]
        assert hits
        assert all(h["layer"] == "host_file" for h in hits)


# ---------------------------------------------------------------------------
# memory_search policies
# ---------------------------------------------------------------------------


class TestMemorySearchPolicies:
    def test_raw_policy_never_excludes_raw(self, memory: Memory) -> None:
        memory.add_raw_batch(
            [
                RawEvent(
                    id="evt_raw",
                    host="openclaw",
                    session_id="s",
                    thread_id="t",
                    user="alice",
                    timestamp=datetime(2026, 6, 4, tzinfo=UTC),
                    event_type="user_message",
                    content="Hermes adapter raw-only memory should not appear when raw_policy is never.",
                    payload={"role": "user"},
                )
            ]
        )
        bridge = Bridge(memory, config=MemoryRuntimeConfig(recall={"raw_policy": "never"}))
        resp = bridge.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "memory_search",
                "params": {"query": "Hermes adapter", "maxResults": 5},
            }
        )
        assert resp["result"]["hits"] == []

    def test_default_max_results_from_config(self, memory: Memory) -> None:
        memory.add_raw_batch(
            [
                RawEvent(
                    id=f"evt_{i}",
                    host="openclaw",
                    session_id="s",
                    thread_id="t",
                    user="alice",
                    timestamp=datetime(2026, 6, 4, tzinfo=UTC),
                    event_type="user_message",
                    content=f"Hermes adapter repeated memory event number {i} with enough content to index.",
                    payload={"role": "user"},
                )
                for i in range(3)
            ]
        )
        bridge = Bridge(memory, config=MemoryRuntimeConfig(recall={"default_max_results": 1}))
        resp = bridge.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "memory_search",
                "params": {"query": "Hermes adapter"},
            }
        )
        assert len(resp["result"]["hits"]) == 1


# ---------------------------------------------------------------------------
# capture (D52-C agent_end → Memory.add_raw_batch)
# ---------------------------------------------------------------------------


class TestCapture:
    def test_writes_normal_event(self, bridge: Bridge, memory: Memory) -> None:
        resp = bridge.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "capture",
                "params": {
                    "session_id": "s1",
                    "thread_id": "t1",
                    "user": "alice",
                    "host": "openclaw",
                    "events": [
                        {
                            "event_type": "user_message",
                            "content": (
                                "Decision: we will go with D51-C path projection "
                                "because host silent turn writes real files."
                            ),
                            "payload": {"role": "user"},
                        },
                    ],
                },
            }
        )
        assert resp["result"]["accepted"] == 1
        assert resp["result"]["skipped_recall_marker"] == 0
        # And the event is searchable.
        results = memory.search_raw("D51-C path projection", limit=5)
        assert len(results) == 1

    def test_skips_recall_marker(self, bridge: Bridge) -> None:
        resp = bridge.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "capture",
                "params": {
                    "host": "openclaw",
                    "events": [
                        {
                            "event_type": "assistant_message",
                            "content": (
                                "## Memory Recall\nblah blah, this is our own injection "
                                "echoing back from the assistant transcript"
                            ),
                        }
                    ],
                },
            }
        )
        assert resp["result"]["accepted"] == 0
        assert resp["result"]["skipped_recall_marker"] == 1

    def test_skips_short_chatter(self, bridge: Bridge) -> None:
        resp = bridge.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "capture",
                "params": {
                    "host": "openclaw",
                    "events": [
                        {"event_type": "user_message", "content": "hi"},
                        {"event_type": "user_message", "content": "ok"},
                    ],
                },
            }
        )
        assert resp["result"]["accepted"] == 0
        assert resp["result"]["skipped_too_short"] == 2

    @pytest.mark.parametrize("content", ["请记住偏好", "记下来", "remember this", "retain this"])
    def test_short_message_has_no_intent_keyword_exception(self, memory: Memory, content: str) -> None:
        bridge = Bridge(memory, config=MemoryRuntimeConfig(capture={"min_message_chars": 200}))
        resp = bridge.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "capture",
                "params": {
                    "host": "openclaw",
                    "events": [
                        {
                            "event_type": "user_message",
                            "content": content,
                            "payload": {"role": "user"},
                        },
                    ],
                },
            }
        )
        assert resp["result"]["accepted"] == 0
        assert resp["result"]["skipped_too_short"] == 1
        events = memory.list_raw(limit=5)
        assert events == []

    def test_default_event_type_and_id(self, bridge: Bridge, memory: Memory) -> None:
        # When TS shell forgets to set event_type / id, we still accept.
        resp = bridge.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "capture",
                "params": {
                    "host": "openclaw",
                    "events": [
                        {
                            "content": (
                                "A long-enough message that still passes the 50-char threshold for capture acceptance."
                            ),
                        }
                    ],
                },
            }
        )
        assert resp["result"]["accepted"] == 1
        # The synthesized id starts with evt_
        events = memory.list_raw(limit=10)
        assert len(events) == 1
        assert events[0].id.startswith("evt_")
        assert events[0].event_type == "user_message"

    def test_include_roles_filters_assistant(self, memory: Memory) -> None:
        bridge = Bridge(memory, config=MemoryRuntimeConfig(capture={"include_roles": ["user"], "min_message_chars": 0}))
        resp = bridge.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "capture",
                "params": {
                    "host": "openclaw",
                    "events": [
                        {
                            "event_type": "assistant_message",
                            "content": "assistant content long enough",
                            "payload": {"role": "assistant"},
                        },
                        {
                            "event_type": "user_message",
                            "content": "user content long enough",
                            "payload": {"role": "user"},
                        },
                    ],
                },
            }
        )
        assert resp["result"]["accepted"] == 1
        events = memory.list_raw(limit=10)
        assert len(events) == 1
        assert events[0].payload["role"] == "user"

    def test_tool_result_skipped_unless_enabled(self, memory: Memory) -> None:
        bridge = Bridge(
            memory,
            config=MemoryRuntimeConfig(
                capture={"include_roles": ["tool"], "include_tool_results": False, "min_message_chars": 0}
            ),
        )
        resp = bridge.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "capture",
                "params": {
                    "host": "openclaw",
                    "events": [
                        {
                            "event_type": "tool_result",
                            "content": "tool result content long enough",
                            "payload": {"role": "tool"},
                        },
                    ],
                },
            }
        )
        assert resp["result"]["accepted"] == 0
        assert memory.list_raw(limit=10) == []

    def test_store_raw_content_false_replaces_content(self, memory: Memory) -> None:
        bridge = Bridge(
            memory,
            config=MemoryRuntimeConfig(
                capture={"min_message_chars": 0},
                privacy={"store_raw_content": False},
            ),
        )
        resp = bridge.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "capture",
                "params": {
                    "host": "openclaw",
                    "events": [
                        {"event_type": "user_message", "content": "secret project content", "payload": {"role": "user"}}
                    ],
                },
            }
        )
        assert resp["result"]["accepted"] == 1
        event = memory.list_raw(limit=1)[0]
        assert event.content == "[raw content disabled by privacy.store_raw_content=false]"
        assert event.payload["content_redacted"] is True

    def test_redacts_secrets_and_custom_patterns(self, memory: Memory) -> None:
        bridge = Bridge(
            memory,
            config=MemoryRuntimeConfig(
                capture={"min_message_chars": 0},
                privacy={"redact_secrets": True, "redact_patterns": ["project-[0-9]+"]},
            ),
        )
        resp = bridge.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "capture",
                "params": {
                    "host": "openclaw",
                    "events": [
                        {
                            "event_type": "user_message",
                            "content": "token sk-test1234567890 belongs to project-12345",
                            "payload": {"role": "user", "api_key": "sk-test1234567890"},
                        }
                    ],
                },
            }
        )
        assert resp["result"]["accepted"] == 1
        event = memory.list_raw(limit=1)[0]
        assert "sk-test" not in event.content
        assert "project-12345" not in event.content
        assert "[REDACTED]" in event.content
        assert event.payload == {"role": "user"}

    def test_default_threshold_accepts_short_chinese(self, memory: Memory) -> None:
        """Default ``min_message_chars=12`` lets ≥3 CJK chars (e.g. '你好啊') pass."""
        bridge = Bridge(memory)  # rely on DEFAULT_CAPTURE_CFG
        resp = bridge.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "capture",
                "params": {
                    "host": "openclaw",
                    "events": [
                        {"event_type": "user_message", "content": "你好啊", "payload": {"role": "user"}},
                        {"event_type": "user_message", "content": "嗯", "payload": {"role": "user"}},
                    ],
                },
            }
        )
        assert resp["result"]["accepted"] == 1
        assert resp["result"]["skipped_too_short"] == 1
        events = memory.list_raw(limit=10)
        assert len(events) == 1
        assert events[0].content == "你好啊"

    def test_strips_think_tags_before_storing(self, memory: Memory) -> None:
        """``<think>...</think>`` reasoning blocks are removed before persistence."""
        bridge = Bridge(memory, config=MemoryRuntimeConfig(capture={"min_message_chars": 0}))
        resp = bridge.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "capture",
                "params": {
                    "host": "openclaw",
                    "events": [
                        {
                            "event_type": "assistant_message",
                            "content": "<think>internal scratchpad</think>用户的实际回答",
                            "payload": {"role": "assistant"},
                        },
                    ],
                },
            }
        )
        assert resp["result"]["accepted"] == 1
        event = memory.list_raw(limit=1)[0]
        assert "<think>" not in event.content
        assert "scratchpad" not in event.content
        assert event.content == "用户的实际回答"

    def test_strips_partial_think_tags(self, memory: Memory) -> None:
        """Streaming truncation may drop either the opening or closing tag.

        Regression for RISK-019: real raw_events captured both shapes,
        and the previous paired-only regex let them through.
        """
        from octop_memory.application.runtime import _strip_think_tags

        # Shape 1: streaming dropped the opening <think>, only </think> remains.
        assert _strip_think_tags("</think>\n\n哦，听起来不错 ☕") == "哦，听起来不错 ☕"
        # Shape 2: streaming dropped the closing </think>, opening tag and the
        # entire scratchpad spill to end of string.
        assert _strip_think_tags("<think>The user is sharing a casual detail") == ""
        # Sanity: paired blocks still work.
        assert _strip_think_tags("<think>x</think>Y") == "Y"
        # Sanity: content without any think tag is untouched.
        assert _strip_think_tags("just a normal reply") == "just a normal reply"

    def test_partial_think_tags_do_not_leak_to_db(self, memory: Memory) -> None:
        """End-to-end: capture path must not persist orphan ``<think>``/``</think>``."""
        bridge = Bridge(memory, config=MemoryRuntimeConfig(capture={"min_message_chars": 0}))
        resp = bridge.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "capture",
                "params": {
                    "host": "openclaw",
                    "events": [
                        {
                            "event_type": "assistant_message",
                            "content": "</think>\n\n哦，芭乐茉莉乌龙听起来不错 ☕",
                            "payload": {"role": "assistant"},
                        },
                        {
                            "event_type": "assistant_message",
                            "content": "<think>The user is sharing a casual detail about a drink",
                            "payload": {"role": "assistant"},
                        },
                    ],
                },
            }
        )
        # First event keeps the visible reply, second event becomes empty
        # and is dropped (empty content fails the min-chars / non-empty guard).
        assert resp["result"]["accepted"] >= 1
        for event in memory.list_raw(limit=10):
            assert "<think" not in event.content.lower()
            assert "</think>" not in event.content.lower()


class TestProbe:
    """`--probe` is the pre-flight check used by setup/doctor."""

    def test_probe_reports_env_and_exits_zero_with_fts5(self, capsys: pytest.CaptureFixture[str]) -> None:
        from octop_memory.adapters.bridge.server import main

        # --probe must run without --namespace and without touching a store.
        rc = main(["--probe"])
        out = json.loads(capsys.readouterr().out.strip())
        # CPython used to run the suite ships FTS5, so this is the happy path.
        assert rc == 0
        assert out["ok"] is True
        assert out["fts5"] is True
        assert out["protocol_version"] == PROTOCOL_VERSION
        assert out["sqlite_version"]
        assert out["octop_memory_version"]
