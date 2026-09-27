# octop_ui 大 payload 旁路设计 Spec（artifact 剥离方案）

> 关联 issue：TencentCloud/Octop #1032（bilibili 插件返回结果过大）
> 状态：v2 · 三方评审已合入（2026-09-23）
> 评审：step-5-preview / mimo-v2.6-pro / MiniMax-M3 三方独立审核，一致 **APPROVE WITH CHANGES**，必改项已全部合入本文（评审记录见 `tmp/spec-review-*.log`）。
> 本文所有论断均经代码阅读 + 运行时 PoC 双重验证（`tmp/verify_offload_poc.py`，真实 LangGraph agent loop，含原地修改模式复验）。

## 1. 问题

内置插件 bilibili-anime 的工具 `bilibili_search_anime`（`src/octop/infra/agents/plugins/bundled/bilibili-anime/main.py:138-196`）：

1. 搜索番剧后，对最多 8 个季（`max_seasons` 默认 5、封顶 8，`main.py:168`）逐一调用 `_fetch_episodes()` 拉取**全量剧集**（`main.py:169-174`，每季剧集数无上限）；
2. 把 `{octop_ui, data, text}` 整体序列化为一个 JSON 字符串作为 tool result 返回（`main.py:186-196`）。

对《凡人修仙传》这类长篇番剧：5 季 × 100+ 集 × 每集约 150-250 字符，tool result 典型 13-24 KB（PoC 复现 22.5 KB / 200 集）。

## 2. 根因

这个字符串同时服务四类消费者：

| 消费者 | 需求 | 路径 |
|---|---|---|
| LLM 上下文 | 越小越好 | ToolMessage.content 进 state，下次模型调用全量携带 |
| 历史持久化 | 需要完整数据供回放 | `thread_messages`（recorder 主路径 `message_to_dict`） |
| Dashboard 实时渲染 | 需要完整 data | WS `tool_result` 帧（`model_dump`） |
| 插件 UI（`ui/index.js`） | 需要完整 data | `props.data` ← 解析 tool output |

模型与 UI 的需求对立。**截断不可行**（UI 丢剧集），必须在「tool 执行后、ToolMessage 进 state 前」把数据面（大 payload）与控制面（摘要 + 渲染提示）分离。

## 3. 已验证事实

