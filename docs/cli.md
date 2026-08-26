# CLI Reference

`octop` is a single Click app installed as `octop` on `pip install octop`.
It is registered in `src/octop/cli/main.py`; commands are loaded
lazily from `src/octop/cli/registry.py`.

```
$ octop --help
Usage: octop [OPTIONS] COMMAND [ARGS]...

  Octop command-line interface.

Options:
  -v, --version           Show the installed octop version.
  --user TEXT             Default --user for subcommands (admin acting on behalf
                          of a user). [env: OCTOP_USER]
  --agent TEXT            Default --agent for subcommands. [env: OCTOP_AGENT]
  --json                  Emit machine-readable JSON for list-style commands.
  -h, --help              Show this message and exit.

Commands:
  acp        Run Octop agent as ACP server (stdio).
  admin      Admin commands.
  agent      Agent lifecycle commands.
  backup     Export and restore Octop backups.
  chat       [deprecated] Alias for `octop chats`.
  chats      Chat REPL and session management.
  channel    Channel management commands.
  clean      Remove CLI state or wipe all of ~/.octop.
  completion Shell completion utilities.
  config     CLI state (base URL, defaults).
  cron       Cron job management commands.
  init       Bootstrap an Octop server install.
  models     Model catalog and active-model settings.
  plugin     Install and manage plugins.
  provider   Provider management (admin write).
  run        Run octop-server in the foreground.
  service    System service lifecycle (start/stop/restart/status).
  skills     Per-agent skill enable/disable.
  update     Check for and install a newer Octop release.
  user       User management commands.
  version    Show the installed octop version.
```

> **Tip.** Regenerate the per-subcommand listings below with
> `make docs-cli` (each `octop <cmd> --help` is captured to stdout).

## Global options

| Option | Env | Effect |
|--------|-----|--------|
| `--user NAME` | `OCTOP_USER` | Default `--user` for subcommands (admin acting on behalf of a user) |
| `--agent ID` | `OCTOP_AGENT` | Default `--agent` for subcommands |
| `--json` | — | Emit machine-readable JSON for list-style commands |
| `-v, --version` | — | Print version and exit |

## Transport layers

Octop commands pick one of three transports:

| Layer | When | Login? | Examples |
|-------|------|--------|----------|
| **Offline** (local DB only) | Need to read/write `~/.octop` without a running server | No | `init`, `backup`, `plugin`, `agent list`, `chats list/get/create/update/delete`, `cron list`, `user *`, `admin overview/audit`, `models presets/list/active` |
| **Attach** (HTTP / WS) | Need a live `octop run` process (IM, streams, model pulls) | Yes (`octop user login`) | `chats send/repl`, `channel test/probe`, `models ollama-*`, `skills enable/disable`, `provider test` |
| **Embedded** (in-process) | CLI boots `OctopServer` for a single command | No | `octop acp`, `octop chats repl`, `octop chats send` (defaults to embedded), `octop agent create/from-expert/start/stop/reload` |

The dashboards and HTTP callers manage their own JWTs and do **not**
share `~/.octop/cli_state.json`.

## `octop init`

Bootstrap a fresh install (DB migrations, JWT secret, first admin).
Idempotent on the DB; pass `--force` to wipe `~/.octop` first.

```
Usage: octop init [OPTIONS]

  Bootstrap an Octop server (~/.octop dir, DB migrations, JWT secret, first admin).

Options:
  --admin-username TEXT       [env: OCTOP_ADMIN_USERNAME]
  --admin-password TEXT       [env: OCTOP_ADMIN_PASSWORD]
  --admin-display-name TEXT   [env: OCTOP_ADMIN_DISPLAY_NAME]
  --force                     Wipe existing ~/.octop contents before bootstrapping.
  --yes                       Skip all interactive prompts.
  -h, --help                  Show this message and exit.
```

## `octop run`

Start the FastAPI app in the foreground (delegates to
`octop.launch.run_foreground_blocking`).

```
Usage: octop run [OPTIONS]

  Start the Octop server (foreground; uvicorn).

Options:
  --host TEXT                 Override OCTOP_BIND_HOST.
  --port INTEGER              Override OCTOP_PORT.
  --reload / --no-reload      Enable uvicorn auto-reload (dev only).
  --ssl / --no-ssl            Enable HTTPS with a self-signed cert (or a real one).
  --certfile PATH             TLS certificate (PEM).
  --keyfile PATH              TLS private key (PEM).
  --log-level [debug|info|warning|error]
  -h, --help                  Show this message and exit.
```

## `octop service`

Install and manage the Octop system service. The backend is detected
automatically (systemd on Linux, launchd on macOS); the scope
(`user` vs `system`) can be forced via `--scope` or
`OCTOP_SERVICE_SCOPE`.

