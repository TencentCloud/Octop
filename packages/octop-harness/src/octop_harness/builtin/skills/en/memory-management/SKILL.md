---
name: memory-management
description: Save and recall durable knowledge through octop-memory; distinguish user-maintained MEMORY.md from workspace configuration.
metadata:
  octop:
    label:
      zh: "记忆管理"
      en: "Memory"
    summary:
      zh: "通过 octop-memory 保存与召回记忆，区分强记忆和工作区配置。"
      en: "Save and recall octop-memory; distinguish strong memory from workspace configuration."
  harness:
    emoji: "💾"

---

# Memory Management

Follow the memory rules in workspace `AGENTS.md`. Workspace context is loaded
once per session and reused from its checkpoint; edits apply to new sessions.

## The files

| Destination | Purpose | Update through |
|-------------|---------|----------------|
| octop-memory | Durable facts, preferences, decisions and lessons | `memory_save`; background conversation distillation |
| `MEMORY.md` | Strong memory always available in the session | The user edits it manually; agents leave it unchanged |
| `USER.md` | User/agent dossier | The user edits it manually; agents are read-only, including onboarding |
| `AGENTS.md` | Workspace configuration | An explicit configuration request |

Do not create, edit, append to, overwrite or delete `MEMORY.md` or `USER.md` through file
tools or shell commands. Do not use other Markdown files as a substitute for
ordinary memory.

## Saving and recalling

1. When asked to remember something, call `memory_save` with one concise fact,
   preserving its scope and qualifiers. Confirm only after the tool succeeds.
2. If the tool is unavailable or fails, explain the limitation; leave workspace
   files unchanged.
3. Use `memory_search` for relevant history and `memory_get` to inspect sources.
   Strong memory is already present in the session context.
4. For an explicit `AGENTS.md` configuration edit, read the requested document
   and edit only the relevant section.

## What not to put in memory

- Secrets / API keys / credentials. Decline if asked.
- Session-only context (the user's *current* question). That goes in
  the chat history; memory is for things that should persist.
- Massive verbatim transcripts. Summarize.

## Conflict handling

Prefer current user instructions and verified evidence over outdated stored
facts. Leave user-maintained `MEMORY.md` edits to the user.
