# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.5] - 2026-10-24

### 新增

- 可选网页搜索：you.com、腾讯元宝 SearchPro、DeepSeek Search。
- 新增 `ManagedMCPClient`，支持持久 MCP 会话。
- 刷新腾讯云 HAI 预设，DeepSeek Flash 标为多模态。

### 修复

- MCP 工具失败改为工具错误结果，本轮继续，并保留参数 schema。
- HITL 恢复时保留请求身份、工具选择和语言。
- 决策筛选保留发文件、浏览和截图工具。
- 提前结束 agent 流时关闭内层生成器，避免 ContextVar 报错。
- 修复中文 Windows 下 shell 的 UTF-8 输出被丢弃。

### 变更

- 记忆开关决定 `USER.md` / `MEMORY.md` 只读还是可编辑，并可用 `manual_document_policy` 覆盖。

## [1.0.4] - 2026-10-16

### 新增

- 插件系统支持 channel 类型：插件可注册通道实现及展示元数据，宿主按注册所有权收集；同类型冲突时保留先注册的通道。
- 可选决策模型在主模型开口前筛选技能、工具和队友；决策调用失败时保留完整目录。后续轮次打分时带上最近对话，状态预算溢出时仍保留最新消息。
- `USER.md` 与 `MEMORY.md` 由用户手动维护，文件工具禁止 Agent 写入；首次引导只引导用户填写档案。两份文档每个会话加载一次并复用快照，手动修改对新会话生效。用户说「记住」时通过 `memory_save` 写入 octop-memory，并依赖 `octop-memory>=1.0.2`。
- 记忆写入或晋升后与当前手动文档核对。召回按实际会话快照过滤重复；明确冲突以手动文档为准并转为候选审核，同时提示用户。

### 修复

- 本地 Laya 的 CPU 决策批次可能需要约二十秒，通用十五秒客户端超时会导致反复回退到未变更结果；放宽该超时以便批次完成。

### 变更

- 工作区上下文复用 deepagents 原生 `MemoryMiddleware` 的读取、会话快照、提示词格式和缓存断点。加载器只包裹文件内容，`MEMORY.md` 写保护并入现有 `FilesystemGuardMiddleware`，移除单独的记忆规则模块。
- 模型重试耗尽后抛出异常（`on_failure="error"`），由 checkpoint 与宿主记录失败；沿用原有重试判定、次数与退避。团队任务捕获 SDK 异常并释放任务锁；自动失败通知不进入记忆采集。

## [1.0.3] - 2026-10-14

### 新增

- `MemoryMiddleware.pause_background` 支持宿主按专家暂停并排空后台记忆任务，供备份恢复使用。
- 记忆辅助调用使用独立 SDK 实例控制重试次数与退避；回退时重新计算目标模型参数，不携带首选模型的厂商扩展，避免影响主聊天（TencentCloud/Octop#1360）。
- 记忆辅助调用可配置客户端兜底 `memory_aux_max_tokens`（提炼预算仍走 `memory_extract_max_tokens`），以及 OpenAI 兼容端点的 `memory_aux_extra_body`。显式 `extra_body` 覆盖 `memory_aux_thinking` 生成的同名键。
- OpenAI 兼容模型支持按模型选择 Chat Completions 或 Responses API，并可显式开启受限的 Responses → Chat Completions 回退。

### 修复

- ChatGPT Codex 端点使用无状态流式 Responses 请求，将主系统提示词映射到 instructions，后续系统消息保留为 developer；显式 instructions 原样保留，并保留多轮工具历史；将 langchain-openai 最低版本提高至 1.3.3，避免无状态历史引用未存储条目。
- 减少启动和对话过程中的重复诊断日志，保留需要关注的错误与告警。

## [1.0.2] - 2026-10-09

### 修复

- 将 `deepagents` 下限提高到 `>=0.7.16`，接入上游同路径并行 `edit_file` / `write_file` 防护（langchain-ai/deepagents#6446）。
- 记忆辅助调用可单独配置读取超时。提炼输出预算写入 memory runtime 的 `extraction.max_tokens`（提取器总会自带预算，客户端兜底覆盖不到）。OpenAI 兼容端点在 `auto` 下对 Qwen3 / QwQ / DeepSeek-R / reasoner 默认关闭深度思考（TencentCloud/Octop#1360）。
- 小时增量 vacuum 预算提高到 5000 页，大批删除后的 freelist 可在数小时内回收，而不是数周。

## [1.0.1] - 2026-10-03

### 新增

- PII 可识别大陆手机号与 18 位居民身份证。
- 子树专家支持 `explicit_virtual_paths`，由调用方自行转换虚拟路径。
- 新增讯飞星辰 Token Plan 供应商预设。

