# 专家记忆 MCP Server

Octop 把专家记忆通过 MCP（Model Context Protocol）开放给外部 Agent / Bot：Claude Code、Codex、DSH 这类编码助手可以和 Octop 专家共用同一份长期记忆。


- 端点：`/mcp/memory`（Streamable HTTP，**stateless**：每次请求独立，服务重启后客户端不会因为 `Mcp-Session-Id` 失效而报 `-32600 Session not found`）
- 专家选择：**token 直接绑定一个专家**（在 Dashboard「记忆 → MCP 接入」建 token 时选，之后可随时切换）；客户端不再需要专家 ID
- 调用者身份：**用户级 token**（`Authorization: Bearer omcp_…`），不是实例共享 token；`X-Octop-User-Id` 不再被信任
- 接入端：hooks / 原生插件会带 `X-Octop-Client: <terminal>`；Dashboard 可看到每个 token 被哪些接入端用过，并按接入端启用/禁用

## 1. 鉴权模型

每个 Octop 用户可以有多个 token，每个 token 带一个客户端名字（如 `codex@macbook`），可以：

- 绑定一个专家（`expert_ids` 恰好 1 个）：客户端只带 token 就能用，服务端按绑定路由
- 也可以不绑（`null`）或绑多个（高级用法）：此时客户端必须带 `X-Octop-Agent-Id` 指定这次用哪个
- 随时在 Dashboard 上**切换 token 绑定的专家**（`PATCH /api/memory-mcp/tokens/<token_id>`），下一次请求立即生效
- 单独吊销某一个客户端，不影响其它客户端
- 追溯每一条记忆是哪个客户端写的（`payload.caller` 是用户，`payload.source_host` 取 token 名字，不依赖客户端自报）

服务端只保存 token 的 sha256；校验用常量时间比较。**明文只在创建时返回一次**。

### 1.1 创建 / 列出 / 吊销 token

登录 Octop 后调用（`<token>` 是 Octop 的登录 token，与 MCP token 不是一回事）：

```bash
# 创建：返回一次性明文 token
curl -sS -X POST "https://<octop-host>/api/memory-mcp/tokens" \
  -H "Authorization: Bearer <your-octop-session-token>" \
  -H "Content-Type: application/json" \
  -d '{"name": "codex@macbook", "expert_ids": ["Z026BY"]}'

# 列出（不含明文）
curl -sS "https://<octop-host>/api/memory-mcp/tokens" \
  -H "Authorization: Bearer <your-octop-session-token>"

# 切换这个 token 绑定的专家（也可只改 name）
curl -sS -X PATCH "https://<octop-host>/api/memory-mcp/tokens/<token_id>" \
  -H "Authorization: Bearer <your-octop-session-token>" \
  -H "Content-Type: application/json" \
  -d '{"expert_ids": ["<另一个专家ID>"]}'

# 吊销
curl -sS -X DELETE "https://<octop-host>/api/memory-mcp/tokens/<token_id>" \
  -H "Authorization: Bearer <your-octop-session-token>"
```

`POST` 响应里的 `token` 字段形如 `omcp_…`，之后只显示 `token_hint`（`omcp_abcd…wxyz`）。

### 1.2 开启挂载

`/mcp/memory` 默认不挂载（fail-closed，对现有部署零影响）：只有设置环境变量
`OCTOP_MEMORY_MCP_ENABLED=1` 才挂载（进程启动时判定，设置后重启一次 Octop 生效）。
挂载后创建 / 轮换 token、切换专家都立即生效，不需要再重启。

## 2. 客户端配置

任何支持 Streamable HTTP MCP 的客户端都可以接入，只需两样东西：

| 配置 | 值 |
|------|----|
| URL | `https://<octop-host>/mcp/memory/`（或自建入口，见 §5） |
| Header `Authorization` | `Bearer omcp_…`（§1.1 创建、已绑定专家的那个 token） |

> 只有「不限专家」或「绑定了多个专家」的 token 才需要额外带 `X-Octop-Agent-Id`；绑定单个专家的 token 只靠 token 就够了。

### 2.1 Claude Code

```bash
claude mcp add --transport http octop-memory "https://<octop-host>/mcp/memory/" \
  --header "Authorization: Bearer omcp_…"
```

### 2.2 Codex

`~/.codex/config.toml`：

```toml
[mcp_servers.octop-memory]
url = "https://<octop-host>/mcp/memory/"
http_headers = { Authorization = "Bearer omcp_…" }
```

### 2.3 DSH / Cursor / Kiro / 其它客户端

在客户端的 MCP 配置里填 §2 的 URL 与 `Authorization` 即可（DSH 的 `mcpServers` 用 `type: "streamable-http"`）。

### 2.4 一键接入（客户端插件，推荐）

安装器在 octop-memory 仓库的 `plugins/harness`，不经过服务端，token 由你在运行时传入。

macOS / Linux：

```bash
curl -fsSL https://raw.githubusercontent.com/TencentCloud/octop-memory/main/plugins/harness/install.sh \
  | sh -s -- --url https://<octop-host>/mcp/memory/ --token omcp_…
```

Windows PowerShell：

```powershell
irm https://raw.githubusercontent.com/TencentCloud/octop-memory/main/plugins/harness/install.ps1 -OutFile install.ps1
.\install.ps1 -Url https://<octop-host>/mcp/memory/ -Token omcp_…
```

