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

```text
action=list              → enabled runners and session state
action=start             → new session: runner + message (+ optional cwd)
action=message           → continue session
action=respond           → answer [permission_required] with exact option id
action=status            → session open / waiting for permission
action=close             → end session
```

Example user message:

```text
Use acp_runner: action=start, runner=opencode, message=find the README in the workspace and summarize it.
```

Permission prompts from the external agent appear in chat; pick an option or instruct the agent to call `action=respond` with the option id.

After changing global runners, Octop reloads your agents automatically. Changing only `tool_enabled` reloads that agent.

---

## CLI: inbound — expose Octop as an ACP server

Let external clients (e.g. Zed, WorkBuddy, OpenCode) use Octop as their coding agent:

```bash
octop acp
```

| Option | Description |
|--------|-------------|
| `--agent ID_OR_NAME` | Optional default expert: agent id **or** exact display name (else CLI `default_agent` / first local agent) |
| `--debug` | Log to stderr |

This starts a **standalone** `OctopServer` (reads `~/.octop`) and speaks ACP on stdin/stdout. It does **not** require `octop run` to be running; it is a separate process.

### Choosing an expert (multi-agent)

One `octop acp` process advertises **every enabled local agent** as an ACP session config option. Only the default expert is started at process boot (keeps IDE “Loading…” short); switching to another expert starts that agent on demand.

| Field | Value |
|-------|--------|
| `id` | `expert` |
| `category` | `_expert` (custom ACP category) |
| `type` | `select` |
| `currentValue` | `--agent` / CLI default / first local agent |
| `options[].value` | Octop `agent_id` |

Clients that support `session/set_config_option` can switch experts without restarting. Clients that ignore config options keep using `currentValue` (spec-compliant default).

Pin the default agent for convenience (optional — omit `--agent` to use the first local agent):

```bash
octop agent use main   # writes CLI default_agent
octop acp
# or one-shot:
octop acp --agent main
```

### Zed example

`~/.config/zed/settings.json`:

```json
{
  "agent_servers": {
    "Octop": {
      "command": "octop",
      "args": ["acp"],
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
      "args": ["run", "octop", "acp"],
      "env": {}
    }
  }
}
```

Create an agent thread in the client and prompt as usual. ACP `sessionId` maps to an Octop thread (`acp:{sessionId}:{agent_id}` when multiple experts are advertised). The agent workspace remains under `~/.octop/agents/<agent_id>/`.

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

- **octop-harness `[acp]` extra** — pulls in `agent-client-protocol` (included in the Octop wheel dependency on octop-harness).
- **Outbound:** install external CLIs (`opencode`, `codebuddy`, …) on the machine running `octop run`.
- **Inbound:** agent must start successfully (provider + model configured).

## Spec / capability honesty

Inbound ACP is stdio JSON-RPC (ACP v1). Octop advertises session lifecycle capabilities it implements:

| Capability | Advertised? | Notes |
|------------|-------------|-------|
| `session/close` | Yes | Cancels in-flight prompt, drops active session |
| `session/load` (`loadSession`) | Yes | Rebinds session; replays harness checkpoint history via `session/update` |
| `session/resume` | Yes | Rebinds without replay (Zed reopen after ACP process restart) |
| `session/list` | Yes | Process-local active sessions (not durable across ACP process exit) |
| `session/delete` / `fork` | No | Not implemented yet |
| Expert `configOptions` | Yes | When experts are passed into the ACP server |

Cloud / remote ACP (HTTP/WS) is out of scope; use Agent MCP (`/api/mcp/agents`) for remote callers.

Protocol checks: run [acp-tck](https://github.com/agentclientprotocol/acp-tck) against the harness mock agent `octop-harness/tests/fixtures/acp_stdio_agent.py` (no LLM). Full `octop acp` still needs a running local agent and is for IDE smoke tests (Zed, WorkBuddy, …).

Example (from an `acp-tck` checkout; report should say `VERDICT: CONFORMANT` for mandatory/capability tiers):

```bash
uv run acp-tck --agent-cwd /tmp/acp-tck-wd --timeout 15 \
  --report-json /tmp/octop-acp-tck.json \
  -- /path/to/octop-harness/.venv/bin/python \
     /path/to/octop-harness/tests/fixtures/acp_stdio_agent.py
```

### Zed smoke test (`octop acp`)

1. Ensure at least one agent exists locally. `octop acp` lists all enabled agents and boots only the default (others start when you pick them in the IDE).
2. Add to `~/.config/zed/settings.json`:

```json
{
  "agent_servers": {
    "Octop": {
      "command": "uv",
      "args": ["run", "--project", "/Users/huangcheng/Projects/Octop", "octop", "acp"],
      "env": {}
    }
  }
}
```

3. In Zed, open an agent thread with **Octop** and send a short prompt.

If you use an installed `octop` wheel instead of a checkout, set `"command": "octop"` and `"args": ["acp"]`.

---

## Troubleshooting

| Symptom | Likely cause |
|---------|----------------|
| Runner missing on some agents | Upgrade to user-global runners; open `/acp` once or `GET /api/acp` to trigger migration |
| `acp_runner` lists runner but start fails with “Unknown runner” | Restart `octop run` after adding a custom runner (ACP service cache is process-wide) |
| External runner returns no text | Check CLI auth/quota (e.g. `codebuddy auth status`) |
| Zed thread stuck on “Loading…” | First open waits until ACP `initialize` returns. `octop acp` answers `initialize` while the selected expert boots in the background (lean: no IM/cron/catalog scan). Close the thread and open a new one if an older process is still attached. |
| `octop acp` fails immediately | Invalid `--agent` (id/name), or that agent cannot start (provider/model). Check Zed agent stderr / `octop acp --debug` |
| Expert switch returns `-32602` | Unknown agent id, or that agent failed to start on demand (check `octop acp --debug`) |
| Expert dropdown shows only one agent | Restart the ACP connection / open a new thread after upgrading; older builds advertised only the booted default |
| Command not found | Use absolute path in runner `command` if `PATH` for the server process differs from your shell |
| Kimi Code fails to start | Install [kimi-code](https://github.com/MoonshotAI/kimi-code) and run `kimi` login on the host |
| Cursor CLI fails to start | Install Cursor CLI; run `agent login` or set `CURSOR_API_KEY` |
| Pi runner fails to start | Requires Node.js for `npx -y pi-acp`; ensure network access for first npm fetch |

---

## Related

- Dashboard: `/acp`
- CLI: `octop acp --help`
- OpenAPI: `/api/docs`
- Harness implementation: `octop-harness` → `octop_harness.acp` (server + `acp_runner` tool)
