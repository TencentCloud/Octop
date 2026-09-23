# 企查查 MCP 连接器

一张企查查卡片、一次 OAuth 登录，连接以下五个企业数据 Server。查询范围与额度以企查查账户权限为准。

| 数据类别 | MCP 地址 | 工具名称前缀 |
| --- | --- | --- |
| 企业信息 | `https://agent.qcc.com/mcp/company/stream` | `company__` |
| 企业风险 | `https://agent.qcc.com/mcp/risk/stream` | `risk__` |
| 知识产权 | `https://agent.qcc.com/mcp/ipr/stream` | `ipr__` |
| 经营信息 | `https://agent.qcc.com/mcp/operation/stream` | `operation__` |
| 人员信息 | `https://agent.qcc.com/mcp/executive/stream` | `executive__` |

## 使用

1. 打开「连接器 → 内置连接器」，选择「企查查」。
2. 点击「一键授权」，在企查查页面登录并完成授权，无需手动填写 API Key。
3. 返回 Octop，确认五类服务探测成功，保存连接器，并在对话中选择它。
4. 输入企业全称及查询需求，例如「查询思必驰科技股份有限公司的工商变更」。

授权以 company 为入口，复用动态客户端注册、PKCE 和 `mcp:tools` scope。
依据企查查 OAuth 接入文档 V1.4，同一 grant 的 Access Token、Refresh Token 和
client_id 可用于上述五个精确地址。连接前校验目标的 Protected Resource Metadata，
确认 resource 与 issuer 匹配；连接器不会向列表以外的 MCP 地址发送凭证。

## 共享授权与生命周期

- 一条连接器记录保存一份加密授权。每张卡片独立管理自己的账户凭证。
- Octop 内部 HTTP MCP 网关聚合五类工具，保留输入 Schema，并加上类别前缀，避免工具重名。
  一张卡片即可选用所有五类工具，无需创建五个独立连接器。
- 每次上游请求读取最新凭证；临近到期时刷新，401 时最多刷新并重试一次。
  同一 Octop 进程、同一仓库实例内的并发请求共享刷新锁；轮换后的 Token 写回加密存储。
  此锁不覆盖多个 Octop 进程同时使用同一授权的部署。
- 重启后从数据库恢复凭证和内部访问令牌，无需依赖原登录弹窗。授权失效时仍需重新授权。
- 删除卡片时先撤销最新 Refresh Token，再删除本地凭证，五类服务一起解绑。
  撤销失败会保留凭证并报错，供用户重试。已发出的请求可能完成，且撤销 Refresh Token
  不等同于服务端立即吊销所有已签发 Access Token。
- 探测会报告每类服务的结果；任一失败即不报告整体成功。运行时工具发现也要求五类服务均可访问。

## 本地授权与浏览器兼容性

本地部署的回调地址为 `http://127.0.0.1:<实际端口>/api/connectors/oauth/callback`
（地址取决于访问 Octop 时使用的主机和端口）。保持 Octop 服务运行。
若桌面端无法打开授权弹窗，可在独立 Chrome 浏览器中打开同一 Octop 本地页面授权。
允许该 Octop 站点弹窗；如企查查页面请求访问本机应用或本地网络，按需允许该站点。

企查查成功页可能保留在弹窗中，由隐藏 iframe 触发本地回调。
应以 Octop 的授权状态、连接探测和实际工具调用确认完成，不能仅以企查查成功页判断。
Web/云端部署需要将实际 HTTPS 回调地址与企查查确认并加入白名单。

## 验证范围

2026-09-23，贡献者在 Octop v1.0.1 的自定义 MCP 中，使用独立 Chrome、空 Headers
完成 OAuth 授权，发现 company 的 16 个工具，并通过 `get_change_records` 返回实际企业变更数据。
此记录验证了 company 服务与通用 OAuth 流程，不代表五类真实服务均已验证。

本变更的自动化测试使用合成凭证和 HTTP MockTransport，通过真实 MCP SDK 验证五类服务的
初始化、分页工具发现及工具调用；另外覆盖并发刷新、重复 401、数据库重新打开后的凭证恢复、
刷新与解绑竞争、撤销失败重试、内部接口鉴权及跨用户解绑权限。测试不访问真实账户。

五类服务的真实业务调用、真实 Token 到期刷新、完整应用重启和真实撤销仍需授权账户验收。
桌面内嵌浏览器的弹窗及回调兼容不属于此次变更。工具数量由服务端决定，不作为固定契约。

官方入口：<https://agent.qcc.com/>。
连接器图标来自该站点公开的 `/favicon-qcc.png`，用于标识企查查服务。
