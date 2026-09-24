# 企查查 MCP 连接器

一张企查查卡片、一份 API Key，连接以下五个企业数据 Server。查询范围与额度以企查查账户权限为准。

| 数据类别 | MCP 地址 | 工具名称前缀 |
| --- | --- | --- |
| 企业信息 | `https://agent.qcc.com/mcp/company/stream` | `company__` |
| 企业风险 | `https://agent.qcc.com/mcp/risk/stream` | `risk__` |
| 知识产权 | `https://agent.qcc.com/mcp/ipr/stream` | `ipr__` |
| 经营信息 | `https://agent.qcc.com/mcp/operation/stream` | `operation__` |
| 人员信息 | `https://agent.qcc.com/mcp/executive/stream` | `executive__` |

## 使用

1. 打开「连接器 → 内置连接器」，选择「企查查」。
2. 登录 [企查查智能体平台](https://agent.qcc.com/)，在个人中心复制 API Key，粘贴到 Octop。无需 OAuth 回调。
3. 确认已开通的类别探测成功（未开通的类别会跳过），保存连接器，并在对话中选择它。
4. 输入企业全称及查询需求，例如「查询思必驰科技股份有限公司的工商变更」。

五个 MCP 地址共用同一份 Bearer API Key。连接前校验目标的 Protected Resource Metadata，
确认 resource 与 issuer 匹配；连接器不会向列表以外的 MCP 地址发送凭证。

## 共享授权与生命周期

- 一条连接器记录保存一份加密 API Key。每张卡片独立管理自己的账户凭证。
- Octop 以 `mcp_mode=internal` 托管内部 HTTP MCP：对话按 HTTP 加载 `/api/internal/mcp/qcc/…`，
  再聚合五类工具并加上类别前缀。不是进程内 gateway 适配器。
  一张卡片即可选用所有五类工具，无需创建五个独立连接器。
- 删除卡片只清除本地凭证，不会远程吊销 API Key。
- 探测会报告每类服务的结果；任一类别成功即整体可用。运行时工具发现同样只聚合成功类别。

## 验证范围

2026-09-23，贡献者在 Octop 中使用合成凭证和 HTTP MockTransport，通过真实 MCP SDK
验证五类服务的初始化、分页工具发现及工具调用；另外覆盖部分类别失败、内部接口鉴权
及跨用户删除权限。测试不访问真实账户。

五类服务的真实业务调用仍需授权账户验收。工具数量由服务端决定，不作为固定契约。

官方入口：<https://agent.qcc.com/>。
连接器图标来自该站点公开的 `/favicon-qcc.png`，用于标识企查查服务。
