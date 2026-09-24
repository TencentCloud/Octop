# 企查查 MCP OAuth 连接器

一张企查查卡片、一次 OAuth 授权，连接以下五个 Server。查询范围与额度以账户权限为准。

| 数据类别 | MCP 地址 | 工具名称前缀 |
| --- | --- | --- |
| 企业信息 | `https://agent.qcc.com/mcp/company/stream` | `company__` |
| 企业风险 | `https://agent.qcc.com/mcp/risk/stream` | `risk__` |
| 知识产权 | `https://agent.qcc.com/mcp/ipr/stream` | `ipr__` |
| 经营信息 | `https://agent.qcc.com/mcp/operation/stream` | `operation__` |
| 人员信息 | `https://agent.qcc.com/mcp/executive/stream` | `executive__` |

## 使用与回调部署

1. **请用系统浏览器授权**：在 Chrome 等系统浏览器打开 Octop，进入「连接器 → 内置连接器 → 企查查」，点击「一键授权」。内嵌/桌面弹窗可能无法回调；显示企查查授权成功不等于 Octop 已收到回调。
2. 本机部署可以使用 `http://127.0.0.1:端口` 或 `http://localhost:端口`。服务和浏览器必须在同一台电脑。
3. 公网部署必须配置正确的 **HTTPS 公网地址及回调** `/api/connectors/oauth/callback`，并按企查查要求完成回调域名/地址登记。公网 HTTP 会在发起授权前被拒绝；不会降级为 API Key，也不能用 localhost 替代远端服务器地址。
4. 完成登录授权后，确认 Octop 显示已授权、探测成功，在对话中选择卡片，输入企业全称及查询需求。

使用 DCR + 授权码 + PKCE S256，Client Name 为 **`Octop Connector`**，scope 为 `mcp:tools`，授权服务器为 `https://agent.qcc.com`。五类资源共用卡片保存的同一份授权；只向固定资源发送凭证，并校验 Protected Resource Metadata。

## 共享授权与生命周期

- 保留 `mcp_mode=internal`：对话通过内部 HTTP MCP 加载五类工具，不使用进程内 gateway 适配器。继续使用上游的精选工具策略；五类数据接入不意味着全部工具均暴露给模型。
- 探测和工具发现允许部分类别失败，聚合账户可用的类别，不自动申请额外权限。
- 加密持久化访问令牌、刷新令牌及动态客户端信息。即将过期时刷新；401 最多刷新后重试一次。刷新保留内部 HTTP 访问令牌，重启后读取持久化凭证。
- 同一卡片的并发请求共享刷新锁，解绑也使用该锁，防止刷新覆盖解绑。**锁仅覆盖同一进程、同一应用仓库对象，不支持多 worker/多副本同时使用同一 rotating refresh token**；部署一个应用进程，或另行实现跨进程协调。
- 删除 OAuth 卡片先远程撤销最新 refresh token，再删除本地记录。撤销失败保留凭证，以便重试。
- 已有 API Key 卡片继续运行，401 不执行 OAuth 刷新，删除仅清除本地凭证，不远程吊销 API Key。可通过一键授权迁移；新卡片以 OAuth 为默认流程。

## 验证范围

自动化测试使用合成凭证、HTTP MockTransport 和真实 MCP SDK，覆盖五类资源初始化、分页及调用、并发刷新、401 重试、数据库重开、解绑与刷新竞争、旧 API Key 兼容，以及 internal HTTP 配置进入对话的路径。公网 HTTP 回调拒绝与其它 OAuth 连接器行为有回归覆盖。

本分支尚未完成新的真实账户授权、模型对话调用和公网 HTTPS 端到端验收；历史版本的验收不能替代本分支验收。发布前需在系统浏览器完成授权，确认工具实际返回业务数据，并验证重启后查询及解绑。

官方入口：<https://agent.qcc.com/>。图标来自该站点公开的 `/favicon-qcc.png`。
