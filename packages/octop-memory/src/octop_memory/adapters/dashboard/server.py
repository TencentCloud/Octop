"""FastAPI service for the local octop-memory dashboard.

Reads SQLite directly and exposes memory data through REST endpoints.
It intentionally avoids ``octop_memory.core.Memory`` and queries with
``sqlite3`` to keep LLM / embedding dependencies out of the dashboard path.
"""

from __future__ import annotations

import contextlib
import json
import logging
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# FastAPI is optional and only available when the dashboard extra is installed.
try:
    from fastapi import Body, FastAPI, HTTPException, Query
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles
except ImportError as _e:
    raise ImportError(
        "octop-memory dashboard 需要 fastapi 和 uvicorn。\n请运行: pip install 'octop-memory[dashboard]'"
    ) from _e

# ---------------------------------------------------------------------------
# Global state. The dashboard is a local read-only tool in one process.
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).parent / "static"
_STATS_ALLOWED_COLS = frozenset({"timestamp", "created_at", "occurred_at"})

app = FastAPI(title="octop-memory Dashboard", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static frontend files.
if _STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# Allowed table suffixes. Keep this aligned with SqliteMemoryBackend.
_ALLOWED_TABLE_SUFFIXES = frozenset(
    {
        "_raw_events",
        "_candidates",
        "_atoms",
        "_journal",
        "_episodes",
        "_memory_nodes",
        "_entities",
        "_entity_pages",
        "_digests",
        "_meta",
    }
)

# Allowed ORDER BY columns.
_ALLOWED_ORDER_COLS = frozenset(
    {
        "rowid",
        "id",
        "timestamp",
        "created_at",
        "occurred_at",
        "updated_at",
        "deprecated_at",
        "started_at",
        "failed_at",
    }
)

# Allowed ORDER BY directions.
_ALLOWED_ORDER_DIRS = frozenset({"ASC", "DESC"})

# Maximum namespace length.
_MAX_NAMESPACE_LEN = 128


def _norm_ns(namespace: str) -> str:
    """Normalize a namespace into a valid SQLite table prefix."""
    if len(namespace) > _MAX_NAMESPACE_LEN:
        raise HTTPException(status_code=400, detail="namespace 长度超出限制")
    return re.sub(r"[^a-z0-9_]", "_", namespace.lower())


def _safe_table_name(ns: str, suffix: str) -> str:
    """Build a safe table name after validating the namespace and suffix."""
    if not re.fullmatch(r"[a-z0-9_]{1,128}", ns):
        raise HTTPException(status_code=400, detail="namespace 格式非法")
    if suffix not in _ALLOWED_TABLE_SUFFIXES:
        raise HTTPException(status_code=400, detail=f"非法的表名后缀: {suffix!r}")
    return f"{ns}{suffix}"


def _safe_order_col(col: str) -> str:
    """Validate an ORDER BY column against the allowlist."""
    if col not in _ALLOWED_ORDER_COLS:
        raise HTTPException(status_code=400, detail=f"非法的排序列: {col!r}")
    return col


def _safe_order_dir(direction: str) -> str:
    """Validate the ORDER BY direction."""
    upper = direction.upper()
    if upper not in _ALLOWED_ORDER_DIRS:
        raise HTTPException(status_code=400, detail=f"非法的排序方向: {direction!r}")
    return upper


def _safe_db_path(db_path: str) -> str:
    """Resolve and validate a database path to prevent path traversal."""
    expanded = str(Path(db_path).expanduser().resolve())
    # Only SQLite-like file suffixes are accepted.
    if not re.search(r"\.(?:sqlite|sqlite3|db)$", expanded, re.IGNORECASE):
        raise HTTPException(status_code=400, detail="db_path 必须是 .sqlite / .sqlite3 / .db 文件")
    return expanded


def _open_db(db_path: str, readonly: bool = True) -> sqlite3.Connection:
    """Open a SQLite database; readonly by default."""
    expanded = _safe_db_path(db_path)
    if not Path(expanded).exists():
        raise HTTPException(
            status_code=404,
            detail=f"数据库文件不存在: {expanded}。请先与 AI 进行对话以生成记忆数据。",
        )
    if readonly:
        conn = sqlite3.connect(f"file:{expanded}?mode=ro", uri=True, check_same_thread=False)
    else:
        conn = sqlite3.connect(expanded, check_same_thread=False)
        # FTS sync triggers call hm_cjk_seg(), so write connections must register it.
        try:
            from octop_memory.storage.backends.fts_text import register_fts_functions

            register_fts_functions(conn)
        except (sqlite3.Error, ImportError, OSError):
            # Fall back to a passthrough function so triggers do not fail.
            logger.warning("FTS helper registration failed; using passthrough", exc_info=True)

            def _passthrough_cjk(value: str | None) -> str:
                return value or ""

            conn.create_function("hm_cjk_seg", 1, _passthrough_cjk, deterministic=True)
    conn.row_factory = sqlite3.Row
    return conn


def _rows_to_list(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    """Convert sqlite3.Row objects to JSON-serializable dictionaries."""
    result = []
    for row in rows:
        d = dict(row)
        # Decode JSON string fields when present.
        for key in (
            "payload",
            "raw_event_ids",
            "search_terms",
            "people",
            "topics",
            "aliases",
            "digest_ids",
            "before",
            "after",
        ):
            if key in d and isinstance(d[key], str):
                with contextlib.suppress(json.JSONDecodeError, TypeError):
                    d[key] = json.loads(d[key])
        result.append(d)
    return result


def _check_table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    """Return whether a table exists."""
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    )
    return cur.fetchone() is not None


def _paginate_query(
    conn: sqlite3.Connection,
    table: str,
    order_col: str = "rowid",
    order: str = "DESC",
    page: int = 1,
    page_size: int = 20,
    where: str = "",
    params: tuple[Any, ...] = (),
) -> dict[str, Any]:
    """Run a paginated query after identifier allowlist validation."""
    # Defense in depth: revalidate the table identifier shape.
    if not re.fullmatch(r"[a-z0-9_]{1,200}", table):
        raise HTTPException(status_code=400, detail="非法的表名")
    # Defense in depth: validate order_col and order again.
    safe_col = _safe_order_col(order_col)
    safe_order = _safe_order_dir(order)

    if not _check_table_exists(conn, table):
        return {"items": [], "total": 0, "page": page, "page_size": page_size, "has_more": False}

    # Defense in depth: fetch the actual table name from sqlite_master so the
    # string interpolated into SQL comes from SQLite, not user input.
    verified_table = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()[0]

    where_clause = f"WHERE {where}" if where else ""
    count_sql = f"SELECT COUNT(*) FROM {verified_table} {where_clause}"
    total = conn.execute(count_sql, params).fetchone()[0]

    offset = (page - 1) * page_size
    data_sql = f"SELECT * FROM {verified_table} {where_clause} ORDER BY {safe_col} {safe_order} LIMIT ? OFFSET ?"
    rows = conn.execute(data_sql, (*params, page_size, offset)).fetchall()

    return {
        "items": _rows_to_list(rows),
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_more": offset + page_size < total,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/")
def index() -> FileResponse:
    """Return the dashboard frontend."""
    index_file = _STATIC_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="前端文件未找到")
    return FileResponse(str(index_file))


