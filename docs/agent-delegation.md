# Agent 后台协作（harness teams + Octop 投递）

> **同步互调**（`@` Agent、`ask_agent` sync）见 [agent-call-agent.md](./agent-call-agent.md)。  
> 架构说明见 [agent-interop-mailbox.md](./agent-interop-mailbox.md)。

## 行为

1. 主 Agent 调用 **`ask_agent`（`mode=background`）**，harness `TeamManager` 将任务入队并立即返回 `job_id`。
2. 主对话继续；inbox worker 串行执行：`target.call` → 合成提示 → `source.call`（落在父 `thread_id`）。
3. 完成后 **`GlobalProcessor.on_reply`**：Dashboard 仅 `increment_unread`（回复已在 checkpoint）；IM 通道则 `Gateway.push_text`。

## 工具

| `ask_agent` mode | 行为 |
|------------------|------|
| `sync`（默认） | 阻塞等待子 Agent 一次性 `call` 结果 |
| `background` | 入 harness inbox，完成后主动通知 |

可选 `user_question`：写入 inbox 消息，供 `compose_followup` 使用。

### `ask_agent` 的目标是对等 Agent，不是工作区子代理

`ask_agent` / `agent_list` 面向**对等 Agent**（同一用户下的其它 Agent，
`expert` 参数传 `agent_id`，可用 `agent_list` 先查）。两类容易混淆的对象：

| 对象 | 定义位置 | 调用方式 |
|------|----------|----------|
| 对等 Agent（expert） | `agents` 表 / Dashboard 专家 | `ask_agent(expert=<agent_id>, …)` |
| 工作区子代理 | 工作区 `.octop/agents/*.md`（含专家模板内嵌 `agents/` 目录） | `task` 工具（subagent） |

把工作区子代理名传给 `ask_agent` 会得到 `expert not found`——此时应改用
`task` 工具派发；反之，需要独立工作区/记忆的跨 Agent 协作（如专家团队）才用
`ask_agent`。

## Octop 侧保留代码

| 路径 | 职责 |
|------|------|
| `infra/gateway/processor.py` | `GlobalProcessor` 实现 `TeamProcessor`（`compose_followup` / `on_reply`） |
| `infra/agents/manager.py` | 注册 `team_tools()`、`apply_mentions` 薄封装 |

**已移除**：`agent_delegations` 表、`DelegationRepo`、`/delegate` slash（状态由 harness inbox 内存队列管理）。

## 异步场景还需做什么？

当前闭环已可用。可选增强（非阻塞）：

- 前端：用户停留在当前 thread 时，除未读角标外主动 `loadHistory`（或 SSE/WS 通知）。
- harness：inbox `cancel(job_id)` 暴露给 slash 或管理 API（若需要取消长任务）。
- 重启后 in-flight 任务丢失（inbox 纯内存）——若需持久化队列，应在 harness 层扩展，而非 octop DB 重复实现。
