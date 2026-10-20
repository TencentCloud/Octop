"""Live Postgres probe + workspace tests (172.19.0.22 sample instance)."""

from __future__ import annotations

import contextlib
import os
import uuid
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg")

LIVE_HOST = os.environ.get("OCTOP_LIVE_PG_HOST", "172.19.0.22")
LIVE_SPEC: dict[str, object] = {
    "type": "postgres",
    "host": LIVE_HOST,
    "port": int(os.environ.get("OCTOP_LIVE_PG_PORT", "5432")),
    "database": os.environ.get("OCTOP_LIVE_PG_DB", "postgres"),
    "user": os.environ.get("OCTOP_LIVE_PG_USER", "postgres"),
    "password": os.environ.get("OCTOP_LIVE_PG_PASSWORD", "postgres"),
    "schema": "public",
    "table": "octop_harness_live_files",
    "connection_timeout": 5,
}


def _live_available() -> bool:
    try:
        with psycopg.connect(
            f"host={LIVE_SPEC['host']} port={LIVE_SPEC['port']} "
            f"dbname={LIVE_SPEC['database']} user={LIVE_SPEC['user']} "
            f"password={LIVE_SPEC['password']} connect_timeout=3",
        ) as conn:
            conn.execute("SELECT 1")
    except Exception:
        return False
    return True


pytestmark = pytest.mark.skipif(not _live_available(), reason="live Postgres 172.19.0.22 unreachable")


@pytest.fixture
def live_spec() -> dict[str, object]:
    return dict(LIVE_SPEC)


def test_live_postgres_probe_roundtrip(live_spec: dict[str, object]) -> None:
    from octop_harness.backends.probe import probe_backend

    result = probe_backend(live_spec)
    assert result.get("ok") is True, result
    assert result.get("message_key") == "probe_roundtrip_ok"


def test_live_postgres_workspace_roundtrip(live_spec: dict[str, object], tmp_path: Path) -> None:
    from octop_harness.backends import resolve_backend
    from octop_harness.backends.postgres import PostgresBackend
    from octop_harness.backends.workspace import BackendWorkspace, remote_workspace_virtual_root

    backend = resolve_backend(live_spec)
    assert isinstance(backend, PostgresBackend)
    token = uuid.uuid4().hex
    workspace = BackendWorkspace(backend, tmp_path)
    virt = remote_workspace_virtual_root(tmp_path)
    try:
        for leftover in (virt, "/SOUL.md", "/skills"):
            with contextlib.suppress(FileNotFoundError):
                backend.delete_path(leftover)
        workspace.write_text("SOUL.md", f"hello-{token}", force=True)
        assert workspace.read_text("SOUL.md") == f"hello-{token}"
        assert workspace.exists("SOUL.md") is True

        workspace.mkdir("skills")
        workspace.write_text("skills/demo/SKILL.md", "skill-body", force=True)
        assert workspace.read_text("skills/demo/SKILL.md") == "skill-body"

        listing = workspace.list_dir(".")
        names = {str(entry.get("path", "")).rstrip("/").split("/")[-1] for entry in listing or []}
        assert "SOUL.md" in names
        assert "skills" in names

        root = backend.ls("/")
        root_paths = {item["path"] for item in root.entries or []}
        assert "/.octop" in root_paths

        globbed = backend.glob("**/*.md", path=virt)
        assert globbed.error is None
        glob_paths = {item["path"] for item in globbed.matches or []}
        assert f"{virt}/SOUL.md" in glob_paths
        assert f"{virt}/skills/demo/SKILL.md" in glob_paths

        grepped = backend.grep(f"hello-{token}", path=virt)
        assert grepped.error is None
        assert any(match.get("path") == f"{virt}/SOUL.md" for match in grepped.matches or [])

        workspace.write_text("SOUL.md", f"hello-{token}-edited", force=True)
        assert workspace.read_text("SOUL.md") == f"hello-{token}-edited"

        workspace.delete("skills")
        assert workspace.read_text("skills/demo/SKILL.md") is None
        workspace.delete("SOUL.md")
        assert workspace.read_text("SOUL.md") is None
    finally:
        backend.close()