### 修复

- 子 Agent 仅在真正重名时告警。
- 模型和路径错误回传给 Agent，不再整轮中止。
- 修复 S3 / Postgres workspace 与 deepagents 0.7 的兼容，文件不再摊平到存储根。
- Docker 每次执行刷新全局环境。
- 流式 thinking / text 块不再导致协议投影崩溃。

### 变更

- 发版时同步检查多语言 README 版本。
### Added

- PII protection detects mainland China mobile numbers (common 13-19
  prefixes, optional ``+86`` / ``0086``) and 18-character resident IDs with
  a known province code, 1900-2099 birth date, and a valid checksum.
  Existing ``pii_strategy`` / ``pii_surfaces`` apply; 15-digit IDs and other
  countries’ numbers are out of scope.
- Optional ``explicit_virtual_paths`` for subtree experts: shell command,
  environment, and stdout are left unparsed; callers convert one virtual
  absolute path through ``virtual_to_native_path``. Default stays off.
- Bundled provider templates: iFlytek Astron MaaS Token Plan preset
  `iflytek-astron-token-plan` (Spark-X2.5 first; Kimi-K2.6 and Qwen3.5/3.6 marked
  image-capable), with an `iflytek.svg` logo.

### Fixed

- Workspace subagent loading no longer logs a spurious ``Duplicate subagent
  name`` warning when the same ``.octop/agents/*.md`` definition is discovered
  through both the legacy ``agents/`` root and the canonical
  ``system_files_path`` root; the warning now only fires for genuine name
  collisions between different files.
- Leftover Windows absolute paths in filesystem tool calls (``D:\\octop-data\\…``)
  are rewritten onto the current storage root when the same suffix exists, and
  still soft-fail to the model when they do not — they no longer abort the turn
  as a generic model-call failure.
- S3 backend resolution always uses the bundled boto3 implementation, which
  speaks deepagents 0.7 (`WriteResult` / `ReadResult` / `ls` / `glob` /
  `grep`). The `deepagents-backends` 0.2 S3 client is no longer preferred —
  it still passes the removed `files_update` keyword and cannot list or read
  under 0.7. Community path-style aliases (`s3_force_path_style` /
  `force_path_style` / `path_style`) map to `addressing_style="path"`.
  Custom endpoints default to SigV4 + path-style, disable optional CRC
  checksums, and fall back ListObjectsV2 → ListObjects / GetObject when the
  store rejects a header or signature flavour.
- Postgres backend specs accept a libpq `connection_string` / `dsn` and drop
  unknown keys instead of raising `TypeError` on `PostgresConfig`.
- Postgres workspace I/O uses a bundled `psycopg` backend that speaks
  deepagents 0.7 (`WriteResult` / `ReadResult` / `ls` / `glob` / `grep`).
  Probe performs a real write→read→delete round-trip; the table is created
  on first use.
- COS / S3 / OSS / OBS / Postgres workspaces no longer flatten files onto
  the storage root. Agent files live under `/.octop/workspaces/<id>/` so
  listing `/` shows workspace folders, then the workspace tree. Host
  paths such as `~/.octop/agents/<id>` are remapped onto that virtual
  folder and are not stored as object keys.
- Docker execution reloads the global environment file even when a same-size edit or atomic replacement preserves its modification timestamp, avoiding stale injected values.
- Streamed content blocks (Anthropic thinking / text, OpenAI Responses) no
  longer crash chunk projection: list-typed ``AIMessageChunk.content`` is
  normalized per block (thinking → reasoning, text → token) instead of raising
  ``TypeError`` in ``ThinkSplitter.feed``. Plain ``str`` content is unchanged.

## [1.0.0] - 2026-09-24

### 新增

- 首个 1.0.0 正式版本发布到 PyPI。

### 变更

- 对齐 Octop：引入 `develop` 集成分支策略；禁止直推 `main`/`develop`；发版后由 `sync-main-to-develop.yml` 同步；新增 `/publish` skill（发版同步 CHANGELOG / README）。



### Fixed

- Built-in tools soft-fail instead of aborting the agent turn: ``web_fetch``
  (non-http(s) / oversized body), ``current_time`` (unknown timezone),
  ``desktop_screenshot`` (capture ``RuntimeError``), ``acp_runner`` (missing
  ``thread_id`` on close/stream), and local ``execute`` (non-positive timeout).
- Filesystem tools: ``Path ... outside root directory`` ``ValueError`` from
  deepagents ``FilesystemBackend`` is softened by ``FilesystemGuardMiddleware``
  (always mounted) into a ``ToolMessage(status="error")`` so ToolNode does not
  abort the agent turn; deny-path rules still apply when permissions are set.
