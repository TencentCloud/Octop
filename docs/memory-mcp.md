# 专家记忆 MCP Server 使用文档

> Octop 将专家记忆通过 **MCP（Streamable HTTP）** 暴露给外部 agent（编码 agent、机器人等），
> 与进程内 `MemoryService` 能力对齐。外部 agent 可读写专家记忆；每次写入都会带上
> `source` 标记，召回时可追溯来源。
>
> 适用版本：`feat/memory-mcp-extension` 分支（9 工具面）。

---

## 1. 连接信息

| 项 | 值 |
|---|---|
| Endpoint | `http://<octop-host>:<port>/mcp/memory` |
| 协议 | MCP Streamable HTTP（SSE + JSON） |
| 鉴权 | `Authorization: Bearer <OCTOP_MEMORY_MCP_TOKEN>` |
| 专家绑定 | `X-Octop-Agent-Id: <agent_id>` 请求头（一连接绑定一专家） |

### 1.1 鉴权（fail-closed）

- 服务端通过环境变量 `OCTOP_MEMORY_MCP_TOKEN` 配置独立 token；**未配置时不挂载** `/mcp/memory`（安全默认）。
- 每个请求必须带 `Authorization: Bearer <token>`，否则返回 `401`。
- Token 建议与 Octop 登录 JWT 完全隔离（独立凭据，仅限记忆通道使用）。

### 1.2 专家绑定（一连接一专家）

- 端点只有一个 `/mcp/memory`，专家在**连接时**通过 `X-Octop-Agent-Id` 头选择（如 `main`、`MRA7KP`）。
- 一次连接绑定一个专家，工具调用时**不再**传 agent id——调用方只需在建立会话时固定一个专家。
- 所有读写都落在该专家的 `Memory` 实例（默认 SQLite；PG 控制面可显式开启）。

### 1.3 调用者追溯

- 内网增强：MCP 请求的调用者 user id 通过 `X-Octop-User-Id` 头（或工具显式 `user` 参数）传递，
  `memory_capture` / `memory_save` / `memory_update` 会按调用者做 per-user 追溯。
- stateless Streamable HTTP 下 mcp SDK 不提供 `ctx.request_context`，实现用 ContextVar 跨
  ASGI 中间件 → 工具传递，因此每次请求头里的调用者身份是可靠的。

---

## 2. 工具清单（9 个）

### 2.1 读取

| 工具 | 参数 | 说明 |
|---|---|---|
| `memory_recall` | `query: str`, `limit: int = 5`, `user: str | None` | 语义召回专家记忆（原子/树，L2）。日常使用入口 |
| `memory_raws` | `query: str | None`, `session_id: str | None`, `host: str | None`, `user: str | None`, `limit: int = 50` | 查 L0 原始事件（采集即可见，提取前也能查） |

### 2.2 写入

| 工具 | 参数 | 说明 |
|---|---|---|
| `memory_capture` | `content: str`, `source: str`, `session_id: str | None`, `user: str | None` | 记录一条 **L0 原始事件**，走提取流水线（extract → candidate → promote → atom）。适合记录对话/事件原文 |
| `memory_save` | `content: str`, `source: str`, `topic: str | None`, `user: str | None` | 直接持久化一条**结构化事实**到原子层（L2，不经过提取）。适合已知的明确事实 |
| `memory_update` | `atom_id: str`, `new_content: str`, `source: str`, `note: str = "mcp update"`, `user: str | None` | 显式更新一条记忆：旧 atom 标记 deprecated，新事实立即可召回 |

### 2.3 提取 / 审核流水线

