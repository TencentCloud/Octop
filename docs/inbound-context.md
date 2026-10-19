# Gateway inbound request context

Octop supplies `configurable.octop_inbound_context` to the expert runtime for
each gateway chat invocation. It separates the current platform sender from
the Octop account in the existing `user` request field. For IM messages,
`user` is the expert owner's Octop account; several members of the same bot
can share that value.

The context is internal server-generated request data, not a client-settable
HTTP field or an authorization token. Its presence does not imply a WeCom
message or a resolved sender. Consumers must handle an absent context and
`sender: null`.

## Channel coverage and absence

| Invocation path | Context | `sender` |
| --- | --- | --- |
| WeCom through `GlobalProcessor` | Present | `{namespace, id}` only when the adapter identity passes the checks below; otherwise `null` |
| Other IM channels through `GlobalProcessor` (Feishu, DingTalk, Telegram, QQ, Slack, Discord, WeChat, etc.) | Present, with the actual channel type and instance | Always `null`; these adapters do not yet have a sender contract here |
| Dashboard and CLI through `GlobalProcessor` | Present, with `channel_type: "dashboard"` or `"cli"` | Always `null`, including continuation of a thread originally created on WeCom |
| Direct harness calls without an inbound context, including cron agent runs | Key omitted | No current inbound sender; middleware renders the context as `null` |

An unsupported or unknown channel does not acquire a sender by supplying
WeCom-shaped metadata. Direct callers of `build_harness_request` may omit
the optional `inbound_context` argument; this preserves the previous request
shape. Neither `source`, a session key, nor a persisted thread's channel
causes the builder to infer a context or sender.

## Fields

When the context is present, it contains these fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `channel_type` | string | Current `InboundMessage.channel_type`, or `"unknown"` when absent |
| `channel_id` | string | Current channel instance ID, not a conversation ID |
| `octop_user_id` | integer | Resolved Octop account ID, matching request `user` (which remains a string); IM uses the expert owner, Dashboard/CLI use the acting account |
| `sender` | object or `null` | Resolved WeCom sender: `namespace: "wecom:<channel_id>"` and `id: "<platform userid>"`; otherwise `null` |
| `chat_type` | string | `"dm"` or `"group"`, using existing gateway chat-type resolution |
| `conversation_id` | string or `null` | Normalized adapter `metadata.chat_id`; for DMs only, falls back to `channel_subject.subject_id` |
| `message_id` | string or `null` | Normalized adapter `metadata.msgid`; not a universal message-ID mapping for other channels |
| `locale` | string | Resolved and normalized `"zh"` or `"en"` |

Sender, conversation, and message identifiers are stripped of surrounding
whitespace. Non-string, empty, whitespace-only, and case-insensitive
`"unknown"` values resolve to `null`.
Conversation/message IDs are routing data and must not be treated as sender
identity or as guaranteed to exist on every channel.

For example, a resolved WeCom sender yields:

```json
{
  "source": "wecom/channel-example",
  "user": "1",
  "configurable": {
    "octop_inbound_context": {
      "channel_type": "wecom",
      "channel_id": "channel-example",
      "octop_user_id": 1,
      "sender": {
        "namespace": "wecom:channel-example",
        "id": "platform-user-example"
      },
      "chat_type": "dm",
      "conversation_id": "platform-user-example",
      "message_id": "message-example",
      "locale": "zh"
    }
  }
}
```

## Identity and security boundary

The WeCom adapter derives both `metadata.to_handle` and
`channel_subject.subject_id` from the platform sender
(`from.userid`, with the adapter's `from.user_id` compatibility fallback).
Octop populates `sender` only if the actual channel type is `"wecom"`,
the channel instance ID is nonempty, and both normalized identity fields
are valid and equal. Missing or conflicting identity produces `sender: null`;
it does not fall back to the Octop owner or reject an otherwise valid chat.

The two fields come from the same adapter event: checking their agreement is
a consistency check, not independent authentication. Trust still depends on
the platform connection and the server-controlled adapter. Message text,
claimed usernames, `KHT_CALLER`, session keys, `metadata.sender_id`, and a
caller-supplied `metadata.octop_inbound_context` are not identity sources.
Compare the complete `(sender.namespace, sender.id)` pair so identical user
IDs on different channel instances remain distinct.

Only the documented fields are projected. Raw frames, WebSocket clients,
reply URLs, and media decryption keys are excluded. The context is sent to
the configured model in its system message, so the documented account,
sender, and routing identifiers are visible to that model provider.
The localized prompt treats field values as data and instructs the model
not to infer identity from history or user claims; that prompt is not an
enforcement mechanism. Tools and business services must perform their own
authorization and handle unresolved identity explicitly.

## Lifetime and compatibility

`InboundContextMiddleware` reads the current invocation's config on every
model call, in both synchronous and asynchronous paths. It preserves the
existing system content, appends the localized context block, and does not
cache sender identity on the shared expert instance or add the block to
conversation messages. This is not a promise that runtime config, provider
logs, or traces contain no identifiers; consumers must not recover the
current sender from historical state.

Text, multimodal content, and explicit `messages` requests all carry the
same optional context. The existing `source`, `user`, session keys, thread
ownership, and tool permissions retain their semantics. Other middleware
must not require this field, assume that a present context has a sender,
or use it to grant access. Supporting sender identities on another channel
requires an explicit adapter contract and corresponding regression tests.
