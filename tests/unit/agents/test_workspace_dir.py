"""Unit tests for ``workspace_dir`` (independent of ``root_dir`` for harness)."""

from __future__ import annotations

from pathlib import Path

from octop.infra.agents.workspace_dir import (
    agent_facing_workspace_dir_from_config,
    agent_facing_workspace_root,
    default_agent_workspace_dir,
    harness_workspace_path,
    join_agent_facing,
    resolve_workspace_host_path,
    scoped_workspace_dir_str,
    seed_workspace_dir_on_create,
    workspace_dir_from_config,
)
from octop.infra.utils.paths import PathLayout


def _scoped_cfg(root: Path, **extra: object) -> dict:
    return {
        "backend": {
            "type": "local_shell",
            "root_dir": str(root),
            "virtual_mode": True,
        },
        **extra,
    }


def test_scoped_default_persists_agent_facing_path(tmp_path: Path) -> None:
    root = tmp_path / "home"
    root.mkdir()
    paths = PathLayout(tmp_path / "octop-home")
    cfg = _scoped_cfg(root)
    host = seed_workspace_dir_on_create(cfg, paths=paths, agent_id="J1BT2X")
    assert cfg["workspace_dir"] == "/.octop/workspaces/J1BT2X"
    # On-disk tree still lands under the jail root_dir.
    assert host == (root / ".octop" / "workspaces" / "J1BT2X").resolve()
    assert host.is_dir()
    # Host ops map; harness should keep the persisted string as-is.
    assert resolve_workspace_host_path(cfg["workspace_dir"], cfg) == host
    assert Path(cfg["workspace_dir"]) != host
    assert agent_facing_workspace_dir_from_config(cfg) == "/.octop/workspaces/J1BT2X"
    assert (
        agent_facing_workspace_root(
            host,
            root_dir=root,
            virtual_mode=True,
        )
        == "/.octop/workspaces/J1BT2X"
    )
    assert join_agent_facing("/.octop/workspaces/J1BT2X", "inbound/a.zip") == (
        "/.octop/workspaces/J1BT2X/inbound/a.zip"
    )


def test_host_ops_map_octop_workspaces_under_root(tmp_path: Path) -> None:
    root = tmp_path / "home"
    expected = root / ".octop" / "workspaces" / "J1BT2X"
    expected.mkdir(parents=True)
    cfg = _scoped_cfg(root)
    assert resolve_workspace_host_path("/.octop/workspaces/J1BT2X", cfg) == expected.resolve()


def test_user_assigned_workspace_wins(tmp_path: Path) -> None:
    root = tmp_path / "home"
    root.mkdir()
    custom = tmp_path / "custom-ws"
    paths = PathLayout(tmp_path / "octop-home")
    cfg = _scoped_cfg(root, workspace_dir=str(custom))
    host = seed_workspace_dir_on_create(cfg, paths=paths, agent_id="USR1")
    assert cfg["workspace_dir"] == str(custom)
    assert host == custom.resolve()


def test_host_rooted_default_uses_octop_home(tmp_path: Path) -> None:
    paths = PathLayout(tmp_path / ".octop")
    cfg = {
        "backend": {"type": "local_shell", "root_dir": "/", "virtual_mode": True},
    }
    host = seed_workspace_dir_on_create(cfg, paths=paths, agent_id="A1")
    assert cfg["workspace_dir"] == str(host)
    assert host == (tmp_path / ".octop" / "agents" / "A1").resolve()


def test_harness_workspace_keeps_absolute_persisted_value(tmp_path: Path) -> None:
    root = tmp_path / "home"
    cfg = _scoped_cfg(root, workspace_dir=str(tmp_path / "ws"))
    assert harness_workspace_path(cfg["workspace_dir"], cfg) == tmp_path / "ws"


def test_harness_workspace_maps_non_absolute_persisted_value(tmp_path: Path) -> None:
    """Windows cannot express ``/.octop/workspaces/<id>`` as absolute — host-map it."""
    root = tmp_path / "home"
    cfg = _scoped_cfg(root, workspace_dir=".octop/workspaces/W1N")
    assert harness_workspace_path(cfg["workspace_dir"], cfg) == (
        root / ".octop" / "workspaces" / "W1N"
    )


def test_workspace_dir_from_config_roundtrip(tmp_path: Path) -> None:
    root = tmp_path / "home"
    paths = PathLayout(tmp_path / "octop-home")
    cfg = _scoped_cfg(root)
    host = default_agent_workspace_dir(paths, "RT001", cfg=cfg)
    cfg["workspace_dir"] = scoped_workspace_dir_str("RT001")
    assert workspace_dir_from_config(cfg, paths=paths, agent_id="RT001") == host.resolve()