| 工具 | 参数 | 说明 |
|---|---|---|
| `memory_extract` | `session_id: str | None`, `limit: int = 100`, `promote: bool = False` | 手动触发提取：取最近 L0 事件 → LLM 类型化提取 → 候选（pending）。`promote=True` 时直接晋升检查 |
| `memory_candidates` | `status: str | None`, `session_id: str | None`, `limit: int = 50` | 列出候选记忆（默认 pending 队列；可用 status 过滤 promoted / rejected / needs_review） |
| `memory_promote` | `candidate_ids: list[str]`, `importance: str | None` | 审核晋升候选（L1 → L2 原子），可覆盖 importance |
| `memory_reject` | `candidate_id: str`, `reason: str = "rejected by external caller"` | 拒绝候选并记录原因（journal 可审计） |

---

## 3. 使用示例

### 3.1 直接 HTTP（curl）

```bash
TOKEN="<OCTOP_MEMORY_MCP_TOKEN>"
AGENT="main"                      # 绑定的专家
BASE="http://127.0.0.1:8088/mcp/memory"

# 初始化（MCP 握手）
curl -s -X POST "$BASE/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Octop-Agent-Id: $AGENT" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"cli","version":"1.0"}}}'
```

### 3.2 记录一条原始事件（L0）

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "memory_capture",
    "arguments": {
      "content": "user reported: the report panel banner is not rendering",
      "source": "review-bot",
      "user": "alice"
    }
  }
}
```

### 3.3 直接保存一条事实（L2）

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "memory_save",
    "arguments": {
      "content": "机票记忆体系 M1 采用 Octop 专家记忆平台作为目标服务",
      "source": "planning-agent",
      "topic": "flight-memory-system"
    }
  }
}
```

### 3.4 召回

```json
{
  "jsonrpc": "2.0",
  "id": 4,
  "method": "tools/call",
  "params": {
    "name": "memory_recall",
    "arguments": { "query": "机票记忆体系", "limit": 5 }
  }
}
```

### 3.5 用 MCP 客户端 SDK

```python
# pip install mcp
import asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def main():
    # 注意：endpoint 需以 / 结尾，且须带鉴权与专家绑定头
    async with streamablehttp_client(
        "http://127.0.0.1:8088/mcp/memory/",
        headers={"Authorization": "Bearer <token>",
                 "X-Octop-Agent-Id": "main"},
    ) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print([t.name for t in tools.tools])  # 9 个 memory_* 工具
            res = await session.call_tool("memory_recall", {"query": "octop 沙箱"})
            print(res)

asyncio.run(main())
```

---

## 4. 部署与配置

| 配置 | 说明 |
|---|---|
| `OCTOP_MEMORY_MCP_TOKEN` | 必填；未设置则 `/mcp/memory` 不挂载（fail-closed） |
| `X-Octop-Agent-Id` | 连接时必填；专家 id（`octop agent list` 可查） |
| 记忆后端 | 默认 SQLite（`~/.octop/agents/<id>/memory.sqlite`）；PG 控制面显式开启 |

### 4.1 开启步骤

1. 设置环境变量 `OCTOP_MEMORY_MCP_TOKEN=<token>`（可写入 `~/.octop/env`，启动自动加载）。
2. 重启 `octop run`。
3. 验证：`curl -i http://<host>:<port>/mcp/memory/` 应返回 `401`（未带 token）或 MCP 协议响应（带 token）。
4. 外部 agent 按 §1 连接信息接入。

---

## 5. 与进程内 MemoryService 的关系

| MCP 工具 | MemoryService 对应 | 层级 |
|---|---|---|
| `memory_capture` | `add_raw` | L0 原始事件 |
| `memory_extract` / `memory_promote` / `memory_reject` | 提取流水线（extract → candidate → promote） | L0 → L1 → L2 |
| `memory_raws` | 查询 raw events | L0 |
| `memory_candidates` | 查询候选队列 | L1 |
| `memory_recall` / `memory_save` / `memory_update` | 原子/树读写 | L2 |

写入链路：`capture`（L0）→ `extract`（L1 候选）→ `promote`（L2 原子）；直接 `save` 则跳过提取直写 L2。
