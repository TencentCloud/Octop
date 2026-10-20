<p align="center">
  <img src="assets/images/banner.jpeg" alt="Octop Memory — 帮你珍藏记忆的小章鱼" width="880" />
</p>

<p align="center">
  <strong>让 Agent 记住重要的事。</strong><br />
  记住你的偏好，延续每次对话，把积累的记忆带到下一个 Agent。
</p>

<p align="center">
  <a href="pyproject.toml"><img alt="Python 3.12+" src="https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&amp;logoColor=white" /></a>
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-E85D75" /></a>
  <a href="pyproject.toml"><img alt="Core dependencies: 0" src="https://img.shields.io/badge/Core_dependencies-0-E85D75" /></a>
  <a href="#可选依赖"><img alt="Storage: SQLite and PostgreSQL" src="https://img.shields.io/badge/Storage-SQLite_%7C_PostgreSQL-4169E1" /></a>
  <a href="CONTRIBUTING.md"><img alt="Code style: Ruff" src="https://img.shields.io/badge/Code_style-Ruff-261230?logo=ruff&amp;logoColor=white" /></a>
</p>

<p align="center">
  <a href="#highlights">亮点</a> ·
  <a href="#快速开始">快速开始</a> ·
  <a href="#外部-agent-适配">宿主接入</a> ·
  <a href="#cli">CLI</a> ·
  <a href="#代码架构">架构</a> ·
  <a href="CONTRIBUTING.md">参与贡献</a>
</p>

<p align="center">
  <a href="README.md">English</a> · <b>中文</b>
</p>

---

**Octop Memory** 是面向 LLM Agent 的持久化、可迁移记忆系统。让个人助手记住使用偏好，
让开发协作延续项目背景与关键决策，也让已经积累的记忆随你迁移到其他已适配的宿主。
从本地 SQLite 起步，按需加入 PostgreSQL 和模型辅助提炼。

它为 **Octop 生态**提供记忆能力，也可独立作为 Python 库、CLI 或 JSON-RPC bridge 使用。
**OpenClaw** 与 **Hermes** 插件将各自的 hook 和工具接入同一套记忆 runtime。
宿主负责 Agent 执行与模型调度，Octop Memory 负责捕获、提炼、召回、存储和迁移。

> **值得记住的事，留得住，也带得走。** 保存、召回，让记忆在已适配的 Agent 之间延续。

<a id="highlights"></a>

## ✨ 亮点

| | 亮点 | 带来的价值 |
|---|---|---|
| 🪶 | **轻装上手，按需扩展** | 核心零依赖，仅 Python 标准库 + SQLite/FTS5；手工存储与全文召回无需模型。 |
| 🧠 | **把对话沉淀成长期记忆** | 模型辅助抽取与 promotion 将原始事件提炼为带证据引用的事实，再由实体页面和 Episode 组织上下文。 |
| 🔍 | **为当前问题找回相关上下文** | 全文检索、排序、去重与 token 预算共同组织 prompt 记忆。 |
| 🧳 | **记忆跟着你走** | 支持导入导出和 `.hmpkg` 打包，在 OpenClaw、Hermes 等已适配宿主之间迁移记忆。 |
| 🔌 | **接入你的 Agent** | Python `MemoryService`、JSON-RPC bridge 和独立宿主插件复用同一套 runtime。 |
| 💾 | **从本地到服务端** | SQLite 适合本地起步，PostgreSQL 支持服务端部署。 |
| 🌳 | **让记忆有条理** | `AtomCard` 保存事实，实体页面与 `root → branch → leaf` 记忆树帮助组织浏览；namespace 隔离后端中的记忆空间。 |
| 🔖 | **让会话可以继续** | 可选 LangGraph checkpoint 保存执行状态，与长期记忆并存，支持 SQLite 和 PostgreSQL。 |

