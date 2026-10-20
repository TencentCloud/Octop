"""``MemoryMiddleware`` — capture conversations through MemoryService and/or JSONL.

Hooks the langgraph model loop to:

1. **Snapshot recalled snippets** on each new user message (``before_model``),
   then replay them on API copies of messages (``wrap_model_call``). The system
   prompt stays unchanged and checkpoints preserve earlier recall verbatim.
2. **Capture the turn** as L0 raw events after each model call
   (``after_model``) through :class:`MemoryService.capture_turn` when
   a service is bound.
3. **Append a daily JSONL log** under ``jsonl_dir`` for ops debugging.

The MemoryService and JSONL sinks are independent; either can be used on
its own. Capture runs on background threads; recall is synchronous before the
first model call of a user turn, then reused through tool calls and resumes.

Fail-soft: any IO / RPC error during write or recall is logged at
``WARNING`` and never raised.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import weakref
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from octop_harness.middleware.memory_recall import (
    has_recall_snapshot,
    replay_recall_snapshots,
    stamp_recall_snapshot,
)

# ~20MB at the default 4KB page size. Matches
# octop_memory.pipeline.lifecycle.vacuum.MAINTENANCE_INCREMENTAL_VACUUM_PAGES.
# Kept local so a host can pass it to an already-installed octop-memory
# whose ``nudge_vacuum`` accepts ``pages`` but does not export the constant yet.
_MAINTENANCE_VACUUM_PAGES = 5000

if TYPE_CHECKING:
    from langchain.agents.middleware.types import ModelRequest, ModelResponse
    from octop_memory import MemoryService

logger = logging.getLogger(__name__)

# Background pool for capture / extract — small, single-purpose. We do NOT
# use the agent's main asyncio loop because middleware hooks run in mixed
# sync/async contexts and capture must keep working even when called from
# a sync hook on a synchronous test setup.
_BG_LOCK = threading.Lock()
_BG_POOL: _BackgroundExecutor | None = None
_IO_BLOCKING_PHASES = frozenset({"pruning", "compacting"})
_VISIBLE_PHASES = frozenset({"queued", "pruning", "compacting"})
_PHASE_PERCENT = {
    "idle": 0,
    "queued": 8,
    "pruning": 32,
    "compacting": 68,
    "done": 100,
    "skipped": 100,
}

# Last reclaim pass per ``Memory`` instance, so several middlewares bound to
# the *same* store (one shared Memory per namespace + DSN — see
# ``octop_harness.memory.store``) coalesce into one tick instead of each
# running GC over the same rows. Weak-keyed: an entry dies with its Memory.
_LAST_RECLAIM: weakref.WeakKeyDictionary[Any, float] = weakref.WeakKeyDictionary()
_LAST_RECLAIM_LOCK = threading.Lock()


def _claim_reclaim_slot(memory: Any, *, window: float) -> bool:
    """True when this caller may reclaim ``memory`` now.

    False when another middleware already ran a pass within ``window``
    seconds. Unhashable / non-weakrefable stores always get a slot.
    """
    if window <= 0:
        return True
    now = time.monotonic()
    try:
        with _LAST_RECLAIM_LOCK:
            previous = _LAST_RECLAIM.get(memory)
            if previous is not None and now - previous < window:
                return False
            _LAST_RECLAIM[memory] = now
    except TypeError:  # pragma: no cover - exotic Memory without weakref/hash
        return True
    return True


class _BackgroundExecutor:
    """Lightweight fire-and-forget thread runner with daemon threads.

    We avoid ``concurrent.futures.ThreadPoolExecutor`` so that test runs and
    short-lived agent processes don't have to pay attention to executor
    shutdown — daemon threads die with the interpreter. Tasks that fail are
    logged at ``WARNING`` and dropped.
    """

    def submit(self, fn: Callable[[], None], *, label: str) -> None:
        from octop_harness.observability.logging import current_log_agent_id, logging_scope

        agent_id = current_log_agent_id()

        def _runner() -> None:
            try:
                with logging_scope(agent_id):
                    fn()
            except Exception:  # pragma: no cover - never raise into the user turn; pylint: disable=broad-except
                logger.warning("MemoryMiddleware background %s failed", label, exc_info=True)

        threading.Thread(target=_runner, name=f"hm-{label}", daemon=True).start()


def _bg_pool() -> _BackgroundExecutor:
    global _BG_POOL  # noqa: PLW0603
    with _BG_LOCK:
        if _BG_POOL is None:
            _BG_POOL = _BackgroundExecutor()
        return _BG_POOL


class MemoryMiddleware(AgentMiddleware[Any, Any]):
    """Wire ``MemoryService`` / JSONL into the agent loop.

    Args:
        service: A :class:`MemoryService`. When set, the middleware uses
            the host lifecycle (``recall`` / ``capture_turn`` / ``extract``)
            on the read and write paths.
        recall_inject_enabled: When ``True`` and a service is bound, the
            middleware snapshots recall once per new user message. API copies
            append it to that message; historical snapshots always replay.
        recall_limit: Per-turn recall snippet cap. Forwarded to
            :meth:`MemoryService.recall`.
        capture_enabled: When ``True`` and a service is bound, the middleware
            captures each turn as L0 raw events via
            :meth:`MemoryService.capture_turn` after the model call. Run on a
            background thread so the user reply is never blocked.
        jsonl_enabled: Whether to additionally write a daily JSONL file
            under ``jsonl_dir``. Defaults to True.
        jsonl_dir: Destination directory for the daily ``YYYY-MM-DD.jsonl``
            files. Required when ``jsonl_enabled`` is True.
        jsonl_max_bytes: Soft size cap; on exceed, the active file is
            renamed to ``{date}.{N}.jsonl`` and a fresh one is started.
        on_chat_model: Optional callback with the live chat model ref after
            each turn, so extract can fall back when ``aux_model`` fails.
        maintenance_interval_seconds: When > 0 and a service is bound,
            run cheap DB maintenance (lifecycle GC + nudge vacuum) on this
            cadence. Default 0 so one-shot middleware (tests, throwaway
            ``end_session``) does not start a timer. Hosts that want
            unattended slimming pass a positive value from
            ``MemoryRuntime.build_middleware``.
        maintenance_initial_delay_seconds: Delay before the first cheap
            maintenance tick. Hosts use ~1s so reclaim starts shortly after
            the service is bound.
    """

    @property
    def name(self) -> str:
        """Distinct name to avoid collision with deepagents' MemoryMiddleware."""
        return "HarnessMemoryMiddleware"

    def __init__(
        self,
        *,
        service: MemoryService | None = None,
        recall_inject_enabled: bool = True,
        recall_limit: int = 5,
        capture_enabled: bool = True,
        extract_idle_seconds: float = 0.0,
        extract_interval_seconds: float = 0.0,
        jsonl_enabled: bool = True,
        jsonl_dir: str | Path | None = None,
        jsonl_max_bytes: int = 50 * 1024 * 1024,
        on_chat_model: Callable[[str], None] | None = None,
        maintenance_interval_seconds: float = 0.0,
        maintenance_initial_delay_seconds: float = 60.0,
    ) -> None:
        super().__init__()
        if jsonl_max_bytes <= 0:
            raise ValueError("jsonl_max_bytes must be positive")
        if jsonl_enabled and jsonl_dir is None:
            raise ValueError("jsonl_dir must be set when jsonl_enabled=True")
        self._service = service
        self._recall_inject_enabled = recall_inject_enabled
        self._recall_limit = recall_limit
        self._capture_enabled = capture_enabled
        self._extract_idle_seconds = extract_idle_seconds
        # Fixed-interval extraction: when > 0 a single repeating timer sweeps
        # all sessions seen since the last sweep. Mutually exclusive with the
        # idle watchdog — the host wires exactly one of the two (see
        # ``MemoryRuntime.build_middleware``).
        self._extract_interval_seconds = extract_interval_seconds
        self._jsonl_enabled = jsonl_enabled
        self._jsonl_dir = Path(jsonl_dir) if jsonl_dir is not None else None
        self._jsonl_max_bytes = jsonl_max_bytes
        self._on_chat_model = on_chat_model
        self._maintenance_interval_seconds = maintenance_interval_seconds
        self._maintenance_initial_delay_seconds = maintenance_initial_delay_seconds
        self._lock = threading.Lock()
        self._background_condition = threading.Condition()
        self._background_active = 0
        self._background_paused = False
        self._background_shutdown = False
        # Per-session idle timers for the extract watchdog. Each captured turn
        # re-arms its session's timer; on expiry we fire ``end_session`` so
        # promotion to atoms runs after a quiet period without a host signal.
        self._idle_timers: dict[str, threading.Timer] = {}
        self._idle_lock = threading.Lock()
        # Single repeating timer for fixed-interval extraction.
        self._interval_timer: threading.Timer | None = None
        self._interval_lock = threading.Lock()
        self._interval_stopped = False
        # Dedicated slimming timer — not the extract LLM beat (ADR-027).
        self._maintenance_timer: threading.Timer | None = None
        self._maintenance_lock = threading.Lock()
        self._maintenance_stopped = False
        self._maintenance_running = threading.Lock()
        # Per-thread snapshot of the message count at ``before_model`` time
        # so ``after_model`` can record only the messages produced this turn.
        # Keyed by thread id rather than ``self`` to stay correct under parallel
        # subagents.
        self._cursors: dict[int, int] = {}
        # Track session_id -> set of thread_ids seen, for ``end_session``.
        # We treat one langgraph thread_id as one logical session for now;
        # callers wanting cross-thread sessions can pass an explicit one in
        # ``configurable['session_id']``.
        self._session_threads: dict[str, set[str]] = {}
        self._sessions_lock = threading.Lock()
        self._status_lock = threading.Lock()
        self._status: dict[str, Any] = {
            "phase": "idle",
            "percent": 0,
            "detail": None,
            "file_bytes": None,
            "started_at": None,
            "updated_at": None,
            "skipped_reason": None,
        }

        # Best-effort startup probe so misconfigured paths surface at
        # construction time (logged, never raised).
        if self._jsonl_enabled and self._jsonl_dir is not None:
            try:
                self._jsonl_dir.mkdir(parents=True, exist_ok=True)
            except OSError:
                logger.error(
                    "MemoryMiddleware startup probe failed: cannot create %s",
                    self._jsonl_dir,
                    exc_info=True,
                )

        # Arm the fixed-interval sweep once, at construction. Unlike the
        # idle watchdog (re-armed per turn) this runs on a steady cadence
        # regardless of activity.
        if self._extract_interval_seconds > 0 and self._service is not None:
            self._arm_interval_extract()
        if self._maintenance_interval_seconds > 0 and self._service is not None:
            self._arm_maintenance(delay=self._maintenance_initial_delay_seconds)

    # ------------------------------------------------------------------
    # Hooks
    # ------------------------------------------------------------------

    def before_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        """Snapshot the message count and persist recall before entering the model.

        Only a trailing user message can start fresh recall. Tool continuations
        and legacy history are never retroactively filled with today's memories.
        LangGraph's add_messages reducer replaces the stamped message by ID.
        """
        try:
            messages = _extract_messages(state)
            self._cursors[threading.get_ident()] = len(messages)
            if (
                self._service is not None
                and self._recall_inject_enabled
                and messages
                and isinstance(messages[-1], HumanMessage)
                and not has_recall_snapshot(messages[-1])
            ):
                manual_context = {
                    str(path).replace("\\", "/").rsplit("/", 1)[-1]: body
                    for path, body in state.get("memory_contents", {}).items()
                    if str(path).replace("\\", "/").rsplit("/", 1)[-1] in {"USER.md", "MEMORY.md"}
                }
                stamped = self._prepare_recall(messages[-1], runtime, manual_context=manual_context or None)
                return {"messages": [stamped]}
        except Exception:  # pragma: no cover - never raise into the user turn; pylint: disable=broad-except
            logger.warning("MemoryMiddleware before_model failed", exc_info=True)
        return None

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        """Replay durable recall on API message copies; preserve the system prompt."""
        return handler(request.override(messages=replay_recall_snapshots(request.messages)))

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Any],
    ) -> Any:
        return await handler(request.override(messages=replay_recall_snapshots(request.messages)))

    def after_model(self, state: Any, runtime: Any) -> None:
        """Persist messages produced this turn to MemoryService and/or JSONL.

        With a :class:`MemoryService` bound, we route the user / assistant
        contents through :meth:`MemoryService.capture_turn` on a background
        thread so the user reply is never blocked by SQLite IO.

        Memory writes are filtered down to the *user-visible* transcript
        only — we keep the user prompt that triggered the turn (located by
        :func:`_find_turn_trigger_user`, which looks past this turn's tool
        traffic) plus the *final* ``AIMessage`` of the turn (one with empty
        ``tool_calls``).
        Intermediate AI thinking, tool calls, and tool results are
        dropped. The full message stream still flows through JSONL when
        enabled.
        """
        try:
            messages = _extract_messages(state)
            cursor = self._cursors.pop(threading.get_ident(), 0)
            new_messages: list[BaseMessage] = list(messages[cursor:]) if cursor <= len(messages) else []
            if not new_messages:
                return

            configurable = _get_configurable(runtime)
            thread_id = configurable.get("thread_id", "unknown")
            session_id = configurable.get("session_id") or thread_id
            self._remember_chat_model(configurable)

            # Track session -> thread_ids for end_session().
            with self._sessions_lock:
                self._session_threads.setdefault(session_id, set()).add(thread_id)

            # The user prompt that triggered this turn — include it so the
            # persisted transcript contains both sides of the exchange. It is
            # at ``cursor - 1`` on the turn's first step, but sits behind this
            # turn's tool traffic on later ones, so search back for it.
            trigger_user = _find_turn_trigger_user(messages, cursor)

            visible = _filter_visible_messages(new_messages, trigger_user=trigger_user)

            if (
                self._service is not None
                and self._capture_enabled
                and visible
                and configurable.get("octop_memory_capture_exclude") is not True
            ):
                if self._maintenance_blocks_io():
                    logger.info(
                        "memory.capture skip: maintenance %s",
                        self.maintenance_status()["phase"],
                    )
                else:
                    self._submit_capture(visible, configurable)
                    self._arm_idle_extract(session_id)

            if self._jsonl_enabled and self._jsonl_dir is not None:
                # Include the triggering user message (lives just before
                # the cursor) so JSONL contains both sides of the exchange.
                # Deliberately a strict ``cursor - 1`` check, NOT
                # ``_find_turn_trigger_user``: JSONL appends one record per
                # model step, so the prompt is already written by the turn's
                # first step. Searching back would re-emit it on every
                # subsequent tool step and duplicate it in the log.
                jsonl_messages = list(new_messages)
                if cursor > 0 and isinstance(messages[cursor - 1], HumanMessage):
                    jsonl_messages = [messages[cursor - 1], *jsonl_messages]
                self._write_jsonl(jsonl_messages, configurable)
        except Exception:  # pragma: no cover - never raise into the user turn; pylint: disable=broad-except
            logger.warning("MemoryMiddleware after_model failed", exc_info=True)

    async def abefore_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        return self.before_model(state, runtime)

    async def aafter_model(self, state: Any, runtime: Any) -> None:
        self.after_model(state, runtime)

    # ------------------------------------------------------------------
    # Session-end extract trigger
    # ------------------------------------------------------------------

    def end_session(
        self,
        session_id: str,
        *,
        background: bool = True,
        incremental: bool = True,
        promote: bool = True,
        regen_pages: bool = True,
    ) -> None:
        """Trigger L0 → L2/L3 distillation for a finished session.

        Hosts (REPL ``/exit``, idle-timeout watchdog, ACP server tear-down,
        …) call this once per logical session. No-op when no service is
        bound or when no captured events exist for ``session_id``.

        ``background=True`` (default) runs ``extract`` on a daemon thread
        so the caller (e.g. a CLI exit hook) returns immediately. Set to
        ``False`` for synchronous batch jobs / tests where determinism is
        required.
        """
        service = self._service
        if service is None:
            return

        # A direct end_session supersedes any pending idle timer for this
        # session so the watchdog doesn't re-fire the same extraction.
        self._cancel_idle_timer(session_id)

        def _run() -> None:
            try:
                logger.info(
                    "memory.trigger end_session->extract session=%s incremental=%s promote=%s regen_pages=%s",
                    session_id,
                    incremental,
                    promote,
                    regen_pages,
                )
                result = service.extract(
                    session_id,
                    incremental=incremental,
                    promote=promote,
                    regen_pages=regen_pages,
                )
                result_dict = result if isinstance(result, dict) else None
                failure_reason = result_dict.get("failure_reason") if result_dict else None
                if failure_reason:
                    logger.info(
                        "MemoryMiddleware.end_session(%s) degraded: %s",
                        session_id,
                        failure_reason,
                    )
                else:
                    if result_dict is not None:
                        summary: object = {k: result_dict[k] for k in ("candidates", "promoted") if k in result_dict}
                    else:
                        summary = result
                    logger.info(
                        "memory.trigger end_session->extract done session=%s result=%s",
                        session_id,
                        summary,
                    )
            except Exception:  # pragma: no cover - extract is off the user path; pylint: disable=broad-except
                logger.warning(
                    "MemoryMiddleware.end_session(%s) failed",
                    session_id,
                    exc_info=True,
                )
            finally:
                with self._sessions_lock:
                    self._session_threads.pop(session_id, None)

        self._submit_background(_run, label="extract", background=background)

    # ------------------------------------------------------------------
    # Read-path helper (recall injection)
    # ------------------------------------------------------------------

    def _prepare_recall(
        self, message: HumanMessage, runtime: Any, *, manual_context: dict[str, str] | None = None
    ) -> HumanMessage:
        """Freeze success, empty recall, maintenance skip, or failure for this turn."""
        rendered = ""
        try:
            query = _stringify_content(message.content).strip()
            configurable = _get_configurable(runtime)
            thread_id = _opt_id(configurable, "thread_id")
            session_id = _opt_id(configurable, "session_id") or thread_id
            if self._maintenance_blocks_io():
                logger.info("memory.recall skip: maintenance %s", self.maintenance_status()["phase"])
            elif query:
                assert self._service is not None  # gated by caller
                context_options = {"manual_context": manual_context} if manual_context is not None else {}
                result = self._service.recall(
                    query, thread_id=thread_id, session_id=session_id, limit=self._recall_limit, **context_options
                )
                rendered = getattr(result, "rendered", None) or ""
                logger.debug(
                    "memory.trigger recall_inject thread=%s session=%s limit=%d hit=%s",
                    thread_id,
                    session_id,
                    self._recall_limit,
                    bool(rendered),
                )
        except Exception:  # recall injection is best-effort; pylint: disable=broad-except
            logger.warning("MemoryMiddleware recall injection failed", exc_info=True)
        return stamp_recall_snapshot(message, rendered)

    # ------------------------------------------------------------------
    # Write-path helpers
    # ------------------------------------------------------------------

    def _submit_capture(self, visible: list[BaseMessage], configurable: dict[str, Any]) -> None:
        """Capture a turn through ``MemoryService.capture_turn`` off-thread."""
        user_text, assistant_text = _split_user_assistant(visible)
        if not user_text and not assistant_text:
            return
        thread_id = configurable.get("thread_id", "unknown")
        session_id = configurable.get("session_id") or thread_id
        user_id = configurable.get("user")
        service = self._service
        assert service is not None  # gated by caller

        def _run() -> None:
            logger.debug(
                "memory.trigger capture_turn session=%s thread=%s user=%s user_chars=%d asst_chars=%d",
                session_id,
                thread_id,
                user_id,
                len(user_text or ""),
                len(assistant_text or ""),
            )
            service.capture_turn(
                user=user_text,
                assistant=assistant_text,
                session_id=session_id,
                thread_id=thread_id,
                user_id=user_id,
            )

        self._submit_background(_run, label="capture")

    def _remember_chat_model(self, configurable: dict[str, Any]) -> None:
        """Tell the extract LLM client which model just served this turn."""
        if self._on_chat_model is None:
            return
        model_ref = _active_model_ref(configurable)
        if not model_ref:
            return
        try:
            self._on_chat_model(model_ref)
        except Exception:  # hook failures must not break the turn; pylint: disable=broad-except
            logger.debug("MemoryMiddleware on_chat_model failed", exc_info=True)

    # ------------------------------------------------------------------
    # Idle-extract watchdog
    # ------------------------------------------------------------------

    def _arm_idle_extract(self, session_id: str) -> None:
        """(Re)start the per-session idle timer that fires ``end_session``.

        Each captured turn pushes the deadline out by
        ``extract_idle_seconds``; the timer only fires once a session has
        been quiet for that long. No-op when the watchdog is disabled or no
        service is bound.
        """
        if self._extract_idle_seconds <= 0 or self._service is None:
            return
        from octop_harness.observability.logging import current_log_agent_id

        agent_id = current_log_agent_id()
        with self._idle_lock:
            existing = self._idle_timers.pop(session_id, None)
            if existing is not None:
                existing.cancel()
            timer = threading.Timer(
                self._extract_idle_seconds,
                self._on_idle_extract,
                args=(session_id, agent_id),
            )
            timer.daemon = True
            timer.name = f"hm-idle-{session_id}"
            self._idle_timers[session_id] = timer
            timer.start()

    def _on_idle_extract(self, session_id: str, agent_id: str | None = None) -> None:
        """Timer callback: drop the timer and run session-end extraction."""
        from octop_harness.observability.logging import logging_scope

        with self._idle_lock:
            self._idle_timers.pop(session_id, None)
        with logging_scope(agent_id):
            self.end_session(session_id, background=True)
            self._submit_maintenance()

    def _cancel_idle_timer(self, session_id: str) -> None:
        """Cancel any pending idle timer for ``session_id`` (idempotent)."""
        with self._idle_lock:
            timer = self._idle_timers.pop(session_id, None)
        if timer is not None:
            timer.cancel()

    # ------------------------------------------------------------------
    # Fixed-interval extract sweep
    # ------------------------------------------------------------------

    def _arm_interval_extract(self) -> None:
        """(Re)start the single repeating fixed-interval sweep timer.

        No-op when the interval is disabled, no service is bound, or the
        middleware has been shut down. Each fire re-arms the next one so the
        cadence is steady regardless of conversation activity.
        """
        if self._extract_interval_seconds <= 0 or self._service is None:
            return
        with self._interval_lock:
            if self._interval_stopped:
                return
            if self._interval_timer is not None:
                self._interval_timer.cancel()
            timer = threading.Timer(
                self._extract_interval_seconds,
                self._on_interval_extract,
            )
            timer.daemon = True
            timer.name = "hm-interval-extract"
            self._interval_timer = timer
            timer.start()

    def _on_interval_extract(self) -> None:
        """Timer callback: extract every session seen since the last sweep.

        We snapshot the tracked-session set (populated by ``after_model``)
        and fire ``end_session`` on each. ``end_session`` pops the session
        from tracking when it completes, so the next sweep only revisits
        sessions that saw new turns in the meantime. The timer re-arms
        itself even when the snapshot is empty.
        """
        try:
            with self._sessions_lock:
                session_ids = list(self._session_threads.keys())
            if session_ids:
                logger.info(
                    "memory.trigger interval_extract fire sessions=%d interval=%ss",
                    len(session_ids),
                    self._extract_interval_seconds,
                )
                for session_id in session_ids:
                    self.end_session(session_id, background=True)
        finally:
            self._arm_interval_extract()

    def _stop_interval_timer(self) -> None:
        """Stop the interval sweep permanently (idempotent)."""
        with self._interval_lock:
            self._interval_stopped = True
            timer = self._interval_timer
            self._interval_timer = None
        if timer is not None:
            timer.cancel()

    def shutdown(self) -> None:
        """Cancel all background timers. Safe to call multiple times."""
        with self._background_condition:
            self._background_shutdown = True
        self._stop_interval_timer()
        self._stop_maintenance_timer()
        with self._idle_lock:
            timers = list(self._idle_timers.values())
            self._idle_timers.clear()
        for timer in timers:
            timer.cancel()

    def _submit_background(self, fn: Callable[[], None], *, label: str, background: bool = True) -> None:
        with self._background_condition:
            if self._background_paused or self._background_shutdown:
                return
            self._background_active += 1

        def run() -> None:
            try:
                fn()
            finally:
                with self._background_condition:
                    self._background_active -= 1
                    self._background_condition.notify_all()

        if background:
            try:
                _bg_pool().submit(run, label=label)
            except Exception:
                with self._background_condition:
                    self._background_active -= 1
                    self._background_condition.notify_all()
                raise
        else:
            run()

    @contextmanager
    def pause_background(self, *, timeout: float = 120) -> Iterator[None]:
        """Drain this expert's memory workers for a host-owned restore.

        The host must separately stop graph admission. New background work is
        skipped while paused; timeout restores normal admission without closing
        resources still in use. Other middleware instances remain independent.
        """
        with self._background_condition:
            if self._background_paused:
                raise RuntimeError("Memory background work is already paused")
            self._background_paused = True
        try:
            with self._background_condition:
                if not self._background_condition.wait_for(lambda: self._background_active == 0, timeout=timeout):
                    raise TimeoutError("Memory background work did not become idle")
            yield
        finally:
            with self._background_condition:
                self._background_paused = False

    def maintenance_status(self) -> dict[str, Any]:
        """Snapshot of the current slimming phase for host status APIs."""
        with self._status_lock:
            return dict(self._status)

    def _set_status(self, *, phase: str, **fields: Any) -> None:
        with self._status_lock:
            self._status["phase"] = phase
            self._status["percent"] = _PHASE_PERCENT.get(phase, self._status.get("percent") or 0)
            self._status["updated_at"] = time.time()
            if self._status["started_at"] is None and phase in _VISIBLE_PHASES:
                self._status["started_at"] = time.time()
            if phase in {"idle", "done", "skipped"}:
                # Keep started_at so the UI can show elapsed on the last tick.
                pass
            for key, value in fields.items():
                if key in self._status:
                    self._status[key] = value

    def _maintenance_blocks_io(self) -> bool:
        with self._status_lock:
            return self._status["phase"] in _IO_BLOCKING_PHASES

    # ------------------------------------------------------------------
    # Idle DB maintenance (GC + nudge; no checkpoint prune, no compact)
    # ------------------------------------------------------------------

    def _arm_maintenance(self, *, delay: float) -> None:
        """(Re)start the repeating slimming timer.

        ``delay`` is the wait until this fire; later fires use
        ``maintenance_interval_seconds``. No-op when disabled, unbound,
        or shut down.
        """
        if self._maintenance_interval_seconds <= 0 or self._service is None:
            return
        with self._maintenance_lock:
            if self._maintenance_stopped:
                return
            if self._maintenance_timer is not None:
                self._maintenance_timer.cancel()
            wait = delay if delay > 0 else self._maintenance_interval_seconds
            timer = threading.Timer(wait, self._on_maintenance)
            timer.daemon = True
            timer.name = "hm-idle-maintenance"
            self._maintenance_timer = timer
            timer.start()

    def _on_maintenance(self) -> None:
        """Timer callback: run one maintenance tick, then re-arm."""
        try:
            self._submit_maintenance()
        finally:
            self._arm_maintenance(delay=self._maintenance_interval_seconds)

    def _submit_maintenance(self) -> None:
        """Run one GC + nudge tick off-thread. Overlapping ticks skip."""
        if self._maintenance_interval_seconds <= 0 or self._service is None:
            return
        service = self._service

        def _run() -> None:
            self._run_maintenance_tick(service)

        self._submit_background(_run, label="maintenance")

    @staticmethod
    def _run_reclaim_pass(memory: Any, *, run_gc: Any, nudge_vacuum: Any) -> None:
        """Lifecycle GC then incremental vacuum. Each step fail-soft on its own.

        One failure still lets the other run.
        """
        gc_stats = None
        gc_error = None
        try:
            gc_stats = run_gc(memory)
        except Exception as exc:  # reported back as a maintenance error; pylint: disable=broad-except
            gc_error = f"{type(exc).__name__}: {exc}"
            message = str(exc)
            # Lifecycle SQL is SQLite-only, and a namespace whose tables were
            # never created (a Postgres agent that has not written memory yet)
            # has nothing to collect. Neither deserves a warning traceback
            # every hour.
            if "GC requires SQLite backend" in message:
                logger.debug("memory.maintenance skip gc: backend is not sqlite")
                gc_error = None
            elif type(exc).__name__ == "UndefinedTable" or ("relation" in message and "does not exist" in message):
                logger.debug("memory.maintenance skip gc: namespace tables not created yet")
                gc_error = None
            else:
                logger.warning("memory.maintenance run_gc failed", exc_info=True)
        vacuum = None
        vacuum_error = None
        try:
            vacuum = nudge_vacuum(memory)
        except Exception as exc:  # reported back as a maintenance error; pylint: disable=broad-except
            vacuum_error = f"{type(exc).__name__}: {exc}"
            logger.warning("memory.maintenance nudge_vacuum failed", exc_info=True)
        gc_rows = None if gc_stats is None else gc_stats.total_deleted
        pages = None if vacuum is None else vacuum.pages_reclaimed
        # An idle store reclaims nothing on most ticks. Logging every one of
        # those at INFO buries the host log (one line per agent per hour, plus
        # a burst on every restart), so only a pass that did something — or
        # broke — is worth a line.
        did_work = bool(gc_rows) or bool(pages)
        level = logging.INFO if (did_work or gc_error or vacuum_error) else logging.DEBUG
        logger.log(
            level,
            "memory.maintenance done gc_err=%s vacuum_err=%s gc_rows=%s pages=%s auto_vacuum=%s",
            gc_error,
            vacuum_error,
            gc_rows,
            pages,
            None if vacuum is None else vacuum.auto_vacuum_enabled,
        )

    def _run_maintenance_tick(
        self,
        service: Any,
    ) -> None:
        """Run one cheap GC + incremental-vacuum tick.

        Full compact/VACUUM is intentionally never scheduled by the agent;
        operators may still invoke octop-memory's explicit compact command.
        """
        if not self._maintenance_running.acquire(blocking=False):
            logger.debug("memory.maintenance skip overlapping tick")
            return
        try:
            # Deliberately NOT ``run_idle_maintenance``: its first step is
            # ``prune_checkpoints`` and it has no switch to skip that, so the
            # two reclaim steps are called directly. LangGraph checkpoint rows
            # are never deleted from here — sealing a delta-omitted parent
            # before dropping its ancestors could truncate a transcript.
            from octop_memory.pipeline.lifecycle import nudge_vacuum, run_gc

            memory = getattr(service, "memory", None)
            if memory is None:
                logger.warning("memory.maintenance skipped: service has no memory")
                return
            # Agents sharing one store (same namespace + DSN) would otherwise
            # each reclaim the same rows back to back. Half the cadence is a
            # wide enough window to fold a startup burst into one pass while
            # still letting the next hourly tick through.
            if not _claim_reclaim_slot(memory, window=self._maintenance_interval_seconds / 2):
                logger.debug("memory.maintenance skip: another agent just reclaimed this store")
                return

            def _nudge(store: Any) -> Any:
                return nudge_vacuum(store, pages=_MAINTENANCE_VACUUM_PAGES)

            self._run_reclaim_pass(memory, run_gc=run_gc, nudge_vacuum=_nudge)
        except Exception:  # maintenance runs off the user path; pylint: disable=broad-except
            logger.warning("memory.maintenance failed", exc_info=True)
        finally:
            self._maintenance_running.release()

    def _stop_maintenance_timer(self) -> None:
        """Stop the slimming timer permanently (idempotent)."""
        with self._maintenance_lock:
            self._maintenance_stopped = True
            timer = self._maintenance_timer
            self._maintenance_timer = None
        if timer is not None:
            timer.cancel()

    # ------------------------------------------------------------------
    # JSONL writer
    # ------------------------------------------------------------------

    def _write_jsonl(
        self,
        messages: list[BaseMessage],
        configurable: dict[str, Any],
    ) -> None:
        assert self._jsonl_dir is not None  # gated by caller
        with self._lock:
            try:
                self._jsonl_dir.mkdir(parents=True, exist_ok=True)
                target = self._active_file_path()
                self._maybe_rotate(target)

                base_record = {
                    "thread_id": configurable.get("thread_id"),
                    "user": configurable.get("user"),
                    "source": configurable.get("source"),
                }
                model_ref = _active_model_ref(configurable)

                user_msg = _find_first(messages, HumanMessage)
                ai_msg = _find_last(messages, AIMessage)

                entries: list[dict[str, Any]] = []
                if user_msg is not None:
                    entries.append(_render_record(user_msg, "user", base_record))
                if ai_msg is not None:
                    entries.append(
                        _render_record(
                            ai_msg,
                            "assistant",
                            base_record,
                            model=model_ref,
                        ),
                    )

                if not entries:
                    return

                with target.open("a", encoding="utf-8") as fh:
                    for entry in entries:
                        fh.write(json.dumps(entry, ensure_ascii=False))
                        fh.write("\n")
            except OSError:
                logger.warning(
                    "MemoryMiddleware could not write JSONL to %s",
                    self._jsonl_dir,
                    exc_info=True,
                )

    def _active_file_path(self) -> Path:
        assert self._jsonl_dir is not None
        # Local-time date so overnight rotation matches operator expectation.
        date_str = datetime.now().astimezone().strftime("%Y-%m-%d")
        return self._jsonl_dir / f"{date_str}.jsonl"

    def _maybe_rotate(self, target: Path) -> None:
        try:
            size = target.stat().st_size
        except FileNotFoundError:
            return
        if size < self._jsonl_max_bytes:
            return
        # Find the next free sequence number for today.
        n = 1
        date_part = target.stem  # 'YYYY-MM-DD'
        while True:
            candidate = target.with_name(f"{date_part}.{n}.jsonl")
            if not candidate.exists():
                break
            n += 1
        os.replace(target, candidate)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_messages(state: Any) -> list[BaseMessage]:
    """Best-effort extraction of the ``messages`` list from agent state."""
    if state is None:
        return []
    if isinstance(state, dict):
        return list(state.get("messages", []) or [])
    return list(getattr(state, "messages", []) or [])


