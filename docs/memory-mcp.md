# 专家记忆 MCP Server 使用文档

> Octop 把**专家记忆**通过标准 **MCP（Streamable HTTP）** 暴露给外部 agent（编码 agent、机器人、
> 其他 AI 工具），能力与进程内 `MemoryService` 对齐：外部 agent 可以召回记忆、按路径下钻读全文、
> 写入新的事件与事实，并能区分"这条记忆是谁说的"。
>
> 当前工具面：**11 个 `memory_*` 工具**（读取 4 个 / 写入 3 个 / 提取与审核 4 个）。

---

## 1. 连接信息

| 项 | 值 |
|---|---|
| Endpoint | `http(s)://<octop-host>/mcp/memory`（MCP 侧实际请求路径为 `/mcp/memory/`） |
| 协议 | MCP Streamable HTTP（SSE + JSON） |
| 鉴权 | `Authorization: Bearer <OCTOP_MEMORY_MCP_TOKEN>` |
| 专家绑定 | `X-Octop-Agent-Id: <agent-id>` 请求头 |
| 调用者标识 | `X-Octop-User-Id: <user-id>` 请求头（可选，见 §1.3） |

### 1.1 鉴权（fail-closed）

- 服务端通过环境变量 `OCTOP_MEMORY_MCP_TOKEN` 配置这条通道的独立 token；**未配置时整个
  `/mcp/memory` 端点不挂载**（安全默认）。
- 每个请求都必须带 `Authorization: Bearer <token>`，否则返回 `401`。
- 建议该 token 与 Octop 登录凭据完全隔离——它是独立凭据，仅用于记忆通道。

### 1.2 专家绑定（按请求校验，无需重启）

- 端点只有一个 `/mcp/memory`，URL 里不含专家 id；专家由请求头 `X-Octop-Agent-Id` 选择。
- **每个请求都会用该 id 去专家注册表校验**（存在且处于启用状态），校验不通过返回 `404`。
  因此新建或停用专家**立即生效**，不需要重启服务。
- 所有读写都落在该专家的 `Memory` 实例上，工具调用时**不再**传 agent id。
- 记忆是**专家级共享**的：同一专家下的多个外部调用者看到同一份记忆，不做按人硬隔离；
  需要按人定位时依赖 §1.3 的发送者归属。

### 1.3 调用者归属（`X-Octop-User-Id`）

- 调用者身份通过 `X-Octop-User-Id` 头（或工具的显式 `user` 参数，优先级更高）传递。
- `memory_capture` / `memory_save` / `memory_update` 会把调用者 id **拼进内容前缀**
  `<user>说：…` 后再落库。原因：`AtomCard` 没有 user 列，把发送者写进正文才能随原子一起
  落库、被全文检索命中（查询里带上发送者名字即可命中其记忆）、并在召回时直接可见。
- 因此**不要把名字重复写进 `content`**；内容已带同名前缀时不会重复拼接；不带该头时保持原文。
- 未匹配到调用者身份时，写入仍然成功，只是没有前缀。

---

## 2. 工具清单（11 个）

### 2.1 读取（4 个）

