# [2026-08-12] 聊天欢迎区展示专家自定义描述

> **本文件是本任务的单一真相源（Single Source of Truth）**：任务元信息、进度、当前步骤、关键决策全部在这里。
> 会话恢复时，先读本文件定位当前步骤，再按需加载对应阶段文件。
>
> ⚠️ 本项目**不维护**全局 `.specs/plan.md`——跨任务查看请列 `.specs/plans/` 目录。
> ⚠️ Meta 中的 `分支` 字段是上下文恢复时定位任务的唯一依据，**必须**与 `git branch --show-current` 的输出完全一致。

---

## Meta

| 项 | 值 |
|----|----|
| 分支 | `feature/chat-welcome-expert-display` |
| Issue / TAPD | `#188`（GitHub；无 TAPD） |
| 摘要 | 空聊天欢迎区 `@名称` 后优先展示 Agent 自定义 description；为空则回退 welcome_message |
| 状态 | ✅ 已完成 |
| 创建日期 | 2026-08-12 |
| 负责人 | 杨广知 |
| 预期完成 | 2026-08-12 |
| 开发模式 | 独立开发 |
| 测试环境 |  |
| 预估代码改动行数 | ~25（不含测试 / 文档） |
| 小需求模式 | ⬜ 否 |
| 模型 | Cursor Grok 4.5 |

---

## Progress

<!-- 本文件结构 / 字段定义 / Progress / 时间记录 SOP 规则见
     .specs/plans/_template/00-overview.md；本任务文件精简不重复。
     规则变更只改 _template/，本任务文件由 init_specs.sh 后续刷新
     不影响旧任务。 -->

- [x] 01. Clarify    → [01-clarify.md](./01-clarify.md) (描述进聊天；空则 welcome_message 兜底)
- [x] 02. Plan       → [02-plan.md](./02-plan.md) (前端 resolveWelcomeSuffix；~25 LOC)
- [x] 03. Implement  → [03-implement.md](./03-implement.md) (纯函数 + hook 接线；Node smoke 7/7)
- [x] 04. UT         → [04-ut.md](./04-ut.md) (Plan §6.1 7/7 PASS)
- [x] 05. Docs       → [05-docs.md](./05-docs.md) (无对外文档变更)
- [x] 06. Review     → [06-review.md](./06-review.md) (去掉多余 useMemo；批准合入)
- [x] 07. Commit     → [07-commit.md](./07-commit.md) (fix(dashboard): prefer agent description…)

---

## 当前步骤

> 恢复会话时，优先读取此处指向的阶段文件。

- **步骤**：✅ 07. Commit（边界点 A 已锁定）
- **文件**：[07-commit.md](./07-commit.md)
- **上次更新**：2026-08-12 20:23:07

---

## 时间记录

<!-- 本文件结构 / 字段定义 / Progress / 时间记录 SOP 规则见
     .specs/plans/_template/00-overview.md；本任务文件精简不重复。
     规则变更只改 _template/，本任务文件由 init_specs.sh 后续刷新
     不影响旧任务。 -->

| # | 步骤 | 开始时间 | 结束时间 | 耗时 | 对话轮次 | 备注 |
|---|------|---------|---------|------|---------|------|
| 01 | Clarify    | 2026-08-12 15:10:26 | 2026-08-12 19:51:57 | 4h41m31s | 8 | Discovery + Challenge |
| 02 | Plan       | 2026-08-12 19:53:36 | 2026-08-12 19:54:35 | 59s | 1 |  |
| 03 | Implement  | 2026-08-12 19:57:13 | 2026-08-12 20:03:47 | 6m34s | 1 | vitest 因本环境 npm 失败未跑；Node smoke 7/7 |
| 04 | UT         | 2026-08-12 20:04:29 | 2026-08-12 20:07:55 | 3m26s | 1 | vitest 本环境未跑；Node strip-types 导入源码 7/7 |
| 05 | Docs       | 2026-08-12 20:11:21 | 2026-08-12 20:11:38 | 17s | 1 | 清单全不涉及 |
| 06 | Review     | 2026-08-12 20:20:52 | 2026-08-12 20:21:25 | 33s | 1 | 去掉多余 useMemo |
| 07 | Commit     | 2026-08-12 20:22:25 | 2026-08-12 20:23:07 | 42s | 2 | TAPD 路径 C 跳过 |

---

## 关键决策备忘

> **跨阶段共享的关键上下文**。仅记录影响后续步骤的决策，避免恢复时还要翻阅历史阶段文件。

- 来源：[GitHub #188](https://github.com/TencentCloud/Octop/issues/188)
- **本轮 scope**：只做「描述进聊天欢迎区」；不新增标题/口号字段；不改 greeting 大标题
- **展示优先级**：非空 `agent.description` > `welcome_message`（manifest / 模板）；空 description → `welcome_message`
- **布局**：`@名称` + 描述同一行；完整展示、允许自然换行、不截断
- **数据注意**：从模板新建会预填 description（`CreateFromExpertDrawer`），上线后多数 Agent 副文案会从短欢迎语变为表单描述
- **实现方案**：新增纯函数 `resolveWelcomeSuffix`；在 `useExpertChatWelcome` 组合；无后端 / DB 变更
- **TAPD**：路径 C 跳过——非 CVM 流程，仅跟踪 GitHub #188
- **Commit**: `fix(dashboard): prefer agent description on chat welcome`

---

## 风险速览

| # | 风险 | 严重度 | 缓解 |
|---|------|-------|------|
| 1 | 预填长 description 导致欢迎区文案整体变长 | 🟡 中 | 产品接受；靠现有 subtitle 样式自然换行 |
| 2 | #188 标题字段未做，Issue 可能不完全关闭 | 🟢 低 | 评论说明本轮只修描述一致性 |

---

## 文件索引

| 文件 | 产物 |
|------|------|
| [00-overview.md](./00-overview.md) | 任务总览（本文件） |
| [01-clarify.md](./01-clarify.md) | 需求澄清：背景、目标、范围、待确认问题 |
| [02-plan.md](./02-plan.md) | 方案设计：改动文件、调用链、数据模型、IT 用例 |
| [03-implement.md](./03-implement.md) | 实现：关键细节、与 Plan 差异、检查结果 |
| [04-ut.md](./04-ut.md) | 单元测试：用例、覆盖率、未覆盖行 |
| [05-docs.md](./05-docs.md) | 文档更新清单 |
| [06-review.md](./06-review.md) | Code Review：问题与修复 |
| [07-commit.md](./07-commit.md) | Commit message 与 amend 流程 |