def _get_configurable(runtime: Any) -> dict[str, Any]:
    """Read the current graph run's ``configurable`` dict.

    LangGraph v0.6+ injects per-run config through
    :func:`langgraph.config.get_config`; ``ModelRequest.runtime`` only keeps
    ``context`` and no longer exposes ``config``. We must try ``get_config()``
    first or keys like ``thread_id`` / ``session_id`` / ``user`` disappear and
    get recorded as ``unknown``.

    Other middleware (model_router / mcp_tools / skill_filter) already moved to
    :func:`octop_harness.middleware.runtime.runtime_config`; keep the same
    precedence here: get_config -> runtime.config -> runtime.configurable.
    """
    # 1) LangGraph v0.6+: read RunnableConfig from the contextvar.
    try:
        from langgraph.config import get_config

        config = get_config()
        if isinstance(config, dict):
            configurable = config.get("configurable")
            if isinstance(configurable, dict) and configurable:
                return configurable
    except (RuntimeError, ImportError):
        # RuntimeError: not inside a graph run, e.g. direct middleware unit tests.
        # ImportError: very old langgraph versions.
        pass

    # 2) Fallback: older runtime.config.
    if runtime is None:
        return {}
    runtime_config = getattr(runtime, "config", None)
    if isinstance(runtime_config, dict):
        configurable = runtime_config.get("configurable")
        if isinstance(configurable, dict):
            return configurable
    # 3) Fallback：runtime.configurable
    configurable = getattr(runtime, "configurable", None)
    if isinstance(configurable, dict):
        return configurable
    return {}


