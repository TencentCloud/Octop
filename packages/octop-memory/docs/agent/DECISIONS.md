# DECISIONS.md

保留历史 ADR 编号，压缩为对外可用的设计依据；省略私人样本、部署记录与日期。
Accepted 表示当前设计选择，不表示所有环境均已验证；验证缺口见 [KNOWN_RISKS](KNOWN_RISKS.md)。
新决策记录「背景 → 选择及理由 → 替代方案/代价 → 复核条件」，必要时标明 supersedes，禁止静默覆盖旧约束。

## ADR-001：Memory / MemoryBackend 边界（Accepted）

上层需要可替换存储；公共存储 API 集中于 `Memory`，backend 以 Protocol 约束并 lazy import。
避免上层直接依赖 SQL 和可选依赖；代价是两种 backend 都要维护同一 contract，扩展 API 时复核。

## ADR-002：RawEvent 是派生记忆证据（Accepted）

L0 append-only，Candidate/AtomCard 保留 raw refs 和原文引用，支持追溯与重新提炼。
不以模型改写替代高价值原文；代价是证据存储与隐私留存需单独管理，调整 retention 时复核。

## ADR-003：Extractor 无持久化副作用（Accepted）

`CandidateExtractor.extract()` 返回结果，由 caller 决定入库；LLM/parse failure 返回 `failure_reason`。
便于测试、检查与重试；代价是 caller 必须处理失败，不能把空结果一律当作成功。

## ADR-004：规则优先的 Promotion（Accepted）

按 value → evidence → entity → duplicate → conflict 执行，首个 terminal outcome 生效，歧义才使用 LLM。
避免每条候选都调用模型；代价是规则与状态映射需要共同验证。新增自动晋升条件时复核 demotion-only 边界。

## ADR-005：事实 append + deprecate（Accepted）

创建新 Atom，用 `superseded_by` / `deprecated_at` 使旧事实失效，默认查询排除失效事实。
不原地覆盖 assertion，以保留关系与审计；代价是历史存储和并发替换控制，人工修正见 ADR-034。

## ADR-006：EntityPage 独立存储（Accepted）

Entity 与页面分表，page 有 dirty/version/regen 状态，失败保留旧内容，保护 `## My Notes`。
避免热索引读取大正文与模型覆盖人工笔记；代价是异步更新可能暂时陈旧，修改 regeneration 时复核。

## ADR-007：独立笔记树（Superseded by ADR-010）

曾把 tree 与 pipeline 事实分开，并将 leaf 作为独立召回 source；该方案已被单一事实源替代，不作为当前实现规则。

## ADR-008：宿主 shell 复用 Python runtime（Accepted）

OpenClaw 用 TypeScript + stdio JSON-RPC bridge，Hermes 在进程内复用 Bridge handler。
不维护第二套记忆算法或额外网络 daemon；代价是解释器、进程和协议生命周期需验证，见[集成指南](../integrations.md)。

## ADR-009：有版本的 JSONL 迁移（Accepted）

首行 header、记录 envelope 和依赖顺序支持流式导入/导出；不直接复制 backend 私有 SQL 数据。
代价是新字段与格式升级需要明确兼容规则，修改 export/import 时复核。

## ADR-010：AtomCard 为事实真源（Accepted；替代 ADR-007）

leaf 只存 `atom_id`，读取 JOIN atom assertion；manual store、promotion 和 direct atom write 共用事实链。
Entity 对应组织 branch；tree 不再是独立召回 source。避免事实双写，代价是 leaf 生命周期依赖 atom。
召回 source 的当前条件见 [PROJECT_MAP](PROJECT_MAP.md)，不沿用历史“只有 atom/raw”的绝对表述。

## ADR-011：hybrid context 由 host 提供（Accepted，真实 host 待验证）

OpenClaw 在 prompt build 前调用可选 `recallPrefetcher`，把结果交给同步 promptBuilder。
不从 `agent_end` 补本轮上下文；代价是依赖 host 实际调用 hook，SDK/host 升级时复核。

## ADR-012：capture 兼容短 CJK 消息并剥离 think（Accepted）

共享 capture policy 使用 CJK 加权长度，在判长与入库前剥离 `<think>`；不再按显式记忆意图关键词给短消息放行，主动保存由 Agent 调用 memory_save。
避免各宿主重复实现过滤与推理文本回灌；代价是边界消息可能被过滤，修改阈值时验证多语言样本。

