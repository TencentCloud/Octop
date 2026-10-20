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

Ask the user to fill `USER.md` in Memory → User profile, including agent identity,
their name and communication preferences. Agents must not edit this file.

`MEMORY.md` is maintained manually by the user in Memory → Strong memory. Leave it unchanged during onboarding. Save remember requests to octop-memory through `memory_save`.

Talk about what matters to them, how they want you to work, and any hard lines.
They can maintain these rules in the profile editor. Save explicit remember requests through `memory_save`.

## Wrap up

After everything is saved, create an empty `{{BOOTSTRAP_MARKER}}` file to mark onboarding complete. Keep `BOOTSTRAP.md` as reference — do not delete it.

---

_Go._
