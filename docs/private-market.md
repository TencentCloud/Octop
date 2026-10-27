# 内网自建插件市场与专家市场

访问不了 `octop.cloud` 和 `download.octop.cloud` 时，可以在局域网里按本文的 HTTP 接口自建市场。Octop 只认这两份目录和目录里给出的安装包地址，不需要部署完整的 octop.cloud。

技能市场（控制台「技能」里的 SkillHub）是另一套上游，默认 `https://api.skillhub.cn`，用 `SKILLHUB_HOST` 指定。那套协议不在本文范围内。

## Octop 怎么访问市场

```
控制台打开插件市场 / 专家市场
        │
        ▼
Octop 进程  GET {OCTOP_PORTAL_URL}/api/market/plugins
            GET {OCTOP_PORTAL_URL}/api/market/experts
        │
        │  成功后把 data.items 整表缓存 30 秒
        ▼
用户点击安装
        │
        ▼
Octop 进程  GET 该条目的 download_url
            （必须落在 OCTOP_MARKET_REMOTE_URL 上，且路径以 /octop/market/ 开头）
```

两条目录都是一次取全量。Octop 不传查询参数，专家的搜索和场景筛选都在本地做。所以 `content`、`quick_prompts` 也要放在列表条目里：详情页读的是同一份缓存，不会再去请求 `/{id}`。

请求不带登录态。把市场放在内网，靠网络边界限制谁能访问；别指望 Octop 会带 Token。

单次目录响应不超过 **1 MiB**，超时 **8 秒**。请求头带 `Accept: application/json` 和 `User-Agent: Octop`。`success` 必须是 JSON 布尔值 `true`。`data.items` 必须是数组，里面不是对象的元素会被丢掉。HTTP 错误、超时、门户地址为空、或者 `success` 不是 `true`，都算目录不可用：插件市场和专家市场都显示「暂时不可用」。

成功结果在进程里缓存 30 秒。改完 JSON 等一会儿，或者重启 Octop，再刷新页面。

## 让 Octop 指向自建市场

在 **跑 `octop run` 的那台机器** 上设置环境变量，然后重启进程。可以写进 `~/.octop/env`（服务启动时会载入），也可以写进 systemd 的 `Environment=`。

```bash
OCTOP_PORTAL_URL=http://market.internal:9000
OCTOP_MARKET_REMOTE_URL=http://market.internal:9000
```

| 变量 | 含义 |
|---|---|
| `OCTOP_PORTAL_URL` | 目录源站，只写协议、主机和端口，**不要带路径**。未设置时默认 `https://octop.cloud`。设成空字符串则关闭远程目录。 |
| `OCTOP_MARKET_REMOTE_URL` | 安装包源站，同样只保留源站。未设置或无法解析时默认 `https://download.octop.cloud`。 |

目录和安装包可以放同一台机器，所以上面两个变量可以相同。`download_url` 必须同时满足：

- 协议、主机与 `OCTOP_MARKET_REMOTE_URL` 一致
- 环境变量里写了端口时，`download_url` 的端口也要相同；没写端口就用该协议的默认端口，URL 里也不要另加端口
- 路径以 `/octop/market/` 开头

推荐路径：

```text
/octop/market/plugins/{id}/{version}/{id}-{version}.zip
/octop/market/experts/{slug}/{version}/{slug}-{version}.zip
```

图标别指向公网。插件卡片的 `icon` 由**浏览器**直接加载；专家的 `icon_url` 若是 `http(s)` 图片，由 **Octop 进程**在创建专家时下载（失败就不用这张图，创建照常继续）。内网能访问的地址，或者下面的 `icon_name`，都行。

## 接口

```yaml
openapi: 3.0.3
info:
  title: Octop private plugin and expert market
  version: "1"
  description: >
    Catalog read by the Octop server. Octop calls only the two list
    operations. Archive bytes are fetched from download_url.
servers:
  - url: http://market.internal:9000
paths:
  /api/market/plugins:
    get:
      operationId: listMarketPlugins
      summary: Full plugin catalog
      responses:
        "200":
          description: Catalog envelope
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/PluginCatalog"
  /api/market/experts:
    get:
      operationId: listMarketExperts
      summary: Full expert catalog
      responses:
        "200":
          description: Catalog envelope
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ExpertCatalog"
components:
  schemas:
    Localized:
      oneOf:
        - type: string
        - type: object
          properties:
            zh: { type: string }
            en: { type: string }
    PluginCatalog:
      type: object
      required: [success, data]
      properties:
        success: { type: boolean, enum: [true] }
        data:
          type: object
          required: [items]
          properties:
            items:
              type: array
              items: { $ref: "#/components/schemas/Plugin" }
    ExpertCatalog:
      type: object
      required: [success, data]
      properties:
        success: { type: boolean, enum: [true] }
        data:
          type: object
          required: [items]
          properties:
            items:
              type: array
              items: { $ref: "#/components/schemas/Expert" }
    Plugin:
      type: object
      required: [id, version, download_url]
      properties:
        id: { type: string, pattern: "^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$" }
        version: { type: string }
        name: { $ref: "#/components/schemas/Localized" }
        description: { $ref: "#/components/schemas/Localized" }
        kind: { type: string, default: tool }
        icon: { type: string, description: "Emoji, or an http(s) URL the browser can load" }
        group: { type: string }
        requires:
          type: array
          items: { type: string }
        download_url: { type: string, format: uri }
        updated_at: { type: string, description: "ISO-8601. Octop sorts newer stamps first." }
    Expert:
      type: object
      required: [slug, download_url]
      properties:
        id: { type: string }
        slug: { type: string, pattern: "^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$" }
        label: { $ref: "#/components/schemas/Localized" }
        description: { $ref: "#/components/schemas/Localized" }
        scene: { type: string }
        sub_scene: { type: string }
        icon_url: { type: string, description: "http(s) raster image, or omit and use icon_name" }
        icon_name: { type: string }
        color: { type: string }
        skill_slugs:
          type: array
          items: { type: string }
        skill_count: { type: integer }
        content: { $ref: "#/components/schemas/Localized" }
        quick_prompts:
          type: array
          items:
            type: object
            properties:
              title: { $ref: "#/components/schemas/Localized" }
              description: { $ref: "#/components/schemas/Localized" }
              prompt: { $ref: "#/components/schemas/Localized" }
              color: { type: string }
              icon_name: { type: string }
        task_examples:
          type: object
          properties:
            zh: { type: array, items: { type: string } }
            en: { type: array, items: { type: string } }
        download_url: { type: string, format: uri }
        updated_at: { type: string }
```

