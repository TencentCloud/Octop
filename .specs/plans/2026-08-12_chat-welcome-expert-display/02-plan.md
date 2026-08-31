# 02. Plan

> **目的**：把 Clarify 的结论转化为可落地的技术方案。
> **输入**：`01-clarify.md` 的目标与范围
> **输出**：改动清单、调用链、数据模型、**UT 用例（TDD 先行）**、IT 用例
> **TDD 模式**：本阶段必须**先于 Implement** 设计完 UT 用例（§ 6）；UT/IT 边界与红绿循环约束详见 `04-ut.md` §0.5，本文件只列 UT 用例骨架，重复内容不复制。

---

## 1. 方案概述

前端最小改动：在聊天欢迎区副文案解析处增加优先级——**非空 `agent.description`（trim 后）优先于 API `welcome_message`**；二者皆空时保持现有行为（`WelcomeScreen` 再回退到 i18n `chatWelcome.descriptionWithAgentSuffix`）。

不改后端、不改 DB、不改 welcome API；`OctopAgent.description` 已由 `GET /api/agents` 提供。抽纯函数 `resolveWelcomeSuffix` 便于 TDD；在 `useExpertChatWelcome` 中组合 `agent.description` 与拉取到的 `welcome_message`，并让 effect / 返回值随 `description` 变化更新。

## 2. 改动文件清单

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `dashboard/src/pages/Chat/utils/resolveWelcomeSuffix.ts` | 新增 | 纯函数：`description` 非空 → 用之；否则 → `welcomeMessage` |
| `dashboard/src/pages/Chat/utils/resolveWelcomeSuffix.test.ts` | 新增 | §6.1 函数级 UT |
| `dashboard/src/pages/Chat/hooks/useExpertQuickCards.ts` | 修改 | 用 `resolveWelcomeSuffix(agent?.description, apiWelcome)` 作为返回的 `welcomeSuffix`；deps 含 `agent?.description` |

> 不改 `WelcomeScreen.tsx` 布局（已是 `@名` + 后缀同行 + 自然换行）；不改 `Chat/index.tsx` 传参形状（仍传 `welcomeSuffix`）。

## 3. 影响范围

| 维度 | 影响 |
|------|------|
| 接口 | 无（复用已有 agents + chat/welcome） |
| 模块 | Dashboard Chat 欢迎区副文案数据源 |
| DB schema | 无 |
| 配置 | 无 |
| 协议兼容 | 无协议变更；仅前端展示优先级 |
| 上下游服务 | 无 |

## 4. 调用链

```
Chat/index.tsx
  → useExpertChatWelcome(activeAgent)          // 修改：组合 description
       → agentChatApi.welcome(agentId)         // 不变：拿 welcome_message + quick_prompts
       → resolveWelcomeSuffix(                 // 新增
            activeAgent.description,
            localized welcome_message
          )
  → WelcomeScreen({ agentName, welcomeSuffix }) // 不变：@名 + welcomeSuffix 同行
```

原链路差异：原先 `welcomeSuffix` = 仅 `welcome_message`；现为 `description ?? welcome_message`（空串 / 纯空白视为空）。

## 5. 数据结构变更

### 5.1 内部 DataType / Schema

| 类型 | 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| （无新类型） | — | — | — | `resolveWelcomeSuffix(description: string \| null \| undefined, welcomeMessage: string \| null \| undefined): string \| null` |

### 5.2 DB 表结构

| 表 | 变更 | 索引影响 | 回滚方式 |
|----|------|---------|---------|
| — | 无 | — | — |

### 5.3 协议 / 接口契约

| 接口 | 新增字段 | 必填 | 兼容性 |
|------|---------|------|-------|
| — | 无 | — | 旧后端无需升级 |

## 6. UT 用例设计（TDD 必填，先于 Implement）

### 6.1 函数级 UT 用例

