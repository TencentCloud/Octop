# Octop 项目管理 / 项目记忆 / 跨团队协作 —— 可行性分析报告

> 输入：`01-需求分析文档-v1.0(1).docx`（决策已锁定版）+ 用户口述的「跨团队拉群 + 项目记忆下发」思路
> 方法：拉取 5 个仓库源码 + 关键路径逐行核实（所有结论均带 `文件:行号` 证据）
> 结论：**可以实现**。你思路里的 7 个环节中，5 个已有现成接缝（接线即可），2 个必须新建。

---

## 〇、先说三件必须纠正的前提

### 1. `octop-momory` 是笔误，正确仓库是 `octop-memory`

你给的链接 404。正确地址：<https://github.com/TencentCloud/octop-memory>。已拉取。

### 2. 四个开源仓库 ≠ 你现在 fork 的那个 Octop 的依赖（**最关键**）

| 仓库 | 模块名 | Octop `main` 依赖 | Octop `develop` 依赖 |
|---|---|---|---|
| octop-harness | `octop_harness` | `orcakit-harness-agent>=1.0.14`（模块 `harness_agent`） | **`octop-harness[all]>=1.0.0`** |
| octop-memory | `octop_memory` | `harness-memory>=0.9.11`（模块 `harness_memory`） | **`octop-memory>=1.0.0`** |
| octop-gateway | `octop_gateway` | `harness-gateway>=0.9.9` | **`octop-gateway>=1.0.0`** |
| octop-browser | `octop_browser` | `harness-browser>=0.7.9` | **`octop-browser>=1.0.0`** |

证据：`main` 的 [pyproject.toml](Octop/pyproject.toml:24) vs `develop` 的 `pyproject.toml`（我单独拉了 develop 分支核对）。

这四个仓库是 harness-* 运行时**开源并改名后的 1.0.0 版本**（`octop-memory` 的更名说明在 [integrations.md](octop-memory/docs/integrations.md:7)：*"不提供旧命令、import 或环境变量别名"*）。

**这意味着：**

- 在 `main` 上 fork，`harness_agent` 是一个**不在这四个开源仓库里的闭源 wheel** → 你想改 agent 内部行为（群聊、记忆注入）**改不动**。
- 在 `develop` 上 fork，四个运行时**全部开源可改**，且 Octop 的 import 已经切成 `octop_harness` / `octop_gateway`。
- **所以：fork 必须基于 `develop`，不是 `main`。** 这是本次分析里对路线选择影响最大的一条。

### 3. 需求文档里两处技术前提已过期

| 文档原文 | 实际情况 | 影响 |
|---|---|---|
| §1.1「已有 KB 知识库（含跨用户 shared + **成员表**）」 | `knowledge_base_members` 表**已在 v7 迁移中被 DROP**（[007_resource_identity_and_profile.sql](Octop-develop/src/octop/infra/db/migrations/007_resource_identity_and_profile.sql:20)，CHANGELOG 记为"删除未使用的表"）。现在 KB 只有 `owner_user_id` + `shared` 布尔两态 | **M3「绑定项目知识库（KB 成员）」没有先例可复用**，要新建 KB 成员模型 |
| §10「迁移 **018**」 | 仓库最新迁移是 `017_thread_conversation_mode`，下一个确实是 018 | ✅ 文档这条判断**正确** |

文档里另外两条我逐一核实过，**完全正确**：team host 的 `HOST_TOOLS_ALLOWED` 白名单、WeKnora 连接器只读。

---

## 一、能不能实现？—— 结论

**能。** 而且比你预想的顺利：你描述的核心机制（拉群、拉人、拍板、下发记忆、派单开发）**有 5 个环节在 Octop 里已经有现成代码**，只是没有产品化外壳。

| 你的环节 | 现状 | 工作量 |
|---|---|---|
| ① 把「团队」建成可协作实体 | ✅ 已有：`agents.kind='team'` + host + 工区 manifest 编制 | 0 |
| ② 拉群（多 Agent 同房间讨论） | 🟡 **已有雏形**：团队房间（host thread + 成员发言投影 + speaker 标记 + WS 流 + IM 通道推送），但限「单用户内单团队」 | 中 |
| ③ 拉我（真人进房间） | 🟡 真人本来就能在 thread 里发言，但没有「房间成员」实体来管理谁在群里 | 小 |
| ④ 拉任务相关人员 / 拉开发团队 | ✅ `ask_agent` 可跨团队调用同用户任意专家；`team_peers` 是**请求级白名单**，现成接缝 | 小 |
| ⑤ 项目经理拍板 | ✅✅ **HITL 人工闸门完整存在**（含 IM 卡片式审批、暂停/恢复） | 0~小 |
| ⑥ 把部分项目记忆下发给开发团队 | 🟡 注入接缝 `bind_peer_session` 现成；但「项目级记忆」本身不存在，要新建 | 中 |
| ⑦ 开发团队快速了解后开发 | ✅ `acp_runner` 工具可派 OpenCode / Claude Code / Codex / CodeBuddy | 小 |
| ⑧ commit 回写任务 | ❌ **完全空白**，Octop 侧没有任何 commit/diff 落库逻辑 | 中 |

---

## 二、项目记忆：可以复制 Octop Memory 的模式吗？

### 2.1 先回答「能不能复制」——准确答案是：**你不需要复制，Octop 里已经跑着它了**

Octop 的 per-agent 记忆就是 octop-memory（harness-memory 的开源版）：

- 装配层：[memory_backend.py](Octop-develop/src/octop/infra/agents/memory_backend.py:68) → `open_memory_kwargs()`
- 注入层：octop-harness 的 [memory.py](octop-harness/src/octop_harness/middleware/memory.py:259) `MemoryMiddleware.before_model()` → `MemoryService.recall()` → 把 `result.rendered` 打快照进消息
- 召回链：[recall/__init__.py](octop-memory/src/octop_memory/pipeline/recall/__init__.py:314)（cache → parse → route → gather → rerank → diversify → suppress → budget → render）

所以「复制模式」应改为「**加一个项目级作用域的 Memory 实例**」。这是成本最低、且天然继承全部能力的路径。

### 2.2 哪些能白拿，哪些必须自研

**可以直接吃（这是你最该白拿的部分）：**

| 能力 | 出处 | 价值 |
|---|---|---|
| 分层蒸馏 `RawEvent→Candidate→AtomCard→EntityPage` | [types.py](octop-memory/src/octop_memory/types.py:57)、[prompts.py](octop-memory/src/octop_memory/pipeline/extractor/prompts.py:236)（v2.3） | 「一事一条 + 来源必填」正好对上 M15 |
| **中文 FTS5 单字切分** | [fts_text.py](octop-memory/src/octop_memory/storage/backends/fts_text.py:46) | 中文项目讨论召回的关键，别自己写 |
| 召回全链路（5 因子排序 / 去重 / 抑制 / token 预算 / 渲染模板） | [rerank.py](octop-memory/src/octop_memory/pipeline/recall/rerank.py:40)、[budget.py](octop-memory/src/octop_memory/pipeline/recall/budget.py:77)、[recall/__init__.py](octop-memory/src/octop_memory/pipeline/recall/__init__.py:223) | 直接解决 R7「记忆膨胀」+ R8「token 失控」 |
| promotion 规则链（价值/证据/实体/重复/冲突） | [checks.py](octop-memory/src/octop_memory/pipeline/promotion/checks.py:178) | 5 个 check 不用自己写 |
| **作废 / supersede / GC 保留期** | [core.py](octop-memory/src/octop_memory/core.py:471)（`supersede_atom`）、[gc.py](octop-memory/src/octop_memory/pipeline/lifecycle/gc.py:6) | 对上 M15「可作废」+ 用户故事 22 |
| 跨宿主打包 `.hmpkg` + `doctor` 校验 | [packer.py](octop-memory/src/octop_memory/operations/migration/portable/packer.py:127)、[adopter.py](octop-memory/src/octop_memory/operations/migration/portable/adopter.py:177) | 对上「把记忆下发给另一个团队」 |
| 双 backend（SQLite FTS5 / PG tsvector） | `storage/backends/` | 和 Octop 的 SQLite/PG 双栈天然一致 |

**必须自研（这是 Octop Memory 明确不做的）：**

