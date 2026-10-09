# Bridge（Octop ↔ Octop 实例桥）

> 状态：实现中（Phase 0–3 骨架已落地）。命名与范围以本文为准；实现落在 `infra/bridge/`。  
> 与同机 Agent 互调无关：见 [agent-call-agent.md](./agent-call-agent.md)（`ask_agent` 不参与跨实例）。

用户级连接另一台 Octop（云端或另一台本地），在本机 Dashboard 查看对端专家列表、按需拉取对话记录，并像选择本地专家一样与对端专家对话（对称：对端也可经同一桥访问本机）。对话只在**专家所在实例**执行；发起侧不落库完整历史。

## 1. 需求结论

| 项 | 结论 |
|----|------|
| 连接粒度 | 用户级：地址 + 用户名 + 密码；密码加密存储便于自动重连 |
| 多节点 | 同一用户可同时连接多个远程 Octop |
| 拓扑 | 两边均可主动建连；同一逻辑连接共用一个 `connection_id` |
| 专家 | 在线拉取列表；影子入口；不复制 workspace；不安装为本地 runnable agent |
| 可见范围 | 与该账号在对端本机可见范围一致（无额外「联邦可见」勾选） |
| UI | 远程单独入口/分组，不与本地专家混排 |
| 对话执行 | 仅在专家所在侧跑 harness；发起侧不改 harness |
| 历史 | 按需拉取；权威在专家所在侧；发起侧仅临时会话、不写本机 threads |
| 附件 | 支持；文件落入专家所在侧 `inbound/` |
| 前端调用 | 浏览器只打本机 API；本机识别远程后经桥转发 |
| 远程 agent id | `bridge:{connection_id}:{remote_agent_id}` |
| 传输 | 联邦长连接用 WebSocket；其上以**通用 HTTP 隧道**为主；特殊能力以后再补显式 RPC |
| 非目标 | 改造 `ask_agent` / harness 跨端协议；双边双写完整聊天记录；浏览器直连对端 baseURL |

## 2. 总体架构

```
┌─────────────────────┐         Bridge WS（双向可发起）        ┌─────────────────────┐
│ 本机 Octop          │◄─────────────────────────────────────►│ 对端 Octop          │
│                     │   HTTP 隧道 + turn 流式多路复用         │                     │
│ Dashboard ──HTTP──► │                                       │ ◄──HTTP── Dashboard │
│   localhost API     │                                       │   peer API          │
│         │           │                                       │         │           │
│   infra/bridge      │                                       │   infra/bridge      │
│   (识别 bridge:* /  │                                       │   (执行隧道请求)     │
│    转发 / 收隧道)   │                                       │                     │
│         │           │                                       │         │           │
│ 本地 agent+harness  │                                       │ 对端 agent+harness  │
└─────────────────────┘                                       └─────────────────────┘
```

![图 2-1 总体架构：两台 Octop 经 Bridge WebSocket 互联](./assets/bridge-architecture.png)
<!-- 生图建议：扁平化技术架构示意图，16:9。左侧一台服务器图标标「本机 Octop」，右侧标「对端 Octop」，中间一条加粗双向箭头标「Bridge WebSocket（双向可发起）」，细注「HTTP 隧道 + turn 流式多路复用」。两侧各自画出：Dashboard（浏览器仅连本机）、localhost/peer API、infra/bridge 模块、本地/对端 agent+harness。强调机机总线是独立 Bridge WS，不复用浏览器 Hub。现代 SaaS 蓝灰配色、等宽无衬线、留白充足。（注意：含精确文字的架构图建议用 Mermaid/Excalidraw 生成；AI 生图只作概念示意图，文字以图注补充） -->

- **Harness / GlobalProcessor** 保持单机语义；桥只负责把请求送到对端执行并把响应送回。
- Dashboard 的 `WebSocketHub` 仅服务浏览器↔本机；**机机总线是独立的 Bridge WS**，不要复用 Hub。
- NAT：对端 HTTP 往往不可达时，业务走已建立的 Bridge WS 隧道（尤其云端访问家里的本地实例）。

## 3. 模块边界