| 工具 | 参数 | 说明 |
|---|---|---|
| `memory_recall` | `query: str`, `limit: int = 5`, `session_id?: str`, `thread_id?: str`, `user?: str` | **读入口首选**。跑完整召回管线（分词 → 路由 → FTS → 重排 → 去重），返回结构化片段 + 可直接注入 system prompt 的 markdown（`rendered`）。L2 原子优先，主题页标题并入 atom 命中，L0 原始事件仅兜底。**自动注入（hook）场景建议传 `session_id`**：管线会据此把本会话的 raw 排除，避免"注入 → 被记录 → 下轮又召回"的回声；`thread_id` 则启用共指消解（"那个项目" 靠该线程的 active-entity stack） |
| `memory_search` | `query: str`, `max_results: int = 5`, `corpus: str = "all"` | 同一套召回管线，但**不渲染 markdown**，而是给每条命中一个虚拟 `path`，交给 `memory_get` 下钻。`corpus`：`all`/`memory`（原子+原始事件同管线）、`atom`（只要 L2 原子）、`raw`（直接走 L0 全文检索，不受"有原子命中就丢 raw"的兜底影响） |
| `memory_get` | `path: str`, `start?: int`, `lines?: int` | 把命中路径解析成完整 markdown。支持 `atom/<atom_id>.md`、`page/<entity_id>.md`、`raw/<YYYY-MM-DD>/<event_id>.md`；长内容用 `start`/`lines` 分页（1-based）。路径非法或过期时返回 `{error, hint}` 而不是抛栈 |
| `memory_raws` | `query?: str`, `session_id?: str`, `host?: str`, `user?: str`, `limit: int = 50` | **原始事件（证据源）**。`query` 走全文检索（写入后立即可见，提取前也能查），其余字段做结构化过滤，按时间倒序返回 |

返回形状：

```jsonc
// memory_recall
{ "memories": [{ "source_id", "timestamp", "layer", "text" }], "count", "rendered", "caller" }
// memory_search
{ "hits": [{ "path", "layer", "snippet", "occurred_at", "source_id" }], "total", "corpus", "hint" }
// memory_get
{ "path", "kind", "content", "total_lines", "from_line", "to_line", "truncated", "metadata" }
// memory_raws
{ "events": [{ "event_id", "timestamp", "session_id", "user", "event_type", "source", "content" }], "count", "caller" }
```

### 2.2 写入（3 个，两条通道）

| 工具 | 参数 | 说明 |
|---|---|---|
| `memory_capture` | `content: str`, `source: str`, `session_id?: str`, `user?: str` | **记录原始事件（L0）**：走 提取 → 候选 → 晋升 → 原子 的流水线，适合记录对话/事件原文。写入后立即可用 `memory_raws` / `memory_search(corpus="raw")` 查；晋升成原子后才能被 `memory_recall` 召回。`session_id` 缺省派生为 `ext:{source}:{user}`，用于让提取管线按会话分组蒸馏 |
| `memory_save` | `content: str`, `source: str`, `topic?: str`, `user?: str` | **直接保存事实（L2）**：不经过提取，立即可召回。适合已知的明确事实/约定 |
| `memory_update` | `atom_id: str`, `new_content: str`, `source: str`, `note: str = "mcp update"`, `user?: str` | **更新记忆**：旧原子标记 deprecated，新事实立刻可召回，并带 `supersedes` 关联。适合纠正过时事实 |

`memory_capture` 是**幂等**的：同一 `session_id` + 同一内容重复写入时不会产生重复 L0 事件，
返回里带 `duplicate: true` 并复用已有 `event_id`（下游提取因此可以反复重跑）。

它还有**回声保护**：内容里带 `memory_recall` 的注入标记（`[memory] Earlier in this workspace` /
`## Memory Recall`）时**不写入**，直接返回 `{recorded: false, skipped: "recall_echo"}`。
原因：MCP 写路径直接调 `Memory.add_raw`，绕过了 `MemoryRuntime.capture` 的 `skip_memory_echo`；
不补这层，hook 注入的召回块会被当作新事件采集，形成"注入 → 采集 → 再召回"的放大环。

### 2.3 提取与审核流水线（4 个）

| 工具 | 参数 | 说明 |
|---|---|---|
| `memory_extract` | `session_id?: str`, `limit: int = 100`, `promote: bool = False` | 手动触发提取：取最近 L0 事件 → LLM 类型化提取 → 候选（pending）；`promote=True` 时直接跑晋升检查。复用**该专家进程内**的 `MemoryService`（含其配置的提取模型）；专家未运行/无记忆运行时时返回 `error` |
| `memory_candidates` | `status?: str`, `session_id?: str`, `limit: int = 50` | 列出 L1 候选（默认 pending）。`status` 可取 `pending` / `promoted` / `rejected` / `needs_review` / `conflict`，非法值报错 |
| `memory_promote` | `candidate_ids: list[str]`, `importance?: str` | 审核晋升：对指定候选跑 5 项晋升检查，通过则写入 L2 原子并记录 journal |
| `memory_reject` | `candidate_id: str`, `reason: str = "rejected by external caller"` | 拒绝候选并记录原因（不进原子层，journal 可审计） |

