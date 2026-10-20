<div align="center">
  <img src="assets/images/banner.jpeg" alt="Octop Gateway" width="600" />
  <h1>Octop Gateway</h1>
</div>

<p align="center">
  <strong>多平台 IM 通道桥接 —— 用一套抽象接口，让 AI Agent 连接任意即时通讯平台。</strong>
</p>

<p align="center">
  <a href="https://www.python.org/downloads/"><img alt="Python 3.12+" src="https://img.shields.io/badge/python-3.12%2B-blue?logo=python&logoColor=white" /></a>
  <a href="https://github.com/TencentCloud/octop-gateway/blob/main/LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-green" /></a>
  <a href="https://pypi.org/project/octop-gateway/"><img src="https://img.shields.io/pypi/v/octop-gateway" alt="PyPI" /></a>
  <a href="https://github.com/astral-sh/ruff"><img alt="Code Style: Ruff" src="https://img.shields.io/badge/code%20style-ruff-000000?logo=ruff&logoColor=white" /></a>
  <a href="https://github.com/TencentCloud/octop-gateway"><img alt="GitHub stars" src="https://img.shields.io/github/stars/TencentCloud/octop-gateway?style=social" /></a>
</p>

<p align="center">
  <a href="README.md">English</a> · <b>中文</b>
</p>

<p align="center">
  <a href="#什么是-octop-gateway">什么是 Octop Gateway？</a> ·
  <a href="#为什么选择-octop-gateway">为什么选择 Octop Gateway？</a> ·
  <a href="#如何使用">如何使用</a> ·
  <a href="#文档">文档</a>
</p>

---

## 什么是 Octop Gateway？

**octop-gateway** 是一个面向 AI Agent 与机器人的多平台 IM 通道桥接库，提供统一的消息抽象。它连接各大主流 IM 平台，把每一条入站消息归一为同一条处理管线——你的 Agent 逻辑**只写一次**，即可在飞书、钉钉、QQ、企业微信、微信 iLink、元宝、小艺、MQTT、Telegram 与 Discord 上运行。

> Harness Gateway 的设计目标：你只需写一个异步消息处理器，网关便会为每个平台处理连接、解析、媒体与回传，并以统一的接口交付给你。

## 为什么选择 Octop Gateway？

| | 特性 | 说明 |
|---|------|------|
| 🔌 | **10 个平台，一个处理器** | 飞书、钉钉、QQ、企业微信、微信 iLink、元宝、小艺、MQTT、Telegram、Discord —— 全部共用一套接口 |
| 🧩 | **统一抽象** | `BaseChannel` 把各平台的差异，收敛为通用的 `InboundMessage` / `MessageEvent` 模型 |
| 📨 | **流式事件** | 你的处理器是异步生成器，产出 `MessageEvent`，原生支持逐字流式输出 |
| 💾 | **可插拔媒体** | `MediaBackend` 负责附件存储，默认提供 `FileSystemMediaBackend` |
| 🚦 | **约束控制** | 按通道设置限流、超时与"正在输入"状态 |
| 📡 | **主动推送** | `push_text` / `push_content` / `push_to_all` 用于主动消息 |
| 🏢 | **多租户** | 可同时运行多个同类型通道，彼此隔离 |
| 🐍 | **Pythonic** | 纯 `asyncio`、类型完备的模型，没有隐式魔法 |

### 核心技术

| 层级 | 技术 |
|------|------|
| **语言** | Python 3.12+ |
| **通道模型** | `BaseChannel` + 10 个内置平台适配器 |
| **消息模型** | `InboundMessage` / `MessageEvent` / `ContentPart` |
| **编排** | `ChannelManager`（异步队列 + 工作池） |
| **媒体** | `MediaBackend`（默认 `FileSystemMediaBackend`） |
| **约束** | 限流 / 超时 / 输入状态 |
| **构建 / 质量** | hatchling · ruff · mypy · pytest |

### 功能特性

#### 已支持平台

| 平台 | 通道类型 | 传输方式 | 文本 | 媒体 |
|------|----------|----------|------|------|
| 飞书（Lark） | `feishu` | WebSocket + REST | ✅ | ✅ |
| 钉钉 | `dingtalk` | Stream | ✅ | ✅ |
| QQ | `qq` | WebSocket | ✅ | ✅ |
| 企业微信 | `wecom` | 回调 + API | ✅ | ✅ |
| 微信 iLink | `weixin` | — | ✅ | ✅ |
| 元宝 | `yuanbao` | — | ✅ | ✅ |
| 小艺 | `xiaoyi` | — | ✅ | ✅ |
| MQTT | `mqtt` | MQTT | ✅ | ✅ |
| Telegram | `telegram` | 长轮询 | ✅ | ✅ |

