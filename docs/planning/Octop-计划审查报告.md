# Octop 计划审查报告（汇总与对抗验证）

> 审查对象：《Octop-总计划与落地开发计划.md》（v1.0，下称「计划」）
> 需求基线：《需求文档-v1.0-正文提取.md》（下称「需求」）
> 源码基线：`Octop-develop` / `octop-harness` / `octop-memory`
> 审查人：synthesizer（汇总与对抗验证员）
> 前置输入：`_review/01-需求覆盖审查.md`、`_review/02-技术事实核查.md`、`_review/03-依赖与排序审查.md`、`_review/04-工程风险审查.md`
> 本报告是本次审查的唯一最终交付物。

---

## 1. 结论摘要

**共发现 32 条问题：blocker 3 · high 8 · medium 12 · low 9。**

**M1 能否按现计划开工：不能。** 计划自述「可直接开工」不成立。按现文执行，第一天就会卡住：

1. **迁移号断言覆盖面被严重低估（blocker）**：铁律 #3 与 T1.2 声称只改 `test_db_pool.py` 的 7 处 `assert v == 17`。实测全仓需同步改 **16 处 / 8 个文件**（含 `assert version == 17` 5 处、`assert v == 17` 4 处、`schema_version == 17` 1 处、`"runtime_schema_version": 17` 1 处等），`make all` 会跑全量测试，只改 1 个文件当天必红。
2. **T1.1 验收命令在 Windows 上跑不通（blocker，低成本修复）**：`rm -f /tmp/t.db` + `Path('/tmp/t.db')` 是 POSIX 写法，且违反计划自身的铁律 #12；任务环境就是 Windows pwsh。
3. **项目 KB 创建/绑定任务缺失（blocker）**：`projects.kb_id` 在 DDL 里可空，但没有任何任务卡负责「立项时创建项目 KB 并回写 kb_id」；T3.4「写项目 KB」与 AC-10 在 kb_id 为 NULL 时必然失败，M1 宣称的「资料归档」闭环断掉。

其余关键结论：Owner 闸门复用 HITL 语义不匹配（应改 `ask_user_question`）；AC-03/AC-04 与 AC-15 三条验收在 M1/M2 均无落点；观察者 viewer 只读语义零落地；ProjectMemory 不建表导致「来源回链 + 创建者」两项硬需求丢失；M1 工期标称 12d、任务卡实加 13.5d。

---

## 2. blocker 与 high 明细

### B1 · 迁移号断言 16 处/8 文件，计划只改 7 处/1 文件 — blocker

- **类型**：D（技术错误）
- **来源**：R2 #2 · R3 D3 · R4 §3.1/§3.3/§7
- **问题**：计划铁律 #3 与 T1.2 均声称「7 处 `assert v == 17`，只改 `tests/unit/db/test_db_pool.py`」。独立 grep 全仓实测，随 `_schema_version` 从 17 → 18 需要同步改动的版本断言共 **16 处 / 8 文件**：
  - `test_db_pool.py`：7 处（`:102`、`:184` 为 `assert v == 17`；`:321`、`:346`、`:381`、`:464`、`:670` 为 `assert version == 17`）
  - `test_system_archive.py`：2 处（`:1181` `assert result["schema_version"] == 17`；`:1235` `"runtime_schema_version": 17`）
  - `test_skill_package_icons.py`：2 处（`:94`、`:113`）
  - `test_agent_profile_columns.py:122`、`test_clip_thread_title.py:85`、`test_published_experts_repo.py:30`、`test_skill_packages_repo.py:31`、`test_repo_knowledge.py:53`：各 1 处
- **证据**：上述断言均为 `SELECT version FROM _schema_version` 后 `assert == 17`（已逐处读源码核实，如 `test_repo_knowledge.py:48-53`、`test_db_pool.py:316-321`）。
- **影响**：`make all` = `pytest -m "not live"` 跑全量，只改 1 个文件会因另 9 处失败 → 第一天「下班前必须绿」破功；§7 检测脚本 `sed "s/assert v == ${MINE#0}/..."` 也漏掉 `assert version ==` 拼写与其余 7 个文件，rebase 时同样会漏改。
- **修复建议**：T1.2 改为「全仓 `grep -rn '== 17' tests/`（并单独搜 `"runtime_schema_version": 17`）逐处改 18」；§7 脚本用统一正则 `assert (v|version|result\["schema_version"\]) == ` 并跨文件处理；铁律 #3 文本从「7 处」改为「16 处/8 文件」。
- **涉及**：计划 §5 铁律 #3、§7 迁移号检测脚本、T1.2 卡、§6.3 基线自检。