@app.get("/api/connect")
def connect(
    db_path: str = Query(..., description="SQLite 数据库路径"),
    namespace: str = Query(..., description="记忆命名空间（表前缀）"),
) -> dict[str, Any]:
    """Validate database connectivity and return available table info."""
    # Always validate path format through _safe_db_path to prevent traversal.
    expanded = _safe_db_path(db_path)
    if not Path(expanded).exists():
        raise HTTPException(
            status_code=404,
            detail=f"数据库文件不存在: {expanded}。请先与 AI 进行对话以生成记忆数据。",
        )

    ns = _norm_ns(namespace)
    conn = _open_db(db_path)
    try:
        # Check table existence through _safe_table_name suffix allowlisting.
        tables = {
            "raw_events": _check_table_exists(conn, _safe_table_name(ns, "_raw_events")),
            "candidates": _check_table_exists(conn, _safe_table_name(ns, "_candidates")),
            "atoms": _check_table_exists(conn, _safe_table_name(ns, "_atoms")),
            "journal": _check_table_exists(conn, _safe_table_name(ns, "_journal")),
            "episodes": _check_table_exists(conn, _safe_table_name(ns, "_episodes")),
        }
        return {
            "ok": True,
            "db_path": expanded,
            "namespace": namespace,
            "ns_prefix": ns,
            "tables": tables,
        }
    finally:
        conn.close()