| # | 事实 | 证据 |
|---|---|---|
| F1 | `AgentMiddleware.awrap_tool_call` 可拦截工具结果并替换 ToolMessage（langchain 1.3.18）；只写 sync 版会 NotImplementedError | `langchain/agents/middleware/types.py:756-823`；Octop 先例 `infra/agents/middleware/thread_artifacts.py:186-193` |
| F2 | 中间件链组装处可闭包注入 `row`/`ws` | `manager.py:3026-3041`（`ws` 于 `manager.py:2912-2917` 构造） |
| F3 | 模型请求转换（`convert_to_openai_messages`）不含 artifact 字段，artifact 不进模型上下文 | `langchain_core/messages/utils.py:1653-1680`；PoC [3]；harness 的 memory/compaction 模块均不读 artifact（grep 实证） |
| F4 | WS 实时帧经 `model_dump()` 序列化，含 artifact；team relay 亦原样透传 | `api/routers/chat/sse.py:9-21`、`ws.py:70-75`、`teams/team_manager.py:754-773`；PoC [5] |
| F5 | 持久化主路径 `message_to_dict` → `messages_from_dict` 往返保留 artifact | `history_projection.py:64-80`、`history.py:291-313`；PoC [4] |
| F6 | **历史 API 序列化丢 artifact**：tool_result block 只输出 content | `api/routers/chat/serialize.py:937-941` |
| F7 | **dashboard 实时路径 content 优先**，且 `ToolCallData` 类型无 artifact 字段、`closeToolCall` 不提取 artifact | `chatStore.ts:1703-1756`、`1759-1858`；`sseHelpers.ts:11-22` |
| F8 | **dashboard 历史路径只读 output 字段** | `dashboard/src/utils/messageParser.ts:210-232` |
| F9 | `patchResult` 是纯前端内存操作，无服务器写回通道，刷新即丢 | `chatStore.ts:1865-1901`；`host.ts:65-68` |
| F10 | recorder 兜底分支（chunk 缺 messages 时）重建 ToolMessage 不含 artifact；常规路径（`_live_wire` → `message_to_dict`）含 artifact。兜底当前几乎不可达（harness 的 tool_result chunk 恒带 messages） | `recorder.py:177-194`；`harness_agent/protocols/langgraph.py:228-234` |
| F11 | trajectory 事件只存 content（`projector.py:85-103`），剥离后 payload 自动变小；clip 仅作用于 summary 字段 | `trajectory/projector.py:285-294`；`tests/unit/trajectory/test_trajectory_list_summarize.py:68` |
| F12 | `PluginContext` 无 workspace/agent 上下文；插件工具是纯函数 | `harness_agent/plugins/context.py:17-115`、`tools.py:78-90` |
| F13 | 插件 UI 的 host 自带鉴权 `request()` | `dashboard/src/plugins/toolRenderers/host.ts:69-71` |
| F14 | workspace 下载路由要求 agent running 且强制 attachment disposition —— 故弃用「workspace 文件 + 下载 URL」方案 | `api/common/workspace.py:37-68`、`api/routers/workspace.py:328-364` |
| F15 | 移动端无 octop_ui 消费（`mobile/tools.py:29` 是 Android UI dump 路径）；CLI repl 不读 content | `infra/mobile/tools.py`、`cli/repl/render.py:194` |
| F16 | 插件 UI 用 `{...d, ...next}` 全量回传 patch（纯前端内存） | `bilibili-anime/ui/index.js:42-45`；`parseToolOutput.ts:66-88` |
| F17 | team host 白名单仅 5 个内置工具，插件工具在 host 被 deny；team member 是独立 agent，工具+中间件齐全 | `infra/agents/teams/service.py:32-50`、`manager.py:3233-3235` |
| F18 | 备份导出按原始行拷贝 `thread_messages`，artifact 随 message_json 存活 | `infra/backup/chats.py:81-110` |
| F19 | `thread_fork.py:223-228` 把 messages（含 artifact）灌进新 checkpoint —— 但由 F3，artifact 永不进模型请求；fork 仅复制 checkpoint 存储，**不构成上下文回灌** | `infra/agents/thread_fork.py:223-228` + F3 |
| F20 | 当前 26 个 octop_ui 插件的 `data` 中均不含 `file://`/workspace 媒体路径（grep 零命中） | `src/octop/infra/agents/plugins/bundled/` |

## 4. 方案

### 4.1 新增中间件 `OctopUiOffloadMiddleware`

位置：`src/octop/infra/agents/middleware/octop_ui_offload.py`。实现 `awrap_tool_call`（async 版，F1）：

1. `result = await handler(request)`；非 ToolMessage（含 Command）→ 原样返回；
2. 剥离条件（全部满足，任一不满足原样返回）：
   - `result.content` 是 str 且长度 ≥ `_OFFLOAD_MIN_CHARS = 4000`（模块级常量）；
   - content 可解析为 JSON 对象，含非空 `octop_ui.renderer`；
   - 顶层 `data` 键存在且非空（`None`/`{}`/`[]` 不剥离）；
   - content 不含 `file://`（守护媒体/路径提取消费方，见 §4.6）；
3. 剥离动作（**原地修改**，不新建 ToolMessage，保留 `id`/`name`/`tool_call_id`/`status`/`response_metadata`/`additional_kwargs`——PoC [0] 已验证字段存活）：
   - `result.artifact = data`（`data` 键整体搬家，兄弟字段如 `results[i].episodes_error` 随 data 走，envelope 其余字段原样保留）；
   - `result.content = 去掉 data 的 envelope + "data_ref": "artifact"`；
4. 任何异常：记 warning + METRICS 计数，原样返回。

