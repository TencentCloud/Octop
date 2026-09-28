# Octop 项目管理改造 —— 总计划与落地开发计划

> **本文档是唯一执行依据。** 替代此前所有分散分析。
> **版本 v2.1** —— v2.0 已按《Octop-计划审查报告》闭合 3 blocker + 8 high + 12 medium + 关键 low；v2.1 再按复核报告 V1/V2 闭合 6 条新不一致 + 4 条部分成立。
> 修订对照见 **附录 E-1 / E-2**。复核结论：**无常驻 blocker，有条件可开工**（前置条件见 §6.1）。

---

# 第一部分：总计划

## 0. 一页纸总览

| 项 | 结论 |
|---|---|
| **目标** | 在 Octop 上新增原生「项目管理」能力：立项 → 拆任务 → 派单 → 讨论 → 需求节点 → Owner 拍板 → 归档 |
| **实施路线** | Fork Octop，**基于 `develop` 分支** |
| **里程碑 M1** | **14.5–16 天**（1 人全职）→ 交付可用的项目管理系统 |
| **里程碑 M2** | 约 14 天 → 项目记忆 + 跨用户协作 + 方案评审闸门 + commit 回写 |
| **最大风险** | 上游 `infra/agents` 正在重构（2026-09-25 起）→ M2 需等其稳定 |
| **最大纪律** | 只加不改；新代码进新文件；每月 rebase 一次 |

> ⚠️ **工期口径（v2.1 收口）**：v1.0 标称 M1=12 天；v2.0 改为 13.5–15 天但**阶段小计与任务卡不符**（复核发现）。
> v2.1 起以**任务卡实加值**为准：**S1=3 + S2=7 + S2.5=4.5 = 14.5 天**，含 rebase/联调缓冲报 **14.5–16 天**。
> 每次改动任务卡预估时，**必须同步改本节与 §2.1 / §3 三处**。

---

## 1. 决策台账（6 项，已全部锁定）

| # | 决策项 | 结论 | 影响 |
|---|---|---|---|
| D1 | 实施路线 | Fork Octop，**基于 `develop`** | 四个运行时全部开源可改；`main` 依赖闭源包，改不动 |
| D2 | 项目记忆档位 | **A**（项目 = 一个 namespace） | 复用 octop-memory 全部能力 |
| D3 | 项目记忆存储 | **PostgreSQL**（与控制面同 DSN） | 零 DDL、备份白拿；`.hmpkg` 不可用 |
| D4 | 控制面数据库 | **已在 PostgreSQL** | 无迁移工程 |
| D5 | 跨团队协作 | **项目内成员都能互动**（不限团队创建者） | 需 1 个 harness 补丁 + 3 处 Octop 放权（M2） |
| D6 | 团队工具 | 知识库 1 行放开；连接器 / ACP 走「项目房间 host」角色 | 保护现有三层防失控边界（M2） |

> **注**：本计划决策编号 D1–D6 为**本计划内部编号**，与需求文档 §〇 的 D1–D4 不是同一套编号体系。需求 D1=使用者范围、D2=实施路线、D3=需求节点确认权、D4=开发的含义。

---

## 2. 范围界定

### 2.1 M1 做（14.5–16 天）

| ✅ | 对应需求 |
|---|---|
| 立项 / 编辑 / 归档（含 **Project 状态机流转校验**） | M1 |
| 成员与角色 + **权限矩阵**（owner/admin/member/viewer 逐接口校验） | M2 |
| **项目 KB 生命周期**（立项自动建 KB + 回写 `kb_id`） | M3、M14 前置 |
| 任务分解（父子 / 依赖 / 优先级 / 指派 / 状态机） | M4 |
| 任务看板（状态列 + 拖拽 + 过滤） | M5 |
| 任务讨论线（**双层模型**，见 §4.3） | M6 |
| 评论与留痕 | M7 |
| 评论打标（business / requirement，可撤销留痕） | M8 |
| 需求节点池（6 态状态机） | M9 |
| Leader 拆解草案（**Leader = 普通专家**，见 §4.4） | M10 |
| **Owner 确认闸门（走 `ask_user_question`，见 §4.5）** | M11 |
| 派单给专家/团队（同用户，现成能力） | M12 |
| 资料归档（写项目 KB + `project_artifacts` 回链） | M14 |
| **全过程留痕 / 时间线回放**（状态、派工、产出、评论） | **M16** |
| 会话列表项目分组 + 「项目会话」标签 | 新增需求 |
| 聊天列表分类 / 隐藏未使用 / 群聊标签 | 新增需求 |

### 2.2 M1 明确不做（**逐条声明，不留悬空**）

| ❌ 不做项 | 类型 | 说明 |
|---|---|---|
| 项目记忆 | 后置 M2 S3 | 要改 `infra/agents/memory_backend.py`，上游高 churn |
| 跨**用户**协作 | 后置 M2 S4 | 要改 harness + `infra/agents/manager.py` |
| ACP 派单 + commit 回写 | 后置 M2 S5 | 上游 `thread_artifact` 区域快速迭代 |
| **AC-09 的「项目记忆条目」部分** | **显式裁剪** | M1 派工消息只带任务标题/描述/验收标准，不带记忆条目（记忆在 M2） |
| **AC-12 的「记忆变更」事件** | **显式裁剪** | M1 时间线记录状态/派工/产出/评论，记忆变更事件在 M2 |
| **S4 IM 群讨论回流（仅入站）** | **决策：不做** | 指「IM 群消息 → 项目评论入库」，octop-gateway 无建群/拉人 API。**出站不受影响**：审批卡片推到已绑定的 IM 会话走既有 channel 能力，M1 可用（见 §4.5） |
| **M3 后半句「项目 KB 成员授权」** | **后置 M2 S4** | `knowledge_base_members` 表已在 v7 被 DROP，需重建成员模型；M1 只做「立项自动建 KB + 绑定」 |
| S1 需求节点去重/合并 | 后置 | Should 级，M1 用人工合并 |
| S2 看板统计 | 后置 | Should 级 |
| S3 超期催办 | 后置 | Should 级，可复用 cron |
| S5 项目模板 | 后置 | Should 级 |
| C1 PRD 自动草稿 / C3 跨项目记忆复用 / C4 客户只读门户 | 后置 | Could 级 |
| 甘特图 / 工时 / 多项目组合 / 移动端 / SaaS 多租户 | 非目标 | 需求 §1.3 |

### 2.3 遗留问题裁决（回答需求 §九 Q5–Q10）

| 问题 | 裁决 | 理由 |
|---|---|---|
| Q5 资料库归属 | **一期只写 Octop KB**；WeKnora 只读，写入二期直连其 API | 连接器适配器第一行 docstring 即 "Read-only" |
| Q6 讨论来源 | **只 Dashboard**；IM 回流不做（见 §2.2） | octop-gateway 缺建群/拉人能力 |
| **Q7 专家资产** | **用现有专家库**；M1 不做「项目专属专家」。项目成员表直接引用 `agent_id`，跨项目复用即「同一专家加入多个项目」 | 避免新增专家类型；`agents` 表 `UNIQUE(user_id, name)` 已够用 |
| Q8 记忆读者 | **两者都要**：AI 做上下文注入（M2 S3），真人有「项目知识页」（M2 S3 前端） | 用户故事 20/21 要求 |
| Q9 多项目并行 | **M1 即支持**（`projects` 表天然多行 + 成员表隔离）；跨项目复用需求节点**不做** | 无额外成本 |
| **Q10 节点粒度** | **一个节点 = 一条需求**；子需求拆成 `project_tasks`（`requirement_nodes.split_task_ids`） | 与 `Task.parent_id` 父子层级配套，避免节点内再套节点 |

---

## 3. 里程碑与工期

```
M1「项目管理可用」  14.5 天（含缓冲报 14.5–16 天；S0 可并行 +2.5 天）
├─ S1   项目域地基                          3 天    （T1.1–T1.5 之和）
├─ S2   项目/成员/任务/看板                  7 天    （T2.1–T2.6 之和）
└─ S2.5 讨论/打标/需求节点/Owner闸门/归档     4.5 天  （T3.1–T3.5 之和）

M2「记忆与跨团队」  约 14 天（等上游 infra/agents 重构稳定）
├─ S3   项目记忆（档位 A + PG）              4.5 天
├─ S4   跨团队房间 + 工具放开                5 天
└─ S5   方案评审闸门 + ACP 派单 + commit 回写  4.5 天
```

**并行建议**：S0（聊天列表改造）与 S1 无依赖，可两人并行或一人交替。

---

## 4. 架构总览

```
┌─ Octop 控制面（PostgreSQL，public schema）─────────────────────────┐
│  M1 新增（迁移 019）：                                             │
│    projects / project_members / project_tasks / project_comments   │
│    node_mark_logs / requirement_nodes / project_rooms              │
│    project_room_members / project_artifacts / timeline_events      │
│  projects.kb_id       ← 立项时自动创建并回写（T2.1）                │
│  projects.memory_namespace = "project_{project_id}"  ← M2 用       │
└────────────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┴─────────────────────┐
        │ M1 复用（零改造）                          │ M2 新增
        ▼                                          ▼
┌──────────────────────────┐        ┌──────────────────────────────┐
│ threads / thread_messages│        │ octop_memory schema          │
│ ask_user_question（审批） │        │  namespace=project_{id}      │
│ ask_agent + 团队 room    │        │  ProjectMemoryStore 门面     │
│ KB（owner + shared）     │        │  + source_refs 映射层         │
│ threads.artifacts（上游） │        └──────────────────────────────┘
└──────────────────────────┘
```

### 4.1 关键设计约束

| # | 约束 | 理由 |
|---|---|---|
| 1 | **不改 `threads` 表** | 项目关联靠 `project_rooms` / `project_tasks` 反查 |
| 2 | **不动 `GET /agents/{agent_id}/threads`** | 430+ 测试与多处前端依赖；新端点纯新增 |
| 3 | 讨论线用**双层模型**（见 §4.3） | 不新建评论系统 |
| 4 | 产物复用上游 `thread_artifacts` | 不重新扫描工作区 |
| 5 | **Owner 闸门走 `ask_user_question`（不是裸 HITL）** | 见 §4.5 —— HITL 语义是「工具调用审批」 |

### 4.2 数据库与时间戳约定

| 项 | 约定 | 依据 |
|---|---|---|
| **PG 时间戳类型** | 与仓库既有约定一致：**`INTEGER NOT NULL`**（不用 BIGINT） | `001_initial.pg.sql` 的 `created_at` 均为 INTEGER |
| **PG 主键** | `INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY` | 既有 .pg.sql 写法 |
| 资源表 id | 整数 `id` PK + 对外字符串 `{entity}_id` UNIQUE；子表 FK **字符串 id** | AGENTS.md §7 |
| 时间戳语义 | Unix 秒（INTEGER / SQLite INTEGER） | 与既有表一致 |

### 4.3 讨论线双层模型（**必须显式理解，勿误读**）

`threads` 表结构是 **`agent_id NOT NULL`（一个 thread 只属于一个 agent）**，因此**不能**用一条 thread 装下多参加者的讨论线。正确模型：

```text
project_tasks.thread_id  ──►  一个 agent thread：任务主要执行者与 Owner 的对话流（thread_messages）
                              ＋
project_comments         ──►  结构化评论层：承载打标、来源、多参加者发言、节点关联
                              （.thread_id 可选外键指回对话流）
```

**含义**：
- 「任务讨论线」= 对话流（单 agent thread）+ 结构化评论层（`project_comments`）
- 多参加者（除 assignee 外的项目成员）的发言**落 `project_comments`**，需要 AI 参与时另开该 agent 的 thread
- 每个任务的 `thread_id` 指向该任务的**主执行 agent** 的对话流

### 4.4 Leader 拆解草案机制（M10）