| 缺口 | 证据 | 说明 |
|---|---|---|
| **作用域只有 namespace**，没有 user/project/team 行级隔离 | [sqlite.py](octop-memory/src/octop_memory/storage/backends/sqlite.py:61)（表名前缀 `{ns}_`）；PG 用 `namespace` 列 | 项目隔离靠「一个项目一个 namespace」实现，不靠行级字段 |
| **零权限 / 零 ACL** | bridge 自述 *"no auth, no encryption"*（[bridge/__init__.py](octop-memory/src/octop_memory/adapters/bridge/__init__.py:23)） | 项目成员可见性必须**在 FastAPI 层自建** |
| **atom 层没有 owner 列** | `atoms` 表无 user 列 | 「这条事实属于谁」在事实层无法回答，只能靠 namespace 归属推断 |
| **选择性共享**：只能整 namespace rename / 整表 JSONL / 整包 `.hmpkg` | [rename.py](octop-memory/src/octop_memory/operations/migration/rename.py:9) | 「发送**部分**项目记忆」要么用子 namespace，要么用 recall 渲染成文本 |
| **无记忆版本 / 无增量注入** | 两侧都未找到 | AC-11「注入版本 +1」要从零设计 |
| **并发**：`Memory` 是单连接单线程设计 | [bridge/server.py](octop-memory/src/octop_memory/adapters/bridge/server.py:22) | FastAPI 多 worker 需 per-worker 实例 + WAL，或切 PG |
| 无项目语义类型（sprint / 里程碑 / 需求单） | [types.py](octop-memory/src/octop_memory/types.py:99) 枚举是个人助手导向 | 需求节点类型要自建 |

### 2.3 推荐的项目记忆设计（三档，按成本排序）

**档位 A —— 项目 = 一个 namespace（推荐一期）**

```
项目创建 → 分配 namespace: project_{project_id}
            ↓
派工/拉群时 → MemoryService(namespace=project_X).recall(query=任务标题+描述, limit=5)
            ↓ rendered
       bind_peer_session(prepare=...) 把 rendered 拼进 message
```

- 改动点极小：`open_memory_kwargs()`（[memory_backend.py](Octop-develop/src/octop/infra/agents/memory_backend.py:76)）现在写死 `ns = f"agent_{agent_id}"`，扩展成可按 project 取 ns。
- 注入完全走 harness 的现成钩子：[team_manager.py](octop-harness/src/octop_harness/teams/team_manager.py:86) `bind_peer_session(prepare=...)`，其 docstring 原话就是 *"prepare may rewrite thread_id / session_key / message / configurable (for example Octop's threads table and **a group-chat transcript**)"*——**这就是官方给你留的项目记忆注入点**。
- 优点：复用全部召回能力，天然有 token 预算和去重，不会把项目记忆做成流水账。
- 注意：SQLite 前缀方案下 namespace 多了表数会线性增长；项目多时建议直接上 PG。

**档位 B —— 项目记忆 = 工作区 Markdown（快速验证用，不建议生产）**

项目创建时往 agent 工作区写 `PROJECT_MEMORY.md`，靠 harness 的 memory 注入生效。

- 致命问题 1：注入文件名是**硬编码**的 4 个（`AGENTS.md/MEMORY.md/USER.md/SOUL.md`，见 [workspace.py](octop-harness/src/octop_harness/backends/workspace.py:79)），要 per-project 注入必须改 harness 核心。
- 致命问题 2：注入是**每轮全量拼接**，不是增量 → 项目一长 token 直接爆（正是文档 R8 担心的场景）。
- 只适合做 3 天 Spike 验证链路。

**档位 C —— 改造 octop-memory 加 project 维度（二期再说）**

给每张表加 `project_id` 列 + 行级权限，实现「一份记忆多项目复用 + 细粒度共享」。

- 要改 [sqlite.py](octop-memory/src/octop_memory/storage/backends/sqlite.py)（2242 行）和 [postgres.py](octop-memory/src/octop_memory/storage/backends/postgres.py)（2354 行）每一处 WHERE，且受项目自身「双 backend gate」约束（`AGENTS.md` 要求 SQLite/PG 同步维护并跑真实 PG 用例）。
- 只有当你确实需要「跨项目复用记忆 + 按条授权」时才值得。

### 2.4 「把**部分**项目记忆发给开发团队」的三种落地方式

| 方式 | 做法 | 改造成本 | 适用 |
|---|---|---|---|
| **推文本（推荐日常）** | 派工/拉群时 `recall(任务标题+描述)` 渲染成 `[memory]...[/memory]` 文本拼进 message | 几乎为零 | 每次派工自动带上下文，对上 AC-09 |
| **推子包（冷启动）** | 把要交接的记忆写进 `proj_X_handoff_dev` 子 namespace，`pack()` 成 `.hmpkg` 交付 | 低（纯约定） | 新团队/新专家入场，对上用户故事 22「0 提问进入状态」 |
| 按 atom 粒度分享 | 自研选择器 + 复制 | 高 | 二期 |

**注意**：`bind_peer_session` 的 `prepare` 只能改写 `thread_id/session_key/message/configurable`，身份键（`agent_id/user/thread_id/source`）会被过滤防冒充（[util.py](octop-harness/src/octop_harness/teams/util.py:16)）——这是个**安全设计，不要绕过**。

---

## 三、跨团队协作：团队之间怎么互相调用

### 3.1 现成的调用链（已核实）

```
宿主 Octop
  └─ HarnessAgentManager（按用户）
      └─ AgentRuntime（按 Agent）
          └─ HarnessAgent + PeerAgentMiddleware（team_enabled=True 时挂载）
              ├─ agent_list   → TeamManager.list_peers(user_id)
              └─ ask_agent    → resolve_peer → call_peer(sync) 或 submit_peer(async inbox)
```

- **工具面**：[tools.py](octop-harness/src/octop_harness/teams/tools.py:140) `build_team_tools()`
- **可调用范围**：[team_manager.py](octop-harness/src/octop_harness/teams/team_manager.py:175) `list_peers()` —— `metadata["user_id"]` 为 None（共享专家）或与调用者相同（同用户）的**全部专家**，不限于本团队
- **`team_peers` 白名单**：请求级覆盖，`None` 表示不限制（[:191-199](octop-harness/src/octop_harness/teams/team_manager.py:191)）
- **同步/异步**：`peer_invoke_mode` 三态 `sync|async|both`，且**只能降权不能提权**（[util.py](octop-harness/src/octop_harness/teams/util.py:26)，有测试锁定）

### 3.2 「拉群」——房间机制已经存在

Octop 的团队房间（[team_manager.py](Octop-develop/src/octop/infra/agents/teams/team_manager.py:1) 文件头 docstring）：

- **房间 ID = 主持人的 `thread_id`**
- 成员独立 checkpoint：`{主thread}~{成员id}`（[derive_peer_thread_id](octop-harness/src/octop_harness/teams/util.py:72)）
- 成员发言 **fan-in 回房间** 并逐 token 转播（`stream_peer_to_room`）
- 每条消息带 **`speaker_agent_id`**，前端已支持气泡区分说话人（有 `MessageBubble.teamSpeaker.test.tsx` 覆盖）
- 房间内容**还能推到 IM 群**：[`_push_room_to_channels()`](Octop-develop/src/octop/infra/agents/teams/team_manager.py:889) 会把成员发言以完整出站消息推到绑定该 thread 的 IM 会话
- 派工消息**自带房间 transcript**：`teams.member_briefing_with_history`（[:623-636](Octop-develop/src/octop/infra/agents/teams/team_manager.py:623)）

**所以「拉群、多 Agent 同房间讨论、电脑上/微信里都能看」这件事，Octop 已经做到了 80%。**

### 3.3 你的场景逐步拆解

| 步骤 | 现成程度 | 具体落在哪 |
|---|---|---|
| 交付团队执行中发现问题 | ✅ | 团队 host 已经在跑 |
| **拉一个群** | 🟡 需扩展 | 现房间 = 单团队；要「交付团队 + 开发团队 + 真人」同房间，需要新增**房间参与人**实体（给 `thread_id` 挂 participant 列表），并把 `team_peers` 注入为房间全集 |
| **拉我（真人）** | 🟡 需扩展 | 真人在 thread 里发言本来就通（host 派工时取最后一条 human 消息），但没有「成员」实体管理谁在群里、谁能看 |
| **拉任务相关人员** | ✅ | `team_peers` 请求级白名单现成，注入目标名单即可 |
| **拉开发团队** | ✅/🟡 | `ask_agent` 可跨团队调同用户专家 ✅；但「团队」被硬性禁止共享（[manager.py](Octop-develop/src/octop/infra/agents/manager.py:597) 抛 `TEAM_NOT_SHAREABLE`），跨用户要改可见性判定 |
| **项目经理论证并拍板** | ✅✅ | HITL 完整链路：[models.py](octop-harness/src/octop_harness/security/models.py:46) `HitlPolicy` → [agent.py](octop-harness/src/octop_harness/agent.py:1369) `interrupt_on` → `HITL_REQUIRED` 事件 → `resume_hitl()`；IM 侧审批卡片在 [coordinator.py](Octop-develop/src/octop/infra/gateway/hitl/coordinator.py) + `format_ask_card`。**「拍板」不需要新建机制，把 Owner 确认闸门做成 HITL 即可** |
| **把部分项目记忆下发给开发团队** | 🟡 | 接缝 `bind_peer_session(prepare=...)` 现成；项目记忆本体要新建（见 §2） |
| **开发团队快速了解后开发** | ✅ | `acp_runner` 工具，支持 list/start/message/respond/status/close |
| **commit 回写任务** | ❌ | 完全空白，见 §四 |

