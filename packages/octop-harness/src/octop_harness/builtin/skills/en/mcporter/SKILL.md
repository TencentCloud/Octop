---
name: mcporter
description: >-
  使用 mcporter CLI 列出、配置、认证和调用 MCP 服务器/工具（HTTP 或 stdio），支持临时服务器、
  配置管理和 CLI/类型代码生成。当用户提到 mcporter、想要调用 MCP 服务器工具、列出可用的
  MCP 服务器、生成 MCP CLI 工具、管理 MCP 配置时使用。触发词包括：mcporter、MCP 工具调用、
  MCP 服务器列表、MCP CLI、MCP 配置、call mcp tool。
metadata:
  octop:
    label:
      zh: "mcporter"
      en: "mcporter"
    summary:
      zh: "用 CLI 列出、配置并调用 MCP 服务器与工具。"
      en: "List, configure, and call MCP servers and tools from the CLI."
  harness:
    emoji: "🔗"
  lightclaw:
    emoji: "🔗"
    requires:
      bins:
        - mcporter
    install:
      - id: node
        kind: node
        package: mcporter
        bins:
          - mcporter
        label: "通过 npm 安装 mcporter"
      - id: brew
        kind: brew
        tap: steipete/tap
        formula: steipete/tap/mcporter
        bins:
          - mcporter
        label: "通过 Homebrew 安装 mcporter"
---

# mcporter — MCP 服务器/工具 CLI 🔌

你是一位精通 MCP（Model Context Protocol）生态的工程师，擅长使用 `mcporter` CLI 快速发现、
调用和管理 MCP 服务器与工具。

## 前置条件

在执行任何操作前，先检查 mcporter 是否可用：

```bash
mcporter --version
```

如果命令不存在，使用以下方式安装（二选一）：

```bash
# 方式 1：通过 npm 全局安装
npm install -g mcporter

# 方式 2：通过 Homebrew 安装
brew tap steipete/tap && brew install steipete/tap/mcporter

# 方式 3：无需安装，直接 npx 使用
npx mcporter --version
```

> **提示**：如果不想全局安装，所有命令都可以用 `npx mcporter` 代替 `mcporter`。

## 核心工作流

### 1. 列出可用的 MCP 服务器和工具

mcporter 会自动发现本地配置（`~/.mcporter/mcporter.json`）、项目配置（`config/mcporter.json`）
以及从 Cursor、Claude Desktop、VS Code 等编辑器导入的配置。

```bash
# 列出所有已配置的服务器
mcporter list

# 查看某个服务器的工具列表和参数 schema
mcporter list <server> --schema

# 查看远程 MCP 端点的工具（临时连接，无需配置）
mcporter list https://mcp.example.com/mcp --all-parameters

# 列出 stdio 类型的本地服务器
mcporter list --stdio "bun run ./local-server.ts" --env TOKEN=xyz

# 输出机器可读的 JSON 格式
mcporter list --json
```

### 2. 调用 MCP 工具

支持多种语法风格，选择最适合当前场景的方式：

```bash
# 选择器风格（最常用）: <server>.<tool> key=value key:number
mcporter call linear.list_issues team=ENG limit:5

# 函数调用风格
mcporter call 'linear.create_comment(issueId: "ENG-123", body: "Looks good!")'

# 简写形式（省略 call）
mcporter linear.list_issues

# 直接调用远程 URL 上的 MCP 工具
mcporter call https://api.example.com/mcp.fetch url=https://example.com

# 调用 stdio 类型的本地服务器工具
mcporter call --stdio "bun run ./server.ts" scrape url=https://example.com

# 传入完整 JSON 参数
mcporter call <server.tool> --args '{"limit": 5, "query": "bug"}'
```

**常用 flag：**
- `--output json` — 输出机器可读的 JSON 结果
- `--raw` — 输出原始结果（不做格式化）
- `--config <path>` — 指定自定义配置文件路径
- `--no-coerce` — 禁用参数类型自动转换
- `--log-level debug` — 显示调试日志
- `--tail-log` — 尾随显示日志

### 3. 认证（OAuth）

部分 MCP 服务器需要 OAuth 认证：

```bash
# 对指定服务器执行 OAuth 登录
mcporter auth <server>

# 重置认证
mcporter auth <server> --reset
```

### 4. 配置管理

管理 MCP 服务器的连接配置：

```bash
# 列出当前所有配置
mcporter config list

# 查看某个服务器的配置
mcporter config get <server>

# 添加新的全局服务器
mcporter config add <name> <url>

# 从编辑器导入已有配置（如 Cursor、Claude Desktop）
mcporter config import cursor --copy

# 移除配置
mcporter config remove <server>

# 配置登录/登出
mcporter config login
mcporter config logout
```

### 5. 守护进程（Daemon）

对需要持久连接的有状态服务器（如 Chrome DevTools），可使用守护进程模式：

```bash
mcporter daemon start     # 启动守护进程
mcporter daemon status    # 查看状态
mcporter daemon stop      # 停止守护进程
mcporter daemon restart   # 重启
```

### 6. 代码生成

#### 生成独立 CLI 工具

将任何 MCP 服务器打包为独立的命令行工具：

```bash
# 从远程 MCP 端点生成 CLI
mcporter generate-cli --command https://mcp.context7.com/mcp

# 从 stdio 命令生成 CLI
mcporter generate-cli "npx -y chrome-devtools-mcp@latest"

# 生成并打包
mcporter generate-cli --command <url> --bundle

# 生成 Bun 独立二进制
mcporter generate-cli --command <url> --compile --runtime bun
```

#### 审查已生成的 CLI

```bash
mcporter inspect-cli <path> [--json]
```

#### 生成 TypeScript 类型定义

```bash
# 生成 .d.ts 类型声明文件
mcporter emit-ts <server> --out types/<server>-tools.d.ts

# 生成即用型客户端包装器
mcporter emit-ts <server> --mode client --out clients/<server>.ts

# 包含可选参数
mcporter emit-ts <server> --include-optional
```

## 操作指南

- 用户说"列出 MCP 服务器"或"有哪些 MCP 工具" → 执行 `mcporter list`
- 用户说"调用 xxx 工具"或"call xxx" → 使用 `mcporter call` 调用
- 用户说"连接某个 MCP 服务器" → 先 `mcporter list <url>` 确认可用，再 `mcporter config add` 添加配置
- 用户说"登录/认证" → 执行 `mcporter auth <server>`
- 用户说"生成 CLI"或"打包工具" → 使用 `mcporter generate-cli`
- 用户想在代码中调用 MCP → 建议使用 mcporter 的 TypeScript API（`callOnce` 或 `createRuntime`）
- 需要机器可读输出时 → 始终加 `--output json` 或 `--json`

## 配置文件

默认配置路径：
- **全局配置**：`~/.mcporter/mcporter.json`（或 `.jsonc`）
- **项目配置**：`./config/mcporter.json`

mcporter 会自动合并全局配置、项目配置和编辑器导入的配置。可通过 `--config <path>` 覆盖默认路径。

## 重要提醒

1. 所有命令都可用 `npx mcporter` 代替全局安装的 `mcporter`
2. 调用工具时，mcporter 会自动进行参数类型转换（如字符串转数字），如不需要可加 `--no-coerce`
3. mcporter 支持环境变量占位符，如 `${TAVILY_API_KEY}`
4. 执行结果默认以人类可读格式输出，需要程序处理时加 `--output json`
5. OAuth 认证信息会缓存在本地，使用 `--reset` 可重新认证
