# PROJECT_MAP.md

当前模块、调用链和数据契约。架构变化时更新本文；设计原因见 [DECISIONS.md](DECISIONS.md)。

发行包/CLI 为 `octop-memory`，宿主插件 ID 为 `octopmemory`，bridge 为 `octopmemory-bridge`。
配置环境变量使用 `OCTOP_MEMORY_*` / `OCTOPMEMORY_*`；默认目录遵循新名称。
Python 入口为 `from octop_memory import Memory, MemoryService`。

```text
Python host → MemoryService ─────────┐
Hermes → in-process Bridge ──────────┤
OpenClaw → stdio Bridge ─────────────┴→ MemoryRuntime → pipeline → Memory
CLI → application / operations ──────────────────────────────────┘
                                                     ├→ SQLite / PostgreSQL
                                                     └→ optional VectorIndex
```

`MemoryService.recall()` 直接使用 recall pipeline，部分 CLI 直接调用 Memory/operations。
现有 dashboard 直接访问 SQLite；它是源码工具，不是新 adapter 的分层模板。

| 阅读入口（相对 `src/octop_memory/`） | 职责 |
|---|---|
| `types.py`、`domain/` | 数据结构、alias 与 UTC 规则 |
| `core.py` | `Memory` API、backend factory、可选 LangGraph saver |
| `service.py`、`application/runtime.py` | typed host API 和共享 capture/search/get/extract/promote 编排 |
| `application/config.py`、`host_files.py`、`path_projection.py` | policy、host Markdown 索引和 virtual path |
| `storage/backends/__init__.py`、`sqlite.py`、`postgres.py`、`postgres_pool.py`、`storage/driver_errors.py` | `MemoryBackend` contract、SQL、FTS、事务、namespace；降级捕获的异常元组 |
| `storage/vector/`、`ports/llm/` | 可选向量索引、embeddings 和 `LLMClient` |
| `pipeline/` | extractor、promotion、page、episode、recall、lifecycle |
| `adapters/` | JSON-RPC bridge、Click CLI、源码 dashboard |
| `operations/migration/` | export/import、portable package、namespace migration、backfill |
| `domain/retention.py`、`operations/retention.py` | 系统报错来源判定；存量预览和软停用；USER.md/MEMORY.md 原文核对、冲突软停用/替代候选/审计元数据 |

手动文档治理由 `MemoryService` / Bridge → `application.MemoryRuntime` → `operations.retention`
共享实现。宿主提供当前文档/可选 freshness callback；save/自动 promotion 可注册 provider。
`manual_documents/v1` 保存比较版本、已核对 assertion hash、未决候选和审计快照；小型
`manual_documents/recall/v1` 保存召回抑制清单。原文不会批量导入 Atom/FTS。
召回通过实际 session `manual_context` 去重，并屏蔽冲突旧 Atom 的 raw fallback 和待重建页面。
审核候选校验对账版本；宿主还应在采纳时提供当前 `manual_documents`，拦截未重新核对的文件变化。

portable 的 Agent 默认发现目录为 `~/.octop/agents/*/memory.sqlite` 与 `~/.octop-harness/*/memory.sqlite`；
其它位置由 `list_sources(extra_paths=...)` 显式加入，不自动搬移数据。

外部 Agent 适配位于根目录 `plugins/<host>/`，当前包括 OpenClaw、Hermes；验证位于 `tests/`、`evals/`，示例位于 `examples/`。
`examples/basic_usage.py` 合并基础读写、树和 prompt recall，仅通过公共 API 写入临时库；
`evals/recall/run.py` 比较 raw FTS、atom/raw 和完整 recall，使用合成 corpus，不是正式质量基准。
`scripts/` 提供插件构建、部署、真实宿主验收及本地维护启动器；个人诊断和工具配置不纳入公共源码。
根目录 `.editorconfig` 固定 4 空格、LF、UTF-8，Python 行宽 120，与 `ruff` 一致。
pipeline/storage/domain 不依赖 adapters，storage 不依赖 pipeline，service 不依赖 bridge。
`tests/test_architecture_boundaries.py` 固化这些约束；SQL 留在 storage 内。

### 连接与并发

