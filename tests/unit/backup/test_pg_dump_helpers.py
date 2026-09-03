from __future__ import annotations

from types import SimpleNamespace

import pytest

from octop.infra.backup import pg_dump
from octop.infra.errors import OctopError


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