### B2 · T1.1 验收命令 POSIX 化，Windows 跑不通 — blocker（低成本修复）

- **类型**：D（技术错误）
- **来源**：R4 §3.3
- **问题**：T1.1 验收 `rm -f /tmp/t.db && uv run python -c "... Path('/tmp/t.db') ..."`。Windows pwsh 下 `rm -f` 不是合法参数（`Remove-Item` 用 `-Force`），`/tmp` 不存在。且此写法违反计划自身铁律 #12（「用 `tmp_path` / `Path`；POSIX 专用加 `skipif`」）与 AGENTS.md §7 交叉平台测试纪律。
- **证据**：计划 T1.1 验收块原文（`rm -f /tmp/t.db`）。
- **影响**：T1.1 是第一天下午的任务，验收命令跑不通即「无法按文开工」。
- **修复建议**：改为 `uv run python -c "from tempfile import ...; db=SqlitePool(Path(tmp))"` 或直接落一个用 `tmp_path` fixture 的 pytest 用例；基线自检 §6.3 的 `grep -c 'assert v == 17'` 期望值一并改为「按 B1 的 16 处口径」。
- **涉及**：T1.1 卡、§6.3 基线自检。

### B3 · 项目 KB 创建/绑定任务缺失，kb_id 无人写 — blocker

- **类型**：C（漏依赖）+ B（漏功能）
- **来源**：R1（M3）· R3 D1 · R4 §一 AC-10
- **问题**：`projects.kb_id`（附录 A DDL）为 `TEXT` 可空。S2 接口契约 `POST /api/projects` 只写 owner 成员行 + 分配 `memory_namespace`，不创建 KB、不回写 `kb_id`。全计划没有任何任务卡负责「创建项目 KB + 绑定 kb_id」。而 T3.4「资料归档（写项目 KB）」与 AC-10（任务转 done 产出进项目 KB）在 `kb_id` 为 NULL 时必失败。
- **证据**：计划 S2 接口契约（`POST /api/projects` 说明）、附录 A `kb_id TEXT`（计划第 613 行）、T3.4 卡、S2.5 AC 表 AC-10；源码侧 KB 创建走 `POST /api/knowledge-bases` 且需 `require_permission("knowledge_bases")` + `assert_knowledge_usable`（R3 已核实，`api/routers/knowledge_bases.py`）。
- **影响**：M1 宣称范围含「资料归档 / AC-10」，但无 KB 绑定前置，T3.4/AC-10 无法验收 → M1 核心闭环断。
- **修复建议**：新增任务卡「项目 KB 生命周期」（立项自动建 KB + 写 `projects.kb_id` + 归档处理），或显式并入 T2.1；在附录 C 补对应产出。
- **涉及**：§2 M1 做清单、S2 接口契约、T2.1/T3.4 卡、附录 A/C。

### H1 · AC-15 缺失 + M13「先文档后代码」评审闸门无落点 — high

- **类型**：A（漏需求）
- **来源**：R1（D4/M13/AC-15）· R4 §一/§二
- **问题**：需求 D4 定义「开发=先文档后代码」、M13 定义「确认后先方案/PRD → Owner 通过 → 再派 ACP」，AC-15 要求「未过方案评审无 ACP 派单入口」。计划 S5（M2）只写「ACP 派单 + commit 回写」，**没有「方案评审 → Owner 通过 → 才放行 ACP」的闸门任务**，AC-15 在两处验收表（S2.5、M2 概要）均未出现。
- **证据**：需求文档 §六 AC-15 原文、计划 S5 概要（「ACP 派单 + commit 回写 + 时间线」）、S2.5 验收表（缺 AC-15）。
- **影响**：D4 的后半段「先文档」约束在计划中无执行落点，M13 核心流程约束静默丢失。
- **修复建议**：在 M2 S5 概要补一张任务卡「方案评审闸门」（confirmed → 派 PRD 类专家出方案 → Owner 通过 → 才开 ACP 派单入口），并补 AC-15 对照测试（未过评审时 UI/API 均无派单入口）。
- **涉及**：计划 §2、M2 S5、验收表。

