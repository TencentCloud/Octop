---
name: memory-management
description: Maintain the harness memory files (USER.md, MEMORY.md, AGENTS.md) so that long-term knowledge persists across conversations.
---

# Memory Management

The harness ships a set of memory files that the agent reads at the start of
**every** conversation. Use them to store durable context that should survive
across turns, threads, and even process restarts.

Two read-only tools are available when you need to recall something that
isn't in the current context:

- `memory_search(query, max_results, corpus)` — ranked hits across past
  conversation snippets and host files.
- `memory_get(path, start, lines)` — fetch the source markdown for a hit
  returned by `memory_search`.

Your primary job is to maintain the human-readable Markdown files below.

## The files

| File | Purpose | Update when... |
|------|---------|----------------|
| `USER.md` | Stable info about the human and the agent: names, roles, preferred tone, language, behavioral rules. | The user shares something personal, expresses a preference, or corrects your style. |
| `MEMORY.md` | Project-level long-term notes: decisions, constraints, lessons, environment config. | A turn produces a fact you'll need next time. |
| `AGENTS.md` | Project conventions (build commands, code style, repo layout). | The user clarifies how the project should be worked on. |

Transient day-of context (a single emotion, a passing event, the question of
the moment) does **not** belong in any of these files — leave it in the
conversation. Promote a fact only when you'll still need it next session.

## When to update memory

- **Promotable signal**: the user says "remember that…", "from now on…",
  corrects you on style, or shares contextual info you'd otherwise re-ask.
- **Ambient signal**: you notice you keep re-deriving the same fact across
  turns. Lift it into the appropriate memory file.

Do **not** dump every chat into memory. The top-level files are read on every
turn — bloat costs tokens for every future conversation. Only promote into
`USER.md` / `MEMORY.md` when the fact is durable; transient context belongs
in the conversation, not in a memory file.

## How to update

1. **`read_file`** the target memory file first. You're amending, not
   recreating.
2. **`edit_file`** for small additions: add a bullet under the right section.
   Use **`append_file`** when you only need to add a new line at the end.
3. Keep entries terse: 1-2 lines per fact. Use bullets, not paragraphs.
4. Group by section (e.g. `## Coding style`, `## User preferences`). Create
   a section before adding to it if one doesn't already exist.
5. **Never use `write_file`** on any memory file: it overwrites everything.
6. After updating, briefly tell the user you saved the memory and where, so
   they can correct misinterpretations.

## How to recall

If the user clearly references past context ("last time", "we talked about",
"earlier") and the answer isn't already in the current context, fall back to:

1. `memory_search` with concrete keywords (names, project names, tech stack).
2. `memory_get` with a `path` from the search results to read the source.
3. If still empty, read `MEMORY.md` directly.

Weave findings naturally into the reply — never say "I found in my memory…".

## What not to put in memory

- Secrets / API keys / credentials. Decline if asked.
- Session-only context (the user's *current* question). That goes in the
  chat history; memory is for things that should persist.
- Massive verbatim transcripts. Summarize.

## Conflict handling

If a new instruction contradicts an existing memory, **delete or update the
old line** rather than appending. Two contradictory facts in memory will
confuse you next time. When in doubt, ask the user which to keep.
