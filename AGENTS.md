# AGENTS.md

Short navigation for coding agents. File-scoped checklists live in [`.cursor/rules/`](.cursor/rules/).

## Collaboration

Favor caution over speed; trivial tasks may relax this.

- State assumptions; ask when unsure. If several readings exist, list them — do not pick silently.
- Write the minimum code that solves the problem. No unrequested features, abstractions, or defensive handling for cases that cannot happen.
- Touch only task-related lines. Do not restyle nearby code or delete unrelated dead code. Remove orphans **you** introduced.
- Before saying done, show evidence. Ship bar: **`make all`** green.

## What this is

**Octop** — self-hosted multi-user, multi-agent assistant. One Python wheel: FastAPI + React dashboard + Click CLI. No external queue. No required service beyond an LLM provider.

Python 3.12+, asyncio (blocking I/O only via `run_in_executor`), SQLite (`sqlite3`, WAL) or PostgreSQL (`psycopg`), `octop-harness` (LangGraph), `octop-gateway`, React 18 + Vite. Package manager: **uv** (`uv run pytest`, never bare `pytest`). API docs: Scalar at `/api/docs`.

## Layout

```
src/octop/
  config.py     env config — no infra / api / cli imports
  launch.py     only module that imports both infra.server and api.app
  i18n/         zh + en bundles, tr()
  infra/        domain
  api/          HTTP adapters
  cli/          Click (`commands/`, `support/`, `repl/`)
  dashboard/    built SPA — do not edit
dashboard/      Vite source — edit here
docs/  tests/
```

Dependencies flow inward: CLI and HTTP call domain; domain never calls HTTP or CLI.

| Layer | May import | Must not |
|-------|------------|----------|
| `infra/` | peer infra, `octop.config` | `api/`, `cli/`, `launch.py` |
| `infra/db/repos/` | `db/_base`, `utils/` | other infra domain |
| `infra/utils/` | stdlib, third-party | other infra |
| `api/` | `infra/`, sibling api | `cli/`, `launch.py`; no domain rules |
| `cli/` | `infra/`, `launch.py` | `api/`; do not duplicate domain logic |

Legacy paths are gone: `octop.agents` / `channels` / `db` / `users` / `utils` / `errors` / `server` / `shared` → `octop.infra.*` (metrics: `octop.infra.metrics`). Routers use `server.services`, never a module-level repo import.

## Invariants

Details and examples are in the matching rule under `.cursor/rules/`.

- Workspace **content** goes through `HarnessAgent.workspace` (`BackendWorkspace`). Do not `Path.read_text` agent workspace files or branch on backend type.
- Schema changes are a numbered `.sql` + `.pg.sql` pair. Fold unreleased work into the current unreleased migration.
- User-facing server strings live in `src/octop/i18n/` (`en` and `zh`, same keys). Dashboard chrome lives in `dashboard/src/locales/`.
- Timestamps users see use `config.json` → `default_timezone`, not the browser zone.
- Do not edit `src/octop/dashboard/`. Build it with `make build-frontend`.

## Commands

```bash
make install-hooks          # once: .githooks pre-commit runs make all + dashboard build
make all                    # format-all + lint + typecheck + test
uv run pytest -m "not live" # full suite, no LLM calls
cd dashboard && npx tsc -b  # after UI changes
make build-frontend         # dashboard/ → src/octop/dashboard/
```

Do not skip hooks to land red tests. CI runs on Linux and Windows.

## Where to look

| Question | Location |
|----------|----------|
| Auth | `api/deps.py`, `api/middleware/jwt_auth.py`, `api/routers/auth.py` |
| Boot | `launch.py`, `cli/commands/run.py`, `infra/server.py` |
| Messages | `infra/gateway/processor.py` |
| Agents | `infra/agents/manager.py` |
| Cron | `infra/cron/manager.py` |
| Schema | `infra/db/migrations/`, `infra/db/repos/` |
| Env | `config.py` |
| Frontend API | `dashboard/src/api/request.ts` |
| i18n | `src/octop/i18n/`, `dashboard/src/locales/` |
| Timezone | `default_timezone` in `config.py`; `dashboard/src/hooks/useServerTimezone.ts` |
| Tests | `tests/support/`, `tests/unit/`, `tests/integration/` |
| Release | `CONTRIBUTING.md`, `.cursor/skills/publish` |

## Workflow

1. Read the code and confirm assumptions before editing.
2. Run `make install-hooks` once per clone.
3. Keep the diff minimal. After UI changes, run `make build-frontend`.
4. Verify with `make all`. After i18n JSON edits, run `uv run pytest tests/unit/i18n -q`.
5. Do not commit or push unless asked.

Branch: `feature/*` → `develop` → `release/x.y.z` → `main` (merge commit) → tag `v*` on `main` only. Hotfix from `main`, then into `develop`. Keep `main` an ancestor of `develop`. Do not push `develop` onto `main`.

## Communication

Default to Chinese. Cite code as `` `path:line` ``. Lead with the conclusion, then the verification command and result.
