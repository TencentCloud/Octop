---
name: llm-wiki
description: "Karpathy's LLM Wiki: 构建/查询互联 markdown 知识库。"
version: 2.1.0
author: Octop
license: MIT
compatibility: linux, macos, windows
metadata:
  octop:
    label:
      zh: "LLM Wiki"
      en: "LLM Wiki"
    summary:
      zh: "构建并查询互相链接的 Markdown 知识库。"
      en: "Build and query an interlinked Markdown knowledge base."
  harness:
    emoji: "📖"
    tags: [wiki, knowledge-base, research, notes, markdown, rag-alternative]
    category: research
    related_skills: [obsidian, arxiv]
---

# Karpathy's LLM Wiki

## Harness-agent tools#

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

构建和维护一个持久的、复合的知识库，以互联的 markdown 文件形式。
基于 [Andrej Karpathy's LLM Wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)。

与传统 RAG（每次查询都重新发现知识）不同，wiki
一次性编译知识并保持最新。交叉引用已经存在。
矛盾已经标记。综合反映了所有摄取的内容。

**劳动分工：** 人类策划来源并指导分析。代理
总结、交叉引用、文件和维护一致性。

## 何时此技能激活#

当用户：

- 要求创建、构建或启动 wiki 或知识库
- 要求摄取、添加或处理来源到他们的 wiki
- 询问问题且配置的路径处存在现有 wiki
- 要求 lint、审计或健康检查他们的 wiki
- 在研究中引用他们的 wiki、知识库或"笔记"

## Wiki 位置#

**位置：** 通过 `WIKI_PATH` 环境变量设置（例如，在 `{workspace}/.env` 中）。

如果未设置，默认为 `~/wiki`。

```bash
WIKI="${WIKI_PATH:-$HOME/wiki}"
```

wiki 只是一个 markdown 文件目录——在 Obsidian、VS Code 或
任何编辑器中打开它。无需数据库，无需特殊工具。

## 架构：三层#

```
wiki/
├── SCHEMA.md           # 约定、结构规则、领域配置
├── index.md            # 带一行摘要的分段内容目录
├── log.md              # 按时间顺序的操作日志（仅追加，每年轮换）
├── raw/                # 第 1 层：不可变来源材料
│   ├── articles/       # Web 文章、剪报
│   ├── papers/         # PDF、arxiv 论文
│   ├── transcripts/    # 会议笔记、访谈
│   └── assets/         # 来源引用的图像、图表
├── entities/           # 第 2 层：实体页面（人物、组织、产品、模型）
├── concepts/           # 第 2 层：概念/主题页面
├── comparisons/        # 第 2 层：并排分析
└── queries/            # 第 2 层：值得保留的已归档查询结果
```

**第 1 层 — 原始来源：** 不可变。代理读取但从不修改这些。

**第 2 层 — Wiki：** 代理拥有的 markdown 文件。由代理创建、更新和
交叉引用。

**第 3 层 — 模式：** `SCHEMA.md` 定义结构、约定和标签分类法。

## 恢复现有 Wiki（关键——每会话都执行此操作）#

当用户有现有 wiki 时，**在执行任何操作之前始终先让自己定向**：

① **读取 `SCHEMA.md`** — 理解领域、约定和标签分类法。
② **读取 `index.md`** — 了解存在哪些页面及其摘要。
③ **扫描最近的 `log.md`** — 读取最后 20-30 个条目以理解最近活动。

```bash
WIKI="${WIKI_PATH:-$HOME/wiki}"

# 会话开始时的定向读取
read_file "$WIKI/SCHEMA.md"
read_file "$WIKI/index.md"
read_file "$WIKI/log.md" offset=<最后 30 行>
```

只有定向后，你才应该摄取、查询或 lint。这可以防止：

- 为已存在的实体创建重复页面
- 缺少与现有内容的交叉引用
- 与模式的约定矛盾
- 重复已在日志中记录的工作

对于大型 wikis（100+ 页面），在创建任何新内容之前，还要对当前主题运行快速 `glob`。

## 初始化新 Wiki#

当用户要求创建或启动 wiki 时：

1. 确定 wiki 路径（来自 `$WIKI_PATH` 环境变量，或询问用户；默认为 `~/wiki`）
2. 创建上方的目录结构
3. 询问用户 wiki 涵盖什么领域——要具体
4. 编写针对该领域定制的 `SCHEMA.md`（见下方模板）
5. 编写带分段标题的初始 `index.md`
6. 编写带创建条目的初始 `log.md`
7. 确认 wiki 已就绪并建议第一个要摄取的来源

### SCHEMA.md 模板#

针对用户的领域调整。模式约束代理行为并确保一致性：

```markdown
# Wiki Schema

## Domain
[此 wiki 涵盖的内容——例如，"AI/ML research", "personal health", "startup intelligence"]

## Conventions
- 文件名：小写、连字符、无空格（例如，`transformer-architecture.md`）
- 每个 wiki 页面以 YAML frontmatter 开头（见下方）
- 使用 `[[wikilinks]]` 在页面之间链接（每页至少 2 个出站链接）
- 更新页面时，始终更新 `updated` 日期
- 每个新页面必须添加到正确分段下的 `index.md`
- 每个操作必须追加到 `log.md`
- **来源标记：** 在综合 3+ 来源的页面上，在声明来自特定来源的段落末尾附加 `^[raw/articles/source-file.md]`
  这让读者可以在不重新读取整个原始文件的情况下追溯每个声明。在单来源页面上可选，其中
  `sources:` frontmatter 已足够。

## Frontmatter
  ```yaml
  ---
  title: Page Title
  created: YYYY-MM-DD
  updated: YYYY-MM-DD
  type: entity | concept | comparison | query | summary
  tags: [from taxonomy below]
  sources: [raw/articles/source-name.md]
  # Optional quality signals:
  confidence: high | medium | low        # 声明支持得有多好
  contested: true                        # 当页面有未解决矛盾时设置
  contradictions: [other-page-slug]      # 此页面与哪些页面冲突
  ---
  ```

`confidence` 和 `contested` 是可选的，但建议用于意见重度或快速移动的
主题。Lint 会显示 `contested: true` 和 `confidence: low` 页面以供审查，以便弱声明
不会静默强化为已接受的 wiki 事实。

### raw/ Frontmatter#

原始来源也获得一个小的 frontmatter 块，以便重新摄取可以检测漂移：

```yaml
---
source_url: https://example.com/article   # 原始 URL（如果适用）
ingested: YYYY-MM-DD
sha256: <hex digest of the raw content below the frontmatter>
---
```

`sha256:` 让未来的相同 URL 重新摄取跳过处理（当内容未更改时），
并在内容已更改时标记漂移。仅在正文（frontmatter 之后的所有内容）上计算，而不是 frontmatter 本身。

## Tag Taxonomy
[为领域定义 10-20 个顶级标签。在首先使用它们之前在此处添加新标签。]

示例用于 AI/ML：
- Models: model, architecture, benchmark, training
- People/Orgs: person, company, lab, open-source
- Techniques: optimization, fine-tuning, inference, alignment, data
- Meta: comparison, timeline, controversy, prediction

规则：页面上的每个标签必须出现在此分类法中。如果需要新标签，
首先在此处添加它，然后使用它。这可以防止标签扩散。

## Page Thresholds#
- **创建页面** 当实体/概念出现在 2+ 来源中或对一个来源至关重要时
- **添加到现有页面** 当来源提到已涵盖的内容时
- **不要创建页面** 用于路过提及、次要细节或领域之外的事物
- **拆分页面** 当它超过 ~200 行时——用交叉链接拆分为子主题
- **归档页面** 当其内容完全被取代时——移动到 `_archive/`，从索引中移除

## Entity Pages#
每篇 notable 实体一页。包括：
- 概述 / 它是什么
- 关键事实和日期
- 与其他实体的关系（[[wikilinks]]）
- 来源引用

## Concept Pages#
每个概念或主题一页。包括：
- 定义 / 解释
- 知识的当前状态
- 开放问题或辩论
- 相关概念（[[wikilinks]]）

## Comparison Pages#
并排分析。包括：
- 正在比较什么以及为什么
- 比较维度（首选表格格式）
-  verdict 或综合
- 来源

## Update Policy#
当新信息与现有内容冲突时：
1. 检查日期——较新的来源通常取代较旧的
2. 如果确实矛盾，用日期和来源记录两个位置
3. 在 frontmatter 中标记矛盾：`contradictions: [page-name]`
4. 在 lint 报告中标记供用户审查

### index.md 模板#

索引按类型分段。每个条目一行：wikilink + 摘要。

```markdown
# Wiki Index

> Content catalog. Every wiki page listed under its type with a one-line summary.
> Read this first to find relevant pages for any query.
> Last updated: YYYY-MM-DD | Total pages: N

## Entities
<!-- Alphabetical within section -->

## Concepts#

## Comparisons#

## Queries#
```

**缩放规则：** 当任何分段超过 50 个条目时，按首字母或子域拆分为子分段。当索引总数超过 200 个条目时，创建一个 `_meta/topic-map.md`，按主题分组页面以便更快导航。

### log.md 模板#

```markdown
# Wiki Log

> Chronological record of all wiki actions. Append-only.
> Format: `## [YYYY-MM-DD] action | subject`
> Actions: ingest, update, query, lint, create, archive, delete

> When this file exceeds 500 entries, rotate: rename to log-YYYY.md, start fresh.

## [YYYY-MM-DD] create | Wiki initialized
- Domain: [domain]
- Structure created with SCHEMA.md, index.md, log.md
```

## 核心操作#

### 1. 摄取#

当用户提供来源（URL、文件、粘贴）时，将其集成到 wiki 中：

① **捕获原始来源：**
   - URL → 使用 `web_fetch` 获取 markdown，保存到 `raw/articles/`
   - PDF → 使用 `web_fetch`（处理 PDF），保存到 `raw/papers/`
   - 粘贴的文本 → 保存到适当的 `raw/` 子目录
   - 描述性地命名文件：`raw/articles/karpathy-llm-wiki-2026.md`
   - **添加原始 frontmatter**（`source_url`、`ingested`、`sha256` 正文）。
     在重新摄取相同 URL 时：重新计算 sha256，与存储的值比较——
     如果相同则跳过，如果不同则标记漂移并更新。这足够便宜，可以在每次重新摄取时执行并捕获静默来源更改。

② **与用户讨论要点** — 什么有趣，什么对此领域重要。
   （在自动化/cron 上下文中跳过此操作——直接进行。）

③ **检查已存在的内容** — 搜索 index.md 并使用 `glob` 查找
   已提及实体/概念的现有页面。这是不断增长的 wiki 和一堆重复项之间的区别。

④ **编写或更新 wiki 页面：**
   - **新实体/概念：** 仅当它们满足 SCHEMA.md 中的页面阈值时才创建页面
     （2+ 来源提及，或对一个来源至关重要）
   - **现有页面：** 添加新信息，更新事实，更新 `updated` 日期。
     当新信息与现有内容矛盾时，遵循更新策略。
   - **交叉引用：** 每个新页面或更新的页面必须通过 `[[wikilinks]]` 链接到至少 2 个其他
     页面。检查现有页面是否链接回来。
   - **标签：** 仅使用 SCHEMA.md 分类法中的标签
   - **来源：** 在综合 3+ 来源的页面上，附加 `^[raw/articles/source.md]`
     标记到声明来自特定来源的段落。这允许读者追溯每个
     声明回到其来源，而无需重新读取整个原始文件。可选在单来源页面上，其中 `sources:` frontmatter 已足够。
   - **置信度：** 对于意见重度、快速移动或单来源声明，在 frontmatter 中设置
     `confidence: medium` 或 `low`。除非
     声明在多个来源中得到充分支持，否则不要标记 `high`。

⑤ **更新导航：**
   - 将新页面添加到 `index.md` 下的正确分段，按字母顺序
   - 更新索引标题中的"Total pages"计数和"Last updated"日期
   - 追加到 `log.md`：`## [YYYY-MM-DD] ingest | Source Title`
   - 在日志条目中列出每个创建或更新的文件

⑥ **报告更改的内容** — 向用户列出创建或更新的每个文件。

单个来源可以触发跨 5-15 个 wiki 页面的更新。这很正常
并且是期望的——它是复合效应。

### 2. 查询#

当用户询问有关 wiki 领域的问题时：

① **读取 `index.md`** 以识别相关页面。
② **对于 100+ 页面的 wikis**，还要跨所有 `.md` 文件
   `glob` 以查找关键术语——仅索引可能会错过相关内容。
③ **使用 `read_file` 读取相关页面。**
④ **从编译的知识中综合答案。** 引用你从中抽取的 wiki 页面：
   "Based on [[page-a]] and [[page-b]]..."
⑤ **将有价值的答案反馈回来** — 如果答案是实质性的比较、
   深度潜水或新颖的综合，请在 `queries/` 或 `comparisons/` 中创建一个页面。
   不要归档平凡的查找——仅归档重新派生会痛苦的回答。
⑥ **使用查询和是否已归档更新 `log.md`。**

### 3. Lint#

当用户要求 lint、健康检查或审计 wiki 时：

① **孤立页面：** 查找没有其他页面 `[[wikilinks]]` 的页面。
   ```python
   # 使用 execute_code 执行此操作 — 跨所有 wiki 页面进行程序化扫描
   import os, re
   from collections import defaultdict

   wiki = "<WIKI_PATH>"
   # 扫描 entities/、concepts/、comparisons/、queries/ 中的所有 .md 文件
   # 提取所有 [[wikilinks]] — 构建入站链接映射
   # 零入站链接的页面是孤立的
   ```

② **断开的 wikilinks：** 查找指向不存在的页面的 `[[links]]`。

③ **索引完整性：** 每个 wiki 页面都应出现在 `index.md` 中。比较
   文件系统与索引条目。

④ **Frontmatter 验证：** 每个 wiki 页面必须具有所有必需字段
   （title、created、updated、type、tags、sources）。标签必须出现在分类法中。

⑤ **过期内容：** 其 `updated` 日期比提及相同实体的最新
   来源旧 >90 天的页面。

⑥ **矛盾：** 关于同一主题但声称不同的页面。查找
   共享标签/实体但陈述不同事实的页面。显示所有带有
   `contested: true` 或 `contradictions:` frontmatter 的页面以供用户审查。

⑦ **质量信号：** 列出带有 `confidence: low` 的页面以及任何仅引用
   单个来源但没有设置置信度字段的页面——这些是候选
   用于查找 corroboration 或降级为 `confidence: medium`。

⑧ **来源漂移：** 对于 `raw/` 中每个带有 `sha256:` frontmatter 的文件，重新计算
   哈希并标记不匹配。不匹配表示原始文件被编辑过
   （不应发生——raw/ 是不可变的）或从已更改的 URL 重新摄取。不是硬错误，但值得报告。

⑨ **页面大小：** 标记超过 200 行的页面——用于拆分的候选。

⑩ **标签审计：** 列出使用中的所有标签，标记任何不在 SCHEMA.md 分类法中的标签。

⑪ **日志轮换：** 如果 log.md 超过 500 个条目，轮换它。

⑫ **报告发现** 并按严重性分组（断开的链接 > 孤立 > 来源漂移 > 矛盾页面 > 过期内容 > 样式问题）。

⑬ **追加到 log.md：** `## [YYYY-MM-DD] lint | N issues found`。

## 使用 Wiki 工作#

### 搜索#

```text
# 按内容查找页面
grep(pattern="transformer", path="$WIKI")

# 按文件名查找页面
glob(pattern="**/*.md", path="$WIKI")

# 按标签查找页面
grep(pattern="tags:.*alignment", path="$WIKI")
```

```bash
# 最近活动
read_file "$WIKI/log.md" offset=<最后 20 行>
```

### 批量摄取#

一次摄取多个来源时，批量更新：

1. 首先读取所有来源
2. 跨所有来源识别所有实体和概念
3. 检查它们所有（一次搜索，而不是 N 次）的现有页面
4. 在一次传递中创建/更新页面（避免冗余更新）
5. 最后更新 index.md
6. 写入覆盖批次的单个日志条目

### 归档#

当内容完全被取代或领域范围更改时：

1. 如果不存在，创建 `_archive/` 目录
2. 将页面移动到 `_archive/` 及其原始路径（例如，`_archive/entities/old-page.md`）
3. 从 `index.md` 中移除
4. 更新链接到它的页面——用纯文本 + "(archived)" 替换 wikilink
5. 记录归档操作
6. 日志归档操作

### Obsidian 集成#

wiki 目录开箱即用作 Obsidian 保管库：
- `[[wikilinks]]` 渲染为可点击的链接
- 图形视图可视化知识网络
- YAML frontmatter 支持 Dataview 查询
- `raw/assets/` 文件夹保存通过 `![[image.png]]` 引用的图像

为了获得最佳结果：
- 将 Obsidian 的附件文件夹设置为 `raw/assets/`
- 在 Obsidian 设置中启用"Wikilinks"（默认通常开启）
- 安装 Dataview 插件以进行查询，如 `TABLE tags FROM "entities" WHERE contains(tags, "company")`

如果将 Obsidian 技能与此技能一起使用，请将 `OBSIDIAN_VAULT_PATH` 设置为
与 wiki 路径相同的目录。

### Obsidian Headless（服务器和无头机器）#

在没有显示器的机器上，使用 `obsidian-headless` 而不是桌面应用程序。
它通过 Obsidian Sync 同步保管库而无需 GUI——非常适合
在服务器上运行并写入 wiki 而 Obsidian 桌面在另一台设备上读取它的代理。

**设置：**

```bash
# 需要 Node.js 22+
npm install -g obsidian-headless

# 登录（需要带有 Sync 订阅的 Obsidian 帐户）
ob login --email <email> --password '<password>'

# 为 wiki 创建远程保管库
ob sync-create-remote --name "LLM Wiki"

# 将 wiki 目录连接到保管库
cd ~/wiki
ob sync-setup --vault "<vault-id>"

# 初始同步
ob sync

# 持续同步（前台——对后台使用 systemd）
ob sync --continuous
```

**通过 systemd 持续后台同步：**

```ini
# ~/.config/systemd/user/obsidian-wiki-sync.service
[Unit]
Description=Obsidian LLM Wiki Sync
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/path/to/ob sync --continuous
WorkingDirectory=/home/user/wiki
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now obsidian-wiki-sync
# 启用 linger 以便同步在注销后继续：
sudo loginctl enable-linger $USER
```

这让代理可以在服务器上写入 `~/wiki`，而你在笔记本电脑/手机上的 Obsidian 中浏览相同的
保管库——更改在几秒钟内出现。

## 陷阱#

- **永远不要修改 `raw/` 中的文件** — 来源是不可变的。更正转到 wiki 页面。
- **始终首先定向** — 在新会话中执行任何操作之前，读取 SCHEMA + 索引 + 最近日志。
  跳过此操作会导致重复和错过交叉引用。
- **始终更新 index.md 和 log.md** — 跳过此操作会使 wiki 降级。它们是
  导航骨干。
- **不要为路过提及创建页面** — 遵循 SCHEMA.md 中的页面阈值。仅在
  脚注中出现一次的名称不保证实体页面。
- **不要创建没有交叉引用的页面** — 孤立页面是不可见的。每个页面必须
  链接到至少 2 个其他页面。
- **Frontmatter 是必需的** — 它启用搜索、过滤和过期检测。
- **标签必须来自分类法** — 自由格式标签衰减为噪音。首先向 SCHEMA.md
  添加新标签，然后使用它们。
- **保持页面可扫描** — wiki 页面应可在 30 秒内阅读。将页面拆分为
  超过 200 行的页面。将详细分析移至专用的深度潜水页面。
- **在大规模更新之前询问** — 如果摄取会触及 10+ 现有页面，请首先与用户确认
  范围。
- **轮换日志** — 当 log.md 超过 500 个条目时，将其重命名为 `log-YYYY.md` 并从头开始。
  代理应在 lint 期间检查日志大小。
- **显式处理矛盾** — 不要静默覆盖。用日期记录两个声明，
  在 frontmatter 中标记，并标记供用户审查。

## 相关工具#

[llm-wiki-compiler](https://github.com/atomicmemory/llm-wiki-compiler) 是一个 Node.js CLI，
它使用相同的 Karpathy 灵感将来源编译为概念 wiki。它是 Obsidian 兼容的，
因此想要预定/CLI 驱动的编译管道的用户可以将其指向此技能维护的相同保管库。
权衡：它拥有页面生成（替换此技能的页面
创建上的判断）并为早期
设置和大量来源批量摄取进行调整。使用此技能当你想要代理在循环中策划时；
使用 llmwiki 当你想要批量编译来源目录时。
