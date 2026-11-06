# ADR 003 — Skill Package & Knowledge Base Storage (SQLite | PostgreSQL)

**Status:** Accepted  
**Date:** 2026-10-23  

**Related:** [ADR 002](./002-database-backends.md)（控制面双后端；本期把技能包源与知识库也纳入同一驱动绑定）

---

## Context

技能包正文与知识库原文/向量索引目前落在 `~/.octop/skill-packages/`、`~/.octop/knowledge/`（含本地 `index.sqlite`）。控制面虽可选 PostgreSQL，这些内容仍绑单机磁盘，无法在多实例间共享，也为后续水平扩展埋下瓶颈。

一期目标：**在不改变专家侧既有行为的前提下**，让 PostgreSQL 模式把技能包源与知识库存进同一套 PG；SQLite 模式保持现有本地布局。集群租约、IM 多活、composite 默认挂载等不在本期范围。

---

## Decision

### 1. 与控制面驱动绑定

| 控制面 `database.driver` | 技能包源 | 知识库原文 | 知识库向量 |
|--------------------------|----------|------------|------------|
| `sqlite` | 本地目录（现状） | 本地 `knowledge/<id>/docs/` | 本地 `index.sqlite` |
| `postgresql` | PG 文件表（见下） | PG 文件表（见下） | **pgvector**（同库另表） |

不提供「CP 用 PG、技能包/KB 仍本地」的一期配置分叉。

### 2. 安装时选定，一期不做迁移

- 初始化 / 安装向导选择 sqlite 或 postgresql 后按该模式建存储。
- **不做** sqlite→PG 的一键迁移；迁移工具可后续单独提供。

### 3. 技能包：外置源 + 复制进专家（不改挂载模型）

- **不**引入 `/_octop` 挂载，**不**把默认 backend 改成 composite。
- 专家侧继续现有逻辑：`skills` / `_builtin_skills` 走 workspace backend；绑定技能包仍走 **复制进专家 backend 目录**（现有 copy 策略：`snapshot` / `lock` 等维持默认与可选项）。
- 变化仅在「源」：
  - sqlite：从本地 `skill-packages/` 读，再写入专家 backend；
  - postgresql：从 PG 技能包文件表读，再写入专家 backend（local_shell / filesystem / postgres / opensandbox 等同一条复制路径）。
- 控制台编辑技能包文件：经统一 **Store**，底层为本地 FS 或 PG 文件存储，不直打与 Store 无关的散落路径。

### 4. PG 文件存储：复用 PostgresBackend 形态，分表隔离

不新造 zip 整包或平行 bytea 协议。技能包源、知识库原文均按 harness [`PostgresBackend`](../../../octop-harness/src/octop_harness/backends/postgres.py) 的方式入库（`path` + `content` JSONB 等），并与专家 workspace 表隔离，例如：

- `public.skill_package_files`
- `public.knowledge_files`
- `public.knowledge_chunks`（pgvector，与 `knowledge_bases` 同在 `public`）

（具体 schema/表名实现时可微调，原则是 **独立表、路径一行一文件**。）

### 5. 知识库：只改存储与 `search_knowledge`

- **不**把 KB 挂进或复制进专家工作区。
- 原文进上述知识库文件表（PG）或本地目录（sqlite）。
- 向量：PG 模式用 **pgvector**；sqlite 模式保持现有本地索引。
- `search_knowledge`（及索引写入）按控制面驱动选择读哪套索引。
- `CREATE EXTENSION vector` 仍遵循 ADR 002：由 Docker init / 运维侧负责，不塞进控制面 `*.pg.sql` 强依赖（部署 PG 知识库前需可用的 vector 扩展）。

### 6. 明确不在本期

- 多 Octop 实例的 Cron/任务租约、专家晚加载/offload、无粘滞网关下的 turn 迁移
- IM 通道多活
- 技能包/KB 的对象存储（S3/COS）——Store 接口可留扩展点，一期只实现本地与 PG
- sqlite↔PG 数据迁移工具

---

## Consequences

- PostgreSQL 安装可在多机之间共享技能包源与知识库（配合共享 CP），为后续集群化打下存储基础，但 **单进程运行时假设仍在**（见 ADR 001），多实例写仍需后续协调。
- 专家行为与 copy 策略面不变，回归面主要在 Store 与检索路径。
- 运维需在 PG 部署中准备 `vector` 扩展（与现有 docker init 方向一致）。
- 已有 sqlite 用户升级到 PG 需等待后续迁移工具，或新建 PG 实例后手工导入。

---

## Implementation sketch（非规范，供排期）

1. `SkillPackageStore` / KB 文件层改为 Store 抽象：`Filesystem*` | `PostgresBackend`-backed。
2. 复制技能包：源改走 Store，目标仍是专家 `BackendWorkspace`。
3. KB 索引：PG 路径写入 pgvector 表；`search_knowledge` 分支。
4. 安装向导 / 文档：选驱动即选定内容平面；说明 PG 需 vector 扩展。
5. 测试：sqlite 现状回归 + `@pytest.mark.postgresql` 覆盖 Store 与检索。
