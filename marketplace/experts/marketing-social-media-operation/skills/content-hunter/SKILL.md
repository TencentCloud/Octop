---
name: content-hunter
description: 内容捕手 (Content Hunter) - 短视频平台热门内容抓取机器人。支持小红书、抖音、B站，可分批抓取热门内容并自动生成汇报。/Content Hunter - Hot content crawler for Xiaohongshu, Douyin, Bilibili. Supports batch scraping and scheduled reporting.
version: 1.1.0
changelog: |
  - 1.1.0: 支持定时多次抓取模式，每次创建独立任务文件夹，支持10次批量抓取
  - 1.0.0: 初始版本，支持单次抓取和晚8点汇报
---

# 内容捕手 / Content Hunter

## 概述 / Overview
持续刷小红书、抖音，B站3个平台，每次每平台抓取40条热门内容并保存，晚上8点生成汇报。/Scrapes 3 platforms (Xiaohongshu, Douyin, Bilibili), 40 items each, generates daily report at 8 PM.

---

## 一、浏览器标签管理 / Browser Tab Management

| 平台 / Platform | 网站URL / URL | 提取要素 / Data Fields | 备注 / Notes |
|------|---------|----------|------|
| 小红书 / Xiaohongshu | https://www.xiaohongshu.com | 标题、作者、点赞、收藏、评论、话题、内容总结 / Title, Author, Likes, Saves, Comments, Tags, Summary | 需要登录 / Login required |
| 抖音 / Douyin | https://www.douyin.com | 标题、作者、点赞、话题、内容总结 / Title, Author, Likes, Tags, Summary | |
| B站 / Bilibili | https://www.bilibili.com | 标题、UP主、播放、弹幕、点赞、投币、收藏、字幕、内容总结 / Title, UP, Views, Danmaku, Likes, Coins, Favs, Subtitles, Summary | 尝试提取字幕 / Try extract subtitles |

**每次每个平台抓取40条热门内容 / Scrape 40 hot items per platform each time**

---

## 二、存储位置 / Storage Location

工作空间 / Workspace：`~/.openclaw/workspace/content-hunter/`

**重要：每次任务新建独立子文件夹，不覆盖历史数据！** / **Important: Create new subfolder for each task, NEVER overwrite historical data!**

```
content-hunter/
├── task-2026-03-11-0900/     # 任务1：按时间命名
│   ├── xiaohongshu.md
│   ├── douyin.md
│   ├── bilibili.md
│   └── summary.md              # 本次任务汇报
├── task-2026-03-11-0930/     # 任务2
│   ├── xiaohongshu.md
│   ├── douyin.md
│   ├── bilibili.md
│   └── summary.md
└── task-2026-03-11-2000/     # 晚8点汇报任务
    └── summary.md
```

**文件夹命名规则**：`task-YYYY-MM-DD-HHMM`

每次任务执行前：
1. 创建新文件夹：`task-$(date +%Y-%m-%d-%H%M)`
2. 在新文件夹中抓取和保存数据

---

## 三、记录格式 / Data Format

**重要：每条记录必须包含以下所有字段，缺一不可！** / **Important: Every record MUST have ALL these fields!**

### 小红书 / Xiaohongshu
```markdown
### 第X条 / Item #X
- 标题 / Title: xxx
- 作者 / Author: xxx
- 点赞 / Likes: xxx
- 收藏 / Saves: xxx
- 评论 / Comments: xxx
- 话题 / Tags: #xxx #xxx
- 内容总结 / Summary: 详细描述... (3-5句话 / 3-5 sentences)
```

### 抖音 / Douyin
```markdown
### 第X条 / Item #X
- 标题 / Title: xxx
- 作者 / Author: @xxx
- 点赞 / Likes: xxx
- 话题 / Tags: #xxx
- 内容总结 / Summary: 详细描述... (3-5句话 / 3-5 sentences)
```

### B站 / Bilibili
```markdown
### 第X条 / Item #X
- 标题 / Title: xxx
- UP主 / UP: xxx
- 播放 / Views: xxx
- 弹幕 / Danmaku: xxx
- 点赞 / Likes: xxx
- 投币 / Coins: xxx
- 收藏 / Favs: xxx
- 字幕 / Subtitles: 有/无 / Yes/No
- 内容总结 / Summary: 详细描述... (3-5句话 / 3-5 sentences)
```

