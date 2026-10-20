<div align="center">
  <img src="assets/images/banner.jpeg" alt="Octop Gateway" width="600" />
  <h1>Octop Gateway</h1>
</div>

<p align="center">
  <strong>Multi-platform IM channel bridge — one abstraction layer that lets AI agents connect to any instant-messaging platform.</strong>
</p>

<p align="center">
  <a href="https://www.python.org/downloads/"><img alt="Python 3.12+" src="https://img.shields.io/badge/python-3.12%2B-blue?logo=python&logoColor=white" /></a>
  <a href="https://github.com/TencentCloud/octop-gateway/blob/main/LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-green" /></a>
  <a href="https://pypi.org/project/octop-gateway/"><img src="https://img.shields.io/pypi/v/octop-gateway" alt="PyPI" /></a>
  <a href="https://github.com/astral-sh/ruff"><img alt="Code Style: Ruff" src="https://img.shields.io/badge/code%20style-ruff-000000?logo=ruff&logoColor=white" /></a>
  <a href="https://github.com/TencentCloud/octop-gateway"><img alt="GitHub stars" src="https://img.shields.io/github/stars/TencentCloud/octop-gateway?style=social" /></a>
</p>

<p align="center">
  <a href="#what-is-octop-gateway">What is Octop Gateway?</a> ·
  <a href="#why-octop-gateway">Why Octop Gateway?</a> ·
  <a href="#how-to-use">How to Use</a> ·
  <a href="#documentation">Documentation</a>
</p>

<p align="center">
  <b>English</b> · <a href="README_CN.md">中文</a>
</p>

---

**octop-gateway** is a multi-platform IM channel bridge with a unified message abstraction for AI agents and bots. It connects to mainstream IM platforms and normalizes every inbound message into one processing pipeline, so your agent logic is written **once** and runs across Feishu, DingTalk, QQ, WeCom, WeChat iLink, Yuanbao, Xiaoyi, MQTT, and Telegram.

> octop-gateway's design goal: you write a single async message processor, and the gateway handles transport, parsing, media, and delivery for every platform behind a common interface.

## What is Octop Gateway?

| | Feature | Description |
|---|---------|-------------|
| 🔌 | **10 platforms, one processor** | Feishu, DingTalk, QQ, WeCom, WeChat iLink, Yuanbao, Xiaoyi, MQTT, Telegram, Discord — all behind one interface |
| 🧩 | **Unified abstraction** | `BaseChannel` turns each platform's quirks into a common `InboundMessage` / `MessageEvent` model |
| 📨 | **Streaming events** | Your processor is an async generator yielding `MessageEvent` — first-class token streaming |
| 💾 | **Pluggable media** | `MediaBackend` stores attachments; `FileSystemMediaBackend` ships by default |
| 🚦 | **Constraints** | Per-channel rate limit, timeout, and typing indicator |
| 📡 | **Push routing** | `push_text` / `push_content` / `push_to_all` for proactive messages |
| 🏢 | **Multi-tenant** | Run multiple channels of the same kind, each isolated |
| 🐍 | **Pythonic** | Pure `asyncio`, fully typed models, no hidden magic |

## Why Octop Gateway?

Harness Gateway sits between your agent and the outside world. Each platform is implemented as a `BaseChannel` subclass that knows how to connect, parse inbound traffic, and send replies. A `ChannelManager` orchestrates them through async queues and hands your agent a normalized stream of `MessageEvent`s. You never write platform-specific code in your bot — just one processor.

> Because the abstraction lives in the gateway, swapping IM platforms is a configuration change, not a rewrite.

### Core Technology

| Layer | Technology |
|-------|-----------|
| **Language** | Python 3.12+ |
| **Channel model** | `BaseChannel` + per-platform adapter (10 built-in) |
| **Messaging model** | `InboundMessage` / `MessageEvent` / `ContentPart` |
| **Orchestration** | `ChannelManager` (async queues, worker pools) |
| **Media** | `MediaBackend` (`FileSystemMediaBackend` default) |
| **Constraints** | Rate limit / timeout / typing indicator |
| **Build / quality** | hatchling · ruff · mypy · pytest |

### Features

#### Supported platforms

| Platform | Channel kind | Transport | Text | Media |
|----------|--------------|-----------|------|-------|
| Feishu (Lark) | `feishu` | WebSocket + REST | ✅ | ✅ |
| DingTalk | `dingtalk` | Stream | ✅ | ✅ |
| QQ | `qq` | WebSocket | ✅ | ✅ |
| WeCom (Enterprise WeChat) | `wecom` | Callback + API | ✅ | ✅ |
| WeChat iLink | `weixin` | — | ✅ | ✅ |
| Yuanbao (元宝) | `yuanbao` | — | ✅ | ✅ |
| Xiaoyi (小艺) | `xiaoyi` | — | ✅ | ✅ |
| MQTT | `mqtt` | MQTT | ✅ | ✅ |
| Telegram | `telegram` | Long-polling | ✅ | ✅ |