| 项 | 设计 | 依据 |
|---|---|---|
| **Leader 身份** | **普通专家**（不是 team host） | 需求 §二 硬约束：team host 工具白名单仅 5 个，无法落库草案 |
| 草案产出 | Leader 专家在需求节点的讨论线里产出草案（子任务 + 建议负责人 + **验收标准**） | |
| **验收标准字段落点** | 暂存 `project_tasks.description` 的固定小节（`## 验收标准`）；**不新增列**（避免schema膨胀） | 报告 M2 建议 |
| 落库路径 | 草案写 `project_comments`（`node_type='requirement'` 关联节点）+ `requirement_nodes.summary` | |
| Owner 采用 | 走 §4.5 的 `ask_user_question` 闸门 → 确认后按草案生成 `project_tasks` | |

### 4.5 Owner 确认闸门：走 `ask_user_question`，不是裸 HITL

> ⚠️ **审查报告 H2 修正**：HITL 的语义是「**工具执行前**的人工审批」，决策对象是工具调用（approve/edit/reject/respond），**承载不了「确认一份需求节点草案」这种跨 turn 的业务审批**。
>
> 🔧 **v2.1 修正（技术复核 V2）**：原文写的「配 `allowed_decisions=["respond"]`」是错的 —— 该值**在 harness 里硬编码，不是配置项**。

| 用 | 不用 |
|---|---|
| ✅ **`ask_user_question`**（`builtin/tools/ask_user.py`）：模块 docstring 明确它是「real implementation is the human」的合作通道 | ❌ 裸 `HitlPolicy(approve/reject)` 模拟业务审批 |

**机制事实（源码核实，[`agent.py:1359-1384`](octop-harness/src/octop_harness/agent.py:1359)）**

```python
def _ask_user_active(self) -> bool:
    return bool(cfg.ask_user_enabled) and ASK_USER_TOOL_NAME not in cfg.tools_disabled

def _resolve_interrupt_on(self):
    ...
    if self._ask_user_active():
        # ``respond`` only: the human answers *instead of* running the tool.
        interrupt_on[ASK_USER_TOOL_NAME] = {
            "allowed_decisions": ["respond"],          # ← 硬编码，无需也无法配置
            "description": "The agent is asking you to decide.",
        }
```

| 事实 | 含义 |
|---|---|
| `allowed_decisions=["respond"]` **硬编码** | **不需要配置项**。设计正好够用：Owner 只需「回答」，无需 approve/edit 工具 |
| 挂载条件 = `cfg.ask_user_enabled` 且 `ask_user_question` 不在 `tools_disabled` | **T3.3 必须确保项目相关 agent 满足这两个前置**，否则闸门静默失效 |
| docstring：*"Deliberately independent of `SecurityPolicy` … a collaboration channel, not an approval gate, so it must work with `hitl.enabled=False`"* | **不需要开 HITL**；项目宿主不得禁用 `ask_user_question` |

**接线（T3.3 负责）**

| 步骤 | 实现 |
|---|---|
| 1 | 需求节点转 `pending_confirm` 时，**向该项目的「确认会话」发起一轮 agent turn**（走 T2.5 同一套派发路径：`build_harness_request` + `agent_manager.stream`），让 agent 调用 `ask_user_question`（选项：采用 / 修改 / 驳回） |
| 2 | 前置校验：`cfg.ask_user_enabled == True` 且 `ask_user_question ∉ cfg.tools_disabled`；不满足则**立即报错**（不得静默降级） |
| 3 | IM 卡片：出站复用 [`hitl/format.py`](Octop-develop/src/octop/infra/gateway/hitl/format.py) 的 `format_ask_card` + `collect_ask_reply`，推到**已绑定该会话的 IM 渠道**（既有 channel 能力，非新增） |
| 4 | **回复落库机制（v2.1 补充）**：走既有 HITL resume 路径 —— `resume_hitl(thread_id, decisions)` 恢复被中断的 turn；**由 T3.3 在恢复点注册回调**，从 `decisions[].message` 解析「采用/修改/驳回」并写 `requirement_nodes.status` + `confirmed_by/confirmed_at` 或 `rejected_reason`；同一 `pending_id` 幂等去重 |
| 5 | 触发条件、超时（未回复如何处理）、多 Owner 场景由 T3.3 明确并写测试 |

**收益与边界（v2.1 澄清，消除与 §2.2 的表面矛盾）**

| 方向 | M1 是否做 |
|---|---|
| **出站**：审批卡片 → 已绑定的 IM 会话（飞书/企微群） | ✅ **做** —— 走既有 channel 绑定能力，无新增 |
| **入站**：IM 群消息 → 项目评论入库（§2.2 的 S4） | ❌ **不做** |

### 4.6 权限矩阵（**新增，闭合 H6**）

| 操作 | owner | admin | member | viewer |
|---|---|---|---|---|
| 查看项目/看板/任务/评论/资料 | ✅ | ✅ | ✅ | ✅（只读） |
| 创建/编辑任务 | ✅ | ✅ | ✅ | ❌ 403 |
| 改任务状态 | ✅ | ✅ | ✅ | ❌ 403 |
| 评论 / 打标 | ✅ | ✅ | ✅ | ❌ 403 |
| 确认/驳回需求节点 | ✅ | ✅ | ❌ 403 | ❌ 403 |
| 维护成员与角色 | ✅ | ✅ | ❌ 403 | ❌ 403 |
| **归档 / 删除项目** | ✅ | **❌ 403** | ❌ 403 | ❌ 403 |
| 非成员 | 一律 403（AC-13） | | | |

**实现**：`service` 层统一 `assert_project_role(project_id, user, required)`；测试覆盖 viewer 写操作 403 与 admin 归档 403。

**`projects` 权限键的 category 决策**：放 `category="settings"`（与 `knowledge_bases` 同级 → 进入 `BASELINE_PERMISSIONS`，新用户默认获得）。**这是有意的**：项目数据本身由 `project_members` join 保护，粗粒度键只控制「能否使用项目功能」。若日后判定项目数据敏感，改 `control`/`admin` 即可。

---

## 5. 工程纪律（13 条铁律）

| # | 铁律 | 违反后果 |
|---|---|---|
| 1 | **Ship bar = `make all` 绿**（`format-all + lint + mypy + pytest`）；前端另跑 `cd dashboard && npx tsc -b` | CI 红 |
| 2 | **迁移必须成对**：`018_x.sql` + `018_x.pg.sql`，末尾 `UPDATE _schema_version SET version = 19;` | SQLite/PG 行为分叉 |
| 3 | **迁移号断言共 16 处 / 8 个文件**，必须全部同步改（清单见附录 F） | **`make all` 必红** |
| 4 | **权限键三处同步**：后端 `PERMISSIONS` + 前端 `PERM`/`NAV_PERMISSIONS`/`pathPermissionKeys` + 测试 `GATED_FILES` | ACL 守卫静默漏检 |
| 5 | **i18n 双语键对齐**：`src/octop/i18n/{en,zh}.json` + `dashboard/src/locales/{en,zh}.json`；跑 `uv run pytest tests/unit/i18n -q` | 测试强制对齐 |
| 6 | **只加不改**：核心文件改动个位数行 | rebase 成本爆炸 |
| 7 | **i18n key 追加到文件末尾 + 独立命名空间**（`projects.*`） | 中间插入必冲突 |
| 8 | **不改 `threads` 表** | 破坏上游兼容 |
| 9 | **资源表 id 约定**：整数 `id` PK + 字符串 `{entity}_id` UNIQUE；子表 FK 字符串 id | 违反 AGENTS.md §7 |
| 10 | **前端只通过 `/api` HTTP 访问后端** | 不得 import Python |
| 11 | **不要照抄 `memory_client.py` 的 LRU**（淘汰时不 close） | PG 连接泄漏 |
| 12 | **交叉平台**：用 `tmp_path` / `Path`；POSIX 专用加 `skipif(os.name != "posix")`；**验收命令不得用 `rm -f /tmp`** | Windows CI 红 |
| 13 | **时区纪律**：用户可见时间必须用 `default_timezone` / `formatServerDateTime` / `formatMessageTime(..., timeZone)`；**禁裸 `toLocaleString()`** | 平台不合规（AGENTS.md §7） |

**附带硬禁（AGENTS.md §5/§8，纳入 code review 检查项）**

- 模块边界：`infra/` **不得** import `api/`、`cli/`、`launch.py`；`api/` 不得 import `cli/`；`infra/db/repos/` 不得 import 非 DB 的 `infra` 包
- **不得直接编辑 `src/octop/dashboard/`**（构建产物）—— 只改 `dashboard/`，然后 `make build-frontend`
- 新 API 路由必须有 `summary` + 类型化 `response_model`；改完 glance `/api/docs`
- `ErrorCode` 新增时同步后端 `errors.<CODE>` 与前端 `apiErrors.*` 两处

---

## 6. 开工前准备（第一天上午）

### 6.1 环境链自检（**必须全部通过**）

> 🔧 **v2.2 已在实机验证**（Windows 11 家庭版中文版）—— 以下 ①②③ 的具体内容来自实测，**其中 ② 的两个坑不处理会直接卡住第一天**。

```powershell
# ① Git
git --version                       # 实测 2.55.0.windows.3
#   安装：winget install --id Git.Git -e --source winget --accept-package-agreements --accept-source-agreements

# ② Python / uv / make —— 三个坑
#   坑 2.1 本机 `python` 可能是微软商店占位符（python --version 输出为空）
#          → 不要用系统 python，用 uv 管理的：uv python list --only-installed
#          → 实测 uv 已带 cpython-3.12.13，`uv sync` 会自动用它
uv --version                        # 实测 0.12.0
make --version                      # 实测 GNU Make 4.4.1
#   安装：winget install --id ezwinports.make -e --source winget --accept-package-agreements --accept-source-agreements

#   坑 2.2 ★★★ 本仓库 Makefile 需要 Unix shell（用了 pwd / pipe / chmod / command -v）
#          → 必须把 Git 自带的 usr/bin 加进 PATH，否则 make 报
#            "process_begin: CreateProcess(NULL, pwd, ...) failed" 并回退到 python3 -m pip
$env:Path = 'C:\Program Files\Git\usr\bin;' + $env:Path     # 每个新会话都要（或永久加到 User PATH 末尾）

#   坑 2.3 ★★★ 中文 Windows 的 locale 默认编码是 GBK(cp936)，而仓库 SQL/源码含 UTF-8 中文
#          → 不开 UTF-8 模式，tests/unit/db 会 18 个失败（UnicodeDecodeError: 'gbk' ... 0x92）
#          → 实测：不设 = 18 failed；设了 = 157 passed, 1 skipped
$env:PYTHONUTF8 = '1'
#   永久化（推荐，一次性）：
#   [Environment]::SetEnvironmentVariable('PYTHONUTF8','1','User')
#   [Environment]::SetEnvironmentVariable('UV_LINK_MODE','copy','User')   # 消除 hardlink 警告

# ③ Node（前端构建）
node --version                      # 实测 v22.23.2

# ④ PostgreSQL 连通 + 权限          ← 需要用户提供 DSN
psql "$env:OCTOP_DATABASE_URL" -c "SELECT version();"
psql "$env:OCTOP_DATABASE_URL" -c "CREATE SCHEMA IF NOT EXISTS _probe_tmp; DROP SCHEMA _probe_tmp;"
#    ↑ 必须成功：项目记忆要建 octop_memory schema，账号需 CREATE SCHEMA 权限

# ⑤ btree_gin 扩展可用（octop-memory PG 后端 FTS 依赖）
psql "$env:OCTOP_DATABASE_URL" -c "CREATE EXTENSION IF NOT EXISTS btree_gin; DROP EXTENSION IF EXISTS btree_gin;"

# ⑥ pg_dump 可用（octop backup 依赖）
pg_dump --version
#   ④⑤⑥ 若本机无 PG：winget install --id PostgreSQL.PostgreSQL.17 -e  （同时也带来 psql/pg_dump）
```

**一键自检（建议存成 `check-env.ps1`）**

