# 自建技能市场

控制台「技能」里的 SkillHub 技能市场默认请求 `https://api.skillhub.cn`。访问不了公网时，可以在局域网里按本文的 HTTP 接口自建一个兼容源站。Octop 只认下面三个读接口，不需要部署完整的 SkillHub。

插件市场和专家市场是另一套目录，见 [内网自建市场](private-market.md)。专家技能集（`/api/v1/skillsets`）也不走这里，仍用 `SKILLHUB_HOST`（未设置时同样是 `https://api.skillhub.cn`）。从技能集里拉取单个技能压缩包时，走的是本文的下载接口，因此也会落到 `SKILL_MARKET_ORIGIN`。

## Octop 怎么访问

```
控制台打开技能市场
        │
        ▼
Octop 进程  GET {SKILL_MARKET_ORIGIN}/api/v1/showcase/hot
            GET …/featured  …/newest  …/recommended  …/trending  …/paid
        │
        │  六个榜单各自请求；某一个失败时，其余榜单仍返回
        ▼
用户搜索
        │
        ▼
Octop 进程  GET {SKILL_MARKET_ORIGIN}/api/v1/search?q=…&limit=…
        │
用户点击安装
        │
        ▼
Octop 进程  GET {SKILL_MARKET_ORIGIN}/api/v1/download?slug=…
```

请求不带登录态。把市场放在内网，靠网络边界限制谁能访问。

搜索和榜单超时 **10 秒**，单次 JSON 不超过 **4 MiB**。下载超时 **30 秒**，压缩包不超过 **32 MiB**。请求头带 `User-Agent: octop-skillhub-market/1.0`。搜索和榜单的 `Accept` 是 `application/json`；下载的 `Accept` 是 `application/zip,application/octet-stream,*/*`。

空关键字会被换成 `a`。`limit` 会被夹到 1–100。榜单没有单独的 `all` 路径：Octop 自己并发请求上面六个路径，再拼成 `{ "rankings": { "hot": …, … } }`。

`SKILL_MARKET_ORIGIN` **已设置**时，这些请求失败就直接报错，不会再改去公网的 `skillhub` 命令行。未设置时，HTTP 失败仍可能退回那条命令行，而命令行访问的是公网注册表。

## 让 Octop 指向自建市场

在 **跑 `octop run` 的那台机器** 上设置环境变量，然后重启进程。可以写进 `~/.octop/env`（服务启动时会载入），也可以写进 systemd 的 `Environment=`。

```bash
SKILL_MARKET_ORIGIN=http://market.internal:9000
```

只写协议、主机和端口，**不要带路径**。写成 `market.internal:9000` 时按 `https://` 补协议。写了路径、查询或账号信息也会被丢掉，实际请求仍是 `{源站}/api/v1/...`。未设置或空字符串时用 `https://api.skillhub.cn`。协议不是 `http`/`https`，或没有主机名，则这次请求失败，不会悄悄改回公网。

## 接口

```yaml
openapi: 3.0.3
info:
  title: Octop private skill market
  version: "1"
  description: >
    Read by the Octop server. Search and the six showcase paths return
    JSON. Download returns a ZIP. There is no combined rankings path.
servers:
  - url: http://market.internal:9000
paths:
  /api/v1/search:
    get:
      operationId: searchSkills
      summary: Search skills
      parameters:
        - in: query
          name: q
          required: true
          schema: { type: string }
        - in: query
          name: limit
          schema: { type: integer, minimum: 1, maximum: 100 }
      responses:
        "200":
          description: Search envelope
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/SearchResponse"
  /api/v1/showcase/{kind}:
    get:
      operationId: showcaseSkills
      summary: One ranking section
      parameters:
        - in: path
          name: kind
          required: true
          schema:
            type: string
            enum: [hot, featured, newest, recommended, trending, paid]
      responses:
        "200":
          description: Ranking object. Octop passes it through.
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Ranking"
  /api/v1/download:
    get:
      operationId: downloadSkill
      summary: Skill package bytes
      parameters:
        - in: query
          name: slug
          required: true
          schema: { type: string }
      responses:
        "200":
          description: ZIP archive
          content:
            application/zip:
              schema: { type: string, format: binary }
        "404":
          description: Skill is not published
components:
  schemas:
    SearchResponse:
      type: object
      required: [results]
      properties:
        results:
          type: array
          items: { $ref: "#/components/schemas/Skill" }
    Ranking:
      type: object
      properties:
        section: { type: string }
        total: { type: integer }
        skills:
          type: array
          items: { $ref: "#/components/schemas/Skill" }
    Skill:
      type: object
      required: [slug]
      properties:
        slug: { type: string }
        displayName: { type: string }
        name: { type: string }
        summary: { type: string }
        description: { type: string }
        version: { type: string }
        description_zh: { type: string }
        iconUrl: { type: string, description: "http(s) URL the browser can load" }
        downloads: { type: integer }
        installs: { type: integer }
        stars: { type: integer }
        category: { type: string }
        labels:
          type: object
          additionalProperties: true
```

