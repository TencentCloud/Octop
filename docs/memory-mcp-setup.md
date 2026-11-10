# 记忆 MCP：安装与配置指引

本文是 [记忆 MCP Server](./memory-mcp.md) 的安装/配置分册：怎么拿到 token、怎么在本地终端里装好 hooks 与 MCP 条目、怎么验证和排查。

> 前置：Octop 已开启记忆 MCP（`OCTOP_MEMORY_MCP_ENABLED=1`，或库里已存在有效 token 后重启一次）。

## 1. 先创建一个 Token

**Dashboard（推荐）**：登录 Octop → 左侧「个性化 → 记忆」→ 顶部 tab「MCP 接入」→「创建 Token」。

- 名称：客户端标识，例如 `codex@macbook`
- 上报专家：**单选一个专家**（token 绑定哪个专家，通过它上报的记忆就落到哪个专家）；也可以选「不限定专家」，但那样客户端必须自己带 `X-Octop-Agent-Id`
- 创建成功后明文**只显示一次**，页面会同时给出可直接复制的一键安装命令
- 之后可以随时在列表里「切换专家」或「撤销」；切换/撤销对下一次请求立即生效

**API**（脚本化时）：

```bash
curl -sS -X POST "https://<octop-host>/api/memory-mcp/tokens" \
  -H "Authorization: Bearer <octop-session-token>" \
  -H "Content-Type: application/json" \
  -d '{"name": "codex@macbook", "expert_ids": ["<专家ID>"]}'
```

响应里的 `token` 形如 `omcp_…`；`token_hint` 是之后列表里显示的掩码。

## 2. 一键安装（推荐）

安装器只返回脚本，**不内置任何凭据**；token 通过环境变量或交互输入提供。

### 2.1 macOS / Linux

```bash
# 交互式：检测本机装了哪些终端，勾选后粘贴 token
curl -fsSL "https://<octop-host>/mcp/memory/setup" | sh

# 非交互：token 走环境变量，终端用 OCTOP_TERMINALS 指定（逗号分隔）
curl -fsSL "https://<octop-host>/mcp/memory/setup" | \
  OCTOP_MEMORY_TOKEN=omcp_… OCTOP_TERMINALS=codex sh

# 只装到某个项目（hook 脚本与含 token 的 config.json 仍留在用户目录）
curl -fsSL "https://<octop-host>/mcp/memory/setup?project=$PWD" | \
  OCTOP_MEMORY_TOKEN=omcp_… sh
```

可用终端名：`claude-code`、`kiro`、`dsh`、`codex`、`cursor`。

### 2.2 Windows（原生 PowerShell，不需要 Git Bash）

```powershell
irm "https://<octop-host>/mcp/memory/setup?os=windows" | iex
# 非交互
$env:OCTOP_MEMORY_TOKEN="omcp_…"; $env:OCTOP_TERMINALS="codex"; \
  irm "https://<octop-host>/mcp/memory/setup?os=windows" | iex
```

### 2.3 装了哪些东西

| 终端 | hooks 目录 | 注册位置 | 说明 |
|------|-----------|---------|------|
| Claude Code | `~/.claude/hooks-events/` | `~/.claude/settings.json`（项目级写 `.claude/settings.local.json` + local scope MCP） | UserPromptSubmit 召回、Stop 上报 |
| Kiro | `~/.kiro/hooks/` | `~/.kiro/hooks/*.json` | 项目级 MCP 因含凭据会跳过并提示 |
| Codex | `~/.codex/hooks/` | `~/.codex/config.toml` 的 hooks 段 | MCP 条目由 Codex 自己管理，安装器不改 |
| Cursor | `~/.cursor/hooks/` | `~/.cursor/hooks.json` | 召回 + 上报 |
| DSH | — | `~/.dsh/bundles/octop-memory-native/` + profile | **原生插件**进程内召回/上报，不装 hook 桥接 |

每个终端的 hooks 目录都有 `config.json`（`url` / `token`）和 `octop-hook.log`（运行日志）。token 是唯一凭据，配置文件里**没有**专家 ID。

### 2.4 卸载

```bash
curl -fsSL "https://<octop-host>/mcp/memory/uninstall" | sh
# Windows
irm "https://<octop-host>/mcp/memory/uninstall?os=windows" | iex
# 只清某个项目/终端
curl -fsSL "https://<octop-host>/mcp/memory/uninstall?project=$PWD&terminals=codex" | sh
```

## 3. 手动配置（不用安装器）