---

## 3. 记忆分层与选工具

| 层级 | 内容 | 对应工具 |
|---|---|---|
| L0 | 原始事件（原话、证据） | `memory_capture` 写入；`memory_raws` / `memory_search(corpus="raw")` 读取 |
| L1 | 候选（提取产物，待审核） | `memory_extract` 产生；`memory_candidates` 查看；`memory_promote` / `memory_reject` 裁决 |
| L2 | 原子（长期记忆，可被召回） | `memory_save` / `memory_update` 直写；`memory_capture` 经流水线晋升；`memory_recall` / `memory_search` 召回 |
| L3 | 主题页（实体页） | 随晋升重新生成；可用 `memory_get(page/<entity_id>.md)` 读取 |

按意图选工具：

- 只想把相关背景拉进上下文 → `memory_recall`
- 要定位某条具体记忆并读全文 → `memory_search` 拿 `path`，再 `memory_get(path)`
- 要原话/证据，或内容刚写入还没晋升 → `memory_raws`（或 `memory_search(corpus="raw")`）
- 记录对话/事件 → `memory_capture`；记录明确事实/规则 → `memory_save`；纠正过时事实 → `memory_update`
- 处理审核队列 → `memory_candidates` → `memory_promote` / `memory_reject`

---

## 4. 使用示例

> 下面默认客户端**直连** Octop 的 `/mcp/memory`。如果 Octop 前面还挂了一层网关/代理（例如由代理统一校验调用人身份并注入上游 token），只需把 URL 换成代理端点、按代理要求填它需要的凭证（通常是**一个** token 头）；此时 `Authorization` / `X-Octop-User-Id` 由代理负责，**不要**在客户端重复配置。

> 接入任一客户端都是**两步**：① 配好 MCP 服务器（§4.3 Kiro / §4.4 Claude Code / §4.5 DSH 各自的「配置」段）——这一步只让工具**可用**；② 再配**自动化**（Kiro 与 Claude Code 挂 hooks；DSH 新建并使用「共享记忆」预设）——这一步才会**自动召回、自动沉淀**。只做第 ① 步的话，每次都得手动让模型去调工具。§4.1 / §4.2 是最简的手动自测形态。

### 4.1 直接 HTTP（curl）

```bash
TOKEN="<OCTOP_MEMORY_MCP_TOKEN>"
AGENT="<agent-id>"
BASE="http://127.0.0.1:<port>/mcp/memory"

# 1) 初始化（MCP 握手）
curl -s -X POST "$BASE/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Octop-Agent-Id: $AGENT" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"cli","version":"1.0"}}}'

# 2) 记录一条原始事件（L0）
curl -s -X POST "$BASE/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Octop-Agent-Id: $AGENT" \
  -H "X-Octop-User-Id: alice" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"memory_capture","arguments":{"content":"报告页横幅没有渲染出来","source":"review-bot"}}}'
```

其余工具只是换 `params.name` / `params.arguments`：

```jsonc
// 直接保存一条事实（L2，立即可召回）
{ "name": "memory_save",
  "arguments": { "content": "部署约定：记忆端点挂在 /mcp/memory", "source": "planning-agent", "topic": "octop-deploy" } }

// 召回
{ "name": "memory_recall", "arguments": { "query": "部署约定", "limit": 5 } }

// 检索拿 path
{ "name": "memory_search", "arguments": { "query": "部署约定", "corpus": "atom" } }

// 读全文（path 来自上一步 hits[].path）
{ "name": "memory_get", "arguments": { "path": "atom/<atom_id>.md", "lines": 40 } }
```

