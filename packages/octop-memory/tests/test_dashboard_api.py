"""Unit tests for the dashboard FastAPI endpoints.

Uses an in-memory SQLite database to build test data, verifying the
correctness of each API endpoint as well as namespace isolation
(openclaw__default_ vs agent_zywztd_).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

pytest.importorskip("fastapi", reason="dashboard extra not installed")

from fastapi.testclient import TestClient

from octop_memory.adapters.dashboard.server import _norm_ns, app

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _create_test_db(path: str, namespaces: list[str]) -> None:
    """Create a test SQLite database at the given path, creating tables and inserting test data for each namespace."""
    conn = sqlite3.connect(path)
    for ns_raw in namespaces:
        ns = _norm_ns(ns_raw)
        conn.executescript(f"""
            CREATE TABLE IF NOT EXISTS {ns}_raw_events (
                id TEXT PRIMARY KEY,
                host TEXT NOT NULL,
                session_id TEXT,
                thread_id TEXT,
                "user" TEXT,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                content TEXT NOT NULL,
                payload TEXT NOT NULL DEFAULT '{{}}'
            );
            CREATE TABLE IF NOT EXISTS {ns}_candidates (
                id TEXT PRIMARY KEY,
                raw_event_ids TEXT NOT NULL DEFAULT '[]',
                candidate_type TEXT NOT NULL,
                status TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                assertion TEXT NOT NULL,
                verbatim_quote TEXT NOT NULL DEFAULT '',
                quote_event_id TEXT NOT NULL DEFAULT '',
                subject_name TEXT NOT NULL DEFAULT '',
                subject_entity_type TEXT NOT NULL DEFAULT 'User',
                target_entity_id TEXT,
                confidence TEXT NOT NULL DEFAULT 'medium',
                importance TEXT NOT NULL DEFAULT 'medium',
                recommended_action TEXT NOT NULL DEFAULT '',
                promotion_reason TEXT NOT NULL DEFAULT '',
                extractor_version TEXT NOT NULL DEFAULT '1.0',
                created_at TEXT NOT NULL,
                decided_at TEXT,
                decided_by TEXT,
                session_id TEXT,
                payload TEXT NOT NULL DEFAULT '{{}}'
            );
            CREATE TABLE IF NOT EXISTS {ns}_atoms (
                id TEXT PRIMARY KEY,
                entity_id TEXT NOT NULL,
                candidate_id TEXT NOT NULL,
                raw_event_ids TEXT NOT NULL DEFAULT '[]',
                assertion TEXT NOT NULL,
                verbatim_quote TEXT NOT NULL DEFAULT '',
                quote_event_id TEXT NOT NULL DEFAULT '',
                search_terms TEXT NOT NULL DEFAULT '[]',
                occurred_at TEXT NOT NULL,
                confidence TEXT NOT NULL DEFAULT 'medium',
                importance TEXT NOT NULL DEFAULT 'medium',
                superseded_by TEXT,
                deprecated_at TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS {ns}_journal (
                id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                action TEXT NOT NULL,
                actor TEXT NOT NULL,
                target_entity_id TEXT,
                target_atom_id TEXT,
                target_candidate_id TEXT,
                before TEXT,
                after TEXT,
                note TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS {ns}_episodes (
                id TEXT PRIMARY KEY,
                raw_event_ids TEXT NOT NULL DEFAULT '[]',
                occurred_at TEXT NOT NULL,
                summary TEXT NOT NULL,
                verbatim_quote TEXT NOT NULL DEFAULT '',
                quote_event_id TEXT NOT NULL DEFAULT '',
                emotion TEXT NOT NULL DEFAULT 'neutral',
                intensity INTEGER NOT NULL DEFAULT 1,
                people TEXT NOT NULL DEFAULT '[]',
                topics TEXT NOT NULL DEFAULT '[]',
                extractor_version TEXT NOT NULL DEFAULT '1.0',
                session_id TEXT,
                digest_ids TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL
            );
        """)

        # Insert test data
        conn.execute(
            f"INSERT INTO {ns}_raw_events VALUES (?,?,?,?,?,?,?,?,?)",
            (
                f"{ns}_evt1",
                "openclaw",
                f"{ns}_sess1",
                None,
                None,
                "2026-07-01T10:00:00",
                "user_message",
                f"[{ns_raw}] 用户说：我喜欢 TypeScript",
                "{}",
            ),
        )
        conn.execute(
            f"INSERT INTO {ns}_candidates VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                f"{ns}_cand1",
                "[]",
                "Fact",
                "pending",
                "TypeScript 偏好",
                f"[{ns_raw}] 用户偏好 TypeScript",
                "",
                "",
                "User",
                "User",
                None,
                "high",
                "high",
                "",
                "",
                "1.0",
                "2026-07-01T10:01:00",
                None,
                None,
                f"{ns}_sess1",
                "{}",
            ),
        )
        conn.execute(
            f"INSERT INTO {ns}_atoms VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                f"{ns}_atom1",
                f"{ns}_entity1",
                f"{ns}_cand1",
                "[]",
                f"[{ns_raw}] 用户偏好 TypeScript",
                "",
                "",
                '["TypeScript","偏好"]',
                "2026-07-01T10:01:00",
                "high",
                "high",
                None,
                None,
                "2026-07-01T10:01:00",
            ),
        )
        conn.execute(
            f"INSERT INTO {ns}_journal VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                f"{ns}_jrn1",
                "2026-07-01T10:02:00",
                "promote",
                "auto",
                None,
                f"{ns}_atom1",
                f"{ns}_cand1",
                None,
                None,
                f"[{ns_raw}] 自动晋升",
            ),
        )
        conn.execute(
            f"INSERT INTO {ns}_episodes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                f"{ns}_ep1",
                "[]",
                "2026-07-01T10:00:00",
                f"[{ns_raw}] 用户讨论了 TypeScript 偏好",
                "",
                "",
                "positive",
                3,
                "[]",
                '["TypeScript"]',
                "1.0",
                f"{ns}_sess1",
                "[]",
                "2026-07-01T10:01:00",
            ),
        )
    conn.commit()
    conn.close()


@pytest.fixture
def db_file(tmp_path: Path) -> str:
    """Create a test database containing two namespaces, return its path."""
    db_path = str(tmp_path / "test_memory.sqlite")
    _create_test_db(db_path, ["openclaw__default", "agent_zywztd"])
    return db_path


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# Tests: /api/connect
# ---------------------------------------------------------------------------


class TestConnect:
    def test_connect_success(self, client: TestClient, db_file: str) -> None:
        res = client.get("/api/connect", params={"db_path": db_file, "namespace": "openclaw__default"})
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data["tables"]["raw_events"] is True
        assert data["tables"]["atoms"] is True

    def test_connect_db_not_found(self, client: TestClient) -> None:
        res = client.get(
            "/api/connect",
            params={
                "db_path": "/nonexistent/path/memory.sqlite",
                "namespace": "test",
            },
        )
        assert res.status_code == 404
        # The server returns a user-facing Chinese message; assert on the
        # stable path fragment rather than the wording.
        assert "/nonexistent/path/memory.sqlite" in res.json()["detail"]


# ---------------------------------------------------------------------------
# Tests: /api/stats
# ---------------------------------------------------------------------------


class TestStats:
    def test_stats_openclaw(self, client: TestClient, db_file: str) -> None:
        res = client.get("/api/stats", params={"db_path": db_file, "namespace": "openclaw__default"})
        assert res.status_code == 200
        data = res.json()
        assert data["raw_events"] == 1
        assert data["atoms_active"] == 1
        assert data["atoms_deprecated"] == 0
        assert data["candidates_pending"] == 1
        assert data["episodes"] == 1
        assert data["last_capture"] is not None

    def test_stats_hermes(self, client: TestClient, db_file: str) -> None:
        """Hermes namespace stats should be completely independent from OpenClaw's."""
        res = client.get("/api/stats", params={"db_path": db_file, "namespace": "agent_zywztd"})
        assert res.status_code == 200
        data = res.json()
        # Each namespace has 1 row of data, no cross-contamination.
        assert data["raw_events"] == 1
        assert data["atoms_active"] == 1


# ---------------------------------------------------------------------------
# Tests: namespace isolation (core verification)
# ---------------------------------------------------------------------------


class TestNamespaceIsolation:
    def test_raw_events_isolated(self, client: TestClient, db_file: str) -> None:
        """openclaw__default's raw_events should not show up in agent_zywztd's query results."""
        res_oc = client.get("/api/raw_events", params={"db_path": db_file, "namespace": "openclaw__default"})
        res_hz = client.get("/api/raw_events", params={"db_path": db_file, "namespace": "agent_zywztd"})
        assert res_oc.status_code == 200
        assert res_hz.status_code == 200

        oc_ids = {item["id"] for item in res_oc.json()["items"]}
        hz_ids = {item["id"] for item in res_hz.json()["items"]}

        # The two namespaces' data sets should not overlap.
        assert oc_ids.isdisjoint(hz_ids), f"namespace data leak: {oc_ids & hz_ids}"
        # Each namespace should only contain its own data.
        assert any("openclaw__default" in i for i in oc_ids)
        assert any("agent_zywztd" in i for i in hz_ids)

    def test_atoms_isolated(self, client: TestClient, db_file: str) -> None:
        """Atoms queries should be strictly isolated by namespace."""
        res_oc = client.get("/api/atoms", params={"db_path": db_file, "namespace": "openclaw__default"})
        res_hz = client.get("/api/atoms", params={"db_path": db_file, "namespace": "agent_zywztd"})
        oc_ids = {item["id"] for item in res_oc.json()["items"]}
        hz_ids = {item["id"] for item in res_hz.json()["items"]}
        assert oc_ids.isdisjoint(hz_ids)

    def test_candidates_isolated(self, client: TestClient, db_file: str) -> None:
        res_oc = client.get("/api/candidates", params={"db_path": db_file, "namespace": "openclaw__default"})
        res_hz = client.get("/api/candidates", params={"db_path": db_file, "namespace": "agent_zywztd"})
        oc_ids = {item["id"] for item in res_oc.json()["items"]}
        hz_ids = {item["id"] for item in res_hz.json()["items"]}
        assert oc_ids.isdisjoint(hz_ids)


# ---------------------------------------------------------------------------
# Tests: /api/raw_events, /api/atoms, /api/journal, /api/episodes
# ---------------------------------------------------------------------------


class TestDataEndpoints:
    def test_raw_events_pagination(self, client: TestClient, db_file: str) -> None:
        res = client.get(
            "/api/raw_events",
            params={
                "db_path": db_file,
                "namespace": "openclaw__default",
                "page": 1,
                "page_size": 10,
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert "items" in data
        assert "total" in data
        assert data["total"] >= 1

    def test_atoms_exclude_deprecated_by_default(self, client: TestClient, db_file: str) -> None:
        res = client.get(
            "/api/atoms",
            params={
                "db_path": db_file,
                "namespace": "openclaw__default",
            },
        )
        assert res.status_code == 200
        items = res.json()["items"]
        # Deprecated atoms are not returned by default.
        assert all(item["deprecated_at"] is None for item in items)

    def test_atoms_include_deprecated(self, client: TestClient, db_file: str) -> None:
        res = client.get(
            "/api/atoms",
            params={
                "db_path": db_file,
                "namespace": "openclaw__default",
                "include_deprecated": "true",
            },
        )
        assert res.status_code == 200

    def test_atom_detail(self, client: TestClient, db_file: str) -> None:
        ns = _norm_ns("openclaw__default")
        atom_id = f"{ns}_atom1"
        res = client.get(
            f"/api/atoms/{atom_id}",
            params={
                "db_path": db_file,
                "namespace": "openclaw__default",
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["id"] == atom_id
        assert "candidate" in data  # associated candidate is already inlined

    def test_journal_list(self, client: TestClient, db_file: str) -> None:
        res = client.get(
            "/api/journal",
            params={
                "db_path": db_file,
                "namespace": "openclaw__default",
            },
        )
        assert res.status_code == 200
        assert res.json()["total"] >= 1

    def test_episodes_list(self, client: TestClient, db_file: str) -> None:
        res = client.get(
            "/api/episodes",
            params={
                "db_path": db_file,
                "namespace": "openclaw__default",
            },
        )
        assert res.status_code == 200
        assert res.json()["total"] >= 1


# ---------------------------------------------------------------------------
# Tests: /api/namespaces
# ---------------------------------------------------------------------------


class TestNamespaces:
    def test_list_namespaces(self, client: TestClient, db_file: str) -> None:
        res = client.get("/api/namespaces", params={"db_path": db_file})
        assert res.status_code == 200
        ns_list = res.json()["namespaces"]
        # Both namespaces should be detected.
        assert "openclaw__default" in ns_list
        assert "agent_zywztd" in ns_list

    def test_namespaces_db_not_found(self, client: TestClient) -> None:
        res = client.get("/api/namespaces", params={"db_path": "/no/such/file.sqlite"})
        assert res.status_code == 404


# ---------------------------------------------------------------------------
# Tests: /api/defaults
# ---------------------------------------------------------------------------


class TestDefaults:
    def test_defaults_empty_by_default(self, client: TestClient) -> None:
        """Returns empty strings when no defaults have been injected."""
        # Clear any leftover state.
        app.state.default_db_path = ""
        app.state.default_namespace = ""
        res = client.get("/api/defaults")
        assert res.status_code == 200
        data = res.json()
        assert data["db_path"] == ""
        assert data["namespace"] == ""

    def test_defaults_injected(self, client: TestClient, db_file: str) -> None:
        """After the CLI injects defaults, /api/defaults should return them."""
        app.state.default_db_path = db_file
        app.state.default_namespace = "openclaw__default"
        res = client.get("/api/defaults")
        assert res.status_code == 200
        data = res.json()
        assert data["db_path"] == db_file
        assert data["namespace"] == "openclaw__default"
        # Cleanup.
        app.state.default_db_path = ""
        app.state.default_namespace = ""