## ADR-021：分层目录与共享 MemoryRuntime（Accepted）

采用 adapters → application → pipeline/core/storage/ports/domain，service 不依赖 bridge，storage 不依赖 pipeline。
旧内部路径不保留 shim，避免两套结构长期共存；代价是内部 import 使用者需要迁移。
未来稳定 extension API 应单独定义，不能推导为允许破坏现有 public API。

## ADR-022：checkpoint 裁剪独立于记忆 GC（Accepted，安全条件由 ADR-029/036 补充）

执行态清理与事实 lifecycle 分开，不为每条删除新增 journal，避免清理一张表却撑大另一张。
代价是需要独立统计与恢复依赖验证；不能把删行、历史裁剪和物理回收视为同一操作。

## ADR-023：extract_run 心跳合并（Superseded by ADR-028）

历史方案按 session 合并 quiet journal；现在改写 meta，心跳配置不再控制 journal 写入。

## ADR-024：SQLite journal target 使用 partial index（Accepted）

target 字段大量为空，使用 `WHERE col IS NOT NULL`，通过 schema 内省幂等迁移。
不加列或拆表；查询语义不变，代价是旧索引重建需要时间，修改 journal 查询时复核覆盖。

## ADR-025：按意图提供空间维护入口（Accepted）

`check_storage` 只读检查，`nudge_vacuum` 轻量回收，`compact_vacuum` 重型整理；按 backend 实现。
避免调用者依赖 backend 术语；代价是锁、空间与共享表范围不同，普通 PG VACUUM 也不能承诺无锁等待。

## ADR-026：raw 默认只作兜底（Accepted）

prompt recall 在 rerank 前执行 `raw_policy=fallback`，有提炼结果时不靠 raw 补满，并排除当前 session/thread 的 raw。
避免本轮回灌污染 prompt；代价是召回数量可能减少。工具可显式配置 raw policy，修改过滤顺序时复核。

## ADR-027：轻量维护由宿主空闲调度（Accepted）

新 SQLite 文件使用 INCREMENTAL；`run_idle_maintenance()` 按 prune → gc → nudge 执行。
重型 compact 和 WAL truncate 需要合适空闲窗口与空间检查；库不承诺所有宿主自动调度，接入时单独验证。

## ADR-028：运行摘要与决策 journal 分离（Accepted；替代 ADR-023）

`extract_run` 覆盖 meta 摘要，journal 按 action 留存，GC 返回计数而非逐行 journal。
避免空转撑大审计表；代价是无法从摘要重放每次空运行，PG retention 缺口见风险清单。

## ADR-029：裁剪前封口父图（Accepted）

保留回合内逐步 checkpoint；裁剪默认 `keep_last=1`，先封口父图 messages，再按安全条件删除祖先/子图。
进行中、HITL 或封口失败不能按普通结束回合处理；代价是封口和依赖验证成本，恢复语义变化时复核。

## ADR-030：PostgreSQL 普通操作使用短事务（Accepted）

统一 `_cursor()` 结束普通读写事务，显式 transaction 保留跨操作原子性；bootstrap 有锁超时和 FTS catalog fast path。
避免 idle transaction 阻塞 DDL；代价是确需长时间的 migration 必须单独规划，不能全局放宽超时。

## ADR-031：人工采纳代表用户决定（Accepted）

pending 走自动检查；conflict/needs_review 由 approve 处理，duplicate 合并，矛盾 active atom 被 successor 替代。
写入、candidate 状态、supersede、user journal 在同一事务内；代价是明确覆盖自动判断，不能把它当普通重试。

## ADR-032：PostgreSQL 在 cursor 边界恢复连接（Superseded by ADR-040）

transaction 外才允许 reset/reconnect 并恢复 search_path；显式 transaction 内失败即失败。
避免静默提交半套写入；代价是调用方需重试整个事务。既有 SQLite-only GC 缺口不代表允许静默能力分叉。

## ADR-033：namespace-first GIN（Accepted）

共享 PG schema 尝试 `btree_gin` + `GIN(namespace, tsv)`，扩展安装在 savepoint 中失败则保留普通 GIN。
保持权限不足时查询正确性；代价是 namespace 性能隔离减弱，需要真实 PG 验证。