### 4.2 MCP 客户端 SDK（Python）

```python
# pip install mcp
import asyncio

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


async def main():
    # 注意：endpoint 以 / 结尾；鉴权与专家绑定都放在 headers 里
    async with streamablehttp_client(
        "http://127.0.0.1:<port>/mcp/memory/",
        headers={
            "Authorization": "Bearer <token>",
            "X-Octop-Agent-Id": "<agent-id>",
            "X-Octop-User-Id": "alice",
        },
    ) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print([t.name for t in tools.tools])  # 11 个 memory_* 工具

            await session.call_tool(
                "memory_capture",
                {"content": "报告页横幅没有渲染出来", "source": "review-bot"},
            )
            res = await session.call_tool("memory_recall", {"query": "报告页 横幅"})
            print(res)


asyncio.run(main())
```

### 4.3 Kiro

Kiro 原生支持远程 MCP（`url` + `headers`）。配置分两级，同名条目以工作区为准：

- 工作区：`.kiro/settings/mcp.json`
- 用户级：`~/.kiro/settings/mcp.json`
- 打开方式：命令面板 `Kiro: Open workspace MCP config (JSON)` / `Kiro: Open user MCP config (JSON)`；保存后自动热重载。

```jsonc
{
  "mcpServers": {
    "octop-memory": {
      "type": "streamable_http",
      "url": "https://<octop-host>/mcp/memory/",
      "headers": {
        "Authorization": "Bearer <OCTOP_MEMORY_MCP_TOKEN>",
        "X-Octop-Agent-Id": "<agent-id>",
        "X-Octop-User-Id": "<your-user-id>"
      },
      "disabled": false
    }
  }
}
```

Kiro 侧注意事项：

- **远程 `url` 必须是 `https`**（只有本地回环允许 `http`）。
- 工具名带**服务器名前缀**：服务器名 `octop-memory` → 工具 `mcp_octop_memory_memory_recall`；在 hooks 或提示词里必须写全名。
- 工具默认不放行：在 `~/.kiro/settings/permissions.yaml` 里找到 `capability: mcp` 的 `match` 列表，按需加 `effect: allow`（只读先放 `memory_recall` / `memory_raws`，需要沉淀再放 `memory_capture` / `memory_save`）。
- 用 `${VAR}` 引用环境变量时，要先把变量加入 Kiro 的允许列表（设置项 `Mcp Approved Env Vars`），否则不会被展开。
- 校验：会话里执行 `/mcp`，确认服务器已连接、工具已加载。

#### 自动化：hooks（配好 MCP 之后必配）

**只配 `mcp.json` 只是"工具能用"——不会自动召回、也不会自动沉淀，必须再挂 hooks。** Kiro 的 hooks 放在 `~/.kiro/hooks/*.json`，用 `trigger` + `action.type: agent` 让模型在固定时机去调对应工具。

提交提示词时召回 —— `~/.kiro/hooks/memory-recall-on-prompt-submit.json`：

```jsonc
{
  "version": "v1",
  "hooks": [
    {
      "name": "Recall Memory on Prompt Submit",
      "trigger": "UserPromptSubmit",
      "action": {
        "type": "agent",
        "prompt": "回答前，按需主动召回相关记忆来辅助本次工作。结合用户本次输入与当前项目上下文构造查询，调用 `mcp_octop_memory_memory_recall`。若本次输入与已召回记忆无关可跳过，不要重复召回同一查询。"
      },
      "description": "收到消息时自动召回相关记忆，提供上下文连续性。",
      "enabled": true
    }
  ]
}
```

会话结束时沉淀 —— `~/.kiro/hooks/memory-save-on-stop.json`：