@app.get("/api/stats")
def stats(
    db_path: str = Query(..., description="SQLite 数据库路径"),
    namespace: str = Query(..., description="记忆命名空间"),
) -> dict[str, Any]:
    """Return memory counts across layers."""
    ns = _norm_ns(namespace)
    conn = _open_db(db_path)
    try:
        # Pre-build safe table names through suffix allowlisting.
        tbl_raw = _safe_table_name(ns, "_raw_events")
        tbl_atoms = _safe_table_name(ns, "_atoms")
        tbl_cands = _safe_table_name(ns, "_candidates")
        tbl_episodes = _safe_table_name(ns, "_episodes")
        tbl_journal = _safe_table_name(ns, "_journal")

        def _count(table: str, where: str = "", params: tuple[Any, ...] = ()) -> int:
            if not _check_table_exists(conn, table):
                return 0
            # Fetch the actual table name from sqlite_master before SQL interpolation.
            verified = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()[0]
            where_clause = f"WHERE {where}" if where else ""
            return int(conn.execute(f"SELECT COUNT(*) FROM {verified} {where_clause}", params).fetchone()[0])

        def _max_ts(table: str, col: str) -> str | None:
            if not _check_table_exists(conn, table):
                return None
            # Validate the column name allowlist to prevent injection.
            if col not in _STATS_ALLOWED_COLS:
                raise HTTPException(status_code=400, detail=f"非法的统计列: {col!r}")
            # Fetch the actual table name from sqlite_master.
            verified = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()[0]
            row = conn.execute(f"SELECT MAX({col}) FROM {verified}").fetchone()
            return row[0] if row else None

        raw_events_total = _count(tbl_raw)
        atoms_active = _count(tbl_atoms, "deprecated_at IS NULL")
        atoms_deprecated = _count(tbl_atoms, "deprecated_at IS NOT NULL")
        candidates_pending = _count(tbl_cands, "status = ?", ("pending",))
        episodes_total = _count(tbl_episodes)
        journal_total = _count(tbl_journal)
        last_capture = _max_ts(tbl_raw, "timestamp")

        return {
            "raw_events": raw_events_total,
            "atoms_active": atoms_active,
            "atoms_deprecated": atoms_deprecated,
            "atoms_total": atoms_active + atoms_deprecated,
            "candidates_pending": candidates_pending,
            "episodes": episodes_total,
            "journal": journal_total,
            "last_capture": last_capture,
        }
    finally:
        conn.close()


@app.get("/api/raw_events")
def raw_events(
    db_path: str = Query(...),
    namespace: str = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session_id: str | None = Query(None),
    event_type: str | None = Query(None),
) -> dict[str, Any]:
    """List raw conversation events."""
    ns = _norm_ns(namespace)
    conn = _open_db(db_path)
    try:
        where_parts = []
        params: list[Any] = []
        if session_id:
            where_parts.append("session_id = ?")
            params.append(session_id)
        if event_type:
            where_parts.append("event_type = ?")
            params.append(event_type)
        where = " AND ".join(where_parts)
        return _paginate_query(
            conn,
            _safe_table_name(ns, "_raw_events"),
            "timestamp",
            "DESC",
            page,
            page_size,
            where,
            tuple(params),
        )
    finally:
        conn.close()


@app.get("/api/candidates")
def candidates(
    db_path: str = Query(...),
    namespace: str = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    candidate_type: str | None = Query(None),
) -> dict[str, Any]:
    """List candidate memories."""
    ns = _norm_ns(namespace)
    conn = _open_db(db_path)
    try:
        where_parts = []
        params: list[Any] = []
        if status:
            where_parts.append("status = ?")
            params.append(status)
        if candidate_type:
            where_parts.append("candidate_type = ?")
            params.append(candidate_type)
        where = " AND ".join(where_parts)
        return _paginate_query(
            conn,
            _safe_table_name(ns, "_candidates"),
            "created_at",
            "DESC",
            page,
            page_size,
            where,
            tuple(params),
        )
    finally:
        conn.close()


