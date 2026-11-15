## feat(hitl): complete structured_form lifecycle — timeout, idempotency, cancellation

为 `request_structured_form` HITL 工具补全生命周期管理，使结构化表单从『发出即永久挂起』变为具备**超时自动失效**、**提交幂等**和**用户主动取消**三项生产级能力。

---

## 变更文件

| 文件 | 变更 |
|---|---|
| `src/octop/infra/gateway/hitl/structured_form.py` | `allowed` set 增加 `timeout_seconds`；`validate_structured_form_request` 增加整型 30–3600 范围校验 |
| `src/octop/infra/gateway/hitl/coordinator.py` | 超时检查、提交幂等检查、cancel 已消费防护、`cancel_structured_form` 公开方法、`form_context` 注入 |
| `src/octop/infra/gateway/hitl/store.py` | `HitlPendingRecord` 新增 `form_context` / `consumed_submission_ids` 字段；`mark_form_consumed` 幂等方法；`cancel_pending_by_form_id` 批量取消方法 |
| `src/octop_harness/builtin/tools/structured_form.py` | `StructuredFormRequestArgs` 新增 `timeout_seconds: int \| None` 可选字段（ge=30, le=3600） |
| `src/octop_harness/agent.py` | `request_structured_form` 的 `allowed_decisions` 从 `["respond"]` 扩展为 `["respond", "cancel"]` |

## 新增功能

### 1. 超时自动失效（Timeout）
- **参数**: `timeout_seconds`（int，30–3600 秒，可选）
- **行为**: Agent 发出表单后开始计时，超时后任何决策（respond/cancel）均返回 `"structured form has expired"`
- **缺省行为**: 不传 `timeout_seconds` 时无超时限制（向后兼容）

### 2. 提交幂等（Idempotency）
- **机制**: `HitlPendingRecord.consumed_submission_ids: set[str]`
- **行为**: 重复 `submission_id` 被拒绝，返回 `"structured form submission has already been consumed"`
- **存储**: `store.mark_form_consumed()` 原子记录，随 record TTL 自动清理

### 3. 用户主动取消（Cancellation）
- **入口**: `HitlChannelCoordinator.cancel_structured_form(form_id, agent_id, user_id)`
- **行为**: 按 `form_id` 批量过期所有匹配的 pending 记录
- **防护**: 已消费表单（`consumed_submission_ids` 非空）不允许取消

## 测试报告

### gateway/structured_form.py — timeout_seconds 参数校验（10/10）

| # | 用例 | 预期 | 结果 |
|---|---|---|---|
| 1 | 缺 timeout_seconds | None（合法） | PASS |
| 2 | timeout_seconds=30（下边界） | None（合法） | PASS |
| 3 | timeout_seconds=3600（上边界） | None（合法） | PASS |
| 4 | timeout_seconds=29（低于最小值） | 错误信息 | PASS |
| 5 | timeout_seconds=3601（高于最大值） | 错误信息 | PASS |
| 6 | timeout_seconds="abc"（字符串） | 错误信息 | PASS |
| 7 | timeout_seconds=True（布尔） | 错误信息 | PASS |
| 8 | timeout_seconds=0 | 错误信息 | PASS |
| 9 | timeout_seconds=300（中间值） | None（合法） | PASS |
| 10 | timeout_seconds=None（等同缺省） | None（合法） | PASS |

### gateway/coordinator.py — 决策核心逻辑（9/9）

| # | 用例 | 预期 | 结果 |
|---|---|---|---|
| 1 | 合法 respond 决策 | None | PASS |
| 2 | 超时已过期的 respond | `"structured form has expired"` | PASS |
| 3 | 超时未过期的 respond | None | PASS |
| 4 | 重复 submission_id（幂等拒绝） | `"...already been consumed"` | PASS |
| 5 | 不同 submission_id（幂等通过） | None | PASS |
| 6 | cancel 允许（未消费） | None | PASS |
| 7 | cancel 拒绝（已消费） | `"...cannot be cancelled"` | PASS |
| 8 | cancel 不在 allowed_decisions 中 | `"decision 'cancel' is not allowed..."` | PASS |
| 9 | cancel 时超时已过期 | `"structured form has expired"` | PASS |

### gateway/store.py — 幂等记录与批量取消（10/10）

| # | 用例 | 预期 | 结果 |
|---|---|---|---|
| A1 | 首次消费 sub-001 | True + 入集合 | PASS |
| A2 | 重复消费 sub-001 | False | PASS |
| A3 | 消费新 sub-002 | True | PASS |
| A4 | 不存在的 pending_id | False | PASS |
| B1 | 按 form_id 批量取消 | True | PASS |
| B2 | 3 条目标记录均已过期 | 全部 expired | PASS |
| B3 | 不相关记录未被影响 | 仍 pending | PASS |
| B4 | 二次取消已过期表单 | False | PASS |

