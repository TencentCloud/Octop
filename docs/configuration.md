# Configuration

Octop stores all of its state under `~/.octop/`. The directory is created
on first server start (or by `octop init` / `octop run`).

## Filesystem layout

```
~/.octop/
├── config.json              # process-level settings (host, port, CORS, DB, TLS, …)
├── octop.db                 # SQLite — users, agents, providers, sessions, audit
├── cli_state.json           # CLI token + pinned defaults (`octop user login`)
├── repl_history             # readline-style history for `octop chats repl`
├── secrets/
│   └── jwt_secret           # 32-byte random; rotate with `octop admin rotate-jwt-secret`
├── agents/<agent_id>/       # per-agent workspace (LangGraph state, attachments, …)
├── plugins/                 # installed third-party plugins
├── ssl/                     # self-signed certs when `octop run --ssl` is used without --cert/--key
├── logs/                    # rotating log files (when `octop service start` writes a logfile)
└── octop.log                # default foreground log path
```

The root can be overridden with `OCTOP_HOME` (absolute path). Most
sub-paths are exposed as properties on `PathLayout` in
`octop.infra.utils.paths`.

## `config.json`

Generated with defaults on first run; merged with environment overrides
on each start. Schema (`OctopConfig` in `octop/config.py`):

```json
{
  "bind_host": "127.0.0.1",
  "port": 8088,
  "log_level": "info",
  "access_token_ttl_seconds": 86400,
  "login_max_attempts": 5,
  "login_lockout_seconds": 900,
  "cors_origins": [],
  "default_timezone": "Asia/Shanghai",
  "enable_dashboard": true,
  "enable_api_docs": false,
  "require_setup_password": true,
  "database": {
    "driver": "sqlite",
    "sqlite_path": "octop.db",
    "host": "127.0.0.1",
    "port": 5432,
    "database": "octop",
    "user": "octop"
  },
  "tls": {
    "enabled": false,
    "mode": "",
    "domains": [],
    "cert_file": "",
    "key_file": "",
    "issued_at": "",
    "expires_at": "",
    "acme_staging": false,
    "http_port": 80
  }
}
```

Notes:

- `default_timezone` is the process default for dashboard timestamps, cron
  scheduling, and harness. Legacy `cron_timezone` in `config.json` and
  `OCTOP_CRON_TIMEZONE` are still accepted; the new key/env wins when both
  are set.
- `database.password`：向导用离散字段配置 PostgreSQL 时**可能**写入
  `config.json`（便于本机首次启动）。生产环境更推荐只用
  `OCTOP_DATABASE_PASSWORD` 或带密码的 `OCTOP_DATABASE_URL`，并限制
  `config.json` 文件权限。环境变量始终覆盖文件中的同名配置。
- `enable_api_docs=false` keeps `/api/docs` (Scalar) off in production
  while still serving `/api/openapi.json` to the dashboard.
- `require_setup_password=true` adds the wizard password gate to the
  first-run setup flow; set `false` for unattended bootstraps via
  `OCTOP_ADMIN_USERNAME` / `OCTOP_ADMIN_PASSWORD`.

## Environment overrides

Each variable, when set, takes precedence over the matching key in
`config.json`. Unset variables leave the on-disk value untouched.