```jsonc
{
  "version": "v1",
  "hooks": [
    {
      "name": "Save Memory on Session End",
      "trigger": "Stop",
      "action": {
        "type": "agent",
        "prompt": "会话结束前静默沉淀：1) 调用 `mcp_octop_memory_memory_capture` 记录本次会话（source=\"kiro-session\"，session_id 形如 \"session-YYYY-MM-DD-主题\"）；2) 对值得长期保留的事实（偏好、约定、架构决策、环境配置）调用 `mcp_octop_memory_memory_save`（source=\"kiro-session\"）。只写对未来确有价值的信息；成功后一句话告知，不要复述会话内容。"
      },
      "description": "会话结束时把可复用事实沉淀到 octop-memory。",
      "enabled": true
    }
  ]
}
```

改完 hooks / permissions 后重载或重启 Kiro 生效。

### 4.4 Claude Code

Claude Code 直接支持远程 HTTP + 自定义请求头：

```bash
claude mcp add --transport http octop-memory https://<octop-host>/mcp/memory/ \
  --header "Authorization: Bearer <token>" \
  --header "X-Octop-Agent-Id: <agent-id>" \
  --header "X-Octop-User-Id: <your-user-id>"
```

`--header` 可重复（短写 `-H`）。也可以直接写配置文件（`.mcp.json` 项目级 / `~/.claude/settings.json` 用户级）：

```jsonc
{
  "mcpServers": {
    "octop-memory": {
      "type": "http",
      "url": "https://<octop-host>/mcp/memory/",
      "headers": {
        "Authorization": "Bearer ${OCTOP_MEMORY_MCP_TOKEN}",
        "X-Octop-Agent-Id": "<agent-id>",
        "X-Octop-User-Id": "<your-user-id>"
      }
    }
  }
}
```

Claude Code 侧注意事项：

- Streamable HTTP 写 `"type": "http"`（MCP 规范名 `streamable-http` 也接受）；**带 `url` 就必须带 `type`**，否则该条目会被当作 stdio 服务器跳过。
- 工具名带前缀：`mcp__octop-memory__memory_recall`。
- 排查：`claude mcp list`、`claude mcp get octop-memory`，会话内 `/mcp`。

#### 自动化：hooks（配好 MCP 之后必配）

同样，**只加 MCP 服务器不会自动召回/沉淀**。Claude Code 在 `settings.json` 的 `hooks` 字段挂命令脚本（脚本放 `~/.claude/hook-events/`），两个事件各一个：

| 脚本 | 事件 | 作用 |
|---|---|---|
| `octop-user-prompt-recall.mjs` | `UserPromptSubmit` | 向 stdout 注入「先召回」的指令；真正调用工具的是模型，脚本**不直连 MCP**，任何异常静默放行、不阻断本轮 |
| `octop-stop-capture.mjs` | `Stop` | 输出 `{"decision":"block","reason":"..."}`，让模型在追加的一轮里执行 `memory_capture`；`stop_hook_active` 为真时直接退出，防止召回/沉淀互相触发成死循环 |

```jsonc
// ~/.claude/settings.json
{
  "hooks": {
    "UserPromptSubmit": [
      { "hooks": [ { "type": "command", "command": "node ~/.claude/hook-events/octop-user-prompt-recall.mjs" } ] }
    ],
    "Stop": [
      { "hooks": [ { "type": "command", "command": "node ~/.claude/hook-events/octop-stop-capture.mjs" } ] }
    ]
  }
}
```

`octop-user-prompt-recall.mjs` 最小实现：

```javascript
#!/usr/bin/env node
// UserPromptSubmit：把「先召回」指令注入本轮上下文；真正调用 MCP 工具的是模型。
process.stdout.write(
  "[octop-memory] 回答前先按需召回相关记忆：结合用户输入与当前项目上下文构造查询，" +
    "调用 MCP 工具 mcp__octop-memory__memory_recall；与本轮无关可跳过，不要重复召回同一查询。\n",
);
```