**挂载位置**：追加到 `agent_middleware` 列表**末尾（最内层）**，在 `manager.py:3026-3041` 组装。理由：langchain 语义「列表首位 = 最外层」，最内层最先看到工具原始返回、剥离后外层所有中间件（harness PII/媒体、Octop 各中间件）观测面一致。对 `ThreadArtifactsMiddleware._paths_from_content` 的影响已由 F20 + `file://` 守护条件双重兜底。

**为什么中间件优于改插件 SDK（`response_format="content_and_artifact"`）**：`_to_structured_tool` 目前不透传 response_format（F12），改 SDK 还需每个插件改返回值；中间件对现有 26 个 octop_ui 插件零改动生效，并自动覆盖未来插件。

**为什么弃用 workspace 文件 + 下载 URL**：下载路由要求 agent running（F14），agent 停止后历史播放器会挂；artifact 存消息记录内，无 agent 状态依赖，存储体积与现状相同。

### 4.2 历史 API 透出 artifact

`serialize.py:937-941` 的 tool_result block 增加 `artifact` 字段（**仅当** ToolMessage 带非空 artifact 时；additive 变更，不破坏现有消费者）。

配套文档：`docs/api.md` 标注 tool_result block 新字段及 `output` 中可能出现 `data_ref: "artifact"` 的语义；CHANGELOG 标注行为变更（见 §5 发布约束）。

### 4.3 dashboard 完整实现路径（评审确认的最大缺口，逐点落实）

1. `ToolCallData` 接口（`dashboard/src/pages/Chat/hooks/sseHelpers.ts:11-22`）增加 `artifact?: unknown`；
2. `closeToolCall`（`chatStore.ts:1759-1858`）：从 WS 帧 messages 的 ToolMessage 上提取 artifact 写入 `toolData.artifact`（F4 已证链路不丢字段：`ws.py:70-75` → `chatStore.ts:2236` → `parseHarnessChunk.ts:268-274` 原样透传）；
3. 历史路径：`extractToolData`（`messageParser.ts:210-232`）读取 block.artifact（§4.2 提供）；
4. 渲染：`MessageBubble.tsx` `ToolDetailsInline`（约 356-432 行）——`parsed.data === undefined` 且 `data_ref === "artifact"` 时，用 `toolData.artifact` 作为 `props.data`；
5. **解析优先级（防 patch 回跳）**：显式 `data` 键恒优先于 `data_ref`→artifact。因为 `mergePatchedToolOutput` 会把 patch 后的 `data` 写回 output 字符串而 `data_ref` 残留，若不定义优先级，用户选集后 UI 会跳回旧状态（`parseToolOutput.ts:66-88`）。

### 4.4 recorder 兜底分支补 artifact

`recorder.py:186-194` 重建 ToolMessage 时透传 artifact。触发概率极低（F10）但后果是历史永久丢数据，属廉价保险；同时加日志。

### 4.5 thread_fork 路径：不改代码

F19 已论证：artifact 不进模型请求（F3），fork 只复制 checkpoint 存储，无上下文回灌。harness 的 memory/compaction 路径均不读 artifact（F3 证据）。本 spec 不改 fork；集成测试补一条 fork 后用例防回归（§6）。

### 4.6 媒体/路径提取消费方守护

`ThreadArtifactsMiddleware`（`thread_artifacts.py:314`）与 `tool_media.py` 的富化函数从 content 提取文件路径/媒体块。若未来插件在 octop_ui `data` 内嵌 `file://` 路径，剥离会让这些提取失效。守护 = §4.1 条件中的 `file://` 排除（含则退回旧行为）+ F20 现状为零 + 测试计划加守护用例。

### 4.7 明确不做

- 不改 harness_agent 插件 SDK，不改任何现有插件代码；
- 不动 `patchResult`（F9 验证无回填通道）；
- trajectory 不透 artifact（F11，剥离后该面自动变小）；
- 不做 patch 状态的服务端持久化（若未来要做，只存 UI 状态增量，绝不收客户端全量 data 覆盖存储）；
- bilibili 工具的模型侧分页参数（`season_id`/`page`）是后续可选增强，不在本 spec；
- 不为超大 artifact（如 >100KB）引入 workspace 文件二级通道——后续需要时再议。