### 3.4 三层防失控（现成的，别改坏）

1. team host 工具白名单只有 5 个：`agent_list / ask_agent / memory_search / memory_get / current_time`（[service.py](Octop-develop/src/octop/infra/agents/teams/service.py:25)）
2. 成员被派工时请求级强制降级为 `sync` + `team_peers` 收窄到本团队成员 → **成员不能再异步往群里拉人**（[team_manager.py](Octop-develop/src/octop/infra/agents/teams/team_manager.py:534)）
3. 成员不能是 team → 杜绝嵌套团队（[service.py](Octop-develop/src/octop/infra/agents/teams/service.py:198)）

⚠️ 你要做的「跨团队拉群」会**触碰第 2 条**。建议做法：不要放开成员权限，而是**新增一个「项目房间 host」角色**（普通专家 + 房间工具白名单），由它来做跨团队调度 —— 这样第 2 条对原团队成员继续生效。

---

## 四、真实缺口清单（无任何既有实现）

| # | 缺口 | 影响需求 |
|---|---|---|
| 1 | **无 project / task / ticket / issue 实体**（30 张表全查过，一个都没有） | M1/M4/M5 从零建域（但也意味着零冲突） |
| 2 | **无业务评论实体**，没有 `parent_id` 盖楼、没有 reactions。`thread_messages`（`role` + `message_json`）是唯一语义接近的底座 | M6/M7 要新建，或把评论建模进 `thread_messages` |
| 3 | **ACP 执行结果无 commit/diff 回写** | M13 后半段、C2 |
| 4 | **无记忆版本 / 无增量注入** | AC-11 |
| 5 | **无 KB 成员模型**（v7 已删） | M3 要重新设计 |
| 6 | **octop-gateway 完全没有建群/拉人 API**（全仓 grep `create_chat|createGroup|invite|add_member` 零命中） | S4「IM 群联动」若需**主动建群**则要自研；若只是「已有群 ↔ 项目房间」绑定，则现成 |
| 7 | **feishu/discord 直接丢弃所有 bot 消息**（[feishu.py](octop-gateway/src/octop_gateway/channels/feishu.py:485)、[discord.py](octop-gateway/src/octop_gateway/channels/discord.py:229)） | 多个 Agent 同群会**互相失聪**，多 Agent 入群必须改造 |
| 8 | **WeKnora 只读**（适配器第一行 docstring 就是 "Read-only"） | M14 一期只写 Octop KB（文档 R5 判断正确） |
| 9 | group_context 算出来了但**没送进 Agent**（示例 processor 未读 `msg.group_context`） | S4 群上下文回流要补这一环 |

---

## 五、改动面与 rebase 成本

### 5.1 纯新增文件（rebase 零成本）

```
src/octop/infra/db/migrations/018_projects.sql + .pg.sql
src/octop/infra/db/repos/projects.py
src/octop/infra/projects/service.py
src/octop/api/routers/projects.py
dashboard/src/pages/Projects/ (+ components/)
dashboard/src/api/modules/projects.ts (+ api/types/projects.ts)
tests/unit/projects/ 、tests/integration/test_projects_api.py
docs/projects.md
```

### 5.2 必改核心文件（rebase 成本来源 = 5 个热点）

| 文件 | 改什么 | 风险 |
|---|---|---|
| [api/app.py](Octop-develop/src/octop/api/app.py) | 加 import + `_mount_routers` mount | **高（冲突热点）** |
| [infra/db/services.py](Octop-develop/src/octop/infra/db/services.py) | `RepoBundle` / `from_pool` / `SharedServices` 三处 | **高（全域共用）** |
| [dashboard/src/routes/index.tsx](Octop-develop/dashboard/src/routes/index.tsx) | lazy + pathToKey + routes | **高（冲突热点）** |
| [dashboard/src/layouts/sidebarNav.tsx](Octop-develop/dashboard/src/layouts/sidebarNav.tsx) | 分组白名单 + NavItem | **高（冲突热点）** |
| [dashboard/src/utils/permissions.ts](Octop-develop/dashboard/src/utils/permissions.ts) | PERM / NAV_PERMISSIONS / pathPermissionKeys | 中 |
| [infra/users/permissions.py](Octop-develop/src/octop/infra/users/permissions.py:50) | 加 `projects` 权限键（现有 22 个） | 中（前端要同步） |
| [infra/db/migrate.py](Octop-develop/src/octop/infra/db/migrate.py) | 加幂等 `_ensure_projects_schema()` | 中 |
| [infra/errors.py](Octop-develop/src/octop/infra/errors.py) + `i18n/{en,zh}.json` | 新增 `PROJECT_*` 错误码（两语言键必须一致） | 中 |
| [tests/unit/db/test_db_pool.py](Octop-develop/tests/unit/db/test_db_pool.py) | **7 处 `assert v == 17` → `== 18`** | 低但必做 |
| [tests/unit/api/test_acl_gate_coverage.py](Octop-develop/tests/unit/api/test_acl_gate_coverage.py:12) | `GATED_FILES` 加新路由 | 低但必做（否则守卫静默漏检） |
| `infra/agents/manager.py` | **仅项目级记忆注入需要**：`memory` 语义要按项目动态化 | 高 |

- 迁移规范：`NNN_x.sql` + `NNN_x.pg.sql` 成对，文件末尾自写 `UPDATE _schema_version SET version = 18;`
- 权限校验走依赖注入 `require_permission("projects")`（[deps.py](Octop-develop/src/octop/api/deps.py:201)），**新增路由默认受 JWT 保护，无需登记**
- Ship bar：`make all`（format-all + lint + mypy + pytest）

---

## 六、建议的实施路线（基于「不改坏上游」原则）

**Step 0（3 天 Spike，压不确定性）**
在 `develop` 上验证三件事：① 新增 `018_projects` 迁移能落地且 7 处断言改完绿；② Dashboard 新页面挂路由 + i18n 双语；③ `bind_peer_session` 注入项目记忆文本能在派工消息里看到。

**Step 1（项目域 MVP）**
`projects / project_members / project_tasks / project_comments` 四表 + 看板 + 权限键。这一层**不碰 agent 运行时**，风险最低。

**Step 2（项目记忆 = 档位 A）**
项目 namespace + `open_memory_kwargs` 扩展 + `bind_peer_session` 注入。对上 AC-09 / AC-11。

**Step 3（Owner 闸门接 HITL）**
需求节点确认做成 HITL，IM 侧直接复用审批卡片。对上 AC-07 / AC-15。

**Step 4（跨团队房间）**
新增「项目房间」概念：房间 host + participant（人 + 专家 + 团队）+ `team_peers` 注入房间全集。**不动**原团队成员的降级规则。

**Step 5（派单 + 交付物）**
`acp_runner` 派单 + commit 回写（自研，需要约定 runner 输出格式）。

**Step 6（IM 联动，可选）**
已有群绑定项目房间推消息 ✅；主动建群/拉人需自研，且需先解决「多 Agent 同群互相失聪」。

---

## 七、需要你先拍板的两个决策

1. **项目记忆接受哪种档位？**
   - 档位 A（项目 namespace + recall 注入）：能力完整，改动可控 —— **推荐**
   - 档位 B（工作区 Markdown 全量注入）：3 天能出 Demo，但项目一长 token 会爆，不建议生产
   - 档位 C（改造 octop-memory 加行级 project 维度）：最强也最贵，建议二期

2. **跨团队协作先做到哪一步？**
   - 只做**同用户内多团队房间**（交付团队 + 开发团队都是你的专家）—— 成本可控，**推荐一期**
   - 要做**跨用户**房间（同事的团队也能拉进来）：要改 octop-harness 的 `list_peers` 可见性语义 + 新增团队共享/成员表（团队编制现在存在 host 工作区 manifest 里，**跨用户共享一个工作区文件不是可行载体**），成本陡增

---

## 附：本报告核实过的关键坐标