## 应用场景

### 场景 A — 审批工作流
> Agent 发出『确认部署到生产』表单，`timeout_seconds=600`。10 分钟内用户提交 → 幂等通过 → Agent 执行。重复点击 → 幂等拦截。用户点取消 → 表单过期。10 分钟后超时 → 任何操作被拒。

### 场景 B — 数据收集
> Agent 发出『填写服务器配置』表单，用户中途放弃。超时机制确保 Agent 不无限挂起占用资源。

### 场景 C — 多步骤工作流取消
> 单个 `form_id` 关联多个步骤。`cancel_pending_by_form_id` 批量清理所有 pending 记录，避免孤立挂起。

## 向后兼容性

> **向后兼容性** = 新代码不会搞崩老用法（功能层面）。我们只做了『加法』，没有修改任何现有字段的语义或默认值。

| 新增项 | 旧代码行为 | 安装新版后行为 | 是否破坏兼容 |
|---|---|---|---|
| `timeout_seconds` 参数 | 不传该字段 | 不传 = 无超时，与旧版完全一致 | ❌ |
| `consumed_submission_ids` | 不传 `submission_id` | `getattr(record, "consumed_submission_ids", set())` 兜底为空集合 | ❌ |
| `cancel` 决策类型 | `allowed_decisions` 只有 `["respond"]` | cancel 不在白名单里，旧 Agent 根本发不出 cancel 决策 | ❌ |
| `form_context` 字段 | 序列化时不包含 | 键不存在 → 旧 record 反序列化后 `form_context=None`，不影响逻辑 | ❌ |

**结论：无破坏性变更。** 无论是生产环境 v1.0.2 还是上游 v1.0.3b5，安装新版后所有旧调用路径不受影响。

## 上游冲突分析

> **上游冲突** = Git 代码合并时两个分支改了同一个文件的同一区域（Git 层面）。与功能兼容性无关。

```
TencentCloud/Octop main (v1.0.3b5)
         │
         ├── 我们基于它创建 feat/interaction-lifecycle
         │                              │
         │                         改 6 个文件
         │
         └──（上游在我们 fork 之后没有对这 6 个文件做任何提交）
```

- `git merge-base`（最近共同祖先）= `cd17e8d3` = `v1.0.3b5` 本身
- 上游在我们改的 6 个文件上**没有额外提交**
- 可以直接 `git rebase upstream/main` 或提交 PR，**不会产生任何代码冲突**

## Store 持久化：现状与演进

### 当前风险

`HitlPendingStore` 采用进程内 `dict[str, HitlPendingRecord]` 存储，存在三类问题：

| 风险 | 触发条件 | 后果 |
|---|---|---|
| **进程重启丢失** | 部署、OOM、崩溃 | 所有 pending 记录消失、`consumed_submission_ids` 清空 → **幂等性被打破**、Agent 图永久挂起 |
| **多实例不共享** | 水平扩展 | 多个 Gateway 实例各自维护独立 pending 集合，路由到不同实例会丢记录 |
| **无事务保证** | 并发读写 | `_gc()` 全量扫描 + `mark_form_consumed` 非原子，存在竞态窗口（当前单线程串行处理风险可控） |

### 分层关系

```
┌─────────────────────────────────────┐
│ LangGraph Checkpoint (PG/SQLite)    │ ← 已持久化
│  Agent 图状态、快照、恢复点          │
├─────────────────────────────────────┤
│ HitlPendingStore (进程内存) ⚠️       │ ← 未持久化，问题所在
│  pending 记录、form_context、        │
│  consumed_submission_ids、TTL        │
└─────────────────────────────────────┘
```

Agent 图本身通过 langgraph checkpoint 持久化了，但 HITL 协调层的 pending 元数据是『孤岛』。重启后 Agent 图仍在等待响应，但协调层已『失忆』。

### 演进路线

| 阶段 | 方案 | 说明 |
|---|---|---|
| **当前 PR** | 进程内存（现状） | 功能已完整，单机部署可工作，文档中标明风险 |
| **下一步** | `HitlPendingPostgresStore` | 基于 gateway 层已有的 `langgraph-checkpoint-postgres` 依赖，一步到位解决持久化 + 多实例 + 事务问题 |
| **不建议** | SQLite 后端 | Gateway 层已有 PG 依赖且 HITL pending 是全局热数据，SQLite 的并发瓶颈与单机限制不适合此场景 |

## 限制与后续
- `store.py` 为进程内存存储，重启后 pending 记录丢失（详见上方『Store 持久化』章节）
- 建议下个 PR 基于 `langgraph-checkpoint-postgres` 实现 `HitlPendingPostgresStore`
- 本次未包含端到端集成测试（需完整 Octop 运行时 + LLM 后端）
