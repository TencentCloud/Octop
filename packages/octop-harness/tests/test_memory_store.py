"""Shared ``Memory`` store: rebuilds keep the same backend / checkpointer."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from octop_harness.agent import HarnessAgent
from octop_harness.config import HarnessAgentConfig, ModelConfig, ProviderConfig
from octop_harness.manager import HarnessAgentManager
from octop_harness.memory.runtime import MemoryRuntime
from octop_harness.memory.store import hold_shared_memory, memory_identity, shared_memory_store


def _cfg(tmp_path: Path, *, namespace: str = "ns", name: str = "agent") -> HarnessAgentConfig:
    return HarnessAgentConfig(
        name=name,
        workspace_dir=tmp_path,
        backend={"type": "filesystem", "root_dir": str(tmp_path), "virtual_mode": False},
        providers=[
            ProviderConfig(
                id="p",
                base_url="https://x",
                api_key="k",
                models=[ModelConfig(id="m")],
            )
        ],
        default_model="p/m",
        memory_enabled=True,
        memory_namespace=namespace,
        memory_backend={"type": "sqlite", "db_path": str(tmp_path / "mem.sqlite")},
        memory_aux_model_enabled=False,
        session_log_enabled=False,
        checkpointer=False,
    )


def _runtime(cfg: HarnessAgentConfig, tmp_path: Path) -> MemoryRuntime:
    return MemoryRuntime(config=cfg, workspace_path=tmp_path, model_factory=MagicMock())


class TestMemoryIdentity:
    def test_sqlite_key_uses_resolved_path(self, tmp_path: Path) -> None:
        cfg = _cfg(tmp_path)
        ident = memory_identity(cfg, tmp_path)
        assert ident is not None
        assert ident.backend == "sqlite"
        assert ident.namespace == "ns"
        assert ident.location == str((tmp_path / "mem.sqlite").resolve())

    def test_postgres_key_is_namespace_plus_dsn(self, tmp_path: Path) -> None:
        cfg = HarnessAgentConfig(
            name="a",
            workspace_dir=tmp_path,
            memory_enabled=True,
            memory_namespace="hh",
            memory_backend={"type": "postgres", "dsn": "postgresql://u@h/db"},
        )
        ident = memory_identity(cfg, tmp_path)
        assert ident is not None
        assert ident.backend == "postgres"
        assert ident.namespace == "hh"
        assert ident.location == "postgresql://u@h/db"

    def test_disabled_or_instance_backend_is_not_shared(self, tmp_path: Path) -> None:
        off = HarnessAgentConfig(workspace_dir=tmp_path, memory_enabled=False)
        assert memory_identity(off, tmp_path) is None
        live = HarnessAgentConfig(workspace_dir=tmp_path, memory_backend=object())
        assert memory_identity(live, tmp_path) is None


class TestSharedMemoryRefs:
    def test_two_runtimes_share_one_memory(self, tmp_path: Path) -> None:
        cfg = _cfg(tmp_path)
        first = _runtime(cfg, tmp_path)
        second = _runtime(cfg, tmp_path)
        try:
            assert first.memory is second.memory
            ident = memory_identity(cfg, tmp_path)
            assert ident is not None
            assert shared_memory_store().refs(ident) == 2
            backend = first.memory.backend
            first.close()
            assert shared_memory_store().refs(ident) == 1
            assert getattr(backend, "_conn", None) is not None
            backend._conn.execute("SELECT 1")
        finally:
            second.close()
        ident = memory_identity(cfg, tmp_path)
        assert ident is not None
        assert shared_memory_store().refs(ident) == 0

    def test_last_close_releases_backend(self, tmp_path: Path) -> None:
        cfg = _cfg(tmp_path)
        runtime = _runtime(cfg, tmp_path)
        backend = runtime.memory.backend
        runtime.close()
        # sqlite connection is closed; further execute fails.
        with pytest.raises(sqlite3.ProgrammingError):
            backend._conn.execute("SELECT 1")

    def test_different_namespace_is_a_different_memory(self, tmp_path: Path) -> None:
        a = _runtime(_cfg(tmp_path, namespace="a"), tmp_path)
        b = _runtime(_cfg(tmp_path, namespace="b"), tmp_path)
        try:
            assert a.memory is not b.memory
        finally:
            a.close()
            b.close()

    def test_hold_survives_remove_then_create(self, tmp_path: Path) -> None:
        cfg = _cfg(tmp_path)
        first = _runtime(cfg, tmp_path)
        mem = first.memory
        with hold_shared_memory(cfg, tmp_path):
            first.close()
            assert getattr(mem.backend, "_conn", None) is not None
            second = _runtime(cfg, tmp_path)
        try:
            assert second.memory is mem
        finally:
            second.close()


class TestManagerRebuildKeepsMemory:
    @pytest.mark.asyncio
    async def test_arebuild_reuses_memory_object(self, tmp_path: Path) -> None:
        cfg = _cfg(tmp_path)
        providers = list(cfg.providers)
        with (
            patch("langchain_openai.ChatOpenAI", return_value=MagicMock()),
            patch("deepagents.create_deep_agent", return_value=MagicMock()),
        ):
            mgr = HarnessAgentManager(providers=providers)
            created = await mgr.acreate_agent(cfg, agent_id="aid1", init_workspace=False)
            mem = created.agent.memory
            assert mem is not None
            rebuilt = await mgr.arebuild_agent("aid1", cfg)
            assert rebuilt.agent is not created.agent
            assert rebuilt.agent.memory is mem
            mgr.close()

    def test_rebuild_agent_reuses_memory_object(self, tmp_path: Path) -> None:
        cfg = _cfg(tmp_path)
        providers = list(cfg.providers)
        with (
            patch("langchain_openai.ChatOpenAI", return_value=MagicMock()),
            patch("deepagents.create_deep_agent", return_value=MagicMock()),
        ):
            mgr = HarnessAgentManager(providers=providers)
            created = mgr.create_agent(cfg, agent_id="aid1", init_workspace=False)
            mem = created.agent.memory
            mgr._rebuild_agent("aid1")
            rebuilt = mgr.get_agent("aid1")
            assert rebuilt.agent is not created.agent
            assert rebuilt.agent.memory is mem
            assert isinstance(rebuilt.agent, HarnessAgent)
            mgr.close()