```powershell
$env:Path = 'C:\Program Files\Git\usr\bin;' + [Environment]::GetEnvironmentVariable("Path","Machine") + ';' + [Environment]::GetEnvironmentVariable("Path","User")
$env:PYTHONUTF8 = '1'
foreach ($c in 'git','make','uv','node','psql','pg_dump') {
  $p = Get-Command $c -ErrorAction SilentlyContinue
  '{0,-8} {1}' -f $c, $(if ($p) { $p.Source } else { '*** MISSING ***' })
}
'PYTHONUTF8 = ' + $env:PYTHONUTF8
uv run python -c "import locale; print('locale default =', locale.getpreferredencoding(False))"   # 期望 utf-8
```

### 6.2 拉取代码（**统一路径**）

> 🔧 **v2.2 实机修正** —— 以下三件事不做，clone 后 `make all` 会把工作区搞脏或根本拉不下来。

**① 网络：`github.com` 可能被阻断，但子域正常**

实测（中国大陆网络）：`github.com` 的 TLS 会被 reset，但 `codeload.github.com` / `raw.githubusercontent.com` / `api.github.com` **都正常**。

| 现象 | 处理 |
|---|---|
| `git clone https://github.com/...` → `Recv failure: Connection was reset` | git 不读 Windows 系统代理。**查出系统代理端口并配给 git** |
| 查系统代理 | `Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' \| Select ProxyEnable,ProxyServer` |
| 配给 git | `git config --global http.proxy http://127.0.0.1:<port>`（同理 `https.proxy`） |
| 备选：SSH | `github.com:22` 实测**可用**（`ssh -T git@github.com` 返回 `Permission denied (publickey)` = 通道正常，只差注册公钥）。适合 push |
| 备选：zipball | `codeload.github.com` 不封，可用于只读拉取（但**没有 git 历史，无法 rebase**） |

**② Windows 换行符：clone 时就必须关掉 autocrlf（★ 最坑的一个）**

**事实**（实测全量扫描 HEAD 的 3627 个 blob）：

| blob 行尾 | 数量 | 占比 |
|---|---|---|
| **LF** | **3489** | **96%** |
| binary | 99 | 2% |
| no-newline | 23 | — |
| **CRLF** | **16** | 0.4%（只有 `dashboard/public/assets/mbti/*.svg`） |

**所以上游存的是 LF。** 但 Git for Windows 的**系统级** `gitconfig` 默认 `core.autocrlf=true`，clone 时会把工作区写成 CRLF → 工作区与 index 不一致。

```powershell
# ★ 正确做法：clone 时就关掉，一步到位
git -c core.autocrlf=false clone -b develop https://github.com/TencentCloud/Octop.git Octop-develop

# 已经 clone 了的补救（实测有效）：
git config core.autocrlf false      # 仓库级覆盖系统级
# 然后把 i/lf 却 w/crlf 的文件批量转回 LF（见下方脚本思路）
# 最后重建 index：
git read-tree HEAD
```

**三个必须知道的陷阱**

| # | 陷阱 | 后果 | 正解 |
|---|---|---|---|
| a | `git checkout -- .` **不会**重写工作区 | 以为修好了，其实没有 | 必须逐文件把 CRLF 转成 LF |
| b | 批量改文件后 **`git status` 会撒谎** | `status` 报 2462 个改动，`git diff` 只报 9 个 | `git read-tree HEAD` 重建 index（实测：2462 → 12） |
| c | **PowerShell 的 `>` 重定向把 LF 转成 CRLF** | 用它做字节比对会得出**完全相反**的结论（实测把 1138 字节的 LF 文件读成 2366 字节 CRLF） | 字节比对必须用 `[System.IO.File]::ReadAllBytes` 或 Python 的 `subprocess` 二进制管道 |

> b 的判据：`git diff`（index↔worktree）、`git diff HEAD`、`git diff --cached` 三者一致时，**以 `git diff` 为准**，`git status` 是 index stat 缓存陈旧。
> 实测：抽样 40 个跨全树文件做三方逐字节比对，**40/40 完全一致**，而 `status` 仍报 2462。

**③ clone 与远端**

```powershell
cd D:\nancc\octop
# 注意：fork 若只有 main，不要直接 clone fork（拿不到 develop）
# 正确做法：clone 上游 develop，再把 origin 指向自己的 fork
git clone -b develop https://github.com/TencentCloud/Octop.git Octop-develop
cd Octop-develop
git remote rename origin upstream
git remote add origin https://github.com/<你的账号>/Octop.git

git config core.autocrlf false                 # ②
git config core.hooksPath .githooks            # 等价于 make install-hooks

# 若 fork 上没有 develop 分支，把本地的推上去（需要 push 凭据）
# git push -u origin develop

make install        # uv sync（实测装 213 个包）
npm ci --prefix dashboard   # 前端依赖（1066 包，prettier 必需）
make all            # 必须绿
```

> **实测基线**：`make all` = ruff ✅ + prettier ✅ + mypy（527 文件）✅ + pytest **3719 passed / 119 skipped（7 分 33 秒）**。首次跑测试约 7–8 分钟，属正常。

> 另需 fork `octop-harness`（M2 S4 的补丁用）：`git clone -b develop https://github.com/TencentCloud/octop-harness.git octop-harness`（M1 不需要）。

### 6.3 建分支

```powershell
git checkout -b feature/projects-p0              # S1
# 后续：feature/projects-crud（S2）、feature/projects-nodes（S2.5）、feature/chat-sidebar（S0）
```

### 6.4 基线自检

```powershell
git branch --show-current
ls src/octop/infra/db/migrations/ | Select-Object -Last 3          # 期望最高 017
(Get-ChildItem src/octop/infra/db/migrations -Filter '018*').Count  # 期望 0
uv run pytest tests/unit/db -q
cd dashboard; npx tsc -b; cd ..
```

**四个前置条件全部满足才开始写代码**：环境链 6 项通过 · 基线 `make all` 绿 · 迁移最高号 < 018 · 前端可构建。

---

## 7. 上游同步纪律

| 项 | 要求 |
|---|---|
| **节奏** | **每月固定 rebase 一次**（上游约 15 commits/天） |
| **方式** | `git fetch upstream && git rebase upstream/develop` |
| **前置** | 每次 rebase 前读 **commit feed**（CHANGELOG `[Unreleased]` 不完整） |
| **重点盯** | `infra/agents/**` · `thread_artifact.py` · `memory_*.py` · i18n JSON |
| **迁移号** | rebase 后跑 `scripts/bump_schema_version.py`（见下） |
| **提交粒度** | 「迁移 + 16 处断言」单独成 commit，便于集中解冲突 |
| **预期成本** | 每次 0.5–1 小时，3–6 个文件冲突，其中 1 个必冲突 |

### 迁移号迁移脚本（跨平台，替代 v1.0 的 sed）

**`scripts/bump_schema_version.py`**

```python
#!/usr/bin/env python
"""Renumber the project migration when upstream occupies its version.

Handles every spelling found in the test suite:
    assert v == 17 / assert version == 17 / assert result["schema_version"] == 17
    "runtime_schema_version": 17
"""
from __future__ import annotations
import re, subprocess, sys
from pathlib import Path

MINE = 18
ROOT = Path(__file__).resolve().parents[1]
MIG = ROOT / "src/octop/infra/db/migrations"

versions = sorted(int(m.group(1)) for p in MIG.glob("0*.sql")
                  if (m := re.match(r"^(\d{3})_", p.name)))
upstream_max = max(versions)
if upstream_max < MINE:
    print(f"OK: upstream max={upstream_max} < {MINE}, no renumber needed")
    sys.exit(0)

new = upstream_max + 1
print(f"upstream max={upstream_max} >= {MINE}; renumbering project migration -> {new:03d}")

for suffix in (".sql", ".pg.sql"):
    src = MIG / f"{MINE:03d}_projects{suffix}"
    if src.exists():
        subprocess.run(["git", "mv", str(src), str(MIG / f"{new:03d}_projects{suffix}")], check=True)

for p in MIG.glob(f"{new:03d}_projects*.sql"):
    p.write_text(re.sub(rf"version = {MINE};", f"version = {new};", p.read_text(encoding="utf-8")),
                 encoding="utf-8")

PAT = re.compile(rf"(?P<pre>== |: ){MINE}(?P<post>\b)")
changed = 0
for p in (ROOT / "tests").rglob("test_*.py"):
    t = p.read_text(encoding="utf-8")
    nt, n = PAT.subn(lambda m: f"{m.group('pre')}{new}{m.group('post')}", t)
    if n:
        p.write_text(nt, encoding="utf-8")
        changed += n
        print(f"  {p.relative_to(ROOT)}: {n} occurrence(s)")

print(f"done: {changed} assertion(s) updated; now re-run `make all`")
```

> **注意**：脚本只在「上游占用 018」时改写。若上游只是改了 i18n/权限键，无需跑它。

---

## 8. 风险登记册（含需求 §七 对应）

| # | 风险 | 概率 | 影响 | 应对 | 需求 §七 对应 |
|---|---|---|---|---|---|
| R1 | **fork 分支选错**（用 main） | 中 | 致命 | 开工前必查 `git branch --show-current` | R1 fork 同步成本 |
| R2 | 上游重构 `infra/agents` 撞车 | 高 | 中 | **M2 推迟**到重构稳定 | R1 |
| R3 | 迁移号被上游占用 | 中 | 低 | `scripts/bump_schema_version.py` 自动重命名 | R1 |
| R4 | PG 连接泄漏 | 中 | 高 | 不照抄 `memory_client.py`；`ProjectMemoryStore` 显式 close + 上限 + `pg_stat_activity` 回归测试（M2） | — |
| R5 | 权限语义漂移 | 中 | 高 | M2 的 `visible_agent_ids()` 三处共用 | R2 |
| R6 | 非成员越权访问项目数据 | 中 | 高 | `service` 层 `assert_project_role` + AC-13/AC-16 对照测试 | R2 |
| R7 | **WeKnora 只读，产出写不进去** | 高 | 中 | **一期只写 Octop KB**；WeKnora 二期直连 API | R5 |
| R8 | **AI 打标准确率不可控** | 中 | 中 | 打标只出候选，Owner 确认闸门兜底 | R6 |
| R9 | **项目记忆膨胀成流水账** | 中 | 中 | 一事一条 + 来源必填 + supersede + 定期蒸馏（M2 S3） | R7 |
| R10 | **上下文注入无上限，token 失控** | 中 | 中 | 增量注入 + 条数上限 + 超限走 KB 检索（M2 S3） | R8 |
| R11 | 前端 i18n 是平台硬约定 | 高 | 低 | 新页面同时补 zh/en 词条；跑 i18n 测试 | R9 |
| R12 | **ACP 派单依赖外部 runner 可用性** | 中 | 中 | 派单前健康检查 + 失败回退人工 + 时间线留痕（M2 S5） | R10 |
| R13 | i18n 键不一致 | 中 | 低 | 每次改完跑 `uv run pytest tests/unit/i18n -q` | R9 |
| R14 | 未确认节点被生成任务 | 中 | 高 | AC-07 对照测试（UI + API 双路径） | — |
| R15 | `pg_dump` 缺失导致备份失败 | 低 | 中 | **已纳入 §6.1 开工自检 ⑥** | — |
| R16 | PG 账号无 `CREATE SCHEMA` 权限 / 无 `btree_gin` | 低 | 高 | **已纳入 §6.1 开工自检 ④⑤** | — |
| R17 | **T2.5 间接触及 `infra/agents/teams` 接口**（上游重构期签名变动） | 中 | 中 | 对 team room 调用封装小门面；上游签名变更只改一处 | R1 |
| R18 | 两套侧栏（classic/minimal）只改一套 | 高 | 低 | S0 先改 classic（默认布局），minimal 后续跟进 | — |

---

## 9. 已知陷阱清单

