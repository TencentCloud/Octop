# Octop 自动打标签功能 — 技术文档

## 概述

在对话分组/标签功能（见 `thread-organization-design.md`）之上，增加**自动打标签**：新对话的第一轮对话完成后，自动分析聊天主题，给会话打上合适的标签，免去用户手动输入。

设计前提：现有"自动起标题"不是 LLM 做的（`gateway.py` 里把首条用户消息截断当标题），所以打标签需要**新发起一次独立的 LLM 调用**。

**本次明确不做自动文件夹**——文件夹是单选归属（一个会话只能属于一个），LLM 归错类用户要手动挪回去，出错成本高；标签是多选、可叠加，归错了一个标签影响小，适合先自动化。

---

## 设计决策

| 决策项 | 方案 | 理由 |
|--------|------|------|
| 触发时机 | 一轮对话**成功完成**时；只对会话的**首个完成回合**触发（每个会话最多自动打一次）。判定信号：在 `touch_last_active` 之前读 `row.last_active == 0`（建线程时的哨兵值） | 此时消息内容完整；**不能用"标题从无到有"判定**——dashboard 发消息时会乐观 PATCH 标题（`useChatSend.ts` 的 `renameSession`），轮到钩子执行时标题必已存在，`last_active` 对"谁写标题"免疫 |
| 调用方式 | 异步 fire-and-forget（`asyncio.create_task`），不阻塞用户看到回复 | 打标签是锦上添花，绝不能拖慢消息流 |
| 写入策略 | **只有当会话现有标签为空时才写入**；用户手动改过标签就不再覆盖 | 自动是起点不是裁判，用户手动标签永远优先 |
| 词汇控制 | LLM 从**该用户已有的标签**里优先选；实在没有合适的才允许造 1 个新词；每会话最多 3 个标签 | 不加控制标签会爆炸式增多（每会话造几个新词，几周后几百个标签就没法用了） |
| 标签来源 | 把"首条用户消息 + 自动生成的标题"作为分析素材 | 最贴主题；标题已经是一份压缩好的摘要，一并给 LLM 更准 |
| 模型选择 | 按聊天同一套兜底链解析：全局默认模型 → 会话 `model_ref` → 网关注入的兜底回调（agent manager 的"第一个可用模型"），都用 `probe.py` 的 `build_probe_chat_model` 发一次轻量调用 | 打标签是轻任务，不该要求用户先配全局默认模型；聊天能跑通的地方打标也应该能跑通（2026-09-13 实测：用户未设全局默认模型导致静默跳过，已修） |
| 失败策略 | try/except 吞掉，记日志，**绝不让打标签失败影响消息发送** | 标签丢了用户无感，消息发不出去用户有感 |
| 功能开关 | Agent 的 `config_json` 保存布尔键 `auto_thread_tags`；缺失或非布尔值一律按 `false`，每个 Agent 默认关闭 | 自动打标会额外消耗 token；只有用户主动为当前 Agent 开启时才允许发起标签 LLM 调用，且不同 Agent 互不影响 |
| 多用户 | 每个用户打自己的标签，词汇表也是按 agent + user 隔离 | 跟手动标签的隔离规则一致 |

---

## 依赖关系图

```
Step 1 (Repo层 list_tags)
  │
  ├─► Step 2 (自动打标服务 AutoTagger) ─► Step 3 (Processor 挂钩)
  │                                      │
  └──────────────────────────────────────┴─► Step 4 (Agent 级开关 + 编辑专家抽屉)
```

Step 1 至 Step 3 已完成；本次只改造 Step 4，并回调 Step 2 的开关判定。每步都可独立跑测试验证。

---

## 跨步骤关联标记（重要）

| 关联点 | 涉及步骤 | 说明 |
|--------|----------|------|
| `list_tags` 返回类型 | Step 1 ↔ Step 2 | 返回 `list[str]`（去重、去空白），AutoTagger 把它塞进 prompt |
| `config_json.auto_thread_tags` | Step 2 ↔ Step 4 | 后端开关接口和 AutoTagger 读取的是同一个 Agent 级布尔键；键不存在时统一视为关闭 |
| `set_tags` 的"仅空才写"判断 | Step 2 ↔ Step 3 | 判断逻辑放在 AutoTagger 内部，Processor 只管调，不重复判断 |
| 标签清洗 | Step 1 ↔ Step 2 | AutoTagger 产出标签后必须用现有的 `parse_thread_tags` 清洗再存，跟手动标签的存储格式完全一致 |

