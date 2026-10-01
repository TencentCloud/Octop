"""Create, update, and reload entry points for subtree experts.

Helper-only checks live in ``test_windows_root`` and ``test_workspace_dir``.
These tests call ``AgentManager.create``, ``AgentManager.update``, and
``_build_harness_config`` (the load path used when a record is started).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from octop.config import OctopConfig
from octop.infra.agents.manager import AgentCreateSpec, AgentManager
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRow
from octop.infra.db.services import build_shared_services
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.paths import PathLayout

_MEMORY_OFF: dict[str, Any] = {"memory": {"memory_enabled": False}}


@pytest.fixture
def manager(tmp_path: Path) -> AgentManager:
    paths = PathLayout(tmp_path / ".octop")
    paths.ensure_root()
    db = SqlitePool(paths.db)
    run_migrations(db)
    services = build_shared_services(db=db, paths=paths, config=OctopConfig())
    return AgentManager(repos=services.repos, paths=services.paths)


def _row(
    *,
    agent_id: str = "01AGENT",
    config_json: str | None = None,
) -> AgentRow:
    return AgentRow(
        id=1,
        agent_id=agent_id,
        user_id=1,
        name="bot",
        description=None,
        persona_mbti=None,
        default_model=None,
        system_prompt=None,
        enabled=1,
        config_json=config_json,
        last_state=None,
        last_error=None,
        created_at=0,
        updated_at=0,
    )


def _enable_windows_create(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "octop.infra.agents.workspace.windows_root.windows_new_expert_subtree_enabled",
        lambda: True,
    )


def _freeze_home(monkeypatch: pytest.MonkeyPatch, home: str) -> None:
    monkeypatch.setattr("octop.infra.utils.host_dirs.host_home_dir", lambda: home)
    monkeypatch.setattr("octop.infra.utils.host_dirs.host_path_text", lambda path: str(path))


def _tree(root: Path) -> set[str]:
    if not root.exists():
        return set()
    return {str(path.relative_to(root)) for path in root.rglob("*")}


@pytest.mark.asyncio
async def test_posix_create_does_not_stamp_subtree(
    manager: AgentManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _noop(_row: AgentRow) -> None:
        return None

    monkeypatch.setattr(manager, "_complete_create_bootstrap", _noop)
    row = await manager.create(
        AgentCreateSpec(name="posix-expert", config=dict(_MEMORY_OFF)),
        defer_bootstrap=True,
    )
    assert "root_semantics" not in manager.get_config(row.agent_id)


@pytest.mark.asyncio
async def test_create_normalizes_string_backend_and_rejects_relative_home(
    manager: AgentManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_windows_create(monkeypatch)
    _freeze_home(monkeypatch, "work")
    before = _tree(manager.paths.root)
    with pytest.raises(OctopError, match="fully qualified") as caught:
        await manager.create(
            AgentCreateSpec(name="string-backend", config={**_MEMORY_OFF, "backend": "local_shell"}),
            defer_bootstrap=True,
        )
    assert caught.value.code is ErrorCode.WORKSPACE_ROOT_RESTRICTED
    assert manager._repos.agent_repo.list_all() == []
    assert _tree(manager.paths.root) == before


@pytest.mark.asyncio
async def test_create_rejects_relative_root_before_mkdir(
    manager: AgentManager,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _enable_windows_create(monkeypatch)
    before = _tree(manager.paths.root)
    with pytest.raises(OctopError, match="fully qualified"):
        await manager.create(
            AgentCreateSpec(
                name="relative-root",
                config={
                    **_MEMORY_OFF,
                    "backend": {
                        "type": "local_shell",
                        "root_dir": "./work",
                        "virtual_mode": True,
                    },
                },
            ),
            defer_bootstrap=True,
        )
    assert manager._repos.agent_repo.list_all() == []
    assert _tree(manager.paths.root) == before
    assert not (tmp_path / "work").exists()


@pytest.mark.asyncio
async def test_create_rejects_virtual_mode_off_before_mkdir(
    manager: AgentManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_windows_create(monkeypatch)
    sentinel = Path.cwd() / "C:"
    existed = sentinel.exists()
    before = _tree(manager.paths.root)
    with pytest.raises(OctopError, match="virtual_mode") as caught:
        await manager.create(
            AgentCreateSpec(
                name="virtual-off",
                config={
                    **_MEMORY_OFF,
                    "backend": {
                        "type": "local_shell",
                        "root_dir": "C:/work",
                        "virtual_mode": False,
                    },
                },
            ),
            defer_bootstrap=True,
        )
    assert caught.value.code is ErrorCode.WORKSPACE_ROOT_RESTRICTED
    assert manager._repos.agent_repo.list_all() == []
    assert _tree(manager.paths.root) == before
    assert sentinel.exists() is existed


def _silence_bootstrap(manager: AgentManager, monkeypatch: pytest.MonkeyPatch) -> None:
    async def _noop(_row: AgentRow) -> None:
        return None

    monkeypatch.setattr(manager, "_complete_create_bootstrap", _noop)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "backend",
    [
        {"type": "docker", "image": "octop"},
        "docker",
        {"type": "composite", "default": {"type": "store"}},
        {"type": "s3", "bucket": "exports"},
    ],
)
async def test_create_keeps_supported_non_local_backends(
    manager: AgentManager,
    monkeypatch: pytest.MonkeyPatch,
    backend: object,
) -> None:
    """Non-local backends skip subtree checks, including the new harness field."""
    _enable_windows_create(monkeypatch)
    _silence_bootstrap(manager, monkeypatch)
    monkeypatch.setattr(
        "octop.infra.agents.manager._HARNESS_AGENT_CONFIG_FIELDS",
        frozenset({"name", "workspace_dir"}),
    )
    expected = copy.deepcopy(backend)
    row = await manager.create(
        AgentCreateSpec(
            name="non-local",
            config={**_MEMORY_OFF, "backend": backend},
        ),
        defer_bootstrap=True,
    )
    stored = manager.get_config(row.agent_id)
    assert "root_semantics" not in stored
    assert stored["backend"] == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "backend",
    ["nope", {}, {"type": "not-a-backend"}, ["local_shell"]],
)
async def test_create_rejects_uninterpretable_backend_before_mkdir(
    manager: AgentManager,
    monkeypatch: pytest.MonkeyPatch,
    backend: object,
) -> None:
    _enable_windows_create(monkeypatch)
    before = _tree(manager.paths.root)
    with pytest.raises(OctopError, match="unsupported backend") as caught:
        await manager.create(
            AgentCreateSpec(name="bad-backend", config={**_MEMORY_OFF, "backend": backend}),
            defer_bootstrap=True,
        )
    assert caught.value.code is ErrorCode.WORKSPACE_ROOT_RESTRICTED
    assert manager._repos.agent_repo.list_all() == []
    assert _tree(manager.paths.root) == before


@pytest.mark.asyncio
async def test_create_composite_keeps_the_existing_scoped_workspace(
    manager: AgentManager,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A composite root still follows the pre-subtree scoped workspace path."""
    _enable_windows_create(monkeypatch)
    _silence_bootstrap(manager, monkeypatch)
    monkeypatch.setattr(
        "octop.infra.agents.manager._HARNESS_AGENT_CONFIG_FIELDS",
        frozenset({"name", "workspace_dir"}),
    )
    jail = tmp_path / "jail"
    jail.mkdir()
    backend = {
        "type": "composite",
        "default": {
            "type": "filesystem",
            "root_dir": str(jail),
            "virtual_mode": True,
        },
    }
    row = await manager.create(
        AgentCreateSpec(name="composite-scoped", config={**_MEMORY_OFF, "backend": backend}),
        defer_bootstrap=True,
    )
    stored = manager.get_config(row.agent_id)
    assert "root_semantics" not in stored
    assert stored["backend"] == backend
    assert stored["workspace_dir"] == f"/.octop/workspaces/{row.agent_id}"
    assert (jail / ".octop" / "workspaces" / row.agent_id).is_dir()


