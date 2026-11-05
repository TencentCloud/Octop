# Secure forms and the user vault (`request_secure_form`)

Multi-field collection of sensitive values through a paused turn, with a
user-scoped encrypted vault for reuse across the user's agents. Modeled
after masked handoffs in chat assistants: the agent pauses, a launcher card
docks in chat, and a modal collects typed fields without the values ever
becoming chat messages.

Use `request_secret_input` for a single secret that becomes one environment
variable; use `request_secure_form` when the handoff is multi-field — a site
login (username + password), CLI configuration (host + port + user +
password), or a payment card. The trigger is field structure, not
browser-vs-CLI.

## Data flow

```
Model calls request_secure_form(fields=[...], routing=env|vault)
→ registration validates BEFORE the pause enters the store
  (invalid forms are refused inline: no card, no eviction of other pendings)
→ harness interrupt (respond-only); the turn pauses
→ dashboard docks a launcher card → Open fetches the server-owned record
  (GET /api/agents/{id}/chat/secure-form/{pending_id})
→ the modal renders fields + a trust banner ONLY from that record
→ POST /api/agents/{id}/chat/secure-form/submit (one-shot; values travel once)
   → pre-claim validation → atomic claim (bounded reopen lease)
   → ONE transaction: env slot writes + vault item + audit row
→ the resumed turn sees metadata only: field ids, slot names, vault item id
```

## Routing

- `env` — every field maps to an environment-variable slot on the agent's
  command executions (the `request_secret_input` pipeline, including
  same-turn availability after the awaited harness rebuild). Slot names are
  normalized and rejected against a denylist that includes the exec-hijack
  class (`LD_PRELOAD`, `BASH_ENV`, `NODE_OPTIONS`, `PATH`, …); the banner
  marks names that replace existing slots.
- `vault` — fields persist as a typed item in the user's vault
  (`login` / `card` / `contact`). A colliding title requires an explicit
  replace confirmation; rotation reuses the existing item identity.
- `save_to_vault` (opt-in checkbox on env forms with registered vault
  metadata) — the envelope writer applies the per-type allow-list
  (`login` → text/password, `card` → number/expiry, `contact` → text):
  `card_cvv` and `otp` values never reach the vault, and an all-filtered
  save is refused instead of minting an empty credential. Env-routed values
  (including cvv/otp when collected that way) persist as the agent's
  environment secrets and remain reusable by the agent in later turns — the
  modal says so.

## Security guarantees

- Values never appear in chat history, thread records, model context, SSE
  frames, server logs, error messages, or 422 bodies (asserted end-to-end
  with per-field synthetic markers).
- Every bypass surface is closed: session `allow_all`, approval policies,
  the generic `/chat/hitl/resume`, slash approval, team rooms (inline
  refusal), and agent-MCP resume all reject secure-form pauses; the tools
  cannot be enabled in the admin HITL picker.
- One active secure-form pause per user session; the pending store evicts
  the previous pause and its card renders a terminal expired state.
- The vault envelope is Fernet-encrypted under a dedicated purpose key and
  binds `{user_id, vault_item_id, item_type}` into the ciphertext; a blob
  transplanted between rows fails to decrypt.
- Submits are idempotent for lost responses; recoverable refusals
  (replace-required, cap, capacity drift) never consume a reopen attempt,
  and only a hard write failure spends one (bounded at 5).

## Honest boundaries

- The purpose key lives in the same database as the ciphertext: encryption
  defends against log/query/metadata leakage, not full-DB compromise, and
  there is no automated key rotation today (the envelope carries a key
  version so a future rewrap has a marker).
- Origins shown in the banner are agent-declared and labeled as such;
  verified per-user origin allow-lists and the server-side browser fill
  executor are follow-up work.
- Vault items are user-scoped and shared across that user's agents; agents
  cannot read or enumerate items they did not just create (lookup/use
  tooling is follow-up work).

## Managing the vault

- `GET /api/vault/items` lists metadata only (title, type, origin,
  timestamps); `DELETE /api/vault/items/{vault_item_id}` removes an item
  (owner or admin). The dashboard's vault page (sidebar → Vault) offers the
  same. Create/rotate/delete are audit-logged with ids only.

## Disabling

The tool appears in the built-in tool catalog (`interaction` category) and
can be disabled per agent like any other tool; disabling removes both the
tool and its interrupt registration.
