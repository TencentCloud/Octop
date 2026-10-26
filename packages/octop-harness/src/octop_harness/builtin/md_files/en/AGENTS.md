---
summary: "Workspace template for AGENTS.md"
read_when:
  - Bootstrapping a workspace manually
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

Skills document specialized tools — read each `SKILL.md` before use. For an explicit `AGENTS.md` configuration change, read first and edit precisely.

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