| # | 陷阱 | 位置 | 正确做法 |
|---|---|---|---|
| 1 | LRU 淘汰时**不 close** → PG 连接泄漏 | [`memory_client.py:90`](Octop-develop/src/octop/api/common/memory_client.py:90) | 显式 `memory.backend.close()` |
| 2 | 用「存在 thread」判定「用过」 | —— | 用 `Session.hasActivity` |
| 3 | `.hmpkg` pack/adopt 在 PG 上硬拒 | [`memory_portable.py:47`](Octop-develop/src/octop/api/routers/memory_portable.py:47) | 共享同一 namespace，不打包 |
| 4 | 简单放大 team host 工具白名单 | [`teams/service.py:24`](Octop-develop/src/octop/infra/agents/teams/service.py:24) | 新增「项目房间 host」角色 |
| 5 | 重新扫描工作区填 `project_artifacts` | —— | 引用上游 `thread_artifacts` |
| 6 | 成员派工时放开 `peer_invoke_mode` | `team_manager.py:571-574`（sync 降级处） | 保持 sync 降级 |
| 7 | 绕过 `bind_peer_session` 身份键过滤 | [`util.py:16`](octop-harness/src/octop_harness/teams/util.py:16) | 只改 `message` |
| 8 | `_builtin_skills/` 前缀写入 | 上游最新修复 | 参考 workspace 路由 403 保护 |
| 9 | **用裸 `HitlPolicy` 承载业务审批** | −—— | 用 `ask_user_question`（§4.5） |
| 10 | **一条 thread 装多参加者讨论线** | `threads.agent_id NOT NULL` | 双层模型（§4.3） |

---

# 第二部分：落地开发计划

> 任务卡格式：**任务 ID · 内容 · 产出文件 · 验收**
> 每张卡完成即提交，commit message 用 `feat(projects): ...` 前缀

---

## S1：项目域地基（3 天）

### T1.1 — 迁移 019（0.5 天）

**产出**
- `src/octop/infra/db/migrations/019_projects.sql`
- `src/octop/infra/db/migrations/019_projects.pg.sql`
- `src/octop/infra/db/migrations/019_projects_ensure.py`（或 `migrate.py` 内 `_ensure_projects_schema()`）

**内容**：见 **附录 A** 完整 DDL（10 张表）。

**⚠️ 必须配幂等 helper**（v2–v17 每一个迁移都有 `_ensure_*`；缺它会导致「版本号已跳过但列缺失」的老库修复路径失效。参考 [`migrate.py:1592-1705`](Octop-develop/src/octop/infra/db/migrate.py:1592)）

```python
def _ensure_projects_schema(db: DatabasePool) -> None:
    """Idempotent create for DBs whose recorded version skipped 018."""
    # 逐表 CREATE TABLE IF NOT EXISTS + 必要索引；必须可重复执行
```
并在 `run_migrations` 末尾调用。

**验收**（**跨平台写法，不用 `/tmp`**）

```powershell
uv run pytest tests/unit/db/test_migration_019.py -q
```

新增用例 `tests/unit/db/test_migration_019.py`（用 `tmp_path` fixture）：

```python
def test_migration_019_creates_project_tables(tmp_path):
    db = SqlitePool(tmp_path / "t.db")
    run_migrations(db)
    with db.connect() as c:
        assert c.execute("SELECT version FROM _schema_version").fetchone()[0] == 18
        names = {r[0] for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'project%'")}
    assert {"projects", "project_members", "project_tasks", "project_rooms",
            "project_room_members"} <= names

def test_migration_019_is_idempotent(tmp_path):
    db = SqlitePool(tmp_path / "t.db")
    run_migrations(db); run_migrations(db)     # 第二次不得报错
```

---

### T1.2 — 迁移号断言：**16 处 / 8 文件**（0.5 天）

> ⚠️ **v1.0 严重错误**：原文写「7 处 / 1 文件」。实测需同步改 **16 处 / 8 文件**，只改 `test_db_pool.py` 会因另 9 处失败导致 `make all` 必红。

**完整清单**：见 **附录 F**。

**验收**

```powershell
# ① 先列出全部待改点（人工逐条核对，不要盲改）
Select-String -Path tests -Include *.py -Recurse |
  Where-Object { $_.Line -match '==\s*17\b' -or $_.Line -match '["'']runtime_schema_version["'']\s*:\s*17\b' -or
                 $_.Line -match 'schema_version["'']?\]?\s*==\s*17\b' } |
  Select-Object Path, LineNumber, Line

# ② 改完后只能命中附录 F 的 16 处 → 复查应为 0
#    ⚠️ 不要用裸 '== 17|: 17' —— 会误命中非版本断言：
#       max_iters == 17 / recursion_limit == 17 / idle_timeout: 17.0 等（复核实测 3 处误报）
#    必须用上面的精确正则（带 schema_version / runtime_schema_version / _schema_version 上下文）

# ③ 行为验证
uv run pytest tests/unit/db tests/unit/backup -q
make all
```
> ⚠️ 本任务单独成一个 commit（rebase 时冲突集中于此，易解）

---

### T1.3 — Repo 层：**10 张表全覆盖**（0.5 天）

> ⚠️ **v1.0 缺口**：原文只定义 3 个 repo class，其余 7 张表无 repo 任务，阻断 T2.3 / T3.1–T3.5。

**产出**（拆成 3 个文件，避免单文件过大）

| 文件 | 覆盖表 | Repo class |
|---|---|---|
| `src/octop/infra/db/repos/projects.py` | `projects`、`project_members` | `ProjectRepo`、`ProjectMemberRepo` |
| `src/octop/infra/db/repos/project_tasks.py` | `project_tasks`、`timeline_events` | `ProjectTaskRepo`、`TimelineRepo` |
| `src/octop/infra/db/repos/project_content.py` | `project_comments`、`node_mark_logs`、`requirement_nodes` | `ProjectCommentRepo`、`NodeMarkLogRepo`、`RequirementNodeRepo` |
| `src/octop/infra/db/repos/project_rooms.py` | `project_rooms`、`project_room_members`、`project_artifacts` | `ProjectRoomRepo`、`ProjectArtifactRepo` |

**约束**：只许 import `infra/db/_base`、`infra/utils/`（AGENTS.md §5 硬禁）。

**软外键校验**（`subject_id` / `parent_id` / `thread_id` 等无 FK 的列）：在 Repo 层补存在性校验，避免依赖 DB 约束。

**验收**
```powershell
uv run pytest tests/unit/db -q -k project
```

---

### T1.4 — Service + Router 骨架 + 权限键 + 错误码（1 天）

**产出**
| 文件 | 内容 |
|---|---|
| `src/octop/infra/projects/__init__.py` | 包 |
| `src/octop/infra/projects/service.py` | 领域逻辑 + **`assert_project_role()` 权限矩阵（§4.6）** |
| `src/octop/api/routers/projects.py` | 薄 HTTP 层，`require_permission("projects")` |

**必改核心文件（6 处，均为追加式）**

| # | 文件 | 改动 |
|---|---|---|
| 1 | [`infra/db/services.py`](Octop-develop/src/octop/infra/db/services.py) | `RepoBundle` 加 4 个 repo 字段 · `from_pool` 加构造 · `SharedServices` 加 property；**为 M2 预留 `project_memory` 字段位** |
| 2 | [`infra/users/permissions.py`](Octop-develop/src/octop/infra/users/permissions.py:50) | `PERMISSIONS` 加 `"projects"`（`category="settings"`，理由见 §4.6） |
| 3 | [`api/app.py`](Octop-develop/src/octop/api/app.py:203) | import + `_RouterMount(projects.router, "/api", ["projects"])` |
| 4 | [`api/openapi_meta.py`](Octop-develop/src/octop/api/openapi_meta.py) | `OPENAPI_TAGS` 加 tag + 描述 |
| 5 | [`infra/errors.py`](Octop-develop/src/octop/infra/errors.py) | `ErrorCode` 加 `PROJECT_*` + `_HTTP_STATUS` 映射 |
| 6 | `src/octop/i18n/{en,zh}.json` | 追加 `errors.PROJECT_*`（**文件末尾**） |

**新增 ErrorCode**
```
PROJECT_NOT_FOUND / PROJECT_FORBIDDEN / PROJECT_MEMBER_INVALID
PROJECT_TASK_NOT_FOUND / PROJECT_TASK_STATUS_INVALID
PROJECT_NODE_NOT_FOUND / PROJECT_NODE_NOT_CONFIRMED
PROJECT_KB_BIND_FAILED / PROJECT_ROLE_FORBIDDEN
```

**验收**
```powershell
uv run pytest tests/unit/api -q          # ACL 守卫
uv run pytest tests/unit/i18n -q         # 键对齐
make all
# 人工：GET /api/docs 可见 projects tag，且有 summary + response_model
```

---

### T1.5 — S1 收口（0.5 天）

**产出**
- 修改 [`tests/unit/api/test_acl_gate_coverage.py`](Octop-develop/tests/unit/api/test_acl_gate_coverage.py:12)：`GATED_FILES` 加 `routers/projects.py`
- `tests/unit/projects/`（目录 + `__init__.py`）

**验收**
```powershell
make all
cd dashboard; npx tsc -b; cd ..
git tag m1-p0-done
```

---

## S2：项目 / 成员 / 任务 / 看板（7 天）

### 接口契约

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/projects` | 我可见的项目（**强制 join `project_members`**） |
| POST | `/api/projects` | 立项（写 owner 成员行 + 分配 `memory_namespace` + **自动建 KB 并回写 `kb_id`**） |
| GET/PATCH/DELETE | `/api/projects/{project_id}` | 详情 / 编辑 / 归档（**归档仅 owner**） |
| GET/POST | `/api/projects/{project_id}/members` | 成员列表 / 增删改角色 |
| GET/POST | `/api/projects/{project_id}/tasks` | 任务列表（看板源）/ 创建 |
| PATCH/DELETE | `/api/projects/{project_id}/tasks/{task_id}` | 改状态（拖拽）/ 编辑 / 删除 |
| POST | `/api/projects/{project_id}/tasks/{task_id}:dispatch` | **派单**（见 T2.5） |

### 任务卡

| ID | 任务 | 产出 | 预估 |
|---|---|---|---|
| **T2.1** | 项目 CRUD + **项目 KB 生命周期** + **Project 状态机** | 扩展 `projects/service.py` | 2 天 |
| **T2.2** | 项目列表/详情/成员 前端页 | `pages/Projects/index.tsx`、`Detail/` | 1.5 天 |
| **T2.3** | 任务 CRUD + 状态机 + `timeline_events` 写入 | 扩展 service | 1 天 |
| **T2.4** | 看板页（状态列 + 拖拽 + 过滤） | `pages/Projects/Detail/Board.tsx` | 1.5 天 |
| **T2.5** | 派单（同用户，见下） | `service.dispatch_task()` | 0.5 天 |
| **T2.6** | 会话列表项目分组 + 「项目会话」标签 | 扩展 S0 的 `useSessionInbox` | 0.5 天 |

### T2.1 三件事（闭合 B3 与 M8）

**① 项目 KB 生命周期（B3 blocker）**

> 🔧 **v2.1 修正（技术复核 V2）**：原文「⑤ 失败则整体回滚」**不成立** —— 各 repo 各自开事务，**没有跨 repo 的共享事务**。KB 创建是独立于控制面事务的外部副作用，必须**补偿删除**。

```text
POST /api/projects
  → ⓪ 前置校验（任一不满足即拒绝，不留半成品）：
       · 立项人拥有 knowledge_bases 权限（require_permission("knowledge_bases") 同语义）
       · 该用户 KB 数未达 MAX_BASES_PER_OWNER（create_base 会因 assert_knowledge_usable 失败）
       · 名称冲突预检（knowledge_bases 有 UNIQUE(owner_user_id, name)）
  → ① INSERT projects（memory_namespace = "project_{project_id}"）
  → ② INSERT project_members(owner)
  → ③ 调 KB service 的 create_base（不经 HTTP，直接内部调用）→ 得 kb_id
        失败分支：补偿删除 ①② 已写行，抛 PROJECT_KB_BIND_FAILED（或透传 KB 侧错误码）
  → ④ UPDATE projects SET kb_id = ?
        失败分支：补偿删除 ③ 刚建的 KB + ①② 已写行
  → ⑤ 全部成功才返回 201
