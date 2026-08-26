# ACP (Agent Client Protocol)

Octop integrates [ACP](https://agentclientprotocol.com/) in two directions:

| Direction | ACP server | ACP client | Typical use |
|-----------|------------|------------|-------------|
| **Inbound** | Octop (`octop acp`) | Zed, OpenCode, … | External IDE drives your Octop agent |
| **Outbound** | OpenCode, CodeBuddy, … | Octop (`acp_runner` tool) | Octop agent delegates coding tasks |

Both use **stdio** JSON-RPC today. Octop does not expose an HTTP ACP endpoint.

---

## Dashboard: outbound runners

Open **ACP** in the sidebar (`/acp`).

### What is global vs per-agent

| Setting | Scope | Stored in |
|---------|--------|-----------|
| Runner cards (command, args, enabled, …) | **Per user** — shared by all your agents | `settings` table (`acp_runners:user:{id}`) |
| **Enable acp_runner tool** toggle | **Per agent** | Agent `config_json.acp.tool_enabled` |

Legacy per-agent `config_json.acp.runners` is migrated to the user-global store on first load.

### Built-in runners

| ID | Command | Args |
|----|---------|------|
| `opencode` | `opencode` | `acp` |
| `codebuddy` | `codebuddy` | `--acp` |
| `claude_code` | `npx` | `-y`, `@zed-industries/claude-agent-acp` |
| `codex` | `npx` | `-y`, `@zed-industries/codex-acp` |
| `kimi_code` | `kimi` | `acp` |
| `cursor_cli` | `agent` | `acp` |
| `pi` | `npx` | `-y`, `pi-acp` |

Install the CLI on the host where `octop run` executes, ensure it is on `PATH` (or set an absolute `command` in the runner drawer). Built-in runners cannot be deleted; custom runners can be added from **Add runner**.

### Enable delegation in chat

1. Configure and enable at least one runner on `/acp`.
2. Switch agent in the top bar and turn on **Enable acp_runner tool** for that agent.
3. In chat, ask the agent to use `acp_runner`, or let it delegate when appropriate.

### `acp_runner` tool workflow

```
action=list              → enabled runners and session state
action=start             → new session: runner + message (+ optional cwd)
action=message           → continue session
action=respond           → answer [permission_required] with exact option id
action=status            → session open / waiting for permission
action=close             → end session
```

Example user message:

```text
请用 acp_runner：action=start, runner=opencode, message=在 workspace 里找 README 并总结。
```

Permission prompts from the external agent appear in chat; pick an option or instruct the agent to call `action=respond` with the option id.

After changing global runners, Octop reloads your agents automatically. Changing only `tool_enabled` reloads that agent.

---

## CLI: inbound — expose Octop as an ACP server

Let external clients (e.g. Zed) use an Octop agent as their coding agent:

```bash
octop acp --agent main
```

| Option | Description |
|--------|-------------|
| `--agent ID` | Agent to expose (default: CLI `default_agent` or first agent) |
| `--debug` | Log to stderr |

This starts a **standalone** `OctopServer` (reads `~/.octop`), boots the agent, and speaks ACP on stdin/stdout. It does **not** require `octop run` to be running; it is a separate process.

Pin the default agent for convenience:

```bash
octop user login --username you
# set default_agent in ~/.octop/cli_state.json, or:
octop --agent main acp
```

### Zed example

`~/.config/zed/settings.json`:

```json
{
  "agent_servers": {
    "Octop": {
      "command": "octop",
      "args": ["acp", "--agent", "main"],
      "env": {}
    }
  }
}
```

From a dev checkout:

```json
{
  "agent_servers": {
    "Octop": {
      "command": "uv",
      "args": ["run", "octop", "acp", "--agent", "main"],
      "env": {}
    }
  }
}
```

Create an agent thread in Zed and prompt as usual. Sessions map to `thread_id`; the agent workspace remains under `~/.octop/agents/<agent_id>/`.

---

## HTTP API

Interactive docs: `/api/docs` (tag **agents**).

### Global runners (current user)

| Method | Path | Body |
|--------|------|------|
| `GET` | `/api/acp` | — |
| `PUT` | `/api/acp` | `{ "runners": { "<id>": { … } } }` |
| `GET` | `/api/acp/{runner_name}` | — |
| `PUT` | `/api/acp/{runner_name}` | runner object |
| `DELETE` | `/api/acp/{runner_name}` | custom runners only |

### Per-agent tool toggle

| Method | Path | Body |
|--------|------|------|
| `GET` | `/api/agents/{agent_id}/acp` | returns global `runners` + agent `tool_enabled` |
| `PUT` | `/api/agents/{agent_id}/acp` | `{ "tool_enabled": bool, "runners": …? }` — `runners` optional, updates global |
| `PUT` | `/api/agents/{agent_id}/acp/tool` | `{ "tool_enabled": bool }` only |

Runner shape:

```json
{
  "enabled": true,
  "command": "opencode",
  "args": ["acp"],
  "env": {},
  "trusted": true,
  "tool_parse_mode": "update_detail",
  "stdio_buffer_limit_bytes": 52428800
}
```

---

## Prerequisites

- **harness-agent `[acp]` extra** — pulls in `agent-client-protocol` (included in the Octop wheel dependency on harness-agent).
- **Outbound:** install external CLIs (`opencode`, `codebuddy`, …) on the machine running `octop run`.
- **Inbound:** agent must start successfully (provider + model configured).

---

## Troubleshooting

| Symptom | Likely cause |
|---------|----------------|
| Runner missing on some agents | Upgrade to user-global runners; open `/acp` once or `GET /api/acp` to trigger migration |
| `acp_runner` lists runner but start fails with “Unknown runner” | Restart `octop run` after adding a custom runner (ACP service cache is process-wide) |
| External runner returns no text | Check CLI auth/quota (e.g. `codebuddy auth status`) |
| `octop acp` fails immediately | Agent not running or invalid `--agent`; create/start agent in dashboard first |
| Command not found | Use absolute path in runner `command` if `PATH` for the server process differs from your shell |
| Kimi Code fails to start | Install [kimi-code](https://github.com/MoonshotAI/kimi-code) and run `kimi` login on the host |
| Cursor CLI fails to start | Install Cursor CLI; run `agent login` or set `CURSOR_API_KEY` |
| Pi runner fails to start | Requires Node.js for `npx -y pi-acp`; ensure network access for first npm fetch |

---

## Related

- Dashboard: `/acp`
- CLI: `octop acp --help`
- OpenAPI: `/api/docs`
- Harness implementation: `harness-agent` → `harness_agent.acp` (server + `acp_runner` tool)
