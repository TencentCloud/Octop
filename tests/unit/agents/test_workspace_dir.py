"""Unit tests for ``workspace_dir`` (independent of ``root_dir`` for harness)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from octop.infra.agents.workspace.dir import (
    _is_host_root_sentinel,
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


@pytest.mark.skipif(os.name != "nt", reason="Windows drive-root semantics")
@pytest.mark.parametrize("sep", ["/", "\\"])
def test_windows_home_drive_root_is_host_sentinel(tmp_path: Path, sep: str) -> None:
    """A drive root on the OCTOP_HOME drive keeps OCTOP_HOME agents/ workspaces."""
    home_drive_root = f"{tmp_path.drive}{sep}"
    paths = PathLayout(tmp_path / ".octop")
    cfg = {
        "backend": {
            "type": "local_shell",
            "root_dir": home_drive_root,
            "virtual_mode": True,
        },
    }
    host = seed_workspace_dir_on_create(cfg, paths=paths, agent_id="WIN1")
    assert cfg["workspace_dir"] == str(host)
    assert host == (tmp_path / ".octop" / "agents" / "WIN1").resolve()
    assert ".octop/workspaces" not in cfg["workspace_dir"].replace("\\", "/")


@pytest.mark.skipif(os.name != "nt", reason="Windows drive-root semantics")
def test_windows_foreign_drive_root_is_scoped_jail(tmp_path: Path) -> None:
    """Drive root on another drive is a scoped jail (issue #2386).

    Defaulting such a workspace to OCTOP_HOME would place it outside the
    backend root, so every workspace path (skills, memory) fails the
    virtual-mode containment check and chat breaks. The workspace must land
    under the chosen drive root instead.
    """
    foreign_roots = [
        f"{chr(letter)}:/"
        for letter in range(ord("A"), ord("Z") + 1)
        if f"{chr(letter)}:" != tmp_path.drive and Path(f"{chr(letter)}:/").is_dir()
    ]
    if not foreign_roots:
        pytest.skip("machine exposes a single drive")
    root_dir = foreign_roots[0]
    paths = PathLayout(tmp_path / ".octop")
    cfg = {
        "backend": {
            "type": "local_shell",
            "root_dir": root_dir,
            "virtual_mode": True,
        },
    }
    host = seed_workspace_dir_on_create(cfg, paths=paths, agent_id="WIN2")
    assert cfg["workspace_dir"] == "/.octop/workspaces/WIN2"
    assert host == (Path(root_dir) / ".octop" / "workspaces" / "WIN2").resolve()
    assert resolve_workspace_host_path(cfg["workspace_dir"], cfg) == host


def test_host_root_sentinel_drive_semantics(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only a home-drive root is the host tree; foreign drive roots are jails."""
    import octop.infra.utils.host_dirs as host_dirs

    monkeypatch.setattr(os, "name", "nt", raising=False)
    monkeypatch.setattr(host_dirs, "host_fs_tree_root", lambda: "C:/")
    assert _is_host_root_sentinel("C:/") is True
    assert _is_host_root_sentinel("c:\\") is True
    assert _is_host_root_sentinel("/") is True
    assert _is_host_root_sentinel(None) is True
    assert _is_host_root_sentinel("E:/") is False
    assert _is_host_root_sentinel("e:") is False
    assert _is_host_root_sentinel("D:/data") is False


def test_host_root_sentinel_posix_drive_letter_keeps_legacy_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import octop.infra.utils.host_dirs as host_dirs

    monkeypatch.setattr(os, "name", "posix", raising=False)
    monkeypatch.setattr(host_dirs, "host_fs_tree_root", lambda: "/")
    assert _is_host_root_sentinel("D:/") is True


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


def test_workspace_dir_from_config_falls_back_when_unwritable(tmp_path: Path) -> None:
    paths = PathLayout(tmp_path / "octop-home")
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x", encoding="utf-8")
    stale = blocker / "YZQ7X4"
    cfg = {"workspace_dir": str(stale)}
    out = workspace_dir_from_config(cfg, paths=paths, agent_id="YZQ7X4")
    assert out == paths.agent_workspace("YZQ7X4")
    assert out.is_dir()
    assert not stale.exists()


def test_default_workspace_falls_back_when_scoped_root_unwritable(tmp_path: Path) -> None:
    paths = PathLayout(tmp_path / "octop-home")
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x", encoding="utf-8")
    cfg = _scoped_cfg(blocker)
    out = default_agent_workspace_dir(paths, "F46T8Y", cfg=cfg)
    assert out == paths.agent_workspace("F46T8Y")
    assert out.is_dir()


def test_neutralize_unwritable_local_root(tmp_path: Path) -> None:
    from octop.infra.agents.workspace.dir import neutralize_unwritable_local_root

    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x", encoding="utf-8")
    cfg = _scoped_cfg(blocker, workspace_dir="/.octop/workspaces/F46T8Y")
    out = neutralize_unwritable_local_root(cfg)
    assert out["backend"]["root_dir"] == "/"
    writable = tmp_path / "home"
    writable.mkdir()
    keep = neutralize_unwritable_local_root(_scoped_cfg(writable))
    assert keep["backend"]["root_dir"] == str(writable)