##### Discord

Use a Bot Token and enable Message Content Intent in the developer portal. `allow_all_channels` defaults to `True`, including configurations without this field, allowing all guild channels accessible to the bot. Set it to `False` to restrict access to `allowed_channel_ids` (empty denies guild messages). DMs always require `allowed_user_ids`; an empty user list denies DMs. Guild messages require a direct bot mention by default, and threads inherit parent-channel access. Supports HTTP proxying, attachments, typing and split replies. See [`examples/discord_bot.py`](examples/discord_bot.py).

#### Unified message abstraction
- `InboundMessage` carries the text, structured `ContentPart`s (text / image / video / audio / file), and a `ChannelSubject`.
- Your processor is a `Callable[[InboundMessage], AsyncIterator[MessageEvent]]` — emit `MESSAGE` for complete text, `DELTA` for token streaming, and `COMPLETED` to flush.
- `ERROR` is a failed terminal event: consumers stop reading immediately and explicitly close the producer. Put cleanup in the producer's `finally`; cleanup has a five-second timeout and failures are logged. Persist any durable failure history before yielding `ERROR`, since no later event is required.
- `ChannelConfig` is a typed dataclass per platform; `BaseChannel` defines `start` / `stop` / `parse_inbound` / `_send_*`.

#### Custom channels
Subclass `BaseChannel`, register it with `ChannelManager.add_channel(...)`, and the rest of the pipeline (media, constraints, push) works unchanged.

#### Constraints, media & push
- **Constraints** — rate limit, response timeout, and typing indicator per channel.
- **Media** — pluggable `MediaBackend`; persist attachments wherever you like.
- **Push** — `push_text` / `push_content` to one subject, or `push_to_all` for broadcasts.

#### Multi-tenant
Run several channels of the same kind (e.g. two Feishu apps for two teams) — each is isolated by `channel_id`.

## How to Use

### Prerequisites
- **Python 3.12+**
- Credentials for the platforms you connect to

### 1. Install

```bash
# Core library
pip install octop-gateway

# With example / agent integration extras
pip install "octop-gateway[examples]"
```

### 2. Minimal echo bot (Telegram)

```python
import asyncio, os
from collections.abc import AsyncIterator

from octop_gateway import ChannelManager, InboundMessage, MessageEvent
from octop_gateway.channels.telegram import TelegramConfig


async def echo(message: InboundMessage) -> AsyncIterator[MessageEvent]:
    yield MessageEvent.text(f"Echo: {message.text}")
    yield MessageEvent.completed()


async def main():
    manager = ChannelManager(processor=echo)
    await manager.start()
    await manager.add_telegram_channel(TelegramConfig(bot_token=os.environ["TELEGRAM_BOT_TOKEN"]))
    await asyncio.Event().wait()


asyncio.run(main())
```

### 3. Add more platforms

```python
import asyncio, os
from collections.abc import AsyncIterator

from octop_gateway import ChannelManager, InboundMessage, MessageEvent
from octop_gateway.channels.dingtalk import DingTalkConfig
from octop_gateway.channels.feishu import FeishuConfig
from octop_gateway.channels.qq import QQConfig


async def unified_bot(msg: InboundMessage) -> AsyncIterator[MessageEvent]:
    yield MessageEvent.text(f"[{msg.channel_type}] {msg.text}")
    yield MessageEvent.completed()


async def main():
    manager = ChannelManager(processor=unified_bot, workers_per_channel=4)
    await manager.start()

    await manager.add_feishu_channel(
        FeishuConfig(app_id=os.environ["FEISHU_APP_ID"], app_secret=os.environ["FEISHU_APP_SECRET"])
    )
    await manager.add_qq_channel(
        QQConfig(app_id=os.environ["QQ_APP_ID"], token=os.environ["QQ_TOKEN"], secret=os.environ["QQ_SECRET"])
    )
    await manager.add_dingtalk_channel(
        DingTalkConfig(app_key=os.environ["DINGTALK_APP_KEY"], app_secret=os.environ["DINGTALK_APP_SECRET"])
    )
    await asyncio.Event().wait()


asyncio.run(main())
```

Copy `.env.example` to `.env` for environment-based configuration.

## Documentation