```

**补偿删除是硬要求**：任一步失败都必须显式撤销前序副作用，否则会留下「有项目无 KB」或「有 KB 无项目」的孤儿数据。**T2.1 必须为失败分支写测试**（注入 KB 创建失败，断言 `projects` 表无残留行、KB 数未增加）。

> **T3.4 前置**：归档只在 `kb_id IS NOT NULL` 时执行；为 NULL 时明确报错而非静默跳过。

**② Project 状态机流转校验（M8）**

| 当前 | 允许转 | 条件 |
|---|---|---|
| draft | active | 至少 1 名成员 + 有 owner |
| active | paused / archived | 归档仅 owner |
| paused | active / archived | |
| archived | **终态** | 任何写操作 403 |

**③ 权限矩阵落地**：`assert_project_role(project_id, user, required)`，覆盖 §4.6 表。

### T2.5 派单实现（闭合 M11/M12 依赖）

**明确调用链**（v1.0 未指明）：

> 🔧 **v2.1 修正（技术复核 V2）**：原文写的「走 `gateway.run_in_session()`」**命名错** —— `run_in_session` 是**会话串行锁包装器**，不是发消息的。**正确参照实现是 [`infra/cron/delivery.py`](Octop-develop/src/octop/infra/cron/delivery.py)**：`deliver()` 在最外层持会话锁 → `_deliver_agent()` 内 `build_harness_request(...)` 组装请求 → `agent_manager.stream(agent_id, request)` 真正执行。

```text
POST /api/projects/{pid}/tasks/{tid}:dispatch
  → 校验：task.assignee_type ∈ {agent, team}
  → ① 建 thread：ThreadRegistry.create_thread(agent_id=assignee_id, user_id=派单人)
        （等价于 POST /api/agents/{agent_id}/threads，但走内部调用不经 HTTP）
  → ② 组装任务上下文（纯文本）：
        「任务标题 + 描述 + ## 验收标准 小节 + 项目名 + 任务链接」
  → ③ 发起一轮 agent turn —— 照抄 cron delivery 的两段式：
        · request = build_harness_request(...)            # 注意传 thread_id / session_key
        · async for chunk in agent_manager.stream(assignee_id, request): ...
        · 外层用会话串行锁包住（与 cron 的 run_in_session 同语义），避免与同会话
          的其它回合交错污染（上游已修过此类 bug）
  → ④ 分两条路径：
        · assignee_type=agent → 上述 turn 直接跑该专家
        · assignee_type=team  → 该 turn 跑 team host；**host 必须真的启动一轮 turn**
                                  （不是只投递一条消息），其 ask_agent(async) 才会
                                  触发现有团队 room 并把成员发言 fan-in 回房间
  → ⑤ UPDATE project_tasks SET thread_id = ?
  → ⑥ 写 timeline_events(action='dispatch')
```

> **实现要点**：**不要把这段逻辑重写一遍** —— 直接复用/抽取 `infra/cron/delivery.py` 的 `_deliver_agent()` 路径（它已经处理好 thread_id、session_key、MCP 装配、团队 agent 分支）。T2.5 应做的是**把该路径抽成一个可传自定义 prompt 的内部函数**，而不是另起一套。

> **接口风险封装（R17）**：对 team room 的调用包一层 `_TeamRoomBridge`，上游 `infra/agents/teams` 签名变动时只改这一处。

### 前端必改（3 登记点 + 2 i18n）

| 文件 | 改动 |
|---|---|
| [`dashboard/src/routes/index.tsx`](Octop-develop/dashboard/src/routes/index.tsx) | lazy + `pathToKey` + routes 数组 |
| [`dashboard/src/layouts/sidebarNav.tsx`](Octop-develop/dashboard/src/layouts/sidebarNav.tsx) | `SIDEBAR_GROUPED_NAV_KEYS` + NavItem |
| [`dashboard/src/utils/permissions.ts`](Octop-develop/dashboard/src/utils/permissions.ts) | `PERM` + `NAV_PERMISSIONS` + `pathPermissionKeys` |
| `dashboard/src/api/modules/projects.ts` + `api/types/projects.ts` | 新增（仿 `modules/teams.ts`） |
| `dashboard/src/locales/{en,zh}.json` | `nav.projects` 等（**文件末尾追加**） |

**时间显示**：所有时间用 `formatServerDateTime` / `formatMessageTime(..., timeZone)`（铁律 #13）。

### 验收

```powershell
uv run pytest tests/integration/test_projects_api.py -q
cd dashboard; npx tsc -b; npm run test -- --run; cd ..
```

| AC | 条件 | 客观判定 |
|---|---|---|
| AC-01 | 建项目含 ≥1 真人/专家/团队，角色正确回显 | 断言响应 JSON |
| AC-02 | 10 个任务看板一屏尽览；改状态实时反映 | 人工：1920×1080 下任务列不出现滚动条（截图存档） |
| AC-09 | 派工消息含任务标题/描述/验收标准 | 断言 thread 首条消息文本 |
| **AC-13** | **非成员访问项目数据一律拒绝** | 对照测试：非成员 对 5 类资源 × 4 方法 全 403 |
| **AC-16** | 项目 A 共享专家不可被项目 B 未授权访问 | 对照测试 |
| **新增** | **viewer 写操作 403**；**admin 归档 403** | 权限矩阵测试（§4.6） |

---

## S2.5：讨论 / 打标 / 需求节点 / Owner 闸门（4.5 天）

### 任务卡

| ID | 任务 | 产出 | 预估 |
|---|---|---|---|
| **T3.1** | 讨论线（**双层模型**）+ `project_comments` CRUD | `infra/projects/discussion.py` | 1.5 天 |
| **T3.2** | 打标 + 需求节点池 + Leader 草案落库 | `infra/projects/nodes.py` | 1 天 |
| **T3.3** | **Owner 闸门走 `ask_user_question`**（§4.5）+ 需求池前端页 | `infra/projects/approval.py`、`pages/Projects/Detail/RequirementPool.tsx` | 1 天 |
| **T3.4** | 资料归档（**前置：kb_id 已绑定**，见 T2.1） | 扩展 service | 0.5 天 |
| **T3.5** | 时间线回放接口 | 扩展 service | 0.5 天 |

### T3.1 必须补的三项验收（闭合 H5）

| AC | 要求 | 测试 |
|---|---|---|
| **AC-03** | 任务独立讨论线，发言不污染其他任务 | 建 2 个任务 → 各发 3 条评论 → 断言各自只读到自己的 3 条 |
| **AC-04** | 每条评论显示作者（真人名/专家名）+ 时间；**专家产出自动落入对应任务讨论线** | 断言 `comment.author_type/author_id/created_at` 齐全；派单后专家产出回写 `project_comments`（`source='agent'`） |

**时间显示遵守铁律 #13**（时区）。

### T3.2 Leader 草案（闭合 M10）

按 **§4.4** 实现：Leader = 普通专家；验收标准暂存 `project_tasks.description` 的 `## 验收标准` 小节；草案落 `project_comments` + `requirement_nodes.summary`。

### T3.3 Owner 闸门（闭合 H2）

按 **§4.5** 实现：`ask_user_question`（`allowed_decisions` 由 harness 硬编码为 `["respond"]`，**无需配置**，只需确保 `cfg.ask_user_enabled` 且工具未被 `tools_disabled` 禁用）+ IM 卡片出站复用 `hitl/format.py`。**不得使用裸 `HitlPolicy(approve/reject)`**。

### 验收

| AC | 条件 |
|---|---|
| AC-05 | 打「需求节点」后，需求池 1 次刷新内出现该节点并带来源链接 |
| AC-06 | 撤销打标后节点消失（或转 draft），`node_mark_logs` 留痕可查 |
| **AC-07** | **对照测试**：未确认节点在 UI 与 API 上均无「生成任务」路径 |
| AC-08 | Leader 草案 → Owner 确认 → 生成 N 个任务，每个 `origin_node_id` 可追溯 |
| AC-10 | 任务转 done 时产出出现在**项目 KB**；KB 条目可跳回任务与来源评论 |
| AC-12 | 任务时间线完整有序（**不含记忆变更事件 —— M1 显式裁剪，见 §2.2**） |
| AC-14 | 搜产出关键句 30s 内命中并可定位来源任务（人工：计时 + 记录） |
| **AC-03/04** | 见上 |

```powershell
uv run pytest tests/integration/test_project_nodes_api.py -q
make all
git tag m1-done     # 🎉 M1 里程碑
```

---

## S0：聊天列表改造（2.5 天，可并行）

> **S0 与 S1/S2 无依赖**。默认布局是 `classic`（[`layoutModeStorage.ts:18`](Octop-develop/dashboard/src/layouts/layoutModeStorage.ts:18)），**先改 `SessionList.tsx`**。

### T0.1 — 后端：跨 agent 会话聚合端点（0.5 天）

**产出**：`src/octop/api/routers/chat/sessions.py` + `chat/__init__.py` 注册一行

**用服务端聚合，不依赖 limit 边界**（`history.py:102` 实际是 `limit: int = 50`，CHANGELOG 的「1–200」在快照代码里未见实现，语义不稳定）

```
GET /api/threads/summary
→ [ { agent_id, session_count, has_activity, last_active,
      pinned: [ { thread_id, title, ... } ] } ]     # 每个 agent 一行，天然有界
```

**产出 2**：`ThreadRepo.list_by_user(user_id, limit)`（追加方法，见附录 B）

### T0.2 — 前端 hook（0.5 天）

**产出**：`dashboard/src/pages/Chat/hooks/useSessionInbox.ts`
单次请求；复用 `toSession()`；监听会话事件做本地 patch；`agentKey` 依赖避免重复请求。

### T0.3 — SessionList 三段式改造（1 天）

```
📌 置顶 (n)
💬 会话 (m)
   ├ 交付团队  [群聊]  ▸ 3
   └ 开发专家          ▸ 5
📦 未使用 (k)  ▸        ← 默认折叠，搜索时强制展开
```

| 改动 | 说明 |
|---|---|
| 新增 props | `inboxByAgent` / `pinnedSessions` |
| 分组判定 | **用 `hasActivity`，不用「存在 thread」** |
| 群聊标签 | 复用 [`TeamChatBadge`](Octop-develop/dashboard/src/pages/Chat/components/TeamChatBadge.tsx) |
| **放开隐藏** | [`useHiddenSharedExperts.ts`](Octop-develop/dashboard/src/pages/Chat/hooks/useHiddenSharedExperts.ts)：删 `filterVisible`/`pickHidden` 里的 `isSharedExpertViewer` 过滤，`canHide` 返回 `true`（storage key 不变，向后兼容） |

### T0.4 — i18n + 测试（0.5 天）

i18n 追加（**文件末尾，独立命名空间**）：`chat.sectionPinned` / `chat.sectionActive` / `chat.sectionUnused`

测试：`useSessionInbox.test.ts`、`SessionList.grouping.test.tsx`、`tests/unit/api/test_threads_router.py`

**人工验收**：进聊天页 Network **只出现 1 次**请求；未使用组默认折叠且计数正确；搜索自动展开；团队显示「群聊」；可隐藏自建专家。

---

## M2 阶段（概要）

| 阶段 | 核心内容 | 预估 |
|---|---|---|
| **S3** 项目记忆 | `ProjectMemoryStore` 门面 + `project_{id}` namespace + **`source_refs` 映射层** + `bind_peer_session` 注入 | 4.5 天 |
| **S4** 跨团队房间 | harness `bind_peer_scope` 补丁 + Octop 三处放权 + 团队工具放开 | 5 天 |
| **S5** 方案评审 + 派单 | **方案评审闸门** + ACP 派单 + commit 回写 + R10 健康检查 | 4.5 天 |

### S3 必须补的三项（闭合 H3 与 R9/R10）

**① `source_refs` 映射层 + `created_by`（H3）**