---

## Step 1：Repo 层 —— 查出某用户已有的所有标签

**目标**：加一个 `list_tags(agent_id, user_id)` 方法，把该用户所有会话的标签收集、解析、去重后返回。AutoTagger 要靠它来控制"不滥造新词"。

### 改动文件

| 文件 | 改动 |
|------|------|
| `src/octop/infra/db/repos/threads.py` | 新增 `list_tags` 方法：查出非空 tags 的行，用现有 `parse_thread_tags` 逐个解析，Python 里去重、排序后返回 |

### 新增文件

| 文件 | 内容 |
|------|------|
| `tests/unit/db/test_auto_thread_tags.py` | 测试 `list_tags`：空库返回空、多个会话的标签合并去重、格式不规范的标签被 `parse_thread_tags` 纠正 |

### 验证

```bash
uv run pytest tests/unit/db/test_auto_thread_tags.py -q
```

---

## Step 2：自动打标服务（AutoTagger）

**目标**：新建一个 `AutoTagger`，输入"标题 + 首条用户消息"，输出一组清洗好的标签。

### 改动文件

| 文件 | 改动 |
|------|------|
| `src/octop/infra/agents/auto_tag.py`（新增） | 核心逻辑：① 查该用户已有标签作候选词表 ② 构造 prompt 让 LLM 从中选、最多造 1 个新词、最多 3 个 ③ 解析返回 ④ `parse_thread_tags` 清洗 ⑤ **检查现有标签为空才**调 `set_tags` 写入 |

调用 LLM 的方式**照搬** `src/octop/infra/agents/providers/probe.py:42` 的 `build_probe_chat_model`：从默认提供商构造一个 chat model，直接 `await model.ainvoke(prompt)`，不经过 harness。

### 关键点

- **prompt 里明确约束**：优先用候选词表；候选都不合适才新增，且只新增 1 个；总共不超过 3 个；只输出标签，用顿号或逗号分隔，不要输出任何解释。
- 所有 LLM 调用包在 try/except 里，失败返回空列表，调用方无感。
- 这是唯一新增的服务模块，Step 3 只调它一行。

### 验证

```bash
# 单测：mock 掉 LLM 调用，验证"选候选词 / 限 1 新词 / 限 3 个 / 空时写入、非空不覆盖 / 失败不抛"
uv run pytest tests/unit/agents/test_auto_tag.py -q
```

---

## Step 3：挂钩到对话流程（已完成）

在一轮对话成功完成、且这是会话的首个完成回合时，Processor 异步调度 AutoTagger。首回合仍以 `last_active == 0` 判定，**不依赖标题变化**；是否实际调模型统一由 AutoTagger 的 Agent 级开关判定。

---

## Step 4：Agent 级自动打标签开关（本次实施）

**目标**：让用户为每个 Agent 独立决定是否启用自动打标签。默认关闭；关闭状态下不创建标签 LLM 调用，从源头避免额外 token 和资源开销。

### 配置与兼容规则

| 项目 | 方案 |
|------|------|
| 存储位置 | `agents.config_json` 的顶层布尔字段 `auto_thread_tags` |
| 默认值 | 字段缺失、值为 `null` 或类型不为 `bool` 时，均按 `false` 处理 |
| 开启条件 | 仅字段严格为 JSON `true` 的 Agent 可以进入 AutoTagger 的 LLM 调用逻辑 |
| 作用范围 | 同一用户的不同 Agent 各自保存，互不影响；不新增数据库列或 migration |
| 已有会话 | 开关只决定后续新会话首回合是否自动打标签；不补打、删除或修改已有标签 |
| 旧全局 KV | 删除 `AutoTagger` 对 `SettingsRepo.auto_thread_tags` 的读取；数据库里历史遗留的同名 Settings 值不迁移也不再生效，避免它绕过“默认关闭”。`SettingsRepo` 仍只负责模型选择。 |

