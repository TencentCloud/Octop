"""Windows subtree roots: reject ambiguous input before realpath."""

from __future__ import annotations

import copy
import os

import pytest

from octop.infra.agents.experts.default_agent import default_home_local_backend
from octop.infra.agents.workspace.windows_root import (
    stamp_new_windows_subtree,
    windows_picker_defaults,
    windows_root_input_ambiguous,
)


@pytest.mark.parametrize(
    "raw",
    [
        "/",
        "\\",
        "/data/a.txt",
        "\\data\\a.txt",
        "D:",
        "D:work",
        "d:work",
        "work",
        "./work",
        "../work",
        ".",
        "..",
        ".\\work",
        "..\\work",
    ],
)
def test_ambiguous_windows_inputs(raw: str) -> None:
    assert windows_root_input_ambiguous(raw) is True


@pytest.mark.parametrize(
    "raw",
    ["C:/work", "C:\\work\\data", "D:/", "d:\\", "\\\\server\\share\\data"],
)
def test_fully_qualified_windows_inputs(raw: str) -> None:
    assert windows_root_input_ambiguous(raw) is False


def test_stamp_fills_omitted_root_and_keeps_explicit_root() -> None:
    def keep(path: str) -> str:
        return path.replace("\\", "/")

    omitted: dict = {"backend": {"type": "local_shell", "virtual_mode": True}}
    stamp_new_windows_subtree(omitted, home="C:/Users/bob", policy_root="D:/data", resolve=keep)
    assert omitted["root_semantics"] == "subtree"
    assert omitted["backend"]["root_dir"] == "D:/data"

    home_only: dict = {}
    stamp_new_windows_subtree(home_only, home="C:/Users/bob", resolve=keep)
    assert home_only["backend"]["root_dir"] == "C:/Users/bob"
    assert home_only["root_semantics"] == "subtree"

    explicit: dict = {"backend": {"type": "local_shell", "root_dir": "C:/work"}}
    stamp_new_windows_subtree(explicit, home="C:/Users/bob", policy_root="D:/data", resolve=keep)
    assert explicit["backend"]["root_dir"] == "C:/work"


@pytest.mark.parametrize(
    "raw",
    ["/", "/data/a.txt", "D:", "D:work", "\\data", "work", "./work", "../work", ".", ".."],
)
def test_stamp_rejects_ambiguous_root_before_resolve(raw: str) -> None:
    seen: list[str] = []

    def explode(path: str) -> str:
        seen.append(path)
        return path

    cfg = {"backend": {"type": "local_shell", "root_dir": raw}}
    with pytest.raises(ValueError, match="fully qualified"):
        stamp_new_windows_subtree(cfg, home="C:/Users/bob", resolve=explode)
    assert seen == []


def test_stamp_normalizes_a_volume_root() -> None:
    cfg = {"backend": {"type": "local_shell", "root_dir": "d:\\"}}
    stamp_new_windows_subtree(cfg, home="C:/Users/bob", resolve=lambda path: path)
    assert cfg["backend"]["root_dir"] == "D:/"
    assert cfg["backend"]["virtual_mode"] is True


def test_stamp_normalizes_local_backend_strings() -> None:
    shell: dict = {"backend": "local_shell"}
    stamp_new_windows_subtree(shell, home="C:/Users/bob", resolve=lambda path: path)
    assert shell["root_semantics"] == "subtree"
    assert shell["backend"] == {
        "type": "local_shell",
        "root_dir": "C:/Users/bob",
        "virtual_mode": True,
    }

    filesystem: dict = {"backend": "filesystem"}
    stamp_new_windows_subtree(filesystem, home="D:/data", resolve=lambda path: path)
    assert filesystem["backend"]["type"] == "filesystem"
    assert filesystem["backend"]["root_dir"] == "D:/data"
    assert filesystem["backend"]["virtual_mode"] is True


def test_stamp_rejects_virtual_mode_off_without_resolving() -> None:
    seen: list[str] = []
    cfg = {
        "backend": {
            "type": "local_shell",
            "root_dir": "C:/work",
            "virtual_mode": False,
        }
    }
    with pytest.raises(ValueError, match="virtual_mode"):
        stamp_new_windows_subtree(
            cfg,
            home="C:/Users/bob",
            resolve=lambda path: seen.append(path) or path,
        )
    assert seen == []
    assert "root_semantics" not in cfg
    assert cfg["backend"]["virtual_mode"] is False


@pytest.mark.parametrize(
    "backend",
    [
        "docker",
        {"type": "docker", "image": "octop"},
        {"type": "composite", "default": {"type": "filesystem", "root_dir": "/data"}},
        {"type": "s3", "bucket": "exports"},
        "opensandbox",
    ],
)
def test_stamp_leaves_supported_non_local_backends_alone(backend: object) -> None:
    seen: list[str] = []
    expected = copy.deepcopy(backend)
    cfg = {"backend": backend}
    stamp_new_windows_subtree(
        cfg,
        home="C:/Users/bob",
        resolve=lambda path: seen.append(path) or path,
    )
    assert cfg["backend"] == expected
    assert "root_semantics" not in cfg
    assert seen == []


@pytest.mark.parametrize(
    "backend",
    ["nope", "", {}, {"type": ""}, {"type": "not-a-backend"}, object(), ["local_shell"]],
)
def test_stamp_rejects_uninterpretable_backend(backend: object) -> None:
    cfg = {"backend": backend}
    with pytest.raises(ValueError, match="unsupported backend"):
        stamp_new_windows_subtree(cfg, home="C:/Users/bob", resolve=lambda path: path)
    assert "root_semantics" not in cfg


def test_picker_defaults_skip_a_home_volume_that_is_not_ready() -> None:
    payload = windows_picker_defaults(
        home="E:/Users/bob",
        drives=["C:\\", "D:\\"],
        legacy_tree_root="C:/",
    )
    assert payload["default_root_dir"] == "C:/"
    assert payload["tree_roots"] == ["C:/", "D:/"]


def test_picker_defaults_keep_legacy_tree_root() -> None:
    payload = windows_picker_defaults(
        home="C:/Users/bob",
        drives=["C:\\", "d:\\", "C:/"],
        legacy_tree_root="C:/",
    )
    assert payload == {
        "default_root_dir": "C:/",
        "tree_root": "C:/",
        "tree_roots": ["C:/", "D:/"],
    }


def test_windows_default_backend_preselects_process_home(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setattr(
        "octop.infra.agents.experts.default_agent.host_home_dir",
        lambda: "home",
    )
    monkeypatch.setattr(
        "octop.infra.agents.experts.default_agent.host_path_text",
        lambda _path: "C:/Users/bob",
    )
    backend = default_home_local_backend()
    assert backend["root_dir"] == "C:/Users/bob"
    assert backend["virtual_mode"] is True
    assert default_home_local_backend(root_dir="D:/work")["root_dir"] == "D:/work"
