# 外部 Agent 集成指南

本页维护外部 Agent 的接入方式、宿主适配和验证约定；当前已有 OpenClaw、Hermes 实现。
核心 API 与开发流程见
[README](../README_CN.md) 和 [CONTRIBUTING](../CONTRIBUTING.md)。

## 更名与已有安装迁移

项目统一使用 `octop-memory`。Python import 为 `octop_memory`，主命令为 `octop-memory`，
bridge 为 `octopmemory-bridge`，OpenClaw/Hermes 插件 ID 为 `octopmemory`。
这是入口名称的破坏性变更，不提供旧命令、import 或环境变量别名；版本号未因改名而调整。

如果从旧项目升级，先停止宿主和所有数据库写入者，备份配置及数据库，再修改安装和启动配置：

| 配置项 | 当前名称 |
|---|---|
| 发行包 / Python import | `octop-memory` / `octop_memory` |
| bridge / Hermes 插件包 | `octopmemory-bridge` / `octop-memory-hermes` |
| OpenClaw 包 / 插件 ID | `@octop-memory/openclaw` / `octopmemory` |
| 环境变量前缀 | `OCTOP_MEMORY_*` / `OCTOPMEMORY_*` |
| 本地数据目录 | `~/.octop-memory/` / `~/.octopmemory/` |
| 宿主插件数据目录 | `~/.openclaw/octopmemory/` / `$HERMES_HOME/octopmemory/` |
| 部署目录参数 | `OCTOP_MEMORY_DIR` / `--octop-memory-dir` |
| Hermes 配置文件 | `$HERMES_HOME/octopmemory.json` |
| Python Agent 宿主 | `octop-harness` |

- 安装新发行包后更新 Python import、bridge 路径、OpenClaw entries/slot/allow/install 配置和
  Hermes provider。迁移旧插件配置到新 ID，重新运行 setup/doctor；旧包需要自行卸载，避免宿主重复加载。
- SQLite 数据库结构、namespace、`hm_*` 内部表、`harness-checkpoint-v1` 编码和 `.hmpkg`
  文件格式保持不变。可以通过显式 `db_path` 继续读取原数据库，也可以停机后备份并迁移整个数据目录；
  不要只复制仍在写入的 `.sqlite` 文件而遗漏 WAL。Chroma 的目录也需迁移或显式指定。
- PostgreSQL 新共享 schema 为 `octop_memory`。使用旧数据库时保持原 DSN，在备份、停机并确认
  新 schema 尚不存在后，由数据库所有者核实旧 schema 的实际名称，再执行
  `ALTER SCHEMA "<旧 schema 的实际名称>" RENAME TO octop_memory;`（先替换占位符）。
  已存在两个 schema 时不要覆盖，需要单独核对并合并数据。默认 DSN 数据库名也改为 `octop_memory`；
  数据库本身不要求改名，可通过 `OCTOP_MEMORY_DSN` 显式配置原数据库。
- portable 的 Agent 默认扫描路径为 `~/.octop/agents/*/memory.sqlite` 和
  `~/.octop-harness/*/memory.sqlite`。旧目录不再自动扫描；可迁移到新位置，或在 Python
  `list_sources(extra_paths=[("agent", "/path/to/previous/*/memory.sqlite")])` 中显式补充扫描路径。
- 本次源码更名不会自动搬移数据库，也不会执行远端仓库改名或 PyPI/npm 发布。
  新默认路径/schema 不会自动发现旧位置，已有安装应先完成迁移再启动。

## 接入方式与边界

Python 宿主优先使用 `MemoryService`；跨语言或隔离进程通过 stdio `octopmemory-bridge` 接入。
需要指定 Agent 的插件生命周期、工具 schema 和安装配置时，在 `plugins/<host>/` 实现适配。
`src/octop_memory/adapters/` 提供库侧 CLI/协议入口，`plugins/` 负责外部宿主侧接线，两者职责不同。

