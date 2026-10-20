"""Tests for MemoryMiddleware."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from octop_harness.middleware.memory import MemoryMiddleware


class _SpyService:
    def __init__(self) -> None:
        self.capture_calls: list[dict[str, Any]] = []
        self.extract_calls: list[dict[str, Any]] = []
        self.recall_calls: list[dict[str, Any]] = []
        self._capture_event = threading.Event()

    def recall(
        self,
        query: str,
        *,
        thread_id: str | None = None,
        session_id: str | None = None,
        limit: int = 5,
    ) -> MagicMock:
        self.recall_calls.append({"query": query, "thread_id": thread_id, "session_id": session_id, "limit": limit})
        return MagicMock(rendered="")

    def capture_turn(self, **kwargs: Any) -> dict[str, Any]:
        self.capture_calls.append(kwargs)
        self._capture_event.set()
        return {"ok": True}

    def extract(self, session_id: str, **kwargs: Any) -> dict[str, Any]:
        self.extract_calls.append({"session_id": session_id, **kwargs})
        return {}

    def wait_for_capture(self, timeout: float = 2.0) -> bool:
        return self._capture_event.wait(timeout)


@pytest.fixture
def service() -> _SpyService:
    return _SpyService()


@pytest.fixture
def mw(service: _SpyService, tmp_path: Path) -> MemoryMiddleware:
    return MemoryMiddleware(service=service, jsonl_enabled=True, jsonl_dir=tmp_path / "logs")  # type: ignore[arg-type]


def _make_state(messages: list[Any]) -> dict[str, Any]:
    return {"messages": messages}


def _make_runtime(thread_id: str = "t1", user: str = "alice") -> MagicMock:
    runtime = MagicMock()
    runtime.config = {"configurable": {"thread_id": thread_id, "user": user, "source": "test"}}
    return runtime


class TestMemoryMiddleware:
    def test_failed_team_notification_is_only_logged(
        self, mw: MemoryMiddleware, service: _SpyService, tmp_path: Path
    ) -> None:
        from langchain_core.messages import AIMessage, HumanMessage

        runtime = _make_runtime()
        runtime.config["configurable"]["octop_memory_capture_exclude"] = True
        user = HumanMessage(content="System task notification: child failed authentication (401).")
        reply = AIMessage(content="The member failed. Please update its credentials.")
        mw.before_model(_make_state([user]), runtime)
        mw.after_model(_make_state([user, reply]), runtime)
        assert service.capture_calls == []
        assert any("401" in path.read_text() for path in (tmp_path / "logs").rglob("*.jsonl"))

    def test_runtime_error_keeps_user_input_without_capturing_error(
        self, mw: MemoryMiddleware, service: _SpyService, tmp_path: Path
    ) -> None:
        from langchain_core.messages import AIMessage, HumanMessage

        user_msg = HumanMessage(content="记住: 排障时先检查服务状态。")
        failure = AIMessage(
            content="Model call failed after 3 attempts with AuthenticationError: 401 token_expired",
            response_metadata={"octop_runtime_error": True},
        )
        runtime = _make_runtime()
        mw.before_model(_make_state([user_msg]), runtime)
        mw.after_model(_make_state([user_msg, failure]), runtime)

        assert service.wait_for_capture()
        assert service.capture_calls[0]["user"] == user_msg.content
        assert service.capture_calls[0]["assistant"] is None
        logs = list((tmp_path / "logs").rglob("*.jsonl"))
        assert any("token_expired" in path.read_text() for path in logs)

    def test_after_model_captures_visible_turn(self, mw: MemoryMiddleware, service: _SpyService) -> None:
        from langchain_core.messages import AIMessage, HumanMessage

        user_msg = HumanMessage(content="What is memory?")
        ai_msg = AIMessage(content="Memory is a system for storing information.")
        runtime = _make_runtime()

        mw.before_model(_make_state([user_msg]), runtime)
        mw.after_model(_make_state([user_msg, ai_msg]), runtime)

        assert service.wait_for_capture()
        assert service.capture_calls == [
            {
                "user": "What is memory?",
                "assistant": "Memory is a system for storing information.",
                "session_id": "t1",
                "thread_id": "t1",
                "user_id": "alice",
            },
        ]

    def test_jsonl_file_written(self, mw: MemoryMiddleware, tmp_path: Path) -> None:
        from langchain_core.messages import AIMessage, HumanMessage

        user_msg = HumanMessage(content="Hello")
        ai_msg = AIMessage(content="Hi!")
        runtime = _make_runtime()

        mw.before_model(_make_state([user_msg]), runtime)
        mw.after_model(_make_state([user_msg, ai_msg]), runtime)

        log_dir = tmp_path / "logs"
        jsonl_files = list(log_dir.glob("*.jsonl"))
        assert len(jsonl_files) >= 1

    def test_jsonl_disabled_still_captures_service_turn(self, service: _SpyService) -> None:
        from langchain_core.messages import AIMessage, HumanMessage

        mw = MemoryMiddleware(service=service, jsonl_enabled=False)  # type: ignore[arg-type]
        user_msg = HumanMessage(content="Hi")
        ai_msg = AIMessage(content="Hello")
        runtime = _make_runtime()

        mw.before_model(_make_state([user_msg]), runtime)
        mw.after_model(_make_state([user_msg, ai_msg]), runtime)

        assert service.wait_for_capture()
        assert service.capture_calls[0]["user"] == "Hi"
        assert service.capture_calls[0]["assistant"] == "Hello"

    def test_jsonl_only_mode_does_not_capture(self, tmp_path: Path) -> None:
        from langchain_core.messages import AIMessage, HumanMessage

        mw = MemoryMiddleware(jsonl_enabled=True, jsonl_dir=tmp_path / "logs")
        user_msg = HumanMessage(content="Hi")
        ai_msg = AIMessage(content="Hello")
        runtime = _make_runtime()

        mw.before_model(_make_state([user_msg]), runtime)
        mw.after_model(_make_state([user_msg, ai_msg]), runtime)

        assert list((tmp_path / "logs").glob("*.jsonl"))

    def test_no_messages_no_capture(self, mw: MemoryMiddleware, service: _SpyService) -> None:
        state = _make_state([])
        runtime = _make_runtime()

        mw.before_model(state, runtime)
        mw.after_model(state, runtime)

        time.sleep(0.05)
        assert service.capture_calls == []

    def test_filter_drops_tool_calls_and_intermediate_ai(
        self,
        mw: MemoryMiddleware,
        service: _SpyService,
    ) -> None:
        """Only the user prompt and the final tool-call-free AIMessage are captured."""
        from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

        user = HumanMessage(content="What's the weather in Beijing?")
        intermediate_ai = AIMessage(
            content="",
            tool_calls=[{"name": "web_fetch", "args": {"url": "x"}, "id": "call_1"}],
        )
        tool_result = ToolMessage(content="sunny, 22C", tool_call_id="call_1")
        final_ai = AIMessage(content="Beijing is sunny, 22°C.")
        runtime = _make_runtime(thread_id="weather-thread")

        mw.before_model(_make_state([user]), runtime)
        mw.after_model(_make_state([user, intermediate_ai, tool_result, final_ai]), runtime)

        assert service.wait_for_capture()
        call = service.capture_calls[0]
        assert call["user"] == "What's the weather in Beijing?"
        assert call["assistant"] == "Beijing is sunny, 22°C."
        assert call["thread_id"] == "weather-thread"

    def test_multiple_human_messages_are_joined(
        self,
        mw: MemoryMiddleware,
        service: _SpyService,
    ) -> None:
        from langchain_core.messages import AIMessage, HumanMessage

        u1 = HumanMessage(content="First prompt")
        u2 = HumanMessage(content="Follow-up inside the same turn")
        a = AIMessage(content="Combined reply")
        runtime = _make_runtime(thread_id="multi-human")

        mw.before_model(_make_state([u1]), runtime)
        mw.after_model(_make_state([u1, u2, a]), runtime)

        assert service.wait_for_capture()
        call = service.capture_calls[0]
        assert call["user"] == "First prompt\n\nFollow-up inside the same turn"
        assert call["assistant"] == "Combined reply"

    def test_turn_with_only_tool_calls_captures_nothing(
        self,
        mw: MemoryMiddleware,
        service: _SpyService,
    ) -> None:
        from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

        prior_user = HumanMessage(content="Search for X")
        ai_with_call = AIMessage(
            content="",
            tool_calls=[{"name": "web_fetch", "args": {}, "id": "c1"}],
        )
        tool_msg = ToolMessage(content="result", tool_call_id="c1")
        runtime = _make_runtime(thread_id="tool-only")

        mw.before_model(_make_state([prior_user]), runtime)
        mw.after_model(_make_state([prior_user, ai_with_call, tool_msg]), runtime)

        time.sleep(0.05)
        assert service.capture_calls == []


class TestToolTurnUserCapture:
    """A prompt that triggers tool use must still reach the memory store.

    Regression: ``after_model`` located the trigger prompt with a strict
    ``messages[cursor - 1]`` check. On a turn's second step that slot holds a
    ``ToolMessage``, so the prompt was dropped — and the first step had
    already discarded it (tool_calls only, no final reply to pair with), so
    it was lost for good. Every instruction that made the agent use a tool
    went unrecorded.
    """

    def test_tool_turn_captures_user_prompt(self, mw: MemoryMiddleware, service: _SpyService) -> None:
        from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

        user = HumanMessage(content="帮我打开")
        ai_call = AIMessage(content="", tool_calls=[{"name": "open_file", "args": {}, "id": "c1"}])
        tool = ToolMessage(content="opened", tool_call_id="c1")
        final = AIMessage(content="已经打开了")
        runtime = _make_runtime(thread_id="tool-turn")

        # Step 1: prompt in, model only emits tool_calls -> nothing captured yet.
        mw.before_model(_make_state([user]), runtime)
        mw.after_model(_make_state([user, ai_call, tool]), runtime)
        time.sleep(0.05)
        assert service.capture_calls == []

        # Step 2: tool result is at cursor-1, final reply arrives.
        mw.before_model(_make_state([user, ai_call, tool]), runtime)
        mw.after_model(_make_state([user, ai_call, tool, final]), runtime)

        assert service.wait_for_capture()
        assert len(service.capture_calls) == 1
        call = service.capture_calls[0]
        assert call["user"] == "帮我打开"
        assert call["assistant"] == "已经打开了"

    def test_multi_step_tool_turn_captures_prompt_once(self, mw: MemoryMiddleware, service: _SpyService) -> None:
        from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

        user = HumanMessage(content="调研并写报告")
        c1 = AIMessage(content="", tool_calls=[{"name": "search", "args": {}, "id": "a"}])
        t1 = ToolMessage(content="hits", tool_call_id="a")
        c2 = AIMessage(content="", tool_calls=[{"name": "write_file", "args": {}, "id": "b"}])
        t2 = ToolMessage(content="written", tool_call_id="b")
        final = AIMessage(content="报告写好了")
        runtime = _make_runtime(thread_id="multi-step")

        history = [user]
        for produced in ([c1, t1], [c2, t2], [final]):
            mw.before_model(_make_state(list(history)), runtime)
            history.extend(produced)
            mw.after_model(_make_state(list(history)), runtime)

        assert service.wait_for_capture()
        assert len(service.capture_calls) == 1, "prompt must be captured exactly once"
        assert service.capture_calls[0]["user"] == "调研并写报告"
        assert service.capture_calls[0]["assistant"] == "报告写好了"

    def test_does_not_reach_into_previous_turn(self, mw: MemoryMiddleware, service: _SpyService) -> None:
        """A turn with no prompt of its own must not re-capture the last one."""
        from langchain_core.messages import AIMessage, HumanMessage

        prev_user = HumanMessage(content="上一轮的问题")
        prev_reply = AIMessage(content="上一轮的回答")
        new_reply = AIMessage(content="没有新提问的回复")
        runtime = _make_runtime(thread_id="no-prompt")

        mw.before_model(_make_state([prev_user, prev_reply]), runtime)
        mw.after_model(_make_state([prev_user, prev_reply, new_reply]), runtime)

        assert service.wait_for_capture()
        assert len(service.capture_calls) == 1
        assert service.capture_calls[0]["user"] is None, "must not borrow the previous turn's prompt"

    def test_jsonl_does_not_duplicate_prompt_across_steps(self, mw: MemoryMiddleware, tmp_path: Path) -> None:
        """JSONL writes per step, so the prompt must appear exactly once."""
        import json

        from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

        user = HumanMessage(content="帮我部署")
        ai_call = AIMessage(content="", tool_calls=[{"name": "deploy", "args": {}, "id": "d1"}])
        tool = ToolMessage(content="ok", tool_call_id="d1")
        final = AIMessage(content="部署好了")
        runtime = _make_runtime(thread_id="jsonl-dup")

        mw.before_model(_make_state([user]), runtime)
        mw.after_model(_make_state([user, ai_call, tool]), runtime)
        mw.before_model(_make_state([user, ai_call, tool]), runtime)
        mw.after_model(_make_state([user, ai_call, tool, final]), runtime)

        lines = [
            json.loads(line)
            for path in (tmp_path / "logs").glob("*.jsonl")
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        users = [entry for entry in lines if entry.get("role") == "user"]
        assert len(users) == 1, f"prompt duplicated in JSONL: {users}"
        assert users[0]["content"] == "帮我部署"


class TestIntervalExtract:
    """Fixed-interval sweep timer (mode='interval')."""

    def test_interval_sweeps_tracked_sessions(self, service: _SpyService) -> None:
        from langchain_core.messages import AIMessage, HumanMessage

        # Tiny interval so the timer fires within the test.
        mw = MemoryMiddleware(
            service=service,  # type: ignore[arg-type]
            jsonl_enabled=False,
            extract_interval_seconds=0.15,
        )
        try:
            # Two sessions become "tracked" via after_model captures.
            for tid in ("s-a", "s-b"):
                rt = _make_runtime(thread_id=tid)
                mw.before_model(_make_state([HumanMessage(content="hi")]), rt)
                mw.after_model(
                    _make_state([HumanMessage(content="hi"), AIMessage(content="yo")]),
                    rt,
                )
                assert service.wait_for_capture()

            # Wait for at least one sweep to fire + background extract to run.
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                if {c["session_id"] for c in service.extract_calls} >= {"s-a", "s-b"}:
                    break
                time.sleep(0.02)
            extracted = {c["session_id"] for c in service.extract_calls}
            assert extracted >= {"s-a", "s-b"}
        finally:
            mw.shutdown()

    def test_shutdown_stops_interval_timer(self, service: _SpyService) -> None:
        mw = MemoryMiddleware(
            service=service,  # type: ignore[arg-type]
            jsonl_enabled=False,
            extract_interval_seconds=0.1,
        )
        mw.shutdown()
        # After shutdown the timer must not re-arm; no sweeps accumulate.
        before = len(service.extract_calls)
        time.sleep(0.3)
        assert len(service.extract_calls) == before

    def test_interval_disabled_by_default(self, service: _SpyService) -> None:
        mw = MemoryMiddleware(service=service, jsonl_enabled=False)  # type: ignore[arg-type]
        assert mw._interval_timer is None


class TestRecallInjectScope:
    def test_inject_forwards_session_and_thread(self, service: _SpyService) -> None:
        from langchain_core.messages import HumanMessage

        mw = MemoryMiddleware(service=service, jsonl_enabled=False)  # type: ignore[arg-type]
        runtime = MagicMock()
        runtime.config = {
            "configurable": {"thread_id": "thr-1", "session_id": "sess-A"},
        }
        update = mw.before_model({"messages": [HumanMessage(content="what did we decide")]}, runtime)
        assert update is not None
        assert service.recall_calls == [
            {
                "query": "what did we decide",
                "thread_id": "thr-1",
                "session_id": "sess-A",
                "limit": 5,
            }
        ]


class TestRecallFallback:
    def test_wrap_model_call_survives_recall_crash(self) -> None:
        from langchain_core.messages import HumanMessage

        class _BoomService:
            def recall(self, *args: Any, **kwargs: Any) -> Any:
                raise Exception("InvalidSubscription")

        mw = MemoryMiddleware(service=_BoomService(), jsonl_enabled=False)  # type: ignore[arg-type]
        request = MagicMock()
        update = mw.before_model({"messages": [HumanMessage(content="remember this")]}, None)
        assert update is not None
        request.messages = update["messages"]
        request.system_prompt = "sys"
        handler = MagicMock(return_value="ok")

        assert mw.wrap_model_call(request, handler) == "ok"
        handler.assert_called_once()


class TestIdleMaintenance:
    """Dedicated slimming timer (ADR-027). Off unless the host opts in."""

    def test_disabled_by_default(self, service: _SpyService) -> None:
        mw = MemoryMiddleware(service=service, jsonl_enabled=False)  # type: ignore[arg-type]
        assert mw._maintenance_timer is None

    def test_maintenance_status_starts_idle(self, service: _SpyService) -> None:
        mw = MemoryMiddleware(service=service, jsonl_enabled=False)  # type: ignore[arg-type]
        status = mw.maintenance_status()
        assert status["phase"] == "idle"
        assert status["percent"] == 0
        mw._set_status(phase="compacting", file_bytes=4096)
        updated = mw.maintenance_status()
        assert updated["phase"] == "compacting"
        assert updated["percent"] == 68
        assert updated["file_bytes"] == 4096
        assert mw._maintenance_blocks_io() is True

    def test_runtime_enables_hourly_maintenance(self, tmp_path: Path) -> None:
        from octop_harness.config import HarnessAgentConfig
        from octop_harness.memory.runtime import MemoryRuntime

        cfg = HarnessAgentConfig(
            name="t",
            workspace_dir=tmp_path,
            memory_aux_model_enabled=False,
            session_log_enabled=False,
        )
        runtime = MemoryRuntime(
            config=cfg,
            workspace_path=tmp_path,
            model_factory=MagicMock(),
        )
        try:
            mw = runtime.build_middleware()
            assert mw is not None
            assert mw._maintenance_interval_seconds == 3600.0
            assert mw._maintenance_initial_delay_seconds == 1.0
            assert mw._maintenance_timer is not None
        finally:
            runtime.close()

    def test_timer_fires_and_shutdown_stops_it(self, service: _SpyService) -> None:
        hits: list[object] = []
        mw = MemoryMiddleware(
            service=service,  # type: ignore[arg-type]
            jsonl_enabled=False,
            maintenance_interval_seconds=0.15,
            maintenance_initial_delay_seconds=0.05,
        )
        mw._submit_maintenance = lambda **_: hits.append(True)  # type: ignore[method-assign]
        try:
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                if hits:
                    break
                time.sleep(0.02)
            assert hits, "maintenance timer never fired"
        finally:
            mw.shutdown()
        after = len(hits)
        time.sleep(0.35)
        assert len(hits) == after

    def test_first_and_later_ticks_only_submit_cheap_maintenance(self, service: _SpyService) -> None:
        hits: list[object] = []
        mw = MemoryMiddleware(
            service=service,  # type: ignore[arg-type]
            jsonl_enabled=False,
            maintenance_interval_seconds=3600.0,
            maintenance_initial_delay_seconds=3600.0,
        )
        mw._submit_maintenance = lambda: hits.append(True)  # type: ignore[method-assign]
        try:
            mw._on_maintenance()
            mw._on_maintenance()
            assert hits == [True, True]
        finally:
            mw.shutdown()

    def test_idle_extract_also_kicks_maintenance(self, service: _SpyService) -> None:
        hits: list[object] = []
        mw = MemoryMiddleware(
            service=service,  # type: ignore[arg-type]
            jsonl_enabled=False,
            extract_idle_seconds=0.05,
            maintenance_interval_seconds=3600.0,
            maintenance_initial_delay_seconds=3600.0,
        )
        mw._submit_maintenance = lambda **_: hits.append(True)  # type: ignore[method-assign]
        try:
            mw._on_idle_extract("sess-1")
            assert hits == [True]
        finally:
            mw.shutdown()

    def test_background_submit_keeps_log_agent_only(self) -> None:
        """Background work inherits the log agent id, not the HTTP session scope."""
        from octop_harness.llm.session_header import current_session_id, session_header_scope
        from octop_harness.middleware.memory import _BackgroundExecutor
        from octop_harness.observability.logging import current_log_agent_id, logging_scope

        seen: dict[str, object] = {}
        done = threading.Event()

        def _fn() -> None:
            seen["agent"] = current_log_agent_id()
            seen["session"] = current_session_id()
            done.set()

        with session_header_scope("thread-1"), logging_scope("AGT1"):
            _BackgroundExecutor().submit(_fn, label="log-scope")
        assert done.wait(2)
        assert seen["agent"] == "AGT1"
        assert seen["session"] != "thread-1"

    def test_maintenance_runs_gc_and_nudge_without_prune(
        self, service: _SpyService, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A tick reclaims space but never deletes LangGraph checkpoints."""
        import sys
        import types

        service.memory = object()  # type: ignore[attr-defined]
        calls: list[str] = []

        def _fake_gc(_memory: object, **_kwargs: object) -> Any:
            calls.append("run_gc")
            stats = MagicMock()
            stats.total_deleted = 3
            return stats

        seen_pages: list[object] = []

        def _fake_nudge(_memory: object, **kwargs: object) -> Any:
            calls.append("nudge_vacuum")
            seen_pages.append(kwargs.get("pages"))
            stats = MagicMock()
            stats.pages_reclaimed = 7
            stats.auto_vacuum_enabled = True
            return stats

        def _fail(*_args: object, **_kwargs: object) -> Any:
            raise AssertionError("checkpoint prune must not run from maintenance")

        fake = types.ModuleType("octop_memory.pipeline.lifecycle")
        fake.run_gc = _fake_gc  # type: ignore[attr-defined]
        fake.nudge_vacuum = _fake_nudge  # type: ignore[attr-defined]
        fake.run_idle_maintenance = _fail  # type: ignore[attr-defined]
        fake.prune_checkpoints = _fail  # type: ignore[attr-defined]
        fake.maybe_bootstrap_incremental = _fail  # type: ignore[attr-defined]
        fake.compact_vacuum = _fail  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "octop_memory.pipeline.lifecycle", fake)
        mw = MemoryMiddleware(service=service, jsonl_enabled=False)  # type: ignore[arg-type]
        try:
            mw._run_maintenance_tick(service)
            assert calls == ["run_gc", "nudge_vacuum"]
            from octop_harness.middleware.memory import _MAINTENANCE_VACUUM_PAGES

            assert seen_pages == [_MAINTENANCE_VACUUM_PAGES]
        finally:
            mw.shutdown()


