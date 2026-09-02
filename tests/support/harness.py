"""Patch harness-agent so tests run without a real LLM."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from tests.support.fakes import FakeHarnessAgent


def _sync_fake_skill_dirs(agent: FakeHarnessAgent, config: Any) -> None:
    """Mirror harness ``skills_dir`` onto the fake so package skills list correctly."""
    skills_dir = getattr(config, "skills_dir", None)
    agent.config.skills_dir = skills_dir
    roots: list[dict[str, str]] = []
    for raw in skills_dir or ():
        path = Path(str(raw))
        package_id = ""
        parts = path.parts
        if "skill-packages" in parts:
            idx = parts.index("skill-packages")
            if idx + 1 < len(parts):
                package_id = parts[idx + 1]
        if package_id:
            roots.append({"id": package_id, "path": str(path)})
    agent.config.skill_package_roots = roots or None


def _wire_add_provider(mock_manager: MagicMock) -> None:
    def _add_provider(provider: Any) -> None:
        mock_manager._providers.append(provider)
        if mock_manager._shared_factory is None:
            factory = MagicMock()
            factory._providers = {provider.id: provider}
            mock_manager._shared_factory = factory
            mock_manager.shared_factory = factory
        else:
            mock_manager._shared_factory._providers[provider.id] = provider

    mock_manager.add_provider = MagicMock(side_effect=_add_provider)
    mock_manager.remove_provider = MagicMock()


def build_harness_manager_mock(
    *,
    fake_agent: Any | None = None,
    providers: list[Any] | None = None,
) -> MagicMock:
    """Return a MagicMock that quacks like HarnessAgentManager."""
    from harness_agent.manager import AgentEntry  # type: ignore[import]

    agent = fake_agent if fake_agent is not None else FakeHarnessAgent()
    entries: dict[str, AgentEntry] = {}

    def _create(config: Any, agent_id: str | None = None, **_kw: Any) -> AgentEntry:
        aid = agent_id or "fake"
        if isinstance(agent, FakeHarnessAgent):
            entry_agent: Any = FakeHarnessAgent(
                chunks=list(agent.chunks),
                raise_on_stream=agent.raise_on_stream,
            )
        else:
            entry_agent = agent
        ws_dir = getattr(config, "workspace_dir", None)
        if ws_dir is not None and isinstance(entry_agent, FakeHarnessAgent):
            backend_cfg = getattr(config, "backend", None)
            virtual_mode = True
            if isinstance(backend_cfg, dict):
                virtual_mode = bool(backend_cfg.get("virtual_mode", True))
                root_dir = str(backend_cfg.get("root_dir") or "").strip()
                if virtual_mode and root_dir not in {"", "/", "\\"}:
                    ws_dir = Path(root_dir) / str(ws_dir).lstrip("/\\")
            entry_agent.use_workspace_dir(Path(str(ws_dir)), virtual_mode=virtual_mode)
        if isinstance(entry_agent, FakeHarnessAgent):
            _sync_fake_skill_dirs(entry_agent, config)
        entry = AgentEntry(
            agent_id=aid,
            agent=entry_agent,
            config=config,
            metadata={},
            tags=[],
            created_at=datetime.now(tz=UTC),
        )
        entries[aid] = entry
        return entry

    def _get_agent(agent_id: str) -> AgentEntry:
        return entries[agent_id]

    def _remove(agent_id: str) -> None:
        entries.pop(agent_id, None)

    async def _acreate(config: Any, agent_id: str | None = None, **kw: Any) -> AgentEntry:
        entry = _create(config, agent_id=agent_id, **kw)
        if kw.get("init_workspace", True) and isinstance(entry.agent, FakeHarnessAgent):
            await entry.agent.seed_default_subagent()
        return entry

    async def _arebuild(agent_id: str, config: Any, **kw: Any) -> AgentEntry:
        old_entry = entries.get(agent_id)
        old_agent = old_entry.agent if old_entry else None
        # Reuse the existing FakeHarnessAgent on reload so in-memory state
        # (workspace files, ``skills_disabled``, …) survives the rebuild — a
        # real running harness agent is the same object across reloads.
        if isinstance(old_agent, FakeHarnessAgent):
            ws_dir = old_agent._workspace_dir
            backend_cfg = getattr(config, "backend", None)
            virtual_mode = True
            if isinstance(backend_cfg, dict):
                virtual_mode = bool(backend_cfg.get("virtual_mode", True))
            old_agent.use_workspace_dir(ws_dir, virtual_mode=virtual_mode)
            _sync_fake_skill_dirs(old_agent, config)
            entry = AgentEntry(
                agent_id=agent_id,
                agent=old_agent,
                config=config,
                metadata={},
                tags=[],
                created_at=datetime.now(tz=UTC),
            )
            entries[agent_id] = entry
            return entry
        ws_dir = old_agent._workspace_dir if isinstance(old_agent, FakeHarnessAgent) else None
        _remove(agent_id)
        entry = await _acreate(config, agent_id=agent_id, init_workspace=False, **kw)
        if ws_dir is not None and isinstance(entry.agent, FakeHarnessAgent):
            backend_cfg = getattr(config, "backend", None)
            virtual_mode = True
            if isinstance(backend_cfg, dict):
                virtual_mode = bool(backend_cfg.get("virtual_mode", True))
            entry.agent.use_workspace_dir(ws_dir, virtual_mode=virtual_mode)
            _sync_fake_skill_dirs(entry.agent, config)
        return entry

    async def _aremove(agent_id: str) -> None:
        _remove(agent_id)

    mock_manager = MagicMock()
    mock_manager.create_agent.side_effect = _create
    mock_manager.acreate_agent = AsyncMock(side_effect=_acreate)
    mock_manager.arebuild_agent = AsyncMock(side_effect=_arebuild)
    mock_manager.aremove_agent = AsyncMock(side_effect=_aremove)
    mock_manager.get_agent.side_effect = _get_agent
    mock_manager.remove_agent.side_effect = _remove

    def _stream(agent_id: str, request: Any) -> Any:
        return _get_agent(agent_id).agent.stream(request)

    def _call(agent_id: str, request: Any) -> Any:
        agent_obj = _get_agent(agent_id).agent
        if hasattr(agent_obj, "call"):
            return agent_obj.call(request)
        raise NotImplementedError("fake agent has no call()")

    def _resume_hitl(agent_id: str, thread_id: str, decisions: Any) -> Any:
        agent_obj = _get_agent(agent_id).agent
        if hasattr(agent_obj, "resume_hitl"):
            return agent_obj.resume_hitl(thread_id, decisions)
        raise NotImplementedError("fake agent has no resume_hitl()")

    mock_manager.stream = MagicMock(side_effect=_stream)
    mock_manager.call = MagicMock(side_effect=_call)
    mock_manager.resume_hitl = MagicMock(side_effect=_resume_hitl)
    mock_manager._shared_factory = None
    mock_manager.shared_factory = None
    mock_manager._providers = []
    mock_manager.team = MagicMock()
    mock_manager.team.team_tools.return_value = []
    _wire_add_provider(mock_manager)
    for provider in providers or []:
        mock_manager.add_provider(provider)
    return mock_manager


@contextmanager
def patch_harness(fake_agent: Any | None = None):
    """Patch the AgentManager harness layer so tests run without a real LLM."""
    agent = fake_agent if fake_agent is not None else FakeHarnessAgent()

    def _constructor(**kw: Any) -> MagicMock:
        return build_harness_manager_mock(
            fake_agent=agent,
            providers=kw.get("providers"),
        )

    with patch(
        "octop.infra.agents.manager.HarnessAgentManager",
        side_effect=_constructor,
    ):
        yield agent
