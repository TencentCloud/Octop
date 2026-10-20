---
name: watchers
description: "轮询 RSS、JSON API 和 GitHub，带水位线去重。"
version: 1.0.0
author: Octop
license: MIT
compatibility: linux, macos
metadata:
  octop:
    label:
      zh: "订阅监控"
      en: "Watchers"
    summary:
      zh: "轮询 RSS、JSON API 与 GitHub，并按水位线去重。"
      en: "Poll RSS, JSON APIs, and GitHub with watermark dedup."
  harness:
    emoji: "🔔"
    tags: [cron, polling, rss, github, http, automation, monitoring]
    category: devops
    related_skills: []
---

# Watchers

## Harness-agent tools

本技能从 Octop 移植。使用以下 harness/deepagents 工具：

| 概念 | 工具 |
|---------|------|
| Shell | `execute` |
| 读/写/编辑文件 | `read_file`, `write_file`, `edit_file` |
| 查找文件/搜索内容 | `glob`, `grep` |
| 获取 URL | `web_fetch` |
| 浏览器自动化 | `browser_use` |
| 子代理工作 | `task` |
| 记忆 | `memory_store`, `memory_recall`, `memory_search` |

内置技能文件位于 `/_builtin_skills/<name>/`。用户安装的技能位于 `/skills/<name>/`。

按间隔轮询外部源，仅对新项目做出反应。三个现成脚本加一个共享水位线助手；通过 cron 作业（或直接从终端）将它们接入。

## 何时使用

- 用户想要监视 RSS/Atom 源并在新条目时收到通知
- 用户想要监视 GitHub 仓库的 issues / PR / releases / commits
- 用户想要轮询任意 JSON 端点并在新项目时收到通知
- 用户询问"X 的监视器"或"当 X 变化时通知我"

## 心智模型

监视器只是一个脚本，它：

1. 从外部源获取数据
2. 与先前已见 ID 的水位线文件进行比较
3. 将新水位线写回
4. 向 stdout 打印新项目（或无更改时为空）

下面的脚本处理所有三个。代理通过 execute 工具运行它们——从 cron 作业、webhook 或交互式聊天中——并报告新内容。

## 现成脚本

所有三个脚本在技能安装后都位于 `/_builtin_skills/watchers/scripts/`。

| 脚本 | 监视内容 | 去重键 |
|---|---|---|
| `watch_rss.py` | RSS 2.0 或 Atom 源 URL | `<guid>` / `<id>` |
| `watch_http_json.py` | 返回对象列表的任意 JSON 端点 | 可配置的 id 字段 |
| `watch_github.py` | GitHub issues / PR / releases / commits | `id` / `sha` |

所有三个脚本：

- 首次运行记录基线——从不重放现有源
- 水位线是 bounded ID 集合（最多 500 个）以限制内存
- 输出格式：`## <title>\n<url>\n\n<optional body>` 每个项目
- 无新项目时 stdout 为空——调用者将其视为静默
- 获取错误时非零退出

## 用法

通过 `execute` 运行监视器（路径相对于 `init_workspace` 后的工作区根目录）：

```bash
python _builtin_skills/watchers/scripts/watch_rss.py \
  --name hn --url https://news.ycombinator.com/rss --max 5
```

监视 GitHub 仓库（设置 `GITHUB_TOKEN` 环境变量以避免 60 次请求/小时的匿名速率限制）：

```bash
python _builtin_skills/watchers/scripts/watch_github.py \
  --name my-issues --repo owner/repo --scope issues
```

轮询任意 JSON API：

```bash
python _builtin_skills/watchers/scripts/watch_http_json.py \
  --name api --url https://api.example.com/events \
  --id-field event_id --items-path data.events
```

## 周期性运行

octop-harness 没有内置 cron。选项：

1. **临时性**——用户询问时运行监视器；如果 stdout 非空则总结
2. **OS cron / launchd**——在主机上调度相同的 `python _builtin_skills/watchers/scripts/...` 命令
3. **外部调度器**——将脚本接入你的部署的作业运行器

示例用户提示：

> 每当我询问时，运行 HN 监视器并总结新标题。如果 stdout 为空则保持静默。

## 状态文件

每个监视器将 `watcher-state/<name>.json` 写入磁盘。检查：

```bash
cat watcher-state/hn.json
```

强制重放（下次运行视为首次轮询）：

```bash
rm watcher-state/hn.json
```

## 编写你自己的

所有三个脚本使用相同的模板：加载水位线、获取、diff、保存、输出。`scripts/_watermark.py` 是共享助手；导入它以获取原子写入 + bounded ID 集合 + 首次运行基线。有关它需要多少样板，请参见三个参考脚本中的任何一个。

## 常见陷阱

1. **在每个 tick 打印"无新项目"头部。** 调用者依赖空 stdout = 静默。如果你在空 delta 时打印任何内容，你就会垃圾邮件频道。已发布的脚本会处理此问题；自定义脚本也必须如此。
2. **期望首次运行发出项目。** 它不会——首次运行记录基线。如果你需要初始摘要，请在首次运行后删除状态文件，或在你自己的脚本中添加 `--prime-with-latest N` 标志。
3. **unbounded 水位线增长。** 共享助手上限为 500 个 ID。对于高流失率源，请提高它；对于受限文件系统，请降低它。
4. **将状态目录放在代理无法写入的位置。** 默认 `watcher-state/` 在本地 backend 上是可写的。