@pytest.mark.asyncio
async def test_create_fails_before_mkdir_when_harness_lacks_explicit_paths(
    manager: AgentManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_windows_create(monkeypatch)
    monkeypatch.setattr(
        "octop.infra.agents.manager._HARNESS_AGENT_CONFIG_FIELDS",
        frozenset({"name", "workspace_dir"}),
    )
    sentinel = Path.cwd() / "C:"
    existed = sentinel.exists()
    before = _tree(manager.paths.root)
    with pytest.raises(OctopError, match="explicit_virtual_paths") as caught:
        await manager.create(
            AgentCreateSpec(
                name="no-runtime",
                config={
                    **_MEMORY_OFF,
                    "backend": {
                        "type": "local_shell",
                        "root_dir": "C:/work",
                        "virtual_mode": True,
                    },
                },
            ),
            defer_bootstrap=True,
        )
    assert caught.value.code is ErrorCode.WORKSPACE_OP_UNSUPPORTED
    assert manager._repos.agent_repo.list_all() == []
    assert _tree(manager.paths.root) == before
    assert sentinel.exists() is existed


def _subtree_config(agent_id: str, root: Path) -> dict[str, Any]:
    return {
        **_MEMORY_OFF,
        "root_semantics": "subtree",
        "workspace_dir": f"/.octop/workspaces/{agent_id}",
        "backend": {
            "type": "filesystem",
            "root_dir": str(root),
            "virtual_mode": True,
        },
    }


@pytest.mark.asyncio
async def test_update_preserves_stored_root_semantics(
    manager: AgentManager,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    async def _noop(_row: AgentRow) -> None:
        return None

    monkeypatch.setattr(manager, "_complete_create_bootstrap", _noop)
    monkeypatch.setattr(manager, "_schedule_reload", lambda _agent_id: None)
    row = await manager.create(
        AgentCreateSpec(name="subtree-kept", config=dict(_MEMORY_OFF)),
        defer_bootstrap=True,
    )
    root = tmp_path / "selected"
    root.mkdir()
    stored = _subtree_config(row.agent_id, root)
    manager._repos.agent_repo.update_config(
        row.agent_id,
        config_json=json.dumps(stored),
    )

    omitted = dict(stored)
    omitted.pop("root_semantics")
    omitted["foo"] = 1
    await manager.update(row.agent_id, config_json=json.dumps(omitted))
    assert manager.get_config(row.agent_id).get("root_semantics") == "subtree"

    deleted = dict(stored)
    deleted["root_semantics"] = None
    deleted["foo"] = 2
    await manager.update(row.agent_id, config_json=json.dumps(deleted))
    assert manager.get_config(row.agent_id).get("root_semantics") == "subtree"

    forged = dict(stored)
    forged["root_semantics"] = "forged"
    forged["foo"] = 3
    await manager.update(row.agent_id, config_json=json.dumps(forged))
    assert manager.get_config(row.agent_id).get("root_semantics") == "subtree"

    loaded = manager._build_harness_config(manager.get_row(row.agent_id) or row)
    assert loaded.explicit_virtual_paths is True
    assert (root / ".octop" / "workspaces" / row.agent_id).is_dir()


@pytest.mark.asyncio
async def test_update_cannot_forge_root_semantics_onto_an_old_record(
    manager: AgentManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _noop(_row: AgentRow) -> None:
        return None

    monkeypatch.setattr(manager, "_complete_create_bootstrap", _noop)
    monkeypatch.setattr(manager, "_schedule_reload", lambda _agent_id: None)
    row = await manager.create(
        AgentCreateSpec(name="old-record", config=dict(_MEMORY_OFF)),
        defer_bootstrap=True,
    )
    assert "root_semantics" not in manager.get_config(row.agent_id)

    await manager.update(
        row.agent_id,
        config_json=json.dumps({"foo": 1, "root_semantics": "subtree"}),
    )
    assert "root_semantics" not in manager.get_config(row.agent_id)

    loaded = manager._build_harness_config(manager.get_row(row.agent_id) or row)
    assert loaded.explicit_virtual_paths is False


def test_load_subtree_fails_before_write_when_harness_lacks_the_flag(
    manager: AgentManager,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / ".octop").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(
        "octop.infra.agents.manager._HARNESS_AGENT_CONFIG_FIELDS",
        frozenset({"name", "workspace_dir"}),
    )
    row = _row(
        agent_id="SUB1",
        config_json=json.dumps(_subtree_config("SUB1", root)),
    )
    with pytest.raises(OctopError, match="explicit_virtual_paths") as caught:
        manager._build_harness_config(row)
    assert caught.value.code is ErrorCode.WORKSPACE_OP_UNSUPPORTED
    assert not (outside / "workspaces").exists()
