# ADR 002 — Dual Database Backends (SQLite | PostgreSQL)

**Status:** Accepted  
**Date:** 2026-07-20  

**Related:** [spec](../superpowers/specs/2026-07-20-postgresql-dual-backend-design.md), [plan](../superpowers/plans/2026-07-20-postgresql-dual-backend.md)

---

## Context

Operators need an optional PostgreSQL control plane for compliance / externalized state, while keeping zero-friction SQLite as the default. Agent memory (harness-memory) already supports a postgres backend; Octop must be able to pass it through without forking harness-*.

## Decision

### Three storage layers (do not conflate)

```text
Layer 1 — Octop control plane
  users / agents / channels / cron / settings / secrets
  → SQLite file  OR  PostgreSQL (psycopg3 pool 1–8)
  → Setup wizard: greenfield defers open until database step; first bind
    (hot rebind only if swapping while user_count == 0)

Layer 2 — Harness checkpoints
  default: {workspace}/checkpoints.sqlite
  when memory is postgres: reuse Memory / PostgresSaver (harness-agent)

Layer 3 — Agent memory (harness-memory)
  default on SQLite control plane: {workspace}/memory.sqlite
  default on PostgreSQL control plane: same DSN, schema agent_<id>
  override: config_json.memory.backend = { type: "sqlite" }
            or { type: "postgres", dsn } / { use_control_plane_dsn: true }
  → not merged into control-plane migrations
```

Workspace content files (SOUL, skills, inbound, JSONL) remain files via `BackendWorkspace`.

### Control-plane adapter

- Repos keep `?` placeholders; `PostgresPool` rewrites to `%s` at the boundary.
- Parallel migrations: `NNN_*.sql` (SQLite) and `NNN_*.pg.sql` (PostgreSQL).
- Sync pool from async (same pattern as today). Optional `asyncio.to_thread` helpers are **out of scope** (follow-up “1b”).
- Single active Octop writer; no multi-instance write promise.
- Greenfield only — no SQLite→PG data migrator.
- Backup: SQLite file snapshot vs `pg_dump -Fc`; manifest carries `database_driver` + `database_dump_format`; refuse cross-engine restore.
- Default dependency includes `psycopg[binary]`. Live PG tests are gated by `@pytest.mark.postgresql` + `OCTOP_TEST_DATABASE_URL`.
- Hot rebind during empty setup: `rebind_control_plane` opens the new pool, then `AppRuntime.replace_services` retargets singletons via each component’s public `replace_*` API (db layer does not poke runtime private fields).

### Where initialization SQL lives (do not conflate)

| Concern | Owner | Location |
|---------|--------|----------|
| Control-plane tables / indexes | Octop migrate | `migrations/NNN_*.sql` and `NNN_*.pg.sql` |
| Connection / session settings | Pool connect | SQLite: `PRAGMA` in `SqlitePool`; PG: defaults (FK on) — **not** in migrations |
| Instance extensions (`vector`, …) | Ops / docker | `docker/postgres/init-vector.sql` via `initdb.d`, or DBA on managed PG |
| Agent memory DDL | harness-memory | Runtime `_init_schema` per `agent_*` schema |

**Hard rule:** Octop control-plane `*.pg.sql` must **not** run `CREATE EXTENSION`. Many managed Postgres roles cannot create extensions; the control plane also does not need `vector` (plain types only). harness-memory today uses built-in `tsvector`, not pgvector. Keep `CREATE EXTENSION vector` in docker/ops for optional future embedding use.

### Memory wiring

Octop passes `memory_backend` into `HarnessAgentConfig` and opens dashboard Memory with the same spec. Portable pack/adopt for postgres is refused (use `pg_dump` on the memory schema).

## Consequences

- `DatabasePool` Protocol; `open_database()` returns SQLite or PG.
- Setup first step must succeed before admin creation when operators choose PG.
- Operators may colocate control plane + memory on one Postgres (separate schemas) or split DSNs.
- ADR 001’s “one process” model is unchanged; PG is an optional backing store, not a second Octop instance.
