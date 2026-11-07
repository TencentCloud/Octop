# ADR 003 — Tenant (Organization) Entity and Resource Isolation

**Status:** Proposed
**Date:** 2026-09-16

**Related:** issue #107, [ADR 001](001-single-process-model.md), [ADR 002](002-database-backends.md)

---

## Context

Octop today is effectively single-tenant: there is one control plane, one set of
users, and one global pool of resources (agents, workspaces, connectors,
published experts, knowledge bases). The permission model in
`src/octop/infra/users/permissions.py` distinguishes **role** (`admin` vs `user`)
and **module keys**, but it has no notion of *which tenant a resource belongs to*.

Operators increasingly ask for the next step: running several isolated groups
(teams, business units, or external customers) from one Octop deployment, where
group A cannot see or reach group B's resources. Issue #107 tracks introducing a
first-class tenant / organization entity and enforcing isolation end to end.

The term already exists informally. `tenant_id` appears **23 times across 9
files** (chat turn handling, connectors, the IM gateway WS/CLI channels, and
`infra/gateway/process/processor.py`), but it is a loose, optional field — never
a first-class model, never an enforced filter, and never part of the schema that
other resources join against. This ADR proposes promoting it to a real entity
with enforced scoping, while keeping today's single-tenant deployments
byte-for-byte compatible.

This is a **design proposal** for maintainer alignment. No implementation lands
with this ADR; the migration and query-scoping work follows once the shape below
is agreed.

## Current state (verified against the tree at `main`)

- `src/octop/infra/users/` models users and the `admin` role only — **no tenant
  entity** and no `tenants` table.
- Control-plane persistence goes through `src/octop/infra/db/repos/*` and
  versioned migrations in `src/octop/infra/db/migrations/NNN_*.sql`
  (+ `NNN_*.pg.sql` for PostgreSQL, per ADR 002). Both backends are first-class,
  so any new table/migration must ship for **both** SQLite and PostgreSQL.
- Instance-level toggles live in the `settings` KV store
  (`src/octop/infra/db/repos/settings.py`) — fine for scalars, not for a
  relational entity with referential integrity.
- `tenant_id` is currently read on the gateway/connector/chat paths but is not
  persisted on agents, workspaces, or connectors, and is not used to filter any
  repository query.

## Decision

Introduce a first-class `Tenant` (organization) entity, attach resources to it,
and enforce tenant scoping in the repository layer so that every read/write path
— HTTP, WebSocket, cron, and IM gateway — is isolated. Default single-tenant
deployments are unchanged.

### 1. Tenancy model

```text
tenants
  id             uuid PK
  name           text        -- human label
  slug           text unique -- stable, URL-safe id
  is_platform_default bool   -- exactly one row; owns pre-existing data
  settings       text/json   -- per-tenant overrides (jsonb on PostgreSQL)
  created_at, updated_at
```

- `users.tenant_id` → `tenants.id` (FK, indexed). Existing users are assigned to
  the platform-default tenant during migration, so their effective scope is
  "everything", exactly as today.
- Resources gain `tenant_id` + index: `agents`, `workspaces`, connectors,
  knowledge bases, published experts, cron jobs, and shared resource pools.
- Scope levels are explicit: **platform** (cross-tenant, admin-only),
  **tenant**, **user**. The first cut only needs tenant + user; the platform
  level exists for admin/ops surfaces.

### 2. Tenant context resolution (do not rely on HTTP middleware alone)

| Path | Where the tenant is resolved |
|------|------------------------------|
| HTTP API | FastAPI dependency resolves the caller's `tenant_id` from the authenticated user (server-side), not from a client-supplied header |
| WebSocket | Resolve from the authenticated connection, carry it on the session/context object |
| Cron | Resolve from the job owner's tenant, persisted on the job row |
| IM gateway (`infra/gateway/**`) | Resolve from the bound user/connection, not just the inbound payload |
| Agent tools | Resolve from the owning agent's tenant; never trust model-supplied ids |

**Hard rule:** `tenant_id` is *derived from the authenticated principal or the
resource's owning row* — it is never taken from request bodies, query params,
model output, or loosely-parsed payloads. This is what makes the existing 23
call sites safe rather than a bypass.

### 3. Repository-layer enforcement

- All resource repositories accept/derive a tenant scope and append
  `WHERE tenant_id = ?` to reads and writes by default (mirroring the existing
  `?`-placeholder pattern that `PostgresPool` rewrites to `%s`).
- A repository method that intentionally crosses tenants must opt in explicitly
  (e.g. `list_all_tenants()` used only by admin/ops code), so a missed filter is
  a compile-time-visible decision rather than a silent leak.
- For PostgreSQL, application-level filtering is the baseline. Row-Level
  Security (RLS) is a *possible* defense-in-depth follow-up, not part of this
  first cut (it would not help SQLite and doubles the policy surface).

### 4. Migration and backward compatibility

- Migration seeds exactly one `tenants` row (`is_platform_default = true`) and
  backfills every existing row's `tenant_id` to it.
- `NNN_*.sql` **and** `NNN_*.pg.sql` ship together; the migration is idempotent
  and safe to run on a populated control plane.
- After migration, a single-tenant deployment behaves identically: the default
  tenant owns all data and existing queries resolve to it.
- No SQLite→PostgreSQL data migration is introduced (consistent with ADR 002).

### 5. Isolation tests

- Two tenants, each with agents/workspaces/connectors: neither can list, read,
  mutate, or install from the other's resources (API-level tests for every
  resource type).
- Cross-tenant access attempts return `403` (or `404` where existence itself is
  sensitive), never a partial result.
- Cron and IM-gateway paths resolve the correct tenant (tested through the
  gateway, not only through HTTP).
- Migration test: run on a populated fixture and assert every row is assigned to
  the default tenant and all prior behavior is preserved.

## Consequences

- **Positive:** isolation becomes a property of the data model and repository
  layer, not of each endpoint; the informal `tenant_id` fields are unified under
  one enforced model; it enables later tenant-scoped quotas and RBAC.
- **Cost / risk:** touches the schema, the migration set (both backends), the
  repository layer, and every gateway entry point. Broad surface — hence
  landing it behind the default tenant first, then tightening.
- **Non-goals for the first cut:** per-tenant billing/quota, cross-tenant
  resource sharing, PostgreSQL RLS, and a tenant-admin UI.

## Alternatives considered

1. **Keep `tenant_id` as a loose field and filter opportunistically.** Rejected:
   no referential integrity, and each new endpoint risks forgetting the filter.
2. **Store tenancy purely in the `settings` KV store.** Rejected: needs joins and
   FK integrity; KV is for scalars.
3. **One database per tenant.** Rejected for now: multiplies ops burden and
   conflicts with the single-process model (ADR 001). Revisit only if hard
   physical isolation becomes a requirement.
4. **Enforce only in the API layer via JWT claims.** Rejected: WS, cron, and IM
   gateway paths bypass HTTP middleware, so the enforcement point must be shared.

## Open questions (maintainer alignment)

1. **Naming:** `Tenant`, `Organization`, or reuse `Workspace`? Affects table and
   API naming.
2. **Claim vs resolution:** is `tenant_id` carried in the JWT, or always resolved
   server-side from the user? (This ADR assumes server-side resolution.)
3. **Published experts / market:** stay platform-global, or become tenant-scoped
   with optional cross-tenant sharing?
4. **Sharing model:** is any cross-tenant sharing needed in v1, or is hard
   isolation enough?
5. **First-cut scope:** schema + read filtering only, or schema + full write path
   in one step? This ADR recommends the former, then tightening.