SQLite 每个 backend 保留一条连接，完整 SQL 操作、结果读取和显式事务共用一把可重入锁；
不再按线程缓存连接。单次失败写入在非显式事务中回滚，`close()` 等待操作结束后关闭且不重开。
内部 vacuum、WAL truncate 与 export 的直接 SQL 也遵守此锁。不同 backend 的锁互不影响，
LangGraph checkpoint 使用单独连接，不与业务 SQL 共用事务；SQLite 取舍见 ADR-039。
PostgreSQL 的 `postgres_pool.py` 按进程、规范化 DSN 与驱动选项共享业务池（8）和 checkpoint/维护池（4）。
`_cursor()` 借用短事务连接；显式事务持有同一连接及 backend 锁，失败不会重拨后续写。
两类池均 `min_size=0`、`max_idle=600`，取连接时探测存活；排队上限 64、等待上限 30 秒。
租约 `close()` 幂等且等待本实例操作，最后引用释放才销毁共享池；checkpoint DDL 按池串行初始化一次，失败释放租约并允许重试。
导出通过 backend cursor，vacuum/check/compact 与 checkpoint 共用 autocommit 池；取舍见 ADR-040。

### 数据与写入

| 数据 | 用途 |
|---|---|
| L0 `RawEvent` | 原始证据，受 capture/privacy 过滤 |
| L1 `Candidate` | 抽取或手工构造的候选及 review 状态 |
| L2 `AtomCard` | canonical fact、证据引用、置信度、替代关系 |
| L2.5 `Episode` / digest | 事件与周期摘要 |
| L3 `Entity` / `EntityPage` | 实体锚点、整合页面与 headline |
| L4 journal | 明确的业务决策与 lifecycle 记录，不是全部 SQL mutation 日志 |

`capture → RawEvent → extraction → Candidate → promotion → AtomCard/Entity → dirty page → regeneration`。
Candidate 可自动晋升、合并、丢弃或进入 conflict/needs_review，不能等同于全量人工审核队列。
Episode 从 RawEvent 独立提炼；页面由 dirty 标记和 regeneration 触发更新，不承诺每次写入即时刷新。
自动提炼使用注入的 `LLMClient`；无模型时 capture 和 FTS 可用，提炼返回不可用原因。

octop-harness 主路径使用 `on_failure="error"`，失败写入 checkpoint task error，不产生合成助手回复；团队自动失败通知使用 `configurable.octop_memory_capture_exclude=true` 排除整轮采集。自定义宿主仍合成错误时必须使用 `payload.octop_runtime_error=true`。capture、Candidate/Episode extractor、promotion 及 raw prompt recall 只共用结构化来源规则，无记忆意图/排障价值关键词。Agent 自行调用 memory_save；后台采集只保留既有长度等策略，不为特定措辞放行短句。`audit_runtime_errors` 默认预览，显式 apply 也只在全部证据带错误标记时停用自动 Atom、拒绝未决 Candidate。旧版严格报错格式仅在 operations 层生成审核提示，缺失/混合来源返回 review_*_ids，原状态不改；原始证据不改写，人工保存/批准/编辑按来源保护。

`Memory.store()` 的 leaf 写入使用手工 RawEvent/Candidate/AtomCard 路径，无需 LLM。
`root → branch → leaf` 是组织树，leaf 用 `atom_id` 投影事实正文，不复制第二份事实。
人工 correction 创建 successor、active-only supersede 旧 atom 并写 `user_edit` journal；
不伪造新对话证据。page regeneration 保护 `## My Notes`，绝对事件时间统一为 aware UTC。

### 读取与隔离

- `Memory.recall()` 返回 atom 对应的 tree leaf；`Memory.search()` 搜索归档 conversation messages。
- `MemoryService.recall()` / `recall_for_prompt()` 返回 `RecallResult.snippets` 与 `rendered`。
- 主召回：cache → parse → route → gather → raw policy → rerank → diversify → suppress → budget → render。
  默认 atom/raw，entity anchor 加 page_headline，有 index 加 vector；tree 非独立 source。
- 默认 raw fallback 在命中提炼结果时排除 raw；传入当前 session/thread 时排除本会话 raw。
  工具搜索还可合并允许的 host Markdown，`memory_get` 按虚拟路径读取。
- SQLite 使用 namespace 表名前缀；PostgreSQL 使用共享 `octop_memory` schema 和 namespace-first keys。
  Chroma/Qdrant 仅增强检索，不能替代关系数据和事务。