新增适配应明确四件事：namespace/session/thread 如何映射、何时 capture、何时召回和提炼、退出时如何清理后台任务。
记忆处理规则复用 `MemoryService` / `MemoryRuntime`，不要在插件中复制抽取、promotion 或排序逻辑。
在临时库上测试宿主契约，再以真实宿主验证安装、读写与生命周期；Python 单测不能代替宿主 E2E。

## 当前适配

| | OpenClaw | Hermes |
|---|---|---|
| 插件 | npm `@octop-memory/openclaw` | Python `octop-memory-hermes` / native provider |
| 接入 | TypeScript → stdio `octopmemory-bridge` | Python provider → 进程内 `Bridge` |
| Python 环境 | 独立 uv/pipx 环境，bridge 路径必须可用 | 必须装进 Hermes 实际使用的解释器 |
| 存储 | 默认 SQLite，可配置 PostgreSQL | 当前 provider 构造 SQLite |
| 默认 namespace | `openclaw__default` | `hermes__default` |
| 配置 | `openclaw.json` 中 `plugins.entries.octopmemory.config` | `$HERMES_HOME/octopmemory.json` |

Python 要求 3.12+，SQLite 需要 FTS5。宿主兼容要求以
[OpenClaw manifest](../plugins/openclaw/octopmemory/package.json) 和 Hermes provider contract 为准；
Hermes 适配要求具备 `MemoryProvider` 接口的 v0.10.0+。安装说明不代表所有后续宿主版本均已验收。

## OpenClaw

### 安装与激活

```bash
uv tool install 'octop-memory[cli]'
octopmemory-bridge --probe
openclaw plugins install @octop-memory/openclaw
octop-memory openclaw setup
openclaw gateway restart
octop-memory openclaw doctor
```

也可用 `pipx install 'octop-memory[cli]'`。probe 应返回 `ok: true` 与 `fts5: true`。
首次 setup 用 Python CLI：插件尚未取得 memory slot 时，其 `openclaw octopmemory` 子命令可能还未注册。
setup 配置 `plugins.slots.memory=octopmemory`、conversation access、namespace 和 bridge 路径。
单独在任意目录执行 npm install 不等于将插件注册到宿主。

```bash
octop-memory openclaw setup --profile proactive --namespace my_project
octop-memory openclaw setup --db-path /path/to/memory.sqlite
octop-memory openclaw setup --bridge-python /path/to/python
octop-memory openclaw print-config --profile privacy
```

setup 默认数据位于 `~/.openclaw/octopmemory/<namespace>/memory.sqlite`；自定义 OpenClaw home 时随其变化。
未显式配置路径的 bridge 才回退到 `~/.octopmemory/<namespace>/memory.sqlite`，以实际生成的配置为准。
`bridge.command` 优先于 `bridge.python`，前者由 setup 定位 console script。
切换 PostgreSQL 时在 bridge 的 Python 环境安装 `[postgres]`，设置 `backend: "postgres"`，
并向启动插件的进程注入 `OCTOP_MEMORY_DSN`；不要把含密码的 DSN 放入会经 argv 转发的 JSON 配置。

### 配置与 profile

配置顺序为 profile 默认值 < 显式 override。不要把旧 profile 表当作运行时配置真源；
完整字段、defaults 和合并逻辑见 [config.ts](../plugins/openclaw/octopmemory/src/config.ts)，
宿主校验见 [openclaw.plugin.json](../plugins/openclaw/octopmemory/openclaw.plugin.json)。

| Profile | 主要用途 |
|---|---|
| `balanced` | 默认工具提示、原始对话 capture，raw 作 fallback |
| `low_latency` | 减少搜索来源与捕获范围 |
| `proactive` | `hybrid` 自动召回；依赖宿主调用 prefetch hook |
| `privacy` | 收紧来源，raw 正文替换为占位文本，仍可保留 metadata |
| `archive` | 更完整的对话留存，包括更多 tool 内容 |
| `eval` | 用于合成评测，避免短消息过滤影响 fixture |

常用 override（合并到 `plugins.entries.octopmemory.config`）：