| 主题 | 文件:行 |
|---|---|
| team host 工具白名单 | `Octop-develop/src/octop/infra/agents/teams/service.py:25` |
| 房间 fan-in + IM 推送 | `Octop-develop/src/octop/infra/agents/teams/team_manager.py:889` |
| 派工消息带房间 transcript | `Octop-develop/src/octop/infra/agents/teams/team_manager.py:623` |
| 成员降级防失控 | `Octop-develop/src/octop/infra/agents/teams/team_manager.py:534` |
| 项目记忆注入接缝 | `octop-harness/src/octop_harness/teams/team_manager.py:86` |
| 只传文本不传历史 | `octop-harness/src/octop_harness/teams/util.py:130` |
| 可调用范围 | `octop-harness/src/octop_harness/teams/team_manager.py:175` |
| 记忆注入 middleware | `octop-harness/src/octop_harness/middleware/memory.py:259` |
| HITL 策略 | `octop-harness/src/octop_harness/security/models.py:46` |
| per-agent namespace 写死 | `Octop-develop/src/octop/infra/agents/memory_backend.py:76` |
| 记忆打包/迁移 | `octop-memory/src/octop_memory/operations/migration/portable/packer.py:127` |
| 中文 FTS 切分 | `octop-memory/src/octop_memory/storage/backends/fts_text.py:46` |
| 迁移最新编号 | `Octop-develop/src/octop/infra/db/migrations/017_thread_conversation_mode.sql` |
| 团队不可共享 | `Octop-develop/src/octop/infra/agents/manager.py:597` |

---

# 附录 B：第二轮追问的核实结论

## B1. 项目记忆 A → C 能升级吗？

**能，现成工具齐备，但有一个前提必须在 A 阶段就做对。**

### 现成的迁移工具

| 工具 | 位置 | 能力 |
|---|---|---|
| `rename_namespace` | [rename.py](octop-memory/src/octop_memory/operations/migration/rename.py:1) | 纯**元数据操作**（改 `{ns}_` 表前缀），支持 rename 或 copy（`--keep-source`） |
| `export_namespace(..., tables=...)` | [export.py](octop-memory/src/octop_memory/operations/migration/export.py:248) | **可按表导出子集** |
| `import_namespace(...)` | [import_.py](octop-memory/src/octop_memory/operations/migration/import_.py:332) | JSONL 重放到任意目标 namespace/backend，支持 `on_conflict` |
| `_migrate_schema()` | [sqlite.py](octop-memory/src/octop_memory/storage/backends/sqlite.py:629) | 探测 + `ALTER TABLE ADD COLUMN` 增量模式 |

### A→C 的实质 = 「N 个 namespace」→「1 个 namespace + 一列 project_id」

**SQLite 与 PG 的成本差一个数量级：**

- **PG 侧几乎免费**：共享 schema 里每张表**已经有 `namespace` 列 + PK `(namespace, id)`**。A→C 只差 `ALTER TABLE ADD COLUMN project_id` + 从 namespace 反填 + 调 PK。**在 PG 上做的 A，其实已经是「行级就绪」状态。**
- **SQLite 侧要重**：表前缀方案下一个项目一套表，转成单套表要么重建，要么走 `export_namespace(每个项目 ns) → import_namespace(单 ns) → ADD COLUMN → 反填`。

### ⚠️ 前提：AtomCard 里藏不了 project_id

[AtomCard](octop-memory/src/octop_memory/types.py:184) 的字段全表是：`id / entity_id / candidate_id / raw_event_ids / assertion / verbatim_quote / quote_event_id / search_terms / occurred_at / confidence / importance / created_at / superseded_by / deprecated_at`。

**没有 `metadata`、没有 `topic`、没有 `project_id`。** 所以 A 阶段不可能把项目归属藏在记忆行里，C 阶段的回填只能靠外部映射。

**因此 A 阶段必须做两件事：**
1. 使用**确定性命名规则** `project_{project_id}`（不要放飞命名）；
2. 在 Octop 控制面存映射：`projects.memory_namespace`。

这样 C 阶段回填 = 读映射表直接 UPDATE，**零启发式、零猜测、可重放**。

### 结论与建议

| 问题 | 答案 |
|---|---|
| A→C 可行吗 | ✅ 可行，迁移脚本可写，风险中等 |
| 最大成本在哪 | SQLite 的表前缀 → 单套表；PG 侧只是 ADD COLUMN |
| **省钱的选项** | **A 阶段就直接用 PG 后端**。这样 A→C 从「表重建工程」降级为「一个小迁移」。如果项目数会超过十几个，这一步几乎必然要做 |
| 现在要额外做什么 | ① 命名规则固定为 `project_{id}`；② 控制面加 `memory_namespace` 映射列；③ 把"项目记忆读写"收敛到一个 `ProjectMemoryStore` 门面，将来换实现只改这一个文件 |

**第三条最关键**：只要所有调用都走 `ProjectMemoryStore` 门面（内部现在用 namespace，将来改成 project_id 列），A→C 就是换实现，不动业务代码。

---

## B2. 跨团队协作：不管谁建的团队，项目成员都能互动

**技术上可行。而且有个好消息纠正了我上一轮的说法。**

### 好消息：跨用户调用在运行时是通的

我核对了注册表归属 —— [AgentManager](Octop-develop/src/octop/infra/agents/manager.py:318) 是**进程级单例**（在 [server.py](Octop-develop/src/octop/infra/server.py:373) 创建一次），内部只有**一个** `HarnessAgentManager`（[manager.py](Octop-develop/src/octop/infra/agents/manager.py:468)）。

> README 架构图里写的 "HarnessAgentManager（按用户）" **不准确**。实际上所有用户的 agent 都在同一个进程级注册表里，靠 [metadata["user_id"]](Octop-develop/src/octop/infra/agents/manager.py:2877) 区分归属。

**这意味着「跨用户互动」不需要动架构，只需要放可见性。** 拦路虎只有三处。

### 三处放权

**① 组队时** — [`_user_may_use_member`](Octop-develop/src/octop/infra/agents/teams/service.py:71)

现在只认 admin / 本人 / `is_shared`。要让「项目成员互相把对方专家加进团队」，这里加一条判定：**该 agent 的 owner 是本项目成员**。纯 Octop 侧改动，无风险。

**② 调用时** — [`list_peers`](octop-harness/src/octop_harness/teams/team_manager.py:175)（**必须改 octop-harness**）

```python
for entry in self._registry.list():
    meta_uid = entry.metadata.get("user_id")
    if meta_uid is None or str(meta_uid) == wanted:   # ← 硬前置过滤
        by_id[entry.agent_id] = entry
```

关键在于：`team_peers` 白名单是在**这个过滤之后**才应用的（[:191-199](octop-harness/src/octop_harness/teams/team_manager.py:191)）——所以**它只能收窄，永远不能放宽**。

要放宽只有一条路：给 octop-harness 加一个宿主可注入的作用域钩子。仿照已有的 `bind_peer_enrich` / `bind_peer_session` 风格：

```python
# teams/team_manager.py（约 15 行）
def bind_peer_scope(self, scope: Callable[[str], set[str] | None] | None) -> None:
    """Return the caller's allowed peer agent_ids, or None to keep the user_id rule."""
```

返回非 None 时替换前置过滤；Octop 侧用 `project_members` 实现它。

> **这是 fork 必须基于 `develop` 的第二个硬理由**：这个补丁只在 octop-harness 开源版上做得成。

**③ 运行时会话归属（唯一需要实测的点）**

[`_build_peer_request`](octop-harness/src/octop_harness/teams/team_manager.py:455) 用**调用方的 `user_id`** 构造 callee 请求；而 callee 的连接器 / ACP runner 用的是 **agent owner 的 `user_id`**（[manager.py](Octop-develop/src/octop/infra/agents/manager.py:3151) `acp_user_id = row.user_id`）。

跨用户时这两者会不一致，必须显式定策略：

| 待定问题 | 建议 |
|---|---|
| token 计量算谁 | 算**调用方**（谁发起谁付费），但要在 UI 提示 |
| 产物落谁的 thread | 落**项目房间 thread**（不落个人 thread） |
| 谁的权限可见 | 项目成员可见（用项目房间做边界，不靠个人 thread） |
| callee 的记忆 namespace | 保持 `agent_{callee_id}` 不变，**不要**因为跨用户切换 |

### 安全设计建议（重要）

不要把规则做成「谁的 agent 都能被任何人调」。正确语义是：

> **agent owner 同意把自己的 agent 加入本项目 → 该 agent 成为项目成员 → 项目内其他成员可调它。**

这样既满足「项目成员都能互动」，又不破坏 owner 边界。落地就是 `ProjectMember(subject_type=agent, subject_id=..., role=...)` —— **项目成员表本身就是唯一授权来源**。

### 还要顺带放宽的两处

| 位置 | 现状 | 要改 |
|---|---|---|
| [manager.py](Octop-develop/src/octop/infra/agents/manager.py:597) | `kind=team` 抛 `TEAM_NOT_SHAREABLE` | 跨用户团队要么放开，要么规定"团队跟随 host 的 owner" |
| [service.py](Octop-develop/src/octop/infra/agents/teams/service.py:22) | 团队成员编制存在 **host 工作区的 `manifest.json`** | ⚠️ **跨用户共享一个工作区文件不是可行载体**。要么保持"编制只能由 host owner 维护"，要么把编制迁到控制面表（`team_members`）——**如果要做跨用户团队，这件事躲不掉** |

