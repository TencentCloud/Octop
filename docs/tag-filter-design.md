# Octop 标签筛选交互升级 — 技术文档

## 概述

现有侧边栏顶部有一排标签 chips（`tagFilterBar`），存在两个体验问题：

1. **放不下的标签被隐藏**：一行横排 + `overflow-x: auto` 但滚动条被 CSS 隐藏（`chatAgentCard.partial.less:384`），用户不知道右边还有标签。按拼音排序时第 5 个及以后的标签（如"学习"）实际不可见。
2. **只能单选**：`activeTag: string | null` 单值过滤，无法组合多个标签。

本次升级：**筛选按钮 + 常用快捷标签 + 弹层多选**。

- 顶部改为：【标签筛选按钮（带选中计数徽标）】+ 最多 3 个**按点击频率排序**的快捷标签
- 点击筛选按钮弹出 Popover：全量标签多选（OR 语义）、可一键清除
- 冷门标签不再靠横滑找，进弹层勾

---

## 设计决策

| 决策项 | 方案 | 理由 |
|--------|------|------|
| 快捷标签数量 | 固定最多 3 个 | 宽度自适应（ResizeObserver）代码量不值；3 个覆盖"常用"足够 |
| 快捷标签排序 | 按**点击次数**降序，次数相同按拼音（localeCompare） | 用户常点的自动浮出来；冷启动全是 0 次时退化为拼音序，与现状一致 |
| 点击次数存储 | 浏览器 localStorage，key 按 agent 隔离：`octop.tagFilterClicks.<agentId>` | 纯前端改动、零后端成本；单用户自用足够。代价：换浏览器/清缓存清零（可接受） |
| 计数时机 | **激活**标签筛选时 +1（快捷 chip 或弹层勾选都算）；取消勾选不扣减 | 频率代表"历史兴趣"，不是当前状态 |
| 多选语义 | **OR**：会话只要命中任一选中标签就显示 | AND 要求一个会话同时打多个指定标签，太严格，多数情况筛空 |
| 弹层标签来源 | 新后端端点 `GET /agents/{id}/thread-tags`（全量查询） | 现有 allTags 从"已加载会话"派生，分页只加载前 10 条，存在于未加载会话上的标签永远进不了筛选——这正是"打了标签却筛不到"的根因。后端 `ThreadRepo.list_tags` 在自动打标签时已存在，只差端点 |
| 选中但不在快捷位的标签 | 不塞进快捷行；由筛选按钮的**计数徽标**（如"标签筛选 · 2"）+ 弹层勾选态暴露 | 强塞会撑爆布局；徽标 + 弹层已能保证可发现、可清除 |
| 状态同步 | 快捷 chip 高亮 ↔ 弹层 checkbox 勾选，同源 `activeTags` 状态 | 两处只是同一状态的不同视图 |
| 旧横滑 chip 行 | **删除**，替换为新行 | 新行是它的超集（常用直达 + 全部可达） |

---

## 依赖关系图

```
Step 1 (后端 thread-tags 端点)
  │
  ├─► Step 2 (前端 API client + useSessions 全量标签)
  │
  └─► Step 3 (筛选 UI：多选状态 + 筛选按钮 + Popover + 快捷行)
        │
        └─► Step 4 (点击频率 localStorage + 快捷位排序)
```

Step 1 不完成，Step 2/3 的"全量标签"拿不到；Step 3 的快捷行先用拼音序占位，Step 4 接上频率后自动生效。

---

## 跨步骤关联标记（重要）

| 关联点 | 涉及步骤 | 说明 |
|--------|----------|------|
| 端点路径 `/agents/{id}/thread-tags` ↔ `listTags()` 客户端 | Step 1 ↔ Step 2 | 仿 `thread-folders` / `listFolders()`，路径与响应字段 `{tags: string[]}` 必须一致 |
| `activeTags` 状态 | Step 3 内部 + Step 4 | 频率记录函数接收"被激活的标签"列表，两处入口（chip、checkbox）都调它 |
| localStorage key 含 agentId | Step 4 | 切换 agent 后频率重新计算，互不污染 |
| i18n key | Step 3 | 复用现有 `chat.tags.filterByTag`（"按标签筛选"）作按钮文案；新增"清除"key 需 en/zh 同步 |

---

## Step 1：后端 —— 全量标签端点

**目标**：`GET /agents/{agent_id}/thread-tags` 返回该用户在该 agent 下所有会话的标签并集。

### 改动文件

| 文件 | 改动 |
|------|------|
| `src/octop/infra/gateway/threads.py` | `ThreadRegistry` 新增 `list_tags(*, agent_id, user_id) -> list[str]`，透传 `self._thread_repo.list_tags(...)`（方法已存在于 Repo 层） |
| `src/octop/api/routers/chat/history.py` | 新增 `GET /agents/{agent_id}/thread-tags` 路由，完全仿照 `list_thread_folders`（history.py:148）：`require_agent_row` 校验 + `effective_uid`，返回 `{"tags": tags}` |

### 新增/修改测试

| 文件 | 内容 |
|------|------|
| `tests/unit/api/test_thread_organization_api.py` | 仿现有 `thread-folders` 用例（158-164 行）：mock `thread_registry.list_tags`，断言调用参数与响应格式 |

### 验证