### 现有 API 与保存语义

不新增专用开关接口。编辑专家抽屉加载时已经通过 `GET /api/agents/{agent_id}` 获得完整 `config`；保存时通过已有 `PATCH /api/agents/{agent_id}` 写回合并后的完整配置。因此，抽屉必须以加载得到的 `agentConfig` 为基底，只覆盖 `auto_thread_tags`、后端和运行参数等当前编辑字段，避免丢失其余配置。

开关和抽屉其他字段一致：用户切换 `Switch` 后只更新表单本地状态，必须点击右下角“保存”才会持久化；点击取消或关闭抽屉不修改配置。无需重启 Agent：AutoTagger 每次准备处理首回合时读取当前配置。

### 后端改动文件

| 文件 | 改动 |
|------|------|
| `src/octop/infra/agents/auto_tag.py` | 保留 `SettingsRepo` 仅用于模型兜底链；改为从 `AgentRepo` 按 `agent_id` 读取 `config_json.auto_thread_tags`，并只在值严格为 `True` 时继续。检查必须位于模型解析之前，关闭时不调用 LLM。 |
| `src/octop/infra/gateway/gateway.py` | 调整 AutoTagger 构造依赖，注入读取 Agent 配置所需的现有 `AgentRepo`。 |
| `tests/unit/agents/test_auto_tag.py` | 将全局开关用例替换为：字段缺失默认关闭、仅严格 `true` 启用、关闭时不解析模型、不调用模型，以及两个 Agent 状态隔离。 |

### Dashboard 改动

开关放在 `dashboard/src/pages/Experts/components/EditAgentDrawer.tsx` 的“记录运行轨迹”下方、“可选知识库”上方，而非全局设置页或独立 Agent 配置页。抽屉加载详情时读取 `config.auto_thread_tags === true`；点击右下角“保存”时把 `auto_thread_tags: values.auto_thread_tags === true` 合并入已有 `config` 后，通过已有 PATCH 请求一并提交。

| 文件 | 改动 |
|------|------|
| `dashboard/src/pages/Experts/components/EditAgentDrawer.tsx` | 增加表单字段、加载/保存配置合并和带说明的 `Switch`。 |
| `dashboard/src/locales/zh.json`、`dashboard/src/locales/en.json` | 增加开关标题和说明的双语文案。 |

### 验证

```bash
PYTHONUTF8=1 uv run pytest tests/unit/agents/test_auto_tag.py -q
cd dashboard && npx tsc --noEmit
```

用户在界面验证：两个 Agent 初始均关闭；只开启其中一个后，为两个 Agent 各新建一轮会话，确认只有开启的 Agent 获得自动标签；关闭后新会话不再发起打标。

---

## 风险与对策

| 风险 | 对策 |
|------|------|
| 标签越打越多、失去意义 | 候选词表优先 + 最多造 1 新词 + 上限 3 个（设计决策已约束） |
| LLM 调用失败 / 超时 | try/except 吞掉，主流程零影响 |
| 拖慢消息回复 | 异步 fire-and-forget，用户看到回复的速度完全不受影响 |
| 多花了 token | 每个 Agent 默认关闭；只有用户显式开启的 Agent 才会发起轻量标签调用 |
| 自动打的标签不合心意 | 只写空标签的会话，用户可随时手动改；改后不再自动覆盖 |
| 首轮后标签不会立刻出现 | 打标是异步的，可能晚一两秒；前端那边标签栏本来就有，刷新即见，不特殊处理 |
| dashboard 抢先写标题导致触发失灵 | 2026-09-15 实测：前端发消息时乐观 PATCH 标题，`had_title` 变迁触发永远等不到。触发信号改用 `last_active == 0`，对"谁写标题、何时写"免疫 |

## 明确不做（本次范围外）

- **自动分配/创建文件夹**——文件夹是单选归属，出错成本高；将来若做，建议做成"建议文件夹、用户一键确认"而不是直接归位
- **按 IM 渠道区分不同的打标策略**——所有渠道统一一套逻辑
- **自动打标的模型可选配**——先用默认模型，以后有需求再加配置项
