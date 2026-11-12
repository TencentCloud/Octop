# 插件压缩包

插件就是一个目录，打成 ZIP 安装。Octop 解压到 `~/.octop/plugins/<id>/`，再加载 `plugin.yaml` 指向的入口。入口模块必须导出 `setup(ctx)`。

## 压缩包里怎么放

ZIP 文件头是 `PK`。解压后只能有一个带 `plugin.yaml` 的插件根，两种摆法都可以：

```text
weather-0.1.0.zip
└── plugin.yaml          # 根目录就是插件根
    main.py

weather-0.1.0.zip
└── weather/             # 或者只包在唯一一层子目录里
    ├── plugin.yaml
    └── main.py
```

解压后直接子目录里有几个 `plugin.yaml`，就认几个插件根。一个都没有，才看压缩包根上的 `plugin.yaml`。多于一个直接拒绝安装。插件根旁边可以放不带 `plugin.yaml` 的文件，但别再放第二个插件目录。

路径不能逃出解压目录。成员名里的 `..` 和绝对路径都会被拒绝。

## 体积

| 限制 | 值 |
|---|---|
| 压缩包本身 | 100 MiB |
| 解压后合计 | 64 MiB |
| 单个成员解压后 | 64 MiB |
| 成员个数 | 2000 |
| 压缩比 | 解压后超过 1 MiB 的成员，解压大小 / 压缩大小不超过 100 |

从 URL 下载时按收到的字节数算，上限同样是 100 MiB。

## 目录

```text
weather/
├── plugin.yaml          # 清单，必需
├── main.py              # entry 指向的入口，必需
├── requirements.txt     # 可选；加载时用 pip 安装
├── icon.svg             # 可选；plugin.yaml 的 icon 指向它
├── skills/              # 仅 kind: skill
│   └── city-weather/
│       └── SKILL.md
└── ui/                  # 可选；必须是已经构建好的前端
    └── dist/
        ├── index.js
        └── manifest.json
```

安装时不会跑 `npm install`。带界面的插件把构建产物直接放进 `ui/dist/`。

## plugin.yaml

必填的是 `id` 和 `version`，去掉首尾空白后不能为空。`id` 就是安装目录名 `~/.octop/plugins/<id>`，别带路径分隔符。`version` 按字符串逐字比较，不按语义化版本解析。

安装时如果请求里另外指定了期望的 `id` 或 `version`，必须和清单逐字对得上。

```yaml
id: weather
version: 0.1.0
name: 天气
description: 查询城市天气
kind: tool
entry: main.py
icon: "☀️"
group: lifestyle
requires:
  - httpx>=0.27
```

| 字段 | 必需 | 说明 |
|---|---|---|
| `id` | 是 | 插件标识，也是安装目录名 |
| `version` | 是 | 版本字符串 |
| `name` | 否 | 显示名。缺省用 `id` |
| `description` | 否 | 简介。缺省为空 |
| `kind` | 否 | `tool`、`skill`、`hook`、`channel` 之一。缺省 `tool`。大小写不敏感 |
| `entry` | 否 | 相对插件根的 Python 文件。缺省 `main.py`。文件必须存在，并定义 `setup(ctx)` |
| `requires` | 否 | pip 依赖字符串列表。加载时安装；同目录的 `requirements.txt` 也会安装 |
| `icon` | 否 | 卡片图标，见下文 |
| `group` | 否 | 分组 slug，见下文 |
| `ui` | 否 | 预构建前端，见下文 |

`kind` 不在那四个值里、`requires` 不是列表、或者 YAML 根不是对象，清单直接作废。

## 入口

`entry` 会被当成 Python 模块加载。模块里要有可调用的 `setup(ctx)`。`ctx.plugin_id` 就是清单里的 `id`，`ctx.source_path` 是插件根目录。

`setup` 里只能调用和 `kind` 对应的注册方法：

| `kind` | 在 `setup` 里调用 | 作用 |
|---|---|---|
| `tool` | `ctx.tool(name, fn, description=..., config_fields=...)` | 注册一个工具。`name` 不能为空。`fn` 可以是异步函数，参数成为调用参数 |
| `skill` | `ctx.skills("skills")` | 参数是相对插件根的目录，目录必须存在。其下每个含 `SKILL.md` 的子目录是一项技能，Agent 启动时复制到工作区 `skills/<name>/`；工作区里已有同名 `SKILL.md` 的不会覆盖 |
| `hook` | `ctx.middleware(instance, priority=100)` | 注册模型调用前后的中间件。`priority` 缺省 100 |
| `channel` | `ctx.channel(kind, ChannelClass, label=..., icon=..., intro_url=..., fields=...)` | 注册一种通道实现。通道的构造、配置表单和启用行为见 [第三方通道插件](plugin-channels.md) |

工具的 `config_fields` 是表单字段列表，比如 `{"name": "prefix", "type": "text", "required": false}`。运行时用 `get_tool_config("工具名")` 读当前 Agent 上保存的值；这些值不是模型调用参数。

`kind: tool` 的最小入口：

```python
from octop_harness.plugins import PluginContext


async def city_weather(city: str) -> str:
    """Query weather for a city."""
    return city


def setup(ctx: PluginContext) -> None:
    ctx.tool("city_weather", city_weather, description="查询城市天气")
```

## 图标

`icon` 去掉空白后最长 2048 个字符。可以是：

- 一段 emoji 或普通文字，原样显示
- `http://` 或 `https://` 开头的图片地址，由浏览器加载
- `//` 开头的地址、`/api/` 开头的站内路径，或 `data:image/` 开头的图片
- 插件内的相对图片路径，后缀为 `.svg`、`.png`、`.jpg`、`.jpeg`、`.webp`、`.gif`。文件必须在插件根内，路径不能含 `..`

## 分组

`group` 会转成小写，并把 `_` 换成 `-`。只允许字母、数字和 `-`，最长 64 个字符。空字符串视为没写。

这些 slug 在市场里有固定中文标签：`lifestyle`、`news`、`finance`、`media`、`fun`、`games`、`tools`、`ops`。其他符合格式的字符串会归到「其他」。

## 界面

`ui` 是对象时才启用。两个路径都相对插件根，不能含 `..`：

```yaml
ui:
  entry: ui/dist/index.js       # 缺省就是这个路径
  manifest: ui/dist/manifest.json
```

`entry` 指向的文件不存在时，插件就只当后端用。Dashboard 通过 `GET /api/plugins/<id>/ui/…` 加载 `entry`。脚本是自包含 ESM，在 `setup(host)` 里注册渲染器。React 由页面提供，挂在 `window.__OCTOP_REACT__` 和 `window.__OCTOP_JSX__` 上。

工具若要走这块界面，返回 JSON 字符串，并带上渲染器名字：

```json
{
  "octop_ui": { "renderer": "weather_card", "version": 1 },
  "data": { "city": "上海" },
  "text": "纯文本回退"
}
```

## 打包

在插件根的上一级打包，让 ZIP 里只出现一个插件目录：

```bash
zip -r weather-0.1.0.zip weather
```

本地安装目录或 ZIP：

```bash
octop plugin install ./weather
octop plugin install ./weather-0.1.0.zip
```
