---
name: research-paper-monitor
description: 科研文献智能监测与摘要推送系统。自动监测多个学术信源（arXiv、PubMed、CNKI等），根据用户关注的领域和关键词采集最新论文，生成中文摘要并推送。适用于需要跟踪学术前沿的科研工作者、研究生、教师等。使用场景包括：(1) 定时监测特定研究领域的最新论文，(2) 根据关键词筛选高相关度论文，(3) 自动生成论文中文摘要，(4) 接收每日/每周文献推送（需配置飞书渠道）。
license: MIT
clawhub:
  slug: research-paper-monitor
  repo: wiltonMotta/skills
  repoPath: skills/research-paper-monitor
  ref: main
  version: main
  autoEnable: true
  url: https://clawhub.ai/wiltonMotta/research-paper-monitor
---

# 科研文献智能监测与摘要推送系统

## 概述

本技能帮助科研工作者自动跟踪学术前沿，从多个权威信源采集最新论文，生成中文摘要，并支持本地归档和推送通知。

### 核心功能

- **多源监测**: arXiv、PubMed、Google Scholar、CNKI（知网）等
- **智能筛选**: 基于用户自定义关键词匹配
- **中文摘要**: 自动生成论文核心要点（问题/方法/结论）
- **本地归档**: 结构化存储，支持检索
- **主动推送**: 通过飞书或其他渠道推送高相关论文

---

## 快速开始

使用 **arXiv 公开 API**（免费、无需注册、无需 API Key）：

```bash
# 1. 初始化配置
python ~/.openclaw/workspace/skills/research-paper-monitor/scripts/config.py

# 2. 运行监测
python ~/.openclaw/workspace/skills/research-paper-monitor/scripts/monitor.py
```

---

## 详细配置

### 完整流程

```
用户配置关键词 → 定时触发采集 → 多源检索论文 → 去重过滤
      ↓
关键词匹配评分 → 生成中文摘要 → 本地归档 → 推送高相关论文
```

### 关键步骤说明

**Step 1: 采集 (Collection)**
- 使用 `web_search` 检索各信源的最新论文
- 支持按发布日期筛选（默认过去24小时）
- 每信源最多采集20篇

**Step 2: 去重 (Deduplication)**
- 对比本地 `literature-index.json` 索引
- 跳过已记录的论文（通过DOI或标题匹配）

**Step 3: 评分 (Scoring)**
- 基于用户关键词计算相关度分数
- 关键词匹配方式：标题(权重3) + 摘要(权重1)
- 分级：高相关(≥80分) / 中等(50-79分) / 低相关(<50分)

**Step 4: 摘要 (Summarization)**
- 对高相关和中等相关论文生成中文摘要
- 摘要结构：研究问题、方法、主要结论、创新点

**Step 5: 归档 (Archiving)**
- 写入 `research-papers/YYYY-MM/YYYYMMDD-{title}.md`
- 更新 `literature-index.json` 索引
- 按研究领域自动分类

**Step 6: 推送 (Notification)**
- 高相关论文推送到飞书（如果配置了webhook）
- 本地生成日报 `daily-reports/YYYY-MM-DD.md`

---

## 支持的学术信源

| 信源 | 学科领域 | 更新频率 | 备注 |
|------|----------|----------|------|
| **arXiv** | 物理、数学、计算机、生物等 | 实时 | 预印本，开源免费 |
| **PubMed** | 生物医学、生命科学 | 每日 | 权威医学数据库 |
| **Google Scholar** | 全学科 | 每日 | 覆盖范围广 |
| **CNKI（知网）** | 中文学术 | 每日 | 中文核心期刊 |
| **IEEE Xplore** | 工程技术 | 每日 | 电子工程、计算机 |
| **Semantic Scholar** | 全学科 | 实时 | AI增强搜索 |

---

## 配置文件

配置文件位置：`~/.openclaw/research-monitor/config.json`

### 配置示例

```json
{
  "user_profile": {
    "name": "张三",
    "institution": "某大学",
    "research_field": "人工智能"
  },
  "keywords": [
    "large language model",
    "reasoning",
    "AI safety",
    "multimodal"
  ],
  "sources": [
    "arxiv",
    "pubmed",
    "google_scholar"
  ],
  "filters": {
    "max_papers_per_source": 20,
    "min_score_threshold": 50,
    "date_range_days": 1
  },
  "notification": {
    "enabled": true,
    "feishu_webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/xxx",
    "min_score_for_notification": 80
  },
  "storage": {
    "papers_dir": "~/.openclaw/research-papers",
    "index_file": "~/.openclaw/research-monitor/literature-index.json"
  }
}
```

---

## 脚本说明

### scripts/config.py
初始化用户配置，交互式设置研究领域、关键词、信源等。

### scripts/monitor.py
核心监测脚本，执行完整的采集-筛选-摘要-归档流程。

### scripts/search_papers.py
搜索指定信源的论文，支持关键词和时间范围。

用法：
```bash
python scripts/search_papers.py --source arxiv --keywords "transformer" --days 7
```

### scripts/generate_digest.py
生成指定时间段内的文献综述摘要。

用法：
```bash
python scripts/generate_digest.py --days 7 --output weekly-digest.md
```

---

## 数据结构

### 文献索引 (literature-index.json)

```json
{
  "papers": [
    {
      "id": "arxiv-2403.12345",
      "title": "论文标题",
      "authors": ["作者1", "作者2"],
      "source": "arxiv",
      "url": "https://arxiv.org/abs/2403.12345",
      "doi": "10.1234/example",
      "published_date": "2024-03-12",
      "collected_date": "2024-03-12",
      "score": 85,
      "keywords_matched": ["transformer", "attention"],
      "local_file": "research-papers/2024-03/20240312-paper-title.md"
    }
  ]
}
```

### 论文存储格式 (YYYY-MM/YYYYMMDD-title.md)

```markdown
# 论文标题

**作者**: 作者1, 作者2  
**来源**: arXiv  
**链接**: https://arxiv.org/abs/2403.12345  
**发布日期**: 2024-03-12  
**采集日期**: 2024-03-12  
**相关度评分**: 85/100

## 摘要

### 研究问题
...

### 方法
...

### 主要结论
...

### 创新点
...

## 原文摘要

（英文原文摘要）

## 关键词匹配

- transformer (标题匹配)
- attention (摘要匹配)
```

---

## 故障排除

| 问题 | 解决方案 |
|------|----------|
| 未找到相关论文 | 检查关键词是否太窄，尝试同义词 |
| 重复推送 | 检查 `literature-index.json` 是否被正确更新 |
| 摘要质量差 | 尝试提供更详细的领域背景 |
| 飞书推送失败 | 检查 webhook URL 是否有效 |
| 采集速度慢 | 减少信源数量或降低每信源论文数 |

---

## 参考资料

- 详细配置说明：[references/configuration.md](references/configuration.md)
- 信源API说明：[references/data-sources.md](references/data-sources.md)
- 高级用法示例：[references/advanced-usage.md](references/advanced-usage.md)
