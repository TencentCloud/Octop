---
name: apple-reminders
description: |
  通过 remindctl 在 macOS 上管理 Apple Reminders——列出、添加、编辑、完成、
  删除同步到 iPhone/iPad 的待办事项。在提及"提醒"、"Reminders app"、
  需要手机同步的"提醒我"或添加带截止日期的个人待办事项时触发。macOS only。
  当用户需要代理内部提醒（使用 memory_store 或外部
  调度）或日历事件时跳过。
version: 1.0.0
author: Octop
license: MIT
compatibility: macos only — requires Reminders.app and remindctl CLI
metadata:
  octop:
    label:
      zh: "提醒事项"
      en: "Apple Reminders"
    summary:
      zh: "管理同步到 iPhone 的 macOS 提醒与待办。"
      en: "Manage macOS Reminders that sync to iPhone."
  harness:
    emoji: "☑️"
    tags: [Reminders, tasks, todo, macOS, Apple]
    related_skills: [apple-notes]
prerequisites:
  commands: [remindctl]
---

# Apple Reminders

## Harness-agent 工具

| 概念 | 工具 |
|---------|------|
| Shell / brew / remindctl | `execute` |
| 记忆（仅代理笔记，无手机同步） | `memory_store`, `memory_recall` |

内置技能路径：`/_builtin_skills/apple-reminders/`。

使用 `remindctl` 从终端管理 Apple Reminders。任务通过 iCloud 在所有 Apple 设备间同步。

## 引导（首次使用前运行）

在调用 `remindctl` 之前，**不要**调用，直到此检查清单通过。使用 `execute` 自行安装缺少的依赖——除非安装失败或缺少 Homebrew，否则不要要求用户运行 brew。

### 1. 确认 macOS

```bash
uname -s
```

期望 `Darwin`。在 Linux/Windows 上，停止并告诉用户此技能仅限 macOS。

### 2. 检查/安装 `remindctl`

```bash
command -v remindctl && remindctl --version
```

如果缺少：

```bash
command -v brew
brew install steipete/tap/remindctl
remindctl --version
```

如果未安装 `brew`，说明需要 Homebrew 并指向 https://brew.sh——不要猜测其他安装路径。

### 3. 检查/请求 Reminders 权限

```bash
remindctl status
```

如果输出指示缺少授权：

```bash
remindctl authorize
```

然后告诉用户在系统提示或**系统设置 → 隐私与安全 → Reminders** 中批准 Reminders 访问。不要在紧密循环中重试——等待用户确认他们已批准。

### 4. 冒烟测试

```bash
remindctl list
```

如果成功，继续用户的任务。

## 何时使用

- 用户提到"提醒"或"Reminders app"
- 创建同步到 iOS 的带截止日期的个人待办事项
- 管理 Apple Reminders 列表
- 用户希望任务出现在他们的 iPhone/iPad 上

## 何时不使用

- **仅代理的"稍后提醒我"** 无手机同步 → `memory_store` 或要求用户设置 OS cron/外部调度器
- 日历事件 → Apple Calendar 或 Google Calendar
- 项目任务管理 → GitHub Issues、Notion 等
- 如果用户说"提醒我"但意思是聊天内提示 → 先澄清

## 快速参考

### 查看提醒

```bash
remindctl                    # 今天的提醒
remindctl today              # 今天
remindctl tomorrow           # 明天
remindctl week               # 本周
remindctl overdue            # 过期
remindctl all                # 所有
remindctl 2026-01-04         # 特定日期
```

### 管理列表

```bash
remindctl list               # 列出所有列表
remindctl list Work          # 显示特定列表
remindctl list Projects --create    # 创建列表
remindctl list Work --delete        # 删除列表
```

### 创建提醒

在 `add` 之前始终与用户确认标题和截止日期。

```bash
remindctl add "Buy milk"
remindctl add --title "Call mom" --list Personal --due tomorrow
remindctl add --title "Meeting prep" --due "2026-02-15 09:00"
```

### 截止时间 vs 闹钟/提前提示

`--due` 和 `--alarm` 是不同的字段：

- `--due` 设置提醒的截止日期/时间。
- `--alarm` 设置 EventKit 闹钟/通知触发器。当用户要求更早的提示时，显式传递 `--alarm`。

示例——截止下午 2:00，提前 30 分钟通知：

```bash
remindctl add --title "Hairdresser" --due "2026-05-15 14:00" --alarm "2026-05-15 13:30"
```

编辑现有提醒：

```bash
remindctl edit 87354 --due "2026-05-15 14:00" --alarm "2026-05-15 13:30"
```

使用 JSON 验证（UI 可能按闹钟时间分组）：

```bash
remindctl today --json
```

预期字段：`dueDate`（截止时间）、`alarmDate`（通知时间）。

### 完成/删除

```bash
remindctl complete 1 2 3          # 按 ID 完成
remindctl delete 4A83 --force     # 按 ID 删除
```

### 输出格式

```bash
remindctl today --json       # 用于脚本的 JSON
remindctl today --plain      # TSV 格式
remindctl today --quiet      # 仅计数
```

编程解析输出时优先使用 `--json`。

## 日期格式

被 `--due` 和日期过滤器接受：

- `today`, `tomorrow`, `yesterday`
- `YYYY-MM-DD`
- `YYYY-MM-DD HH:mm`
- ISO 8601 (`2026-01-04T12:34:56Z`)

## 规则

1. **"提醒我"**——澄清：Apple Reminders（同步到手机）vs `memory_store`/外部调度
2. 在创建之前始终确认提醒内容和截止日期
3. 当 `remindctl` 失败或会话中首次使用时，运行引导部分
4. 编程解析时使用 `--json`
