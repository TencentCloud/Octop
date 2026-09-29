from __future__ import annotations

import re
from pathlib import Path

import pytest

from octop.config import DatabaseConfig, OctopConfig
from octop.infra.agents.memory.backend import (
    agent_memory_namespace,
    memory_backend_from_agent_config,
    open_memory_kwargs,
    project_memory_namespace,
    resolve_project_namespace,
    team_memory_namespace,
)
from octop.infra.errors import OctopError


def test_default_memory_backend_empty_on_sqlite_control_plane() -> None:
    assert memory_backend_from_agent_config({}, octop_config=OctopConfig()) == {}


def test_default_memory_backend_follows_postgresql_control_plane() -> None:
    cfg = OctopConfig(
        database=DatabaseConfig(
            driver="postgresql",
            host="127.0.0.1",
            database="octop",
            user="octop",
            password="x",
        )
    )
    out = memory_backend_from_agent_config({}, octop_config=cfg)
    assert out["memory_backend"]["type"] == "postgres"
    assert "127.0.0.1" in out["memory_backend"]["dsn"]
    assert (
        out["memory_backend"]["dsn"].endswith("/octop") or "/octop" in out["memory_backend"]["dsn"]
    )


def test_explicit_sqlite_overrides_postgresql_control_plane() -> None:
    cfg = OctopConfig(
        database=DatabaseConfig(
            driver="postgresql",
            host="127.0.0.1",
            database="octop",
            user="octop",
            password="x",
        )
    )
    out = memory_backend_from_agent_config(
        {"memory": {"backend": {"type": "sqlite"}}},
        octop_config=cfg,
        workspace_dir=Path("/tmp/ws"),
    )
    assert out["memory_backend"]["type"] == "sqlite"
    # Compare as Path so the assertion is separator-agnostic (Windows renders
    # the db_path with backslashes; the code uses pathlib, not literal "/").
    assert Path(out["memory_backend"]["db_path"]) == Path("/tmp/ws") / "memory.sqlite"


def test_sqlite_explicit_uses_system_files_path(tmp_path: Path) -> None:
    out = memory_backend_from_agent_config(
        {"memory": {"backend": {"type": "sqlite"}}, "system_files_path": ".octop"},
        octop_config=OctopConfig(),
        workspace_dir=tmp_path,
    )
    assert Path(out["memory_backend"]["db_path"]) == tmp_path / ".octop" / "memory.sqlite"


def test_postgres_explicit_dsn() -> None:
    out = memory_backend_from_agent_config(
        {"memory": {"backend": {"type": "postgres", "dsn": "postgresql://a@b/c"}}},
        octop_config=OctopConfig(),
    )
    assert out["memory_backend"] == {"type": "postgres", "dsn": "postgresql://a@b/c"}


def test_postgres_use_control_plane_dsn() -> None:
    cfg = OctopConfig(
        database=DatabaseConfig(
            driver="postgresql",
            host="127.0.0.1",
            database="octop",
            user="octop",
            password="x",
            url="postgresql://octop:x@127.0.0.1:5432/octop?sslmode=require",
        )
    )
    out = memory_backend_from_agent_config(
        {"memory": {"backend": {"type": "postgres", "use_control_plane_dsn": True}}},
        octop_config=cfg,
    )
    assert out["memory_backend"]["type"] == "postgres"
    assert "sslmode=require" in out["memory_backend"]["dsn"]


def test_use_control_plane_dsn_requires_postgresql() -> None:
    with pytest.raises(OctopError, match="control plane"):
        memory_backend_from_agent_config(
            {"memory": {"backend": {"type": "postgres", "use_control_plane_dsn": True}}},
            octop_config=OctopConfig(),
        )


def test_open_memory_kwargs_follows_postgresql_control_plane(tmp_path: Path) -> None:
    cfg = OctopConfig(
        database=DatabaseConfig(
            driver="postgresql",
            host="127.0.0.1",
            database="octop",
            user="octop",
            password="x",
        )
    )
    ns, backend, backend_config = open_memory_kwargs(
        agent_id="a1",
        cfg={},
        octop_config=cfg,
        workspace_dir=tmp_path,
    )
    assert ns == "agent_a1"
    assert backend == "postgres"
    assert backend_config is not None
    assert "dsn" in backend_config


def test_memory_db_path_prefers_existing_nested(tmp_path: Path) -> None:
    from octop.api.common.memory_client import memory_db_path

    nested = tmp_path / ".octop" / "memory.sqlite"
    nested.parent.mkdir(parents=True)
    nested.write_text("", encoding="utf-8")
    assert memory_db_path(tmp_path) == nested