`octop-stop-capture.mjs` 最小实现：

```javascript
#!/usr/bin/env node
// Stop：让模型多跑一轮，把本轮可复用事实写入 L0。
import fs from "node:fs";

let payload = {};
try {
  const raw = fs.readFileSync(0, "utf8");
  if (raw.trim()) payload = JSON.parse(raw);
} catch {
  // 解析失败也继续：沉淀不该因为载荷缺字段而丢掉
}

if (payload.stop_hook_active) process.exit(0); // 防召回/沉淀互相触发

process.stdout.write(
  JSON.stringify({
    decision: "block",
    reason:
      "会话结束前静默沉淀：调用 mcp__octop-memory__memory_capture 写入本轮可复用事实" +
      '（source="claude-code"）；没有可沉淀内容就不要写入，成功后一句话告知即可。',
  }) + "\n",
);
```

### 4.5 DSH（DeepSeek Harness）

DSH 在 **Settings → MCP** 里管理 MCP 服务器（定义持久化在 `~/.dsh/storages/mcp_servers.json`）。设置页新增一条 Streamable HTTP 服务器时，对应的字段如下：

```jsonc
{
  "serverName": "octop-memory",
  "transport": "streamable-http",
  "enabled": true,
  "url": "https://<octop-host>/mcp/memory/",
  "headers": [
    { "name": "Authorization", "value": "Bearer ${OCTOP_MEMORY_MCP_TOKEN}" },
    { "name": "X-Octop-Agent-Id", "value": "<agent-id>" },
    { "name": "X-Octop-User-Id", "value": "<your-user-id>" }
  ],
  "toolCallTimeoutMs": 60000,
  "failOnStartupError": true
}
```

注意事项：

- `transport` 取 `streamable-http`（另支持 `stdio`）；`enabled: false` 停用整条；`failOnStartupError` 决定连接失败是否阻断启动。
- 设置页里的 Headers 是每行一个 `名称: 值`，值支持 `${ENV}` 替换；密钥类变量交给 DSH 的全局环境变量/凭据存储，不要写进明文配置。
- DSH 默认**按需注入** MCP 工具：会话里先检索一次，才会把 `memory_*` 挂进当前对话——所以只加服务器**更不会**自动召回/沉淀。
- 新增/修改服务器后按提示重连；若工具列表没有刷新，重启 `dsh web`。

#### 自动化：共享记忆预设（配好 MCP 之后必配）

和 Kiro / Claude Code 要挂 hooks 一样，DSH 这边还要**新增一个「共享记忆」模式的 agent preset，并用它开会话**，自动化才会发生：

- 会话首轮：先 `memory_recall`，把相关原子记忆拉进上下文；
- 每轮结束：若本轮产生了可沉淀的事实，调用一次 `memory_capture`（`source` 标记客户端来源、`session_id` 用工作目录派生）；寒暄或已记录内容不重复写。

预设是一个目录（`~/.dsh/.agent-presets/<你的预设>/`），含 `preset.yml`（名称与描述）和 `agent.cordis.yml`（该预设的完整组合）：

```text
<你的预设>/
  preset.yml
  agent.cordis.yml     # 共享记忆策略写在 persona 文本末尾
```

`agent.cordis.yml` 的 `persona` 里追加的策略段（等价于 Kiro / Claude Code 的 hooks）：

```text
── 共享记忆 (shared memory) ─────────────────────────────
This preset auto-reads and auto-writes the octop-memory expert store so durable facts carry across sessions and experts: memory_recall at conversation start, memory_capture at turn end.

会话开始时(本会话首轮、尚无历史):若工具列表里没有 `memory_recall`,先按需注入 octop-memory 工具,再调用 `memory_recall(query=用户当前目标全文)`,把相关原子记忆纳入上下文。

每轮结束时(给出最终回复前):若本轮产生了可沉淀的事实(需求、决定、偏好、约定、结论、关键路径),调用一次 `memory_capture`:
  content: 1–3 句简洁事实摘要(不写机密、不做原始转储)
  source: 'dsh:shared-memory'
  session_id: 'ext:dsh:<当前工作目录名>'
寒暄或已记录内容不重复记录;没有可沉淀事实就不调用。
```