octop-memory 的 atoms 只有 `quote_event_id` / `raw_event_ids`，**没有**「comment/task/artifact」业务回链，也**没有 owner 列**。必须自研映射层：

```sql
-- M2 迁移 020（019 已被 M1 占用并随本分支提交）
CREATE TABLE project_memory_refs (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id TEXT NOT NULL,
  atom_id    TEXT NOT NULL,          -- octop_memory atoms.id
  source_type TEXT NOT NULL,         -- comment|task|artifact
  source_id  TEXT NOT NULL,
  created_by TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  UNIQUE(project_id, atom_id, source_type, source_id)
);
```

**② 注入版本粒度显式决策**：M1/M2 采用**项目级** `projects.inject_version`（满足 AC-11）；**按条增量注入需条目级水位**，若产品要求则在该表加 `injected_at` 列。**必须在 S3 开工前确认**。

**③ AC-11 验收 + 连接泄漏回归测试**

```powershell
uv run pytest tests/integration/test_project_memory.py -q
# AC-11：新增记忆条目 → inject_version +1 → 随后派工消息包含该条
# 连接：连续建/销 100 个项目后，SELECT count(*) FROM pg_stat_activity 不增长
```

**S3 四条硬约束**

1. 按 `project_id` 缓存 `Memory` 实例，**带硬上限**（数值需在 S3 开工时确定，写入 `config`）
2. 淘汰时必须显式 `memory.backend.close()`
3. **不挂 `MemoryMiddleware`**（轻量门面 → 无后台线程、无 segfault 风险）
4. **不要用 `.hmpkg`**；跨团队共享 = 同一个 namespace

### S4 harness 补丁

```python
# octop-harness/src/octop_harness/teams/team_manager.py
def bind_peer_scope(self, scope: Callable[[str], set[str] | None] | None) -> None:
    """Return the caller's allowed peer agent_ids, or None to keep the user_id rule."""
    self._peer_scope = scope
```
在 `list_peers` 的**用户过滤之后、`team_peers` 白名单之前**插入，**替换而非叠加**。
Octop 侧三处共用 `visible_agent_ids()`（会话端点 / `bind_peer_scope` / `_user_may_use_member`）。

### S5 方案评审闸门（闭合 H1/AC-15）

```text
requirement_node confirmed
  → 派 PRD 类专家出方案（写 project_comments + project_artifacts）
  → Owner 通过（同一 ask_user_question 闸门）
  → 才开放 ACP 派单入口
未过评审：UI 与 API 均无 ACP 派单路径（AC-15 对照测试）
```
另补 **R12**：派单前 runner 健康检查 + 失败回退人工 + 时间线留痕。

---

# 附录 A：迁移 019 完整 DDL

**`src/octop/infra/db/migrations/019_projects.sql`**

```sql
-- Schema v18: project management domain.
-- Threads are NOT altered; project linkage resolves via project_rooms/project_tasks.

CREATE TABLE projects (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id       TEXT NOT NULL UNIQUE,
  name             TEXT NOT NULL,
  goal             TEXT NOT NULL DEFAULT '',
  status           TEXT NOT NULL DEFAULT 'draft',   -- draft|active|paused|archived
  owner_user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  memory_namespace TEXT NOT NULL,                   -- "project_{project_id}"
  inject_version   INTEGER NOT NULL DEFAULT 0,
  kb_id            TEXT,                            -- 立项时自动创建并回写（T2.1）
  start_at         INTEGER,
  due_at           INTEGER,
  created_at       INTEGER NOT NULL,
  updated_at       INTEGER NOT NULL
);
CREATE INDEX idx_projects_owner ON projects(owner_user_id, updated_at DESC);

CREATE TABLE project_members (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id   TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
  subject_type TEXT NOT NULL,                       -- user|agent|team
  subject_id   TEXT NOT NULL,                       -- user 时存用户整数 id 的字符串形式
  user_id      INTEGER,                             -- subject_type='user' 时冗余，便于 join
  role         TEXT NOT NULL DEFAULT 'member',      -- owner|admin|member|viewer
  created_at   INTEGER NOT NULL,
  UNIQUE(project_id, subject_type, subject_id)
);
CREATE INDEX idx_project_members_subject ON project_members(subject_type, subject_id);
CREATE INDEX idx_project_members_user    ON project_members(user_id) WHERE user_id IS NOT NULL;

CREATE TABLE project_tasks (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id        TEXT NOT NULL UNIQUE,
  project_id     TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
  parent_id      TEXT,
  title          TEXT NOT NULL,
  description    TEXT NOT NULL DEFAULT '',          -- 含 "## 验收标准" 小节（M10）
  status         TEXT NOT NULL DEFAULT 'todo',      -- todo|doing|review|done|blocked|cancelled
  assignee_type  TEXT,                              -- user|agent|team
  assignee_id    TEXT,
  priority       INTEGER NOT NULL DEFAULT 0,
  deps           TEXT NOT NULL DEFAULT '[]',
  thread_id      TEXT,
  origin_node_id TEXT,
  due_at         INTEGER,
  sort_order     INTEGER NOT NULL DEFAULT 0,
  created_by     INTEGER NOT NULL REFERENCES users(id),
  created_at     INTEGER NOT NULL,
  updated_at     INTEGER NOT NULL
);
CREATE INDEX idx_project_tasks_project ON project_tasks(project_id, status, sort_order);
CREATE INDEX idx_project_tasks_thread  ON project_tasks(thread_id);

CREATE TABLE project_comments (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  comment_id  TEXT NOT NULL UNIQUE,
  project_id  TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
  task_id     TEXT,
  thread_id   TEXT,                                 -- 可选外键，指回对话流（双层模型）
  author_type TEXT NOT NULL,                        -- user|agent|system
  author_id   TEXT NOT NULL,
  body        TEXT NOT NULL,
  source      TEXT NOT NULL DEFAULT 'dashboard',    -- dashboard|im|agent
  node_type   TEXT NOT NULL DEFAULT 'none',         -- none|business|requirement
  created_at  INTEGER NOT NULL,
  updated_at  INTEGER NOT NULL
);
CREATE INDEX idx_project_comments_project ON project_comments(project_id, created_at DESC);
CREATE INDEX idx_project_comments_task    ON project_comments(task_id, created_at);

CREATE TABLE node_mark_logs (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  comment_id TEXT NOT NULL,
  from_type  TEXT NOT NULL,
  to_type    TEXT NOT NULL,
  actor      TEXT NOT NULL,
  at         INTEGER NOT NULL
);
CREATE INDEX idx_node_mark_logs_comment ON node_mark_logs(comment_id, at);

CREATE TABLE requirement_nodes (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  node_id         TEXT NOT NULL UNIQUE,
  project_id      TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
  comment_id      TEXT,
  type            TEXT NOT NULL DEFAULT 'requirement',
  status          TEXT NOT NULL DEFAULT 'draft',    -- draft|pending_confirm|confirmed|split|closed|rejected
  title           TEXT NOT NULL DEFAULT '',
  summary         TEXT NOT NULL DEFAULT '',
  split_task_ids  TEXT NOT NULL DEFAULT '[]',
  proposed_by     TEXT,
  proposed_at     INTEGER,
  confirmed_by    TEXT,
  confirmed_at    INTEGER,
  rejected_reason TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_requirement_nodes_project ON requirement_nodes(project_id, status);

CREATE TABLE project_rooms (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  room_id       TEXT NOT NULL UNIQUE,
  project_id    TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
  thread_id     TEXT NOT NULL,
  host_agent_id TEXT NOT NULL,
  status        TEXT NOT NULL DEFAULT 'open',       -- open|closed
  created_at    INTEGER NOT NULL
);
CREATE INDEX idx_project_rooms_thread  ON project_rooms(thread_id);
CREATE INDEX idx_project_rooms_project ON project_rooms(project_id, status);

CREATE TABLE project_room_members (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  room_id      TEXT NOT NULL REFERENCES project_rooms(room_id) ON DELETE CASCADE,
  subject_type TEXT NOT NULL,
  subject_id   TEXT NOT NULL,
  joined_at    INTEGER NOT NULL,
  UNIQUE(room_id, subject_type, subject_id)
);

-- 命名为 project_artifacts 以避免与上游 threads.artifacts 列概念混淆（报告 L1）
CREATE TABLE project_artifacts (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  artifact_id    TEXT NOT NULL UNIQUE,
  project_id     TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
  task_id        TEXT,
  thread_id      TEXT,                              -- 指回产出所在 thread
  kind           TEXT NOT NULL,                     -- doc|prd|code|context
  name           TEXT NOT NULL,
  uri            TEXT NOT NULL,                     -- 工作区路径（复用上游 thread_artifacts 的 path）
  agent_id       TEXT,                              -- 上游 ThreadArtifact.agent_id
  kb_document_id TEXT,
  commit_ref     TEXT,
  version        INTEGER NOT NULL DEFAULT 1,
  hash           TEXT NOT NULL DEFAULT '',
  created_by     TEXT NOT NULL,
  created_at     INTEGER NOT NULL
);
CREATE INDEX idx_project_artifacts_project ON project_artifacts(project_id, created_at DESC);
CREATE INDEX idx_project_artifacts_task    ON project_artifacts(task_id);

CREATE TABLE timeline_events (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
  task_id    TEXT,
  actor      TEXT NOT NULL,
  action     TEXT NOT NULL,
  payload    TEXT NOT NULL DEFAULT '{}',
  at         INTEGER NOT NULL
);
CREATE INDEX idx_timeline_project ON timeline_events(project_id, at DESC);
CREATE INDEX idx_timeline_task    ON timeline_events(task_id, at);

UPDATE _schema_version SET version = 19;
```

**`019_projects.pg.sql` 差异**

| SQLite | PostgreSQL |
|---|---|
| `INTEGER PRIMARY KEY AUTOINCREMENT` | `INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY` |
| 时间戳 `INTEGER NOT NULL` | **`INTEGER NOT NULL`（保持同型 —— 仓库 `001_initial.pg.sql` 的 `created_at` 均为 INTEGER）** |
| 部分索引 `WHERE user_id IS NOT NULL` | 相同语法 |

> ⚠️ **v1.0 错误修正**：原文写「PG 时间戳用 BIGINT」是误判（报告 L4）。

---

# 附录 B：`ThreadRepo.list_by_user` 追加方法

```python
def list_by_user(self, *, user_id: int, limit: int = 50) -> list[ThreadRow]:
    """Every thread this user owns, newest first — sidebar aggregation."""
    with self._db.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM threads WHERE user_id = ? "
            "ORDER BY pinned DESC, "
            "CASE WHEN last_active > 0 THEN last_active ELSE created_at END DESC, "
            "thread_id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    return map_rows(rows, ThreadRow)
```

---

# 附录 C：文件清单总表

## 新增（约 28 个，**rebase 零冲突**）

```
src/octop/infra/db/migrations/019_projects.sql
src/octop/infra/db/migrations/019_projects.pg.sql
src/octop/infra/db/repos/projects.py                # projects, project_members
src/octop/infra/db/repos/project_tasks.py           # project_tasks, timeline_events
src/octop/infra/db/repos/project_content.py         # project_comments, node_mark_logs, requirement_nodes
src/octop/infra/db/repos/project_rooms.py           # project_rooms, project_room_members, project_artifacts
src/octop/infra/projects/__init__.py
src/octop/infra/projects/service.py                 # 含 assert_project_role 权限矩阵
src/octop/infra/projects/discussion.py              # T3.1
src/octop/infra/projects/nodes.py                   # T3.2（打标 + 需求节点 + Leader 草案）
src/octop/infra/projects/approval.py                # T3.3（ask_user_question 闸门）
src/octop/infra/projects/visibility.py              # M2
src/octop/infra/projects/memory.py                  # M2
src/octop/api/routers/projects.py
src/octop/api/routers/project_nodes.py
src/octop/api/routers/chat/sessions.py              # S0
dashboard/src/pages/Projects/index.tsx
dashboard/src/pages/Projects/Detail/index.tsx
dashboard/src/pages/Projects/Detail/Board.tsx
dashboard/src/pages/Projects/Detail/RequirementPool.tsx
dashboard/src/pages/Chat/hooks/useSessionInbox.ts                # S0
dashboard/src/pages/Chat/components/SessionGroupHeader.tsx       # S0
dashboard/src/api/modules/projects.ts
dashboard/src/api/types/projects.ts
scripts/bump_schema_version.py
tests/unit/db/test_migration_019.py
tests/unit/projects/**（含 test_permissions_matrix.py）
tests/integration/test_projects_api.py
tests/integration/test_project_nodes_api.py
tests/unit/api/test_threads_router.py
dashboard/src/pages/Chat/hooks/useSessionInbox.test.ts           # T0.4
dashboard/src/pages/Chat/components/SessionList.grouping.test.tsx # T0.4
```

