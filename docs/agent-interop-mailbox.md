# Agent Teams：Inbox + Callback 方案

**状态：** 已实现（harness `teams/` + octop `GlobalProcessor` 作为 `TeamProcessor`）
**范围：** `octop-harness`（主实现）+ `octop`（宿主适配）
**关联：** [agent-call-agent.md](./agent-call-agent.md)、[agent-delegation.md](./agent-delegation.md)

> 说明：早前实现的 `AgentMailbox`（把所有 `stream`/`call` 透明入队）将被本方案取代。
> 本方案核心：`stream`/`call` 回到**原始直连**行为；互调能力收敛到一个**全局 inbox** +
> 可选 **callback processor**；相关代码集中到 `octop_harness/teams/`。

---

## 1. 目标

1. 全局一个 `HarnessAgentInboxManager`（收件箱队列），统一管理所有 agent 的收件箱消息，
   每条消息含：`target`（收件人）、`source`、`source_thread_id`、`status` 等关键信息。
2. `HarnessAgentManager` 提供两种使用方式：
   - **不使用 inbox**：`stream` / `call` 入参与行为**与重构前完全一致**（直连 agent，无队列）。
   - **使用 inbox**：构造时提供一个 `callback`（process 方法/类）。提供后，manager 启用对 inbox
     队列的处理：收到消息 → `target.call` → 拿到结果 → 组合提示词后请求
     `source` agent + `source_thread_id` 再 `call` → 把返回通过 callback 暴露出来（主动推送）。
3. `peer_agent` 工具不放在 `builtin/`。新增 `octop_harness/teams/` 目录，集中放 inbox_manager、
   工具、callback 定义。工具**不进 agent 默认工具集**，仅在「启用 team」时由 manager 提供。
4. `ask_agent` 工具：**默认同步阻塞**等待结果返回；**仅当 manager 配置了 callback** 时才走异步
   ——向 `HarnessAgentInboxManager` 投递一条消息并立即返回 `id`。

---

## 2. 模块布局

```
octop_harness/teams/
  __init__.py        # 导出公开符号
  inbox.py           # InboxMessage, InboxStatus, HarnessAgentInboxManager
  processor.py       # TeamProcessor 协议, ReplyEvent, 默认提示词组合
  tools.py           # build_team_tools(manager) -> [agent_list, ask_agent]
  util.py            # extract_call_response / first_user_text 等纯函数
```

删除：`octop_harness/mailbox.py`、`octop_harness/peer.py`（内容拆入 `teams/`）。

---

## 3. 数据模型

### 3.1 `InboxMessage`（队列项）

```python
InboxStatus = Literal["queued", "running", "replying", "done", "failed", "cancelled"]

@dataclass
class InboxMessage:
    id: str
    target_agent_id: str            # 收件人：要执行任务的 agent
    source_agent_id: str            # 发起方 agent（回信对象）
    source_thread_id: str | None    # 回信时落在 source 上的 thread（保上下文）
    message: str                    # 任务内容
    user_id: str | int
    status: InboxStatus = "queued"
    original_user_prompt: str | None = None   # 组合提示词用
    error_text: str | None = None
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any] = {}             # 透传给 callback（session_key 等）
```

> `target.call` 的结果与 `source` 合成回复都是 worker 内的**局部过程值**，不挂在 `InboxMessage` 上：
> 不入库、历史靠 checkpoint，没有事后查结果的场景；`reply_text` 经 `ReplyEvent` 透传给 `on_reply`。

### 3.2 `ReplyEvent`（回调出参）

```python
@dataclass
class ReplyEvent:
    inbox_id: str
    status: Literal["done", "failed", "cancelled"]
    source_agent_id: str
    source_thread_id: str | None
    target_agent_id: str
    user_id: str | int
    reply_text: str | None          # source agent 合成后的主动回复正文
    error_text: str | None
    metadata: dict[str, Any]
```

### 3.3 `TeamProcessor`（process 方法/类）

```python
class TeamProcessor(Protocol):
    # 组合「target 结果 → 给 source 的提示词」；teams 提供默认实现，可覆盖
    def compose_followup(self, msg: InboxMessage, result_text: str) -> str: ...

    # 最终把 source 的回复暴露给宿主（写 thread / IM 推送 / WS 通知）
    async def on_reply(self, event: ReplyEvent) -> None: ...
```

- `compose_followup` 默认实现放在 `teams/processor.py`（等价现 `delegation/synthesis.py`）。
- `on_reply` 是「让用户感知主动推送」的唯一出口；宿主在此投递文本。

---

## 4. `HarnessAgentInboxManager`

