# 企查查 MCP 连接器

一张企查查卡片，支持 **一键 OAuth** 或 **API Key**，连接以下五个 Server。查询范围与额度以账户权限为准。

| 数据类别 | MCP 地址 | 工具名称前缀 |
| --- | --- | --- |
| 企业信息 | `https://agent.qcc.com/mcp/company/stream` | `company__` |
| 企业风险 | `https://agent.qcc.com/mcp/risk/stream` | `risk__` |
| 知识产权 | `https://agent.qcc.com/mcp/ipr/stream` | `ipr__` |
| 经营信息 | `https://agent.qcc.com/mcp/operation/stream` | `operation__` |
| 人员信息 | `https://agent.qcc.com/mcp/executive/stream` | `executive__` |

## 两种接入方式

### 方式一：一键 OAuth（推荐，有 HTTPS 或本机时）

1. **请用系统浏览器授权**：在 Chrome 等系统浏览器打开 Octop，进入「连接器 → 内置连接器 → 企查查」，点击「一键授权」。内嵌/桌面弹窗可能无法回调；显示企查查授权成功不等于 Octop 已收到回调。
2. 本机部署可以使用 `http://127.0.0.1:端口` 或 `http://localhost:端口`。服务和浏览器必须在同一台电脑。
3. 公网部署必须配置正确的 **HTTPS 公网地址及回调** `/api/connectors/oauth/callback`，并按企查查要求完成回调域名/地址登记。公网 HTTP 会在发起授权前被拒绝，也不能用 localhost 替代远端服务器地址。
4. 使用 DCR + 授权码 + PKCE S256，Client Name 为 **`Octop Connector`**，scope 为 `mcp:tools`，授权服务器为 `https://agent.qcc.com`。

### 方式二：API Key（无公网 HTTPS 时）

1. 当前浏览器地址为**公网 HTTP**（非 localhost）时，抽屉不显示「一键授权」，改为「打开授权页」。
2. 点击「打开授权页」进入企查查平台获取 API Key（见 [agent.qcc.com](https://agent.qcc.com/)）。
3. 粘贴到抽屉中的 **API Key** 字段，探测并保存。
4. 不依赖 OAuth 回调；适合内网、HTTP 公网或无法登记回调域名的部署。
5. 与一键授权二选一：保存 API Key 会替换已有 OAuth 凭证；完成一键授权会替换已有 API Key。本机或 HTTPS 环境下也可同时看到「打开授权页」，用于手动取 Key。

完成任一方式后，确认 Octop 显示已授权/已配置、探测成功，在对话中选择卡片并使用默认执行模式（Craft），输入企业全称及查询需求。Ask / Plan 模式按产品设计禁用 MCP，不能用于验证连接器调用。

五类资源共用卡片保存的同一份凭证；只向固定资源发送凭证，并校验 Protected Resource Metadata。

## 共享授权与生命周期

- 保留 `mcp_mode=internal`：对话通过内部 HTTP MCP 加载五类工具，不使用进程内 gateway 适配器。继续使用上游的精选工具策略；五类数据接入不意味着全部工具均暴露给模型。
- 探测和工具发现允许部分类别失败，聚合账户可用的类别，不自动申请额外权限。
- **OAuth**：加密持久化访问令牌、刷新令牌及动态客户端信息。即将过期时刷新；401 最多刷新后重试一次。刷新保留内部 HTTP 访问令牌，重启后读取持久化凭证。
- **API Key**：以 Bearer 调用五类 MCP；401 不执行 OAuth 刷新；删除仅清除本地凭证，不远程吊销。
- 同一卡片的并发请求共享刷新锁，解绑也使用该锁，防止刷新覆盖解绑。**锁仅覆盖同一进程、同一应用仓库对象，不支持多 worker/多副本同时使用同一 rotating refresh token**；部署一个应用进程，或另行实现跨进程协调。
- 删除 OAuth 卡片先远程撤销最新 refresh token，再删除本地记录。撤销失败保留凭证，以便重试。删除 API Key 卡片只清本地。

## 验证范围

自动化测试使用合成凭证、HTTP MockTransport 和真实 MCP SDK，覆盖五类资源初始化、分页及调用、并发刷新、401 重试、数据库重开、解绑与刷新竞争、API Key / OAuth 双模式，以及 internal HTTP 配置进入对话的路径。公网 HTTP 回调拒绝与其它 OAuth 连接器行为有回归覆盖。

2026-09-24，在本分支实现提交 `bf1ea4e` 上完成新的本地真实账户验收（独立实例 `127.0.0.1:8089`）：

- 系统 Chrome 完成 OAuth；五类 Server 共发现 6 个精选工具。
- 五类资源各实际调用一项，均返回 HTTP 200、无 JSON-RPC error、`isError=false`。
- 将本地到期时间设为过期，触发真实远端刷新；5 个并发发现请求均成功，访问/刷新令牌轮换，内部访问令牌不变。未等待自然到期，精确刷新次数由单元测试覆盖。
- 完整重启后，无需重新授权，五类资源再次调用成功。
- 通过 Octop Dashboard WebSocket 发起真实模型对话，在 Craft 模式选择该连接器，实际调用 `company__get_company_profile` 并收到成功工具结果。初次 Ask 模式不暴露 MCP，是模式规则而非 OAuth 故障。
- 解绑返回 204、本地记录删除、旧内部入口返回 404；使用刚撤销的刷新令牌再次刷新，远端返回 400 / `invalid_grant`。验收授权已撤销。

这是五类资源各一项的抽样验收；没有逐一验证全部上游工具。公网 HTTPS 回调、桌面内嵌弹窗及多进程部署未做真实端到端验收。公网部署仍需按上述回调要求配置并单独验证；无 HTTPS 时请改用 API Key。

官方入口：<https://agent.qcc.com/>。图标来自该站点公开的 `/favicon-qcc.png`。