| # | 被测对象（函数 / 类 / 模块路径） | 测试文件（计划） | 类型 | 输入 | 期望输出 / 行为 | Mock 边界 |
|---|----------------------------------|------------------|------|------|----------------|-----------|
| 1 | `resolveWelcomeSuffix` | `dashboard/src/pages/Chat/utils/resolveWelcomeSuffix.test.ts` | 正向 | `description="系统描述"`, `welcomeMessage="模板欢迎语"` | `"系统描述"` | 无（纯函数） |
| 2 | 同上 | 同上 | 边界 | `description=""`, `welcomeMessage="模板欢迎语"` | `"模板欢迎语"` | 无 |
| 3 | 同上 | 同上 | 边界 | `description="   "`, `welcomeMessage="模板欢迎语"` | `"模板欢迎语"`（空白视为空） | 无 |
| 4 | 同上 | 同上 | 边界 | `description=null`, `welcomeMessage="模板欢迎语"` | `"模板欢迎语"` | 无 |
| 5 | 同上 | 同上 | 边界 | `description=null`, `welcomeMessage=null` | `null`（交由 WelcomeScreen i18n 兜底） | 无 |
| 6 | 同上 | 同上 | 正向 | `description="  有空格  "`, `welcomeMessage="x"` | `"有空格"`（trim 后返回） | 无 |
| 7 | 同上 | 同上 | 逆向 | `description=undefined`, `welcomeMessage=undefined` | `null` | 无 |

> 幂等 / 外部异常：纯函数无副作用、无外部依赖，不适用。

### 6.2 场景 UT 用例（可选）

| # | 业务场景 | 入口 | 测试文件 | 类型 | 关键断言 | Mock 边界 |
|---|---------|------|----------|------|---------|-----------|
| — | 不强制 | — | — | — | 手工 / 后续可加 hook 测试 | — |

> CI 可跑 vitest 覆盖纯函数；WelcomeScreen 展示用手工 IT / 本地打开 `/chat` 验证即可。

## 7. IT 用例设计

| # | 场景 | 类型 | 前置条件 | 执行步骤 | 预期结果 |
|---|------|------|---------|---------|---------|
| 1 | 自定义描述展示 | 正向 | Agent 描述为「系统描述」 | 打开该 Agent 空聊天 | `@名称` 后为「系统描述」 |
| 2 | 空描述回退 | 边界 | 清空并保存描述 | 刷新空聊天 | `@名称` 后为模板 welcome_message |
| 3 | 长描述换行 | 正向（典型） | 描述为模板预填长文 | 打开空聊天 | 完整展示、自然换行、无省略号截断 |
| 4 | 无 Agent / 未选中 | 边界 | 无 activeAgent | 看欢迎区 | 走无 agentName 分支（既有 i18n description），不崩 |
| 5 | 改描述后刷新 | 正向 | 编辑专家改描述并保存，AgentContext refresh | 回到空聊天 | 副文案更新为新描述（若 refresh 后 description 已变） |

> 无写操作 API、无外部依赖故障路径；逆向「非法输入」不适用（前端展示字段）。不强制自动化 IT；本地 `octop run` + Dashboard 冒烟即可。

## 8. 风险与兜底

| 风险 | 触发条件 | 影响 | 缓解 | 回滚方案 |
|------|---------|------|------|---------|
| 上线后多数 Agent 副文案变长 | 模板预填 description | 欢迎区文案变「介绍向」 | Clarify 已接受；现有 `.welcomeSubtitle` max-width + 换行 | 回退 commit / 恢复仅用 welcome_message |
| 改描述后 UI 未更新 | AgentContext 未 refresh | 仍显示旧描述 | 依赖现有编辑保存后的 `refresh()`；effect deps 含 `description` | — |
| 误伤无 description 的旧 Agent | description 恒 null | 行为与线上一致 | 空则 welcome_message | — |

## 9. 工时估算

| 阶段 | 工时 | 备注 |
|------|------|------|
| Implement | 0.5–1h | 含 TDD 红绿 |
| UT | 含上 | 纯函数 UT |
| Deploy + IT | 0.5h | 本地冒烟 |
| Docs + Review | 0.5h | 可选简短 docs |
| **预估代码改动行数** | **~25** | **不含测试 / 文档；>10 → 小需求模式 ⬜** |

---

## 决策框架

1. **先画图**：见 §4 调用链。
2. **找相似**：复用 `Chat/utils/*` + colocated `*.test.ts` 模式（如 `threadTitle.ts`）。
3. **最小改动**：只改副文案优先级；不动 API / DB / WelcomeScreen 结构。
4. **边界优先**：空串、空白、null、双空均有 UT。

## 完成标志

- [x] 改动文件清单完整，每文件有说明
- [x] 调用链清晰
- [x] 数据结构变更含回滚方式（无 DB）
- [x] 函数级 UT 用例已设计（§6.1）
- [x] 场景 UT 已评估（不强制）
- [x] IT 用例覆盖正向 / 边界
- [x] 风险表有缓解与回滚
- [x] `00-overview.md` Progress / 当前步骤 / 时间记录已同步
- [x] 已与用户完成结束确认