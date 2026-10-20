# Workspace Subagents

Place subagent definitions here as ``**/*.md`` files. Each file uses YAML frontmatter
plus a markdown body that becomes the subagent ``system_prompt``.

## Minimal example

```markdown
---
name: Research Assistant
id: research-assistant
description: |
  Conducts focused research and returns a concise summary with sources.
---

You are a research assistant. Use web_fetch when needed. Return bullet findings only.
```

## Frontmatter

| Field | Required | Notes |
|-------|----------|-------|
| ``description`` | yes | When the main agent should delegate (``task`` routing) |
| ``name`` | no | Display name for catalogs |
| ``id`` | no | ``subagent_type``; defaults from file path |
| ``emoji`` | no | Catalog icon; defaults to ``🤖`` when omitted |
| ``model`` | no | ``provider:model`` override |
| ``tools`` | no | Omit or ``inherit``; whitelist list; or ``[]`` |
| ``skills`` | no | Skill root directories for this subagent |

Packaged seeds (e.g. ``general-purpose.md``) are copied here on ``init()`` and are
not overwritten on later runs unless ``overwrite=True``. Remove a ``.md`` file to
stop loading that subagent (then call ``reload_subagents()`` or restart the agent).