```
Usage: octop service [OPTIONS] COMMAND [ARGS]...

  Manage the Octop system service (systemd on Linux, launchd on macOS).

Commands:
  start     Install (if missing) and start the service.
  stop      Stop the service.
  restart   Restart the service.
  status    Print whether the service is installed / running / healthy.
```

`status` probes the HTTP health endpoint and prints journal/log hints
on failure.

## `octop user`

Local-DB user management. `login` requires a running server; the
rest are offline.

```
Usage: octop user [OPTIONS] COMMAND [ARGS]...

  User management commands (local DB; no server login required).

Commands:
  create    Create a new user.
  list      List all users.
  passwd    Reset a user's password (admin).
  role      Set a user's role.
  disable   Disable a user.
  delete    Delete a user.
  login     Login against a running server; stores JWT for optional remote HTTP attach.
```

## `octop agent`

Lifecycle and templates. Most commands boot an embedded
`OctopServer` to operate on the local DB without a remote round-trip.

```
Usage: octop agent [OPTIONS] COMMAND [ARGS]...

  Agent lifecycle commands.

Commands:
  create        Create a new agent.
  from-expert   Create an agent from a bundled expert template.
  list          List agents.
  use           Pin this agent as the default for subsequent commands.
  start         Start the agent runtime.
  stop          Stop the agent runtime.
  reload        Reload the agent runtime.
  delete        Delete the agent row (and runtime).
  experts       List bundled expert templates.
```

`create` and `from-expert` accept `--user` (admin only) to create
agents on behalf of another user. `use` writes the agent id into
`~/.octop/cli_state.json` so subsequent commands default to it.

## `octop chats`

Thread CRUD + interactive REPL. The REPL and `send` use an embedded
server (no separate `octop run` needed); `list` / `get` / `create` /
`update` / `delete` work fully offline against `~/.octop/octop.db`.

```
Usage: octop chats [OPTIONS] COMMAND [ARGS]...

  Thread list/history and interactive chat (CLI channel / local DB).

Commands:
  list        List conversation threads for an agent.
  get         Show message history for a thread.
  create      Start a new thread (/new equivalent).
  update      Rename or pin a thread.
  delete      Delete a thread.
  send        Send one message and stream the response.
  repl        Interactive chat REPL (embedded server + CLI gateway channel).
```

`octop chat` is a deprecated alias that prints a stderr warning and
forwards to `chats`.

## `octop channel`

Local DB channel CRUD plus platform-specific bot creators. The
`wecom` / `weixin` / `feishu-setup` subcommands drive the QR-code
bot-creator flows; `config` is the offline config editor.

```
Usage: octop channel [OPTIONS] COMMAND [ARGS]...

  Channel management commands.

Commands:
  list          List channels for an agent.
  get           Show one channel row.
  create        Create a channel.
  patch         Update a channel.
  delete        Delete a channel.
  test          Test a channel (instantiate → start → stop).
  config        Edit channel config offline.
  feishu-setup  Drive the Feishu bot-creator flow.
  bind          Bind-group helper for WeCom / Weixin (QR login, etc.).
```

## `octop cron`

Local DB cron management. `run-now` requires a running `octop run`
because the actual fire is dispatched through the live
`CronManager`.

```
Usage: octop cron [OPTIONS] COMMAND [ARGS]...

  Cron job management commands.

Commands:
  list        List cron jobs for an agent.
  create      Create a cron job.
  delete      Delete a cron job.
  run-now     Trigger a cron job immediately.
```

`create --trigger` accepts cron expressions (`"0 9 * * *"`) and the
`interval:N` / `date:ISO8601` aliases. `--task-type text` pushes the
prompt verbatim; `--task-type agent` (default) runs the LLM and
pushes the reply. `--prompt` is required, must be non-empty and ≤
2000 characters.

## `octop provider`

Local DB provider CRUD. `test` requires a running server.

```
Usage: octop provider [OPTIONS] COMMAND [ARGS]...

  Provider management commands (local DB).

Commands:
  list      List providers.
  create    Create a provider.
  delete    Delete a provider.
  test      Ping the provider (requires running server).
```

## `octop models`

Provider presets and active model management.

```
Usage: octop models [OPTIONS] COMMAND [ARGS]...

  Model catalog and active-model settings.

Commands:
  presets       List built-in provider templates from harness-agent.
  list          List all resolved models across enabled providers.
  active        Show or set the global default model (admin).
  config        Interactively create a provider from presets and set the active model.
  ollama-list   List local Ollama models (requires a running server).
  ollama-pull   Pull a model via Ollama (requires a running server).
  ollama-rm     Remove a local Ollama model (requires a running server).
```

## `octop skills`

Per-agent skill enable / disable. All subcommands need a running
server (the dashboard's Skill Hub and bundled `~/.octop/skills/`
library are queried at boot).