| 路径 | 职责 |
|------|------|
| `infra/bridge/connections.py` | 连接 CRUD、加密凭证、`connection_id`、多节点 |
| `infra/bridge/transport.py` | 出站 WS 客户端 + 入站 WS 端点；重连；同 `connection_id` 去重合并 |
| `infra/bridge/http_tunnel.py` | 通用 `method/path/query/headers/body` ↔ 响应；分片、超时、取消 |
| `infra/bridge/router.py` | 本机侧：目标为 `bridge:*`（或显式 connection 上下文）时改走隧道 |
| `infra/bridge/chat_bridge.py` | 远程对话：本机 chat WS ↔ 桥上对端 turn 流 |
| `api/routers/bridge.py` | 连接管理 HTTP（探测/添加/列表/删除/连接/改名）；Dashboard 入口在 **设置 → 远程桥接**（`/bridge`，知识库下方） |
| `cli/commands/bridge.py` | 同一套管理面的 CLI：`octop bridge`（list/get/probe/create/patch/delete/connect/disconnect/agents） |

### 探测（probe，不落库）

添加连接前可先 `POST /api/bridge/probe`：用填写的 `peer_base_url` + 用户名/密码对端 HTTP 登录，再拉 `GET /api/agents?scope=mine`，返回专家摘要列表（`agent_id` / `name` / `description` / 绝对 `icon_url` 等）。**不**写入 `bridge_connections`，**不**建立 Bridge WS。Dashboard 添加抽屉里的「探测」按钮走此接口。

「保存并连接」仅在登录 + Bridge WS `hello_ack` 成功后落库；失败回滚。管理 API 按连接所有者鉴权（登录用户即可管理自己的桥）。入站隧道允许 **agent 范围内** 的读写（聊天、工作区、定时任务、状态，以及个性化里标记为 limited 的工具 / 插件 / 渠道，含 `PATCH …/tool-settings` 与 `POST …/reload`），外加只读 composer：`GET /api/providers/resolved`、`GET /api/providers/active-model`、`GET /api/knowledge-bases`、`GET /api/knowledge-bases/capability`，以及 Chat dock 浏览器 viewer：`GET /api/browser/env-status`、`GET /api/browser/harness-sessions`、`POST /api/browser/sessions/{id}/handoff`。技能包、全局 ACP、连接器管理、知识库管理在 Dashboard 标为 peer-only，应在对端操作。管理 / 认证 / Bridge 控制面不入隧道。`history-migration` 仅本机处理。入站 hello 不得抢占他人 `connection_id`。旧入口 `/admin/advanced?tab=bridge` 会重定向到 `/bridge`。


依赖：`api` → `infra/bridge` → 现有 `infra`（对端登录、对端执行 agents/history/upload）。  
禁止：`bridge` → `api/` / `cli/` / `launch.py`（peer turn / browser runner 由 `build_app` 注入）；禁止用 Dashboard Hub 做机机通道。

## 4. 连接与身份

### 4.1 配对流程

1. 用户在本机填：`base_url`、`username`、`password`。
2. 发起方用 HTTP 调对端 `POST /api/auth/login` 换 token（**首次配对假定发起方能 HTTP 打到对端**；若不可达需由另一侧发起或另做配对码——实现前写死一种冷启动路径）。
3. 生成 `connection_id`（ULID）；握手帧确认后**两边各存同一 id**。
4. 建立 Bridge WS；之后业务优先走隧道（尤其反向访问 NAT 后实例）。
5. 密码与 token **加密落库**；重连优先 refresh，失败再用密码登录。

![图 4-1 配对流程：从填表到建立 Bridge WS](./assets/bridge-pairing-flow.png)
<!-- 生图建议：横向步骤/时序图。①用户填 base_url+用户名+密码；②本机发 HTTP 登录对端换 token（箭头指向对端）；③生成 ULID connection_id；④握手帧确认后两边各存同一 id（两个数据库图标显示相同 id）；⑤建立 Bridge WS，业务优先走隧道。编号圆点或泳道呈现，蓝灰科技风。（精确流程图建议用 Mermaid，AI 生图作概念示意） -->

### 4.2 存储（示意）

表名建议：`bridge_connections`。