```json
{
  "profile": "balanced",
  "namespace": "my_project",
  "recall": {"raw_policy": "fallback", "default_max_results": 5},
  "capture": {"include_roles": ["user", "assistant"], "include_tool_results": false},
  "privacy": {"redact_secrets": true, "store_tool_payloads": false}
}
```

| 配置组 | 关键字段与语义 |
|---|---|
| `recall` | `mode`: `off` / `tool_hint` / `hybrid`；`default_corpus`: `all` / `memory` / `sessions` / `wiki` |
| `recall` | `raw_policy`: `never` / `fallback` / `always`；`host_files_policy`: `off` / `include` / `only` |
| `recall` | `default_max_results`、`max_prompt_chars`、`layer_order`、`citation_policy` 控制数量、展示预算和排序 |
| `capture` | `agent_end_hook`、`include_roles`、`min_message_chars`、`include_tool_calls/results` 控制入库范围 |
| `capture` | `skip_memory_echo` 过滤已注入片段；`host_files_watcher` 控制 Markdown 索引 |
| `privacy` | `redact_secrets`、`redact_patterns`、`store_raw_content`、`store_tool_payloads` |
| `llm` | `endpoint`、`model`、`model_heavy`、`api_key_env`、timeout/retries；优先环境变量，避免明文 key 经 argv 转发 |
| `extraction` | `promote`、`regen_pages`、`max_candidates`、`page_regen_limit` |
| `compaction` | 控制宿主上下文 flush 阈值与后续索引；不等于数据库 VACUUM |
| `bridge` | `command` / `python`、`log_level`、`spawn_timeout_ms` |

`recall.mode=off` 只关闭 prompt section，不自动关闭 capture 或删除历史。
`tool_hint` 提示模型使用工具；`hybrid` 在 host 调用 `recallPrefetcher` 后渲染结果。
OpenClaw 的 `capture.extract_on_agent_end` 还需要配置 `llm.endpoint` 才触发自动提炼；无模型时只捕获 L0。
旧字段 `recall.limit` / `total_chars` 保留兼容，新配置使用 `default_max_results` / `max_prompt_chars`。

## Hermes

### 安装器方式

先确定 Hermes 实际使用的 Python。下列路径为默认布局，非默认安装需要替换：

```bash
HERMES_PY=~/.hermes/hermes-agent/venv/bin/python
uv pip install --python "$HERMES_PY" octop-memory-hermes
"$HERMES_PY" -c 'import octop_memory, octopmemory; print("ok")'
"$HERMES_PY" -m octopmemory.installer install --no-write-pth
hermes gateway restart
"$HERMES_PY" -m octopmemory.installer doctor
hermes memory status
```

这里包已安装到宿主解释器，`--no-write-pth` 避免另写共享解释器路径。
没有 uv 时可在该解释器执行 `-m ensurepip --upgrade`，再用 `-m pip install octop-memory-hermes`。
不要从 `hermes` 命令的 shebang 猜解释器，它可能是 shell wrapper。

installer 将 provider 放到 `<hermes-source>/plugins/memory/octopmemory/`，备份并修改 config 的
`memory.provider: octopmemory`。非默认布局用 `--hermes-home` / `--hermes-source`；
升级覆盖需显式 `--force`。`doctor` 检查配置、文件与 import 能力，不等于完整 capture 验收。

### Native plugin 方式

维护者可用 `scripts/build-hermes-plugin.sh` 生成独立 plugin 目录；目录包含 provider 和 manifest，
不包含 installer。将该目录作为独立仓库分发后，由用户使用实际的插件仓库 URL：

```bash
hermes plugins install --enable <plugin-repository-url>
hermes memory setup
hermes gateway restart
hermes memory status
```

在 setup 中选择 `octopmemory`，由宿主安装 manifest 声明的核心依赖。
此分发方式没有 `octopmemory.installer`，不要照抄安装器方式的 doctor；以宿主 status 和实际搜索验收。
本仓不假定插件已被上游内置收录。

### 配置和文件

| 路径 | 用途 |
|---|---|
| `$HERMES_HOME/config.yaml` | 选择 `memory.provider` |
| `$HERMES_HOME/octopmemory.json` | 插件配置；省略时使用默认值 |
| `$HERMES_HOME/octopmemory/memory.sqlite` | 默认数据文件 |
| `$HERMES_HOME/memories/` | 默认 host Markdown root |

