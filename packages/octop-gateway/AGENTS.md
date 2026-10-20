# AGENTS.md

Navigation guide for AI coding agents working in this repository.

The working directory and distribution are **`octop-gateway`**; the import package is `octop_gateway`.

## 1. Collaboration principles

> Favor caution over speed; trivial tasks may relax these rules. These principles complement [§12 Change workflow](#12-change-workflow) and [§13 Communication](#13-communication).

### Think before writing

- Read first — copy the existing channel with the closest protocol (Feishu/DingTalk for SDK callbacks, WeCom for streaming, Telegram for bot polling) instead of inventing a new abstraction.
- State assumptions up front; ask when unsure. When several interpretations exist, list them and let the user choose — do not pick one silently.
- Check scope — bug fix, new channel, and refactor each have different success criteria (see [§12](#12-change-workflow)).
- Push back when a simpler approach exists.

### Simplicity first

- Write the minimum code that solves the problem; no unrequested features, abstractions, or config knobs.
- No defensive error handling for scenarios that cannot realistically happen.
- Match the existing channel style even when you would do it differently.

### Surgical edits

- Touch only lines directly related to the task; do not opportunistically "clean up" nearby code, comments, or formatting.
- Do not refactor unrelated broken code — mention it, do not fix it unless asked.
- Remove orphan imports, variables, and functions **you** introduced.
- **Channel-specific:** inside subclass methods call `self._send_*` only — never `self.reply_*` / `self.push_*` (throttle hygiene, see [§8 Outbound API](#outbound-api-reply--push--_send)).

### Verifiable outcomes

| Task | Plan | Verify |
|------|------|--------|
| Bug fix | Reproduce with a failing test → fix → run the suite | `make test` passes; the new test fails before the fix |
| New channel | Copy the closest existing channel → implement required methods → tests + example | `tests/channels/test_{name}.py` passes; `make lint` clean |
| Behavior change | Add the test for the new behavior → implement | targeted `pytest tests/...`, then `make test` |
| Refactor | `make test` before → refactor → `make test` after | zero behavior change unless requested |

**Ship bar:** `make all` (format + lint + typecheck + test) — exactly what the pre-commit hook runs. Enable the hook once per clone with `make install-hooks` (see [§6](#6-run-commands)).

For multi-step work, state a short plan with verify steps:

```
1. Read feishu.py media upload pattern → verify: understand _send_media flow
2. Implement _send_media in {name}.py → verify: pytest tests/channels/test_{name}.py -k media
3. Run the full suite → verify: make test && make lint
```

## 2. What this is

Multi-platform IM channel bridge with a unified message abstraction for AI agents and bots.

Core pattern: a `MessageProcessor` (async generator) feeds events through a `BaseChannel` managed by `ChannelManager`.

Built-in channels: Discord, QQ, Feishu (Lark), DingTalk, WeCom (Enterprise WeChat), WeChat iLink, Yuanbao, Xiaoyi, MQTT, Telegram.

| Platform | Channel kind | Transport | Text | Media |
|----------|--------------|-----------|------|-------|
| Discord | `discord` | Gateway WebSocket + REST | ✅ | ✅ |
| 飞书（Lark） | `feishu` | WebSocket + REST | ✅ | ✅ |
| 钉钉 | `dingtalk` | Stream | ✅ | ✅ |
| QQ | `qq` | WebSocket | ✅ | ✅ |
| 企业微信 | `wecom` | Callback + API | ✅ | ✅ |
| 微信 iLink | `weixin` | HTTP long-poll | ✅ | ✅ |
| 元宝 | `yuanbao` | HTTP REST | ✅ | ✅ |
| 小艺 | `xiaoyi` | WebSocket | ✅ | ✅ |
| MQTT | `mqtt` | MQTT | ✅ | ✅ |
| Telegram | `telegram` | Long-polling | ✅ | ✅ |

## 3. Tech stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.12+ — `from __future__ import annotations` in every source file |
| Async runtime | `asyncio`; SDK callback threads must re-enter the loop via `self.enqueue()` |
| Data models | Pydantic v2 (`BaseModel`, discriminated unions) |
| HTTP | `aiohttp` (channel HTTP), `httpx` where a platform SDK pulls it in |
| Platform SDKs | `lark-oapi`, `dingtalk-stream`, `discord.py`, `python-telegram-bot`, `wecom-aibot-sdk`, `paho-mqtt`, `websockets`, `python-socketio` |
| Packaging | hatchling; `uv` for local dev (`uv sync --extra dev`) |
| Quality gates | ruff (lint + format, line length 120), mypy strict, pytest + pytest-asyncio |

## 4. Package layout

```
src/octop_gateway/
├── models.py          # InboundMessage, MessageEvent, ContentPart, ChannelSubject, GroupContext
├── channel.py         # BaseChannel ABC + ChannelConfig + shared inbound pipeline + media flow
├── manager.py         # ChannelManager (queue, workers, session batching, push, add_*_channel)
├── constraints.py     # ChannelConstraints, RateLimiter, ReplyTimeoutGuard, TypingKeepalive
├── group_context.py   # Group activation policy + short-lived passive-chatter buffer
├── push_routing.py    # Proactive (bot-initiated) push metadata helpers
├── media.py           # MediaBackend ABC + FileSystemMediaBackend
├── utils.py           # Debouncer, content helpers
└── channels/          # one module per platform; lazy-loaded via channels/__init__.py
    ├── discord.py  feishu.py  dingtalk.py  wecom.py  mqtt.py
    ├── qq/            # channel.py + stream.py
    ├── telegram/      # channel.py
    ├── weixin/        # api.py + login_qr.py + media.py
    ├── xiaoyi/  yuanbao/
    └── __init__.py    # _CHANNEL_MAP + _CLASS_NAMES + ChannelKind + SUPPORTED_CHANNEL_KINDS
tests/                 # pytest, mirrors src/ (`tests/channels/test_{name}.py` per channel)
examples/              # runnable demos (`{name}_bot.py`, `all_channels.py`, `advanced/`, `backends/`)
```

Change-mapping cheat sheet:

| To change… | Look at… |
|------------|----------|
| Message / content models | `models.py` |
| Shared inbound pipeline, media, throttling | `channel.py` |
| Queueing, worker loops, push, `add_*_channel` | `manager.py` |
| Rate limits, reply timeout, typing keepalive | `constraints.py` |
| Group activation / passive context | `group_context.py` |
| Proactive push routing | `push_routing.py`, `BaseChannel.resolve_push_subject` |
| Storage for inbound / outbound bytes | `media.py` |
| One platform | `channels/{kind}.*` plus registration in `channels/__init__.py` |

## 5. Architecture

```
platform SDK / webhook ─► parse_inbound() ─► InboundMessage ─► _preprocess_inbound()
                                                                        │
                                    _persist_media + GroupContextManager.prepare
                                                                        ▼
_prepare_inbound ─► _process_inbound ─► MessageProcessor ─► MessageEvent stream
        ▲                                                               │
        └── _finalize_inbound ◄──────────────────── _send_text / _send_content / _send_media
```

Two module tiers:

| Tier | Modules | Rule |
|------|---------|------|
| Core | `models.py`, `channel.py`, `manager.py`, `constraints.py`, `media.py`, `utils.py`, `group_context.py`, `push_routing.py` | Platform-agnostic; must not import any `channels/*` module |
| Channel adapters | `channels/*` | May import core freely; adapters never import each other |

`channels/__init__.py` is the only registration point (`_CHANNEL_MAP`, `_CLASS_NAMES`, `ChannelKind`, guarded by a parity test) and loads every platform SDK lazily, so importing `octop_gateway` never drags in Discord/Telegram/… .

### Media flow architecture

```
ChannelManager(media_backend=FileSystemMediaBackend("/tmp/media"))
    │ set_media_backend() before start()
    ▼
BaseChannel._persist_media(msg):                 # inbound auto-persist
    data = self.fetch_remote_media(url)          ← platform auth GET (override)
    backend.save(data, key)                      ← pluggable storage
    part.local_path = key                        ← MediaBackend key

BaseChannel.load_media_bytes(part):              # outbound read (used in _send_media)
    1. part.data       → base64.b64decode(...)            # zero I/O
    2. part.local_path → backend.read(local_path)          # backend REQUIRED
    3. part.url        → fetch_remote_media(url) + cache  # backend optional
```

## 6. Run commands

```bash
make install-hooks     # once per clone: enable the .githooks pre-commit gate
make all               # format + lint + typecheck + test (ship bar)
make install           # uv sync --extra dev
make format            # ruff check --fix + ruff format (rewrites files)
make lint              # ruff check + ruff format --check
make typecheck         # mypy src
make test              # pytest -m "not integration"
make test-integration  # pytest -m integration (needs env vars + network)
make build             # build wheel + sdist
```

Run a single test while iterating: `uv run pytest tests/channels/test_feishu.py -k media -xvs`.

**Git hooks (required before committing):** run **`make install-hooks`** once per clone. It sets `core.hooksPath=.githooks`, so every `git commit` first runs **`make all`** (`format` rewrites files, then lint / typecheck / test). Staged files rewritten by `format` are re-added automatically, so the commit contains the formatted content. This supersedes `pre-commit install` — `core.hooksPath` overrides `.git/hooks/`. Bypass only in emergencies: `SKIP_PRECOMMIT=1 git commit …` or `git commit --no-verify`; never skip the hook to land a red suite.

### Environment (.env)

Credentials live in `.env` (git-ignored); the template is `.env.example`:

- `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL_NAME` — for examples
- `DISCORD_BOT_TOKEN`, `DISCORD_ALLOW_ALL_CHANNELS`, `DISCORD_ALLOWED_CHANNEL_IDS`, `DISCORD_ALLOWED_USER_IDS`, `DISCORD_HTTP_PROXY`, `DISCORD_HTTP_PROXY_AUTH`
- `QQ_APP_ID`, `QQ_TOKEN`, `QQ_SECRET`
- `FEISHU_APP_ID`, `FEISHU_APP_SECRET`
- `DINGTALK_APP_KEY`, `DINGTALK_APP_SECRET`
- `WECOM_BOT_ID`, `WECOM_SECRET`
- `WEIXIN_ACCOUNT_ID`, `WEIXIN_TOKEN`, `WEIXIN_BASE_URL`
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_HTTP_PROXY`, `TELEGRAM_SHOW_TYPING`
- `MQTT_HOST`, `MQTT_PORT`, `MQTT_USERNAME`, `MQTT_PASSWORD`, …
- `XIAOYI_AK`, `XIAOYI_SK`, `XIAOYI_AGENT_ID`

## 7. Data models

### InboundMessage

Normalized message from user to bot (parsed from the platform-native format by `parse_inbound()`).

| Field | Meaning |
|-------|---------|
| `channel_id` | UUID instance ID (auto-generated) |
| `channel_type` | `"qq"`, `"feishu"`, `"dingtalk"`, … |
| `tenant_id` | Optional tenant identifier |
| `channel_subject` | Reply / conversation target (see below) |
| `channel_session_id` | Platform connection session (NOT user identity) |
| `content` | `list[ContentPart]` — text, image, video, audio, file |
| `group_context` | `GroupContext | None` — short-lived passive group chatter |
| `metadata` | Platform-specific routing info (`msg_id`, `to_handle`, `sender_id`, …) |
| `timestamp` | Message timestamp (default `time.time()`) |

**`channel_subject` semantics — read this before touching group support.** `channel_subject` is the **reply/conversation target**: a user for direct messages, the **conversation ID** for group messages. The individual author of a group message stays in `metadata.sender_id` / `metadata.sender_name` so every member of the group shares one thread without losing attribution. The legacy `sender_id` field is gone — do not reintroduce it.

### ChannelSubject

Known subject that has interacted with a channel. Used for proactive push and as the unified routing handle for all outbound operations.

```python
@dataclass
class ChannelSubject:
    subject_id: str  # Unique identifier (openid, user_id, conversation id, …)
    first_seen: float | None = None
    last_seen: float | None = None
    display_name: str = ""
    chat_type: str = ""  # "direct", "group", etc.
    metadata: dict[str, Any] = {}  # Platform-specific routing extras
```

`metadata` carries the routing context extracted from the last inbound message (e.g. `msg_id`, `webhook_url`, `chat_id`). The channel updates it on every inbound message so it always holds the most recent routing context. Proactive pushes go through `push_routing.py`, which strips turn-scoped keys before sending.

### ContentPart types

Unified content type system using Pydantic discriminated unions:

| Type | Class | Fields |
|------|-------|--------|
| `text` | `TextContent` | `text` |
| `image` | `ImageContent` | `url`, `alt_text`, `width`, `height`, `size`, `mime_type`, `local_path`, `data` |
| `video` | `VideoContent` | `url`, `duration`, `thumbnail_url`, `size`, `mime_type`, `local_path`, `data` |
| `audio` | `AudioContent` | `url`, `duration`, `size`, `mime_type`, `local_path`, `data` |
| `file` | `FileContent` | `url`, `filename`, `size`, `mime_type`, `local_path`, `data` |

Each media part carries up to three byte sources, in priority order (highest first):

| Field | Type | Description |
|-------|------|-------------|
| `data` | `str` (base64) | Agent already holds bytes in memory — most efficient path |
| `local_path` | `str` | MediaBackend key (not a filesystem path) — requires a configured backend |
| `url` | `str` | External URL — fetched via `fetch_remote_media()` |

### MessageEvent

Event emitted by the message processor back to the channel for delivery.

```python
class MessageEvent(BaseModel):
    type: MessageEventType  # MESSAGE, DELTA, THINKING, THINKING_DELTA, FLUSH, TYPING, TOOL_START, TOOL_END, ERROR, COMPLETED
    content: list[ContentPart]
    metadata: dict[str, Any] = {}
    error: str | None = None
```

Factory methods: `MessageEvent.text()`, `.delta()`, `.thinking()`, `.thinking_delta()`, `.flush()`, `.typing()`, `.tool_start()`, `.tool_end()`, `.completed()`, `.error_event()`.

### GroupContext

Structured, short-lived group context attached to the triggering message (`group_context.py` owns the policy):

```python
class GroupContext(BaseModel):
    conversation_id: str
    visibility: str          # how much the platform exposes to the bot
    activation: str          # when the bot replies
    messages: list[GroupContextMessage] = []
    capability_degraded: bool = False
```

`GroupContextConfig` (per-channel, serializable, with per-group overrides) separates two orthogonal ideas: **visibility** (what the platform lets the bot see) and **activation** (when the bot actually starts an agent turn). Non-triggering group messages are buffered as passive context and never enter the durable conversation thread.

## 8. Channel specification

Every channel MUST follow these conventions consistently.

1. **Inherit `BaseChannel`** — every channel subclasses it.
2. **Required methods**: `start()`, `stop()`, `_send_text()`, `_send_content()`, `_send_media()`, `parse_inbound()`.
3. **Constructor signature**: `__init__(self, processor, config, *, channel_id=None, tenant_id=None, debounce_seconds=0.0, constraints=None)`.
4. **Config**: `@dataclass` inheriting `ChannelConfig` with platform-specific fields (`app_id`, `secret`, …). `ChannelConfig` provides `channel_id`, `tenant_id`, and `from_dict()`.
5. **Thread safety**: if the platform SDK uses callback threads (`lark-oapi`, `wecom-sdk`, `discord.py`), use `self.enqueue()` — it dispatches via `call_soon_threadsafe` to the main event loop.
6. **Logging**: `logger = logging.getLogger(__name__)`; INFO for lifecycle/messages, DEBUG for protocol details.
7. **Error handling**: never crash the worker — log exceptions and continue.
8. **Deduplication**: implement `_is_duplicate(msg_id)` with an `OrderedDict` LRU (max 1000 entries).
9. **Tests**: each channel needs `tests/channels/test_{name}.py` with mock-based unit tests (no network).
10. **Media URLs**: always handle a `//` prefix (prepend `https:`) and missing schemes.
11. **Throttle hygiene**: inside subclass methods always call the sibling `self._send_*` helpers (never `self.reply_*` / `self.push_*`); the public entry points already acquire one rate-limit slot per user-visible message.
12. **Inbound template**: do not override `handle_inbound`; use `_preprocess_inbound` for platform normalization/decryption and `_process_inbound` for custom delivery protocols, so media, subject tracking, and group-context policy always run exactly once.

### Connection model

Most channels use **persistent connections** (WebSocket / stream / long-poll). Exceptions:

| Platform | SDK / Protocol |
|----------|----------------|
| Discord | `discord.py` — Gateway WebSocket |
| QQ | `websockets` — QQ Gateway WebSocket |
| Feishu | `lark_oapi.ws.Client` — Lark WebSocket long connection |
| DingTalk | `dingtalk-stream` — DingTalk Stream SDK |
| WeCom | `wecom_aibot_sdk.WSClient` — WeCom WebSocket |
| Weixin | HTTP long-poll / iLink bot API |
| Xiaoyi | WebSocket (primary + backup connections) |
| MQTT | `paho-mqtt` — broker subscribe/publish |
| Telegram | `python-telegram-bot` long-polling updater |
| Yuanbao | HTTP REST API (inbound via webhook/callback enqueue) |

### channel_session_id convention

`InboundMessage.channel_session_id` represents the **platform connection session**, NOT the user identity.

- Set `self._connection_session: str | None = None` in `__init__`.
- Assign it when the connection is established (READY event, authenticated callback, …). QQ derives it per event via `_resolve_session_from_event()`.
- Fallback: `"{channel_id}-unconnected"` if not yet connected.
- This session changes on every reconnect — it is NOT persistent across restarts.

**Conversation thread management is the processor's responsibility** (via `thread_id` in octop-harness), NOT the channel's. The channel only reports platform facts.

### MediaBackend & media flow

A single `MediaBackend` instance is the only file-I/O contract. All bytes — inbound persistence and outbound sends — flow through it.

**Default backend:** when `ChannelManager` is constructed without `media_backend=`, `start()` installs `FileSystemMediaBackend("/")` and propagates it to every channel. This is intentional: storage keys are namespaced (`{channel_type}/{channel_id}/…`), so callers can treat `/` as a transparent root and share the same backend with octop-harness examples (agent tool `file://` paths that already sit under that root reuse their key without copying). Override with an explicit root (e.g. `FileSystemMediaBackend("/tmp/octop-gateway/media")`) when you want filesystem isolation.

Per-channel responsibilities:

```python
class {Name}Channel(BaseChannel):
    async def fetch_remote_media(self, url: str) -> tuple[bytes, str]:
        """Override only if the platform's media URLs need auth headers."""
        token = await self._refresh_token()
        http = await self._ensure_http()
        async with http.get(url, headers={"Authorization": f"Bearer {token}"}) as r:
            r.raise_for_status()
            return await r.read(), r.content_type

    async def _send_media(self, subject: ChannelSubject, media: ContentPart) -> None:
        """Read bytes through MediaBackend, then upload to the platform."""
        data, mime = await self.load_media_bytes(media)        # ← MediaBackend
        platform_id = await self._upload_to_platform(data, mime)  # private helper
        await self._send_with_platform_id(subject, platform_id)
```

Rules:

- `fetch_remote_media` defaults to a plain HTTP GET via `self._ensure_http()`. Override only when the platform's URLs require auth.
- `load_media_bytes` is the **only** way channels read file bytes for outbound. Priority: `part.data` → `part.local_path` → `part.url`. A `local_path` set without a configured `MediaBackend` is a misconfiguration and raises `RuntimeError` — never silently fall through to the URL.
- `_persist_media` (called by `handle_inbound`) writes inbound media to the backend via `fetch_remote_media` and stamps `part.local_path` with the key.
- Platform upload helpers are channel-private (`_upload_image_to_feishu`, `_upload_to_dingtalk`, …). Their signatures match the platform API; there is no shared upload abstraction because every platform's upload protocol diverges (multipart vs URL pass-through, image_key vs media_id, …).

### Outbound API: reply / push / _send

`BaseChannel` exposes three layers for outbound messages. Pick the right one based on **who is calling**, not on what is being sent.

| Layer | Methods | Caller / context | Throttling |
|-------|---------|------------------|------------|
| **Public reply** | `reply_text(subject, text)` / `reply_content(subject, parts)` / `reply_media(subject, media)` | Inbound flow (`handle_inbound` and the constraint hooks). Routing is fully determined by `subject` (`subject_id` + `metadata`). | Each call acquires **exactly one** rate-limit slot before delegating to `_send_*`. |
| **Public push** | `push_text(subject, text)` / `push_message(subject, parts)` | Bot-initiated (scheduled jobs, webhooks, admin pushes). Also exposed as `ChannelManager.push_text` / `push_content`. | Each call acquires one slot, then calls `_send_text` / `_send_content` directly (no nested re-acquire). |
| **Platform primitives** | `_send_text(subject, text)` / `_send_content(subject, parts)` / `_send_media(subject, media)` (abstract) | Subclasses implement these — the only place that talks to the platform SDK / HTTP. | Never acquire here. The public layer owns the throttle. |

**Throttle hygiene** (the rule that makes one-call-one-acquire work):

> Inside any subclass method, call `self._send_*`, never `self.reply_*` or `self.push_*`.

If `_send_content` fans out to `_send_text` per part, or `_send_media` falls back to `_send_text`, the public reply / push call still consumes a single rate-limit slot. Calling `self.reply_text` from inside a subclass would acquire a second slot for the same logical user-visible message and under heavy load could deadlock against itself.

`ChannelManager` keeps the same shape: `manager.push_text(channel_id, subject, …)` forwards to `channel.push_text(subject, ...)`, which routes through the same `_acquire_rate_slot` → `_send_text` path.

### _send_media() requirement

Every channel MUST implement `_send_media()`. Three patterns are valid; pick the one matching the platform's protocol.

**1. Native bytes upload** (feishu, dingtalk, discord, qq c2c/group, telegram)

```python
async def _send_media(self, subject: ChannelSubject, media: ContentPart) -> None:
    try:
        data, mime = await self.load_media_bytes(media)  # MediaBackend
        platform_id = await self._upload_to_platform(data, mime)
        await self._send_with_platform_id(subject, platform_id)
    except Exception:
        # On failure, fall back to text so the message is not silently dropped
        url = self._get_media_url(media)
        label = self._get_media_label(media)
        if url:
            await self._send_text(subject, f"[Attachment: {url}]")
        elif getattr(media, "data", None) or getattr(media, "local_path", None):
            await self._send_text(subject, f"[{label} (local upload failed)]")
```

**2. URL-only protocol** (qq guild, yuanbao, mqtt) — must emit a clear text marker when only inline bytes (`data` / `local_path`) are present, never silently drop the part:

```python
url = self._get_media_url(media)
if url:
    # post URL to platform
    ...
elif getattr(media, "data", None) or getattr(media, "local_path", None):
    label = self._get_media_label(media)
    await self._send_text(subject, f"[{label} (local file, not deliverable on <Platform>)]")
```

Or, if the protocol can carry inline data URLs (Socket.IO etc.):

```python
has_inline = bool(getattr(media, "data", None) or getattr(media, "local_path", None))
if not url and has_inline:
    raw, mime = await self.load_media_bytes(media)  # handles data + local_path
    url = f"data:{mime};base64,{base64.b64encode(raw).decode()}"
```

**3. Pure text fallback** (weixin, wecom — protocol has no media support)

```python
url = self._get_media_url(media)
label = self._get_media_label(media)
if url:
    await self._send_text(subject, f"[{label}: {url}]")
elif getattr(media, "data", None) or getattr(media, "local_path", None):
    await self._send_text(subject, f"[{label} (local file, not deliverable on <Platform>)]")
```

**Hard rule**: never `return` silently when `data` or `local_path` is present — always emit a visible marker so loss of media is observable upstream.

### Local-image support matrix

| Channel | Inbound URL | C2C/group bytes | Guild/DM bytes | Local-only fallback |
|---------|-------------|-----------------|----------------|---------------------|
| feishu  | Bearer-auth | ✅ multipart upload | ✅ same  | text marker on error |
| dingtalk | downloadCode + Bearer | ✅ OAPI media/upload | n/a | text marker on error |
| discord | public CDN | ✅ `discord.File` upload | ✅ same | text marker on error |
| qq | QQBot OAuth | ✅ base64 `file_data` | ⚠ guild requires public URL | text marker for guild-only |
| telegram | public CDN | ✅ `send_photo` / document upload | ✅ same | text marker on error |
| yuanbao | Bearer | URL-only protocol | n/a | text marker |
| mqtt | n/a | URL in payload | n/a | text marker |
| weixin  | bot-token | no media support | n/a | text marker |
| wecom   | none | no media support | n/a | text marker |
| xiaoyi | platform auth | per platform API | n/a | text marker |

### Typing indicator support matrix

While the processor is still working, `BaseChannel.handle_inbound` runs a `TypingKeepalive` loop that calls `_send_typing_indicator` every `typing_keepalive_interval` seconds. Channels with a real platform API override this method; the rest leave the inherited no-op.

| Channel | Native API | `_send_typing_indicator` | Default keepalive interval |
|---------|------------|--------------------------|----------------------------|
| weixin   | `ilink/bot/sendtyping` | ✅ POST with bot token | 5.0 s |
| discord  | `Channel.typing()` | ✅ | 8.0 s |
| telegram | `sendChatAction(typing)` | ✅ | 4.0 s (when `show_typing=True`) |
| qq       | none | ❌ no-op | 0 (disabled) |
| dingtalk | none | ❌ no-op | 0 |
| feishu   | none (emoji ack only) | ❌ no-op | 0 |
| wecom    | "thinking bubble" via stream replies | ❌ no-op (covered by the stream override) | 0 |
| yuanbao  | none | ❌ no-op | 0 |
| mqtt / xiaoyi | none | ❌ no-op | 0 |

**Convention**: a channel enables typing keepalive by setting `typing_keepalive_interval > 0` in `_default_constraints()` AND overriding `_send_typing_indicator`. Setting only the interval makes the loop run but call a no-op (wasted work). Setting only the override without an interval means the keepalive never fires.

### ChannelConstraints

Each channel SHOULD override `_default_constraints()` with platform-specific defaults:

```python
def _default_constraints(self) -> ChannelConstraints:
    return ChannelConstraints(
        send_rate_limit=(20, 60.0),  # Platform rate limit
        reply_timeout=180,  # Platform reply window (seconds, 0=no timeout)
        timeout_strategy="placeholder",  # "placeholder" | "none"
        show_thinking=False,  # Whether to show <think> blocks
        show_tool_hints=True,  # Whether to show tool activity
    )
```

`timeout_strategy` takes only two values:

- **"placeholder"** — when `reply_timeout * 0.8` elapses without a real reply, `BaseChannel` sends one message picked from `placeholder_texts` (e.g. "⏳ thinking..."). Streaming channels (WeCom) handle this in their own override by emitting the placeholder via `reply_stream(finish=False)` before the first real token.
- **"none"** — disable the timeout fallback entirely. Use this on platforms with no hard reply deadline.

### Streaming channel overrides

Channels whose protocol pushes partial updates of *the same logical user-visible message* override `handle_inbound` directly (currently only WeCom's `reply_stream`). They must:

1. Acquire **exactly one** rate-limit slot before the stream loop starts. Subsequent partial updates are not separate sends; do not re-acquire.
2. When `timeout_strategy == "placeholder"` and `reply_timeout > 0`, wrap the *first* processor event in a bounded wait. On timeout, emit the placeholder via the stream API and continue waiting for the real event (do NOT cancel the underlying processor — use `asyncio.wait` rather than `asyncio.wait_for`).
3. Use `self._constraints.placeholder_text` for terminating error chunks so manager-level overrides (`manager.set_constraints(placeholder_texts=...)`) take effect.

Everything else overrides `_process_inbound` (QQ stream, Xiaoyi) or `_preprocess_inbound` (Weixin) and keeps the shared `_prepare_inbound` / `_finalize_inbound` lifecycle intact.

### Debounce key

`get_debounce_key()` returns `channel_subject.subject_id` (inherited from `BaseChannel`) for per-user message serialization. Override only if the platform requires different batching logic (e.g. per-group).

### parse_inbound() specification

`parse_inbound()` MUST return a complete `InboundMessage`:

```python
def parse_inbound(self, raw_payload: Any) -> InboundMessage:
    # ... parse platform payload ...

    return InboundMessage(
        channel_id=self.channel_id,  # UUID instance ID (auto-generated)
        channel_type=self.channel_type,  # "qq", "feishu", "dingtalk", ...
        tenant_id=self._tenant_id,  # Optional tenant identifier (config or kwarg)
        channel_subject=ChannelSubject(  # Reply / conversation target
            subject_id=open_id,  # User id for DMs, conversation id for groups
            display_name=name,
            chat_type="direct",  # or "group"
            metadata={  # Routing extras for _send_* implementations
                "msg_id": msg_id,
                "to_handle": reply_destination,
                # ... platform-specific fields
            },
        ),
        channel_session_id=self._connection_session,  # Platform connection session
        content=content_parts,  # [TextContent, ImageContent, ...]
        metadata={  # Platform-specific routing info (copy of subject.metadata)
            "event_type": ...,
            "msg_id": ...,
            "to_handle": ...,
            # Group adapters also set sender_id / sender_name here
        },
    )
```

**Important**: do NOT set `sender_id` on `InboundMessage` — it has been removed. Identify the target via `channel_subject.subject_id`; keep the group author in `metadata.sender_id` / `metadata.sender_name`.

## 9. Code style

### Language & runtime

- Python 3.12+, `from __future__ import annotations` on **all** source files.
- ALL comments and docstrings are written in **English**.

### Formatter & linter (mandatory gate)

- **ruff** is the single tool for both linting and formatting. The gate is `make all`, which the pre-commit hook runs for you:

  ```bash
  make all     # format + lint + typecheck + test (must be green before committing)
  make format  # ruff check --fix + ruff format (rewrites files)
  make lint    # ruff check + ruff format --check
  ```

- Line length: **120** characters (`line-length = 120` in `pyproject.toml`).
- `ruff check . --fix` may be used for safe auto-fixes; use `--unsafe-fixes` only when reviewed.

### PEP 8 compliance (enforced by ruff)

The following rules are actively checked and **must not be violated**:

| Category | Rule | Requirement |
|----------|------|-------------|
| Imports | E401 | One import per line |
| Imports | E402 | Module-level imports at top of file; use `# noqa: E402` only for path-manipulation patterns (try/except `sys.path`) |
| Imports | F401 | No unused imports |
| Imports | F811 | No redefined names |
| String | UP031 | Use f-strings instead of `%-format` |
| String | RUF001 | No ambiguous Unicode characters in code; add `# noqa: RUF001` only for intentional CJK UI strings |
| Types | UP038 | Use `X | Y` in `isinstance()` instead of `(X, Y)` |
| Types | UP006/UP007 | Use built-in generics (`list[T]`, `dict[K,V]`, `T | None`), never `typing.List/Dict/Optional` |
| Logic | SIM103 | Return conditions directly instead of `if …: return True; return False` |
| Logic | SIM117 | Combine nested `with` statements into a single `with` |
| Tasks | RUF006 | Store `asyncio.create_task()` return value; add a done-callback to a set to prevent GC |
| Variables | F841 | No assigned-but-never-used local variables |
| `__all__` | RUF022 | `__all__` must be isort-sorted |

### Naming conventions

- Functions / variables: `snake_case`
- Classes / exceptions: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`
- Private helpers: single leading `_`; truly private: double `__`

### Type annotations

- All public methods and module-level functions must be fully annotated.
- No mutable default arguments; use `dataclasses.field(default_factory=...)`.
- Prefer modern union syntax: `str | None` over `Optional[str]`.
- Use `list[T]` / `dict[K, V]` (PEP 585), never `List` / `Dict` from `typing`.

### Imports

- Order: `__future__` → stdlib → third-party → local; one blank line between groups.
- Sorted alphabetically within each group (ruff / isort enforces this).
- `from module import *` is forbidden.
- Internal private symbols (prefixed `_`) must NOT be re-exported from `__init__.py` unless intentional.

### Docstrings & comments

- Triple double-quotes `"""` for all docstrings.
- Module, class, and public method docstrings are required.
- Inline comments: `# ` (hash + one space), placed above the relevant line.
- TODO format: `# TODO(name): description`.

### Error handling

- Catch specific exceptions, never bare `except:`.
- Re-raise with `raise` (not `raise exc`) to preserve the traceback.
- Never silently swallow exceptions in channel workers — log and continue.

## 10. Do not

- Do not override `handle_inbound` unless the protocol genuinely streams partial updates (currently only WeCom). Use `_preprocess_inbound` / `_process_inbound` (see [§8](#streaming-channel-overrides)).
- Do not call `self.reply_*` / `self.push_*` from inside `_send_*` or any other subclass method.
- Do not read `part.data` / `part.local_path` / `part.url` directly for outbound bytes — use `load_media_bytes()`.
- Do not silently drop a media part when `data` / `local_path` is present; always emit a visible text marker.
- Do not set `sender_id` on `InboundMessage` — it was removed. Use `channel_subject.subject_id` (+ `metadata.sender_id` for group authors).
- Do not import `channels/*` from core modules, and do not import one channel from another.
- Do not add a channel without registering it in `_CHANNEL_MAP` + `_CLASS_NAMES`.
- Do not push platform quirks into `BaseChannel`; keep them in the adapter.
- Do not block the event loop — no synchronous HTTP, `time.sleep`, or heavy CPU work in async channel code.
- Do not commit credentials; `.env` is git-ignored.

## 11. Where to look

| Question | Location |
|----------|----------|
| How does the inbound pipeline work? | `channel.py` → `handle_inbound` / `_prepare_inbound` / `_process_inbound` / `_finalize_inbound` |
| How is a group message activated? | `group_context.py`, `GroupContextConfig` on the channel config |
| How do proactive pushes route? | `push_routing.py`, `BaseChannel.resolve_push_subject` |
| How does media persist and get read back? | `media.py`, `BaseChannel._persist_media` / `load_media_bytes` |
| How are rate limits and timeouts applied? | `constraints.py`, `BaseChannel._acquire_rate_slot` |
| Who owns conversation threads? | The processor (octop-harness); the channel only reports `channel_session_id` |
| Discord / Feishu / … specifics | `channels/{kind}.py` or `channels/{kind}/` |
| What config fields exist? | `ChannelConfig.from_dict` + each `{Name}Config` |
| Working example wiring | `examples/*_bot.py`, `examples/all_channels.py`, `examples/advanced/` |
| Release flow & hooks | [§12](#12-change-workflow); `CONTRIBUTING.md` |
| Test layout | `tests/`, `tests/channels/`, `tests/conftest.py` |

## 12. Change workflow

1. **Clarify scope** — read relevant code; confirm assumptions and ambiguities with the user (see [§1](#1-collaboration-principles)).
2. **Hooks** — run `make install-hooks` once per clone if this repo has not done it yet ([§6](#6-run-commands)).
3. **Minimal implementation** — change only task-related files.
4. **Verify** — `make test` for targeted work, `make all` before calling it done (format + lint + typecheck + test). For multi-tenant or worker-loop changes, cover the queue/session path too.
5. **Wrap up** — remove orphan symbols introduced in this change; do not commit or push unless asked.

### Adding a new channel

Use an existing channel as the template (Feishu/DingTalk for SDK callbacks, MQTT for pub/sub, Telegram for bot polling).

1. Create `src/octop_gateway/channels/{name}.py` (or `channels/{name}/` if large).
2. Define `{Name}Config(ChannelConfig)` with platform-specific fields; the `ChannelConfig` base provides `channel_id`, `tenant_id`, and `from_dict()`.
3. Define `{Name}Channel(BaseChannel)` implementing:
   - `start()` / `stop()` — connect / disconnect
   - `_send_text()`, `_send_content()`, `_send_media()` — outbound primitives (use `await self.load_media_bytes(part)` for bytes; call sibling `_send_*` helpers from inside, never `reply_*` / `push_*`)
   - `parse_inbound()` — returns `InboundMessage` with `channel_id`, `channel_type`, `tenant_id`, `channel_subject`, and `channel_session_id`
   - Override `fetch_remote_media(url)` if platform media URLs need auth
   - Set `self._connection_session` on the platform connect/ready event
4. Register in `src/octop_gateway/channels/__init__.py` (`_CHANNEL_MAP` + `_CLASS_NAMES`, and `ChannelKind`).
5. Add to the `src/octop_gateway/__init__.py` exports.
6. Add an `add_{name}_channel()` convenience method to `ChannelManager` in `manager.py`.
7. Create `tests/channels/test_{name}.py` — mock-based, no network.
8. Create `examples/{name}_bot.py`.
9. Update the `README_CN.md` channel list.

**Verify:** `pytest tests/channels/test_{name}.py` → `make test` → `make lint`.

### Branching & release

```
feature/* ──PR──► develop ──► release/x.y.z ──PR──► main ──tag v*──► publish
hotfix/* ──PR──► main (+ tag) and ──PR──► develop
```

| Branch | Role |
|--------|------|
| `main` | Production source of truth; **default branch**; only release / hotfix merges; **only `v*` tags on `main` are production** |
| `develop` | Daily integration; **base for feature PRs** |
| `release/x.y.z` | Temporary freeze (version bump / CHANGELOG / README sync); **delete after ship** |
| `hotfix/*` | Emergency fix from `main`; merge to `main` and back to `develop` |

**Rules**

- Never push `develop` directly onto `main` — ship via `release/*` → `main` (or hotfix → `main`) only. Do **not** bulk-merge `develop` → `main`; it forks history and breaks post-release sync.
- Never push directly to `main` or `develop` — always open a PR (GitHub branch protection).
- Merge `release/*` → `main` with a **merge commit** (not squash) so `main` stays reconcilable with `develop`.
- Release sequence: cut `release/*` from latest `develop` → PR into `main` → **tag `v*` on main tip only after merge** → delete `release/*` → Actions syncs `main` → `develop` (`sync-main-to-develop.yml`; opens `chore/sync-develop-after-*` on conflict / branch protection).
- Keep **`main` an ancestor of `develop`** after every release. Do not use legacy `head=main` → `develop` sync PRs.
- Do **not** push a production tag from a release/feature branch before it is on `main`.
- Hotfix: branch from `main`, PR to `main` (and tag if shipping), then PR into `develop`.
- Day-to-day feature work: branch from `develop`, open PR **into `develop`** (not `main`).
- Human detail: `CONTRIBUTING.md`. Agent publish flow: `.cursor/skills/publish` / `.codebuddy/skills/publish`.


## 13. Communication

- Answer in the language the user writes in (default Chinese).
- Lead with the conclusion, then the detail; cite code as `` `path:line` ``.
- When marking work done, include the verification command and its result (or say why it was not run).
- Mention out-of-scope issues briefly; do not expand scope unilaterally.

---

_This file is a living document — keep it in sync when structure, conventions, or workflow change._
