# 专家压缩包

专家就是一个目录，打成 ZIP 安装。Octop 把它放到 `~/.octop/expert_market/<id>/`，建 Agent 时再把里面的文件拷进工作区。

安装包里只留空白模板 `default`。其他模板从专家市场安装。照着下面的目录结构打 ZIP 就行。

## 压缩包里怎么放

ZIP 文件头是 `PK`。`manifest.json` 有两种位置：

```text
ops-engineer-1.0.0.zip
├── manifest.json        # 根目录就是专家目录
├── SOUL.md
└── skills/

ops-engineer-1.0.0.zip
└── ops-engineer/        # 或者唯一的一层子目录里有清单
    ├── manifest.json
    └── SOUL.md
```

根上有 `manifest.json` 时，解压出来的整个目录就是专家目录，`skills/` 等子目录原样保留。根上没有时，解压结果里必须正好有一个子目录，且里面有 `manifest.json`。多一个子目录（包括 macOS 打出来的 `__MACOSX`）都找不到清单。

成员路径不能是绝对路径，也不能含 `..`。

## 体积

| 限制 | 值 |
|---|---|
| 压缩包本身 | 32 MiB |
| 解压后合计 | 64 MiB |
| 成员个数 | 2000 |
| 压缩比 | 解压后超过 1 MiB 的成员，解压大小 / 压缩大小不超过 100 |

## 目录

```text
ops-engineer/
├── manifest.json        # 清单，必需
├── SOUL.md              # 人格，建议有
├── IDENTITY.md          # 可选
├── USER.md              # 可选
├── AGENTS.md            # 可选
├── skills/
│   └── k8s-triage/
│       └── SKILL.md     # 一项技能
└── agents/
    └── reviewer.md      # 一个子 Agent
```

除 `manifest.json` 外，每个文件都按相对路径写进 Agent 工作区。清单本身放到工作区 `.octop/manifest.json`，欢迎语、快捷提示和任务示例都从这里读。

`prompt_files` 列出创建页要预览的根目录 Markdown，比如 `SOUL.md`。只认根目录下没有子目录的 `*.md`。`skills/` 下的文件和 `agents/*.md` 也会出现在预览里。人格正文写在这些 Markdown 里；`prompt_files` 只管预览列出哪些根文件。

常见的根目录 Markdown 还有 `TOOLS.md`、`HEARTBEAT.md`、`PROACTIVE.md`。工作区里实际会放进哪些文件，以压缩包里的文件为准。

技能目录是 `skills/<name>/`，其中要有 `SKILL.md`。文件开头用 YAML frontmatter 写 `name` 和 `description`。子 Agent 是 `agents/` 下的一个 Markdown 文件。

## manifest.json

安装时这份 JSON 必须是对象。`id` 去掉首尾空白后，必须和这次安装用的专家标识一致。标识以字母或数字开头，后面可以跟字母、数字、`.`、`_`、`-`，总共最长 81 个字符。

清单里至少再写一个 `label`。其他字段不填就留空。

```json
{
  "id": "ops-engineer",
  "label": { "zh": "运维工程师", "en": "Ops Engineer" },
  "description": {
    "zh": "Linux、Kubernetes 和网络诊断。",
    "en": "Linux, Kubernetes, and network diagnostics."
  },
  "welcome_message": {
    "zh": "告诉我你要排查的问题",
    "en": "Tell me what to troubleshoot"
  },
  "icon_name": "terminal",
  "color": "#16a34a",
  "prompt_files": ["SOUL.md", "IDENTITY.md"],
  "quick_prompts": [
    {
      "title": { "zh": "K8s Pod 排障", "en": "Debug a K8s pod" },
      "description": { "zh": "查看状态、事件和日志", "en": "Status, events, and logs" },
      "prompt": { "zh": "请给出排查 Pod 异常的命令", "en": "Commands to debug a failing pod" },
      "color": "#e8f4ff",
      "icon_name": "server"
    }
  ],
  "task_examples": {
    "zh": [
      "每天「09:00」巡检集群，有异常再通知我",
      "每周一「10:00」汇总上周故障",
      "每个工作日「18:00」复盘当天告警"
    ],
    "en": [
      "Every day at 09:00, inspect the cluster and notify me only on failure",
      "Every Monday at 10:00, summarize last week's incidents",
      "Every weekday at 18:00, recap today's alerts"
    ]
  }
}
```

| 字段 | 说明 |
|---|---|
| `id` | 专家标识。安装时必须和请求的标识相同。缺省时目录扫描会用文件夹名，市场安装不会接受空的 `id` |
| `label` | 名称 |
| `description` | 简介 |
| `welcome_message` | 对话页欢迎语 |
| `icon_name` | 内置图标名，例如 `terminal` |
| `icon_url` | `http(s)` 图片地址。创建 Agent 时由 Octop 进程下载；失败则不用这张图，创建继续 |
| `color` | 卡片颜色，例如 `#16a34a` |
| `prompt_files` | 根目录人格 Markdown 文件名列表 |
| `quick_prompts` | 欢迎页快捷提示，见下文 |
| `task_examples` | 任务页空状态示例，见下文 |

`label`、`description`、`welcome_message` 可以是字符串，也可以是 `{"zh": "…", "en": "…"}`。写字符串的话，中英文都用这一份。对象里缺当前语言时，就用另一种语言的文本顶上。

## 快捷提示

`quick_prompts` 是对象数组。每一项：

| 字段 | 说明 |
|---|---|
| `title` | 卡片标题。字符串或 `{zh, en}` |
| `description` | 卡片说明 |
| `prompt` | 点进去填进输入框的正文 |
| `color` | 缺省 `#e8f4ff` |
| `icon_name` | 可选 |

不是对象的元素直接丢掉。标题和正文都空的卡片不会留在工作区清单里。

建 Agent 时如果请求里另外带了 `quick_prompts`，会写进工作区 `.octop/manifest.json`，覆盖压缩包里的同名字段。

## 任务示例

`task_examples` 有两种写法：

```json
{ "zh": ["示例一", "示例二", "示例三"], "en": ["One", "Two", "Three"] }
```

```json
["同一份给中文和英文"]
```

展示时保留 3 条或 6 条：不超过 3 条原样展示，4 或 5 条截成 3 条，更多则截成 6 条。字段没填时，界面会按专家名称生成一套默认示例。写成空数组就不显示建议卡。

## 目录条目和压缩包

市场列表上的名称、介绍、场景、图标，以及详情里的工作流正文和快捷提示，都来自目录条目，不是这只压缩包。工作流正文是目录条目的 `content`，一段 Markdown；详情页只拿它展示，不写进工作区。

真正写进工作区的是压缩包：人格和技能是包里的 Markdown，欢迎语和快捷提示来自包里的 `manifest.json`。创建请求若另外带了快捷提示，以请求里的为准。

目录条目和压缩包写成同一份内容就行。卡片上的介绍对应 `description`，工作流正文对应包里给 Agent 看的 Markdown，快捷提示对应 `quick_prompts`。

## 打包

在专家目录的上一级打包：

```bash
zip -r ops-engineer-1.0.0.zip ops-engineer
```

根上不要再并列第二个目录。从专家目录内部打包也可以，那时 `manifest.json` 在 ZIP 根上。
