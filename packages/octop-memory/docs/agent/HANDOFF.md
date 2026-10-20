# HANDOFF.md

代码相关任务的文本澄清与接续入口。使用 Issue / PR 编号或简短标题识别任务，不以日期建流水账。
有 Issue / PR 时链接正文，只在这里保留状态、关键结论和下一步；未开 Issue 时直接使用下方模板。
已完成记录压缩或替换，稳定知识移入对应文档，历史由 Git / Issue / PR 保存。

## 任务模板

- **任务 / 状态 / 链接**：待澄清 → 可实现 → 进行中 → 待验证 → 完成；阻塞时写明原因。
- **问题与场景**：bug 的实际/预期行为及最小复现；新需求的使用者、场景和期望结果。
- **范围与验收**：要做/不做、可验证条件、兼容性及数据影响。
- **待澄清 / 假设**：哪些已确认，哪些影响实现；不能把未回答的问题记成确认。
- **方案与关键文件**：最小实现、受影响调用链；重要取舍链接 DECISIONS。
- **验证**：确切命令、实际结果、失败/skip/未覆盖，必要时附脱敏证据。
- **接续**：当前进度、未解决风险、下一步；受影响文档是否同步。

## 当前任务

### 手动档案与普通记忆协同（PR #20 / harness #76 / Octop #2103）

- **状态 / 场景**：三个仓库实现、验证和配套宿主提交已完成。用户明确要求 USER.md 与 MEMORY.md 只由用户修改；冲突时手动文档优先，通知用户并降级到 Candidate 更新 octop-memory。
- **范围与验收**：复用既有 retention/runtime/promotion/recall 模块，无新 source 模块或 schema；原文引用校验，软停用冲突旧 Atom，替代事实候选保留两侧证据；重复 Atom 仅按实际聊天快照抑制召回；无模型/不确定不强制停用。低层 Memory.store 仍是原始存储 API；宿主通过 Service provider 或显式核对启用治理。
- **方案**：见 ADR-042 / PROJECT_MAP。完整文档只保存对账元数据，不全文导入/索引；小型召回清单参与 cache key，阻止旧 raw/dirty headline 回流。候选采纳校验对账版本，Octop 同时提交当前文件，拦截保存后尚未核对的版本变化。单次 100 条未核对 Atom 可续查。
- **验证**：`TEST_POSTGRES_DSN='dbname=octop_memory_retention_test' make all RUN='.venv/bin/python -m'` format/lint/strict mypy 通过，1483 passed / 4 skipped；真实 PG 均运行。专用 PG 与 SQLite 手动文档同组用例 8 passed；新增单测覆盖模型缺失/伪造/不确定、事务回滚、旧版本采纳、save/自动晋升、分批续查和 recall cache 隔离。四项 skip 为已有可选环境，非 PG。
- **配套 / 接续**：harness 的文件工具写保护覆盖 USER.md/MEMORY.md，规则回归 AGENTS.md/BOOTSTRAP.md，原生统一 session 快照不变；Octop 复用强记忆编辑器新增用户档案、核对提示与候选跳转，支持停止 Agent。既有用户模板不会自动覆盖；外部宿主及旧版本候选处理边界见 KNOWN_RISKS。

### Octop #2060：多 agent 文件描述符与 PostgreSQL 连接容量