只装部分终端加 `--terminals claude-code,codex`；装到项目加 `--project "$PWD"`。
把 [AI-SETUP.md](https://github.com/TencentCloud/octop-memory/blob/main/plugins/harness/AI-SETUP.md)
连同 token 一起交给 AI，也可以自动完成安装。

### 2.5 hooks / 安装器（客户端侧）

自动召回、会话上报、一键安装和各终端适配属于**客户端侧**代码，已从本仓拆出：

- 安装器与 hooks：`octop-memory` 仓库的 `plugins/<client>/`
- DSH 原生插件 `dsh-octop-memory`：独立仓库 <https://github.com/ArvinQi/dsh-octop-memory> 发布（npm + GitHub Release）

本仓库只提供 MCP 服务端、用户级 token 与 Dashboard 管理页；没有安装器也能用（§2 的手动配置即可）。

## 3. 工具清单## 3. 工具清单

### 3.1 日常工具（任何 token 可用）

| 工具 | 作用 |
|------|------|
| `memory_search(query, max_results=5, corpus="all")` | 检索记忆，返回带虚拟 `path` 的命中（`corpus=raw` 只看原始事件） |
| `memory_get(path, start=None, lines=None)` | 把命中里的 `path` 解析成 markdown 全文 |
| `memory_save(content, source, topic=None, supersedes=None)` | 显式保存一条事实（跳过提炼，立即可召回；`supersedes` 用于更正） |
| `memory_capture(content="", source="", session_id=None, assistant=None, thread_id=None, dry_run=False, extract=True, events=None)` | 写原始事件（L0），交给提炼管线；默认**不自动晋升**。`events` 可传客户端已解析好的事件列表 |

### 3.2 审核 / 运维工具（**仅专家所有者**）

| 工具 | 作用 |
|------|------|
| `memory_raws(...)` | 查 L0 原始事件（FTS / 按会话、host、调用者过滤） |
| `memory_candidates(status=None, ...)` | 查 L1 候选（默认 pending） |
| `memory_extract(session_id=None, promote=None)` | 手动触发提炼；专家未运行时直接报错（不会为提炼启动专家） |
| `memory_promote(candidate_ids)` | 采纳候选（与记忆面板同一套实现） |
| `memory_reject(candidate_id, reason=..., actor=None)` | 忽略候选 |

外部 agent 默认只应该拿到 §3.1 的四个工具；把审核工具（能自己晋升自己写的内容）留给专家所有者。

## 4. 记忆分层与选工具

| 层 | 内容 | 读 | 写 |
|----|------|----|----|
| L0 原始事件 | 一轮对话 / 一条记录 | `memory_raws`、`memory_search(corpus="raw")` | `memory_capture` |
| L1 候选 | 提炼出的候选断言 | `memory_candidates` | `memory_extract` |
| L2 原子 / L3 主题页 | 长期记忆 | `memory_search`、`memory_get` | `memory_save`、`memory_promote` |

- 想把一段对话沉淀成记忆 → `memory_capture`，之后到记忆面板审核
- 已经确定的事实 → `memory_save`
- 想找背景 → `memory_search`；要原文 → `memory_get` / `memory_raws`

## 5. 部署与自建入口

- 反代 / ingress 只需暴露 `/mcp/memory`（以及给用户创建 token 用的 `/api/memory-mcp/tokens`）
- 客户端条目要指向别的地址（如公网入口）时，设置环境变量 `OCTOP_MEMORY_PUBLIC_MCP_URL`，或实例 `config.json` 的 `memory_public_mcp_url`
- token 的专家范围在创建时就固定；要调整请新建 token 并吊销旧的

## 6. 行为契约

- **脱敏**：`memory_capture` 走 octop-memory 的 capture 应用层，`redact_secrets` 默认开启，API key / token / password 会在入库前被替换
- **回声保护**：带上游召回标记（`## Memory Recall` / `[memory] Earlier in this workspace`）的内容不会入库
- **审核队列**：外部写入默认不自动晋升；是否晋升跟随专家自己的提炼配置
- **不自动启动专家**：专家停止时 capture 仍写 L0，但不会触发提炼、也不会为了提炼把专家拉起来（避免意外模型费用）
- **权限**：token 属于某个用户；每次请求都会重新校验该用户对目标专家的访问权（自己的 / 共享的专家 / 管理员），改 header 无法越权

## 7. 拆分说明（review 后的计划）

原 PR 把记忆 MCP、召回补丁、对话记录解析、终端安装器/hooks 放在了一起。按 review 建议拆成：

| PR | 内容 | 目标仓库 | 状态 |
|----|------|----------|------|
| a | MCP 服务端 + 用户级鉴权 + token 管理 UI + 文档（本文档） | Octop | 本 PR |
| b | 召回质量优化（实体后缀 / 强 token 排序） | octop-memory | 待提 |
| c | 对话记录解析 + 终端安装器 / hooks（`plugins/<client>/`） | octop-memory | 待提 |
| d | DSH 原生插件 `octop-memory-native` | 独立仓库 | 已拆分 |

服务端不依赖客户端增强：任何支持 Streamable HTTP MCP 的客户端按 §2 手动配置即可接入。