### H2 · Owner 闸门复用 HITL 语义不匹配 — high

- **类型**：D（技术错误）
- **来源**：R2 #12 · R3 D4
- **问题**：计划设计约束 #5 与 T3.3 用 `HitlPolicy / interrupt_on / resume_hitl / coordinator` 承载「Owner 确认需求节点草案」。但 `HitlPolicy` 的 docstring 明写「Human-in-the-loop approval **before selected tools execute**」——决策对象是**工具调用**（`approve/edit/reject/respond`），而「确认节点草案」是**业务审批**（异步、跨 turn、对象是一份文档），两者语义不匹配。计划没有「把确认节点伪造成工具」的接线设计，且 T3.3 没有任务负责配置/启用 HITL 策略。
- **证据**：`octop-harness/src/octop_harness/security/models.py:47-52`（HitlPolicy docstring）；`ask_user.py` 模块 docstring 说明 `ask_user_question` 是「real implementation is the human」的合作通道，经 `interrupt_on` 含 `ask_user_question` 时被 HITL 中间件拦截、以 `{"type":"respond"}` 决策恢复。
- **影响**：M11/AC-07/AC-08 是 M1 硬门禁，按现设计 T3.3 需要返工；且「群里可拍板」的收益依赖一条计划未定义的接线。
- **修复建议**：T3.3 改为「Owner 拍板走 `ask_user_question`（配 `allowed_decisions=["respond"]`），或在其上扩展确认/驳回决策」，并明确触发条件与 IM 卡片挂载；不要用裸 `HitlPolicy(approve/reject)` 模拟业务审批。
- **涉及**：§4 设计约束 #5、T3.3 卡、§9 陷阱表（若保留 HITL 需澄清接线）。

### H3 · ProjectMemory 不建表导致「来源回链 + 创建者」两项硬需求丢失 — high

- **类型**：A（漏需求）
- **来源**：R1 §2.5.1
- **问题**：需求 M15/§四 定义 ProjectMemory 7 字段，其中 `source_refs[]（comment/task/artifact）` 与 `created_by` 是硬要求（用户故事 20/21「0 提问读到来源」「可追溯来源」）。计划改为「不建表，真源=octop-memory atoms + `projects.inject_version`」。逐能力核对：
  - 「一事一条」「可作废」：octop-memory 原生承接 ✅；
  - **`source_refs[]` 业务回链**：atoms 只有 `quote_event_id`（单一 raw_event 来源）与 `raw_event_ids`，无「comment/task/artifact」映射层，计划未排任何自研映射件 ❌ 丢失；
  - **`created_by`**：atoms 无 owner 列 ❌ 丢失；
  - 「注入版本」：从条目级降为项目级（`projects.inject_version` 单值）⚠️ 粒度降级（AC-11 用项目级可满足，但无法按条增量注入）。
- **证据**：需求文档 §四 ProjectMemory 字段、§五用户故事 20/21、§六 AC-11；R1 已核实 atoms 字段结构（可行性分析结论）。
- **影响**：M2 S3 若照概要实施，用户故事 20/21 不成立，「这条记忆谁写的、来自哪个评论/任务/资料」无法回答。
- **修复建议**：在 M2 S3 概要中补「atoms ↔ 项目实体来源映射层（source_refs）+ 创建者标注」设计，并明确注入版本粒度取舍（条目级 or 项目级需显式决策）。
- **涉及**：计划 M2 S3、§4 架构、附录 A（ProjectMemory 说明）。

### H4 · 迁移 018 建 10 张表，repo 层只覆盖 3 张 — high