## 修改（约 24 个）

| 风险 | 文件 |
|---|---|
| **高** | `src/octop/i18n/{en,zh}.json` · `dashboard/src/locales/{en,zh}.json` · `src/octop/infra/errors.py` |
| 低（注册点） | `src/octop/api/app.py` · `src/octop/infra/db/services.py` · `src/octop/infra/users/permissions.py` · `src/octop/api/openapi_meta.py` · `dashboard/src/routes/index.tsx` · `dashboard/src/layouts/sidebarNav.tsx` · `dashboard/src/utils/permissions.ts` |
| 低（追加） | `src/octop/infra/db/repos/threads.py` · `src/octop/api/routers/chat/__init__.py` · `src/octop/infra/db/migrate.py`（`_ensure_projects_schema`） |
| 低（放开过滤） | `dashboard/src/pages/Chat/hooks/useHiddenSharedExperts.ts` |
| 中 | `dashboard/src/pages/Chat/components/SessionList.tsx` |
| **必冲突** | `tests/unit/db/test_db_pool.py` + 另 7 个测试文件（**16 处**，见附录 F） |
| 必改 | `tests/unit/api/test_acl_gate_coverage.py`（`GATED_FILES`） |
| M2 | `src/octop/infra/agents/manager.py` · `memory_backend.py` · `teams/service.py` · `octop-harness/teams/team_manager.py` |

---

# 附录 D：开工第一天清单

```
上午（环境，不写代码）
□ Git 安装 + 6 项环境链自检（§6.1，含 PG CREATE SCHEMA / btree_gin / pg_dump）
□ Move-Item Octop-develop Octop-develop-snapshot
□ git clone -b develop ... Octop-develop
□ git remote add upstream ...
□ make install && make install-hooks && make all        ← 必须绿
□ §6.4 基线自检 4 项
□ git checkout -b feature/projects-p0

下午（T1.1）
□ 写 019_projects.sql + 019_projects.pg.sql（照附录 A）
□ 加 _ensure_projects_schema() 幂等 helper 并在 run_migrations 末尾调用
□ 新增 tests/unit/db/test_migration_019.py（tmp_path，跨平台）
□ uv run pytest tests/unit/db/test_migration_019.py -q   ← 必须绿
□ git commit -m "feat(projects): add migration 019 for project domain"

下班前（T1.2）
□ 全仓改 16 处迁移号断言（照附录 F，用 §T1.2 的精确正则核对，不要盲改）
□ uv run pytest tests/unit/db tests/unit/backup -q       ← 必须绿
□ git commit -m "test(db): bump schema version assertions to 18"
```

**第一天不写业务代码** —— 只把地基和迁移验证掉。

---

# 附录 E：修订对照

## E-1：v1.0 → v2.0 修订对照（共 **30** 条，闭合审查报告 32 项发现）

> 🔧 **v2.1 更正**：原文标题写「29 条」，复核实测为 **30 条**。

| 审查编号 | 级别 | v2.0 修订位置 |
|---|---|---|
| B1 迁移断言 16 处/8 文件 | blocker | 铁律 #3 · T1.2 · §7 脚本 · 附录 F · §6.4 |
| B2 T1.1 验收 POSIX 化 | blocker | T1.1（改 `tmp_path` + pytest 用例） |
| B3 项目 KB 创建/绑定缺失 | blocker | T2.1 三件事① · §2.1 · 接口契约 |
| H1 AC-15/M13 评审闸门 | high | §2.2 不做清单 · S5 方案评审闸门 |
| H2 HITL 语义错配 | high | **§4.5 全新章节** · 约束 #5 · T3.3 · 陷阱 #9 |
| H3 ProjectMemory 丢字段 | high | S3 三项①（`project_memory_refs` DDL） |
| H4 repo 只覆盖 3/10 表 | high | T1.3 改为 4 个文件 / 10 张表 · 附录 C |
| H5 AC-03/04 缺失 | high | T3.1 必须补的三项验收 |
| H6 viewer 只读零落地 | high | **§4.6 权限矩阵** · T2.1③ · S2 验收 |
| H7 时区纪律缺失 | high | **铁律 #13** · T2.4/T3.1/T3.5 |
| H8 工期 12d vs 13.5d | high | §3 里程碑 · §0 总览 |
| M1 风险编号两套 | medium | §8 加「需求 §七 对应」列 |
| M2 M10 机制/验收标准字段 | medium | **§4.4 全新章节** · T3.2 |
| M3 Q5–Q10 悬空 | medium | **§2.3 遗留问题裁决** |
| M4 讨论线表述掩盖 | medium | **§4.3 双层模型** |
| M5 附录 C 遗漏 | medium | 附录 C 已补 4 个文件 |
| M6 §6 缺 4 项前置 | medium | §6.1 六项环境链自检 |
| M7 clone 路径不一致 | medium | §6.2 统一路径 |
| M8 Project 状态机无流转 | medium | T2.1② |
| M9 验收缺客观断言 | medium | S2/S2.5 验收表加判定方式 |
| M10 M3 KB 成员授权 | medium | §2.2 后置声明 + M2 S4 |
| M11 T2.5 端点不明确 | medium | T2.5 明确调用链 |
| M12 T2.5 接口风险 | medium | R17 · T2.5 `_TeamRoomBridge` |
| L1 artifacts 命名混淆 | low | 改名 `project_artifacts`（附录 A） |
| L4 PG 时间戳 BIGINT 误判 | low | §4.2 + 附录 A 修正为 INTEGER |
| L5 软外键无校验 | low | T1.3 补存在性校验 · `project_members.user_id` 冗余列 |
| L6 v18 无 `_ensure_*` | low | T1.1 必配幂等 helper |
| L7 引用行号错位 | low | 陷阱 #6 改为 `team_manager.py:571-574`；limit 说明修正 |
| L8 权限键 category 语义 | low | §4.6 显式决策说明 |
| L9 Should/Could 未声明边界 | low | §2.2 逐条声明 |

**误报（未采纳）**：R2「重复造轮子」3 项（artifacts 表 vs 列、timeline vs trajectory、project_rooms vs room 机制）经汇总员回源码推翻，不构成重复造轮子，仅在 L1/L2/L3 作命名与复用参考处理。

## E-2：v2.0 → v2.1 修订对照（闭合复核报告 V1 的 6 条新不一致 + V2 的 4 条部分成立）

> 复核结论：V1「已闭合 27 · 部分闭合 3 · 未闭合 0 · 改错 0」；V2「复核 11 条 · 不成立 0 · 部分成立 4」。

| # | 来源 | 问题 | v2.1 修订位置 |
|---|---|---|---|
| 1 | V1+V2 | **附录 F 第 10–15 项文件目录写错**（skills/agents/gateway/experts → 全在 `tests/unit/db/`；`tests/unit/experts/` 目录不存在） | 附录 F 表格 + 新增 v2.1 修正注 |
| 2 | V1 | **T1.2 验收 grep `'== 17\|: 17'` 会误命中非版本断言**（`max_iters` / `recursion_limit` / `idle_timeout` 共 3 处） | T1.2 验收改为精确正则 + 显式警告 |
| 3 | V1 | **工期阶段小计与任务卡不符**（S2 7≠6.5、S2.5 4.5≠4、M1 14.5≠13.5） | §0 总览 + §0 工期注 + §2.1 + §3 里程碑，统一为 **14.5–16 天** |
| 4 | V1+V2 | **「群里拍板」与 §2.2「IM 不做」表面矛盾** | §2.2 S4 行改写（区分入站/出站）+ §4.5 新增「收益与边界」表 |
| 5 | V2 | **§4.5 `allowed_decisions` 不是配置项（harness 硬编码）** | §4.5 重写：加源码证据、机制事实表、前置校验、步骤 4 落库机制 |
| 6 | V1+V2 | **T2.5 `gateway.run_in_session()` 命名错**（它是会话锁包装器，不是发送路径） | T2.5 重写：改为参照 `infra/cron/delivery.py` 的 `build_harness_request` + `agent_manager.stream` |
| 7 | V2 | **T2.1「整体回滚」不成立**（无跨 repo 共享事务）+ KB 创建前置条件缺失 | T2.1① 重写为**补偿删除** + ⓪ 前置校验 + 强制失败分支测试 |
| 8 | V1 | **§2.1 缺 M16 一行** | §2.1 补「全过程留痕 / 时间线回放 \| **M16**」 |
| 9 | V1 | **§2.2 的 S4 行「已有 IM 线程 ↔ 项目房间绑定」无任务卡** | §2.2 改写为「仅入站不做」，出站归 §4.5 |
| 10 | V1 | **M3「KB 成员授权」未在 S4 显式写出** | §2.2 新增一行「M3 后半句 → 后置 M2 S4」 |
| 11 | V1 | 附录 E 条目数「29」有误 | 附录 E 标题更正为 **30 条** |
| 12 | V1 | 附录 D 开工清单的 grep 命令过期 | 附录 D 改为引用 T1.2 精确正则 |
| 13 | V1 | 附录 F 尾部注释用裸 `\b17\b` 会误命中 | 附录 F 尾部注释改为引用 T1.2 精确正则 |

**复核未发现 blocker 级残留**：3 个 blocker 的实质缺口均已闭合；V1 判定「有条件可开工」，必修项已在本轮全部处理。

---

# 附录 F：迁移号断言 16 处完整清单

| # | 文件 | 行 | 断言写法 |
|---|---|---|---|
| 1 | `tests/unit/db/test_db_pool.py` | 102 | `assert v == 17` |
| 2 | 同上 | 184 | `assert v == 17` |
| 3 | 同上 | 321 | `assert version == 17` |
| 4 | 同上 | 346 | `assert version == 17` |
| 5 | 同上 | 381 | `assert version == 17` |
| 6 | 同上 | 464 | `assert version == 17` |
| 7 | 同上 | 670 | `assert version == 17` |
| 8 | `tests/unit/backup/test_system_archive.py` | 1181 | `assert result["schema_version"] == 17` |
| 9 | 同上 | 1235 | `"runtime_schema_version": 17,` |
| 10 | `tests/unit/db/test_agent_profile_columns.py` | 122 | `assert version == 17` |
| 11 | `tests/unit/db/test_clip_thread_title.py` | 85 | `assert v == 17` |
| 12 | `tests/unit/db/test_published_experts_repo.py` | 30 | `assert v == 17` |
| 13 | `tests/unit/db/test_repo_knowledge.py` | 53 | `assert v == 17` |
| 14 | `tests/unit/db/test_skill_package_icons.py` | 94 | `assert v == 17` |
| 15 | 同上 | 113 | `assert v == 17` |
| 16 | `tests/unit/db/test_skill_packages_repo.py` | 31 | `assert v == 17` |

> ✅ **v2.2 已用真实仓库逐行核实**（clone 自 `TencentCloud/Octop@develop`，HEAD `4c3bf764`）。
> 上表 **16 处 / 8 文件** 与实测完全一致。实测命令与结果：
> ```powershell
> $f = Get-ChildItem tests -Recurse -File -Filter *.py
> $f | Select-String '==\s*17\b' | Measure-Object        # 18 处（含下方 3 处误报）
> $f | Select-String '["'']runtime_schema_version["'']\s*:\s*17\b'   # +1 处
> # 18 - 3（误报）+ 1 = 16 处 / 8 文件 ✓
> ```