```python
class HarnessAgentInboxManager:
    def __init__(self, *, caller: AgentCaller, processor: TeamProcessor) -> None: ...

    def enqueue(
        self, *,
        target_agent_id: str,
        source_agent_id: str,
        source_thread_id: str | None,
        message: str,
        user_id: str | int,
        original_user_prompt: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str: ...                       # 返回 inbox id，立即返回

    def get(self, inbox_id: str) -> InboxMessage | None: ...
    def list(self, *, target=None, source=None, status=None) -> list[InboxMessage]: ...
    def cancel(self, inbox_id: str) -> bool: ...

    def start(self) -> None: ...
    async def shutdown(self) -> None: ...
```

- `AgentCaller` 是一个最小协议（`HarnessAgentManager` 实现）：
  `async def call(self, agent_id: str, request: ChatRequest) -> dict[str, Any]`。
- 内部：`dict[id -> InboxMessage]` 做状态查询 + 投递队列。
- **并发模型**：单 worker 串行消费；同一 `target` 自然串行。
  （可选增强：按 `target` 分队列并行，跨 target 并发——V2，不在本期。）

### 4.1 worker 处理流程

```text
取出 InboxMessage(status=queued)
  status=running
  result = await caller.call(target_agent_id, ChatRequest(message, thread=新 thread))
  result_text = extract_call_response(result)            # 局部变量

  status=replying
  prompt = processor.compose_followup(msg, result_text)
  reply  = await caller.call(source_agent_id, ChatRequest(prompt, thread=source_thread_id))
  reply_text = extract_call_response(reply)               # 局部变量

  status=done
  await processor.on_reply(ReplyEvent(... reply_text=reply_text ...))
异常 → status=failed, on_reply(status=failed, error_text=...)   # 让 source agent 兜底说明
```

并发：**全局单 worker 串行**消费（不按 target 分队列）。

要点：
- 第二步 `call` 落在 `source_thread_id` 上，langgraph checkpointer 自动把这轮并进父对话，
  天然「结合之前的问题一并处理」。
- `on_reply` 只负责**投递已生成文本**（不再触发 agent），宿主侧实现极薄。

---

## 5. `HarnessAgentManager` 改动

### 5.1 构造与开关

```python
HarnessAgentManager(
    providers=...,
    langfuse=...,
    team_processor: TeamProcessor | None = None,   # 提供即启用 team/inbox
)
```

- `team_processor is None` → 不创建 inbox；`stream`/`call` 直连。
- `team_processor` 非空 → 创建 `HarnessAgentInboxManager(caller=self, processor=...)`。
- 属性 `team_enabled: bool`；`set_team_processor(...)` 支持启动后注入（Octop 装配顺序需要）。

### 5.2 `stream` / `call`：回到原始实现

撤销 mailbox 包裹，恢复重构前直连 `entry.agent.stream/call` + `_cancel_events`。
**对外签名、行为不变。**

### 5.3 互调 API（供工具/宿主调用）

```python
async def call_peer(self, *, from_agent_id, to_agent_id, message, user_id, source="ask_agent") -> PeerResult
    # 同步：直接 self.call(to_agent_id, ...)，返回 response

def submit_peer(self, *, from_agent_id, to_agent_id, message, user_id,
                source_thread_id, original_user_prompt=None, metadata=None) -> str
    # 异步：要求 team_enabled，否则报错；inbox.enqueue(...) 返回 id

async def apply_mentions(self, *, from_agent_id, user_id, mention_agent_ids, prompt, messages) -> list
    # 用户 @：对每个目标并行 call_peer(sync)，注入 system 消息（与现状一致）
```

### 5.3 team 工具

```python
def team_tools(self) -> list[StructuredTool]:
    return build_team_tools(self)        # agent_list + ask_agent
```

- 仅当调用方（Octop）显式取用时加入 agent 工具；**不写进 HarnessAgent 默认工具**。

---

## 6. team 工具（`teams/tools.py`）

### `ask_agent` 行为

| 条件 | 行为 |
|------|------|
| 默认 / `team_enabled=False` | **同步阻塞** `call_peer` → 返回 `response` |
| `team_enabled=True` 且模型选 `mode=background` | `submit_peer` → 入 inbox，返回 `{job_id, status:"queued"}`，提示稍后主动回复 |

- `mode` 字段仅在 `team_enabled` 时有效；未启用时忽略，强制 sync。
- 上下文（`from_agent_id`、`user`、`session_key`/`thread_id`）从 `langgraph.config.get_config().configurable` 读取，与现状一致。
- `submit_peer` 的 `source_agent_id = from_agent_id`、`source_thread_id = 当前 thread_id`。

---

## 7. Octop 适配

### 7.1 实现 `TeamProcessor`

`infra/gateway/processor.py` — `GlobalProcessor` 实现 `TeamProcessor`（`compose_followup` / `on_reply`）

```python
class DelegationProcessor(TeamProcessor):
    def compose_followup(self, msg, result_text) -> str:
        return build_completion_prompt(...)            # 复用 synthesis.py

    async def on_reply(self, event: ReplyEvent) -> None:
        # source.call 已把回复写进 source_thread 的 checkpoint；
        # 这里只需通知用户界面有新消息：
        #   - Dashboard：标记 unread + WS 推一条 “新回复” 通知
        #   - IM：Gateway.push_text(channel, reply_text)
```

