# TEST_MATRIX.md

按改动范围选择最小验证；提交门禁为 `make all`。代码任务的实际结果写入 [HANDOFF.md](HANDOFF.md)，不维护带日期的测试数基线。

| 改动范围 | 最小命令 |
|---|---|
| 包名 / 宿主命名 | `uv run pytest tests/test_cli_entry.py tests/test_cli_config.py tests/test_bridge_server.py tests/test_hermes_adapter.py tests/test_hermes_install.py -q`；`uv build`；在 `plugins/openclaw/octopmemory/` 执行 `npm test`、`npm run typecheck`、`npm run build` |
| 文档 / import 边界 | `uv run pytest tests/test_agent_docs.py tests/test_architecture_boundaries.py -q` |
| Memory / runtime | `uv run pytest tests/test_core.py tests/test_service.py -q` |
| 召回 | `uv run pytest tests/test_recall_pipeline.py tests/test_recall_multi_source.py tests/test_recall_risk_fixes.py -q` |
| 提炼 | `uv run pytest tests/test_extractor.py tests/test_promotion.py -q` |
| 运行报错隔离 / 存量治理 | `uv run pytest tests/test_runtime_error_retention.py tests/test_bridge_server.py tests/test_backend_parity.py -q -rs`；真实 PG 验证仅结构化标记过滤、未知来源只列审核清单、任意措辞手动保存、无短句意图例外、raw fallback、晋升、人工保护、幂等和事务回滚 |
| 手动文档治理 | `uv run pytest tests/test_manual_documents.py tests/test_backend_parity.py -q -rs`；真实专用 PG 的 `-k ManualDocument` 与 SQLite 同组验证冲突/替代候选、原证据保留、raw fallback、快照去重、幂等与回滚；单测覆盖伪造/不确定证据、过期采纳、缓存失效、分批续查、save/自动晋升钩子 |
| 宿主失败来源边界 | 在 octop-harness 运行 `pytest tests/test_model_retry_middleware.py tests/test_memory_middleware.py tests/test_teams/test_inbox.py`：真实图 checkpoint error / 恢复、零错误 raw 写入、团队自动通知排除；WebUI / IM / 团队失败展示在 Octop 测试 |
| 写入 / backend | `uv run pytest tests/test_memory_atom_write.py tests/test_backend_parity.py -q -rs` |
| 连接 / 事务 / fd | `uv run pytest tests/test_sqlite.py tests/test_fd_pressure.py tests/test_postgres_pool.py tests/test_backend_parity.py -q -rs`；设置专用 `TEST_POSTGRES_DSN`，确认 PG 用例实际运行 |
| 向量接口 / 可选 index | `uv run pytest tests/test_vector_chroma.py -q`；使用 mock index 和 `tmp_path` 数据库，不访问默认数据目录 |
| Checkpoint | `uv run pytest tests/test_checkpoint_compaction.py tests/test_checkpoint_gc_safety.py -q` |
| 迁移 | `uv run pytest tests/test_migration_export_import.py tests/test_portable_e2e.py tests/test_portable_sources.py -q` |
| 公共 API 示例 | `uv run python examples/basic_usage.py` |
| Recall 评测 | `uv run python -m evals.recall.run` |
| 示例 / 评测静态检查 | `uv run ruff check examples evals` 与 `uv run ruff format --check examples evals` |

SQLite/PostgreSQL 均为生产 backend。public 读写、持久化编排、contract、schema、transaction、FTS、
lifecycle 修改必须同步维护两种实现，并以同一组断言运行真实 PostgreSQL：

```bash
# 使用专用测试数据库；以下凭据仅为占位。
TEST_POSTGRES_DSN='postgresql://user:pass@localhost/octop_memory_test' \
  uv run pytest tests/test_backend_parity.py tests/test_postgres.py \
    tests/test_memory_atom_write.py tests/test_checkpointer.py -q -rs
```

PG skip 不算通过。CI/release 启动专用 PostgreSQL 16，`TEST_POSTGRES_DSN` 已设置但连接失败时直接失败；
本地未设置时先快速探测，服务不可用才 skip，防止连接池重试让整套测试逐项等待 30 秒。
`test_postgres_pool.py` 验证 69 个实例混合读写和 checkpoint 的总连接数 ≤12，覆盖池满超时/排队上限、
空闲归零与重连、服务端断开空闲连接、初始化失败重试、维护共用预算以及关闭不影响其它实例。
空闲测试只缩短测试进程内的回收周期；生产保留 `max_idle=600`。
关闭测试先断言租约已关闭、引用归零和真实池已关闭，再限时等待远端 `pg_stat_activity` 归零；客户端关闭 socket 不代表远端进程已同步退出。
backend-specific 能力必须显式拒绝另一 backend 并记录限制。
测试使用 `tmp_path`，不能写用户真实记忆库；可选依赖和宿主 E2E 的 skip 单独报告。
`test_fd_pressure.py` 在独立 POSIX 子进程中将 soft NOFILE 设为 1024，验证 69 个临时 Memory
被 8 个常驻 worker 使用时仍可创建 socket，关闭后 fd 回到基线；不修改 pytest 主进程限额。
Windows 或 hard limit 不足时会 skip；Linux `/proc` 的旧短线程回归与此测试分开报告。
若 uv 缓存不可用但虚拟环境工具齐全，可用 `make all RUN='.venv/bin/python -m'`。

## 验证边界

portable 默认发现测试将用户目录展开隔离到 `tmp_path`，覆盖当前 Agent 路径和显式 `extra_paths`。
portable dry-run 使用临时目标库并比较前后数据；召回降级/page headline 测试也使用临时库，不能访问用户默认库。

文档检查覆盖本地链接、公开内容和目录约定；不能证明全文不存在敏感信息。
宿主安装、optional dependencies、真实 PostgreSQL 与 recall 质量需分别验证，不能由基础单测替代。
合成评测的历史 `P@5` 标签实际分母为返回的前五条数量，不固定为 5；MRR 使用整个返回列表。
该小样本偏向实体查询，日期与 ID 每次生成；默认比较 raw_fts 和 full_pipeline，退出码只表示配置的 delta gate。
它没有接入 `make all` / CI，不能据此声明生产召回质量。只改注释时不调整评测口径或 seed 数据。
