"""Lifecycle close behaviour — sync vs async construction/teardown."""

from __future__ import annotations

import contextlib
import gc
import sqlite3
import warnings
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from octop_harness.agent import HarnessAgent, _sync_close_sqlite_connection
from octop_harness.config import HarnessAgentConfig, ModelConfig, ProviderConfig
from octop_harness.memory.runtime import MemoryRuntime
from octop_harness.providers import _parse_model_input


def _close_memory(memory: object) -> None:
    checkpointer = getattr(memory, "_checkpointer", None)
    if checkpointer is not None:
        cp_conn = getattr(checkpointer, "conn", None)
        if cp_conn is not None:
            with contextlib.suppress(Exception):
                cp_conn.close()
    backend = getattr(memory, "backend", None)
    close_fn = getattr(backend, "close", None)
    if callable(close_fn):
        with contextlib.suppress(Exception):
            close_fn()


def _sqlite_agent_cfg(tmp_path: Path, *, memory_enabled: bool = False) -> HarnessAgentConfig:
    return HarnessAgentConfig(
        workspace_dir=tmp_path,
        backend={"type": "filesystem", "root_dir": str(tmp_path), "virtual_mode": False},
        providers=[
            ProviderConfig(
                id="p",
                base_url="https://x",
                api_key="k",
                models=[ModelConfig(id="text", input=["text"])],
            ),
        ],
        default_model="p/text",
        memory_enabled=memory_enabled,
        checkpointer=False if memory_enabled else None,
    )


def _build_agent(cfg: HarnessAgentConfig) -> HarnessAgent:
    with (
        patch("langchain_openai.ChatOpenAI", return_value=MagicMock()),
        patch("deepagents.create_deep_agent", return_value=MagicMock()),
    ):
        return HarnessAgent(cfg)


class TestParseModelInput:
    def test_rejects_invalid_modality(self) -> None:
        with pytest.raises(ValueError, match=r"invalid input modality 'smell'"):
            _parse_model_input(["text", "smell"], model_id="m1")

    def test_accepts_all_modalities(self) -> None:
        assert _parse_model_input(["text", "image", "audio", "video"]) == (
            "text",
            "image",
            "audio",
            "video",
        )


class TestSyncCloseSqliteConnection:
    @pytest.mark.asyncio
    async def test_close_after_async_connect_leaves_no_raw_connection(self, tmp_path: Path) -> None:
        """After the saver opens aiosqlite, sync close must drop the raw handle."""
        import aiosqlite

        db = tmp_path / "cp.sqlite"
        conn = await aiosqlite.connect(str(db))
        await conn.execute("select 1")
        assert getattr(conn, "_connection", None) is not None

        _sync_close_sqlite_connection(conn)
        raw = getattr(conn, "_connection", None)
        assert raw is not None
        with pytest.raises(sqlite3.ProgrammingError):
            raw.execute("select 1")

    def test_close_without_connect_is_noop(self, tmp_path: Path) -> None:
        import aiosqlite

        conn = aiosqlite.connect(str(tmp_path / "lazy.sqlite"))
        assert getattr(conn, "_connection", None) is None
        _sync_close_sqlite_connection(conn)
        assert getattr(conn, "_connection", None) is None


