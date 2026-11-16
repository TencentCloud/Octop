# Telegram channel behavior

This draft integration depends on [octop-gateway #44](https://github.com/TencentCloud/octop-gateway/pull/44). Its immutable uv source override is temporary and must be replaced with the published Gateway version requirement before merging. Gateway owns transport policies, table rendering, mention normalization, quote extraction, callback identity checks and keyboard settlement; this integration installs no local platform presentation patches.

Octop uses the installed Gateway's Telegram configuration capabilities. Saving or probing a channel rejects unknown transport options and invalid activation, streaming, allowlist, or boolean values. The host-owned `response_mode` and legacy nested `enabled` fields are accepted; `enabled: "true"` in an old channel does not prevent registration. `http_proxy` is a transport field, while unknown `http_*` flags are rejected rather than silently ignored.

Dashboard defaults match Gateway: `group_activation=always`, `allow_unaddressed_commands=true`, `topic_isolation=false`, `reply_to_message=true`, `link_preview=true`, `streaming_mode=off`; the other Telegram feature switches default to false. In groups configured for mention activation, use `/models@your_bot` (or mention the bot). Bare `/models` requires `allow_unaddressed_commands=true`. Telegram privacy mode still determines which updates reach the bot.

The model menu lists enabled chat models from enabled providers, using the same eligibility rules as the provider store. Lists larger than 48 entries use opaque, expiring Gateway callback capabilities for page navigation. Gateway binds actions to sender, chat and topic. Octop rechecks agent ownership and model eligibility under the session worker lock; private chats also check the current thread. Group navigation survives unrelated messages rebinding the current thread. Model selection follows the normal `/model` command path. Telegram identity is not an Octop administrative identity.

Single-choice `ask_user_question` buttons are emitted only for a pending question identified by the current response. Octop revalidates the pending record, session, user, question index and owner before execution; private-chat thread rebindings invalidate actions. A failed native-button delivery releases the text question card. Multi-select questions continue to accept text answers. Security approvals remain on their existing authorization path.

Gateway supplies bounded quote metadata. Octop builds the localized quote prompt, omitting an ordinary reply to this bot's own message because that output is already in history. An explicitly selected quote is still included.

With topic isolation enabled, persisted routing includes the native chat and topic IDs. Session identity includes the channel instance ID, chat ID, and topic ID, with escaped separators. Two channel instances connected to the same Telegram chat therefore retain separate sessions. Cancellation of the Telegram processor stream also signals cancellation to the agent runtime.

Agent switching is unsupported in Telegram. Configure a separate channel for each agent. This integration does not provide an agent selection menu.