- 不再需要 `Gateway.push_text_from_session` 重跑父 agent（合成已在 inbox 内的 `source.call` 完成）。
- 可选保留 `agent_delegations` 表：在 `on_reply` / `enqueue` 时记状态，支撑 `/delegations` 列表与
  cancel；执行本身不依赖 DB。

### 7.2 装配

```python
delegation_processor = DelegationProcessor(gateway=..., thread_registry=...)
harness = HarnessAgentManager(providers=..., team_processor=delegation_processor)
# 或 boot 后：harness.set_team_processor(delegation_processor)
```

### 7.3 工具注册

`AgentManager._build_harness_config`：`merged_tools.extend(self._harness_manager.team_tools())`
（仅 Octop 使用 manager，符合「使用 manager 时才启用」）。

### 7.4 入口不变

`chat.py` SSE、`ws_chat.py` + `processor.iter_turn_chunks`、IM → 全部不改协议；
`@` 仍走 `apply_mentions`（同步）。外部 HTTP/WS/SDK 调用方无感。

---

## 8. 端到端：后台调研场景

```text
用户问主 Agent（thread T）→ 主 Agent 调 ask_agent(mode=background, Researcher)
  → manager.submit_peer(target=Researcher, source=主Agent, source_thread_id=T)
  → inbox.enqueue → 返回 id，工具立即回「后台进行中」
主 Agent 继续与用户对话（thread T，直连 call/stream，不受 inbox 影响）

inbox worker：
  Researcher.call(任务)            → result_text
  compose_followup(原问题, result) → prompt
  主Agent.call(thread=T, prompt)   → reply_text（已并入 T 的上下文）
  processor.on_reply(reply_text)   → Dashboard/IM 主动推送给用户
```

---

## 9. 与现有实现的差异（重构清单）

### octop-harness

| 文件 | 操作 |
|------|------|
| `mailbox.py` | **删除** |
| `peer.py` | **拆分** → `teams/util.py`（helpers）+ `teams/inbox.py`（数据/管理器） |
| `manager.py` | `stream`/`call` 还原直连；新增 `team_processor`、`team_enabled`、`team_tools`、`call_peer`/`submit_peer`；`apply_mentions` 用 `call_peer` |
| `builtin/tools/peer_agent.py` | **移动** → `teams/tools.py`（`build_team_tools`） |
| `teams/inbox.py`、`teams/processor.py`、`teams/tools.py`、`teams/util.py` | **新增** |
| `tests/test_mailbox.py` | 替换为 `tests/test_inbox.py` |
| `tests/test_peer_agent.py` | 调整为 `teams` 导入 |

### octop

| 文件 | 操作 |
|------|------|
| `infra/gateway/processor.py` | `GlobalProcessor` 实现 `TeamProcessor`；`on_reply` 投递未读/IM |
| `infra/agents/manager.py` | 构造 `team_processor=...`；`team_tools()` 注册；`apply_mention_agent_calls` 透传 |
| `infra/agents/agent_call.py` | 重导出从 `octop_harness.teams.util` |
| `api/routers/chat.py`、`infra/gateway/processor.py` | 导入路径调整，逻辑不变 |
| 相关单测 | 跟随导入调整 |

---

## 10. 实施阶段

1. **teams 骨架**：`teams/util.py` + `teams/inbox.py`（`InboxMessage`、`HarnessAgentInboxManager`）+ `teams/processor.py`（协议 + 默认 compose）。
2. **manager 接线**：`stream`/`call` 还原；`team_processor` 开关；`call_peer`/`submit_peer`/`apply_mentions`/`team_tools`。
3. **teams/tools.py**：`agent_list` + `ask_agent`（sync 默认，team 时支持 background）。
4. **harness 测试**：`test_inbox.py`（enqueue→target.call→source.call→on_reply）、`test_team_tools.py`。
5. **Octop 接线**：`DelegationProcessor`、装配、工具注册、删旧路径；回归 `uv run pytest -m "not live"`。

---

## 11. 决策（已确认）

1. **inbox 并发**：全局**单 worker 串行**。不按 target 分队列。
2. **持久化**：**纯内存**，不入库；历史靠 langgraph checkpoint。
3. **`on_reply` 投递**：**整段推送**（`call` 不产 token），不走流式。
4. **`compose_followup` 归属**：放 `TeamProcessor`，**宿主可定制**（teams 提供默认实现）。
5. **失败语义**：target 失败时**仍 `on_reply(status=failed)`**，让 source agent 给用户兜底说明。
6. **`InboxMessage` 字段**：不保存 `result_text` / `reply_text`（worker 局部变量），消息仅保留路由/状态信息。