| 列 | 说明 |
|----|------|
| `connection_id` | 双方一致的逻辑连接 id |
| `owner_user_id` | 本机用户 |
| `peer_base_url` | 对端地址 |
| `peer_username` | 对端登录名 |
| `display_name` | **必填**、同一用户下唯一；聊天页分组切换用的显示名 |
| `notes` | 可选备注，仅本机展示 |
| `password_encrypted` | 加密密码 |
| `access_token_encrypted` / refresh / 过期时间 | 会话 |
| `created_at` / `last_seen_at` / `status` | 元数据 |

同一本机用户可有多行（多远程节点）。

### 4.3 鉴权与可见性

- 隧道内请求以**对端该登录用户**身份执行。
- 专家可见范围 = 该用户在对端本机可见范围。
- 本机用户 id 与对端用户 id **无对应关系**。

### 4.4 双向主动连

- 任一侧可 dial；握手携带 `connection_id` + 用户证明。
- 已存在同一 `connection_id` 的活连接则合并或踢旧，避免双管道。

## 5. 通用 HTTP 隧道

机制通用：任意 `method + path + query + headers + body` 可经 Bridge WS 转发；产品 v1 先接专家列表、对话、历史上传、附件。不是「只服务这几类」的专用协议；可选 path 允许/拒绝仅作安全开关。

### 5.1 帧形态（示意）

```text
→ tunnel.request  { id, method, path, query, headers, body_b64? | chunks }
← tunnel.response { id, status, headers, body_b64? | chunks, done }
← tunnel.error    { id, code, message }
→ tunnel.cancel   { id }
```

- 大 body（上传）分片；支持取消与超时。
- SSE：v1 可不透传或单独标记；实时对话用 §6 的 turn 流，避免与 HTTP 隧道搅在一起。

![图 5-1 HTTP 隧道帧流转：Bridge WS 上的请求/响应/错误/取消帧](./assets/bridge-tunnel-frames.png)
<!-- 生图建议：展示一条 Bridge WS 管道上流动的四类消息气泡：tunnel.request（id/method/path/body）、tunnel.response（status/body/chunks/done）、tunnel.error、tunnel.cancel。标注「大 body 分片」「支持取消/超时」。画成消息流气泡，蓝灰风。（含文字帧名建议用 Mermaid 序列图，AI 生图作概念示意） -->

### 5.2 本机路由（浏览器只打本机）

1. Dashboard 请求本机（列表、history、upload、chat 等）。
2. 若目标为 `bridge:{connection_id}:{agent_id}`（或带 connection 上下文）：
   - path 内 agent id 改写为对端真实 id；
   - 经该 connection 隧道发到对端；
   - 将 status/body 原样返回浏览器。
3. 本地真实 agent 仍走现有代码，零隧道。

![图 5-2 本机路由：浏览器只打本机，bridge:* 目标改走隧道](./assets/bridge-routing.png)
<!-- 生图建议：路由判断图。浏览器→本机 API；本机 router 用菱形判断目标是否为 bridge:{connection_id}:{agent_id}：若是则改写真实 id 并经隧道转发对端、原样回传（蓝色「隧道路径」）；若本地真实 agent 则零隧道走现有代码（绿色「本地路径」）。双色区分两条分支。（建议用 Mermaid 流程图，AI 生图作概念示意） -->

## 6. 远程专家与对话

### 6.1 列表

- Dashboard「远程节点」按 connection 分组。
- 本机经隧道调对端 `GET /api/agents`（或等价列表），将 id 映射为 `bridge:{connection_id}:{id}` 再返回前端。
- 不写本地 `agents` 表作为权威（进程内短缓存可选）。

### 6.2 开聊

- 前端仍连本机：`/api/agents/bridge:…/chat/ws`（或等价入口）。
- 本机识别 `bridge:*`：不启本地 harness；将 user_turn / subscribe 转到对端对应 agent 的对话通道。
- 对端正常 `GlobalProcessor → harness`；chunk 经桥回传，本机再推给浏览器（帧形状尽量与现有 dashboard chat 一致）。
- 同一条 Bridge WS 上：**HTTP 隧道**与 **turn 流式帧**多路复用。
- Chat dock「远程浏览器」在 `bridge:*` 专家下经隧道读对端 `env-status` / `harness-sessions` / `handoff`，画面走显式 `browser.*` 中继（`WS /api/bridge/connections/{id}/browser-stream/ws`）；独立 Remote Browser 页与 install/录制仍打本机。