def test_memory_db_path_legacy_when_only_root_exists(tmp_path: Path) -> None:
    from octop.api.common.memory_client import memory_db_path

    root = tmp_path / "memory.sqlite"
    root.write_text("", encoding="utf-8")
    assert memory_db_path(tmp_path) == root


def test_memory_db_path_new_layout_signal_without_sqlite_yet(tmp_path: Path) -> None:
    from octop.api.common.memory_client import memory_db_path

    (tmp_path / ".octop" / "_builtin_skills").mkdir(parents=True)
    assert memory_db_path(tmp_path) == tmp_path / ".octop" / "memory.sqlite"


def test_memory_db_path_empty_octop_dir_stays_legacy(tmp_path: Path) -> None:
    from octop.api.common.memory_client import memory_db_path

    (tmp_path / ".octop").mkdir()
    assert memory_db_path(tmp_path) == tmp_path / "memory.sqlite"


# ---------------------------------------------------------------------------
# T-35 — explicit namespace override (project memory gets its own namespace)
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC = _REPO_ROOT / "src" / "octop"

# A namespace is either the ``open_memory_kwargs`` result or a named resolver
# (``memory/backend.py``); it is never built inline at a call site.
_INLINE_NAMESPACE_LITERAL = re.compile(r"\bnamespace\s*=\s*[frbu]{0,2}[\"']")
_HARDCODED_NS_ASSIGNMENT = re.compile(r"\bns\s*=\s*f[\"']")
_POSITIONAL_MEMORY_NAMESPACE = re.compile(r"\bMemory\(\s*[\"']")

# T-42 — the ``team_`` namespace prefix is *spelled* in exactly one source file.
# Matches the literal ``"team_"`` and an inline ``f"team_{...}"``, but not the
# unrelated identifiers that merely start with ``team_`` (``team_agent_id``,
# ``team_live_streamed``, …), which is why the closing character is required.
_TEAM_NAMESPACE_PREFIX_LITERAL = re.compile(r"[\"']team_[\"'{]")


def _pg_plane() -> OctopConfig:
    return OctopConfig(
        database=DatabaseConfig(
            driver="postgresql",
            host="127.0.0.1",
            database="octop",
            user="octop",
            password="x",
            url="postgresql://octop:x@127.0.0.1:5432/octop?sslmode=require",
        )
    )


def test_open_memory_kwargs_namespace_none_is_unchanged(tmp_path: Path) -> None:
    """T-35 acc.1 — zero regression: ``namespace=None`` keeps the pre-change tuples.

    The expectations are the values captured from the unmodified function (a
    7-case matrix), so any change on the default path fails this test.
    """
    ws = tmp_path / "ws"
    sqlite_plane = OctopConfig()
    sqlite_cases = [
        ("default", {}, ws / "memory.sqlite"),
        ("explicit-sqlite", {"memory": {"backend": {"type": "sqlite"}}}, ws / "memory.sqlite"),
        (
            "explicit-sqlite-dbpath",
            {
                "memory": {
                    "backend": {"type": "sqlite", "db_path": str(tmp_path / "x" / "m.sqlite")}
                }
            },
            tmp_path / "x" / "m.sqlite",
        ),
        (
            "system-files-path",
            {"memory": {"backend": {"type": "sqlite"}}, "system_files_path": ".octop"},
            ws / ".octop" / "memory.sqlite",
        ),
    ]
    for label, cfg, expected_db in sqlite_cases:
        ns, backend, backend_config = open_memory_kwargs(
            agent_id="a1", cfg=cfg, octop_config=sqlite_plane, workspace_dir=ws
        )
        assert (ns, backend) == ("agent_a1", "sqlite"), label
        assert backend_config is not None, label
        assert Path(backend_config["db_path"]) == expected_db, label

    assert open_memory_kwargs(
        agent_id="a1",
        cfg={"memory": {"backend": {"type": "postgres", "dsn": "postgresql://a@b/c"}}},
        octop_config=sqlite_plane,
        workspace_dir=ws,
    ) == ("agent_a1", "postgres", {"dsn": "postgresql://a@b/c"})

    pg_plane = _pg_plane()
    pg_cases = [
        ("pg-default", {}),
        (
            "pg-use-control-plane-dsn",
            {"memory": {"backend": {"type": "postgres", "use_control_plane_dsn": True}}},
        ),
    ]
    for label, cfg in pg_cases:
        ns, backend, backend_config = open_memory_kwargs(
            agent_id="a1", cfg=cfg, octop_config=pg_plane, workspace_dir=ws
        )
        assert (ns, backend) == ("agent_a1", "postgres"), label
        assert backend_config == {"dsn": pg_plane.database.postgresql_conninfo()}, label