> ⚠️ **必须排除的 3 处误报**（实测内容，**不是** schema 版本断言，不要改）：
>
> | 文件:行 | 实际内容 |
> |---|---|
> | `tests/integration/test_agents_api.py:47` | `assert created["max_iters"] == 17` |
> | `tests/unit/agents/test_agent_manager.py:2016` | `assert req["recursion_limit"] == 17` |
> | `tests/unit/browser/test_browser_setup.py:40` | `assert hb_settings.idle_timeout_minutes == 17.0` |
>
> 这正是 T1.2 要求用**带上下文的正则**、而不是裸 `'== 17'` 的原因。

> 🔧 **v2.1 修正（复核 V1+V2 共同发现）**：v2.0 把第 10–15 项散写成 `tests/unit/skills/`、`tests/unit/agents/`、`tests/unit/gateway/`、`tests/unit/experts/` —— **全部错误**（`tests/unit/experts/` 目录根本不存在）。实测确认除第 8–9 项在 `tests/unit/backup/` 外，其余全部在 `tests/unit/db/`。

---

# 附录 G：本机环境实况（2026-09-25 实测，可作为 onboarding 参照）

> 环境已按 §6.1 全部装好并验证。一键脚本：**`D:\nancc\octop\dev-env.ps1`**（点号加载 `. .\dev-env.ps1`）。
> ⚠️ 该脚本必须存为 **UTF-8 with BOM** —— Windows PowerShell 5.1 读无 BOM 的 `.ps1` 会按 GBK 解析中文导致语法错误。

| 组件 | 实测版本 | 安装方式 |
|---|---|---|
| Git | 2.55.0.windows.3 | `winget install Git.Git` |
| GNU Make | 4.4.1 | `winget install ezwinports.make` |
| uv | 0.12.0 | 已有 |
| Python | 3.12.13（uv 托管） | 随 `uv sync` 自动获取（系统 `python` 是商店占位符，不可用） |
| Node | v22.23.2 | 已有 |
| PostgreSQL 服务端 | **17.11** | **Docker 容器 `octop-pg`**（`postgres:17`） |
| PostgreSQL 客户端 | 17.11 | **免安装绿色版**解压到 `D:\nancc\tools\pgsql`（EDB binaries zip，325 MB） |

**PostgreSQL 容器**

```powershell
docker run -d --name octop-pg `
  -e POSTGRES_USER=octop -e POSTGRES_PASSWORD=octop_dev_pw -e POSTGRES_DB=octop `
  -p 127.0.0.1:5432:5432 -v octop-pgdata:/var/lib/postgresql/data `
  --restart unless-stopped postgres:17
```

- 角色 `octop` 是 **superuser** → 满足 `CREATE SCHEMA`（`octop_memory` schema）要求
- `btree_gin` 1.3 已装（octop-memory PG 后端 FTS 依赖）
- 只绑 `127.0.0.1`；这是本地开发库，**若日后对外暴露请改密码**

**测试 DSN**

```powershell
$env:OCTOP_TEST_DATABASE_URL = 'postgresql://octop:octop_dev_pw@127.0.0.1:5432/octop'
uv run pytest -m postgresql -q        # 不带 DSN = 7 skipped；带 DSN = 7 passed
```

**四个必须处理的环境坑（都已修，见 §6.1/§6.2）**

| # | 坑 | 症状 | 修法 |
|---|---|---|---|
| 1 | Makefile 需要 Unix shell | `make` → `CreateProcess(NULL, pwd, ...) failed` | 把 `C:\Program Files\Git\usr\bin` 加进 PATH |
| 2 | 中文 Windows locale = GBK | `tests/unit/db` **18 个失败**（`UnicodeDecodeError: 'gbk' ... 0x92`） | `PYTHONUTF8=1` |
| 3 | git 不读 Windows 系统代理 | `github.com` TLS 被 reset，clone 失败 | 配 git proxy，或走 SSH（本机 SSH **可用**，已配 `~/.ssh/config`） |
| 4 | Git `autocrlf=true` | 工作区被写成 CRLF（上游 96% 是 LF） | `git -c core.autocrlf=false clone`；已 clone 的见 §6.2 ② |

**pre-commit 钩子的时间成本（实测，影响工期估算）**

`git commit` 会触发 `.githooks/pre-commit` → `make precommit`（format-all + lint + typecheck + **testmon 增量测试**）+ 前端构建。

| 路径 | 测试数 | 耗时 | 说明 |
|---|---|---|---|
| `make all`（手动） | **3762** | **3 分 39 秒** | pytest 带 `-n auto`（xdist 并行） |
| `git commit`（钩子） | 894（testmon 选中） | **20 分 11 秒** | testmon 串行，**没有 xdist** |
| 首次提交 | 3735 + 前端构建 | **约 25 分钟** | `.testmondata` 不存在时跑全量 |

> **优化选项**：手动跑 `make all` 绿了之后，用 `SKIP_PRECOMMIT=1 git commit`。保证强度等价（同一套 format-all + lint + typecheck + 全量 test），但快 **5 倍**。
> 注意 AGENTS.md 的红线是「**不要为了提交红测试而跳过钩子**」——上面这个顺序不违反它。是否采用由你决定。

**已知 flaky 测试（与本环境无关）**

`tests/integration/test_trajectory_api.py::test_sse_catchup_refreshes_same_seq_tool_after_history`
用 `asyncio.wait_for(timeout=5)`，14 个并行 worker 抢 CPU 时会超时。
实测：单独跑 1 passed；全量跑第一次 1 failed、第二次 0 failed。**偶发，重跑即可**；排查时可用 `-p no:xdist` 或 `-n 4`。

**基线实测（可作为"改动后没坏"的对照）**

| 命令 | 结果 |
|---|---|
| `make all`（不带 DSN） | 3719 passed, 119 skipped |
| `make all`（带 DSN） | **3727 passed, 111 skipped**（PG 7 项由 skip 转为 pass） |
| `uv run pytest -m postgresql -q` | **7 passed** |
| 耗时 | 全量约 **4–8 分钟**（视并行度） |

---

**计划结束（v2.2）。开工。**

> **修订历史**
> - **v1.0** 初版
> - **v2.0** 按《Octop-计划审查报告》闭合 3 blocker + 8 high + 12 medium + 关键 low（附录 E-1）
> - **v2.1** 按复核报告 V1（文档级）+ V2（技术级）闭合 6 条新不一致 + 4 条部分成立（附录 E-2）
> - **v2.2** 附录 F 用真实仓库逐行核实（16 处确认）；§6.1/§6.2 补入实机验证的 4 个环境坑；新增附录 G（本机环境实况）
> - 复核结论：**无常驻 blocker**；环境已就绪，**可开工**


---

# 附录 H：执行实况（2026-09-27，v2.2 之后）

> 这一节记录**实际做完的部分**与计划原文的偏差。计划正文未逐条改写的地方，以本节为准。

## H.1 已完成并推送（`feature/projects-p0`，8 个提交）

| 提交 | 卡片 | 内容 |
|---|---|---|
| `7858e1b5` | T1.1 + T1.2 | 迁移（**019**，见 H.2）+ 16 处版本断言 |
| `3d7c3b79` | S2 仓储层 | Project / Member / Task repo（按计划附录 C 拆 4 文件） |
| `2f07aaa6` | T2.1 | KB 生命周期（补偿删除）+ 项目状态机 + §4.6 权限矩阵 |
| `c3ac257c` | T2.3 | 任务 CRUD + 任务状态机 + `timeline_events` |
| `9ef2b70d` | **T1.4** | 路由层 + app 注册 + OpenAPI tag + 10 个实体专属错误码 |
| `23bc3a66` | T2.2 | 前端：项目列表 / 详情 / 成员 |
| `a8f808a8` | — | 修复：知识库功能不可用时仍能立项（见 H.3） |
| `c7b57690` | — | 改号 018 → 019（见 H.2） |

**门禁**：`make all` → **3852 passed, 111 skipped**。PG 路径另有三份独立验证脚本。

## H.2 迁移号 018 被上游占用 → 改号 019

计划写的是 `018_projects`。执行期间上游 `develop` 抢走了 018：

```
upstream/develop  9a13f53f
  018_user_role.sql / 018_user_role.pg.sql   ← schema v18 = 角色模板
```

`_discover()` 对重复版本号**直接抛 RuntimeError** —— 两个 018 并存会让**每次数据库操作都失败**（不只是某个测试）。

**改号范围**（`_tools/renumber_018_to_019.py` 一次做完，13 项验证脚本 `_tools/verify_migration_numbering.py` 确认）：

1. `018_projects.{sql,pg.sql}` → `019_projects.{sql,pg.sql}`，水位 18 → 19
2. `_ensure_projects_schema` 读 019 文件对
3. 我方 sqlite 分支 → `if version == 19:`
4. **上游的 `if version == 18:` 与 `_ensure_user_role_schema` 原样保留**
5. 16 处断言 18 → 19（叠加在上游自己的 17 → 18 之上）

> ⚠️ **解冲突时最危险的一点**：`migrate.py` 里两个 `if version == 18:` 因为**位于不同函数**（`_apply_sqlite_migration` 与 `run_migrations`），git **文本上自动合并成功**。表面无冲突，实际第一个分支会吃掉第二个。**必须人工核对，不能只看 git 有没有报冲突。**

## H.3 设计缺口：项目 KB 是「必需」还是「尽力绑定」

**部署到全新 `~/.octop` 时发现的真 bug**：`POST /api/projects` 返回 500 `PROJECT_KB_BIND_FAILED`。

根因：新装 Octop 的 `knowledge_bases_enabled` 默认 **false**，`create_base` 抛 `RuntimeError`；而 T2.1 的 ⓪ 前置校验**只查了权限/数量/重名，没查功能是否可用**。测试漏掉它是因为 fixture 把 `assert_knowledge_usable` 打桩成了 no-op。

**计划自相矛盾**：T2.1 ①③ 要求 KB 失败即补偿删除（暗示必需），但 T3.4 前置写「归档只在 `kb_id IS NOT NULL` 时执行」（暗示可以为 NULL）。

**当前实现**（已在 `a8f808a8` 落地）：

| 知识库功能状态 | 行为 |
|---|---|
| **可用** | 正常绑 KB；③④ 失败仍走补偿删除 → `PROJECT_KB_BIND_FAILED` |
| **不可用** | 项目照建，`kb_id = NULL`，记一条 log |

理由：若强制必需，全新安装**在配好 embedding 模型前建不出任何项目**，T3.4 那句就是死文本。

> **待你裁决**：如果产品上要求「必须先配好知识库才能立项」，把 `create_project` 里 `bind_kb` 为 False 的分支改成抛 `OctopError(KNOWLEDGE_FEATURE_DISABLED)` 即可（一处）。

## H.4 其它实况

- **`git` 只推 `origin`（你的 fork）**；`upstream` 的 pushurl 已设为 `DISABLED` 锁死（`remote.upstream.pushurl = DISABLED`）。
- **pre-commit 钩子成本**：testmon 串行跑 894 个测试要 **20 分钟**；手动 `make all`（xdist 并行全量 3800+）只要 **3.6 分钟**。→ 采用「手动 `make all` 绿 + `SKIP_PRECOMPIT=1 git commit`」。
- **`release/1.0.2b3` 不要合并**：它是 `develop` 的子集（`develop - release = 0` 个提交），唯一提交只改了 CHANGELOG / README / 版本号字符串，**零代码**；且按 AGENTS.md §10 是发完即删的临时冻结分支。
- **本地部署**：`octop init` 后 `octop run --host 127.0.0.1 --port 8088`，SQLite 控制面。`~/.octop` 老库（v18，只有项目表）在重启后**自愈**到 v19 并补齐了上游的 `user_role` 表 —— 这是 `_ensure_*` 幂等 helper 的价值实证。