只需要两样东西：URL 与 `Authorization`（token 已绑定专家时不需要其它头）。

| 配置 | 值 |
|------|----|
| URL | `https://<octop-host>/mcp/memory/` |
| Header `Authorization` | `Bearer omcp_…` |
| Header `X-Octop-Agent-Id` | 仅当 token「不限专家」或绑定多个专家时需要 |

### 3.1 Claude Code

```bash
claude mcp add --transport http octop-memory "https://<octop-host>/mcp/memory/" \
  --header "Authorization: Bearer omcp_…"
```

### 3.2 Codex

`~/.codex/config.toml`：

```toml
[mcp_servers.octop-memory]
url = "https://<octop-host>/mcp/memory/"

[mcp_servers.octop-memory.http_headers]
Authorization = "Bearer omcp_…"
```

### 3.3 Cursor / 其它客户端

`~/.cursor/mcp.json`（或客户端等价配置）：

```json
{
  "mcpServers": {
    "octop-memory": {
      "type": "http",
      "url": "https://<octop-host>/mcp/memory/",
      "headers": { "Authorization": "Bearer omcp_…" }
    }
  }
}
```

### 3.4 DSH 原生插件

安装器已在 `~/.dsh/bundles/octop-memory-native/` 落盘并登记 profile；手动装时把仓库里的
`src/octop/infra/agents/dsh_native_plugin/` 复制到该目录，再在 profile 的 `cordis.patch.yml` 写入：

```yaml
- insert:
    - id: octop-memory-native
      name: 'octop-memory-native'
      config:
        endpoint: 'https://<octop-host>/mcp/memory/'
        token: 'omcp_…'
        tokenHeader: Authorization
```

## 4. 验证

1. **Dashboard**：「MCP 接入」列表的「最近使用」会随请求更新。
2. **MCP 握手**（不依赖任何客户端）：

   ```bash
   curl -sS -o /dev/null -w "%{http_code}\n" -X POST "https://<octop-host>/mcp/memory/" \
     -H "Authorization: Bearer omcp_…" \
     -H "Accept: application/json, text/event-stream" \
     -H "Content-Type: application/json" \
     -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"curl","version":"0"}}}'
   ```

   期望 `200`（返回 event-stream 的 `initialize` 结果）。
3. **终端里**：随便问一句，然后看该终端 hooks 目录下的 `octop-hook.log`，应能看到 `hits=N http=200`（召回）与 `parsed=N imported=N`（上报）。

## 5. 故障排查

| 现象 | 原因 / 处理 |
|------|-------------|
| `401 missing bearer token` | 客户端没带 `Authorization`；检查 hooks 的 `config.json` / MCP 条目的 header |
| `401 invalid token` | token 写错或已被删除；到 Dashboard 重建 |
| `401 token revoked` | 该 token 已撤销；重建一个 |
| `400 either bind the token to a single expert, or send X-Octop-Agent-Id` | token 不限专家或绑定多个专家，但请求没带 `X-Octop-Agent-Id`；给 token 绑定单个专家，或补上该头（响应里 `allowed_expert_ids` 是允许列表） |
| `403 this token is not scoped to that expert` | 带的专家不在 token 范围内；切换 token 绑定或换 token |
| `403 token owner cannot access that expert` | 该专家不属于 token 所有者、也未共享给他 |
| `404 missing or unknown agent_id` | 专家不存在或已停用；确认专家 ID 正确且处于启用状态 |
| `/mcp/memory` 404 | 服务未开启记忆 MCP：设 `OCTOP_MEMORY_MCP_ENABLED=1` 或先创建 token 后重启 |
| Codex hook 不执行 | Codex 首次需要 **trust** hook（或在启动时加 `--dangerously-bypass-hook-trust`） |
| DSH 不生效 | 插件是进程内加载，安装后需重启 DSH；确认 profile 的 `cordis.patch.yml` 有同名配置块 |
| 项目级安装后没生效 | 项目模式只写「注册」，hook 脚本和含 token 的 `config.json` 仍在用户目录；确认项目里注册的路径存在 |

## 6. 安全说明

- 服务端只保存 token 的 sha256，校验用常量时间比较；明文只在创建时返回一次
- token 绑定用户：调用者身份只从 token 推出，`X-Octop-User-Id` 不被信任
- token 可随时撤销、可切换专家；每次请求都会重读 token 行并按 owner/共享规则校验专家访问权
- `/mcp/memory/setup` 只返回脚本，不发放、也不内置任何凭据
