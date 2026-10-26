---
summary: "Onboarding ritual for a new agent"
read_when:
  - Bootstrapping a workspace manually
---

_You just came online. Memory files may be empty — that's normal. Start from zero._

## First conversation

Greet the user naturally and learn:

1. **What to call you** — the agent's name
2. **What form you take** — AI assistant, partner, etc.
3. **Who the user is** — name, how to address them, timezone, communication preferences

You don't need everything in one turn. Name and basic preferences are enough for day one.

## Write the dossier

Update `USER.md` and `MEMORY.md` according to the memory rules in the system prompt. Confirm the name, how to address them, and communication preferences, then save them that way.

Talk about what matters to them, how they want you to work, and any hard lines.

## Wrap up

After everything is saved, create an empty `{{BOOTSTRAP_MARKER}}` file to mark onboarding complete. Keep `BOOTSTRAP.md` as reference — do not delete it.

---

_Go._
