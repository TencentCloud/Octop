# OpenCLI 集成指南

OpenCLI 将任何网站变成命令行工具，**复用浏览器已有登录态**，无需额外配置 Cookie / API Key，AI Agent 可直接操控浏览器获取数据。

安装仓库：https://github.com/jackwener/opencli

---

## 安装步骤

```bash
# 1. 克隆仓库
git clone https://github.com/jackwener/opencli
cd opencli

# 2. 按照仓库内 README 完成安装
# （通常为 npm install 或 pip install，具体见仓库说明）

# 3. 验证安装
opencli list        # 查看所有可用命令
opencli --version   # 查看版本

# 4. 加载 opencli-operate skill（赋予 AI Agent 直接操控能力）
# 将 skills/opencli-operate/SKILL.md 指向 Cursor
```

**核心优势**：直接复用你在浏览器中已登录的账号（抖音/小红书/微博等），无需重新登录或配置。

---

## Step 1：行业分析 — 可用命令

### 热点与趋势

```bash
# 微博热搜（行业舆情）
opencli weibo hot
opencli weibo search "[行业关键词]"

# 知乎热榜（深度讨论）
opencli zhihu hot
opencli zhihu search "[行业关键词]"
opencli zhihu question [question_id]

# 36氪行业资讯
opencli 36kr hot
opencli 36kr news
opencli 36kr search "[行业关键词]"

# B站行业热门（视频类行业参考）
opencli bilibili hot
opencli bilibili ranking
opencli bilibili search "[行业关键词]"

# Google 搜索趋势
opencli google trends "[关键词]"
opencli google search "[行业关键词] 趋势 2025"
opencli google news "[行业关键词]"
```

### 平台内容爬取

```bash
# 小红书行业内容
opencli xiaohongshu search "[行业关键词]"
opencli xiaohongshu feed

# 抖音行业视频
opencli douyin videos --keyword "[行业关键词]"
opencli douyin hashtag "[话题标签]"
```

---

## Step 2：竞品分析 — 可用命令

### 竞品账号分析

```bash
# 小红书竞品账号
opencli xiaohongshu user "[账号名]"
opencli xiaohongshu creator-profile    # 获取创作者主页
opencli xiaohongshu creator-stats      # 获取创作者数据统计
opencli xiaohongshu creator-notes      # 获取笔记列表
opencli xiaohongshu creator-note-detail [note_id]  # 笔记详情
opencli xiaohongshu creator-notes-summary          # 笔记汇总分析

# 抖音竞品账号
opencli douyin profile                 # 查看账号主页
opencli douyin videos                  # 账号视频列表
opencli douyin stats                   # 账号数据统计
opencli douyin collections             # 合集内容

# 微博竞品搜索
opencli weibo search "[竞品名]"
```

### 电商竞品数据

```bash
# 京东商品详情（含评价）
opencli jd item "[商品名/ID]"

# 闲鱼二手（了解市场价格）
opencli xianyu search "[产品名]"
opencli xianyu item [item_id]

# 什么值得买（电商比价）
opencli smzdm search "[产品名]"
```

### 内容平台竞品

```bash
# 知乎竞品话题
opencli zhihu search "[竞品名]"
opencli zhihu question [id]

# B站竞品视频
opencli bilibili search "[竞品关键词]"
opencli bilibili user-videos [uid]
```

---

## Step 3：账号养号 — 可用命令

```bash
# 小红书：浏览行业内容（模拟真实行为）
opencli xiaohongshu feed               # 刷首页
opencli xiaohongshu search "[核心关键词]"  # 模拟搜索行为
opencli xiaohongshu notifications      # 查看通知/互动

# 抖音：浏览行业内容
opencli douyin videos --keyword "[核心关键词]"
opencli douyin hashtag "[行业标签]"
opencli douyin activities              # 查看平台活动

# 视频号（通过微信）
opencli weixin download [url]          # 下载/查看内容
```

---

## Step 4：爆款内容创作 — 可用命令

### 发现爆款选题

```bash
# 各平台热点（每日必看）
opencli weibo hot                      # 微博热搜
opencli zhihu hot                      # 知乎热榜
opencli bilibili hot                   # B站热门
opencli 36kr hot                       # 科技/商业热点
opencli douyin hashtag "[行业]"        # 抖音话题热度
opencli xiaohongshu search "[关键词]"  # 小红书热门笔记

# 行业深度内容
opencli zhihu search "[行业痛点关键词]"
opencli bilibili ranking               # B站排行榜
```

### 内容参考与下载

```bash
# 下载竞品爆款视频（用于分析，非商业用途）
opencli bilibili download [bvid]       # B站视频
opencli douyin videos                  # 抖音视频列表
opencli xiaohongshu download [note_id] # 小红书笔记

# 微信公众号文章
opencli weixin download [url]          # 微信文章内容
```

### 活动与热点检测

```bash
# 每日热点检测
opencli weibo hot                      # 微博实时热搜
opencli zhihu hot                      # 知乎今日热榜
opencli bilibili hot                   # B站热门视频
opencli 36kr news                      # 36氪最新资讯
opencli google trends "[行业]"         # 搜索趋势
```

### 发布内容

```bash
# 抖音发布
opencli douyin publish                 # 发布视频
opencli douyin drafts                  # 查看草稿
opencli douyin stats                   # 发布后统计数据

# 小红书发布
opencli xiaohongshu publish            # 发布笔记
```

---

## Step 5：互动钩子 — 可用命令

```bash
# 监控评论与互动
opencli xiaohongshu notifications      # 小红书通知（评论/点赞/关注）
opencli douyin stats                   # 抖音内容互动数据

# 发现高互动内容（用于学习钩子设计）
opencli xiaohongshu creator-notes-summary  # 自己笔记汇总分析
opencli douyin stats                   # 各视频互动对比

# 竞品评论区分析（收集用户声音）
opencli xiaohongshu creator-note-detail [note_id]  # 笔记评论详情
opencli zhihu question [id]            # 知乎问题下的回答和评论
```

---

## 数据获取方式对比

| 方式 | 优势 | 适用场景 |
|------|------|----------|
| **opencli**（推荐） | 复用浏览器登录态，零配置，实时数据 | 已在浏览器登录过账号的平台 |
| 内置 Python 脚本 | 批量处理，可定制数据格式 | 需要大量数据清洗和分析 |
| WebSearch/WebFetch | 无需登录，覆盖公开数据 | 没有登录态的平台/公开内容 |
| ima 知识库 | 调取历史积累数据 | 有历史数据沉淀时优先 |

**推荐策略**：
1. 先查 ima 知识库（历史数据）
2. 有登录态的平台用 opencli（实时，最准确）
3. 需要批量处理用内置脚本
4. 兜底用 WebSearch/WebFetch

---

## 常用操作组合示例

### 行业热点日报（每天运行）
```bash
opencli weibo hot
opencli zhihu hot
opencli bilibili hot
opencli 36kr hot
opencli douyin hashtag "[行业标签]"
```

### 竞品账号深度分析
```bash
# 小红书竞品
opencli xiaohongshu user "[竞品账号]"
opencli xiaohongshu creator-notes
opencli xiaohongshu creator-notes-summary

# 抖音竞品
opencli douyin profile
opencli douyin videos
opencli douyin stats
```

### 爆款内容监测
```bash
opencli xiaohongshu search "[行业关键词]"  # 最新热门笔记
opencli bilibili ranking                    # B站热门排行
opencli zhihu hot                           # 知乎热议话题
```