class TestHarnessAgentClosePaths:
    @pytest.mark.asyncio
    async def test_aclose_awaits_aiosqlite_in_running_loop(self, tmp_path: Path) -> None:
        """``aclose()`` should use ``await conn.close()`` when the loop is active."""
        cfg = _sqlite_agent_cfg(tmp_path)
        with warnings.catch_warnings():
            warnings.simplefilter("error", ResourceWarning)
            agent = _build_agent(cfg)
            cp = await agent._checkpointer_conn
            await cp.execute("select 1")
            await agent.aclose()
            assert agent._checkpointer_conn is None
            del agent, cp
            gc.collect()

    @pytest.mark.asyncio
    async def test_async_context_manager_uses_aclose(self, tmp_path: Path) -> None:
        cfg = _sqlite_agent_cfg(tmp_path)
        with warnings.catch_warnings():
            warnings.simplefilter("error", ResourceWarning)
            async with _build_agent(cfg) as agent:
                cp = await agent._checkpointer_conn
                await cp.execute("select 1")
            gc.collect()

    def test_sync_build_and_close_default_checkpointer(self, tmp_path: Path) -> None:
        """Sync ``HarnessAgent()`` + ``close()`` must not leak sqlite3 handles."""
        cfg = _sqlite_agent_cfg(tmp_path)
        with warnings.catch_warnings():
            warnings.simplefilter("error", ResourceWarning)
            agent = _build_agent(cfg)
            assert agent._checkpointer_conn is not None
            agent.close()
            assert agent._checkpointer_conn is None
            del agent
            gc.collect()

    @pytest.mark.asyncio
    async def test_async_context_build_and_close(self, tmp_path: Path) -> None:
        """Building inside a running loop (pytest-asyncio) still closes cleanly."""
        cfg = _sqlite_agent_cfg(tmp_path)
        with warnings.catch_warnings():
            warnings.simplefilter("error", ResourceWarning)
            agent = _build_agent(cfg)
            cp = agent._checkpointer_conn
            assert cp is not None
            cp = await cp
            await cp.execute("select 1")
            agent.close()
            assert agent._checkpointer_conn is None
            del agent, cp
            gc.collect()

    def test_memory_enabled_closes_both_sqlite_handles(self, tmp_path: Path) -> None:

        cfg = HarnessAgentConfig(
            workspace_dir=tmp_path,
            backend={"type": "filesystem", "root_dir": str(tmp_path), "virtual_mode": False},
            providers=[
                ProviderConfig(id="p", base_url="https://x", api_key="k", models=[ModelConfig(id="m")]),
            ],
            memory_enabled=True,
            memory_backend={"type": "sqlite", "db_path": str(tmp_path / "mem.sqlite")},
            checkpointer=False,
        )
        with warnings.catch_warnings():
            warnings.simplefilter("error", ResourceWarning)
            agent = _build_agent(cfg)
            mem = agent.memory
            assert mem is not None
            assert getattr(mem, "_checkpointer", None) is not None
            agent.close()
            assert agent._memory_runtime.memory is None
            del agent, mem
            gc.collect()

    def test_memory_runtime_close_matches_helper(self, tmp_path: Path) -> None:
        from octop_memory import Memory

        mem = Memory(namespace="t", backend_config={"db_path": str(tmp_path / "m.sqlite")})
        runtime = MemoryRuntime(
            config=HarnessAgentConfig(name="t", workspace_dir=tmp_path, memory_enabled=False),
            workspace_path=tmp_path,
            model_factory=MagicMock(),
        )
        runtime._memory = mem  # type: ignore[attr-defined]
        runtime._memory_key = None
        runtime._service = None
        with warnings.catch_warnings():
            warnings.simplefilter("error", ResourceWarning)
            runtime.close()
        # Idempotent second close.
        runtime.close()

    def test_close_memory_helper_covers_standalone_memory(self, tmp_path: Path) -> None:
        from octop_memory import Memory

        mem = Memory(namespace="t", backend_config={"db_path": str(tmp_path / "solo.sqlite")})
        with warnings.catch_warnings():
            warnings.simplefilter("error", ResourceWarning)
            _close_memory(mem)
            gc.collect()

    def test_close_is_idempotent(self, tmp_path: Path) -> None:
        cfg = _sqlite_agent_cfg(tmp_path)
        agent = _build_agent(cfg)
        agent.close()
        agent.close()
        agent.close()


class TestCloseDeferredWhileBusy:
    """A hot-reload closes the agent it just replaced; a running turn still needs it.

    Releasing the checkpointer (and the memory backend behind it) under an
    active turn makes the end-of-turn write flush fail on a dead handle —
    ``psycopg_pool.PoolClosed`` on Postgres — after the answer already streamed.
    """

    @pytest.mark.asyncio
    async def test_close_waits_for_in_flight_invocation(self, tmp_path: Path) -> None:
        agent = _build_agent(_sqlite_agent_cfg(tmp_path))
        assert agent._checkpointer_conn is not None

        async with agent._invocation():
            agent.close()
            # Deferred: the running turn can still reach its checkpointer.
            assert agent._checkpointer_conn is not None

        assert agent._checkpointer_conn is None

    @pytest.mark.asyncio
    async def test_repeated_close_requests_release_once(self, tmp_path: Path) -> None:
        agent = _build_agent(_sqlite_agent_cfg(tmp_path))

        async with agent._invocation():
            agent.close()
            agent.close()
            await agent.aclose()
            assert agent._checkpointer_conn is not None

        assert agent._checkpointer_conn is None
        assert agent._close_pending is False

    @pytest.mark.asyncio
    async def test_nested_invocations_hold_the_release(self, tmp_path: Path) -> None:
        agent = _build_agent(_sqlite_agent_cfg(tmp_path))

        async with agent._invocation():
            async with agent._invocation():
                agent.close()
            # Outer invocation still running — do not release yet.
            assert agent._checkpointer_conn is not None

        assert agent._checkpointer_conn is None

    @pytest.mark.asyncio
    async def test_stream_holds_the_pin_until_it_finishes(self, tmp_path: Path) -> None:
        import asyncio

        agent = _build_agent(_sqlite_agent_cfg(tmp_path))
        started = asyncio.Event()
        released = asyncio.Event()

        class _BlockingProtocol:
            name = "fake"

            async def stream(
                self,
                _messages: object,
                _config: object,
                **_kwargs: object,
            ) -> AsyncIterator[dict[str, str]]:
                yield {"type": "token", "content": "a"}
                started.set()
                await released.wait()
                yield {"type": "token", "content": "b"}

        proto = _BlockingProtocol()
        with patch.object(agent, "_prepare_call", return_value=([], {}, proto)):
            chunks: list[dict[str, str]] = []

            async def consume() -> None:
                async for chunk in agent.stream("hi"):
                    chunks.append(chunk)

            task = asyncio.create_task(consume())
            await started.wait()

            agent.close()
            assert agent._checkpointer_conn is not None

            released.set()
            await task

        assert [c["content"] for c in chunks] == ["a", "b"]
        assert agent._checkpointer_conn is None

    def test_idle_close_still_releases_immediately(self, tmp_path: Path) -> None:
        agent = _build_agent(_sqlite_agent_cfg(tmp_path))
        assert agent._checkpointer_conn is not None
        agent.close()
        assert agent._checkpointer_conn is None