## ADR-034：人工 correction 只追加 Atom（Accepted）

successor 保留历史来源，`user_edit` journal 记录修改，不伪造 RawEvent/Candidate。
两种 backend 均要求 active-only supersede，失败整体回滚；代价是原 quote 只能称为原始来源，不能证明修正内容。

## ADR-035：Episode 绝对时间统一 aware UTC（Accepted）

写入/读取/查询边界统一 UTC，legacy naive 按 UTC 解释，排序额外防御。
避免混合时间类型且无需先迁移旧值；代价是不能恢复旧值的未知本地时区，未来本地时间需独立字段与版本迁移。

## ADR-036：checkpoint 内容复用与显式迁移（Accepted）

SQLite 同库 typed blob + 格式 envelope 复用大字段，读时恢复历史值，不读取“最新文件”代替历史快照。
新写入和存量迁移分开，独立 reader 有自身 decoder/cache；代价是旧 reader 不兼容，降级前需 expand。
离线迁移、备份和回退见 [Checkpoint 维护](../../CONTRIBUTING.md#checkpoint-维护)。

补充：`db slim` 默认预览，显式 apply/offline 备份后去重和回收，不隐式裁剪历史；高级参数仍用 checkpoints。
在线瘦身由宿主暂停新 invocation、协调 reader 和恢复，批次使用事务且不追逐无限新增行。
长 reader 可能延期 WAL 回收，保留备份并报告部分完成，不能自动用备份覆盖后续合法写入。

## ADR-037：统一 Octop 命名，保留磁盘协议（Accepted）

发行包/CLI 为 `octop-memory`，Python 包为 `octop_memory`，宿主插件 ID 为 `octopmemory`。
环境变量、默认目录、bridge probe 字段与 PostgreSQL schema 同步更名，不提供旧入口别名。
SQLite checkpoint 编码、`hm_*` 表和 `.hmpkg` 格式属于持久化协议，保留以避免品牌更名破坏历史读取。
代价是旧安装必须显式迁移配置、目录或 PG schema，操作步骤仅维护在 [集成指南](../integrations.md#更名与已有安装迁移)。

## ADR-038：失败降级只捕获可预期的驱动与 I/O 错误（Accepted）

查询、文件和超时失败使用 `storage/driver_errors.py` 的 `DRIVER_ERRORS`（`sqlite3.Error`、已安装时的 `psycopg.Error`、`OSError`、`TimeoutError`、`RuntimeError`），记 warning 后降级。向量索引使用 `VECTOR_ERRORS`。doctor、抽取入口、bridge、idle maintenance、backfill 与 host 轮询使用 `REPORTABLE_ERRORS`。
事务回滚和 checkpoint 备份删除用 `try` / `finally`，失败和取消都会回滚。
这些元组之外的异常向上抛。`AssertionError` 不在降级集合里。

## ADR-039：SQLite 每 backend 一条连接，按操作与事务串行（Accepted）

为避免多 agent 与常驻 worker 的连接数相乘，移除线程本地 SQLite 连接注册表。
每 backend 使用一条 `check_same_thread=False` 连接和可重入锁，锁覆盖完整 execute/fetch/commit，
显式事务与关闭也持同一锁；非显式事务中的失败写入回滚后再抛出原错误。
vacuum、WAL truncate 和 export 的内部 SQL 同样受保护，避免维护与正常写入串入同一事务。

选择单连接而非引入 SQLite 连接池，减少空闲 fd 和生命周期分支。PostgreSQL 的共享池见 ADR-040。
代价是慢查询和长显式事务会阻塞同 backend 的其他 SQL；LLM 调用不在这些操作锁内，
不同 backend 以及单独的 checkpoint 连接仍可并行。保留 SQLite/WAL、表、事务原子性与召回契约，
无需数据迁移。后续若要增加同 backend SQL 并行，必须使用有界连接租约并重新验证事务与关闭行为。


## ADR-040：PostgreSQL 按连接配置共享有界池（Accepted）

每 agent 一条业务连接加独立 checkpoint 池仍会叠加容量：69 个活跃实例至少需要 138 条会话，
10 分钟空闲释放无法覆盖活跃峰值。改为按进程、规范化 DSN 与驱动选项共享 8 条业务连接和 4 条
checkpoint/维护连接；namespace 留在 SQL 条件中，不参与池标识。不同会话设置使用独立池，避免串用身份或配置。

业务借用连接覆盖完整 cursor/结果读取/事务，显式事务跨调用保留同一连接和 backend 可重入锁。
池在 checkout 探测坏连接，归还时提交或回滚，事务中断不重拨后续写。连接的 search_path 由池配置回调恢复。
原 backend 私有常驻 `_conn`、逐实例空闲 Timer 和重连冷却由 psycopg_pool 的回收、探测及重连退避替代。
`postgres` extra 显式声明已经用于 checkpoint 的 psycopg-pool，避免另写一套业务池。

LangGraph 按类型要求 ConnectionPool；内部租约适配器继承该类型但不开启自身池，仅将 `connection()`
委托给共享池，且让 saver.conn 与 Memory._checkpointer_pool 指向同一个幂等租约，兼容宿主两次 close。
每租约只释放一次引用，关闭等待其在途操作，最后引用关闭真实池。checkpoint setup 按池串行一次，
失败不发布 saver/租约且立即回收；autovacuum 设置与维护操作也借用池内连接。

每池最多 64 个等待者、30 秒 checkout 超时，`min_size=0`、`max_idle=600`。容量不足必须报错，
不无限开连接或重放可能已提交的写入。此预算是进程内边界；多进程、不同连接配置及宿主控制面仍需各自计入服务端容量。
无 schema、持久化编码、召回排序或 namespace 契约变更。真实 PG 回归覆盖 69 agent、事务/隔离、
饱和与恢复、空闲/坏连接、初始化失败及关闭引用；SQLite 保持同组公共行为断言。

## ADR-041：按来源隔离运行诊断，保护用户知识（Accepted）

运行失败的发生事实不等于可长期使用的知识。octop-harness / Octop 使用 `on_failure="error"` 让模型失败保留为 checkpoint 异常，由宿主单独展示；团队自动失败通知排除采集。仍合成错误回复的宿主必须标记 `payload.octop_runtime_error=true`，memory 在 capture、两类 extractor、promotion 和 raw prompt recall 仅按结构化来源排除。移除“记住”与“已验证”等意图/价值词表；主动保存由 Agent 自行调用 memory_save，手动写入、人工批准/编辑按来源保护。提炼模型判断普通对话的长期价值。⚠️ 召回/写入路径变更：后台采集不再给意图短句特例；存量治理即使 apply 也只软停用全部证据均带错误标记的自动记录。旧版严格重试失败格式仅在 operations 审核清单中使用，缺失或混合来源保留原状态、返回 review_*_ids；不据文字推断来源，不删 raw 或新增 schema。

## ADR-042：手动文档为准，冲突转候选，去重绑定会话快照（Accepted）

USER.md/MEMORY.md 由宿主用户维护，聊天原有统一加载器只在 session 首次加载全文。
memory 接收当前文件作治理，不负责文件读写或刷新提示词；宿主保存后显式核对，并可在普通保存/
自动晋升后通过 provider 检查。⚠️ 召回/写入路径变更：只有同主体/字段/时间范围的高置信互斥事实、
且模型引用真实完整原文，才在同一 backend 事务内软停用旧 Atom、建立替代事实 Candidate 和 Journal。
原始证据不删，未审核替代事实不晋升；旧 raw 不再自动兜底，dirty 页面等待重建。
历史事件、正常排障经验、不同情境及两个手动文档互相矛盾时不强行改判。

重复 Atom 不删，召回只在实际 session snapshot 含同一信息时抑制；不会把新文件版本硬塞入旧会话。
元数据保存对账版本和审计比较快照；独立小清单参与 recall cache key，避免旧缓存复活。
模型失败、不确定、伪造证据、版本变化和超限均显式报告；每次最多 100 条新 Atom 可续查。
采纳检查最后对账版本，宿主附当前文档可拦截未重新对账的变化。使用既有 Service/Bridge/
retention/promotion/recall 模块及 backend contract，不建新 schema、全文索引或独立加载器。
SQLite/真实 PG 同组测试验证事务、幂等、证据保留及 prompt 过滤。