@app.get("/api/atoms")
def atoms(
    db_path: str = Query(...),
    namespace: str = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    include_deprecated: bool = Query(False),
    importance: str | None = Query(None),
) -> dict[str, Any]:
    """List atom memories."""
    ns = _norm_ns(namespace)
    conn = _open_db(db_path)
    try:
        where_parts = []
        params: list[Any] = []
        if not include_deprecated:
            where_parts.append("deprecated_at IS NULL")
        if importance:
            where_parts.append("importance = ?")
            params.append(importance)
        where = " AND ".join(where_parts)
        return _paginate_query(
            conn,
            _safe_table_name(ns, "_atoms"),
            "created_at",
            "DESC",
            page,
            page_size,
            where,
            tuple(params),
        )
    finally:
        conn.close()


@app.get("/api/atoms/{atom_id}")
def get_atom(
    atom_id: str,
    db_path: str = Query(...),
    namespace: str = Query(...),
) -> dict[str, Any]:
    """Return one atom memory with its linked candidate when available."""
    ns = _norm_ns(namespace)
    conn = _open_db(db_path)
    try:
        atom_table = _safe_table_name(ns, "_atoms")
        if not _check_table_exists(conn, atom_table):
            raise HTTPException(status_code=404, detail="atoms 表不存在")
        # Fetch the actual table name from sqlite_master before SQL interpolation.
        verified_atom_table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (atom_table,),
        ).fetchone()[0]
        row = conn.execute(f"SELECT * FROM {verified_atom_table} WHERE id = ?", (atom_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"atom {atom_id!r} 不存在")
        atom = _rows_to_list([row])[0]

        # Attach the linked candidate when the table exists.
        cand_table = _safe_table_name(ns, "_candidates")
        if _check_table_exists(conn, cand_table):
            verified_cand_table = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (cand_table,),
            ).fetchone()[0]
            cand_row = conn.execute(
                f"SELECT * FROM {verified_cand_table} WHERE id = ?", (atom["candidate_id"],)
            ).fetchone()
            atom["candidate"] = _rows_to_list([cand_row])[0] if cand_row else None
        else:
            atom["candidate"] = None

        return atom
    finally:
        conn.close()


@app.get("/api/journal")
def journal(
    db_path: str = Query(...),
    namespace: str = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    action: str | None = Query(None),
    actor: str | None = Query(None),
) -> dict[str, Any]:
    """List journal entries."""
    ns = _norm_ns(namespace)
    conn = _open_db(db_path)
    try:
        where_parts = []
        params: list[Any] = []
        if action:
            where_parts.append("action = ?")
            params.append(action)
        if actor:
            where_parts.append("actor = ?")
            params.append(actor)
        where = " AND ".join(where_parts)
        return _paginate_query(
            conn,
            _safe_table_name(ns, "_journal"),
            "timestamp",
            "DESC",
            page,
            page_size,
            where,
            tuple(params),
        )
    finally:
        conn.close()


@app.get("/api/episodes")
def episodes(
    db_path: str = Query(...),
    namespace: str = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    emotion: str | None = Query(None),
) -> dict[str, Any]:
    """List episode summaries."""
    ns = _norm_ns(namespace)
    conn = _open_db(db_path)
    try:
        where_parts = []
        params: list[Any] = []
        if emotion:
            where_parts.append("emotion = ?")
            params.append(emotion)
        where = " AND ".join(where_parts)
        return _paginate_query(
            conn,
            _safe_table_name(ns, "_episodes"),
            "occurred_at",
            "DESC",
            page,
            page_size,
            where,
            tuple(params),
        )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Write APIs
# ---------------------------------------------------------------------------