## 5. 风险与发布约束

| 风险 | 评估 | 缓解 |
|---|---|---|
| **前后端必须同批发布** | 后端先上、前端未更新 → 剥离后的 envelope 让旧前端渲染空。wheel 内嵌 dashboard 构建产物，天然原子 ✅ | 自托管分离部署场景在 CHANGELOG 标注；第三方 API 消费者迁移指引写进 `docs/api.md` |
| 新旧消息混存 | 老消息无 `data_ref`/artifact，新消息有 | 前端两条解析路径都要兼容（§4.3.4-4.3.5），测试覆盖 |
| WS 帧带宽 | artifact 随 `model_dump` 进帧，体积与今天相同（今天全量走 content） | 无回归 |
| DB 行体积 | 不变（content → artifact 同体积搬家） | — |
| 模型失去剧集明细可见性 | content 只留 `text` 摘要（数量+默认季标题），追问「第 5 集叫什么」答不出 | 行为变更写入 CHANGELOG；分页查询工具为后续增强 |
| ACP 客户端 | `harness_agent/acp/server.py:124-136` 只读 content → IDE 端看到 slim envelope | 可接受（本来也渲染不了 UI），文档注明 |
| context_usage 估算 | `harness_agent/context_usage.py` 按 content 估 token，剥离后估算与模型实际一致 | 属改善 |
| IM 通道 | 只发 tool_start/tool_end 提示行 + 媒体事件，不读 envelope | 无变化（F15、`stream_project.py:166-207`） |
| team 模式 | host 无插件工具可拦（F17）；member 正常生效，relay 透传 artifact（F4） | 关闭此项 |

## 6. 测试计划

后端：
- 中间件单元测试（新建 `tests/unit/agents/middleware/test_octop_ui_offload.py`）：剥离 / 小 payload 不动 / 非 JSON 不动 / 无 `octop_ui` 不动 / `data` 为空不动 / 含 `file://` 不动 / 坏 JSON 不动 / Command 结果不动 / 原地修改保留 `id`/`tool_call_id`/`name`/`status` / 异常吞掉并计数；
- `serialize.py` 含 artifact 的序列化用例；
- 集成：agent stream 含 octop_ui 大 payload → WS 帧 content 已压缩且 artifact 在场；历史 API 返回 artifact；fork 后新线程首调不爆量。

前端：
- `extractToolResultOutput` / `closeToolCall`：content+artifact 同帧时 artifact 落进 `toolData`；
- `extractToolData` 历史路径读 artifact；
- `parseOctopToolOutput`：`data` 优先于 `data_ref`；老格式（内联 data）兼容；
- `ToolDetailsInline` 在 `data_ref` 时用 artifact 渲染。

回归：`make all` + `cd dashboard && npx tsc -b`。

机制层已预验证：`tmp/verify_offload_poc.py`（含原地修改模式，全部断言通过）。

## 7. 开放问题 → 评审已关闭

- Q1 team 模式：**关闭**。host 白名单仅 5 内置工具（F17），插件工具不挂载，无工具可拦；member 正常。
- Q2 recorder 兜底：**关闭**。常规路径已带 artifact；兜底几乎不可达，§4.4 作廉价保险修复。
- Q3 阈值 4000：**采纳**。其余 25 个插件正常输出 <2-3KB 不误伤；bilibili 默认参数几乎恒触发（符合预期——它正是要修的对象）。
- Q4 API 兼容：**关闭**。artifact 字段 additive；`output` 语义变化经 `docs/api.md` + CHANGELOG 处理。
- Q5 IM 通道：**关闭**。剥离前后 IM 用户所见完全一致。
- Q6 WS 链路：**关闭**。帧内不丢字段，缺口在前端落点，已落为 §4.3 改动项。
