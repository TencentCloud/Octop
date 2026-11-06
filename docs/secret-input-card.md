# Secret input card (`request_secret_input`)

Chat-collected secrets with a masked input card, modeled after Grok's masked
secret prompts: when an agent needs a password, token, or API key, it pauses the
turn and the dashboard chat renders a masked input card. The value is stored
encrypted under a named slot and injected as an environment variable for the
agent's command executions.

## Data flow

```
Model calls request_secret_input(slot, prompt, title?)
→ harness interrupt (allowed_decisions=["respond"]); the turn pauses
→ dashboard chat docks a masked card (antd Input.Password)
→ POST /api/agents/{id}/chat/secret-input/submit   (value travels exactly once)
   → owner + non-shared + pending-scope validation → atomic claim
   → Fernet-encrypt (PURPOSE_AGENT_SECRET) into the agent_secrets table
   → rebuild the agent harness (awaited) so the slot lands in command env
   → resume the paused turn; the ToolMessage carries slot + status only,
     and commands in this same turn already see the injected env var
```

## What the feature guarantees

- The plaintext never appears in chat history, thread records, model context,
  SSE frames, server logs, or error messages. Tests assert a synthetic marker
  is absent end-to-end.
- The generic `/chat/hitl/resume` rejects these pauses (409) so a secret cannot
  be smuggled through a `respond` decision, whose message becomes the tool
  result verbatim.
- Session bypasses (`allow_all` / `allow_tools`) and approval policies cannot
  skip the pause; IM channels and `/approve` only show a dashboard notice.
- 422 validation errors on the submit endpoint never echo the rejected `input`
  or `ctx` fields.
- Storage is Fernet-encrypted at rest; the key is bootstrapped in the `secrets`
  table like every other Octop purpose (no external key management needed).

## Honest boundaries

- The value is injected into the agent's own command execution environment by
  design — a command the agent runs can read it (`printenv`). It must never be
  printed back into the chat; the tool description, the resume message, and the
  existing PII redaction layer all guard against accidental echo.
- Env injection is baked at harness build time: on a successful submit the
  submit endpoint rebuilds the agent harness (awaited) **before** the paused
  turn resumes, so the variable is visible to the commands of that same
  resumed turn — no extra "continue" turn is needed. If the rebuild fails the
  behavior degrades gracefully: the turn still resumes and the variable
  reaches the next build.
- Owner-only and non-shared agents. A shared agent's turns run for many users;
  injecting one user's secret into that shared environment would leak it
  across users.
- Slots are bounded (32 per agent, values ≤ 8192 chars) and slot names must be
  portable env identifiers; reserved platform names (`PATH`, `HOME`, …) and the
  `OCTOP_` prefix are rejected and normalized to upper case.

## Managing stored slots

- `GET /api/agents/{id}/secrets` lists slot metadata (never values).
- `DELETE /api/agents/{id}/secrets/{secret_id}` removes a slot and reloads the
  agent so its env var disappears.
- Submitting the same slot again rotates the stored value.

## Disabling

The tool is listed in the built-in tool catalog (`interaction` category);
disabling `request_secret_input` for an agent removes both the tool and its
interrupt registration.