`id` 和 `slug` 的字符集：以字母或数字开头，后面可以跟字母、数字、`.`、`_`、`-`，总共最长 81 个字符。

插件安装时，目录里的 `version` 必须和压缩包内 `plugin.yaml` 的 `version` 逐字一致，`id` 也要一致。专家安装时，压缩包里 `manifest.json` 的 `id` 必须等于目录里的 `slug`。

`updated_at` 用同一形式的 ISO-8601（比如 `2026-10-26T00:00:00Z`）。Octop 按这个字符串倒序排。

已知的插件分组会显示成中文标签，其他字符串会归到「其他」：`lifestyle`、`news`、`finance`、`media`、`fun`、`games`、`tools`、`ops`。

已知的专家场景同样有翻译，其他字符串按原文显示：`ecommerce`、`finance`、`content-creation`、`lifestyle`、`marketing`、`mysticism`、`academic`、`legal`、`tech`、`education`、`healthcare`、`hr`、`media`、`design`。

## 安装包里要有什么

- 插件压缩包的目录、体积和 `plugin.yaml` 最小清单见 [插件压缩包](plugin-package.md)。
- 专家压缩包的目录、体积和 `manifest.json` 见 [专家压缩包](expert-package.md)。

## 最小部署

同一源站同时提供目录和文件时，目录可以是这样：

```text
/srv/octop-market/
├── api/market/plugins          # 内容类型 application/json
├── api/market/experts
└── octop/market/
    ├── plugins/weather/0.1.0/weather-0.1.0.zip
    └── experts/ops-engineer/1.0.0/ops-engineer-1.0.0.zip
```

`api/market/plugins` 的正文：

```json
{
  "success": true,
  "data": {
    "items": [
      {
        "id": "weather",
        "version": "0.1.0",
        "name": { "zh": "天气", "en": "Weather" },
        "description": { "zh": "查询城市天气", "en": "City weather" },
        "kind": "tool",
        "icon": "☀️",
        "group": "lifestyle",
        "requires": [],
        "download_url": "http://market.internal:9000/octop/market/plugins/weather/0.1.0/weather-0.1.0.zip",
        "updated_at": "2026-10-26T00:00:00Z"
      }
    ]
  }
}
```

用 Nginx 把这个目录挂到任意端口就行，下面的 `9000` 只是示例，换成你自己的端口后，环境变量和 `download_url` 里的端口也要一起改。`api/market/plugins` 和 `api/market/experts` 是没有扩展名的文件，需要显式标成 JSON：

```nginx
server {
    listen 9000;
    server_name market.internal;
    root /srv/octop-market;
    location /api/market/ {
        default_type application/json;
    }
}
```

然后在 Octop 上设好前面两个环境变量并重启。打开控制台的插件市场和专家市场，应该能看到自建条目；安装时 Octop 只会向 `market.internal` 要压缩包。

## 对照检查

| 现象 | 原因 |
|---|---|
| 插件市场或专家市场显示暂时不可用 | 目录请求失败、超时，或 `OCTOP_PORTAL_URL` 为空。在 Octop 机器上 `curl` 两个列表地址，确认 8 秒内返回 `"success": true`。 |
| 卡片在，安装报没有安装包 | `download_url` 的协议、主机、端口和 `OCTOP_MARKET_REMOTE_URL` 不一致，或路径不是 `/octop/market/` 开头。 |
| 安装后版本对不上 | 目录 `version` 与 `plugin.yaml` 的 `version` 不一致；或专家 `slug` 与 `manifest.json` 的 `id` 不一致。 |
| 改了 JSON 页面不变 | 进程内缓存约 30 秒。等待或重启 Octop。 |
| 图标空白 | 图标地址仍指向公网。改成 emoji、`icon_name`，或浏览器和 Octop 都能打开的内网地址。 |