- **类型**：C（漏依赖）
- **来源**：R3 D2
- **问题**：T1.3「Repo 层」只定义 `ProjectRepo / ProjectMemberRepo / ProjectTaskRepo`，产出文件只有 `repos/projects.py`。其余 7 张表（`project_comments`、`node_mark_logs`、`requirement_nodes`、`project_rooms`、`project_room_members`、`artifacts`、`timeline_events`）没有任何 repo 任务，附录 C 新增清单也只列了 `repos/projects.py`。而 T2.3、T3.1–T3.5 都要读写它们。
- **证据**：计划 T1.3 方法清单（仅 3 个 class）、附录 C 新增清单、迁移 018 建表清单（10 张表）。
- **影响**：T2.3（任务时间线）、T3.1–T3.5 的实现按现文无 repo 规格可用，实现者会被卡住。
- **修复建议**：T1.3 把 10 张表的 repo 全部列全（或拆到 T3 各卡显式声明产出），附录 C 同步补齐 7 个 repo 文件。
- **涉及**：T1.3 卡、附录 C。

### H5 · AC-03 / AC-04 缺失：讨论线隔离与评论作者/时间无验收 — high

- **类型**：A（漏需求）+ E（风险漏项）
- **来源**：R1 §2.11 · R4 §一/§二
- **问题**：AC-03（M6 独立讨论线发言不污染其他任务）、AC-04（M7 每条评论显示作者+时间、专家产出自动落入对应讨论线）在 S2.5 验收表均未出现。M6/M7 都在 §2「M1 做」清单内，却没有任何任务卡或验收条目对应。
- **证据**：计划 S2.5 验收表（只列 AC-05/06/07/08/10/12/14，无 AC-03/AC-04）；需求 §六 AC-03/AC-04 原文。
- **影响**：讨论线隔离与「专家产出自动落讨论线」是 M6–M8 闭环底座，无验收即不可证；与 H2（专家回写）叠加，M7 闭环断裂。
- **修复建议**：在 T3.1 补「讨论线隔离测试」与「评论作者/时间显示 + 专家产出回写 project_comments 接线」，并把 AC-03/AC-04 加回 S2.5 验收表；时间显示须遵守 H7 时区纪律。
- **涉及**：T3.1 卡、S2.5 验收表。

### H6 · 观察者 viewer 只读语义零落地（权限矩阵缺失）— high

- **类型**：B（漏功能）
- **来源**：R1 §2.4/§2.5
- **问题**：需求 §二 观察者「只读」、G7「成员仅见其权限内数据」。DDL 有 `role='viewer'`，但计划无权限矩阵、无「viewer 对 PATCH/DELETE/打标/确认等写接口一律 403」的验收；AC-13 只覆盖「非成员拒绝」，不覆盖「成员内 viewer 只读」。同理，「项目管理员 admin 除归档/删除外」的边界（与 owner 的差异）也无接口级实现与测试。需求「下一步」第 1 条要求的「权限矩阵」交付物计划未产出。
- **证据**：需求 §二 角色表（观察者=只读、管理员=除归档/删除外）、G7、下一步第 1 条；计划 §2 M1 做清单（仅列四角色）、AC-13 条件（仅「非成员拒绝」）。
- **影响**：「上级/客户只读」能力静默降级为「存在但不可证」；admin 与 owner 同权违反需求。
- **修复建议**：补权限矩阵（owner/admin/member/viewer × 各写接口），service 层显式校验 + 测试；在 S2 验收补「viewer 写操作 403」「admin 不可归档/删除」用例。
- **涉及**：§2 M1 做清单、S2 验收表、T1.4/T2.1 卡。

### H7 · 时区纪律缺失（铁律无时区项）— high

- **类型**：E（风险漏项）
- **来源**：R4 §3.1 G6
- **问题**：AGENTS.md §7 Timezone 要求「用户可见时间必须用 `default_timezone` / `formatServerDateTime`，禁裸 `toLocaleString`」。计划 §5 十二条铁律未列时区纪律，而 AC-04（评论时间）、AC-12（时间线）都要显示时间，违反即为平台不合规。
- **证据**：`Octop-develop/AGENTS.md` §7 Timezone 段落；计划 §5 铁律清单（无时区项）。
- **影响**：前端时间显示若用裸 `toLocaleString()`，会随用户浏览器时区漂移，与后端时间线（BIGINT/INTEGER 时间戳）不一致。
- **修复建议**：§5 铁律补一条「时区纪律」，T2.4/T3.1/T3.5 明确用 `formatServerDateTime`/`formatMessageTime(..., timeZone)`。
- **涉及**：§5 铁律、T2.4/T3.1/T3.5 卡。