---

## 四、执行流程 / Execution Flow

### 4.1 抓取要求 / Scraping Requirement
**每次每个平台抓取40条热门内容 / Scrape 40 hot items per platform each time**

### 4.2 初始化 / Initialization
1. **创建新任务文件夹** / Create new task folder：`mkdir -p ~/.openclaw/workspace/content-hunter/task-$(date +%Y-%m-%d-%H%M)/`
2. 用 browser.open 打开3个平台 / Open 3 platforms via browser.open

### 4.3 循环执行 / Loop Execution
1. browser.snapshot() 获取页面内容 / Get page content
2. **必须提取所有字段！每条必须包含：标题、作者、热度、内容总结** / **Must extract ALL fields: title, author, views/likes, content summary**
3. **保存到当前任务文件夹** / Save to current task folder：`~/.openclaw/workspace/content-hunter/task-YYYY-MM-DD-HHMM/`
4. 等待3-5分钟 / Wait 3-5 minutes
5. **⚠️ 抓取过程中不发送任何进度消息到群聊，只保存数据** / **⚠️ Do NOT send any progress messages to group chats during scraping, only save data**
6. **汇报任务执行完毕后，停止抓取，等待下次定时任务** / **After report is sent, stop scraping and wait for next scheduled task**

### 4.4 汇报数据范围 / Report Data Scope
**重要：汇报时需要汇总当日所有抓取任务的数据，而非仅最近一次！** / **Important: Report must summarize ALL data from all tasks on that day, not just the latest one!**

汇报生成流程：
1. 读取当日所有task文件夹 / Read all task folders for the day
2. 合并各平台的抓取数据 / Merge data from all platforms
3. 去重后生成汇报 / Deduplicate and generate report
4. 汇总数据量 = 所有任务的累加总和 / Total = sum of all tasks

### 4.5 B站字幕提取 / Bilibili Subtitle Extraction
使用 bilibili-youtube-watcher 技能的 get_transcript.py 脚本提取字幕

---

## 五、晚上汇报 / Daily Report

### 汇报流程 / Report Flow
1. **读取数据**：从最新的task文件夹读取各平台md文件 / Read from latest task folder
2. 生成汇报 / Generate report
3. 发送汇报到群里 / Send report to group
4. **汇报后自动清理**：执行 `openclaw cron list` 找到所有内容捕手相关 cron（名称含"内容捕手"或"hunter"），逐一删除
5. **汇报后停止，等待下次任务** / After cleanup, stop and wait for next task

### 汇报内容 / Report Contents
1. 发原始数据文件链接 / Send raw data links
2. 热门内容TOP20（必须包含内容总结！）/ TOP 20 (MUST include content summary!)
   - 格式：按平台分类，每条包含：标题 | 热度 | 内容总结（1-2句话）
   - 例如：小红书暖心正能量：标题 → 热度 | 内容总结
   - Format: By platform, each item: Title | Views/Likes | Summary
3. 各平台趋势 + 整体趋势 / Platform trends + Overall trends
4. 推荐深度阅读 / Recommended deep reads
5. 呱呱感悟 / Guagua's thoughts
6. 关闭浏览器 / Close browser tabs

---

## 六、可用平台 / Supported Platforms

| 平台 / Platform | 状态 / Status |
|------|------|
| 小红书 / Xiaohongshu | ✅ |
| 抖音 / Douyin | ✅ |
| B站 / Bilibili | ✅ |


---

## 七、使用方式 / Usage

### 7.1 触发方式 / How to Trigger

#### 方式一：手动对话 / Method 1: Manual Chat
- "帮我刷短视频平台" / "Scrape short video platforms"
- "抓取热门内容" / "Get trending content"
- "生成内容汇报" / "Generate content report"
- "启用内容捕手" / "Enable content hunter"

#### 方式二：定时任务 / Method 2: Cron Job (Recommended)
定时任务需要手动创建，参考以下配置：
- 抓取任务：每30分钟执行一次（9:00-20:00），静默执行不发群消息
- 汇报任务：晚上20:00执行，发送到小红书群

**⚠️ 绝对原则：内容捕手的所有任务和汇报，只允许发送到小红书呱呱群（oc_d21f6b6f9bd843444622c8e221134f47），禁止发送到任何其他群！**

