"""Path-addressed control-plane file rows."""

from __future__ import annotations

from pathlib import Path

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.control_files import ControlFileRepo, safe_relative_path
from octop.infra.db.repos.profile_avatars import ProfileAvatarRepo
from octop.infra.users.profile_avatar import KIND_USER

_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0"
    b"\x00\x00\x00\x03\x00\x01\x00\x05\xfe\xd4\xef\x00\x00\x00\x00IEND\xaeB`\x82"
)


def test_safe_relative_path_rejects_escape() -> None:
    assert safe_relative_path("plugin.yaml") == "plugin.yaml"
    assert safe_relative_path("nested/plugin.yaml") == "nested/plugin.yaml"
    assert safe_relative_path(r"nested\plugin.yaml") == "nested/plugin.yaml"
    assert safe_relative_path("../plugin.yaml") is None
    assert safe_relative_path("/etc/passwd") is None
    assert safe_relative_path("nested/../../plugin.yaml") is None


def test_repos_roundtrip_bytes(tmp_path: Path) -> None:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    avatars = ProfileAvatarRepo(db)
    avatars.put(KIND_USER, "1", _PNG, "image/png")
    row = avatars.get(KIND_USER, "1")
    assert row is not None and row.content == _PNG

    files = ControlFileRepo(db)
    files.replace_tree(
        ControlFileRepo.PLUGIN,
        "demo",
        [("plugin.yaml", b"id: demo\n"), ("../escape", b"no")],
    )
    assert files.get(ControlFileRepo.PLUGIN, "demo", "plugin.yaml") == b"id: demo\n"
    assert files.list_files(ControlFileRepo.PLUGIN, "demo") == [("plugin.yaml", b"id: demo\n")]
    files.delete_owner(ControlFileRepo.PLUGIN, "demo")
    assert files.owners(ControlFileRepo.PLUGIN) == []
