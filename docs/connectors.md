# Built-in connectors

**English** · [中文](#内置连接器)

Octop ships a catalog of OAuth / MCP connectors. Dashboard copy (`name`,
`description`, `auth_hint`, and credential-field labels) is bilingual (`en` /
`zh`) and follows `Accept-Language`.

**Source of truth:** [`src/octop/infra/connectors/catalog.json`](../src/octop/infra/connectors/catalog.json).
`src/octop/infra/connectors/catalog.py` only loads and validates that file.

You can also add **custom MCP** servers in the dashboard; they are not listed here.

# 内置连接器

[English](#built-in-connectors) · **中文**

Octop 内置一组 OAuth / MCP 连接器。控制台展示的名称、描述、授权提示和凭证字段
文案支持中英双语，跟随 `Accept-Language`。

**元数据源：** [`src/octop/infra/connectors/catalog.json`](../src/octop/infra/connectors/catalog.json)。
`catalog.py` 只负责加载和校验，不再手写 `_CATALOG`。

控制台还可以添加**自定义 MCP**，不在下表中。完整目录见下方表格。

## Catalog / 目录

The table below must match `catalog.json` (kind, English name, Chinese name,
category, auth, MCP mode, and order). Do not edit the rows by hand unless you
are updating `catalog.json` in the same change.

下表必须与 `catalog.json` 一致（`kind`、英文名、中文名、分类、鉴权、MCP 模式、顺序）。
改连接器时先改 JSON，再改此表。

| Kind | Name | 名称 | Category | Auth | MCP mode |
|------|------|------|----------|------|----------|
| `tencent-docs` | Tencent Docs | 腾讯文档 | office | personal_token | remote |
| `tencent-ima` | Tencent IMA | 腾讯 IMA | knowledge | api_key | gateway |
| `tencent-meeting` | Tencent Meeting | 腾讯会议 | office | personal_token | remote |
| `tencent-news` | Tencent News | 腾讯新闻 | media | api_key | gateway |
| `wechat-reading` | Weixin Reading | 微信读书 | media | api_key | gateway |
| `tencent-lexiang` | Tencent Lexiang | 腾讯乐享 | office | api_key | remote |
| `tencent-weiyun` | Tencent Weiyun | 腾讯微云 | office | personal_token | remote |
| `qq-mail` | Personal Mail | 个人邮箱 | productivity | imap_app_password | gateway |
| `qq-music` | QQ Music | QQ 音乐 | media | api_key | gateway |
| `fliggy` | Fliggy | 飞猪 | travel | api_key | gateway |
| `baidu-map` | Baidu Maps | 百度地图 | travel | api_key | gateway |
| `ctrip-wendao` | Trip.com Wendao | 携程问道 | travel | api_key | gateway |
| `meituan-travel` | Meituan Travel | 美团旅游助手 | travel | api_key | gateway |
| `didi` | DiDi | 滴滴 | travel | api_key | remote |
| `yuandian` | Yuandian | 元典 | professional | api_key | gateway |
| `qcc` | Qichacha | 企查查 | professional | oauth2 | internal |
| `tencent-ardot` | Tencent Ardot | 腾讯设计 Ardot | office | oauth2 | remote |
| `youdao-note` | Youdao Note | 有道云笔记 | knowledge | personal_token | remote |
| `open-design` | OpenDesign | OpenDesign | self_hosted | custom_fields | managed |
| `notion` | Notion | Notion | knowledge | oauth2 | remote |
| `openalex` | OpenAlex | OpenAlex | knowledge | oauth2 | remote |
| `dida365` | TickTick | 滴答清单 | productivity | oauth2 | remote |
| `feishu-cli` | Feishu CLI | 飞书 CLI | office | api_key | gateway |
| `wecom-cli` | WeCom CLI | 企业微信 CLI | office | api_key | gateway |
| `dingtalk-cli` | DingTalk CLI | 钉钉 CLI | office | custom_fields | gateway |
| `agently-cli` | Agent Mail | Agent Mail | office | custom_fields | gateway |
| `obsidian-cli` | Obsidian | Obsidian | knowledge | custom_fields | gateway |
| `yuque-mcp` | Yuque (official MCP) | 语雀（官方 MCP） | knowledge | personal_token | stdio |
| `weknora` | WeKnora | WeKnora | knowledge | custom_fields | gateway |
| `dify` | Dify | Dify | self_hosted | custom_fields | remote |

## MCP modes / MCP 模式

| Mode | Meaning | 含义 |
|------|---------|------|
| `remote` | The harness talks to the vendor MCP URL. | Harness 直连厂商 MCP 地址。 |
| `gateway` | An in-process Python adapter; the harness config is a name-only placeholder. | 进程内 Python 适配器；Harness 配置只占位。 |
| `stdio` | Managed persistent MCP subprocess, isolated per conversation. | 按对话隔离的持续 MCP 子进程。 |
| `internal` | Octop hosts HTTP MCP at `/api/internal/mcp`; the harness loads it over HTTP. | Octop 在 `/api/internal/mcp` 托管 HTTP MCP，Harness 经 HTTP 加载。 |

## Catalog JSON / 目录 JSON

Each `connectors[]` object is a `ConnectorCatalogEntry`. User-facing strings are
either a plain string (used for both locales) or `{ "en": "…", "zh": "…" }`.

`connectors[]` 每一项对应一个 `ConnectorCatalogEntry`。用户可见字符串可以是普通字符串（中英共用），或 `{ "en": "…", "zh": "…" }`。

Required fields: `kind`, `name`, `description`, `auth_kind`, `doc_url`, `icon`,
`color`, `phase`, `mcp_mode`, `category`.

Optional: `quick_auth_url`, `login_url`, `guide_url`, `manual_url`, `auth_hint`,
`allowed_tools`, `oauth_issuer`, `mcp_url`, `oauth_resource`, `oauth_scopes`,
`mcp_user_agent`, `credential_fields`, `remote_transport` (default `raw_http`).

`credential_fields[]` items: `key`, `label`; optional `field_type` (`text` /
`password` / `url` / `tags`), `required`, `placeholder`, `help`, `secret`.

## Deep dives / 深入说明

- [OpenDesign](connectors-open-design.md)
- [Agent Mail CLI](connectors-agently-mail.md)
- [Qichacha / 企查查](connectors-qcc.md)