### H8 · M1 工期标称 12d，任务卡实加 13.5d — high

- **类型**：E（风险漏项）
- **来源**：R4 §五
- **问题**：计划 §3 标称 M1=12d（S1 3d + S2 6d + S2.5 3d），但任务卡逐项相加：S1=3d、S2=6.5d（T2.1–T2.6 之和）、S2.5=4d（T3.1–T3.5 之和）= **13.5d**。叠加 16 处断言返工、AC-03/04 缺失测试、T3.3 HITL 接线偏紧，独立估算 13.5–15d，少算 1.5–3d（12%–25%），且未预留 rebase 缓冲（§7 自述每次 0.5–1h）。
- **证据**：计划 §3 里程碑表 vs S2/S2.5 任务卡预估（T2.1=1.5、T2.2=1.5、T2.3=1、T2.4=1.5、T2.5=0.5、T2.6=0.5；T3.1–T3.5=1/1/1/0.5/0.5）。
- **影响**：里程碑承诺失真，排期与验收口径不一致。
- **修复建议**：§3 里程碑 S2 改 6.5d、S2.5 改 4d、M1 改 13.5–15d；或削减任务卡口径并显式声明。
- **涉及**：§3 里程碑、S2/S2.5 任务卡。

---

## 3. medium 明细

| 编号 | 类型 | 问题 | 证据 | 修复建议 |
|---|---|---|---|---|
| M1 | E | §8 风险登记册（R1–R10）与需求 §七（R1–R10）是两套编号，非 1:1；R5（WeKnora 只读）、R7（记忆膨胀）、R8（token 失控）、R10（ACP runner 可用性）未显式登记或应对缺失 | 计划 §8 vs 需求 §七 逐条比对 | §8 加「需求 §七 对应」列，补登记 R5/R7/R8/R10 及应对 |
| M2 | A | M10「虚拟团队（专家群）产出草案」无机制设计；「Leader=普通专家」硬约束未写入计划正文；草案「验收标准」字段无落库（`project_tasks` 无 acceptance 列） | 需求 §二 硬约束提醒、§三 M10；计划 T3.2 | T3.2 写明 Leader 身份与草案产出/落库路径，验收标准字段落点（description 或新增列） |
| M3 | A | 遗留 Q6（IM 回流）、Q7（专家资产）、Q9（多项目并行）、Q10（节点粒度）悬空；其中 Q7/Q10 直接影响 M1 的 M10/M12/M9 实现口径 | 需求 §九 Q6/Q7/Q9/Q10 | 在计划补一节「遗留问题裁决」，至少对 Q7/Q10 给出 M1 口径 |
| M4 | D | 「讨论线复用 `thread_messages`」表述掩盖事实：`threads` 单 agent（`agent_id NOT NULL`），多参加者讨论必须落 `project_comments` + 多个 thread；计划未显式写明，易被误读为一条 thread 装下整条讨论线 | `001_initial.sql:133-136`；计划设计约束 #3 | §2/S2.5 显式写明「讨论线 = task.thread_id 对话流 + project_comments 结构化评论」双层模型 |
| M5 | C | 附录 C 文件清单遗漏：前端测试 `useSessionInbox.test.ts`/`SessionList.grouping.test.tsx`（T0.4 产出）不在新增清单；`infra/projects/nodes.py` 在清单但无任务卡声明产出（应归 T3.2） | 计划附录 C vs T0.4/T3.2 | 附录 C 补齐遗漏文件，nodes.py 挂到 T3.2 |
| M6 | E | §6 开工前准备缺：Python 3.12/uv/Node/make 可用性、PG 连通性、pg_dump 可用性、PG 账号 CREATE SCHEMA 权限 + btree_gin 扩展检查 | 计划 §6.1/§6.3 vs AGENTS.md §6 | §6 补 4 项前置自检（环境链 + PG 链） |
| M7 | D | §6.1 clone 到 `D:/nancc/octop-fork`，与计划全部文件链接/审查源码所在 `D:\nancc\octop\Octop-develop` 不一致，照做会开出对不上的目录 | 计划 §6.1 vs 全文链接 | 统一 clone 路径 |
| M8 | A | Project 状态机（draft→active→paused→archived）只有枚举，无流转规则/验收（paused 进入/恢复条件） | 需求 §四 Project 状态机；计划附录 A status 注释 | T2.1 补 Project 状态流转校验与测试 |
| M9 | E | 验收命令/标准缺客观断言：`grep -c 'assert v == 17' 期望 7` 实测 2（v vs version）；AC-02「一屏尽览」、AC-05「1 次刷新内」、AC-14「30s」均无阈值/工具/断言 | 计划 §6.3、S2/S2.5 验收表 | 验收改统一正则；AC 补可执行判定（性能基准或人工步骤） |
| M10 | B | M3「绑定项目知识库（KB 成员）」落空：`knowledge_base_members` 表在 v7 已 DROP，计划只有「写项目 KB」与 `is_shared` 复用，无「项目 KB 成员授权」任务（M2 范围） | `007_*.sql:20` `DROP TABLE IF EXISTS knowledge_base_members`；计划 M2 S4 | S4 补「项目 KB 成员授权模型 + 绑定 kb_id」任务 |
| M11 | C | T2.5 派单未指明具体端点：建 thread 走 `ThreadManager.create_thread` 还是 `POST /api/agents/{id}/threads`；发消息无简单 REST 端点（dashboard 走 WS）；纯 agent（非 team）的服务端发送路径未定义 | 计划 T2.5 要点 vs `chat/history.py:213`、`chat/ws.py:32` | T2.5 写明内部调用链并区分「派 agent / 派 team」两条路径 |
| M12 | C | T2.5 间接触及 `infra/agents/teams`（读依赖不编辑），上游重构签名变动风险未在 §8 单独登记 | R3 哈希比对 + 更新日志 | T2.5 对 team room 调用封装小门面，§8 补一条接口变动风险 |