def test_open_memory_kwargs_namespace_override_is_returned_verbatim(tmp_path: Path) -> None:
    """T-35 acc.2 — the override is the namespace used to build ``Memory``."""
    ns, backend, backend_config = open_memory_kwargs(
        agent_id="a1",
        cfg={},
        octop_config=OctopConfig(),
        workspace_dir=tmp_path,
        namespace="project_P1",
    )
    assert ns == "project_P1"
    assert backend == "sqlite"
    assert backend_config is not None
    assert Path(backend_config["db_path"]) == tmp_path / "memory.sqlite"


def test_namespace_override_does_not_change_backend_resolution(tmp_path: Path) -> None:
    ns, backend, backend_config = open_memory_kwargs(
        agent_id="a1",
        cfg={"memory": {"backend": {"type": "sqlite"}}},
        octop_config=_pg_plane(),
        workspace_dir=tmp_path,
        namespace="project_P1",
    )
    assert (ns, backend) == ("project_P1", "sqlite")
    assert backend_config is not None
    assert Path(backend_config["db_path"]) == tmp_path / "memory.sqlite"


def test_project_memory_namespace_matches_the_repo_convention() -> None:
    """One convention, two modules: the resolver must not drift from the writer."""
    from octop.infra.db.repos.projects import project_memory_namespace as repo_convention

    for project_id in ("P1", "AB12CD", ""):
        assert project_memory_namespace(project_id) == repo_convention(project_id)


def test_agent_default_namespace_matches_the_dashboard_read_helper() -> None:
    from octop.api.common.memory_client import memory_namespace

    assert agent_memory_namespace("a1") == memory_namespace("a1") == "agent_a1"


def test_resolve_project_namespace_prefers_the_projects_column() -> None:
    """``projects.memory_namespace`` is the authority; the convention is a fallback."""
    assert (
        resolve_project_namespace(memory_namespace="project_RENAMED", project_id="P1")
        == "project_RENAMED"
    )
    assert resolve_project_namespace(memory_namespace=None, project_id="P1") == "project_P1"
    assert resolve_project_namespace(memory_namespace="", project_id="P1") == "project_P1"


def test_source_never_builds_a_memory_namespace_inline() -> None:
    """T-35 acc.5 — no call site bypasses the namespace parameter (grep ⇒ 0)."""
    offenders: list[str] = []
    for path in sorted(_SRC.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(_SRC).as_posix()
        if _INLINE_NAMESPACE_LITERAL.search(text):
            offenders.append(f"{rel}: namespace=<literal>")
        if _HARDCODED_NS_ASSIGNMENT.search(text):
            offenders.append(f"{rel}: ns = f'<literal>'")
        if _POSITIONAL_MEMORY_NAMESPACE.search(text):
            offenders.append(f"{rel}: Memory(<positional literal>)")
    assert offenders == []


def test_team_namespace_prefix_is_spelled_only_in_backend() -> None:
    """T-42 — the third isolation axis has one spelling site, like the other two.

    Scope: **production source** (``src/octop``), matching the sibling
    ``test_source_never_builds_a_memory_namespace_inline`` above. ``agent_`` /
    ``project_`` are spelled in this module; ``team_`` must be too, otherwise a
    module could define its own namespace convention and the team isolation axis
    would drift silently (``PLAN.md``: no file may fix its own layer count, order
    or namespace spelling).

    Deliberately **not** widened to ``tests/`` (lead arbitration, T-42): a test
    must build its expected value from a literal, not by importing the helper it
    is checking — importing it would make the assertion self-confirming and the
    helper unprovable. So a team_-prefixed string literal inside a test is
    correct usage, not a second spelling site, and this assertion stays scoped to
    production source.
    """
    sites: list[tuple[str, int]] = []
    for path in sorted(_SRC.rglob("*.py")):
        hits = _TEAM_NAMESPACE_PREFIX_LITERAL.findall(path.read_text(encoding="utf-8"))
        if hits:
            sites.append((path.relative_to(_SRC).as_posix(), len(hits)))
    assert sites == [("infra/agents/memory/backend.py", 1)]


def test_multi_ns_forwards_the_team_namespace_helper() -> None:
    """T-42 — ``multi_ns`` re-exports the single implementation; it does not re-spell it."""
    from octop.infra.agents.memory import multi_ns

    assert multi_ns.team_memory_namespace is team_memory_namespace


def test_harness_agent_config_name_is_still_the_agent_namespace() -> None:
    """T-35 hard constraint — only ``Memory``'s namespace may be overridden.

    The harness builds its own ``Memory`` from ``HarnessAgentConfig(name=…)``;
    pointing that at a project namespace would make every member lose its
    private memory (the reason N1 was rejected).
    """
    manager = (_SRC / "infra" / "agents" / "manager.py").read_text(encoding="utf-8")
    assert "name=_memory_namespace(row.agent_id)" in manager
    assert 'ns = f"agent_' not in manager