需要 **Python 3.12+**。自动抽取、promotion 检查和页面生成使用注入的 `LLMClient`；安装包本身不会自动配置模型。
宿主配置见[集成指南](docs/integrations.md)，已有安装升级请先阅读[更名迁移说明](docs/integrations.md#更名与已有安装迁移)。

## 快速开始

```bash
pip install octop-memory
```

```python
from octop_memory import Memory, MemoryService

memory = Memory(
    namespace="demo",
    backend_config={"db_path": "./demo.sqlite"},
)
memory.store("User prefers Python for backend services", topic="preferences")

# 基础事实检索返回 MemoryNode leaf 投影。
for node in memory.recall("Python"):
    print(node.content)

# prompt 召回增加来源选择、排序、去重与预算。
result = MemoryService(memory).recall("Python")
print(result.rendered)
```

示例创建本地数据库；最小 FTS 验证使用原文中出现的词。`Memory.search()` 检索归档 conversation messages，与事实召回是不同入口。

### 可选依赖

| 安装命令 | 用途 |
|---|---|
| `pip install "octop-memory[cli]"` | CLI 与 OpenClaw 配置命令 |
| `pip install "octop-memory[postgres]"` | PostgreSQL memory backend |
| `pip install "octop-memory[langgraph]"` | SQLite LangGraph checkpointer |
| `pip install "octop-memory[langgraph-postgres]"` | PostgreSQL LangGraph checkpointer |

代码已有向量检索接口和 Chroma/Qdrant 适配实现，但当前测试使用 fake/mock，尚缺真实 Chroma/Qdrant 集成验证。向量检索默认不启用，暂不作为已完整支持的安装选项。使用时需初始化索引，并将 `vector_index` 和 `embedding_provider` 注入 `Memory`；仅安装依赖不会启用。关系存储的 `backend` 仍是 `sqlite` 或 `postgres`。

```python
memory = Memory(
    namespace="demo",
    backend="postgres",
    backend_config={"dsn": "postgresql://user:pass@localhost/octop_memory"},
)
```

实际凭据从部署配置注入。SQLite 使用 namespace 表名前缀；PostgreSQL 在共享 `octop_memory` schema 中使用 namespace-first key/index 隔离。

同一进程、相同连接配置的 PostgreSQL 实例共享业务池（最多 8 条连接）及 checkpoint/维护池（最多 4 条），不随 agent 数量增加。每池最多等待 30 秒、最多排队 64 个请求；池满超时或队列已满会明确报错。空闲池可收缩到 0，关闭一个实例不会影响其它实例。多进程、不同连接配置及宿主自身数据库连接需要另计容量。

## CLI

先安装 `[cli]`。全局参数放在子命令前，示例显式选择 database 和 namespace。

```bash
octop-memory --db ./demo.sqlite --namespace demo memory store --content "User prefers Python"
octop-memory --db ./demo.sqlite --namespace demo recall "Python"
octop-memory --db ./demo.sqlite --namespace demo memory tree
octop-memory --help
```

| 命令 | 用途 |
|---|---|
| `raw`、`candidate`、`atom`、`entity`、`page` | 查看和维护各记忆层 |
| `episode`、`digest`、`journal` | 事件摘要与决策记录 |
| `memory`、`recall`、`thread` | 记忆树、prompt 召回和 thread state |
| `export`、`import`、`migrate`、`portable` | 备份与迁移 |
| `db`、`gc`、`consolidate` | 存储维护和 lifecycle |
| `config`、`openclaw`、`backfill` | 配置、宿主接入、历史抽取 |

参数以 `<command> --help` 为准。`db slim FILE` 默认只读预览 SQLite checkpoint 去重；添加 `--apply --offline` 后先备份再执行，不删除历史。迁移或降级 reader 前阅读 [checkpoint 兼容性与维护](CONTRIBUTING.md#checkpoint-维护)。

dashboard 当前仅供源码 checkout 配合 `[dashboard]` 依赖运行，其模块未进入 wheel。仅从 PyPI 安装 `octop-memory[dashboard]` 不会获得 dashboard 命令。

## 外部 Agent 适配

`plugins/<host>/` 将外部 Agent 的 hook、工具调用和配置映射到共享 Python runtime。
当前提供 OpenClaw、Hermes 两种适配；其他 Agent 可通过 Python API 或 JSON-RPC 接入，需实现各自的宿主契约。

| 接入方式 | 适用场景 | 入口 |
|---|---|---|
| Python 进程内 | 自有 Agent / Python 应用 | `MemoryService.capture_turn()` / `recall()` / `search()` / `get()` / `extract()` |
| JSON-RPC bridge | 跨语言或独立进程 | stdio `octopmemory-bridge` |
| 宿主插件 | 需要对接指定 Agent 的生命周期和工具接口 | `plugins/<host>/`；已有 OpenClaw、Hermes |

安装、配置、profile、排错和新增适配的边界统一见[集成指南](docs/integrations.md)。

跨宿主迁移使用 `octop-memory portable list-sources / pack / adopt / doctor`。导出的 `.hmpkg` 包含记忆数据，不应提交到源码仓库。

## 代码架构

```text
src/octop_memory/
├── core.py / types.py     # Memory 公共存储 API、数据结构
├── service.py            # MemoryService：Python 宿主入口
├── application/          # MemoryRuntime、配置、宿主文件和路径投影
├── pipeline/             # 抽取、promotion、召回、页面、事件和生命周期
├── storage/              # SQLite / PostgreSQL、checkpoint、向量索引
├── ports/                # LLM 等外部能力接口
├── domain/               # alias、时间等跨层规则
├── adapters/             # JSON-RPC bridge、CLI、源码 dashboard
└── operations/           # 导入导出、迁移、portable package
plugins/                  # 外部 Agent 适配，按宿主组织
examples/                 # 公共 API 示例
tests/ / evals/           # 行为测试 / 合成召回评测
docs/agent/               # Harness 项目认知、决策与交接
```

依赖由 adapters 向 application 和 pipeline/core/storage 等内部层流动。`MemoryService` 与 `Bridge`
复用 `MemoryRuntime`；pipeline/storage 不反向依赖 adapter，backend-specific SQL 留在 storage。
源码 dashboard 的直接 SQLite 访问是现有例外。

### 宿主调用链

```text
Python host → MemoryService ─────────┐
Hermes → in-process Bridge ──────────┤
OpenClaw → JSON-RPC bridge ───────────┴→ MemoryRuntime → pipelines → Memory
CLI → application / operations ────────────────────────────────────┘
                                                     ├→ SQLite / PostgreSQL
                                                     └→ optional vector index
```

Hermes 当前在进程内调用 `Bridge`，OpenClaw 使用 bridge 子进程。`MemoryService.recall()` 也会直接调用 recall pipeline。事实保存在 `AtomCard`；tree leaf 只引用 atom 并投影正文，记忆树是组织视图，不额外复制事实，也不是独立召回 source。

### 长期记忆数据流

```text
RawEvent ──抽取──→ Candidate ──promotion──→ AtomCard ──dirty / regeneration──→ EntityPage
    └────事件提炼────→ Episode                └────atom_id 引用────→ tree leaf
```

Candidate 是候选，不代表每条都要人工审批。promotion 会按价值、证据、实体、重复和冲突检查，
自动晋升、合并或丢弃候选，需复核或有冲突的候选可由用户处理。实体页面并非每次写入都立即更新，
而是在标记 dirty 后由 runtime/CLI/host 触发再生成；Episode 与事实提炼是并列流程。
`Memory.store()` 的手工写入无需模型，直接建立 RawEvent/Candidate/AtomCard 和 leaf 引用。

prompt 召回默认路由 `atom`、`raw`；解析到 entity 时加入 `page_headline`，配置 vector index 后加入 `vector`。默认 raw fallback 策略在命中已提炼记忆时排除 raw；传入当前 session/thread 时排除本会话原始事件。

系统生成的运行报错不自动进入长期记忆，也不通过历史 raw 兜底召回。octop-harness / Octop 将模型异常保留为 checkpoint 失败任务，由宿主单独显示错误；团队自动失败通知排除采集。仍生成合成报错的宿主必须使用 `payload.octop_runtime_error=true` 标记；在线链路只按结构化来源排除，不判断“记住”“已验证”等文字。Agent 自行决定调用 `memory_save`，手工保存与人工批准由来源记录保护。后台采集保留原长度策略，不再有记忆意图关键词例外；主动保存不受此长度限制。原始诊断证据仍可按 ID 检查。`operations.retention.audit_runtime_errors(memory)` 默认仅预览，显式 `apply=True` 也仅软停用全部证据均有错误标记的自动 Atom。旧版固定报错格式只生成 `review_atom_ids` / `review_candidate_ids` 审核清单；证据缺失或混合来源也保留待审，不自动改变这些记录的状态。

手动文档治理使用 `MemoryService.reconcile_manual_documents({"USER.md": text, "MEMORY.md": text})`，Bridge 对应 `reconcile_manual_documents` / `manual_document_review_status`。手动文档优先：明确冲突的旧 Atom 软停用，文档中的替代事实转为待审核 Candidate，保留旧来源和 Journal；采纳才更新为确定事实。重复 Atom 保留，`recall(..., manual_context=实际会话快照)` 避免重复注入。宿主可传 `manual_documents_provider` 在 save/自动晋升后检查当前文件，不刷新聊天快照。每次最多核对 100 条新事实、文档总长最多 100,000 字符；partial 可继续，模型不可用、不确定或证据无效会明确报告，不擅自停用。完整文档只存对账元数据，不导入 Atom 或索引。规则见 ADR-042。

贡献入口见 [CONTRIBUTING.md](CONTRIBUTING.md)，架构与数据流见[项目地图](docs/agent/PROJECT_MAP.md)。AI 协作规则见 [AGENTS.md](AGENTS.md)，任务澄清与交接沿用 [HANDOFF.md](docs/agent/HANDOFF.md)。

## 开发与验证

```bash
make install          # uv sync --group dev
make install-hooks    # 每个 clone 执行一次
make all              # format + lint + strict mypy + tests
uv build              # Python wheel + sdist
```

PostgreSQL 行为测试需通过 `TEST_POSTGRES_DSN` 连接真实测试服务；PG case skip 不代表通过。OpenClaw 在 `plugins/openclaw/octopmemory/` 单独运行 `npm ci`、`npm test`、`npm run build`。

源码仓库保留测试、CI、示例和插件；Python sdist 提供重建 wheel 的源码。开发和发布流程统一见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可证

[MIT](LICENSE)。漏洞报告渠道见 [SECURITY.md](SECURITY.md)。
