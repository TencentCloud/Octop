"""octop db — database inspection and migration utilities."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import click
from psycopg import connect as pg_connect

from octop.config import DatabaseConfig, load_config
from octop.infra.db.factory import open_database
from octop.infra.utils.paths import PathLayout

# Tables that belong to the target Postgres dialect (never overwritten from
# SQLite).  ``sqlite_sequence`` is an SQLite autoincrement bookkeeping table
# that does not exist on Postgres.
PG_NATIVE_TABLES: set[str] = {"_schema_version", "sqlite_sequence"}


def _resolve_src_path(home: Path | None) -> PathLayout:
    return PathLayout(home) if home is not None else PathLayout.from_env()


def _resolve_tgt_config(path: str) -> tuple[Path, DatabaseConfig]:
    """Load a target config.json and return (config_dir, DatabaseConfig)."""
    cfg_path = Path(path).expanduser()
    if not cfg_path.is_file():
        raise click.BadParameter(f"not a file: {cfg_path}")
    cfg = load_config(cfg_path)
    if not cfg.database.is_postgresql:
        raise click.BadParameter(
            f"target config at {cfg_path} does not set database.driver=postgresql"
        )
    return cfg_path.parent, cfg.database


def _source_tables(sqlite_path: Path) -> list[str]:
    """Return user-data table names in the source SQLite database."""
    conn = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    finally:
        conn.close()
    return [r[0] for r in rows if r[0] not in PG_NATIVE_TABLES]


def _source_row_count(sqlite_path: Path, table: str) -> int:
    conn = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


def _column_info(sqlite_path: Path, table: str) -> list[tuple[str, str]]:
    """Return [(name, sqlite_type), ...] for a table."""
    conn = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    try:
        return [(r[1], (r[2] or "").upper()) for r in conn.execute(f"PRAGMA table_info({table})")]
    finally:
        conn.close()


def _pg0param(col_type: str) -> str:
    """Return a psycopg placeholder + cast expression for a SQLite column type."""
    t = col_type.upper()
    if t in ("REAL", "FLOAT", "DOUBLE"):
        return "%s::double precision"
    if t in ("INTEGER", "INT", "BIGINT"):
        return "%s::bigint"
    if t == "BLOB":
        return "%s::bytea"
    if t in ("JSON",):
        return "%s::jsonb"
    return "%s"


def _convert_value(val: Any, col_type: str) -> Any:
    """Convert a single SQLite cell value to a psycopg-compatible type."""
    if val is None:
        return None
    t = col_type.upper()
    if t in ("REAL", "FLOAT", "DOUBLE"):
        return float(val)
    if t in ("INTEGER", "INT", "BIGINT"):
        return int(val)
    if t == "BLOB":
        return bytes(val)
    if t in ("JSON",):
        if isinstance(val, str) and val.strip():
            return json.dumps(json.loads(val))
        if isinstance(val, (dict, list)):
            return json.dumps(val)
        return str(val) if val else "[]"
    if isinstance(val, float):
        return float(val)
    if isinstance(val, int):
        return int(val)
    return str(val)


@click.group()
def db() -> None:
    """Database inspection and migration utilities."""


@db.command("migrate-to-pg")
@click.option(
    "--target-config",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help=(
        "Path to the target Postgres config.json.  The target database must "
        "already be initialised (octop init or equivalent) so that all "
        "tables exist before data is copied."
    ),
)
@click.option(
    "--source-home",
    default=None,
    type=click.Path(exists=True, file_okay=False),
    help="Source OCTOP_HOME directory (default: $OCTOP_HOME or ~/.octop).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Report what would be migrated and exit without writing anything.",
)
@click.option(
    "--yes",
    is_flag=True,
    help="Skip the confirmation prompt.",
)
def migrate_to_pg(
    target_config: str,
    source_home: str | None,
    dry_run: bool,
    yes: bool,
) -> None:
    """Migrate all user data from a SQLite database into a PostgreSQL database.

    The **source** is the current (or ``--source-home``) Octop install whose
    ``config.json`` has ``database.driver: sqlite``.

    The **target** is a PostgreSQL Octop install whose ``config.json`` is
    passed via ``--target-config``.  Run ``octop init`` (or equivalent) against
    the target *first* so that every table exists — this command only copies
    rows, it does not create any schema.

    \b
    Important:
    * Stop ``octop run`` on *both* the source and target instances first.
    * The target database user needs ``SUPERUSER`` so that foreign-key
      checks can be temporarily disabled during the bulk copy.
    """
    src_paths = _resolve_src_path(
        Path(source_home).expanduser() if source_home else None
    )
    sqlite_path = src_paths.db
    if not sqlite_path.is_file():
        raise click.UsageError(f"SQLite database not found: {sqlite_path}")

    tgt_dir, tgt_db = _resolve_tgt_config(target_config)

    # Open both sides to validate connectivity and schema versions.
    src_cfg = load_config(src_paths.config)
    if not src_cfg.database.is_sqlite:
        click.echo(
            f"Source config at {src_paths.config} is not SQLite; nothing to migrate."
        )
        return

    src_db = open_database(src_cfg, src_paths)
    try:
        with src_db.connect() as conn:
            src_ver = conn.execute(
                "SELECT version FROM _schema_version"
            ).fetchone()[0]
    finally:
        src_db.close()

    tgt_conn = pg_connect(tgt_db.postgresql_conninfo(), autocommit=True, connect_timeout=10)
    try:
        tgt_ver_row = tgt_conn.execute(
            "SELECT version FROM _schema_version"
        ).fetchone()
        tgt_ver = tgt_ver_row[0] if tgt_ver_row else 0
        if tgt_ver < int(src_ver):
            raise click.UsageError(
                f"Target schema version {tgt_ver} is older than source ({src_ver}). "
                "Run 'octop init' against the target first."
            )
    finally:
        tgt_conn.close()

    tables = _source_tables(sqlite_path)
    if not tables:
        click.echo("No user-data tables found.")
        return

    # Summary before confirmation.
    total_rows = 0
    table_counts: list[tuple[str, int]] = []
    for tbl in tables:
        n = _source_row_count(sqlite_path, tbl)
        if n:
            table_counts.append((tbl, n))
            total_rows += n

    click.echo(f"Source : {sqlite_path}")
    click.echo(f"Target : {tgt_db.postgresql_conninfo()}")
    click.echo(f"Schema : {src_ver} -> {tgt_ver}")
    click.echo(f"Tables : {len(tables)} ({len(table_counts)} with data, {total_rows} rows)")
    click.echo()

    if not table_counts:
        click.echo("All tables are empty — nothing to copy.")
        return

    for tbl, n in table_counts:
        click.echo(f"  {tbl:40s} {n:>8d} rows")
    click.echo()

    if dry_run:
        click.echo("--dry-run: no changes made.")
        return

    if not yes:
        click.confirm("Overwrite target tables with source data?", abort=True)

    # Disable foreign-key checks (requires SUPERUSER).
    tgt_conn = pg_connect(tgt_db.postgresql_conninfo(), autocommit=True, connect_timeout=10)
    fk_disabled = True
    try:
        tgt_conn.execute("SET session_replication_role = 'replica'")
    except Exception:
        fk_disabled = False
        click.echo(
            "Foreign-key checks are active (SUPERUSER not available).  "
            "Tables will be ordered so that referenced tables are copied first."
        )

    # When foreign keys are enforced, migrate tables without foreign keys
    # first, then retry the rest — their referenced parents are now in place.
    first_pass: list[str] = []
    second_pass: list[str] = []
    if not fk_disabled:
        # Heuristic: tables whose name appears as a prefix in other FK
        # constraint names are likely parent tables.
        fk_tables: set[str] = set()
        try:
            for r in tgt_conn.execute(
                "SELECT table_name FROM information_schema.table_constraints "
                "WHERE constraint_type='FOREIGN KEY' AND table_schema='public'"
            ):
                fk_tables.add(r[0])
        except Exception:
            pass
        for tbl in tables:
            (second_pass if tbl in fk_tables else first_pass).append(tbl)
        ordered = first_pass + second_pass
    else:
        ordered = list(tables)

    failures: list[str] = []
    try:
        for idx, tbl in enumerate(ordered, 1):
            cols = _column_info(sqlite_path, tbl)
            if not cols:
                continue
            col_names = [c[0] for c in cols]
            col_types = [c[1] for c in cols]
            sqlite_count = _source_row_count(sqlite_path, tbl)

            if sqlite_count == 0:
                pg_count = tgt_conn.execute(
                    f"SELECT COUNT(*) FROM {tbl}"
                ).fetchone()[0]
                if pg_count != 0:
                    click.echo(
                        f"  [{idx}/{len(tables)}] {tbl}: SKIP (0 src rows, "
                        f"{pg_count} target rows — left unchanged)"
                    )
                continue

            placeholders = [_pg0param(ct) for ct in col_types]
            insert_sql = (
                f"INSERT INTO {tbl} ({','.join(col_names)}) "
                f"VALUES ({','.join(placeholders)})"
            )

            # Clear target table then copy.
            tgt_conn.execute(f"DELETE FROM {tbl}")

            conn = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
            try:
                sqlite_rows = conn.execute(f"SELECT * FROM {tbl}").fetchall()
            finally:
                conn.close()

            with tgt_conn.transaction():
                for row in sqlite_rows:
                    values = [
                        _convert_value(row[ci], col_types[ci])
                        for ci in range(len(row))
                    ]
                    tgt_conn.execute(insert_sql, values)

            pg_count = tgt_conn.execute(
                f"SELECT COUNT(*) FROM {tbl}"
            ).fetchone()[0]
            if pg_count == sqlite_count:
                click.echo(
                    f"  [{idx}/{len(tables)}] {tbl:40s} "
                    f"{sqlite_count:>8d} -> {pg_count:>8d}"
                )
            else:
                click.echo(
                    f"  [{idx}/{len(tables)}] {tbl:40s} "
                    f"{sqlite_count:>8d} -> {pg_count:>8d}  MISMATCH"
                )
                failures.append(tbl)

    finally:
        # Restore FK checks.
        try:
            tgt_conn.execute("SET session_replication_role = 'origin'")
        except Exception:
            pass
        tgt_conn.close()

    if failures:
        click.echo()
        click.echo(f"Row-count mismatches: {', '.join(failures)}")
        raise click.ClickException("Migration finished with errors — see above.")

    click.echo()
    click.echo(f"Migrated {len(tables)} tables ({total_rows} rows) successfully.")