---

## B3. 团队里没有连接器 / 知识库 —— 确实是硬编码砍掉的

我核实了 [manager.py](Octop-develop/src/octop/infra/agents/manager.py:3315) `_apply_team_host_config()` 与上游构建逻辑。**你的观察完全属实，而且是"双保险"地砍掉**（既清空 `tools`，又叠加 denylist）：

| 被砍掉的 | 位置 | 后果 |
|---|---|---|
| `tools_disabled` = 全目录 − 5 个白名单 | [:3323-3326](Octop-develop/src/octop/infra/agents/manager.py:3323) | **`search_knowledge` 在目录里**（[tool_catalog.py](Octop-develop/src/octop/infra/agents/tool_catalog.py:89)）→ **被禁，host 查不了知识库** |
| `mcp_server_configs = {}` | [:3331-3332](Octop-develop/src/octop/infra/agents/manager.py:3331) | **连接器 / MCP 全没了**（上游 [:3166](Octop-develop/src/octop/infra/agents/manager.py:3166) `if not team_host:` 就根本没构建） |
| `tools = None` | [:3335-3336](Octop-develop/src/octop/infra/agents/manager.py:3335) | 二次抹掉 merged_tools（`knowledge_tools` 在 [:3138](Octop-develop/src/octop/infra/agents/manager.py:3138) 刚加进去就被抹掉） |
| `acp_runners` 清空 | [:3147-3149](Octop-develop/src/octop/infra/agents/manager.py:3147) | **host 不能直接派 ACP runner**，只能让成员去派 |
| `skills_dir = None` | [:3333-3334](Octop-develop/src/octop/infra/agents/manager.py:3333) | 技能全没了 |
| `subagents_auto_load=False` / `bootstrap_enabled=False` | [:3337-3340](Octop-develop/src/octop/infra/agents/manager.py:3337) | 无子 agent、无 bootstrap |

### 改进方案（按成本排序）

| # | 方案 | 改动量 | 说明 |
|---|---|---|---|
| 1 | **只放开知识库** | **1 行** | 把 `search_knowledge` 加进 [HOST_TOOLS_ALLOWED](Octop-develop/src/octop/infra/agents/teams/service.py:25)。host 立刻能查项目 KB —— 对"拍板前先看资料"很关键 |
| 2 | **放开连接器** | 2 处 | 去掉 [:3166](Octop-develop/src/octop/infra/agents/manager.py:3166) 的 `if not team_host` 门禁 **+** 去掉 [:3331-3332](Octop-develop/src/octop/infra/agents/manager.py:3331) 的清空。⚠️ 连接器工具走 MCP 注入，**不受 `tools_disabled` 管**，必须成对改，只改一处无效 |
| 3 | **放开 ACP** | 1 处 | 去掉 [:3147-3149](Octop-develop/src/octop/infra/agents/manager.py:3147) 的清空。这样"项目经理拍板 → host 直接派 OpenCode / Claude Code"就通了，不用再绕一层成员 |
| 4 | **保守推荐：新增「项目房间 host」角色** | 中 | 不改原团队 host 规则，另建一个角色配「项目房间工具白名单」（含 `search_knowledge` / MCP / `acp_runner`） |

### ⚠️ 为什么推荐方案 4 而不是简单放大白名单

现有 5 个工具的白名单是**刻意的防失控设计**，[service.py](Octop-develop/src/octop/infra/agents/teams/service.py:24) 的注释写得很明白：

```python
# Hosts only dispatch and keep light memory/time — members do the work.
```

配合另外两条防线（成员派工时强制降级 `sync` + `team_peers` 收窄；成员不能是 team），共同构成"主持人只调度、不干活"的边界。

- 简单放大白名单 → host 既调度又干活，**递归/成本失控的保护会被削弱**。
- 新建「项目房间 host」角色 → 原团队 host 规则完全不动，新角色单独配白名单，"调度者"和"执行者"职责仍然分离。

**建议：方案 1 立即做（1 行、零风险、收益直接）；方案 4 作为项目房间的正式设计；方案 2/3 只在确有需要时按角色开放，不要放开全局 host。**

---

# 附录 C：决策「项目记忆直接上 PG」的落地影响

> 决策：档位 A，存储直接选 PostgreSQL。

## C1. 这个决策带来的四个变化

### 变化 1：不需要独立数据库

[memory_backend.py](Octop-develop/src/octop/infra/agents/memory_backend.py:32) `memory_backend_from_agent_config()`：**控制面是 PostgreSQL 时，记忆默认复用同一 DSN**（`octop_config.database.postgresql_conninfo()`，[:33-39](Octop-develop/src/octop/infra/agents/memory_backend.py:33)）。

→ 项目记忆 = 控制面 PG 里的 `octop_memory` schema，**零新增基础设施**。

### 变化 2：新建项目 namespace 在 PG 上是零 DDL

| | SQLite | PostgreSQL |
|---|---|---|
| 一个 namespace 的物理形态 | 11 张实体表 + 5 张 FTS5 虚表 + 触发器（表名前缀 `{ns}_`） | **固定表集里的一列取值**（[postgres.py](octop-memory/src/octop_memory/storage/backends/postgres.py:43) `SHARED_SCHEMA = "octop_memory"`） |
| 新建一个项目记忆空间 | 建 16 张表 | **INSERT 行即可，零 DDL** |
| 项目数增长 | 表数线性爆炸 | 行数增长 |

→ **这印证了 PG 决策的正确性。**

### 变化 3（最重要）：A 与 C 的差距在 PG 上被大幅拉平

PG 的表已经是 **`namespace` 列 + PK `(namespace, id)`** —— **档位 A 在 PG 上本来就是"行级隔离"**，不是 SQLite 那种"一套表一个 namespace"。

所以 C 相对 A 真正多出来的能力**只有两条**：

1. **一条记忆同时属于多个项目**（需要多对多表，A 做不到）
2. 语义更直白（`project_id` 比 namespace 前缀清晰）

而"把一条记忆从项目 A 移到项目 B"——在 PG 上**直接 `UPDATE namespace` 列就行**，A 也能做。

> **结论修正：上了 PG 之后，你很可能永远不需要 C。** 除非确实要"多个项目共享同一条记忆"。

### 变化 4：连接数成为新的硬约束（必须现在处理）

| 事实 | 证据 |
|---|---|
| **每个 `Memory` 实例 = 1 条 PG 连接，没有池** | [postgres.py](octop-memory/src/octop_memory/storage/backends/postgres.py:119) `self._conn = self._connect()` |
| `Memory` **没有 `close()`** | 只能通过 [core.py](octop-memory/src/octop_memory/core.py:116) `memory.backend.close()`（[postgres.py](octop-memory/src/octop_memory/storage/backends/postgres.py:132)） |
| Octop 现有 LRU **淘汰时不 close** | [memory_client.py](Octop-develop/src/octop/api/common/memory_client.py:90) 只 `popitem` + 日志 → **软泄漏，靠 GC 兜底** |
| 每次构造都跑一遍 `_init_schema()` | [postgres.py](octop-memory/src/octop_memory/storage/backends/postgres.py:127)（幂等但非零开销） |

→ 项目一多，PG `max_connections`（默认 100）会被打爆。**项目记忆的连接缓存必须显式 `close()` + 设上限 + 容量告警。**

### 附带发现：一个已知的关闭崩溃风险

Octop 自己在 [manager.py](Octop-develop/src/octop/infra/agents/manager.py:934) `_quiesce_octop_memory()` 的 docstring 里记下了这个坑：

> *"``octop-memory`` runs lifecycle GC on a daemon thread. Closing the store while ``list_candidates`` is in flight **segfaults** (Linux live CI and Windows unit tests with a real HarnessAgentManager)."*

**但有个好消息**：后台 GC 线程是 **`MemoryMiddleware`（harness 侧）** 启动的，[service.py](octop-memory/src/octop_memory/service.py) 本身**不启任何线程**（无 `Thread` / `daemon` / `start()`）。

→ 如果项目记忆走**轻量门面**（`Memory` + `MemoryService`，不挂 `MemoryMiddleware`），就**没有后台线程、没有这个 segfault 风险**。代价是没有自动抽取/维护，需显式调 `capture_turn()` / `extract()`（用 cron 触发即可，Octop 已有 `cron_jobs`）。

---

## C2. PG 决策后的落地清单（五件事）