| Variable | Type | Default | Effect |
|----------|------|---------|--------|
| `OCTOP_HOME` | path | `~/.octop` | Install root (DB, secrets, workspaces, plugins) |
| `OCTOP_BIND_HOST` | string | `127.0.0.1` | Listen address (use `0.0.0.0` for LAN access) |
| `OCTOP_PORT` | int | `8088` | Listen port |
| `OCTOP_LOG_LEVEL` | string | `info` | One of `debug` `info` `warning` `error` |
| `OCTOP_ACCESS_TOKEN_TTL` | int (seconds) | `86400` | JWT access-token lifetime |
| `OCTOP_LOGIN_MAX_ATTEMPTS` | int | `5` | Failed-login attempts before lockout |
| `OCTOP_LOGIN_LOCKOUT_SECONDS` | int | `900` | Lockout duration after `OCTOP_LOGIN_MAX_ATTEMPTS` failures |
| `OCTOP_DEFAULT_TIMEZONE` | IANA tz | `Asia/Shanghai` | Default timezone for display, scheduling, and harness (`cron_timezone` / `OCTOP_CRON_TIMEZONE` still accepted) |
| `OCTOP_CORS_ORIGINS` | comma-sep list | empty | Permitted CORS origins for the dashboard / external callers |
| `OCTOP_ENABLE_DASHBOARD` | bool | `true` | Serve the built React SPA at `/` |
| `OCTOP_ENABLE_API_DOCS` | bool | `false` | Expose Scalar API docs at `/api/docs` |
| `OCTOP_REQUIRE_SETUP_PASSWORD` | bool | `true` | Require wizard password during initial setup |
| `OCTOP_DATABASE_URL` | string | empty | Full DSN — overrides the `OCTOP_DATABASE_*` fields below |
| `OCTOP_DATABASE_DRIVER` | `sqlite` \| `postgresql` | `sqlite` | Storage backend |
| `OCTOP_DATABASE_SQLITE_PATH` | path | `octop.db` | SQLite file path (relative to `OCTOP_HOME` unless absolute) |
| `OCTOP_DATABASE_HOST` | string | `127.0.0.1` | PostgreSQL host (when `driver=postgresql`) |
| `OCTOP_DATABASE_PORT` | int | `5432` | PostgreSQL port |
| `OCTOP_DATABASE_NAME` | string | `octop` | PostgreSQL database name |
| `OCTOP_DATABASE_USER` | string | `octop` | PostgreSQL user |
| `OCTOP_DATABASE_PASSWORD` | string | empty | PostgreSQL password (overrides file; prefer env in production) |
| `OCTOP_ADMIN_USERNAME` | string | empty | Pre-fills the first-admin username in `octop init` |
| `OCTOP_ADMIN_PASSWORD` | string | empty | Pre-fills the first-admin password in `octop init` |
| `OCTOP_ADMIN_DISPLAY_NAME` | string | empty | Pre-fills the admin display name |
| `OCTOP_USER` | string | empty | Default `--user` for CLI subcommands |
| `OCTOP_AGENT` | string | empty | Default `--agent` for CLI subcommands |
| `OCTOP_SERVICE_MODE` | `systemd` \| `launchd` | auto | Override the service backend (used by `octop service`) |
| `OCTOP_SERVICE_SCOPE` | `user` \| `system` | auto | systemd `--user` vs system unit (Linux only) |

Invalid integer values are logged and ignored — the on-disk default
remains in effect. `database_env_configured()` returns `True` when any
`OCTOP_DATABASE_*` is set, which lets `OctopServer.start()` pick the
configured backend at boot.

### Agent memory vs control plane

Control-plane `database` and agent memory are separate layers. Defaults:

- Control plane SQLite → agent memory stays `{workspace}/memory.sqlite`.
- Control plane PostgreSQL → agent memory **defaults to the same DSN**
  (harness-memory per-agent PG schema `agent_<id>`). Runtime also needs
  ``langgraph-checkpoint-postgres`` (pulled in via
  ``harness-memory[langgraph-postgres]``) so LangGraph checkpoints work.
  To keep file memory while the control plane is PG, set on the agent:

```json
"memory": { "backend": { "type": "sqlite" } }
```

Or point at another DSN with `"type": "postgres", "dsn": "…"`. There is
no automatic SQLite→PG memory data migration.

PostgreSQL **extensions** (e.g. `vector`) are instance-level ops, not
control-plane migrations. Local compose enables `vector` via
`docker/postgres/init-vector.sql`; managed databases need a DBA /
provider toggle. See [ADR 002](./adr/002-database-backends.md).

## First-boot wizard

The first request to a fresh install lands on the setup page. Greenfield
SQLite installs **defer** opening the control-plane DB until the database
step; password verification works without a pool. The modern flow uses
`/api/setup/*`:

1. `POST /api/setup/begin` (or `POST /api/setup/verify-password` when
   `require_setup_password=true`) — issues a short-lived wizard token.
2. `POST /api/setup/test-database` / `POST /api/setup/database` — choose
   SQLite or PostgreSQL, probe, persist `config.json`, bind pool + migrate.
3. `POST /api/setup/initial-admin` — creates the seed admin (requires DB).
4. `POST /api/setup/test-provider` — pings an optional provider draft.
5. `POST /api/setup/finish` — bootstraps default `main` agent and unlocks
   the rest of the API.

`GET /api/setup/status` returns `setup_required`, wizard password fields,
plus `database_bound` / `database_driver`. `setup_lockdown` middleware
blocks non-setup routes until the wizard completes.

For unattended installs, use `octop init --yes` with
`OCTOP_ADMIN_USERNAME` / `OCTOP_ADMIN_PASSWORD` (and
`OCTOP_REQUIRE_SETUP_PASSWORD=false` if the env-var path is used). This
runs the same migrations + admin creation without the HTTP wizard.

## Secrets

The JWT secret is generated on first start and stored in
`~/.octop/secrets/jwt_secret`. Rotate it with:

```bash
octop admin rotate-jwt-secret
```

Rotation invalidates every outstanding access token immediately. The
old secret is overwritten in place — no zero-downtime rotation today.

Per-agent provider credentials (e.g. API keys) live in the SQLite
`providers` table and are surfaced through
`infra/connectors/credential_crypto.py` for connector OAuth flows.