- [What is Octop Gateway?](#what-is-octop-gateway)
- [Why Octop Gateway?](#why-octop-gateway)
- [How to Use](#how-to-use)
- **Reference**
  - [Architecture](#architecture)
  - [Development](#development)
- **Project Info**
  - [Contributing](#contributing)
  - [Related projects](#related-projects)
  - [License](#license)

### Architecture

```
ChannelManager
 ├─ async queues + worker pools (per channel)
 ├─ add_channel(BaseChannel) / add_*_channel(...)
 ├─ push_text / push_content / push_to_all
 └─ per-channel BaseChannel
      ├─ start / stop
      ├─ parse_inbound → InboundMessage
      └─ _send_text / _send_content / _send_media

MessageProcessor: InboundMessage → AsyncIterator[MessageEvent]
```

Each `BaseChannel` owns its transport; the manager owns scheduling, media, constraints, and fan-out. Your processor only sees the normalized stream.

### QQ Bot QR binding

QQ Bot credentials can be obtained without manually copying an AppID and
AppSecret. Render the returned URL as a QR code, then wait for confirmation:

```python
from octop_gateway.channels.qq import QQBotQRLogin, QQConfig

login = QQBotQRLogin(source="octop")
qr = await login.fetch_qr_code()
print(qr.qrcode_url)  # Render this URL as a QR code in your UI or terminal.

result = await login.wait_for_login(qr.task_id)
if not result.connected:
    raise RuntimeError(result.message)
config = QQConfig.from_qr_credentials(result.credentials[0])
```

The one-time decryption key remains in memory and is discarded after success,
expiry, cancellation, or timeout. Persisting the returned channel config is the
caller's responsibility.

### Group conversation policy

`group_context` separates platform visibility from agent activation. QQ enables
the shared manager by default with a conservative `auto + mention + recent(10)`
policy. It can be configured globally and overridden by native group ID:

```json
{
  "group_context": {
    "enabled": true,
    "visibility": "auto",
    "activation": "mention",
    "history": "recent",
    "history_limit": 10,
    "history_ttl_seconds": 300,
    "clear_after_reply": true,
    "groups": {
      "GROUP_OPENID_WITH_FULL_ACCESS": {
        "visibility": "all",
        "activation": "always"
      },
      "GROUP_OPENID_MENTION_ONLY": {
        "visibility": "mention_only",
        "history": "none"
      }
    }
  }
}
```

- `visibility`: `auto`, `all`, `mention_recent`, or `mention_only`.
- `activation`: `mention` or `always`. `always` is accepted only with explicit
  `all` visibility, so replayed recent messages cannot trigger multiple replies.
- `history`: `recent` or `none`. Passive messages are bounded, expire by TTL,
  and are cleared after a successful reply.

When a platform permission is downgraded, update `visibility` to the granted
level (or restart/reconfigure the channel); this immediately drops the old
in-memory buffer. Platforms that do not publish permission-change events cannot
be detected perfectly, so `auto` remains mention-triggered and the TTL limits
stale context.

### Development

**Prerequisites:** Python 3.12+, [uv](https://docs.astral.sh/uv/)

```bash
make install          # pip install -e ".[dev,examples]"
make all              # lint + typecheck + test
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Run `make all` before submitting
4. Open a Pull Request against `main`

Channel conventions: [AGENTS.md](AGENTS.md).

See [CONTRIBUTING.md](CONTRIBUTING.md) for branching, PR, and release details (`release/*` → `main` auto-publishes to PyPI).

## 🔗 Related projects

| Project | Description |
|---------|-------------|
| [octop-harness](https://github.com/TencentCloud/octop-harness) | Agent runtime that drives the gateway processor |
| [octop-memory](https://github.com/TencentCloud/octop-memory) | Memory system for gateway-backed agents |
| [octop-browser](https://github.com/TencentCloud/octop-browser) | Browser automation for agents |
| [Octop](https://github.com/TencentCloud/Octop) | The self-hosted assistant that composes the Harness stack |

## 📄 License

This project is licensed under the [MIT License](LICENSE).

## ✨ Contributors

Thanks to all contributors:

<a href="https://github.com/TencentCloud/octop-gateway/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=TencentCloud/octop-gateway" />
</a>

### Runtime channel registration

Hosts may use `register_channel_kind(kind, ChannelClass, plugin_id=owner)`
to register a `BaseChannel` subclass before constructing it with
`ChannelManager`. The same owner may replace a class during reload; another
owner or a builtin collision raises `ValueError`. Stop affected instances
before updating. `unregister_channel_kind(kind, plugin_id=owner)` removes the
registration only, not running instances or persisted configuration.
`registered_channel_kinds()` returns the active builtin and plugin kinds;
`SUPPORTED_CHANNEL_KINDS` remains the builtin compatibility snapshot.
