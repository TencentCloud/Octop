# Octop Plugin Demos

[中文版](./README_CN.md)

Sample plugins for the three `kind` values supported by Octop / harness-agent.
Layout inspired by [octop-toolkit](https://github.com/veenyi/octop-plugins/tree/main/octop-toolkit).

## Demos

| Directory | `kind` | What it shows |
|-----------|--------|----------------|
| [`demo-toolkit`](./demo-toolkit/) | `tool` | Register callable tools (time, text stats, configurable echo) |
| [`demo-greeting-skill`](./demo-greeting-skill/) | `skill` | Sync a sample Skill into the agent workspace |
| [`demo-turn-logger`](./demo-turn-logger/) | `hook` | Register `AgentMiddleware` that logs before/after model calls |

## Plugin layout

Each plugin is a folder with at least:

```text
my-plugin/
├── plugin.yaml    # id, version, name, kind, entry
├── main.py        # must define setup(ctx)
└── skills/        # skill plugins only: <name>/SKILL.md
```

In `setup(ctx)`, use the API that matches `kind`:

| `kind` | API |
|--------|-----|
| `tool` | `ctx.tool(name, fn, description=..., config_fields=...)` |
| `skill` | `ctx.skills("skills")` — path relative to the plugin root |
| `hook` | `ctx.middleware(instance, priority=...)` |

## Install locally

```bash
# From a directory (best for development)
octop plugin install ./plugins/demo-toolkit --force
octop plugin install ./plugins/demo-greeting-skill --force
octop plugin install ./plugins/demo-turn-logger --force
octop plugin list
```

Or pack a ZIP first:

```bash
cd plugins
zip -r demo-toolkit.zip demo-toolkit/
octop plugin install ./demo-toolkit.zip --force
```

**Dashboard:** Admin → Plugins → Install. Paste a **direct ZIP download URL**
(on GitHub use `raw.githubusercontent.com` or the Download / raw link — not a `/blob/` page).

After installing a **tool** plugin, open **Tool management**, pick an agent, and enable
the tools. **Skill** plugins sync into the agent workspace `skills/` on agent start.
**Hook** middleware is attached for globally enabled plugins.

## Package rules

The ZIP must contain **exactly one** plugin root that includes `plugin.yaml`:

```bash
# Good — one top-level plugin folder
zip -r demo-toolkit.zip demo-toolkit/

# Bad — multiple plugins, or loose files without a plugin root
```

## Quick validity check

From the repo root (no server required):

```bash
uv run python - <<'PY'
from pathlib import Path
from harness_agent.plugins import PluginRegistry, load_plugin_dir

for name in ("demo-toolkit", "demo-greeting-skill", "demo-turn-logger"):
    PluginRegistry.reset()
    p = load_plugin_dir(Path("plugins") / name, install_deps=False)
    print(
        p.manifest.id,
        p.manifest.kind,
        f"tools={len(p.tools)}",
        f"mw={len(p.middleware)}",
        f"skills={p.skills_dir}",
    )
PY
```

Expected shape:

- `demo-toolkit` → `tool`, 3 tools  
- `demo-greeting-skill` → `skill`, `skills/` present  
- `demo-turn-logger` → `hook`, 1 middleware  
