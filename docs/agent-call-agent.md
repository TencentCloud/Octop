# Agent 互调（harness teams）

> 架构与 inbox 设计见 [agent-interop-mailbox.md](./agent-interop-mailbox.md)。  
> 后台协作见 [agent-delegation.md](./agent-delegation.md)。

## 原则

**`@` Agent** = 进入主 stream 前，对每个被 @ 的 Agent 做一次同步 `call_peer`，结果注入 `system` 后继续主 Agent。

**`ask_agent`** = 模型自行判断是否协作；`mode=sync` 即时返回，`mode=background` 走 harness inbox + `GlobalProcessor.on_reply` 投递。

## 用户侧：`@` Agent

1. 输入框 `@Researcher` → 请求带 `target_agent_ids`
2. `AgentManager.apply_mention_agent_calls` → `HarnessAgentManager.team.apply_mentions`
3. 各 Agent 回复注入 `system`，再 stream 当前 Agent

## Agent 侧工具（harness `teams/tools.py`）

| 工具 | 作用 |
|------|------|
| `agent_list` | 列出当前用户可协作的 Agent |
| `ask_agent` | 同步或后台协作（见 [agent-delegation.md](./agent-delegation.md)） |

在 `AgentManager._build_harness_config` 中通过 `team.team_tools()` 注入（与 cron 工具同级）。

## 执行栈

```text
用户 @ Agent
  → AgentManager.apply_mention_agent_calls
  → TeamManager.apply_mentions → call_peer (sync)

ask_agent mode=sync
  → TeamManager.call_peer

ask_agent mode=background
  → TeamManager.submit_peer → inbox worker → GlobalProcessor.on_reply
```text

## 相关文件

- `harness_agent/teams/` — inbox、`TeamManager`、`build_team_tools`
- `infra/gateway/processor.py` — `GlobalProcessor`（消息路由 + `TeamProcessor` 回调）
- `api/routers/chat.py`、`infra/gateway/processor.py` — `@` 与 slash

## 后续（可选）

- `call` 超时与审计
- 父 thread 展示「后台调研进行中」进度