---

## 4. low 明细

- **L1（D/F）**：自建 `artifacts` 表与上游 `threads.artifacts` 列同名（不同名域，非 SQL 冲突，但概念易混）。建议改名 `project_artifacts` 并声明它引用 `threads.artifacts` 路径。证据：`007_*.sql:19`、计划附录 A artifacts 表。
- **L2（F，非真正重复）**：自建 `timeline_events` 与上游 `trajectory_events`/`audit_log` 语义不同（前者是项目任务时间线，后者是 agent 轨迹/安全审计），但可参考其 `(thread_id, seq)` 与 `actor/action/target/payload` 形状，避免另起炉灶。
- **L3（F）**：`project_rooms` 的 `project_id` 关联是新增能力，但 room 生命周期/投影可复用既有 `room~member` 机制（`peer_room_thread_id`），不必重造。
- **L4（D）**：「时间戳列用 BIGINT」非仓库统一约定——`001_initial.pg.sql` 的 `created_at` 多为 `INTEGER NOT NULL`（如 `:18`、`:39`、`:56`）。计划把 BIGINT 当「PG 版统一差异」是误判，建议与同库新表风格对齐或显式说明。
- **L5（D）**：多态列 `project_members.subject_id TEXT` 等与用户整数 id 混用，多处软外键（`project_tasks.parent_id/thread_id` 等）未声明 FK。建议 member 表对 user 单列 `user_id INTEGER`，软外键在 Repo 层补存在性校验。
- **L6（D）**：迁移 v18 无幂等 `_ensure_*` helper（`migrate.py` 只到 v17 有分支，v18 落到 `executescript` 兜底），且 DDL 用裸 `CREATE TABLE`。建议 v18 配 helper 或用 `CREATE TABLE IF NOT EXISTS`。
- **L7（D）**：计划引用两处错误：`team_manager.py:534` 实为 `install_host_dispatch` docstring（`peer_invoke_mode`/sync 降级在 `:571-574`）；「CHANGELOG 说 1–200」实为 `history.py:102` `limit: int = 50`。
- **L8（D）**：`projects` 权限键放 `category=settings` 会进入 `BASELINE_PERMISSIONS`（`permissions.py:222`），新用户默认获得该键。粗粒度门不受影响（数据仍靠 project_members join），但应意识到该语义；若项目数据敏感建议改 `control`/`admin`。
- **L9（A）**：Should/Could 后置项未显式声明边界——S1/S2/S3/S5/C1/C3/C4 未覆盖且未写「不做/后置」；S4「群讨论回流」既未做也未声明不做。建议在 §2 非目标清单补一行，避免台账悬空。

