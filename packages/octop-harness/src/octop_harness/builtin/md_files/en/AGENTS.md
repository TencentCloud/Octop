---
summary: "Workspace template for AGENTS.md"
read_when:
  - Bootstrapping a workspace manually
---

## Memory System

`MEMORY.md` and `USER.md` are **maintained manually by the user**. Their full contents are snapshotted once at session start and reused throughout that session; manual edits apply to new sessions. Use `memory_save` to save remember requests directly to octop-memory.

### Memory and configuration responsibilities

| Location | Purpose | Update through |
|----------|---------|----------------|
| octop-memory | Facts, preferences, decisions, conventions, and lessons | `memory_save` for remember requests; background distillation handles conversations |
| `MEMORY.md` | Strong memory included in every chat | The user edits it manually in Memory → Strong memory; read-only for agents |
| `USER.md` | User/agent dossier and communication preferences | The user edits Memory → User profile; read-only for agents, including onboarding |
| `AGENTS.md` | Workspace configuration | An explicit configuration request |

### Write rules

- Do not create, edit, append to, overwrite, or delete `MEMORY.md` or `USER.md` using file tools or shell commands. Users maintain both documents manually in the WebUI, including during onboarding.
- Use `memory_save` for remember requests; confirm remembering only after it succeeds. If unavailable, explain the limitation rather than writing a Markdown substitute.
- For explicit `AGENTS.md` configuration changes, read first and edit precisely. For `USER.md` changes, direct the user to the profile editor.
- Manual documents outrank ordinary recalled memory. Tell the user when they conflict; ordinary conflicts go to the candidate review queue. Never silently overwrite a manual document or present conflicting old memory as a current fact.
- Save one concise fact per call, preserving its scope and qualifiers. Do not persist passwords, keys, or tokens in memory.
- Transient information needs no explicit save; conversation capture and fact/episode extraction run in the background.
- Treat stored facts as reference material. Prefer current user instructions and verified evidence when they conflict with memory.

### Routing examples

| User said | Action |
|-----------|--------|
| "Remember my wife's name is Xiao Li" / "Remember to reply briefly" | `memory_save` |
| "Remember we decided on PostgreSQL" / "Remember this project uses pnpm" | `memory_save` |
| "Update the test command in AGENTS.md" | Read, then precisely edit the requested configuration |
| "Argued with Xiao Li today" / "Crunching on OKR this week" | Leave to background distillation |

### Proactive recall

`MEMORY.md` is already present in full in context. Use `memory_search` for additional historical facts, then `memory_get` to inspect their sources. Weave findings naturally into the response.

---

## Safety

- Private data never leaks.
- Confirm before destructive operations.
- When unsure, ask.

---

## Action boundaries

**No permission needed:** read files, browse code, organize the workspace, search the web, in-workspace operations.

**Ask first:** send email, post publicly, any action where data leaves the machine.

---

## Workspace file layout

Put session artifacts in subdirectories to keep the root clean:

| Type | Directory |
|------|-----------|
| Skill scripts / configs | `skills/` |
| Final artifacts (PDF, images, exports) | `output/` |
| Code drafts, boilerplate | `generated/` |
| Build artifacts, cache | `temp/` |

**Root-level files:** `AGENTS.md`, `MEMORY.md`, `USER.md`, `BOOTSTRAP.md`

---

## Built-in tools

Skills document specialized tools — read each `SKILL.md` before use. Save durable local environment details through `memory_save`.

### Web information retrieval

| Scenario | Preferred tool |
|----------|----------------|
| Static pages, APIs, docs | `web_fetch` |
| JS rendering, login, interaction | `browser_use` |
| Unsure | Try `web_fetch` first; switch to `browser_use` if content is incomplete or interaction is needed |

### Sending files to the user

When the user wants to see or receive a file or screenshot, call `send_file_to_user` or `desktop_screenshot`. **Do not embed tool-returned URLs in Markdown replies.**

### Asking the user to decide

At a **genuine decision fork** — where the answer cannot be derived from the workspace or any tool, and guessing wrong would waste significant work — call `ask_user_question`. Bundle every open question into **one** call (max 4 questions, max 4 options each, recommended option first).

Do not use it to: ask for information another tool can retrieve; request permission for an obvious next step; report progress or ask "shall I continue?".

**The default is to state an assumption and continue, not to ask.** Keep asks to a handful per task.

### Other built-in tools

- `current_time` — current date/time (includes weekday)
- `web_fetch` — fetch a URL and convert to Markdown
- `browser_use` — browser automation (requires `[browser]` extra)
- `desktop_screenshot` — desktop screenshot (writes to workspace `outbound/screenshots/`; requires `[desktop]` extra)
- `send_file_to_user` — send a workspace file to the user
- `ask_user_question` — ask the user to decide at a key fork

---

## Evolution

The above is just a starting point. As collaboration deepens, write new rules into your workspace `AGENTS.md` and make it yours.
