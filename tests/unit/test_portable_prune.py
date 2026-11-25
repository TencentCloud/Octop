"""The green/desktop site-packages prune drops packaged bloat and nothing else."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_STATIC_MISS = """        if content:
            return content
        else:
            raise UnknownApiNameOrVersion(
                "name: %s  version: %s" % (serviceName, version)
            )
"""


def _load_prune():
    path = Path(__file__).resolve().parents[2] / "desktop" / "portable" / "prune_packages.py"
    spec = importlib.util.spec_from_file_location("prune_packages", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_prune_removes_bloat_and_keeps_product_files(tmp_path: Path) -> None:
    packages = tmp_path / "packages"
    (packages / "googleapiclient" / "discovery_cache" / "documents").mkdir(parents=True)
    (packages / "googleapiclient" / "discovery_cache" / "documents" / "drive.v3.json").write_text(
        "{}", encoding="utf-8"
    )
    (packages / "googleapiclient" / "discovery_cache" / "__init__.py").write_text(
        "x = 1\n", encoding="utf-8"
    )
    (packages / "googleapiclient" / "discovery.py").write_text(
        "header\n" + _STATIC_MISS + "tail\n", encoding="utf-8"
    )
    (packages / "PyObjCTest" / "case.py").parent.mkdir(parents=True)
    (packages / "PyObjCTest" / "case.py").write_text("x = 1\n", encoding="utf-8")
    dwarf = packages / "objc" / "_objc.so.dSYM" / "Contents"
    dwarf.mkdir(parents=True)
    (dwarf / "Info.plist").write_text("d", encoding="utf-8")
    (packages / "regex" / "tests" / "test_basic.py").parent.mkdir(parents=True)
    (packages / "regex" / "tests" / "test_basic.py").write_text("x = 1\n", encoding="utf-8")
    (packages / "sqlalchemy" / "testing" / "suite.py").parent.mkdir(parents=True)
    (packages / "sqlalchemy" / "testing" / "suite.py").write_text("x = 1\n", encoding="utf-8")
    (packages / "numpy" / "testing" / "__init__.py").parent.mkdir(parents=True)
    (packages / "numpy" / "testing" / "__init__.py").write_text("x = 1\n", encoding="utf-8")
    (packages / "numpy" / "random" / "tests" / "test_random.py").parent.mkdir(parents=True)
    (packages / "numpy" / "random" / "tests" / "test_random.py").write_text(
        "x = 1\n", encoding="utf-8"
    )
    subagent = packages / "octop" / "infra" / "agents" / "subagents" / "library" / "zh" / "testing"
    subagent.mkdir(parents=True)
    (subagent / "SKILL.md").write_text("keep\n", encoding="utf-8")
    (packages / "playwright" / "driver" / "node").parent.mkdir(parents=True)
    (packages / "playwright" / "driver" / "node").write_text("node", encoding="utf-8")

    removed = _load_prune().prune_packages(packages)

    assert "googleapiclient/discovery_cache/documents" in removed
    assert not (packages / "googleapiclient" / "discovery_cache" / "documents").exists()
    assert (packages / "googleapiclient" / "discovery_cache" / "__init__.py").is_file()
    discovery = (packages / "googleapiclient" / "discovery.py").read_text(encoding="utf-8")
    assert "UnknownApiNameOrVersion" not in discovery
    assert "falls through to the network" in discovery
    assert not (packages / "PyObjCTest").exists()
    assert not (packages / "objc" / "_objc.so.dSYM").exists()
    assert not (packages / "regex" / "tests").exists()
    assert not (packages / "sqlalchemy" / "testing").exists()
    assert not (packages / "numpy" / "random" / "tests").exists()
    assert (packages / "numpy" / "testing" / "__init__.py").is_file()
    assert (subagent / "SKILL.md").read_text(encoding="utf-8") == "keep\n"
    assert (packages / "playwright" / "driver" / "node").read_text(encoding="utf-8") == "node"


def test_prune_is_idempotent(tmp_path: Path) -> None:
    packages = tmp_path / "packages"
    packages.mkdir()
    (packages / "googleapiclient").mkdir()
    (packages / "googleapiclient" / "discovery.py").write_text(_STATIC_MISS, encoding="utf-8")
    prune = _load_prune()
    prune.prune_packages(packages)
    prune.prune_packages(packages)
    text = (packages / "googleapiclient" / "discovery.py").read_text(encoding="utf-8")
    assert text.count("falls through to the network") == 1


def test_prune_rejects_a_changed_discovery_client(tmp_path: Path) -> None:
    packages = tmp_path / "packages" / "googleapiclient"
    packages.mkdir(parents=True)
    (packages / "discovery.py").write_text("unrecognized\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="static-discovery miss"):
        _load_prune().prune_packages(packages.parent)
