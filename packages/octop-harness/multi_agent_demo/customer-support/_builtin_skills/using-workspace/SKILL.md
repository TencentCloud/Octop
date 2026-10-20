---
name: using-workspace
description: Use the harness virtual filesystem (workspace) to organize multi-step work; read/write files instead of stuffing everything into the chat.
---

# Using the Workspace

You operate inside a **virtual workspace** backed by octop-harness's filesystem
tools (`ls`, `read_file`, `write_file`, `edit_file`, `glob`, `grep`). Treat
this workspace as your long-term memory for any task that produces artifacts
or spans multiple turns.

## When to use the workspace

- **Anything > ~200 words of generated content.** Write it to a file under a
  meaningful path instead of pasting it into the chat. Reply with a short
  summary plus the file path.
- **Plans, todos, or task lists** that the user will refer back to. Save them
  under `plans/<topic>.md` or use the planning tool when available.
- **Intermediate artifacts** (drafts, research notes, raw fetched data).
  Persist to disk so later steps can grep/read them without re-asking the
  user.
- **Reference material** the user uploads or asks you to study.

## Conventions

- **One topic per directory.** Group related files under a folder named
  after the topic, e.g. `research/customer-X/` rather than scattering
  `customer-X-1.md`, `customer-X-2.md` at the root.
- **Markdown for prose, JSON/YAML for structured data, code in language
  files** with the right extension. The reader (LLM or human) gets better
  affordances when extensions are honest.
- **Prefer relative paths under the current working directory** unless the
  user explicitly asks otherwise. Don't reach into system directories.
- **Read before you write.** When updating an existing file, `read_file`
  first to confirm the current contents and avoid clobbering edits.
- **Use `edit_file` for surgical changes** (string replacement) and
  `write_file` for new or fully-rewritten files. Don't `write_file` over a
  large existing file just to change one line.

## Workflow patterns

1. **Plan → write → reflect.** For non-trivial tasks, save the plan to a
   file first, then execute, updating the file as steps complete. This
   gives both you and the user a checkpoint.
2. **Search before recreating.** Before producing similar content, run
   `glob`/`grep` to see if a relevant file already exists.
3. **Summaries cite paths.** When you finish, include the list of files you
   created or modified in your reply. Users want to know where things landed.