def _active_model_ref(configurable: dict[str, Any]) -> str | None:
    model = configurable.get("model")
    return model if isinstance(model, str) else None


def _find_first(
    messages: list[BaseMessage],
    cls: type[BaseMessage],
) -> BaseMessage | None:
    for m in messages:
        if isinstance(m, cls):
            return m
    return None


def _find_last(
    messages: list[BaseMessage],
    cls: type[BaseMessage],
) -> BaseMessage | None:
    for m in reversed(messages):
        if isinstance(m, cls):
            return m
    return None


def _render_record(
    msg: BaseMessage,
    role: str,
    base: dict[str, Any],
    *,
    model: str | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "ts": datetime.now().astimezone().isoformat(timespec="milliseconds"),
        "role": role,
        "content": _stringify_content(msg.content),
        **{k: v for k, v in base.items() if v is not None},
    }
    if model is not None:
        record["model"] = model
    usage = _extract_usage(msg)
    if usage:
        record["usage"] = usage
    return record


def _stringify_content(content: Any) -> str:
    """Reduce content (possibly a multimodal block list) to a readable string."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text" and isinstance(block.get("text"), str):
                    parts.append(block["text"])
                else:
                    parts.append(json.dumps(block, ensure_ascii=False))
            else:
                parts.append(str(block))
        return "\n".join(parts)
    return str(content)


def _extract_usage(msg: BaseMessage) -> dict[str, int] | None:
    """Pull token usage out of an AI message if available."""
    metadata = getattr(msg, "usage_metadata", None)
    if isinstance(metadata, dict):
        return {
            "input_tokens": int(metadata.get("input_tokens") or 0),
            "output_tokens": int(metadata.get("output_tokens") or 0),
        }
    response_metadata = getattr(msg, "response_metadata", None)
    if isinstance(response_metadata, dict):
        usage = response_metadata.get("token_usage") or response_metadata.get("usage")
        if isinstance(usage, dict):
            return {
                "input_tokens": int(
                    usage.get("input_tokens") or usage.get("prompt_tokens") or 0,
                ),
                "output_tokens": int(
                    usage.get("output_tokens") or usage.get("completion_tokens") or 0,
                ),
            }
    return None


def _find_turn_trigger_user(messages: list[BaseMessage], cursor: int) -> BaseMessage | None:
    """Locate the ``HumanMessage`` that started the turn ending at *cursor*.

    On a turn's first model step the prompt sits exactly at ``cursor - 1``.
    Once the agent starts calling tools, later steps see a ``ToolMessage``
    there instead, so a strict ``messages[cursor - 1]`` check returns None —
    and because that first step already dropped the prompt through
    :func:`_filter_visible_messages`' empty-exchange guard (the step emitted
    only ``tool_calls``, so there was no final AI reply to pair it with), the
    user's message would never be captured at all. Every prompt that happened
    to trigger tool use was therefore missing from memory.

    So we walk back over this turn's tool traffic (``ToolMessage`` and
    tool-calling ``AIMessage``) to find the prompt still driving the turn.
    A tool-call-free ``AIMessage`` means the previous turn already closed,
    so we stop there and return None rather than reaching backwards into it.
    """
    for msg in reversed(messages[:cursor]):
        if isinstance(msg, HumanMessage):
            return msg
        if isinstance(msg, AIMessage) and not (getattr(msg, "tool_calls", None) or []):
            # Previous turn's closing reply — this turn has no user prompt.
            return None
        # ToolMessage / tool-calling AIMessage: this turn's own tool traffic.
    return None


def _filter_visible_messages(
    messages: list[BaseMessage],
    *,
    trigger_user: BaseMessage | None = None,
) -> list[BaseMessage]:
    """Reduce a turn's raw message stream to the user-visible transcript.

    What we keep:
    - ``trigger_user`` (when supplied): the prompt that triggered this
      turn. langgraph's typical flow has the human message already in
      state at ``before_model`` time, so it is *not* part of
      ``messages`` here — the caller passes it in explicitly so it can
      be stitched back into the transcript.
    - Any additional ``HumanMessage`` inside ``messages`` (rare, but
      possible if the agent loop re-prompts mid-turn).
    - The *final* ``AIMessage`` per turn — i.e. one whose ``tool_calls``
      is empty (the model is done with tool dispatch and is talking back
      to the user).

    What we drop:
    - ``ToolMessage`` (tool outputs).
    - Intermediate ``AIMessage`` instances that carry ``tool_calls`` or
      whose content is empty (no text was emitted).
    - Runtime-generated failure replies marked ``octop_runtime_error``.
      Their triggering user input is still captured; JSONL keeps diagnostics.
    """
    visible: list[BaseMessage] = []
    if trigger_user is not None and isinstance(trigger_user, HumanMessage):
        visible.append(trigger_user)
    final_ai: AIMessage | None = None
    runtime_failure = False
    for msg in messages:
        if isinstance(msg, HumanMessage):
            visible.append(msg)
        elif isinstance(msg, AIMessage):
            tool_calls = getattr(msg, "tool_calls", None) or []
            has_text = bool(msg.content)
            if not tool_calls and has_text:
                # Last write wins — if a turn somehow produces multiple
                # tool_call-free AIMessages (rare), keep the latest.
                runtime_failure = msg.response_metadata.get("octop_runtime_error") is True
                final_ai = None if runtime_failure else msg
        # ToolMessage and tool-call-only AIMessages are intentionally skipped.
    if final_ai is not None:
        visible.append(final_ai)
    # Edge case: ``trigger_user`` alone with no AI reply isn't a
    # user-visible exchange yet — drop it so we don't write a record.
    if visible and final_ai is None and trigger_user is not None and len(visible) == 1 and not runtime_failure:
        return []
    return visible


def _split_user_assistant(visible: list[BaseMessage]) -> tuple[str | None, str | None]:
    """Reduce a turn's user-visible message list to flat strings.

    ``MemoryService.capture_turn`` takes a single ``user`` and a single
    ``assistant`` payload (the policy layer maps each to one ``RawEvent``);
    we collapse multiple ``HumanMessage`` instances by joining their
    contents with double newlines (rare path) and pick the *last*
    ``AIMessage`` as the assistant reply.
    """
    user_parts: list[str] = []
    assistant: str | None = None
    for msg in visible:
        if isinstance(msg, HumanMessage):
            user_parts.append(_stringify_content(msg.content))
        elif isinstance(msg, AIMessage):
            text = _stringify_content(msg.content)
            if text:
                assistant = text  # last write wins
    user = "\n\n".join(p for p in user_parts if p) or None
    return user, assistant


def _opt_id(configurable: dict[str, Any], key: str) -> str | None:
    value = configurable.get(key)
    return value if isinstance(value, str) and value else None


__all__ = ["MemoryMiddleware"]