- 从自带预设**拷贝到自己目录再改**，不要直接改部署自带的预设（升级会覆盖）。
- 建好后要在会话里**选择这个预设**才生效；已经在跑的会话不会自动切换。

### 4.6 其它 MCP 客户端

多数客户端共用同一份 JSON 描述一个 Streamable HTTP server：

```jsonc
{
  "mcpServers": {
    "octop-memory": {
      "type": "streamable-http",
      "url": "https://<octop-host>/mcp/memory/",
      "headers": {
        "Authorization": "Bearer <OCTOP_MEMORY_MCP_TOKEN>",
        "X-Octop-Agent-Id": "<agent-id>",
        "X-Octop-User-Id": "<your-user-id>"
      }
    }
  }
}
```

只支持 stdio 的客户端可以用 `mcp-remote` 这类桥接工具转发到远程端点；`type` 的取值随客户端而异（有的写 `http`，有的写 `streamable-http`），以客户端文档为准。自动化同样取决于该客户端有没有 hooks / 预设机制：只挂服务器通常只解决"工具可用"。

---

## 5. 部署与配置

| 配置 | 说明 |
|---|---|
| `OCTOP_MEMORY_MCP_TOKEN` | 必填。未设置时 `/mcp/memory` 不挂载（fail-closed） |
| `X-Octop-Agent-Id` | 每个请求必填，指向一个存在且启用的专家 |
| `X-Octop-User-Id` | 可选；用于把发送者写进记忆正文（§1.3） |
| 记忆后端 | 由专家配置 `memory.backend` 决定：默认 SQLite（`memory.sqlite`）；PostgreSQL 控制面下默认复用控制面 DSN（每专家 schema） |

开启步骤：

1. 设置环境变量 `OCTOP_MEMORY_MCP_TOKEN=<token>`。
2. 重启 Octop 服务（挂载发生在启动阶段）。
3. 验证：不带 token 请求 `/mcp/memory/` 应返回 `401`；带 token 且带合法
   `X-Octop-Agent-Id` 时应返回 MCP 协议响应（未知/停用专家返回 `404`）。
4. 外部 agent 按 §1 / §4 接入。

---

## 6. 行为契约与边界

- **写入分两条通道**：`memory_capture` 走"提取 → 候选 → 晋升"（学习型记忆，质量由流水线把关）；
  `memory_save` / `memory_update` 是权威直写（规则/明确事实，立即可召回）。
  晋升治理（提取触发、候选审核）保留在服务端，站内会话与外部写入走**同一套**记忆治理路径。
- **capture 之后 recall 无结果属预期**：内容还在 L0，需要经提取晋升成原子才会被召回；
  想立刻看到请用 `memory_raws` 或 `memory_search(corpus="raw")`。
- **capture 幂等**：同 `session_id` + 同内容不重复落库（见 §2.2）。
- **召回回声有双向保护**：写入侧 `memory_capture` 丢弃带召回标记的内容（`skipped=recall_echo`）；
  读取侧建议 hook 给 `memory_recall` 传与 capture 一致的 `session_id`，把本会话的 raw 排除。
  两侧都做，才不会出现"注入 → 采集 → 再召回"的放大环（§4.3 / §4.4 的自动召回就是这个场景）。
- **召回是专家级共享**，不做按人隔离；按发送者定位依赖正文里的 `<user>说：` 前缀 + 全文检索。
- **错误形态**：`memory_get` 的坏路径返回 `{error, hint}`；`memory_search` 的非法 `corpus`、
  `memory_candidates` 的非法 `status` 直接报错（参数错误不会被静默吞掉）。
