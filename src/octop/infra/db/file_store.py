"""Runtime PostgreSQL tables for skill-package and knowledge bytes.

Control-plane metadata already lives in ``public`` (``knowledge_bases``,
``knowledge_documents``, ``skill_packages``). These tables use that same
schema and are created on first open, not by numbered migrations.
``CREATE EXTENSION vector`` stays an operator step (ADR 002).

Older builds kept ``octop_knowledge`` and ``octop_skill_packages``. Those
tables are renamed into ``public`` on first open. A primary key on a table
named ``files`` is the index ``files_pkey``, which is unique per schema, so
each index is renamed to the destination table before the table enters
``public``.
"""

from __future__ import annotations

import re
from typing import Any

from octop_harness.backends.postgres import PostgresBackend, PostgresConfig

from octop.config import DatabaseConfig

KNOWLEDGE_FILES = "knowledge_files"
KNOWLEDGE_CHUNKS = "knowledge_chunks"
SKILL_PACKAGE_FILES = "skill_package_files"

_LEGACY_TABLES = (
    ("octop_knowledge", "files", KNOWLEDGE_FILES),
    ("octop_knowledge", "chunks", KNOWLEDGE_CHUNKS),
    ("octop_skill_packages", "files", SKILL_PACKAGE_FILES),
)
_LEGACY_SCHEMAS = ("octop_knowledge", "octop_skill_packages")
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def open_postgres_files(
    database: DatabaseConfig,
    *,
    schema: str,
    table: str,
) -> PostgresBackend:
    """Return a file backend bound to ``schema.table`` on ``database``."""
    adopt_legacy_content_tables(database)
    kwargs: dict[str, Any] = {
        "schema": schema,
        "table": table,
        "sslmode": "prefer",
    }
    if database.url:
        kwargs["connection_string"] = database.url
    else:
        kwargs.update(
            host=database.host,
            port=database.port,
            database=database.database,
            user=database.user,
            password=database.password or "",
        )
    return PostgresBackend(PostgresConfig.from_kwargs(**kwargs))


def adopt_legacy_content_tables(database: DatabaseConfig) -> None:
    """Move pre-unification content tables into ``public`` when they exist."""
    if not database.is_postgresql:
        return
    import psycopg

    with psycopg.connect(database.postgresql_conninfo(), autocommit=True) as conn:
        for schema, old_name, new_name in _LEGACY_TABLES:
            if _relation_exists(conn, "public", new_name):
                _retarget_storage_names(
                    conn, "public", new_name, legacy=old_name, canonical=new_name
                )
            if not _relation_exists(conn, schema, old_name):
                continue
            if not _relation_exists(conn, "public", new_name):
                _retarget_storage_names(conn, schema, old_name, legacy=old_name, canonical=new_name)
                conn.execute(f"ALTER TABLE {_q(schema)}.{_q(old_name)} SET SCHEMA public")
                if old_name != new_name:
                    conn.execute(f"ALTER TABLE public.{_q(old_name)} RENAME TO {_q(new_name)}")
                continue
            conn.execute(
                f"INSERT INTO public.{_q(new_name)} SELECT * FROM {_q(schema)}.{_q(old_name)} "
                "ON CONFLICT DO NOTHING"
            )
            conn.execute(f"DROP TABLE {_q(schema)}.{_q(old_name)}")
        for schema in _LEGACY_SCHEMAS:
            exists = conn.execute(
                "SELECT 1 FROM pg_namespace WHERE nspname = %s",
                (schema,),
            ).fetchone()
            if exists is None:
                continue
            left = conn.execute(
                """
                SELECT 1
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = %s AND c.relkind = 'r'
                """,
                (schema,),
            ).fetchone()
            if left is None:
                conn.execute(f"DROP SCHEMA {_q(schema)}")


def _retarget_storage_names(
    conn: Any,
    schema: str,
    table: str,
    *,
    legacy: str,
    canonical: str,
) -> None:
    """Rename leftover ``files_pkey``-style indexes onto the canonical table."""
    pairs: list[tuple[str, str]] = [
        (f"{legacy}_pkey", f"{canonical}_pkey"),
        (f"idx_{legacy}_path_prefix", f"idx_{canonical}_path_prefix"),
    ]
    if legacy == "chunks":
        pairs.append(("idx_octop_knowledge_chunks_doc", "idx_knowledge_chunks_doc"))
    for old, new in pairs:
        _rename_index(conn, schema, old, new)
        if old.endswith("_pkey"):
            _rename_constraint(conn, schema, table, old, new)


def _rename_index(conn: Any, schema: str, old: str, new: str) -> None:
    if old == new or not _relation_exists(conn, schema, old):
        return
    if _relation_exists(conn, schema, new):
        if not old.endswith("_pkey"):
            conn.execute(f"DROP INDEX {_q(schema)}.{_q(old)}")
        return
    conn.execute(f"ALTER INDEX {_q(schema)}.{_q(old)} RENAME TO {_q(new)}")


def _rename_constraint(conn: Any, schema: str, table: str, old: str, new: str) -> None:
    if old == new or not _constraint_exists(conn, schema, table, old):
        return
    if _constraint_exists(conn, schema, table, new):
        return
    conn.execute(f"ALTER TABLE {_q(schema)}.{_q(table)} RENAME CONSTRAINT {_q(old)} TO {_q(new)}")


def _relation_exists(conn: Any, schema: str, name: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s)", (f"{schema}.{name}",)).fetchone()
    return row is not None and row[0] is not None


def _constraint_exists(conn: Any, schema: str, table: str, name: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM pg_constraint con
        JOIN pg_class rel ON rel.oid = con.conrelid
        JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
        WHERE nsp.nspname = %s AND rel.relname = %s AND con.conname = %s
        """,
        (schema, table, name),
    ).fetchone()
    return row is not None


def _q(name: str) -> str:
    if _IDENT.fullmatch(name) is None:
        raise ValueError(f"unsafe SQL identifier: {name}")
    return name
