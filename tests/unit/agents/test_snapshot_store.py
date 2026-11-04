"""Published-expert snapshots adopted from disk once."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from octop.infra.agents.experts.snapshot_store import (
    adopt_local_snapshots,
    materialize_snapshot,
    published_skill_count,
)
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.control_files import ControlFileRepo
from octop.infra.db.repos.settings import SettingsRepo
from octop.infra.utils.paths import PathLayout

posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX symlinks")


def _open(tmp_path: Path) -> tuple[ControlFileRepo, SettingsRepo, Path]:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    root = PathLayout(tmp_path).published_experts_dir
    return ControlFileRepo(db), SettingsRepo(db), root


def test_snapshot_roundtrip_keeps_nested_directories(tmp_path: Path) -> None:
    repo, settings, root = _open(tmp_path)
    nested = root / "exp1" / "skills" / "weather"
    nested.mkdir(parents=True)
    (root / "exp1" / "manifest.json").write_text("{}", encoding="utf-8")
    (nested / "SKILL.md").write_text("# weather\n", encoding="utf-8")

    adopt_local_snapshots(repo, settings, root)
    dest = tmp_path / "out"
    assert materialize_snapshot(repo, "exp1", dest) is True
    assert (dest / "manifest.json").read_text(encoding="utf-8") == "{}"
    assert (dest / "skills" / "weather" / "SKILL.md").read_text(encoding="utf-8") == "# weather\n"
    assert published_skill_count(repo, "exp1") == 1


def test_adopt_copies_missing_snapshot_and_ignores_later_dirs(tmp_path: Path) -> None:
    repo, settings, root = _open(tmp_path)
    expert = root / "exp1"
    expert.mkdir(parents=True)
    (expert / "manifest.json").write_text('{"id":"exp1"}', encoding="utf-8")

    adopt_local_snapshots(repo, settings, root)

    assert repo.get(ControlFileRepo.PUBLISHED_EXPERT, "exp1", "manifest.json") == b'{"id":"exp1"}'

    later = root / "exp2"
    later.mkdir()
    (later / "manifest.json").write_text('{"id":"exp2"}', encoding="utf-8")
    adopt_local_snapshots(repo, settings, root)
    assert repo.get(ControlFileRepo.PUBLISHED_EXPERT, "exp2", "manifest.json") is None


def test_adopt_leaves_an_existing_snapshot_unchanged(tmp_path: Path) -> None:
    repo, settings, root = _open(tmp_path)
    repo.replace_tree(
        ControlFileRepo.PUBLISHED_EXPERT,
        "exp1",
        [("manifest.json", b'{"id":"stored"}')],
    )
    expert = root / "exp1"
    expert.mkdir(parents=True)
    (expert / "manifest.json").write_text('{"id":"disk"}', encoding="utf-8")

    adopt_local_snapshots(repo, settings, root)

    assert repo.get(ControlFileRepo.PUBLISHED_EXPERT, "exp1", "manifest.json") == b'{"id":"stored"}'


@posix_only
def test_adopt_skips_symlink_directory(tmp_path: Path) -> None:
    repo, settings, root = _open(tmp_path)
    real = tmp_path / "real-expert"
    real.mkdir()
    (real / "manifest.json").write_text('{"id":"real"}', encoding="utf-8")
    root.mkdir(parents=True)
    (root / "linked").symlink_to(real, target_is_directory=True)

    adopt_local_snapshots(repo, settings, root)

    assert repo.has_owner(ControlFileRepo.PUBLISHED_EXPERT, "linked") is False
