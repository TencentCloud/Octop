"""Shared pytest fixtures for octop_harness tests."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from pathlib import Path

import pytest

from octop_harness.agent import HarnessAgent
from octop_harness.config import HarnessAgentConfig, ModelConfig, ProviderConfig
from octop_harness.manager import HarnessAgentManager
from octop_harness.observability.logging import teardown_logging


def close_memory_instance(memory: object) -> None:
    """Close backend and langgraph checkpointer connections on a ``Memory``."""
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


@pytest.fixture(autouse=True)
def _isolate_home_for_runtime_logs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """Keep default ``~/.octop-harness/logs`` out of the developer's real HOME."""
    home = tmp_path.parent / f"{tmp_path.name}_isolated_home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    # init caches this path at import time, before this fixture changes HOME.
    # Overwrite tests must never write the developer's real provider template.
    monkeypatch.setattr("octop_harness.init._PROVIDERS_USER_DIR", home / ".octop-harness")
    teardown_logging()
    yield
    teardown_logging()


@pytest.fixture(autouse=True)
def _close_octop_harnesss_created_in_test() -> Iterator[None]:
    """Close every ``HarnessAgent`` / ``HarnessAgentManager`` built in a test."""
    created_agents: list[HarnessAgent] = []
    created_managers: list[HarnessAgentManager] = []
    original_agent_init = HarnessAgent.__init__
    original_manager_init = HarnessAgentManager.__init__

    def tracking_agent_init(self: HarnessAgent, config: HarnessAgentConfig, **kwargs: object) -> None:
        original_agent_init(self, config, **kwargs)  # type: ignore[arg-type]
        created_agents.append(self)

    def tracking_manager_init(self: HarnessAgentManager, *args: object, **kwargs: object) -> None:
        original_manager_init(self, *args, **kwargs)  # type: ignore[arg-type]
        created_managers.append(self)

    HarnessAgent.__init__ = tracking_agent_init  # type: ignore[method-assign]
    HarnessAgentManager.__init__ = tracking_manager_init  # type: ignore[method-assign]
    try:
        yield
    finally:
        HarnessAgent.__init__ = original_agent_init  # type: ignore[method-assign]
        HarnessAgentManager.__init__ = original_manager_init  # type: ignore[method-assign]
        for manager in created_managers:
            with contextlib.suppress(Exception):
                manager.close()
        for agent in created_agents:
            with contextlib.suppress(Exception):
                agent.close()


@pytest.fixture(autouse=True)
def _close_memory_instances_created_in_test() -> Iterator[None]:
    """Close every ``octop_memory.Memory`` constructed during a test."""
    try:
        from octop_memory import Memory
    except ImportError:
        yield
        return

    created: list[object] = []
    original_init = Memory.__init__

    def tracking_init(self: object, *args: object, **kwargs: object) -> None:
        original_init(self, *args, **kwargs)
        created.append(self)

    Memory.__init__ = tracking_init  # type: ignore[method-assign]
    try:
        yield
    finally:
        Memory.__init__ = original_init  # type: ignore[method-assign]
        for memory in created:
            close_memory_instance(memory)


@pytest.fixture
def sample_provider() -> ProviderConfig:
    return ProviderConfig(
        id="ex",
        base_url="https://api.example.com/v1",
        api_key="sk-test",
        name="Example",
        protocol="openai",
        models=[
            ModelConfig(id="text-only", input=["text"]),
            ModelConfig(id="multimodal", input=["text", "image"]),
            ModelConfig(id="disabled", input=["text"], enabled=False),
        ],
    )


@pytest.fixture
def sample_config(sample_provider: ProviderConfig, tmp_path: Path) -> HarnessAgentConfig:
    return HarnessAgentConfig(
        name="test-agent",
        workspace_dir=tmp_path,
        providers=[sample_provider],
        default_model="ex/text-only",
        memory_enabled=False,
        checkpointer=False,
    )


@pytest.fixture
def workspace_root(tmp_path: Path) -> Iterator[Path]:
    """An empty directory ready to be used as ``workspace_dir`` in tests."""
    yield tmp_path