---

## 5. 误报清单（被推翻/纠正的发现）

1. **R2「迁移号断言 14 处 / 7 文件」→ 纠正为 16 处 / 8 文件**。R2 漏计 `test_system_archive.py` 的两处（`:1181` `schema_version == 17` 与 `:1235` `"runtime_schema_version": 17`，后者是 `: 17` 不是 `== 17`，故 R2 的 grep 漏掉）。R3/R4 的「16 处/8 文件」正确，本报告 B1 采用 16 处。

2. **R2「重复造轮子 4 项」中 3 项判定为过度表述，已降级/纠正**：
   - 「自建 artifacts 表 vs `threads.artifacts` 列」——两者是**表 vs 列**，不同名域，SQL 上不冲突，属命名混淆（L1），不是「重复造轮子」。
   - 「自建 timeline_events vs trajectory_events/audit_log」——语义不同（项目任务时间线 vs agent 轨迹/安全审计），并非可互换的重复（L2）。
   - 「project_rooms vs room~member」——`project_id` 关联是新增，room 机制只是可复用参考（L3）。
   - 仅「Owner 审批应改 ask_user_question、而非扭曲 HITL」成立（H2）。

3. **R1「AC-09 记忆条目删减 / AC-12 记忆变更删减 = 部分覆盖损失」→ 纠正为「M1 合理裁剪，非丢失」**。项目记忆整体后置 M2 是计划明确决策（§2 M1 不做），真正的问题是**未显式声明裁剪**（属 L9），不应计为「功能丢失」。

4. **R1「S1/S2/S3/S5/C1/C3/C4 未覆盖」→ 判定为「合理后置」**。S1（节点去重）、S2（看板统计）、S3（催办）、S5（模板）与 C1/C3/C4 均为需求 Should/Could 级，不排入 M1/M2 属正常取舍，仅建议显式声明边界（L9），不构成漏项。

5. **（主动推翻尝试，未推翻）B1「16 处断言」**：曾试图验证「其余 9 处是否会因 bump 到 18 而失败」——逐处读源码确认均为 `SELECT version FROM _schema_version` 后断言 `== 17`，bump 后必失败，故保留为 blocker。

---

## 6. 对计划的具体修订建议（按章节，可直接照改）

### §5 铁律
- 铁律 #3：`迁移号断言 7 处` → `迁移号断言 16 处（8 文件）`，并列出文件清单。
- 新增一条铁律：**时区纪律**（用户可见时间用 `default_timezone`/`formatServerDateTime`，禁裸 `toLocaleString`）。
- 可选补：模块边界硬禁（`infra/`→`api/` 等，AGENTS.md §5）、不改 `src/octop/dashboard/` 构建产物、API docs 可读性（summary/response_model）、ErrorCode 前后端镜像同步。

### §6 开工前准备
- 6.1 环境：补「Python 3.12 / uv / Node / make（Git Bash）/ PG 连通 / pg_dump 可用 / PG 账号 CREATE SCHEMA 权限 + btree_gin」检查；统一 clone 路径为 `D:/nancc/octop/Octop-develop`（与文档链接一致）。
- 6.3 基线自检：`grep -c 'assert v == 17'` 改为全仓 16 处口径。

### §7 上游同步纪律
- 检测脚本 `sed` 改为统一正则 `assert (v|version) == ` + `schema_version` + `"runtime_schema_version"`，跨 8 文件处理；「改 7 处断言」→「改 16 处断言」。

