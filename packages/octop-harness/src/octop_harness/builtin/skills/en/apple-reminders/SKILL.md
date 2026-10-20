---
name: apple-reminders
description: |
  Manage Apple Reminders on macOS via remindctl — list, add, edit, complete,
  delete to-dos that sync to iPhone/iPad. Trigger on "reminder", "Reminders app",
  "提醒我" with phone sync, or adding personal todos with due dates. macOS only.
  Skip when the user wants agent-internal alerts (use memory_store or external
  scheduling) or calendar events.
version: 1.0.0
author: Octop
license: MIT
compatibility: macos only — requires Reminders.app and remindctl CLI
metadata:
  octop:
    label:
      zh: "提醒事项"
      en: "Apple Reminders"
    summary:
      zh: "管理同步到 iPhone 的 macOS 提醒与待办。"
      en: "Manage macOS Reminders that sync to iPhone."
  harness:
    emoji: "☑️"
    tags: [Reminders, tasks, todo, macOS, Apple]
    related_skills: [apple-notes]
prerequisites:
  commands: [remindctl]
---

# Apple Reminders

## Harness-agent tools

| Concept | Tool |
|---------|------|
| Shell / brew / remindctl | `execute` |
| Memory (agent-only notes, no phone sync) | `memory_store`, `memory_recall` |

Builtin skill path: `/_builtin_skills/apple-reminders/`.

Use `remindctl` to manage Apple Reminders from the terminal. Tasks sync across
all Apple devices via iCloud.

## Bootstrap (run before first use)

Do **not** call `remindctl` until this checklist passes. Install missing deps
yourself via `execute` — do not ask the user to run brew unless install fails
or Homebrew is missing.

### 1. Confirm macOS

```bash
uname -s
```

Expect `Darwin`. On Linux/Windows, stop and tell the user this skill is
macOS-only.

### 2. Check / install `remindctl`

```bash
command -v remindctl && remindctl --version
```

If missing:

```bash
command -v brew
brew install steipete/tap/remindctl
remindctl --version
```

If `brew` is not installed, explain that Homebrew is required and point to
https://brew.sh — do not guess alternative install paths.

### 3. Check / request Reminders permission

```bash
remindctl status
```

If output indicates missing authorization:

```bash
remindctl authorize
```

Then tell the user to approve Reminders access in the system prompt or
**System Settings → Privacy & Security → Reminders**. Do not retry in a tight
loop — wait for the user to confirm they approved.

### 4. Smoke test

```bash
remindctl list
```

If this succeeds, proceed with the user's task.

## When to Use

- User mentions "reminder" or "Reminders app"
- Creating personal to-dos with due dates that sync to iOS
- Managing Apple Reminders lists
- User wants tasks to appear on their iPhone/iPad

## When NOT to Use

- **Agent-only "remind me later"** without phone sync → `memory_store` or ask
  the user to set up OS cron / an external scheduler
- Calendar events → Apple Calendar or Google Calendar
- Project task management → GitHub Issues, Notion, etc.
- If user says "remind me" but means an in-chat nudge → clarify first

## Quick Reference

### View Reminders

```bash
remindctl                    # Today's reminders
remindctl today              # Today
remindctl tomorrow           # Tomorrow
remindctl week               # This week
remindctl overdue            # Past due
remindctl all                # Everything
remindctl 2026-01-04         # Specific date
```

### Manage Lists

```bash
remindctl list               # List all lists
remindctl list Work          # Show specific list
remindctl list Projects --create    # Create list
remindctl list Work --delete        # Delete list
```

### Create Reminders

Always confirm title and due date with the user before `add`.

```bash
remindctl add "Buy milk"
remindctl add --title "Call mom" --list Personal --due tomorrow
remindctl add --title "Meeting prep" --due "2026-02-15 09:00"
```

### Due Time vs Alarm / Early Nudge

`--due` and `--alarm` are different fields:

- `--due` sets the reminder's due date/time.
- `--alarm` sets the EventKit alarm/notification trigger. Pass `--alarm`
  explicitly when the user asks for an earlier nudge.

Example — due 2:00 PM, notify 30 minutes early:

```bash
remindctl add --title "Hairdresser" --due "2026-05-15 14:00" --alarm "2026-05-15 13:30"
```

Edit an existing reminder:

```bash
remindctl edit 87354 --due "2026-05-15 14:00" --alarm "2026-05-15 13:30"
```

Verify with JSON (UI may group by alarm time):

```bash
remindctl today --json
```

Expected fields: `dueDate` (due time), `alarmDate` (notification time).

### Complete / Delete

```bash
remindctl complete 1 2 3          # Complete by ID
remindctl delete 4A83 --force     # Delete by ID
```

### Output Formats

```bash
remindctl today --json       # JSON for scripting
remindctl today --plain      # TSV format
remindctl today --quiet      # Counts only
```

Prefer `--json` when parsing output programmatically.

## Date Formats

Accepted by `--due` and date filters:

- `today`, `tomorrow`, `yesterday`
- `YYYY-MM-DD`
- `YYYY-MM-DD HH:mm`
- ISO 8601 (`2026-01-04T12:34:56Z`)

## Rules

1. **"Remind me"** — clarify: Apple Reminders (syncs to phone) vs
   `memory_store` / external schedule
2. Always confirm reminder content and due date before creating
3. Run the Bootstrap section when `remindctl` fails or on first use in a session
4. Use `--json` for programmatic parsing