![图 6-1 远程对话中继：前端→本机 chat WS→对端 harness→chunk 回传](./assets/bridge-chat-relay.png)
<!-- 生图建议：远程专家对话时序/泳道图。泳道：浏览器 / 本机 bridge / 对端 harness。前端→本机 /api/agents/bridge:…/chat/ws；本机识别 bridge:* 不启本地 harness，把 user_turn/subscribe 转对端对话通道；对端 GlobalProcessor→harness 产出 chunk，经桥回传，本机再推浏览器。底部注「同一 Bridge WS 上 HTTP 隧道与 turn 流多路复用」。蓝灰风。（精确时序建议用 Mermaid，AI 生图作概念示意） -->

### 6.3 会话与历史

- Thread 只在专家所在侧创建与持久化。
- 发起侧：连接/内存级临时会话（持有对端 `thread_id`），**不写**本机 `threads` / `thread_messages`。
- 对话列表与历史：本机 API → 隧道 → 对端现有 history API。
- 对称：云端聊本地专家时，权威在本地。

### 6.4 附件

- 前端仍 `POST` 本机 `/api/agents/bridge:…/upload`。
- 本机隧道转发对端同名 upload，文件落入对端 `inbound/`。
- 预览/下载由本机代理（再隧道 GET），避免浏览器直连对端。

![图 6-2 附件代理：上传经隧道落对端 inbound，本机只代理](./assets/bridge-attachment-proxy.png)
<!-- 生图建议：附件上传代理图。前端 POST 本机 /upload；本机隧道转发对端同名 upload，文件落入对端 inbound/（强调「文件只在对端落盘、本机只代理」）；预览/下载由本机代理（再隧道 GET）避免浏览器直连对端。箭头带文件图标，蓝色隧道路径突出。蓝灰风。（建议用 Mermaid，AI 生图作概念示意） -->

## 7. 与现有组件关系

| 现有 | Bridge 中的角色 |
|------|-----------------|
| Dashboard chat WS / `WebSocketHub` | 仅浏览器↔本机 |
| `GlobalProcessor` / harness | 只在专家所在侧跑 |
| `ask_agent` / Team | 不参与跨实例 |
| `POST …/upload` + `inbound/` | 对端执行；发起侧代理 |
| 用户 JWT | 本机≠对端；隧道用对端登录态 |
| Connector（OAuth/MCP） | 无关；勿与 `bridge` 混名 |

## 8. 分期

| 阶段 | 内容 |
|------|------|
| Phase 0 | 连接 CRUD、密码加密、登录换 token、双边 WS、`connection_id` 握手与去重、隧道 ping/health |
| Phase 1 | 远程分组列表、`bridge:*` 映射、经隧道拉 agents / history；Dashboard 远程入口 |
| Phase 2 | 本机 chat WS ↔ 对端 turn 中继；临时会话；取消/断线 |
| Phase 3 | upload/预览经隧道分片代理 |
| Phase 4 | 多连接稳定性、token 刷新、path 策略、可观测性；必要时对极少数能力补显式 RPC |

## 9. 风险与约束

1. **配对冷启动**：添加连接时对端 HTTP 不可达则无法用「登录换 token」完成首配——须约定由可达的一侧发起，或引入配对码/中继。
2. **隧道面过大**：协议通用后需身份隔离 + 可选 path 策略 + 审计，避免误暴露危险管理 API。
3. **双连接竞态**：两边同时 dial 同一 `connection_id` 必须合并。
4. **流式对话**：不要把 turn 硬塞进模拟 HTTP SSE；HTTP 隧道与 turn 流分帧、同连接多路复用。
5. **版本 skew**：握手带 octop / bridge protocol version；不兼容则拒绝并提示升级。

## 10. 命名一览

| 用途 | 命名 |
|------|------|
| 包 | `octop.infra.bridge` |
| HTTP 管理 API | `/api/bridge/...` |
| CLI | `octop bridge`（与 Dashboard 对端管理同一套 `BridgeManager`） |
| 远程 agent id | `bridge:{connection_id}:{remote_agent_id}` |
| 表 | `bridge_connections` |
| 产品文案 | 「远程节点」/ Bridge（中英文另定） |

旧讨论中的 `federation` / `fed:` **不再使用**。