- **状态 / 链接**：SQLite 与 PG 实现、本仓和宿主验证完成，待审阅及发布；[Octop#2060](https://github.com/TencentCloud/Octop/issues/2060)、[memory PR#19](https://github.com/TencentCloud/octop-memory/pull/19)。
- **问题与场景**：SQLite 按线程缓存连接，常驻 worker 接触多个 agent 后保留“线程 × agent”条连接；69 个实例可耗尽 1024 fd，旧 close 还会打断在途事务。PG 每 agent 一条业务连接加独立 checkpoint 池，69 个活跃实例达到 138 条会话；真实 PG `max_connections=100` 时第 31 个 checkpoint 超时，空闲回收挡不住活跃峰值。
- **范围与验收**：SQLite 每 backend 一条连接，完整 SQL/事务共用可重入锁，close 等待且不重开。PG 同一进程与连接配置共享业务 8 条、checkpoint/维护 4 条预算，显式事务保留一条连接；checkout 有界等待，关闭一实例不影响其它实例，最后引用关闭池。SQLite checkpoint 仍独立；schema、召回 source/排序和 public API 不变。
- **方案与关键文件**：`storage/backends/sqlite.py` 的操作锁与失败回滚；内部 vacuum/WAL truncate/export 遵守锁。`postgres_pool.py` 管理共享池、引用租约与初始化串行；`postgres.py` 借用连接，`core.py` 失败时释放 checkpoint 租约，导出与 PG 维护进入池预算。取舍见 ADR-039/040。
- **验证**：使用专用 `TEST_POSTGRES_DSN` 执行 `make all RUN='uv run --offline --no-sync'`，format、lint、strict mypy 均通过，pytest 为 1420 passed / 4 skipped；真实 PG 用例均运行。跳过项为 Linux `/proc`、两项 Hermes checkout E2E 和 dashboard extra。新增真实 PG 容量、排队/超时恢复、坏连接探测、空闲回收、初始化失败、跨 agent 事务与幂等关闭断言替代旧连接私有字段 mock。Octop 加载新源码的定向联调 95 passed，包含 6 项真实 PG 维护测试。
- **宿主容量复现**：SQLite 69 个真实 MemoryRuntime 在 soft NOFILE=1024 下，4/8 worker 访问及 30 次重建维持 348 fd，全部关闭回到 3。PG 在服务端 100 连接、进程 1024 fd 限制下，69 个真实 MemoryRuntime 创建/全部 checkpoint 预热分别仅占 1/2 条会话，8 worker 混合访问峰值 12；30 次重建不增长，关闭一个实例后其它实例仍可用，全部关闭会话归零且 fd 回到 3。
- **接续**：CI/release 已配置专用 PG，显式测试 DSN 不可用时失败。无数据迁移；慢 SQL/长事务会占用池，饱和明确报错。预算按进程与连接配置计数，宿主控制面另计。发布后 Octop 需更新 memory 依赖才能消费修复。PROJECT_MAP、DECISIONS、TEST_MATRIX、KNOWN_RISKS 与中英文 README 已同步。

### 系统运行报错的记忆隔离（PR #20）

- **状态 / 用户决策**：最小实现与完整验证完成。主动记忆由 Agent 自行调用 memory_save；删除记忆意图和排障价值关键词，在线报错仅按结构化来源排除，存量来源不明保留待人工审核。
- **范围与验收**：只改 `domain/retention.py`、`application/runtime.py`、`operations/retention.py` 三个既有源码模块。移除短消息意图例外，不改变长度阈值；memory_save 的手工保存不受后台采集长度限制。capture / 两类 extractor / promotion / raw recall 复用仅结构化来源规则。没有新模块、schema、前端或 retry 策略变更。
- **治理边界**：自动停用须全部引用证据均为结构化错误；人工保存/批准/编辑由来源保护。旧版严格报错信封仅在存量 operations 生成审核提示；缺失/混合来源返回 `review_atom_ids` / `review_candidate_ids`，即使 apply 也不改变这些记录的状态，不自动新增 UI 待办。不删除原始证据。见 ADR-012/041、KNOWN_RISKS。
- **验证**：先用新增用例复现旧行为（6 failed / 3 passed），修改后定向 154 passed / 1 optional skip；SQLite/真实专用 PostgreSQL 同组治理 28 passed（PG 未 skip），覆盖未知来源保留、结构化停用、无意图词保存、原证据、幂等与事务回滚。配套 harness 记忆工具/中间件/重试检查 60 passed。`TEST_POSTGRES_DSN='dbname=octop_memory_retention_test' make all RUN='.venv/bin/python -m'` format/lint/strict mypy 通过，1504 passed / 4 optional skips，真实 PG 全部执行；文档/架构检查 41 passed。
- **接续**：现有工作区文档和手动记忆协同保持原行为；PROJECT_MAP / DECISIONS / TEST_MATRIX / KNOWN_RISKS / README_AUDIT 与中英文 README 已同步。不会自动回滚已有人工决策或运行生产数据治理。

### Octop 命名收尾

- **状态**：命名清理完成；真实 PostgreSQL、Hermes checkout 和 dashboard 可选环境未验。
- **问题与场景**：发行包已更名，宿主示例、评测数据、迁移说明和 portable 扫描路径仍有旧项目名称。
- **范围与验收**：源码、测试、评测及文档统一使用 `octop-memory` / `octop-harness`；全仓检查两者旧名称及分隔符变体无残留。保留现有 README 改动，不改持久化编码、表名或包格式，不搬移用户数据库。
- **方案与关键文件**：更新 `service.py` 的宿主说明、portable `models.py` 的 Agent 扫描路径、CLI help 和迁移指南；测试使用临时目录验证默认发现和显式扫描旧位置。删除旧包目录中未使用的生成版本文件；修正 portable dry-run / recall 测试的默认用户库访问，补全 `_PKG_ERRORS` 的类型标注以通过 strict mypy，异常捕获范围不变。
- **影响**：portable 改为发现 `~/.octop-harness/*/memory.sqlite`；旧位置需显式提供 `extra_paths` 或先迁移目录。主召回 source/排序、事实写入与双 backend 数据契约不变。
- **验证**：相关测试 183 项通过；fixture 修复后的 portable/recall 子集 32 项通过。`PYTEST_ADDOPTS=-rs make all RUN='.venv/bin/python -m'` 通过 format、lint、strict mypy，pytest 为 1268 passed / 132 skipped（129 项 PostgreSQL 不可用、2 项缺少 Hermes checkout、1 项缺少 dashboard extra），不代表这些环境通过验收。`uv build --offline` 构建 wheel/sdist 成功；源码文件名、内容及构建包的旧名称检查无残留。OpenClaw 的 `npm test` 启动器因沙箱 IPC 限制失败，改用 `node --import tsx --test src/*.test.ts` 后 67 项通过，`npm run typecheck` / `npm run build` 通过。`ruff check evals examples` 和 routing 数据集 JSON 解析通过。
- **接续**：PROJECT_MAP / TEST_MATRIX / README_AUDIT 与集成指南已同步，KNOWN_RISKS 移除已修复的测试默认库访问项。需要环境验收时，配置专用 `TEST_POSTGRES_DSN`、Hermes checkout 与 dashboard extra，再运行 TEST_MATRIX 对应命令；本次未更改 backend SQL、事务或持久化协议。
