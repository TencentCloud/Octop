# AGENTS.md

Navigation guide for AI coding agents working in this repository.

## 1. Collaboration principles

> Favor caution over speed; trivial tasks may relax these rules. These principles complement [§10 Change workflow](#10-change-workflow) and [§11 Communication](#11-communication).

### Think before writing

- State assumptions up front; ask when unsure — do not guess.
- When multiple interpretations exist, list them and let the user choose — do not pick silently.
- Suggest simpler approaches when they exist; push back when appropriate.
- Stop when blocked; name exactly what is unclear.

### Simplicity first

- Write the minimum code that solves the problem; no unrequested features, abstractions, or config knobs.
- Do not add defensive error handling for scenarios that cannot realistically happen.
- Trim the diff when it grows unnecessarily large.

### Surgical edits

- Touch only lines directly related to the task; do not opportunistically "clean up" nearby code, comments, or formatting.
- Do not refactor working code or unify style just because it differs from yours.
- Unrelated dead code: mention it, do not delete it proactively.
- Remove orphan imports, variables, and functions **you** introduced.

### Verifiable outcomes

- Turn tasks into verifiable goals (what to test, which command proves success).
- For multi-step work, sketch a short plan: `step → verify: …`
- Before saying "done", provide verification evidence; the default ship bar is **`make all` green** (see [§6 Run commands](#6-run-commands), [§10 Change workflow](#10-change-workflow)).

## 2. What this is

**Octop** — self-hosted AI assistant platform (multi-user, multi-agent).
One Python wheel: FastAPI backend + React dashboard + Click CLI.
No external queue. No required services beyond an LLM provider.

## 3. Tech stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.11+ |
| Web framework | FastAPI + uvicorn |
| Async runtime | asyncio (no threads except `run_in_executor`) |
| Database | SQLite via `aiosqlite` (WAL mode) |
| LLM runtime | `harness-agent` (LangGraph) at `/workspace/harness-agent` |
| Gateway | `harness-gateway` at `/workspace/harness-gateway` |
| Frontend | React 18 + TypeScript + Vite |
| Package manager | uv — always `uv run pytest`, never bare `pytest` |
| API docs UI | Scalar (`scalar-fastapi`) at `/api/docs` |

## 4. Package layout

High-level tree — see [§5 Module boundaries](#5-module-boundaries) for what each folder owns and what it may import.

```
Octop (`octop/` workspace directory)     Python package root (`src/octop/`)
  config.py
  launch.py                   composition root: OctopServer + FastAPI + uvicorn
  i18n/                       locale JSON bundles + tr() + domain helpers
  infra/                      domain core (agents, DB, gateway, …)
  api/                        HTTP adapters (FastAPI)
  cli/                        Click commands
  dashboard/                  built SPA artifact — do NOT edit

dashboard/                    frontend source (Vite) — edit here
docs/                         human-written reference (e.g. `api.md`)
tests/                        pytest (`unit/`, `integration/`)
```

## 5. Module boundaries

**Rule of thumb:** dependencies flow **inward** — transport layers call domain; domain never calls HTTP/CLI. Within `infra/`, leaf modules (`utils/`, `db/repos/`, `errors.py`) stay free of higher-level orchestration.

### Layer overview

```
dashboard/ ──HTTP──► api/ ──► infra/ ──► infra/utils/, octop.config
cli/ ──► launch.py ──► api/ + infra/
```

| Layer | Role | May import | Must NOT import |
|-------|------|------------|-----------------|
| `octop.config` | Env-based `OctopConfig` | stdlib, pydantic | `infra/`, `api/`, `cli/`, `launch.py` |
| `octop.i18n` | Locale JSON + `tr()` + per-namespace helpers | `infra/utils/locale`, stdlib | `api/`, `cli/`, `dashboard/` |
| `octop.launch` | Wire `OctopServer`, `build_app`, uvicorn for `octop run` | `infra/`, `api/` | business logic; must not be imported by `infra/` |
| `infra/utils/` | Pure helpers (paths, ulid, env files, Ollama) | stdlib, third-party | any other `infra/*` domain code |
| `infra/db/repos/` | One repo per table — SQL only | `infra/db/_base`, `infra/utils/` | `agents/`, `gateway/`, `api/`, orchestration |
| `infra/` (domain) | Business logic & orchestration | `infra/utils/`, `infra/db/`, `octop.config`, peer `infra/*` subpackages, `infra/errors`, `infra/metrics` | `api/`, `cli/`, `launch.py`, `dashboard/` |
| `api/` | HTTP: routing, auth, SSE, OpenAPI | `infra/`, `octop.config`, sibling `api/*` | `cli/`, `launch.py`; no business rules that belong in `infra/` |
| `cli/` | Terminal UX | `infra/`, `octop.config`, `launch.py`, sibling `cli/*` | `api/`; domain logic duplicated from `infra/` |
| `dashboard/` | React UI | `dashboard/src/api` → backend over HTTP | Python packages; no direct DB or `infra/` access |

**Hard bans**

- `infra/` → `api/`, `cli/`, or `launch.py`.
- `api/` → `cli/` or `launch.py`.
- `cli/` → `api/` (use `launch.py` for `octop run` instead).
- `infra/db/repos/` → any non-DB `infra` package.
- `infra/utils/` → any non-utils `infra` package.
- Routers/helpers in `api/routers/` must stay thin: validate HTTP, call `infra/`, map errors — not new domain rules.

### `infra/` subpackages

| Path | Owns | Typical importers |
|------|------|-------------------|
| `infra/agents/` | Agent registry (`manager.py`), harness runtime, provider store (`providers/`), settings stores (`security/`, `acp_settings`, `langfuse`), MBTI personas, expert catalog (`experts/`) | `server.py`, `gateway/`, `api/routers/agents.py` |
| `infra/backend/` | Workspace storage adapter, resolver, remote probe (COS/S3/…) | `agents/`, `api/routers/workspace*.py` |
| `infra/connectors/` | Connector catalog, OAuth, MCP gateway, credential crypto | `api/routers/connectors.py`, `internal_mcp.py`, `agents/manager.py` (MCP assembly) |
| `infra/cron/` | Cron jobs, triggers, agent tool hooks | `server.py`, `api/routers/cron.py` |
| `infra/db/` | `DBPool`, migrations, `RepoBundle` / `SharedServices` in `services.py` | all domain code needing persistence |
| `infra/gateway/` | IM ingress (`processor.py`), threads, slash commands (`slash/`), bot setup (`bot_creators/`) | `server.py`, `api/routers/chat.py`, `channels.py` |
| `infra/setup/` | First-run wizard, system service install, TLS / Let's Encrypt | `server.py`, `launch.py`, `api/routers/setup.py`, `api/routers/tls.py` |
| `infra/users/` | Users, roles, password hashing, `UserManager` | `server.py`, `api/routers/auth.py`, `users.py` |
| `infra/errors.py` | `OctopError`, `ErrorCode` — shared exception types | everywhere in `infra/` and `api/` |
| `infra/metrics.py` | In-process counters (`METRICS`) | lazy-import inside hot paths |
| `infra/server.py` | `OctopServer.start()` — wires infra singletons | `launch.py`, `api/app.py` |

### `launch.py`

| Path | Owns | Must NOT |
|------|------|----------|
| `launch.py` | `run_foreground` / `run_foreground_blocking` — boot `OctopServer`, serve via uvicorn + `build_app`, clean shutdown | HTTP routes, SQL, CLI argument parsing |

Only `launch.py` may import both `infra/server` and `api/app` in the same module.

### `api/` layout

| Path | Owns | Must NOT own |
|------|------|--------------|
| `api/app.py` | FastAPI factory, router registration, static dashboard mount | domain rules, SQL |
| `api/deps.py`, `api/jwt_tokens.py` | JWT extraction, `current_user`, `get_server` | agent lifecycle, cron logic |
| `api/middleware/` | JWT gate, setup lockdown | business validation beyond auth/setup |
| `api/openapi_meta.py` | Scalar tags, API intro text | route handlers |
| `api/errors.py` | Map `OctopError` → HTTP status + JSON | new error semantics (add to `infra/errors.py`) |
| `api/routers/` | One resource per module; Pydantic request/response models | persistence, harness calls — delegate to `infra/` |
| `api/routers/browser/` | Browser session/stream/harness HTTP surface | Playwright logic (stays in harness or helpers here only as glue) |

### `cli/` layout

| Path | Owns |
|------|------|
| `cli/main.py` | Click entry, command registration |
| `cli/*_cmd.py` | User-facing subcommands |
| `cli/support/db.py` | Offline DB (`open_cli_services`) |
| `cli/support/offline_ops.py` | Local CRUD via repos (thin wrappers) |
| `cli/support/embedded_ops.py` | Short-lived `OctopServer` for runtime ops |
| `cli/support/acting.py` | Resolve `--user` / pinned defaults / agent owner |
| `cli/support/ctx.py` | Root `--user` / `--agent` / `--json` resolution |
| `cli/support/state.py` | Pinned `default_user` / `default_agent` in `cli_state.json` |
| `cli/run_cmd.py` | `octop run` — delegates to `launch.run_foreground_blocking` |
| `cli/init_cmd.py`, `cli/backup_cmd.py` | Local DB bootstrap / backup via `infra/db` |

**CLI transport layers** (pick one per command; domain rules live in `infra/`, not duplicated in `cli/`):

| Layer | When | Examples |
|-------|------|----------|
| **Offline** | Read/write local `~/.octop` SQLite only | `user *`, `provider *`, `cron` list/create/delete, `agent list/delete`, `chats` CRUD, `models` presets/list/active, `channel` CRUD, `admin`, `skills` enable/disable |
| **Embedded** | Needs harness/gateway runtime; boots in-process `OctopServer` | `chats send/repl`, `chats get` (history), `cron run-now`, `agent` create/start/stop/reload, `provider test`, `channel test`, `skills list`, `acp` |
| **External** | Talks to OS/daemon directly, no Octop HTTP | `models ollama-*`, channel QR bind (WeCom/WeChat), Feishu bot-creator subprocess |

No `octop user login` — CLI trusts local filesystem access to `~/.octop`. Pin acting user with `octop config set-user` or root `--user`; pin agent with `octop agent use` or root `--agent`. If `octop run` is already running, config CLI writes take effect after server restart (cron, channels loaded at boot).

### `dashboard/src/` layout

| Path | Owns | Must NOT |
|------|------|----------|
| `api/` | Typed fetch wrappers (`request.ts`, `modules/*`) | UI components, page state |
| `pages/` | Route-level screens and page-local hooks | generic reusable widgets (move to `components/`) |
| `components/` | Shared UI building blocks | direct `fetch` (use `api/` modules) |
| `hooks/` | Reusable React hooks | page-specific one-off logic |
| `context/` | App-wide React context (agent, auth, …) | API calls without going through `api/` |
| `layouts/`, `routes/` | Shell, sidebar, route table | business logic |
| `locales/` | i18n strings | — |
| `utils/` | Frontend pure helpers | API or server knowledge |

Frontend talks to Octop **only** via `/api` HTTP — never import or assume Python module layout.

## 6. Run commands

```bash
uv run pytest -m "not live"            # full test suite (no LLM calls)
uv run pytest tests/unit -x -q        # unit tests only, stop on first fail
uv run pytest tests/integration -x -q # integration tests only
make lint                               # ruff check + format check
make typecheck                          # mypy --strict src/octop
make format                             # auto-fix lint issues
make all                                # lint + typecheck + test (ship bar)
cd dashboard && npx tsc --noEmit       # frontend typecheck (after UI changes)
make build-frontend                     # dashboard/ → src/octop/dashboard/
```

## 7. Key patterns

**DI:** Routers receive `server: OctopServer = Depends(get_server)`; core services live on `server.services` (`SharedServices` from `infra/db/services.py`). Never import repos at module level outside `SharedServices` / `RepoBundle`.

**Agent scope:** Most agent routes use `/api/agents/{agent_id}/…` in the URL. A few legacy endpoints (e.g. MBTI) still take `X-Octop-Agent-Id`. Always validate ownership: load the agent row → `_assert_agent_owner(row, user)` (or admin bypass).

**Agent workspace I/O:** All reads/writes of agent workspace **content files** go through `HarnessAgent.workspace` (`BackendWorkspace` from `harness-agent`). Do **not** use `agent.backend` directly, `resolve_harness_backend`, or `Path.write_text` / `read_text` on `~/.octop/agents/<id>/` for workspace content. Do **not** branch on backend type or `virtual_mode` in Octop — path rules live in `BackendWorkspace`.

| Context | Entry |
|---------|--------|
| HTTP (agent must be running) | `require_running_workspace()` in `api/common/workspace.py` |
| Gateway / IM / media | `harness_workspace_for_agent()` in `infra/gateway/process/agent_resolve.py` |
| Agent startup seed (SOUL, expert, plugins) | `agent.workspace` after `_start_agent` |

**Path conventions:** Pass workspace-relative paths to `BackendWorkspace` (`SOUL.md`, `skills/foo/SKILL.md`). Directory listing defaults to `"."` (current workspace directory). `"/"` is a distinct backend-root path inside `BackendWorkspace` — do **not** conflate it with `"."` there. The dashboard may send leading-`/` paths; HTTP adapters normalize those in `workspace_api_path()` before calling `BackendWorkspace`.

**Chat attachments:** Dashboard uploads go to `{workspace}/inbound/` via `api/common/attachments.py` + `api/routers/uploads.py`, not a separate `~/.octop/uploads/` store.

**Database:** Add columns via a new numbered migration (`infra/db/migrations/00N_description.sql`), then bump the version assertion in `tests/unit/db/test_db_pool.py` (currently `v == 1`).

**Slash commands:** `infra/gateway/slash/dispatcher.py` routes; `handlers/` implements; catalog in `catalog.py`.

**Internationalization (i18n):** Supported locales are **`zh`** and **`en`** (`en` is the fallback). User-facing text produced by the **server** (slash replies, IM/channel status, API error messages, tool display names, CLI output) must come from backend bundles — not hard-coded English in `infra/` when the string is shown to end users.

Backend layout (`src/octop/i18n/`):

```
i18n/
  loader.py            load JSON, lookup(), tr() — dot-path resolve + format
  en.json, zh.json     canonical bundles; keep key trees identical across locales
  domains/             one module per top-level JSON namespace
    errors.py          errors.* → error_message()
    tools.py           tools.* → tool_display_name(), all_tool_labels()
    channel.py         channel.* → channel_tool_hint_start/end()
    slash.py           slash.* → tr() with short keys, field_label, localized_rows
```

**Lookup rules**

- Use full paths with `from octop.i18n import tr`, e.g. `tr("slash.catalog.help.label", locale)`.
- Prefer `octop.i18n.domains.<ns>` (or re-exports on `octop.i18n`) for repeated namespaces — e.g. `tool_display_name()`, `error_message()`.
- Slash handlers use `from octop.i18n.domains.slash import tr` (short keys like `"help.title"`).
- Interpolation uses Python `str.format` placeholders (`{name}`, `{tool_name}`).

**Locale resolution** (`infra/utils/locale.py`): stored user preference wins, then `Accept-Language` (dashboard sends this on API calls), then channel-type hints (IM platforms default `zh`, `telegram` → `en`). Use `resolve_user_locale()` in gateway/IM paths; `resolve_request_locale()` in HTTP handlers.

**API errors:** `ErrorCode` values map to `errors.<CODE>` in JSON. `OctopError.to_envelope(locale=…)` and the global exception handler localize `message`. Dashboard mirrors codes under `apiErrors.*` in `dashboard/src/locales/{en,zh}.json` — tests require backend and frontend keys to match.

**IM channels:** Tool names and hint lines must be localized in `stream_project.py` — pass localized `tool_name` and pre-formatted `tool_hint_text` on `MessageEvent.tool_start/end` (harness-gateway reads `tool_hint_text` when present). Do not rely on English `ChannelConstraints.tool_hint_template` alone.

**Frontend split**

- **Dashboard chrome** (nav, forms, buttons): `dashboard/src/locales/{en,zh}.json` via i18next.
- **Server-owned copy** (tools, apiErrors): canonical in `src/octop/i18n/*.json`; dashboard keeps copies synced (see `tests/unit/i18n/`) and may hydrate tools from `GET /api/i18n/tools`.

**Adding strings (checklist)**

1. Add the same key to `en.json` and `zh.json` under the right namespace (`slash`, `errors`, `tools`, `channel`, …).
2. Add or extend a `domains/*.py` helper when the namespace is used in multiple call sites.
3. If the key is an `ErrorCode` or `apiErrors` entry, update both backend `errors` and dashboard `apiErrors`.
4. Run `uv run pytest tests/unit/i18n -q` (key parity + domain helpers).

Do **not** use gettext (`.po` files). Do **not** embed user-visible English in `infra/` when a backend i18n key exists. Expert catalog (`infra/agents/experts/`) still uses embedded `label_zh`/`label_en` in source data — out of scope unless explicitly migrating that catalog.

**Timezone (config.json):**

User-facing datetime display and cron/scheduling defaults MUST use the server timezone from `config.json` → `default_timezone` (env override `OCTOP_DEFAULT_TIMEZONE`; legacy `cron_timezone` / `OCTOP_CRON_TIMEZONE` still accepted) — not the browser's local timezone.

| Layer | Entry |
|-------|--------|
| Config | `OctopConfig.default_timezone` in `config.py` |
| API | `GET /api/settings/timezone` → `{ "timezone": "…" }` (`GET /api/cron/settings` remains a compat alias) |
| Dashboard | `useServerTimezone()`; format with `formatServerDateTime` / `formatServerIsoDateTime` / `formatMessageTime(..., timeZone)` in `dashboard/src/utils/formatMessageTime.ts` |

**Do not** use bare `toLocaleString()` / `toLocaleDateString()` / `toLocaleTimeString()` for timestamps users see without passing the server `timeZone`. Number grouping via `Number#toLocaleString()` (e.g. download counts) is fine.

**Language:** Keep the existing locale resolution (user preference → `Accept-Language` / dashboard i18n → channel hints → `DEFAULT_LOCALE`). Language is **not** a `config.json` key — do not add one unless explicitly requested.

**Workspace storage:** `infra/backend/resolver.py` resolves harness `BackendProtocol` from agent config; remote backends use `probe.py` for fast tree listing.

**Connectors:** `infra/connectors/` — catalog, OAuth registry, MCP gateway; HTTP surface in `api/routers/connectors.py`.

**Metrics:** `from octop.infra.metrics import METRICS` — lazy-import inside functions to avoid circular imports.

**API docs:** Interactive docs live at `/api/docs` (Scalar, backed by `/api/openapi.json`). When adding or changing API routes, keep the generated docs readable for humans:

- Use existing `tags` from `api/openapi_meta.py`; add a tag description there when introducing a new group.
- Give every route a short `summary`; use `description` for non-obvious behavior (auth, streaming, side effects).
- Prefer typed `response_model` and Pydantic request bodies over raw `dict`.
- Document non-obvious fields with `Field(..., description="…")`; name models clearly.
- Spot-check `/api/docs` after API changes — a route that renders as an empty card or untyped blob is unfinished.

**Cross-platform tests:** Octop CI runs on both Linux and Windows, so tests must not assume a single platform:

- Guard POSIX-only behavior with the repo convention `@pytest.mark.skipif(os.name != "posix", reason="…")`; prefer a module-level `posix_only = pytest.mark.skipif(os.name != "posix", reason="…")` alias.
- Do not hard-code POSIX paths (`/`, `/proc`, `/etc`, `/root`, `~` → HOME) in assertions that run on every platform — they resolve differently on Windows (e.g. `/` → `D:\`).
- Prefer `tmp_path` / `tmp_path_factory` and `pathlib` over OS-specific literals; use `Path.as_posix()` / `os.sep` when path string formatting matters.
- When a feature's semantics are inherently POSIX-only (e.g. the host root_dir denied prefixes in `infra/utils/host_dirs.py`), keep the source guards (`os.name != "posix"` short-circuit) and mirror them in the tests.

## 8. Do not

Boundary rules are in [§5](#5-module-boundaries). Additionally:

- Do not import legacy top-level modules — use current paths:
  - `octop.agents.*` → `octop.infra.agents.*`
  - `octop.channels.*` → `octop.infra.gateway.*`
  - `octop.db.*` → `octop.infra.db.*`
  - `octop.users.*` → `octop.infra.users.*`
  - `octop.utils.*` → `octop.infra.utils.*` (or `octop.infra.metrics` for metrics)
  - `octop.errors` / `octop.server` / `octop.shared` → `octop.infra.errors` / `octop.infra.server` / `octop.infra.db.services`
- Do not import `api/` from `infra/` or `cli/` — use `launch.py` to wire HTTP serving.
- Do not put domain logic in `api/routers/` or `cli/*_cmd.py` when it belongs in `infra/`.
- Do not import `infra/db/repos/*` from routers — use `server.services.*_repo` via `infra/` services or managers.
- Do not write bare `pytest` — always `uv run pytest`.
- Do not edit `src/octop/dashboard/` directly — build artifact; source is `dashboard/`.
- Do not add blocking I/O in async functions — use `run_in_executor`.

## 9. Where to look

| Question | Location |
|----------|----------|
| How does auth work? | `api/jwt_tokens.py`, `api/deps.py`, `api/middleware/jwt_auth.py`, `api/routers/auth.py` |
| Setup wizard (password file, tokens) | `infra/setup/`, `api/routers/setup.py` |
| TLS / Let's Encrypt | `infra/setup/tls/`, `api/routers/tls.py` |
| `octop run` boot sequence | `launch.py`, `cli/run_cmd.py` |
| How is a message processed? | `infra/gateway/processor.py` → harness agent |
| How are agents started/stopped? | `infra/agents/manager.py`, `infra/agents/runtime.py` |
| How does cron work? | `infra/cron/manager.py`, `infra/cron/job.py` |
| What DB tables exist? | `infra/db/migrations/` + `infra/db/repos/` |
| What env vars are supported? | `config.py` |
| How does the frontend call the API? | `dashboard/src/api/request.ts` |
| Internationalization (backend) | `src/octop/i18n/`, `infra/utils/locale.py`, `api/routers/i18n.py` |
| Internationalization (dashboard) | `dashboard/src/locales/`, `dashboard/src/i18n.ts`, `dashboard/src/utils/apiError.ts` |
| Server timezone (config.json) | `default_timezone` in `config.py`; `GET /api/settings/timezone`; `dashboard/src/hooks/useServerTimezone.ts`; `dashboard/src/utils/formatMessageTime.ts` |
| Test layout & shared helpers | `tests/support/` (`fakes`, `auth`, `http`, `scenarios`, `app`), `tests/integration/conftest.py`, `tests/unit/{db,cron,gateway,agents,api,cli}/` |
| What is a Thread? | `infra/gateway/threads.py`, `infra/db/repos/threads.py` |
| Workspace backend resolution | `infra/backend/resolver.py`, `infra/backend/adapter.py` |
| Connectors & OAuth | `infra/connectors/`, `api/routers/connectors.py` |
| OpenAPI tags and API intro | `api/openapi_meta.py` |
| Human-readable API reference | `docs/api.md` |
| SharedServices / RepoBundle | `infra/db/services.py` |

## 10. Change workflow

1. **Clarify scope** — read relevant code/docs; confirm assumptions and ambiguities with the user (see [§1](#1-collaboration-principles)).
2. **Minimal implementation** — change only task-related files; dashboard source is in `dashboard/`, build output in `src/octop/dashboard/` (run `make build-frontend` after UI changes).
3. **Verify** — backend: `make all` (`lint` + `typecheck` + `test`). After `dashboard/` changes, also run `cd dashboard && npx tsc --noEmit` (and `npm run lint` when appropriate). After API route changes, glance at `/api/docs` for readable summaries and schemas. After i18n JSON changes, run `uv run pytest tests/unit/i18n -q`.
4. **Wrap up** — remove orphan symbols introduced in this change; do not commit or push unless asked.

## 11. Communication

- Default to **Chinese** when talking to the user; cite code with `` `path:line` ``.
- Lead with the conclusion, then details; write complete sentences, not telegraphic fragments.
- When marking work done, include verification commands and results (or explain why they were not run).
- Do not pile on unrelated follow-ups; mention out-of-scope issues briefly, do not expand scope unilaterally.
