"""Unit tests for ``workspace_dir`` (independent of ``root_dir`` for harness)."""

from __future__ import annotations

from pathlib import Path

import pytest

from octop.infra.agents.workspace.dir import (
    agent_facing_workspace_dir_from_config,
    agent_facing_workspace_root,
    default_agent_workspace_dir,
    harness_workspace_path,
    join_agent_facing,
    resolve_workspace_host_path,
    scoped_workspace_dir_str,
    seed_workspace_dir_on_create,
    uses_scoped_workspace_default,
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


@pytest.mark.parametrize("root_dir", ["C:/", "C:\\", "D:", "d:/"])
def test_windows_drive_root_is_host_sentinel(tmp_path: Path, root_dir: str) -> None:
    """Drive roots must use OCTOP_HOME agents/, not {drive}/.octop/workspaces/."""
    paths = PathLayout(tmp_path / ".octop")
    cfg = {
        "backend": {
            "type": "local_shell",
            "root_dir": root_dir,
            "virtual_mode": True,
        },
    }
    host = seed_workspace_dir_on_create(cfg, paths=paths, agent_id="WIN1")
    assert cfg["workspace_dir"] == str(host)
    assert host == (tmp_path / ".octop" / "agents" / "WIN1").resolve()
    assert ".octop/workspaces" not in cfg["workspace_dir"].replace("\\", "/")


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


def test_workspace_dir_from_config_ensure_false_does_not_mkdir(tmp_path: Path) -> None:
    paths = PathLayout(tmp_path / "octop-home")
    missing = tmp_path / "gone" / "YZQ7X4"
    cfg = {"workspace_dir": str(missing)}
    out = workspace_dir_from_config(cfg, paths=paths, agent_id="YZQ7X4", ensure=False)
    assert out == missing.resolve()
    assert not missing.exists()


def test_default_workspace_ensure_false_does_not_mkdir(tmp_path: Path) -> None:
    paths = PathLayout(tmp_path / "octop-home")
    out = default_agent_workspace_dir(paths, "A1", ensure=False)
    assert out == paths.agent_workspace("A1")
    assert not out.exists()


def test_subtree_drive_root_stays_scoped() -> None:
    cfg = {
        "root_semantics": "subtree",
        "backend": {"type": "local_shell", "root_dir": "D:/", "virtual_mode": True},
    }
    assert uses_scoped_workspace_default(cfg) is True


def test_subtree_workspace_lands_under_root(tmp_path: Path) -> None:
    root = tmp_path / "work"
    root.mkdir()
    paths = PathLayout(tmp_path / "octop-home")
    cfg = _scoped_cfg(
        root,
        root_semantics="subtree",
        workspace_dir=str(tmp_path / "elsewhere"),
    )
    host = seed_workspace_dir_on_create(cfg, paths=paths, agent_id="SUB1")
    assert host == (root / ".octop" / "workspaces" / "SUB1").resolve()
    assert cfg["workspace_dir"] == "/.octop/workspaces/SUB1"
    assert host.is_dir()
    assert not (paths.agents_dir / "SUB1").exists()
    assert not (host / ".octop-write-probe").exists()


def test_subtree_symlink_escape_fails_before_any_write(tmp_path: Path) -> None:
    """A root `.octop` symlink must not receive `workspaces/<id>` before the error."""
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / ".octop").symlink_to(outside, target_is_directory=True)
    kept = root / ".octop-write-probe"
    kept.write_text("keep", encoding="utf-8")
    paths = PathLayout(tmp_path / "octop-home")
    cfg = _scoped_cfg(root, root_semantics="subtree")
    with pytest.raises(ValueError, match="outside the selected root"):
        seed_workspace_dir_on_create(cfg, paths=paths, agent_id="SUBLINK")
    assert not (outside / "workspaces").exists()
    assert kept.read_text(encoding="utf-8") == "keep"
    assert not paths.agents_dir.exists()


def test_subtree_probe_does_not_clobber_an_existing_file(tmp_path: Path) -> None:
    root = tmp_path / "work"
    root.mkdir()
    paths = PathLayout(tmp_path / "octop-home")
    cfg = _scoped_cfg(root, root_semantics="subtree")
    host = seed_workspace_dir_on_create(cfg, paths=paths, agent_id="SUBPROBE")
    kept = host / ".octop-write-probe"
    kept.write_text("keep", encoding="utf-8")
    again = _scoped_cfg(root, root_semantics="subtree")
    seed_workspace_dir_on_create(again, paths=paths, agent_id="SUBPROBE")
    assert kept.read_text(encoding="utf-8") == "keep"
    assert not any(path.name.startswith(".octop-write-probe-") for path in host.iterdir())


def test_subtree_create_does_not_fall_back_to_octop_home(tmp_path: Path) -> None:
    blocked = tmp_path / "not-a-directory"
    blocked.write_text("x", encoding="utf-8")
    paths = PathLayout(tmp_path / "octop-home")
    cfg = _scoped_cfg(blocked, root_semantics="subtree")
    with pytest.raises(ValueError, match="workspace create failed"):
        seed_workspace_dir_on_create(cfg, paths=paths, agent_id="SUB2")
    assert not paths.agents_dir.exists()