| # | 事项 | 要点 |
|---|---|---|
| 1 | **固定命名** `project_{project_id}`，`projects` 表加 `memory_namespace` 列 | 改名 / 审计 / 将来 C 的回填锚点 |
| 2 | **收敛 namespace 定义** | 全仓目前只有**两处**定义 `agent_` 前缀：[memory_backend.py](Octop-develop/src/octop/infra/agents/memory_backend.py:76) 与 [memory_client.py](Octop-develop/src/octop/api/common/memory_client.py:28)。项目记忆**不要再散落第三处**，统一到 `ProjectMemoryStore` 门面 |
| 3 | **连接池化** | 按 `project_id` 缓存 `Memory` 实例，**显式 `close()` + 上限 + 容量告警**；不要照抄现有 LRU（它不 close） |
| 4 | **轻量门面优先** | 项目记忆**不需要 LangGraph checkpointer**（那是对话状态，不是项目事实）。用 `Memory` + `MemoryService`，**不挂 `MemoryMiddleware`** → 无后台线程、无 segfault 风险、无 GC 开销 |
| 5 | **换授权模型** | dashboard 记忆 API 用 `require_agent_owner_row`（**owner-only**，[memory_client.py](Octop-develop/src/octop/api/common/memory_client.py:155)）→ **项目记忆不能复用**，必须换成项目成员校验 |

---

## C3. 万一将来真要 C，PG 上的迁移长什么样

```sql
-- 1) 加列（最安全，先不动 PK）
ALTER TABLE octop_memory.atoms ADD COLUMN project_id TEXT;
-- 2) 从 namespace 确定性反填（命名规则固定，无需启发式）
UPDATE octop_memory.atoms
   SET project_id = regexp_replace(namespace, '^project_', '')
 WHERE namespace LIKE 'project\_%';
-- 3) 建索引
CREATE INDEX idx_atoms_project ON octop_memory.atoms (project_id);
-- 4) 仅当需要「多项目共享一条记忆」时，才加多对多表
CREATE TABLE octop_memory.atom_projects (
  atom_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  PRIMARY KEY (atom_id, project_id)
);
```

对每张表（raw_events / candidates / atoms / entities / entity_pages / episodes / journal / memory_nodes …）重复步骤 1–3。

**全在 PG 上、一次性、可回滚**（先加列不动 PK 是最稳的路径）。而且**只有第 4 步是 A 真正做不到的**。

---

## C4. 一句话总结

> **PG 决策把 A→C 从「表重建工程」降级成「一次加列迁移」，甚至可能让 C 变得不必要。**
> 代价是把风险从「schema 迁移」转移到了「PG 连接管理」——而后者必须在写第一行项目记忆代码之前就设计好。

---

# 附录 D：决策「控制面也跑 PG」的边界核实

> 决策：控制面 PostgreSQL + 项目记忆 PostgreSQL（同一 DSN）。

## D1. 三个「白拿」

| # | 白拿的东西 | 证据 |
|---|---|---|
| 1 | **记忆自动复用控制面 DSN，零配置** | [memory_backend.py](Octop-develop/src/octop/infra/agents/memory_backend.py:33) `if octop_config.database.is_postgresql: return {"memory_backend": {"type":"postgres", "dsn": postgresql_conninfo()}}` |
| 2 | **备份白拿**：`octop backup` 用 `pg_dump -Fc --dbname <conninfo>`，**不带 `-n` 限定 schema** → 整库导出 → `octop_memory` schema 自动包含 | [system_archive.py](Octop-develop/src/octop/infra/backup/system_archive.py:260) → [pg_dump.py](Octop-develop/src/octop/infra/backup/pg_dump.py:31) |
| 3 | 新建项目 namespace **零 DDL** | 见附录 C1 变化 2 |

⚠️ 白拿 2 有部署前置条件：备份依赖外部 `pg_dump` 可执行文件（[pg_dump.py](Octop-develop/src/octop/infra/backup/pg_dump.py:29) `_require_tool("pg_dump")`）。**部署镜像里要有 PG 客户端工具**，否则 `octop backup` 会失败。

## D2. 两个「PG 下会失去的能力」

### 失去 1（**重要**）：`.hmpkg` 打包被硬拒 → 推翻本报告 §2.4 的「推子包」方案

[memory_portable.py](Octop-develop/src/octop/api/routers/memory_portable.py:47) `_refuse_postgres_portable()`：PG 后端下 pack / adopt / doctor **全部抛 HTTP 501**。官方在 docstring 里给了替代答案：

> *"The supported way to give another host access is to **point it at the same DSN and namespace**, where the memory is simply **shared rather than migrated**."*

**这直接作废了 §2.4 表格里「推子包（冷启动）」那一行。** 更新后的设计：

| 场景 | PG 下的正确做法 |
|---|---|
| 交付团队 ↔ 开发团队**在同一项目内** | **不需要"发送"这个动作**——两者本来就该读写同一个 `project_{id}` namespace，**天然共享** |
| 给**项目外**的团队冷启动上下文 | 只能走**推文本**（recall 渲染进派工消息） |
| 真要按条导出 | 自研（octop-memory 无此能力） |

> 其实这比原方案**更贴合你的思路**：你原话是"交付团队把部分项目记忆发送给开发团队"。在 PG 架构下，这会自然演变成"**开发团队被拉进项目 → 直接读同一个项目 namespace**"——共享取代搬运，少一次序列化和一致性问题。

### 失去 2：memory_slim（记忆瘦身 / checkpoint 压缩）在 PG 上不可用

[memory_slim.py](Octop-develop/src/octop/infra/agents/memory_slim.py:73) `_require_memory()` 明确拒绝：`isinstance(memory.backend, SqliteMemoryBackend)` 不成立 → 若为 `PostgresMemoryBackend` 抛 `memory_slim.postgres_unsupported`。它同时依赖 `SqliteMemoryBackend` + `CompactSqliteSaver`，两者都是 SQLite 专用。

**影响评估：对「项目事实记忆」影响有限。**

- 失去的是 **checkpoint 瘦身**（对话状态），而项目记忆**不挂 checkpointer**（见附录 C2 第 4 条）。
- 事实去重靠 promotion 的 `check_duplicate`（[checks.py](octop-memory/src/octop_memory/pipeline/promotion/checks.py:434)）—— 那是 pipeline 内逻辑，**与 backend 无关，PG 下照常工作**。
- 生命周期靠 octop-memory 自己的 GC（[gc.py](octop-memory/src/octop_memory/pipeline/lifecycle/gc.py:6)）—— 同样与 backend 无关。

## D3. 连接预算（现在就能算出来）

| 占用方 | 连接数 | 证据 |
|---|---|---|
| 控制面连接池 | `max_size=8`（默认） | [pool.py](Octop-develop/src/octop/infra/db/pool.py:154) `PostgresPool(conninfo, *, min_size=1, max_size=8)` |
| 每个 agent 记忆实例 | 1 条**裸连接，无池** | [postgres.py](octop-memory/src/octop_memory/storage/backends/postgres.py:119) |
| 每个项目记忆实例 | 1 条**裸连接，无池** | 同上（项目记忆复用同一后端实现） |

**总连接 ≈ `8 + N_agents + N_projects + 其他客户端`。**

→ 「每 agent 一个 Memory」已经存在；项目记忆会**再叠一层**。必须现在就定：
1. PG 侧 `max_connections` 调到多大；
2. Memory 实例缓存的**硬上限**是多少；
3. 超限时是**淘汰并 close**，还是**排队/拒绝**（宁可拒绝也不要静默泄漏）。

## D4. ⚠️ 一个必须澄清的前置问题

**控制面是「已经跑在 PG」，还是「打算从 SQLite 迁过去」？** 这两者工作量差别巨大。

我核实了 Octop 的数据库切换能力：

| 事实 | 证据 |
|---|---|
| 热切换**只在 `user_count == 0` 时允许** | [rebind.py](Octop-develop/src/octop/infra/db/rebind.py:102) `rebind_control_plane()` |
| 已有用户的库直接拒绝 | [rebind.py](Octop-develop/src/octop/infra/db/rebind.py:110) 抛 `SETUP_REQUIRED`「cannot change database after setup has users」(410) |
| 目标库必须为空（greenfield） | [rebind.py](Octop-develop/src/octop/infra/db/rebind.py:82) `assert_control_plane_database_empty()` → `DATABASE_NOT_EMPTY` (409) |
| 备份恢复是**方言匹配**的 | [system_archive.py](Octop-develop/src/octop/infra/backup/system_archive.py:522) `restore_postgres()` 只接受 `pg_dump -Fc` 产物 |

> **结论：Octop 没有内置的 SQLite → PostgreSQL 控制面数据迁移工具。**

- **若已跑在 PG** → 一切顺利，按附录 C2 清单开工即可。
- **若要迁** → 这是一个**独立的中等工程**（需自写跨方言数据搬迁），且**项目记忆应当等控制面迁完再上**，否则后端解析路径要写两遍。

> ✅ **已确认：控制面已在 PostgreSQL 上运行。** 无需迁移，按附录 E 开工。

---

