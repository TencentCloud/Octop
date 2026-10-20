---
name: imessage
description: "通过 macOS 上的 imsg CLI 发送和接收 iMessage/SMS。"
version: 1.0.0
author: Octop
license: MIT
compatibility: macos only
metadata:
  octop:
    label:
      zh: "iMessage"
      en: "iMessage"
    summary:
      zh: "在 macOS 上收发 iMessage 与短信。"
      en: "Send and receive iMessage and SMS on macOS."
  harness:
    emoji: "✉️"
    tags: [iMessage, SMS, messaging, macOS, Apple]
prerequisites:
  commands: [imsg]
---

# iMessage

## Harness-agent 工具

本技能从 Octop 移植。使用以下 harness/deepagents 工具：

| 概念 | 工具 |
|---------|------|
| Shell | `execute` |
| 读/写/编辑文件 | `read_file`, `write_file`, `edit_file` |
| 查找文件/搜索内容 | `glob`, `grep` |
| 获取 URL | `web_fetch` |
| 浏览器自动化 | `browser_use` |
| 子代理工作 | `task` |
| 记忆 | `memory_store`, `memory_recall`, `memory_search` |

内置技能文件位于 `/_builtin_skills/<name>/`。用户安装的技能位于 `/skills/<name>/`。

使用 `imsg` 通过 macOS Messages.app 读取和发送 iMessage/SMS。

## 先决条件

- **macOS** 带 Messages.app 并已登录
- 安装：`brew install steipete/tap/imsg`
- 终端的完全磁盘访问权限（系统设置 → 隐私 → 完全磁盘访问）
- 出现提示时授予 Messages.app 自动化权限

## 何时使用

- 用户要求发送 iMessage 或短信
- 读取 iMessage 对话历史
- 检查最近的 Messages.app 聊天
- 发送到手机号码或 Apple ID

## 何时不使用

- Telegram/Discord/Slack/WhatsApp 消息 → 使用相应的网关通道
- 群聊管理（添加/移除成员）→ 不支持
- 批量/群发消息 → 始终先与用户确认

## 快速参考

### 列出聊天

```bash
imsg chats --limit 10 --json
```

### 查看历史

```bash
# 按聊天 ID
imsg history --chat-id 1 --limit 20 --json

# 带附件信息
imsg history --chat-id 1 --limit 20 --attachments --json
```

### 发送消息

```bash
# 仅文本
imsg send --to "+14155551212" --text "Hello!"

# 带附件
imsg send --to "+14155551212" --text "Check this out" --file /path/to/image.jpg

# 强制 iMessage 或 SMS
imsg send --to "+14155551212" --text "Hi" --service imessage
imsg send --to "+14155551212" --text "Hi" --service sms
```

### 监听新消息

```bash
imsg watch --chat-id 1 --attachments
```

## 服务选项

- `--service imessage` — 强制 iMessage（需要收件人拥有 iMessage）
- `--service sms` — 强制 SMS（绿色气泡）
- `--service auto` — 让 Messages.app 决定（默认）

## 规则

1. **始终在发送前确认收件人和消息内容**
2. **绝不要**在没有用户明确批准的情况下发送到未知号码
3. **验证文件路径**在附加之前存在
4. **不要垃圾发送**——限制自己的速率

## 示例工作流

用户："发短信告诉妈妈我会晚点回来"

```bash
# 1. 找到妈妈的聊天
imsg chats --limit 20 --json | jq '.[] | select(.displayName | contains("Mom"))'

# 2. 与用户确认："找到妈妈在 +1555123456。发送'我会晚点回来'通过 iMessage？"

# 3. 确认后发送
imsg send --to "+1555123456" --text "我会晚点回来"
```
