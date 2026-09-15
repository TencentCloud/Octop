---
created: 2026-08-12
updated: 2026-08-12
---

# 聊天欢迎区展示专家自定义描述

## 需求卡片

**一句话目标**：空聊天欢迎区里，`@专家名` 后面展示该专家在设置里填写的「描述」；描述为空时回退到现有模板欢迎语。
**核心用户**：在 Dashboard「专家」页创建/编辑 Agent 的用户，进入「聊天」空会话时期望看到与设置一致的人设文案。
**做什么**：
- 欢迎区副文案优先使用 Agent 的 `description`（与表单「描述」字段一致）
- `description` 为空 / 未设置时，继续用现有 `welcome_message`（manifest / 模板欢迎语）兜底
- 展示形式保持现状：`@名称` + 描述，同一行，允许自然换行、完整展示
**不做什么**：
- 本轮不新增「标题 / 口号」字段（#188 截图中的标题字段延后）
- 不改大标题「嗨！你专属的智能伙伴来啦～」
- 不改快速开始卡片、侧边栏 Agent 卡片等其它展示位（除非实现时发现同一数据源必须顺带对齐）
**成功标准**：在「专家」里改描述并保存后，打开该 Agent 的空聊天欢迎区，`@名称` 后文案与表单「描述」一致；清空描述后恢复为模板欢迎语。

---

## 1. 背景 (Context)

[GitHub #188](https://github.com/TencentCloud/Octop/issues/188) 反馈：聊天欢迎区副文案与专家设置不一致。

现状（代码）：
- `@名称` 已正确绑定 Agent `name`
- `@` 后文案来自 `GET /agents/{id}/chat/welcome` 的 `welcome_message`（manifest / 专家模板），**不是** Agent 表单里的 `description`

用户在「从模板新建 / 编辑专家」填写的「描述」会出现在专家列表等处，但空聊天欢迎区仍显示模板短欢迎语（例如系统医生的「描述系统症状，我来帮你做健康检查」），造成「名称对了、描述不对」的割裂感。

不做则：用户改完描述后在聊天里看不到，人设配置体验不闭环；#188 持续 open。

## 2. 目标 (Goal)

**主要目标**：
- 欢迎区副文案与专家设置「描述」字段保持一致
- 空描述时行为与线上一致（模板欢迎语兜底），避免空白副文案

**成功指标（可验证）**：

| 指标 | 当前值 | 目标值 | 验证方式 |
|------|-------|-------|---------|
| 有自定义 description 时欢迎区副文案 | 显示 welcome_message | 显示 description | 改描述 → 打开 `/chat/{agentId}` 空会话肉眼核对；UT 断言 WelcomeScreen / 数据优先级 |
| description 为空时副文案 | welcome_message | 仍为 welcome_message | 清空描述后刷新空聊天；UT |
| 布局 | `@名` + 后缀同一行 | 不变；长文自然换行、不截断 | UI 抽查长描述 Agent |

## 3. 风险点

| # | 风险 | 严重度 | 缓解 / 兜底 |
|---|------|-------|------------|
| 1 | 从模板新建会预填较长 description，上线后多数 Agent 副文案由短欢迎语变为长介绍，视觉变化面大 | 🟡 中 | Clarify 已确认「有描述就展示」；完整换行可接受；Plan 阶段注意 max-width / 现有 welcomeSubtitle 样式 |
| 2 | #188 原截图含「标题/口号」字段，本轮只做描述，可能被理解为未完全关闭 Issue | 🟢 低 | 明确本轮 scope；Issue 可评论说明剩余标题字段另开 / 后续迭代 |
| 3 | description 与 welcome_message 语义不同（介绍 vs 行动号召），混用可能弱化 CTA | 🟢 低 | 产品已选一致性优先；空描述仍保留欢迎语 CTA |

## 4. 待确认问题 (Open Questions)

| # | 问题 | 结论 | 决策人 |
|---|------|------|-------|
| 1 | 本轮是否同时做「标题/口号」字段？ | 否，只做描述进聊天 | 杨广知 |
| 2 | 大标题 greeting 是否替换？ | 否，保持「嗨！你专属的智能伙伴来啦～」 | 杨广知（Discovery 默认，未要求改） |
| 3 | description 为空时副文案？ | 仍用现有模板 welcome_message 兜底 | 杨广知 |
| 4 | 有非空 description（含模板预填）是否一律覆盖 welcome_message？ | 是，客户/表单描述优先展示 | 杨广知 |
| 5 | 描述与 `@名称` 是否分行？ | 否，接在 `@名称` 后面同一行 | 杨广知 |
| 6 | 长描述是否截断？ | 否，完整展示、允许自然换行 | 杨广知 |

## 5. 关联 (References)

- TAPD / Issue：[#188](https://github.com/TencentCloud/Octop/issues/188)
- 相关界面：`dashboard/src/pages/Chat/components/WelcomeScreen.tsx`；专家表单 `CreateFromExpertDrawer` / `EditAgentDrawer` 的 `description`
- 相关 API：`GET /api/agents/{agent_id}/chat/welcome`（`welcome_message` + `quick_prompts`）；Agent 列表/详情中的 `description`
- 上游 / 下游：专家创建预填 `pickLocale(expert.description)`；聊天 `useExpertChatWelcome` + `activeAgent.name`

---

## 决策框架

1. **5W1H**：Why 设置与聊天不一致 / What 副文案用 description / Who 配专家的用户 / Where 空聊天 WelcomeScreen / When 有 description 时 / How 优先 description，空则 welcome_message
2. **INVEST**：范围小、可测、可独立交付；标题字段刻意砍掉以保持 Small