# 附录 E：决策全部锁定后的最终实施方案

## E1. 决策台账

| # | 决策项 | 结论 | 对方案的影响 |
|---|---|---|---|
| 1 | 实施路线 | Fork Octop，**基于 `develop` 分支** | 四个运行时全部开源可改（`main` 上做不到） |
| 2 | 项目记忆档位 | **A**（项目 = 一个 namespace） | 复用 octop-memory 全部能力；C 大概率永不必要 |
| 3 | 项目记忆存储 | **PostgreSQL**（与控制面同 DSN） | 零 DDL、备份白拿；`.hmpkg` 不可用 |
| 4 | 控制面数据库 | **已在 PostgreSQL** | 无迁移工程 |
| 5 | 跨团队协作 | **项目内成员都能互动**（不限团队创建者） | 需 1 个 harness 补丁 + 2 处 Octop 放权 |
| 6 | 团队工具 | 知识库 1 行放开；连接器 / ACP 走「项目房间 host」角色 | 保护现有三层防失控边界 |

## E2. 最终架构

```
┌─ Octop 控制面（PostgreSQL，schema=public）────────────────────────┐
│  projects / project_members / project_tasks / project_comments    │
│  project_rooms / project_room_members / requirement_nodes          │
│  artifacts / timeline_events        ← 迁移 018（新增，纯加表）      │
│  projects.memory_namespace = "project_{project_id}"  ← 关键映射    │
└───────────────────────────────────────────────────────────────────┘
                              │ 同一 DSN
┌─ octop_memory schema（共享固定表，namespace 列隔离）──────────────┐
│  namespace = "project_{project_id}"  → 项目记忆（档位 A）          │
│  namespace = "agent_{agent_id}"      → 既有 per-agent 记忆         │
│  真源：atoms / entities / entity_pages / episodes / journal        │
│  能力：FTS5→tsvector 召回、promotion、supersede、GC（全部复用）     │
└───────────────────────────────────────────────────────────────────┘
                              │
┌─ octop-harness（fork，1 个补丁）──────────────────────────────────┐
│  teams/team_manager.py: + bind_peer_scope()   ← 项目级可见性       │
│  bind_peer_session(prepare=...)  ← 项目记忆注入（已有，不改）      │
└───────────────────────────────────────────────────────────────────┘
```

## E3. 数据模型（迁移 018 定稿建议）

沿用 Octop 资源表约定：**整数 `id` 主键 + 对外字符串 id UNIQUE**，子表 FK 到字符串 id（不要 FK 整数 id）。

```sql
projects            (id, project_id TEXT UNIQUE, name, goal, status,
                     owner_user_id, memory_namespace, kb_id,
                     start_at, due_at, created_at, updated_at)
project_members     (id, project_id, subject_type(user|agent|team), subject_id,
                     role(owner|admin|member|viewer), created_at)
project_tasks       (id, task_id TEXT UNIQUE, project_id, parent_id, title, desc,
                     status(todo|doing|review|done|blocked|cancelled),
                     assignee_type(user|agent|team), assignee_id, priority,
                     deps, thread_id, origin_node_id, due_at, sort_order, created_by)
project_comments    (id, comment_id TEXT UNIQUE, project_id, task_id, thread_id,
                     author_type(user|agent|system), author_id, body,
                     source(dashboard|im|agent), node_type(none|business|requirement),
                     created_at, updated_at)
node_mark_logs      (id, comment_id, from_type, to_type, actor, at)
requirement_nodes   (id, node_id TEXT UNIQUE, project_id, comment_id, type, status,
                     title, summary, split_task_ids, proposed_by, proposed_at,
                     confirmed_by, confirmed_at, rejected_reason)
project_rooms       (id, room_id TEXT UNIQUE, project_id, thread_id,
                     host_agent_id, status)              ← 跨团队房间
project_room_members(id, room_id, subject_type, subject_id, joined_at)
artifacts           (id, artifact_id TEXT UNIQUE, project_id, task_id,
                     kind(doc|prd|code|context), name, uri,
                     kb_document_id, commit_ref, version, hash, created_by)
timeline_events     (id, project_id, task_id, actor, action, payload, at)
```

**项目记忆不建表** —— 真源是 `octop_memory` schema 里的 `atoms` / `entities` 等；`projects.memory_namespace` 只做映射。

**AC-11 的「注入版本 +1」**：用 namespace 内 `MAX(atoms.created_at)`，或往 `{ns}_meta` 写一个自增 `inject_version`（[set_meta](octop-memory/src/octop_memory/core.py:1022) 已存在）。

## E4. 跨团队可见性：唯一需要改 harness 的地方

```python
# octop-harness/src/octop_harness/teams/team_manager.py（约 15 行）
PrepareScope = Callable[[str], set[str] | None]

def bind_peer_scope(self, scope: PrepareScope | None) -> None:
    """Return the caller's allowed peer agent_ids, or None to keep the user_id rule.

    Hosts that model project membership (e.g. Octop) bind this so peers are
    resolved by project roster instead of agent ownership.
    """
    self._peer_scope = scope
```

在 [`list_peers`](octop-harness/src/octop_harness/teams/team_manager.py:175) 的用户过滤之后、`team_peers` 白名单之前插入：

```python
scope = self._peer_scope(from_agent_id_or_caller) if self._peer_scope else None
if scope is not None:
    peers = [e for e in peers if e.agent_id in scope]   # 替换而非叠加
```

Octop 侧实现为「查 `project_members` 里该项目所有 agent 主体」。

## E5. 实施顺序（每步独立可验收）

| 阶段 | 内容 | 验收 |
|---|---|---|
| **P0** | 018 迁移 + repo 层 + `projects` 权限键 + 空壳路由；harness `bind_peer_scope` 补丁 | `make all` 绿；7 处 `assert v == 17` 改为 18；新路由挂载成功 |
| **P1** | 项目 / 成员 / 任务 CRUD + 看板页 + i18n 双语 | AC-01 / AC-02 / AC-13 / AC-16 |
| **P2** | `ProjectMemoryStore` 门面 + `project_{id}` namespace + `bind_peer_session` 派工注入 | AC-09 / AC-11 |
| **P3** | 评论 + 打标 + 需求节点池 + **Owner 确认闸门接 HITL** | AC-05 / AC-06 / AC-07 / AC-15 |
| **P4** | 跨团队房间（`project_rooms` + `project_room_members` + peer scope） | 新增用例：跨用户专家可互调 |
| **P5** | 工具放开：`search_knowledge` 进白名单（1 行）+「项目房间 host」角色白名单 | host 能查项目 KB；原 host 规则不变 |
| **P6** | ACP 派单 + commit 回写（自研）+ 资料归档 | AC-10 / AC-14 |

## E6. 连接预算（按你的实际规模校准）

按需求文档口径：1 名 Owner + 少量同事 + 约 30 个专家。

| 占用方 | 数量 |
|---|---|
| 控制面连接池 | 8 |
| 已启动 agent 的 Memory | ≈ 已启动 agent 数（惰性启动，非全部 30） |
| 项目 Memory | ≈ 活跃项目数 |

**合计约 40–50 条，远低于 PG 默认 `max_connections=100`。** 所以**这不是当前瓶颈**。

真正要防的是**写法退化**：

- ❌ 每次 recall 都 `Memory(...)` → 连接爆炸
- ✅ 按 `project_id` 缓存的 `Memory` 实例池，**硬上限 + 淘汰时显式 `memory.backend.close()` + 超限告警**

（提醒：Octop 现有的 [memory_client.py](Octop-develop/src/octop/api/common/memory_client.py:90) LRU 淘汰时**不 close**，不要照抄。）

---

# 附录 F：对话列表改造（分类 / 隐藏未使用 / 标签）

## F1. 现状核实