`hermes memory setup` 调用 provider 的 `get_config_schema()` / `save_config()`；点号 key 会转换为嵌套配置，
并深合并已有文件。配置支持 profile、namespace、db_path、recall/capture/privacy 与 host files，
实际字段见 [provider 源码](../plugins/hermes/octopmemory/__init__.py)。不要将 OpenClaw 的 TS profile 默认值照搬到 Hermes。

```json
{
  "namespace": "hermes__default",
  "recall": {"default_max_results": 5, "raw_policy": "fallback"},
  "capture": {"min_message_chars": 0, "include_roles": ["user", "assistant"]},
  "privacy": {"redact_secrets": true, "store_tool_payloads": false}
}
```

## 共同验证与排错

先在测试环境完成几轮合成对话，再搜索实际写入的词：

```bash
openclaw octopmemory status
openclaw octopmemory search "Python"
hermes octopmemory status
hermes octopmemory search "Python" -n 5 --corpus all
```

用搜索返回的 path 调用 `memory_get` 或宿主 `show`；不要自行猜测 atom ID。
检查命中层、正文、namespace，再检查模型 prompt 是否使用这些结果。

| 现象 | 检查顺序 |
|---|---|
| bridge 启动失败 | probe 的 FTS5、有效 Python 路径、依赖、handshake 日志 |
| Hermes import 失败 | 宿主解释器是否能 import，而非终端默认 Python |
| 插件未加载 | memory slot/provider、安装目录、重启和宿主 status |
| 没有 raw | conversation access、capture 开关、roles、短消息阈值、privacy、实际 db/namespace |
| 没有 atom | 是否有 LLM、是否触发 extraction、Candidate 的 review 状态 |
| 工具能搜但 prompt 没注入 | OpenClaw recall.mode、host 是否调用 prefetch；不要用 doctor 成功推断自动注入 |
| host 文件没命中 | `host_files_root`、watcher、allowlist；默认不扫描整个工作目录 |

默认文件范围为 `MEMORY.md`、`USER.md` 与显式专题 Markdown；不要把 session、日志或数据库加进 allowlist。
迁移使用核心 CLI 的 `portable list-sources / pack / adopt / doctor`；导出的 `.hmpkg` 含记忆数据，不提交到仓库。

## 修改适配器

共用业务逻辑放 `application/`；宿主层只转换 hook/tool contract。现有 OpenClaw/Hermes 适配暴露
`memory_search(query, maxResults?, minScore?, corpus?)` 与 `memory_get(path, from?, lines?, corpus?)`。
搜索结果含 `hits[]`，路径读取返回 `path/excerpt`；corpus 和字段以实际工具 schema 为准。

Hermes 的 `initialize` 必须接受 `hermes_home`；provider 方法和 manifest 事件 hook 是两类接口，不能混放。
`sync_turn` 负责后台 capture，`prefetch` 同步召回，`queue_prefetch` 当前是 no-op；shutdown 要等待后台任务。
[plugin.yaml](../plugins/hermes/octopmemory/plugin.yaml) 和 [contract tests](../tests/test_hermes_contract.py)
共同维护接口。fallback stub 只能支撑本仓单测，真实 Hermes 兼容性仍需 E2E。

```bash
uv run pytest tests/test_hermes_contract.py tests/test_hermes_adapter.py tests/test_hermes_install.py -q
HERMES_SOURCE=/path/to/hermes-agent bash scripts/e2e_hermes_test.sh
npm ci --prefix plugins/openclaw/octopmemory
npm test --prefix plugins/openclaw/octopmemory
npm run typecheck --prefix plugins/openclaw/octopmemory
npm run build --prefix plugins/openclaw/octopmemory
bash scripts/e2e_openclaw_test.sh
```

E2E 可能安装或启动宿主，使用隔离环境并阅读脚本；缺少真实 host 导致的 skip 不算兼容性通过。
