# 科研文献监测 - 详细配置说明

## 配置文件结构

配置文件位于 `~/.openclaw/research-monitor/config.json`，采用 JSON 格式。

## 配置项详解

### user_profile（用户档案）

```json
{
  "user_profile": {
    "name": "张三",
    "institution": "清华大学",
    "research_field": "人工智能"
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| name | string | 用户姓名，用于报告和通知 |
| institution | string | 所属机构，可选 |
| research_field | string | 主要研究领域，用于分类 |

### keywords（关注关键词）

```json
{
  "keywords": [
    "large language model",
    "transformer",
    "reasoning",
    "multimodal learning"
  ]
}
```

- 最多支持 10 个关键词
- 支持中英文关键词
- 建议使用领域内常用术语
- 关键词用于匹配论文标题和摘要

**关键词设置建议：**
- 使用具体术语而非宽泛词汇（如用 "BERT" 而非 "NLP"）
- 包含同义词或变体（如 "deep learning" 和 "neural network"）
- 定期根据研究进展更新关键词

### sources（监测信源）

```json
{
  "sources": [
    "arxiv",
    "pubmed",
    "google_scholar"
  ]
}
```

支持的信源：

| 信源 | 代码 | 学科领域 | 特点 |
|------|------|----------|------|
| arXiv | arxiv | 物理、数学、计算机、生物 | 预印本，更新快，免费 |
| PubMed | pubmed | 生物医学、生命科学 | 权威，含影响因子 |
| Google Scholar | google_scholar | 全学科 | 覆盖广，含引用数 |
| 知网 | cnki | 中文学术 | 中文核心期刊 |
| IEEE Xplore | ieee | 工程技术 | 顶会论文 |
| Semantic Scholar | semantic_scholar | 全学科 | AI增强，含TLDR |

### filters（筛选设置）

```json
{
  "filters": {
    "max_papers_per_source": 20,
    "min_score_threshold": 50,
    "date_range_days": 1
  }
}
```

| 参数 | 说明 | 建议值 |
|------|------|--------|
| max_papers_per_source | 每信源最大采集数 | 10-50 |
| min_score_threshold | 最低相关度阈值 | 30-70 |
| date_range_days | 时间范围（天） | 1-7 |

### notification（推送通知）

```json
{
  "notification": {
    "enabled": true,
    "feishu_webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/3d623017-0f4c-4ea6-b7ce-ba7b619cb7aa",
    "min_score_for_notification": 80
  }
}
```

**飞书机器人设置步骤：**

1. 在飞书群中添加自定义机器人
2. 复制 Webhook URL
3. 粘贴到配置文件中

### storage（存储设置）

```json
{
  "storage": {
    "papers_dir": "~/.openclaw/research-papers",
    "index_file": "~/.openclaw/research-monitor/literature-index.json"
  }
}
```

## 高级配置示例

### 生物医学研究者配置

```json
{
  "user_profile": {
    "name": "李明",
    "institution": "协和医院",
    "research_field": "肿瘤免疫治疗"
  },
  "keywords": [
    "immunotherapy",
    "CAR-T",
    "checkpoint inhibitor",
    "tumor microenvironment",
    "PD-1",
    "cancer vaccine"
  ],
  "sources": ["pubmed", "google_scholar"],
  "filters": {
    "max_papers_per_source": 15,
    "min_score_threshold": 60,
    "date_range_days": 1
  },
  "notification": {
    "enabled": true,
    "feishu_webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/3d623017-0f4c-4ea6-b7ce-ba7b619cb7aa",
    "min_score_for_notification": 75
  }
}
```

### 计算机科学研究者配置

```json
{
  "user_profile": {
    "name": "王芳",
    "institution": "中科院计算所",
    "research_field": "机器学习系统"
  },
  "keywords": [
    "distributed training",
    "model compression",
    "inference optimization",
    "edge computing",
    "federated learning"
  ],
  "sources": ["arxiv", "google_scholar", "ieee"],
  "filters": {
    "max_papers_per_source": 25,
    "min_score_threshold": 50,
    "date_range_days": 1
  }
}
```

## 配置热重载

修改配置文件后，下次运行 monitor.py 时自动生效，无需重启。

## 故障排除

### 配置文件格式错误

使用 JSON 验证工具检查配置文件格式：
```bash
python3 -c "import json; json.load(open('$HOME/.openclaw/research-monitor/config.json'))"
```

### 恢复默认配置

删除配置文件后重新运行 config.py：
```bash
rm ~/.openclaw/research-monitor/config.json
python3 config.py
```
