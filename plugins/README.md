# Octop Plugin Demos

[中文版](./README_CN.md)

Sample plugins for Octop / harness-agent `kind` values, plus a **dual
frontend + backend** demo that renders tool results in chat.
Layout inspired by [octop-toolkit](https://github.com/veenyi/octop-plugins/tree/main/octop-toolkit).

Product plugins shipped with the wheel live in
`src/octop/infra/agents/plugins/bundled/`. `octop init` and `octop run`
copy missing ones into `~/.octop/plugins/` and set them **globally off**
in `config.json`. Uninstalled ids are not re-copied.

## Demos

| Directory | `kind` | What it shows |
|-----------|--------|----------------|
| [`demo-toolkit`](./demo-toolkit/) | `tool` | Register callable tools (time, text stats, configurable echo) |
| [`demo-greeting-skill`](./demo-greeting-skill/) | `skill` | Sync a sample Skill into the agent workspace |
| [`demo-turn-logger`](./demo-turn-logger/) | `hook` | Register `AgentMiddleware` that logs before/after model calls |
| [`demo-ui-card`](./demo-ui-card/) | `tool` + `ui/` | Backend returns `octop_ui` JSON; frontend renders an interactive card |

## Plugin layout

```text
my-plugin/
├── plugin.yaml    # id, version, name, kind, entry; optional ui
├── main.py        # must define setup(ctx)
├── skills/        # skill plugins only: <name>/SKILL.md
└── ui/            # optional prebuilt UI (no npm on install)
    └── dist/
        ├── index.js
        └── manifest.json
```

In `setup(ctx)`, use the API that matches `kind`:

| `kind` | API |
|--------|-----|
| `tool` | `ctx.tool(name, fn, description=..., config_fields=...)` |
| `skill` | `ctx.skills("skills")` — path relative to the plugin root |
| `hook` | `ctx.middleware(instance, priority=...)` |

### Optional icon + UI

```yaml
icon: "🧩"   # emoji or https://… image URL for Admin cards
ui:
  entry: ui/dist/index.js
  manifest: ui/dist/manifest.json
```

### Tool plugins with UI

```yaml
ui:
  entry: ui/dist/index.js
  manifest: ui/dist/manifest.json
```

Prefer JSON tool output:

```json
{
  "octop_ui": { "renderer": "demo_card", "version": 1 },
  "data": { "title": "…", "count": 1 },
  "text": "plain fallback"
}
```

The Dashboard loads `index.js` via `GET /api/plugins/{id}/ui/…`, calls
`setup(host)`, and resolves renderers in chat. Use `host.patchResult` for
interactive L2 updates; streaming still replaces `output` via SSE (L1).
Ship a self-contained ESM; React is provided as `window.__OCTOP_REACT__` /
`__OCTOP_JSX__`.

## Install locally

```bash
octop plugin install ./plugins/demo-toolkit --force
octop plugin install ./plugins/demo-greeting-skill --force
octop plugin install ./plugins/demo-turn-logger --force
octop plugin install ./plugins/demo-ui-card --force
octop plugin list
```

Or pack a ZIP first (include prebuilt `ui/dist/` when present — the server
does **not** run `npm install`).

**Dashboard:** Admin → Plugins → Install. Paste a **direct ZIP download URL**.

After installing a **tool** plugin, open **Tool management** and enable the
tools. **Skill** plugins sync on agent start. **Hook** middleware attaches for
globally enabled plugins. **UI** loads when you open chat.

## Package rules

The ZIP must contain **exactly one** plugin root that includes `plugin.yaml`.

## Quick validity check

```bash
uv run python - <<'PY'
from pathlib import Path
from harness_agent.plugins import PluginRegistry, load_plugin_dir

for name in ("demo-toolkit", "demo-greeting-skill", "demo-turn-logger", "demo-ui-card"):
    PluginRegistry.reset()
    p = load_plugin_dir(Path("plugins") / name, install_deps=False)
    print(p.manifest.id, p.manifest.kind, len(p.tools))
PY
```