搜索结果里没有 `slug` 的条目会被丢掉。卡片标题用 `displayName`，没有再用 `name`，再没有就用 `slug`。简介用 `summary`，没有再用 `description`。`version` 按字符串保存。其余字段原样留给控制台，例如 `iconUrl`、`description_zh`、`downloads`、`labels`。

榜单对象原样返回。控制台读的是每个榜单里的 `skills` 数组，元素字段和搜索相同。`section` 和 `total` 可以带，不参与安装。

下载必须是 ZIP。包内要有根上的 `SKILL.md`；如果所有文件都在同一个顶层目录里，且该目录下有 `SKILL.md`，Octop 会剥掉这一层。解压后条目不超过 **2000** 个，未压缩总体积不超过 **64 MiB**。符号链接、绝对路径、`..` 和加密条目会被拒绝。HTTP 404 表示这个 slug 没有安装包。

`iconUrl` 由**浏览器**直接加载，不要指向 Octop 进程才访问得到的地址。

## 最小部署

```text
/srv/skill-market/
├── api/v1/search                 # 忽略查询参数，返回一份固定结果也行
├── api/v1/showcase/recommended
├── api/v1/showcase/hot
├── api/v1/showcase/featured
├── api/v1/showcase/newest
├── api/v1/showcase/trending
├── api/v1/showcase/paid
└── api/v1/download               # 按 slug 查询参数返回对应 ZIP
```

`api/v1/search` 的正文：

```json
{
  "results": [
    {
      "slug": "weather",
      "displayName": "天气",
      "summary": "查询城市天气",
      "version": "0.1.0",
      "description_zh": "查询城市天气",
      "iconUrl": "http://market.internal:9000/icons/weather.png"
    }
  ]
}
```

`api/v1/showcase/recommended` 的正文：

```json
{
  "section": "recommended",
  "total": 1,
  "skills": [
    {
      "slug": "weather",
      "displayName": "天气",
      "summary": "查询城市天气",
      "version": "0.1.0"
    }
  ]
}
```

用 Nginx 把这个目录挂到任意端口就行，下面的 `9000` 只是示例。没有扩展名的接口需要显式标成 JSON；下载接口要按 `slug` 选出 ZIP，静态文件不够时用一段很小的反代即可。

```nginx
server {
    listen 9000;
    server_name market.internal;
    root /srv/skill-market;
    location /api/v1/showcase/ {
        default_type application/json;
    }
    location = /api/v1/search {
        default_type application/json;
    }
}
```

然后在 Octop 上设好 `SKILL_MARKET_ORIGIN` 并重启。打开控制台的技能市场，榜单和搜索应出现自建条目；安装时 Octop 只会向这个源站要压缩包。

## 对照检查

| 现象 | 原因 |
|---|---|
| 技能市场仍是公网内容 | `SKILL_MARKET_ORIGIN` 没进 `octop run` 的环境，或改完没有重启。在 Octop 机器上 `curl` 搜索地址，确认 10 秒内返回带 `results` 的 JSON。 |
| 设了变量后市场直接报错 | 源站协议或主机名无效，或榜单 / 搜索没有在时限内返回合法 JSON。此时不会再退回公网命令行。 |
| 卡片在，安装失败 | `GET /api/v1/download?slug=` 不是 ZIP，包内没有 `SKILL.md`，或超过体积限制。404 表示这个 slug 没有包。 |
| 图标空白 | `iconUrl` 仍指向公网，或浏览器打不开该地址。 |
| 专家市场没跟着变 | 专家技能集目录不读 `SKILL_MARKET_ORIGIN`。它用 `SKILLHUB_HOST`。 |