@app.patch("/api/candidates/{candidate_id}")
def update_candidate_status(
    candidate_id: str,
    db_path: str = Query(...),
    namespace: str = Query(...),
    status: str = Body(..., embed=True),
) -> dict[str, Any]:
    """Review a candidate memory by updating its status."""
    allowed = {"promoted", "rejected", "pending", "needs_review"}
    if status not in allowed:
        raise HTTPException(status_code=400, detail=f"status 必须是 {allowed} 之一")

    ns = _norm_ns(namespace)
    conn = _open_db(db_path, readonly=False)
    try:
        table = _safe_table_name(ns, "_candidates")
        if not _check_table_exists(conn, table):
            raise HTTPException(status_code=404, detail="candidates 表不存在")
        # Fetch the actual table name from sqlite_master before SQL interpolation.
        verified_table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()[0]
        row = conn.execute(f"SELECT id FROM {verified_table} WHERE id = ?", (candidate_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"candidate {candidate_id!r} 不存在")
        conn.execute(f"UPDATE {verified_table} SET status = ? WHERE id = ?", (status, candidate_id))
        conn.commit()
        return {"ok": True, "id": candidate_id, "status": status}
    finally:
        conn.close()


@app.delete("/api/atoms/{atom_id}")
def deprecate_atom(
    atom_id: str,
    db_path: str = Query(...),
    namespace: str = Query(...),
) -> dict[str, Any]:
    """Soft-delete an atom by setting deprecated_at."""
    ns = _norm_ns(namespace)
    conn = _open_db(db_path, readonly=False)
    try:
        table = _safe_table_name(ns, "_atoms")
        if not _check_table_exists(conn, table):
            raise HTTPException(status_code=404, detail="atoms 表不存在")
        # Fetch the actual table name from sqlite_master before SQL interpolation.
        verified_table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()[0]
        row = conn.execute(f"SELECT id, deprecated_at FROM {verified_table} WHERE id = ?", (atom_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"atom {atom_id!r} 不存在")
        now = datetime.now(UTC).isoformat()
        conn.execute(f"UPDATE {verified_table} SET deprecated_at = ? WHERE id = ?", (now, atom_id))
        conn.commit()
        return {"ok": True, "id": atom_id, "deprecated_at": now}
    finally:
        conn.close()


@app.delete("/api/raw_events/{event_id}")
def delete_raw_event(
    event_id: str,
    db_path: str = Query(...),
    namespace: str = Query(...),
) -> dict[str, Any]:
    """Hard-delete a raw event for privacy cleanup."""
    ns = _norm_ns(namespace)
    conn = _open_db(db_path, readonly=False)
    try:
        table = _safe_table_name(ns, "_raw_events")
        if not _check_table_exists(conn, table):
            raise HTTPException(status_code=404, detail="raw_events 表不存在")
        # Fetch the actual table name from sqlite_master before SQL interpolation.
        verified_table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()[0]
        row = conn.execute(f"SELECT id FROM {verified_table} WHERE id = ?", (event_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"raw_event {event_id!r} 不存在")
        conn.execute(f"DELETE FROM {verified_table} WHERE id = ?", (event_id,))
        conn.commit()
        return {"ok": True, "id": event_id, "deleted": True}
    finally:
        conn.close()


@app.get("/api/defaults")
def get_defaults() -> dict[str, Any]:
    """Return CLI-injected default db_path and namespace for frontend autofill.

    Empty strings mean the CLI did not provide defaults, so the frontend stays
    in manual input mode.
    """
    db_path: str = getattr(app.state, "default_db_path", "")
    namespace: str = getattr(app.state, "default_namespace", "")
    return {"db_path": db_path, "namespace": namespace}


@app.get("/api/namespaces")
def list_namespaces(
    db_path: str = Query(..., description="SQLite 数据库路径"),
) -> dict[str, Any]:
    """Discover namespaces present in the database by scanning table prefixes."""
    conn = _open_db(db_path)
    try:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
        table_names = [r[0] for r in rows]

        # Use tables ending in _raw_events as namespace anchors and validate the
        # prefix shape to filter tampered table names.
        namespaces = []
        for name in table_names:
            if name.endswith("_raw_events"):
                ns_prefix = name[: -len("_raw_events")]
                # Only return syntactically valid namespace prefixes.
                if re.fullmatch(r"[a-z0-9_]{1,128}", ns_prefix):
                    namespaces.append(ns_prefix)

        return {"namespaces": namespaces}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Startup entrypoint used by the CLI.
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    """Return the FastAPI app instance for tests and external mounting."""
    return app