```bash
uv run pytest tests/unit/api/test_thread_organization_api.py -q
```

---

## Step 2：前端 —— API client + useSessions 接入全量标签

**目标**：前端能拿到全量标签列表，不再从已加载会话派生。

### 改动文件

| 文件 | 改动 |
|------|------|
| `dashboard/src/api/modules/octopThreads.ts` | 新增 `listTags: (agentId) => request<{tags: string[]}>(...)`，仿 `listFolders`（116 行） |
| `dashboard/src/pages/Chat/hooks/useSessions.ts` | 仿 `folders` 模式（327-345 行）：新增 `tags` state + `fetchTags`，agent 切换时清空重拉；`setSessionTags` 成功后顺带 `fetchTags()`，保证新标签立即进筛选 |

### 验证

```bash
cd dashboard && npx tsc --noEmit
```

---

## Step 3：前端 —— 筛选交互 UI

**目标**：单选变多选，新增筛选按钮 + Popover，顶部换成新行。

### 改动文件

| 文件 | 改动 |
|------|------|
| `dashboard/src/pages/Chat/components/SessionList.tsx` | ① `activeTag: string \| null` → `activeTags: string[]`，toggle 逻辑改为增删数组元素 ② 过滤条件改 OR：`(s.tags ?? []).some(t => activeTags.includes(t))`（461-469 行）③ fetchAllSessions 触发条件与 `showExpandMore`（520/530 行）同步改用 `activeTags.length > 0` ④ 删除旧 `tagFilterBar` 横滑行（762-775 行），替换为：筛选按钮（antd `Popover`，含全量标签 checkbox 列表 + "清除"按钮，按钮上显示选中数徽标）+ 快捷标签 chips（最多 3 个，点击 toggle，选中高亮复用 `.tagFilterChipActive`）⑤ `allTags` prop 来源切换为 Step 2 的 `tags`（保留从会话派生作为接口兜底说明见"风险"） |
| `dashboard/src/pages/Chat/chatAgentCard.partial.less` | 删除 `.tagFilterBar` 的横滑样式（378-392 行），`.tagFilterChip` 样式保留给快捷行复用；新增 `.tagFilterRow`（按钮 + chips 一行布局）、筛选按钮与徽标样式 |
| `dashboard/src/locales/zh.json` + `en.json` | `chat.tags` 下新增 `clearFilter`（清除）；按钮文案复用现有 `filterByTag` |

### 交互细节

- 弹层 checkbox 列表 = 全量标签（拼音序）；已选中的排不排序无所谓，保持原序简单
- "清除"按钮只在 `activeTags.length > 0` 时可点
- 弹层点击外部关闭，状态保留
- 会话列表标签总数为 0 时，整个筛选行不渲染（同现状 `allTags.length > 0` 判断）

### 验证

```bash
cd dashboard && npx tsc --noEmit
# 手动：浏览器开侧栏，多选筛选、清除、切换 agent 验证
```

---

## Step 4：前端 —— 点击频率 localStorage

**目标**：快捷标签按"用户最常点"排序。

### 新增文件

| 文件 | 内容 |
|------|------|
| `dashboard/src/pages/Chat/utils/tagFilterClicks.ts` | 纯函数：`readTagClicks(agentId): Record<string, number>`（读不到返回 `{}`）、`recordTagClick(agentId, tag)`（+1 后写回，条目数超 50 时裁剪到前 50）。读写包 try/catch，localStorage 不可用时静默降级为"每次空表"（即始终拼音序） |

### 改动文件

| 文件 | 改动 |
|------|------|
| `dashboard/src/pages/Chat/components/SessionList.tsx` | 激活标签时调 `recordTagClick`；快捷位计算：`allTags` 按 `(count desc, localeCompare)` 排序取前 3 |
| `dashboard/src/pages/Chat/utils/__tests__/tagFilterClicks.test.ts`（或同级测试目录，按现有 vitest 布局定） | 单测：空表读取、计数累加、多 agent 隔离、超限裁剪、异常输入不抛 |

### 验证

```bash
cd dashboard && npx vitest run src/pages/Chat/utils
```

---

## 风险与对策

| 风险 | 对策 |
|------|------|
| 全量端点拿到的标签，其会话可能不在已加载的前 50 条内，筛出来是空的 | 保持现有行为：进入筛选态时触发 `fetchAllSessions`（拉 50 条）。会话总量超 50 后筛选可能不全——已知限制，届时再后端化过滤（见"明确不做"） |
| localStorage 被清 / 换浏览器，快捷位退回拼音序 | 频率只是排序_hint_，功能不受影响 |
| 弹层 checkbox 与快捷 chip 状态不同步 | 同源 `activeTags`，两处都是它的投影；单测 + 手动验证 |
| 后端 `list_tags` 查询全表标签的性能 | 标签列有索引前提下的轻量查询；单用户量级（几百会话）无感知 |

## 明确不做（本次范围外）

- **后端按标签过滤会话**（server-side `tag` 参数过滤 + 分页）——现有"拉前 50 条前端过滤"在用户当前会话量下够用；等超过 50 条再升级
- **弹层显示每个标签的会话数**——锦上添花，需要额外统计查询
- **AND 语义多选**——OR 覆盖主要场景
- **频率跨设备同步**——localStorage 够自用