class TestChatModelCallback:
    def test_after_model_notifies_live_chat_model(self, service: _SpyService) -> None:
        from langchain_core.messages import AIMessage, HumanMessage

        seen: list[str] = []
        mw = MemoryMiddleware(
            service=service,
            jsonl_enabled=False,
            on_chat_model=seen.append,
        )
        runtime = _make_runtime()
        runtime.config["configurable"]["model"] = "dashscope/qwen"

        user_msg = HumanMessage(content="hi")
        ai_msg = AIMessage(content="hello")
        mw.before_model(_make_state([user_msg]), runtime)
        mw.after_model(_make_state([user_msg, ai_msg]), runtime)

        assert seen == ["dashscope/qwen"]


class TestRebuildKeepsOneMaintenanceBeat:
    """A graph recompile must not arm a second (leaked) maintenance timer."""

    def _runtime(self, tmp_path: Path) -> Any:
        from octop_harness.config import HarnessAgentConfig
        from octop_harness.memory.runtime import MemoryRuntime

        cfg = HarnessAgentConfig(
            name="t",
            workspace_dir=tmp_path,
            memory_aux_model_enabled=False,
            session_log_enabled=False,
        )
        return MemoryRuntime(config=cfg, workspace_path=tmp_path, model_factory=MagicMock())

    def test_recompile_reuses_the_running_middleware(self, tmp_path: Path) -> None:
        runtime = self._runtime(tmp_path)
        try:
            first = runtime.build_middleware()
            second = runtime.build_middleware()
            assert first is not None
            assert second is first, "recompile built a second middleware — timers leak"
            assert first._maintenance_timer is not None
            assert not first._maintenance_stopped
        finally:
            runtime.close()

    def test_config_change_retires_the_old_timers(self, tmp_path: Path) -> None:
        runtime = self._runtime(tmp_path)
        try:
            first = runtime.build_middleware()
            assert first is not None
            runtime._config.memory_capture_enabled = not runtime._config.memory_capture_enabled
            second = runtime.build_middleware()
            assert second is not first
            assert first._maintenance_stopped is True
            assert first._maintenance_timer is None
            assert second is not None
            assert second._maintenance_timer is not None
        finally:
            runtime.close()