### §8 风险登记册
- 加「需求 §七 对应」列，补 R5/R7/R8/R10；补 T2.5 对 `infra/agents` 接口变动风险。

### T1.1 / T1.2 / T1.3 卡
- T1.1 验收去 POSIX 化（`tmp_path`/tempfile）。
- T1.2 改「全仓 16 处 / 8 文件」，验收用统一正则。
- T1.3 列全 10 张表的 repo（或拆到 T3 各卡），附录 C 补齐 7 个 repo 文件。

### T2.1 / T2.5 / T3.1 / T3.3 / T3.4 卡
- T2.1：补「项目 KB 生命周期」（建 KB + 写 kb_id）；补 Project 状态机流转校验。
- T2.5：写明建 thread / 发消息 / 非 team 路径的调用链，区分「派 agent / 派 team」。
- T3.1：补讨论线隔离测试 + 评论作者/时间显示 + 专家产出回写 project_comments（对应 AC-03/AC-04）。
- T3.3：HITL → 改 `ask_user_question`（respond 决策），明确触发条件与接线。
- T3.4：前置声明 kb_id 已绑定（依赖 B3 的新任务）。

### §2 范围界定
- M1 不做清单补：S4 群讨论回流（做/不做决策）、S1/S2/S3/S5/C1/C3/C4 后置声明、AC-09（记忆条目）/AC-12（记忆变更）的 M1 裁剪声明。

### M2 S3 / S5 概要
- S3：补「atoms ↔ 项目实体来源映射层（source_refs）+ created_by」；补连接泄漏回归测试（`pg_stat_activity`）、`max_connections` 数值与超限策略；补 AC-11 验收（inject_version +1）。
- S5：补「方案评审闸门」任务卡 + AC-15 对照测试；补 R10 健康检查/失败回退人工 + 时间线留痕。

---

## 7. 审查方法与覆盖度说明

### 审了什么
- **四份上游报告全量合并去重**：R1（131 条需求覆盖矩阵）、R2（19 条技术事实核查）、R3（8 依赖 + 4 写冲突 + rebase）、R4（AC 映射 + 门禁 + PG + 工期）。
- **独立对抗验证**（不采信报告结论）：对 B1（迁移断言数）、H2（HITL 语义）、H4（repo 覆盖）、B3（kb_id 无任务写）、L4/L5/L6/L7（PG 时间戳/软外键/迁移 helper/引用行号）逐条回到源码核实；对「重复造轮子」等定性判断做了推翻性审查。关键核实点：
  - `grep '== 17' tests/` 全仓 → 16 处/8 文件（含 `test_system_archive.py:1181,1235`）；
  - `HitlPolicy` docstring（`security/models.py:47`）与 `ask_user.py` 机制；
  - `threads.agent_id TEXT NOT NULL`（`001_initial.sql:136`）、`threads.artifacts` 列（`007_*.sql:19`）；
  - `team_manager.py:534`（install_host_dispatch）与 `:571-574`（sync 降级）；`history.py:102`（limit=50）；
  - `001_initial.pg.sql` 时间戳用 INTEGER；`migrate.py` v16/v17 有 `_ensure_*`、v18 无；
  - `knowledge_base_members` 在 `007_*.sql:20` 被 DROP。

### 没审 / 局限
- 未逐条核对 R1 的 131 条覆盖矩阵每一格（只对 top 项与结论做抽样复核）；覆盖统计（69/44/13/5）沿用 R1。
- 未实际执行 `make all` / 迁移（环境未装 Git/uv/PG），迁移断言数基于静态 grep，行为级验证（bump 后确实全红）是推断而非实跑。
- PG 专项（DSN 复用、octop_memory schema、连接预算）沿用 R4 已核实结论，未独立重复全部源码走查。
- 未审查 harness 补丁（S4 `bind_peer_scope`）的插入位置正确性（R2 #19 已判成立，本报告未复核）。
- 「430+ 测试」「上游 15 commits/天」等经验性数字无法从源码核实，未计入发现。

---

**报告结束。**