### 7.2 可配置参数 / Configurable Parameters

| 参数 / Parameter | 说明 / Description | 默认值 / Default | 设置方式 / How to Set |
|------|------|--------|----------|
| 平台 / Platforms | 要抓取的平台 / Platforms to scrape | 全部3个 / All 3 | "只刷抖音" / "Only Douyin" |
| 数量 / Count | 每平台抓取条数 / Items per platform | 40条 / 40 | "每个刷30条" / "30 items each" |
| 汇报时间 / Report Time | 生成汇报的时间 / When to generate report | 20:00 / 8 PM | "晚上6点汇报" / "Report at 6 PM" |
| 存储路径 | 数据保存目录 | ~/workspace/content-hunter/task-YYYY-MM-DD-HHMM/ | 一般不改 |

### 7.3 实际存储示例 / Storage Example

**任务执行后，文件夹里有什么？**

例如：用户说"帮我刷短视频平台"
```
~/.openclaw/workspace/content-hunter/
└── task-2026-03-11-2100/           # 任务文件夹（按时间命名）
    ├── xiaohongshu.md              # 小红书数据（40条，每条含标题、作者、点赞、内容总结）
    ├── douyin.md                    # 抖音数据
    ├── bilibili.md                 # B站数据
    └── summary.md                  # 汇报文件
```

**每个md文件内容示例：**
```markdown
# 小红书热门内容

### 第1条
- 标题: 最近大家都在安装openclaw
- 作者: 美丽的一天
- 点赞: 1000
- 内容总结: 介绍OpenClaw的安装和使用方法...

### 第2条
- 标题: ...
...
（共40条 / 40 items total）
```

### 7.4 汇报内容示例 / Report Example

**晚上8点汇报长这样：**

```
📊 2026年3月11日 内容捕手汇报

🔥 热门内容TOP20
【小红书】
1. 标题 → 热度 | 内容总结
2. ...

【B站】
1. 标题 → 热度 | 内容总结
...

📈 各平台趋势总结
- 小红书：xxx
- 抖音：xxx
...

🎯 整体趋势
1. xxx
2. xxx

📖 推荐深度阅读
- xxx

🐸 呱呱感悟
xxx
```

### 7.5 对话示例 / Chat Examples

```
用户A：帮我刷短视频平台
→ AI：好的，启动内容捕手，默认抓取3个平台，每平台20条
/User A: Scrape video platforms
→ AI: OK, starting Content Hunter, 3 platforms, 20 items each

用户B：我只刷抖音和B站，每个刷30条
→ AI：好的，只抓取抖音和B站，每平台30条
/User B: Only Douyin and Bilibili, 30 each
→ AI: OK, Douyin + Bilibili, 30 items each

用户C：每天早上9点开始抓取，晚上6点汇报
→ AI：好的，设置抓取时间为9:00-20:00，汇报时间为18:00
/User C: Start at 9 AM, report at 6 PM
→ AI: OK, scraping 9 AM - 8 PM, report at 6 PM

用户D：现在帮我抓一次
→ AI：好的，马上抓取
/User D: Scrape now
→ AI: OK, scraping now

用户E：今天的热门内容有哪些？
→ AI：读取已有数据，生成汇报
/User E: What's trending today?
→ AI: Reading existing data, generating report
```

### 7.4 注意事项 / Notes
- 定时任务可能因Gateway重启而丢失，需定期检查 / Cron may be lost on Gateway restart
- 抓取过程中请勿关闭浏览器 / Don't close browser during scraping
- 建议保持浏览器标签页稳定 / Keep browser tabs stable

---

## 八、依赖 / Dependencies

### 8.1 依赖的Skill / Required Skills
| Skill | 用途 / Purpose |
|-------|------|
| bilibili-youtube-watcher | 提取B站视频字幕 / Extract Bilibili subtitles |

### 8.2 依赖的工具 / Required Tools
| 工具 / Tool | 用途 / Purpose |
|------|------|
| browser | 浏览器自动化抓取 / Browser automation |
| yt-dlp | 视频字幕提取 / Video subtitle extraction |

### 8.3 前置要求 / Prerequisites
- OpenClaw浏览器控制服务正常运行 / OpenClaw browser service running
- bilibili-youtube-watcher技能已安装 / bilibili-youtube-watcher skill installed
