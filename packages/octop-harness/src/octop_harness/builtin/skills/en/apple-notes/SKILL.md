---
name: apple-notes
description: "Manage Apple Notes via memo CLI: create, search, edit."
version: 1.0.0
author: Octop
license: MIT
compatibility: macos only
metadata:
  octop:
    label:
      zh: "备忘录"
      en: "Apple Notes"
    summary:
      zh: "在 macOS 上创建、搜索和编辑 Apple 备忘录。"
      en: "Create, search, and edit Apple Notes on macOS."
  harness:
    emoji: "📝"
    tags: [Notes, Apple, macOS, note-taking]
    related_skills: [obsidian]
prerequisites:
  commands: [memo]
---

# Apple Notes

## Harness-agent tools

This skill was ported from Octop. Use these harness/deepagents tools:

| Concept | Tool |
|---------|------|
| Shell | `execute` |
| Read / write / edit files | `read_file`, `write_file`, `edit_file` |
| Find files / search content | `glob`, `grep` |
| Fetch URLs | `web_fetch` |
| Browser automation | `browser_use` |
| Subagent work | `task` |
| Memory | `memory_store`, `memory_recall`, `memory_search` |

Builtin skill files live under `/_builtin_skills/<name>/`. User-installed skills live under `/skills/<name>/`.

Use `memo` to manage Apple Notes directly from the terminal. Notes sync across all Apple devices via iCloud.

## Prerequisites

- **macOS** with Notes.app
- Install: `brew tap antoniorodr/memo && brew install antoniorodr/memo/memo`
- Grant Automation access to Notes.app when prompted (System Settings → Privacy → Automation)

## When to Use

- User asks to create, view, or search Apple Notes
- Saving information to Notes.app for cross-device access
- Organizing notes into folders
- Exporting notes to Markdown/HTML

## When NOT to Use

- Obsidian vault management → use the `obsidian` skill
- Bear Notes → separate app (not supported here)
- Quick agent-only notes → use `memory_store` instead

## Quick Reference

### View Notes

```bash
memo notes                        # List all notes
memo notes -f "Folder Name"       # Filter by folder
memo notes -s "query"             # Search notes (fuzzy)
```

### Create Notes

```bash
memo notes -a                     # Interactive editor
memo notes -a "Note Title"        # Quick add with title
```

### Edit Notes

```bash
memo notes -e                     # Interactive selection to edit
```

### Delete Notes

```bash
memo notes -d                     # Interactive selection to delete
```

### Move Notes

```bash
memo notes -m                     # Move note to folder (interactive)
```

### Export Notes

```bash
memo notes -ex                    # Export to HTML/Markdown
```

## Limitations

- Cannot edit notes containing images or attachments
- Interactive prompts require terminal access (use pty=true if needed)
- macOS only — requires Apple Notes.app

## Rules

1. Prefer Apple Notes when user wants cross-device sync (iPhone/iPad/Mac)
2. Use `memory_store` for agent-internal notes that don't need to sync
3. Use the `obsidian` skill for Markdown-native knowledge management
