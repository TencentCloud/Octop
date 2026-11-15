## feat(hitl): add PostgreSQL-backed pending store with runtime factory

把 HITL（Human-in-the-loop）待处理记录从进程内 dict 升级为可选的 PostgreSQL 持久化实现，并新增按控制面配置选择实现的工厂。默认行为不变：SQLite 控制面仍使用内存实现；PostgreSQL 控制面在迁移 026 已应用时自动切换到持久化实现，任何异常（缺驱动 / 连不上 / 缺表）都会降级回内存实现，不会导致启动失败。

---

## 变更文件

| 文件 | 变更 |
|---|---|
| `src/octop/infra/gateway/hitl/pg_store.py` | 新增，600 行，`HitlPendingPostgresStore` 共 19 个方法，签名与内存版完全一致 |
| `src/octop/infra/db/migrations/026_hitl_pending_store.sql` | 新增 SQLite 方言建表 DDL + 索引 + `_schema_version = 26` |
| `src/octop/infra/db/migrations/026_hitl_pending_store.pg.sql` | 新增 PostgreSQL 方言建表 DDL + 索引 + `_schema_version = 26` |
| `src/octop/infra/gateway/hitl/factory.py` | 新增，`build_pending_store()` 按控制面配置选择实现，异常一律降级 |
| `src/octop/infra/gateway/hitl/__init__.py` | `HitlPendingPostgresStore` 改为 PEP 562 惰性导出 |
| `src/octop/infra/gateway/process/processor.py` | `GlobalProcessor` 构造协调器时接入 `build_pending_store()` |
| `scripts/smoke_hitl_pg_store.py` | 新增，13 项 PG 冒烟测试，连接串由 `OCTOP_TEST_DSN` 提供 |
| `scripts/verify_hitl_pg_schema.py` | 新增，应用并校验迁移 026 建表与索引结果 |

## 核心设计

### 1. 惰性导出，避免把可选依赖变成硬依赖

`pg_store.py` 在模块级导入 `psycopg` / `psycopg_pool`。若 `hitl/__init__.py` 直接硬导入该类，则 SQLite 安装（无驱动）在导入该包的任何位置都会失败，进而拖挂 chat 路由与 agent_mcp。改为模块级 `__getattr__` 惰性解析，未安装驱动时包仍可正常导入，只在真正访问该名称时抛出 ImportError。

### 2. 运行时工厂，失败即降级

工厂先读控制面配置：无 config.json 且无 `OCTOP_DATABASE_*` 时返回内存实现；非 PostgreSQL 控制面同样返回内存实现。确认是 PostgreSQL 后，先探测连通性与 026 表是否存在，二者都通过才返回 PG 实现；任一环节异常都会记录 warning 并回落内存实现。

降级而非抛错是刻意选择：HITL 记录属会话级状态，进程重启即失效本就是旧行为；而启动失败会让整个网关不可用，代价远大于持久化收益。

### 3. 迁移编号与仓库发现机制一致

`migrate.py` 用 `sorted(_MIGRATIONS_DIR.iterdir())` 自动发现迁移，存量最大编号为 025，新增 026 无需改动任何注册表。同时提供 SQLite 与 PostgreSQL 两种方言，与 021–025 的双方言约定保持一致。

---

## 验证结果

### 迁移与建表（脚本实测）

- 建表 18 列：pending_id / thread_id / agent_id / user_id / session_key / channel_type / action_requests / review_configs / status / ask_question_index / ask_answers / resume_agent_id / resume_thread_id / form_context / consumed_submission_ids / created_at / updated_at / id
- 建索引 9 个，含 idx_hpr_slot / idx_hpr_form_id / idx_hpr_status_created
- `verify_hitl_pg_schema.py` 重复执行结果一致（DDL 全部 IF NOT EXISTS）

### PG Store 冒烟（13/13，连续两次执行均通过）

| # | 用例 | 结果 |
|---|---|---|
| 1 | register 返回 4 位 pending_id | PASS |
| 2 | get 命中且 status=pending | PASS |
| 3 | get_pending 正常会话匹配 | PASS |
| 4 | get_pending 错误会话返回 None | PASS |
| 5 | resolve_for_session 命中同一条记录 | PASS |
| 6 | 同槽位同 actions 幂等 register 返回原记录 | PASS |
| 7 | mark_form_consumed 首次 True / 重复 False | PASS |
| 8 | expire_pending_for_thread 置为 expired | PASS |
| 9 | mark_resolved 置为 approved | PASS |
| 10 | cancel_pending_by_form_id 取消并置 expired | PASS |
| 11 | pending_thread_ids 返回 t1 | PASS |
| 12 | append_ask_answer 追加答案且 index 自增到 2 | PASS |
| 13 | _gc 正常执行 | PASS |

### 工厂选择逻辑（三种控制面实测）

| 场景 | 返回实现 | 结果 |
|---|---|---|
| 默认 / SQLite 控制面 | `HitlPendingStore` | PASS |
| 指向不可达 PG（127.0.0.1:1） | `HitlPendingStore`（降级，无异常抛出） | PASS |
| 有效 PostgreSQL + 026 已应用 | `HitlPendingPostgresStore`（ttl=1800，close 正常） | PASS |

### 回归测试

| 范围 | 结果 |
|---|---|
| `tests/unit/gateway`（除 3 个缺可选依赖的模块） | 488 passed |
| HITL 专项 5 个测试文件 | 84 passed |
| 迁移发现 + 迁移目录 | 46 passed |
| 上一提交的 timeout / 幂等 / cancel 单测 | 29 passed |
| `ruff check` + `ruff format --check` | 全部通过 |

`tests/unit/gateway` 中 3 个模块（test_attachment_hints / test_channels_qr / test_chat_image_pipeline）因测试环境缺 PIL 与 fastapi 无法收集，与本改动无关。

---

## 兼容性与回滚

- 默认行为不变：未配置 PostgreSQL 的安装仍拿到内存实现，调用路径与旧版完全一致。
- 方法签名不变：PG 实现与内存实现一一对应，协调器无需分支判断。
- 回滚方式：删除迁移 026 或把控制面切回 SQLite 即可；表保留不影响旧版本运行（旧版本不读该表）。
- 已知限制：`_gc()` 在 PG 实现中退化为按 `created_at` 的过期更新，未额外引入定时任务；多实例部署下 TTL 清理由各实例读写路径触发。

## 与上一个 PR 的关系

上一个 PR（complete structured_form lifecycle）解决的是表单生命周期功能缺失，本 PR 解决的是运维可靠性。二者在 store.py / coordinator.py / __init__.py 上有文件交集，但主题独立，建议按顺序合入：先功能、后基础设施。