```
Usage: octop skills [OPTIONS] COMMAND [ARGS]...

  Manage agent skills (enable / disable / list).

Commands:
  list      List skills for an agent.
  enable    Enable a skill for the agent.
  disable   Disable a skill for the agent.
  config    Show / edit the per-agent skills config.
```

## `octop admin`

Local DB admin operations. `rotate-jwt-secret` works without a
running server (it edits the SQLite secret row directly).

```
Usage: octop admin [OPTIONS] COMMAND [ARGS]...

  Admin commands (local DB).

Commands:
  overview             Show admin overview (user count, agent state distribution).
  audit                Show audit log entries.
  providers            Global (admin) providers.
  rotate-jwt-secret    Rotate the JWT secret directly via the local DB.
```

## `octop backup`

Export and restore Octop backups. Works fully offline.

```
Usage: octop backup [OPTIONS] COMMAND [ARGS]...

  Backup and restore database + local agent workspaces.

Commands:
  create     Create a backup archive (DB + workspaces + config).
  restore    Restore a backup archive into ~/.octop.
  auto       Automatic backup status and one-shot run.
```

### `octop backup auto`

Automatic backups are scheduled **inside** a running `octop run` process
(via the same system-job mechanism as TLS renewal). Configure in
`config.json` under `backup`, with env overrides
`OCTOP_BACKUP_AUTO_ENABLED`, `OCTOP_BACKUP_SCHEDULE`,
`OCTOP_BACKUP_RETENTION_COUNT`, or via the dashboard Backup settings.

```
Usage: octop backup auto [OPTIONS] COMMAND [ARGS]...

Commands:
  status  Print automatic backup settings from config.json.
  run     Create one automatic backup now and prune by retention.
```

Default schedule when enabled: `cron:0 4 * * *` (daily 04:00, server
timezone). Automatic archives are named `octop-auto-backup-*.tar.gz`;
retention only deletes those files and never touches manual
`octop-backup-*.tar.gz` archives.

## `octop update`

Check for and install a newer Octop release from the configured
channel (PyPI by default).

```
Usage: octop update [OPTIONS]

  Check for and install a newer Octop release.

Options:
  --check / --no-check     Only check; do not install.
  --channel TEXT           Release channel (pypi, testpypi, custom index).
  -h, --help               Show this message and exit.
```

## `octop plugin`

Install and manage third-party plugins (drop into `~/.octop/plugins/`).
The same plugin manager powers the dashboard's "Plugins" page.

Octop also **seeds bundled plugins** into `~/.octop/plugins/` during
`octop init` and every `octop run` start. They are listed in Admin →
Plugins but stay **globally disabled** until you turn them on. An id
already recorded in `config.json` → `bundled_plugins_seeded` is not
copied again after uninstall.

```
Usage: octop plugin [OPTIONS] COMMAND [ARGS]...

  Install and manage plugins.

Commands:
  list       List installed plugins.
  install    Install a plugin (local path or git URL).
  uninstall  Remove an installed plugin.
  reload     Reload all installed plugins without restart.
```

## `octop acp`

Expose an Octop agent as a stdio JSON-RPC ACP server. Boots a
standalone `OctopServer` (reads `~/.octop`); does **not** require
`octop run` to be running.

```
Usage: octop acp [OPTIONS]

  Run Octop agent as ACP server (stdio).

Options:
  --agent TEXT   Agent to expose (default: OCTOP_AGENT or first agent).
  --debug        Log to stderr.
  -h, --help     Show this message and exit.
```

See [ACP integration](./acp.md) for the Zed setup example and the
runner object schema.

## `octop clean`

Reset CLI state or wipe the whole `~/.octop` tree. Destructive — read
the help carefully.

```
Usage: octop clean [OPTIONS]

  Remove CLI state or wipe all of ~/.octop.

Options:
  --state / --all       What to remove.
  --yes                 Skip the confirmation prompt.
  -h, --help            Show this message and exit.
```

## `octop config`

Inspect / edit `~/.octop/cli_state.json` (default base URL, user,
agent).

```
Usage: octop config [OPTIONS] COMMAND [ARGS]...

  CLI state (base URL, defaults).

Commands:
  show       Print the current CLI state.
  set-user   Pin the default --user.
```

## `octop completion` / `octop version`

```text
$ octop completion show bash   # dump a shell snippet
$ octop completion install     # append to ~/.zshrc / ~/.bashrc
$ octop version                # print the installed octop version
```

## CLI state file

`~/.octop/cli_state.json` stores:

```json
{
  "base_url": "http://127.0.0.1:8088",
  "token": null,
  "default_user": null,
  "default_agent": null
}
```

The path is exposed as `octop.cli.support.state.default_state_path()`
and can be overridden via `OCTOP_HOME`. Delete the file to log out
the CLI without hitting the server. The dashboard and HTTP callers
do not share this file — they manage their own tokens.