class TestMaintenanceLogVolume:
    """An idle tick is DEBUG; only real work or a real failure is INFO."""

    @staticmethod
    def _stats(deleted: int, pages: int) -> tuple[Any, Any]:
        gc_stats = MagicMock()
        gc_stats.total_deleted = deleted
        vacuum = MagicMock()
        vacuum.pages_reclaimed = pages
        vacuum.auto_vacuum_enabled = True
        return gc_stats, vacuum

    def _run(self, caplog: pytest.LogCaptureFixture, *, deleted: int, pages: int) -> list[Any]:
        gc_stats, vacuum = self._stats(deleted, pages)
        with caplog.at_level("DEBUG", logger="octop_harness.middleware.memory"):
            MemoryMiddleware._run_reclaim_pass(
                object(),
                run_gc=lambda _m: gc_stats,
                nudge_vacuum=lambda _m: vacuum,
            )
        return [r for r in caplog.records if "maintenance done" in r.getMessage()]

    def test_empty_tick_is_debug(self, caplog: pytest.LogCaptureFixture) -> None:
        records = self._run(caplog, deleted=0, pages=0)
        assert [r.levelname for r in records] == ["DEBUG"]

    def test_tick_that_reclaimed_is_info(self, caplog: pytest.LogCaptureFixture) -> None:
        records = self._run(caplog, deleted=0, pages=12)
        assert [r.levelname for r in records] == ["INFO"]

    def test_missing_namespace_tables_is_a_skip_not_a_traceback(self, caplog: pytest.LogCaptureFixture) -> None:
        # Name matters: the skip check keys off psycopg's exception type name.
        class UndefinedTable(Exception):  # noqa: N818
            pass

        def _boom(_memory: object) -> Any:
            raise UndefinedTable('relation "agent_x_atoms" does not exist')

        _gc, vacuum = self._stats(0, 0)
        with caplog.at_level("DEBUG", logger="octop_harness.middleware.memory"):
            MemoryMiddleware._run_reclaim_pass(
                object(),
                run_gc=_boom,
                nudge_vacuum=lambda _m: vacuum,
            )
        assert not [r for r in caplog.records if r.levelname == "WARNING"]
        done = [r for r in caplog.records if "maintenance done" in r.getMessage()]
        assert [r.levelname for r in done] == ["DEBUG"]

    def test_real_gc_failure_still_warns(self, caplog: pytest.LogCaptureFixture) -> None:
        def _boom(_memory: object) -> Any:
            raise RuntimeError("disk on fire")

        _gc, vacuum = self._stats(0, 0)
        with caplog.at_level("DEBUG", logger="octop_harness.middleware.memory"):
            MemoryMiddleware._run_reclaim_pass(
                object(),
                run_gc=_boom,
                nudge_vacuum=lambda _m: vacuum,
            )
        assert [r for r in caplog.records if r.levelname == "WARNING"]
        done = [r for r in caplog.records if "maintenance done" in r.getMessage()]
        assert [r.levelname for r in done] == ["INFO"]