##### Discord

使用 Bot Token + Gateway 长连接；在开发者门户开启 Message Content Intent。`allow_all_channels` 默认 `True`（包括未填写此字段的旧配置），允许机器人有权限访问的所有服务器频道。设为 `False` 后仅允许 `allowed_channel_ids` 指定的频道，列表为空则拒绝服务器频道消息。私聊始终仅允许 `allowed_user_ids` 中的用户，列表为空则拒绝私聊。频道默认需要直接 @机器人，线程继承父频道权限。支持 HTTP 代理、附件、typing、长回复分段。参见 [`examples/discord_bot.py`](examples/discord_bot.py)。

#### 统一消息抽象
- `InboundMessage` 携带文本、结构化的 `ContentPart`（文本 / 图片 / 视频 / 音频 / 文件）以及 `ChannelSubject`。
- 你的处理器是 `Callable[[InboundMessage], AsyncIterator[MessageEvent]]`——可产出 `MESSAGE` 表示完整文本，`DELTA` 表示逐字流式，`COMPLETED` 表示刷出。
- `ChannelConfig` 是每个平台的类型化 dataclass；`BaseChannel` 定义 `start` / `stop` / `parse_inbound` / `_send_*`。

#### 自定义通道
继承 `BaseChannel`，通过 `ChannelManager.add_channel(...)` 注册，管线其余部分（媒体、约束、推送）无需改动即可工作。

#### 约束、媒体与推送
- **约束** —— 按通道设置限流、响应超时与"正在输入"状态。
- **媒体** —— 可插拔 `MediaBackend`，附件随意落盘。
- **推送** —— `push_text` / `push_content` 定向发送，`push_to_all` 用于广播。

#### 多租户
可同时运行多个同类型通道（例如两个飞书应用对应两个团队），各自以 `channel_id` 隔离。

## 如何使用

### 环境要求
- **Python 3.12+**
- 所接入平台的凭据

### 1. 安装

```bash
# 核心库
pip install octop-gateway

# 附带示例 / Agent 集成依赖
pip install "octop-gateway[examples]"
```

### 2. 最小回声机器人（Telegram）

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

### 3. 接入更多平台

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

将 `.env.example` 复制为 `.env` 进行环境变量配置。

## 文档

- [什么是 Octop Gateway？](#什么是-octop-gateway)
- [为什么选择 Octop Gateway？](#为什么选择-octop-gateway)
- [如何使用](#如何使用)

### 架构

```
ChannelManager
 ├─ 异步队列 + 工作池（每通道）
 ├─ add_channel(BaseChannel) / add_*_channel(...)
 ├─ push_text / push_content / push_to_all
 └─ 每通道一个 BaseChannel
      ├─ start / stop
      ├─ parse_inbound → InboundMessage
      └─ _send_text / _send_content / _send_media

MessageProcessor: InboundMessage → AsyncIterator[MessageEvent]
```

每个 `BaseChannel` 管理自己的传输；管理器负责调度、媒体、约束与分发。你的处理器只看到归一化后的事件流。

### 开发

**环境要求：** Python 3.12+、[uv](https://docs.astral.sh/uv/)

```bash
make install          # pip install -e ".[dev,examples]"
make all              # 格式化 + 类型检查 + 测试
```

## 🤝 贡献

1. Fork 本仓库
2. 创建特性分支（`git checkout -b feature/amazing-feature`）
3. 提交前运行 `make all`
4. 向 `main` 发起 Pull Request

通道实现规范见 [AGENTS.md](AGENTS.md)。

分支、PR 与发版流程见 [CONTRIBUTING.md](CONTRIBUTING.md)（`release/*` → `main` 合并后自动发布到 PyPI）。

## 🔗 相关项目

| 项目 | 说明 |
|------|------|
| [octop-harness](https://github.com/TencentCloud/octop-harness) | 驱动网关处理器的 Agent 运行时 |
| [octop-memory](https://github.com/TencentCloud/octop-memory) | 面向网关 Agent 的记忆系统 |
| [octop-browser](https://github.com/TencentCloud/octop-browser) | 供 Agent 使用的浏览器自动化 |
| [Octop](https://github.com/TencentCloud/Octop) | 组合 Harness 技术栈的自托管助手 |

## 📄 许可证

本项目基于 [MIT 许可证](LICENSE) 开源。

## ✨ 贡献者

感谢所有贡献者：

<a href="https://github.com/TencentCloud/octop-gateway/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=TencentCloud/octop-gateway" />
</a>
