from __future__ import annotations

from types import SimpleNamespace

import pytest

from octop.infra.backup import pg_dump
from octop.infra.errors import ErrorCode, OctopError


def test_require_tool_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pg_dump.shutil, "which", lambda _name: None)
    with pytest.raises(OctopError, match="pg_dump not found"):
        pg_dump._require_tool("pg_dump")


def test_dump_postgres_can_exclude_chat_table_data(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    called: list[str] = []
    monkeypatch.setattr(pg_dump, "_require_tool", lambda _name: "pg_dump")

    def fake_run(command, **_kwargs):
        called.extend(command)
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(pg_dump.subprocess, "run", fake_run)
    pg_dump.dump_postgres(
        "postgresql://example",
        tmp_path / "backup.dump",
        exclude_table_data=("sessions", "threads"),
    )

    assert called.count("--exclude-table-data") == 2
    assert "sessions" in called
    assert "threads" in called


def test_missing_tool_raises_backup_tool_missing(monkeypatch):
    """A missing pg_dump is a client environment problem -> 400, not 500 (#1301)."""
    monkeypatch.setattr(pg_dump.shutil, "which", lambda name: None)
    with pytest.raises(OctopError) as excinfo:
        pg_dump._require_tool("pg_dump")
    assert excinfo.value.code == ErrorCode.BACKUP_TOOL_MISSING
    assert "postgresql-client" in excinfo.value.message


def test_missing_tool_maps_to_400():
    from octop.infra.errors import OctopError

    assert OctopError(ErrorCode.BACKUP_TOOL_MISSING, "missing").status == 400


def test_present_tool_returns_path(monkeypatch):
    monkeypatch.setattr(pg_dump.shutil, "which", lambda name: f"/usr/bin/{name}")
    assert pg_dump._require_tool("pg_restore") == "/usr/bin/pg_restore"


_MISMATCH_STDERR = (
    "pg_dump: error: server version: 18.4; pg_dump version: 17.5\n"
    "pg_dump: aborting because of server version mismatch"
)


def _run_result(returncode: int, stderr: str = "") -> SimpleNamespace:
    return SimpleNamespace(returncode=returncode, stderr=stderr, stdout="")


def test_dump_version_mismatch_raises_backup_tool_mismatch(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Client tools older than the server abort with exit 1 -> 400 with guidance (#1301)."""
    monkeypatch.setattr(pg_dump, "_require_tool", lambda _name: "pg_dump")
    monkeypatch.setattr(
        pg_dump.subprocess, "run", lambda *_a, **_k: _run_result(1, _MISMATCH_STDERR)
    )
    with pytest.raises(OctopError) as excinfo:
        pg_dump.dump_postgres("postgresql://example", tmp_path / "backup.dump")
    assert excinfo.value.code == ErrorCode.BACKUP_TOOL_MISMATCH
    assert "postgresql-client-18" in excinfo.value.message


def test_dump_generic_failure_stays_internal_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setattr(pg_dump, "_require_tool", lambda _name: "pg_dump")
    monkeypatch.setattr(
        pg_dump.subprocess,
        "run",
        lambda *_a, **_k: _run_result(1, "pg_dump: error: connection refused"),
    )
    with pytest.raises(OctopError) as excinfo:
        pg_dump.dump_postgres("postgresql://example", tmp_path / "backup.dump")
    assert excinfo.value.code == ErrorCode.INTERNAL_ERROR
    assert "connection refused" in excinfo.value.message


def test_restore_version_mismatch_not_swallowed_by_warning_threshold(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """The mismatch abort exits 1, which the >=2 warning rule would otherwise tolerate."""
    monkeypatch.setattr(pg_dump, "_require_tool", lambda _name: "pg_restore")
    mismatch = _MISMATCH_STDERR.replace("pg_dump", "pg_restore")
    monkeypatch.setattr(pg_dump.subprocess, "run", lambda *_a, **_k: _run_result(1, mismatch))
    with pytest.raises(OctopError) as excinfo:
        pg_dump.restore_postgres("postgresql://example", tmp_path / "backup.dump")
    assert excinfo.value.code == ErrorCode.BACKUP_TOOL_MISMATCH


def test_restore_exit_one_warnings_still_tolerated(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setattr(pg_dump, "_require_tool", lambda _name: "pg_restore")
    monkeypatch.setattr(
        pg_dump.subprocess,
        "run",
        lambda *_a, **_k: _run_result(1, "pg_restore: warning: errors ignored on purpose: Restore"),
    )
    pg_dump.restore_postgres("postgresql://example", tmp_path / "backup.dump")


def test_backup_tool_mismatch_maps_to_400():
    assert OctopError(ErrorCode.BACKUP_TOOL_MISMATCH, "mismatch").status == 400
