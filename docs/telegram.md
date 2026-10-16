# Telegram channel behavior

Octop uses the installed Gateway's Telegram configuration capabilities. Saving or probing a channel rejects unknown transport options and invalid activation, streaming, allowlist, or boolean values. The host-owned `response_mode` and legacy nested `enabled` fields are accepted; `enabled: "true"` in an old channel does not prevent registration. `http_proxy` is a transport field, while unknown `http_*` flags are rejected rather than silently ignored.

Dashboard defaults match Gateway: `group_activation=always`, `allow_unaddressed_commands=true`, `topic_isolation=false`, `reply_to_message=true`, `link_preview=true`, `streaming_mode=off`; the other Telegram feature switches default to false. In groups configured for mention activation, use `/models@your_bot` (or mention the bot). Bare `/models` requires `allow_unaddressed_commands=true`. Telegram privacy mode still determines which updates reach the bot.

The model menu lists enabled chat models from enabled providers, using the same eligibility rules as the provider store. Lists larger than 48 entries use opaque, expiring Gateway callback capabilities for page navigation. Each action is bound to its Telegram sender, chat, topic, agent owner, and current thread; model eligibility is checked again when selected. Model selection follows the normal `/model` command path. Telegram identity is not an Octop administrative identity.

Single-choice `ask_user_question` buttons are emitted only for a pending question identified by the current response. Stale question indexes, expired records, thread rebindings, and owner changes invalidate actions. Multi-select questions continue to accept text answers. Security approvals remain on their existing authorization path.

With topic isolation enabled, persisted routing includes the native chat and topic IDs. Session identity includes the channel instance ID, chat ID, and topic ID, with escaped separators. Two channel instances connected to the same Telegram chat therefore retain separate sessions. Cancellation of the Telegram processor stream also signals cancellation to the agent runtime.

Agent switching is unsupported in Telegram. Configure a separate channel for each agent. This integration does not provide an agent selection menu.