class TestSharedStoreCoalescing:
    """Agents bound to one shared Memory reclaim it once, not once each."""

    def test_second_agent_skips_a_just_reclaimed_store(self) -> None:
        from octop_harness.middleware import memory as memory_mod

        shared = _SpyService()
        shared.memory = MagicMock()  # type: ignore[attr-defined]
        calls: list[str] = []

        def _pass(_memory: Any, **_kwargs: Any) -> None:
            calls.append("pass")

        mws = [
            MemoryMiddleware(
                service=shared,  # type: ignore[arg-type]
                jsonl_enabled=False,
                maintenance_interval_seconds=3600.0,
                maintenance_initial_delay_seconds=3600.0,
            )
            for _ in range(3)
        ]
        try:
            with patch.object(memory_mod.MemoryMiddleware, "_run_reclaim_pass", staticmethod(_pass)):
                for mw in mws:
                    mw._run_maintenance_tick(shared)
            assert calls == ["pass"], "each agent reclaimed the same store again"
        finally:
            for mw in mws:
                mw.shutdown()

    def test_distinct_stores_each_get_a_pass(self) -> None:
        from octop_harness.middleware import memory as memory_mod

        calls: list[Any] = []

        def _pass(memory: Any, **_kwargs: Any) -> None:
            calls.append(memory)

        services = []
        for _ in range(3):
            svc = _SpyService()
            svc.memory = MagicMock()  # type: ignore[attr-defined]
            services.append(svc)
        mw = MemoryMiddleware(
            service=services[0],  # type: ignore[arg-type]
            jsonl_enabled=False,
            maintenance_interval_seconds=3600.0,
            maintenance_initial_delay_seconds=3600.0,
        )
        try:
            with patch.object(memory_mod.MemoryMiddleware, "_run_reclaim_pass", staticmethod(_pass)):
                for svc in services:
                    mw._run_maintenance_tick(svc)
            assert len(calls) == 3
        finally:
            mw.shutdown()