| 事实 | 证据 |
|---|---|
| 侧栏**不是会话列表，是「按 agent 分组的卡片列表」** | [SessionList.tsx](Octop-develop/dashboard/src/pages/Chat/components/SessionList.tsx:511)：`agents` 每个渲染一张 `AgentCard`（:214），下面挂该 agent 的 sessions |
| 只加载**当前 agent** 的会话 | [useSessions.ts](Octop-develop/dashboard/src/pages/Chat/hooks/useSessions.ts:351) 单 agent store（`_storeAgentId` / `syncStoreToAgent`） |
| 线程 API 是**按 agent** 的 | [octopThreads.ts](Octop-develop/dashboard/src/api/modules/octopThreads.ts:153) `GET /agents/{agentId}/threads` |
| **隐藏机制已存在，但只对「共享专家」生效** | [useHiddenSharedExperts.ts](Octop-develop/dashboard/src/pages/Chat/hooks/useHiddenSharedExperts.ts:18) docstring 原文：*"**Owned experts are never treated as hideable via this hook**"*；`filterVisible` 里 [:56](Octop-develop/dashboard/src/pages/Chat/hooks/useHiddenSharedExperts.ts:56) `if (!isSharedExpertViewer(agent)) return true;` |
| **已有群聊标签** | [TeamChatBadge.tsx](Octop-develop/dashboard/src/pages/Chat/components/TeamChatBadge.tsx:12)（`isTeamAgent(agent)` → "群聊"徽标） |
| **已有 IM 渠道图标** | [SessionChannelIcon.tsx](Octop-develop/dashboard/src/pages/Chat/components/SessionChannelIcon.tsx) |
| **已有置顶 + 产出物数据** | `Session.pinned`、`Session.artifacts`（[useSessions.ts](Octop-develop/dashboard/src/pages/Chat/hooks/useSessions.ts:70)） |
| **已有"活跃度"判定** | [useSessions.ts](Octop-develop/dashboard/src/pages/Chat/hooks/useSessions.ts:53)：`hasActivity = has_messages \|\| title \|\| last_active > 0` |
| **两套侧栏并存** | [ChatSidebarPanel.tsx](Octop-develop/dashboard/src/pages/Chat/components/ChatSidebarPanel.tsx:89) 由 `navEmbedded` 切换；[index.tsx](Octop-develop/dashboard/src/pages/Chat/index.tsx:1137) `navEmbedded={isMinimalLayout}` |

### 🎯 你抱怨的根源找到了

[useHiddenSharedExperts.ts](Octop-develop/dashboard/src/pages/Chat/hooks/useHiddenSharedExperts.ts:18) 的 docstring 写得很明确：

> *"Per-user localStorage preference for hiding shared experts from chat lists. **Owned experts are never treated as hideable via this hook.**"*

**即：你自己拥有的专家，一个都藏不掉。** 30 个自建专家只能全部堆在列表里。

### ⚠️ 顺带发现一个真实性能问题

[MinimalAgentSessionNav.tsx](Octop-develop/dashboard/src/pages/Chat/components/MinimalAgentSessionNav.tsx:359) 为**每个专家**发一次请求来拉预览会话：

```tsx
const entries = await Promise.all(
  agentKey.split(",").map(async (id) => {
    const rows = await octopThreadsApi.list(id, MINIMAL_AGENT_SESSION_PREVIEW);
    ...
```

**30 个专家 = 30 次并发请求**，每次进聊天页都发。这是本次改造必须一并解决的。

**好消息**：这个组件**已经知道**哪些专家零会话（`byAgent[id].length === 0`，[:344](Octop-develop/dashboard/src/pages/Chat/components/MinimalAgentSessionNav.tsx:344)），且已渲染空状态（`:585-593`）。所以「自动隐藏未使用」的判定数据**已经在手上了**。

## F2. 需求拆解：一个后端改动 + 三处前端改动

### 需求 ①：分类（有项目 / 无项目）

**不需要给 `threads` 表加列** —— 靠反查即可，保持「只加不改」纪律：

| 会话类型 | 反查来源 |
|---|---|
| 项目房间会话 | `project_rooms.thread_id` → `project_id` |
| 任务讨论线 | `project_tasks.thread_id` → `project_id` |

### 需求 ②：隐藏「没用过的专家」

两个关键设计判断：

**(a) 判定用 `hasActivity`，不要用「存在 thread」**

`Session.hasActivity`（[useSessions.ts:53](Octop-develop/dashboard/src/pages/Chat/hooks/useSessions.ts:53)）已经区分了"点进去自动建的空 thread"和"真有对话"。用后者 —— 否则误点一下就"被用过"了，隐藏永远不生效。

**(b) 建议「折叠」而不是「真隐藏」**

| 方案 | 问题 |
|---|---|
| 真隐藏 | 专家彻底找不到，团队这种需要主动发现的场景很受伤；下次想用得去设置里翻 |
| **默认折叠的分组** ✅ | 清爽 + 可发现，改动也更小 |

建议：`📦 未使用 (28) ▸` 固定在最后，**搜索命中时自动展开**；同时把现有 `hiddenExpertsPrefs` 保留为**手动永久隐藏**，并把 `canHide` 从「仅共享专家」放开到「全部专家」。

### 需求 ③：标签体系（我建议分两层，不要平铺）

**不要用一堆平级标签**（会变成噪音）。建议 **「1 个类型 + 若干状态点」**：

**类型标签（互斥，决定分组归属）**

| 类型 | 判定 | 现状 |
|---|---|---|
| 项目会话 | thread 关联了 project | 需新增 |
| 群聊 | `isTeamAgent(agent)` 或项目房间 | **已有** `TeamChatBadge` |
| 单会话 | 其余 1:1 | **建议不渲染标签** —— 默认态渲染了反而是噪音，只在"非默认"时显示 |

**状态徽标（可叠加，用小图标，不占文字位）**

| 徽标 | 判定 | 现状 |
|---|---|---|
| 📌 置顶 | `pinned` | **已有** |
| 💬 IM 来源 | `channel_type !== "dashboard"` | **已有** `SessionChannelIcon` |
| 📎 有产出 | `artifacts.length > 0` | **已有** |
| ⏳ 待我处理 | 有未决 HITL | 数据已有，需接线 |
| 🔴 未读 | —— | **当前无 read 状态，建议本期不做**（要新表） |

### 建议的分组结构（三段式，不是两段）

```
📌 置顶
   ├ 项目A · 需求评审          [项目会话]
   └ 数据分析专家              （单会话，无标签）

📁 项目
   ├ 项目A  ▸ (12)
   │    ├ 交付团队群聊          [群聊]
   │    └ T-102 接口联调        [群聊]  ← 任务讨论线
   └ 项目B  ▸ (5)

💬 其他会话
   ├ 交付团队  ▸ (8)           [群聊]
   └ 开发专家  ▸ (3)

📦 未使用 (28)  ▸              ← 默认折叠
```

**为什么加「置顶」一段**：置顶功能已存在，用户置顶了却混在项目/非项目分组里会找不到。

**排序建议**：项目分组按 `last_active` 倒序；「未使用」组固定最后。

**附带收益**：折叠组的计数（`未使用 (28)`）顺便回答了"我这些专家是不是白建了"。

## F3. 后端：新增一个跨 agent 会话端点（唯一后端改动）

它一次解决三个问题：消除 N 次请求、提供 project 维度、提供"哪些专家有会话"。

```
GET /api/threads?scope=all&limit=200
→ { threads: [
     { thread_id, agent_id, agent_name, agent_kind(team|expert),
       title, pinned, channel_type, last_active, created_at,
       has_messages, artifact_count, hitl_pending,
       project_id?, project_name?, task_id?, task_title?,
       session_kind: "project" | "group" | "direct" }
   ], truncated: bool }
```

**约束**：

- **不要动现有 `GET /agents/{agent_id}/threads`** —— 前端多处 + 430 个测试依赖。新端点纯新增。
- **权限**：不能用 `require_permission("projects")`（这是聊天侧栏，所有能聊天的人都要用），走 JWT + 可见 agent 集合过滤。

### ⚠️ 一处必须保持一致的地方

如果按附录 B2 放开了跨团队可见性，而会话列表仍按旧规则过滤，就会出现**「能调但看不到」或「看得到但调不了」**的不一致。

**建议抽一个共享的 `visible_agent_ids(user)` 服务函数**，让这三处都用它：

1. harness 的 `bind_peer_scope` 钩子（附录 E4）
2. 新的跨 agent 会话端点
3. 团队组队时的 `_user_may_use_member` 判定（附录 B2 ①）

否则权限语义会随三处实现漂移。

## F4. 工作量与建议顺序

| 部分 | 内容 | 成本 |
|---|---|---|
| 后端 | 1 个新端点 + 1 个 repo 查询（含 `project_rooms` / `project_tasks` 反查）+ 1 个共享 `visible_agent_ids` | 小 |
| 前端 | `SessionList.tsx`（full 模式）+ `MinimalAgentSessionNav.tsx`（minimal 模式）**两套都要改** | **中（主要工作量）** |
| 数据模型 | **不需要改 `threads` 表** | 0 |
| i18n | 新增分组名 / 标签名，zh + en 双语（前后端键都要对齐） | 小 |

**两套侧栏并存是主要工作量点。** 由 [`isMinimalLayout`](Octop-develop/dashboard/src/pages/Chat/index.tsx:1137) 决定用哪套 —— **建议先确认你日常用的是哪套，先改一套上线，另一套后续跟进**，避免一次性改两套拉长周期。

**依赖关系**：本改造的「项目分组 + 项目会话标签」依赖 `project_rooms` / `project_tasks` 存在 → **排在 P1 之后**。但「隐藏未使用专家」和「群聊/单会话标签」**不依赖项目域**，可以立即做（改动集中在一个 hook + 两个组件）。
