---
name: legal-kb
description: 法律知识库检索技能。当用户需要查询法律法规、合同条款、司法解释时激活。触发词：搜一下法律、查一下这个条款、总结这份合同、法律咨询、法律问题、查法条。适配如意工作台，即插即用。
---

# Legal KB - 法律知识库检索

## 当前数据源覆盖范围

| 分类 | 部数 | 代表法律 |
|------|------|---------|
| 民法典 | 8章节 | 物权、合同、侵权、婚姻、继承、人格权 |
| 行政法 | 5部 | 行政处罚、行政强制、行政许可、行政复议、行政诉讼 |
| 社会法 | 6部 | 劳动法、劳动合同法、安全生产法、未成年人保护法 |
| 经济法 | 6部 | 公司法、破产法、证券法、合伙企业法、税法 |
| 刑法 | 2部 | 刑法（2020）、刑法修正案（十一） |
| 程序法 | 4部 | 刑诉、民诉、仲裁法、公证法 |
| 宪法相关 | 2部 | 宪法、立法法 |
| **合计** | **33部+** | **持续更新中** |

> 数据来源：[just-laws](https://github.com/ImCa0/just-laws)，实时从 GitHub 获取原文。

## 工作流程

1. **读取 SKILL.md** → 确认脚本路径
2. **执行 `search_law.py`** → 在全部 33+ 部法律中全文搜索
3. **本地文件兜底** → 有配置目录时搜索 PDF/DOCX
4. **格式化输出** → 引用条款编号、内容、来源
5. **无结果** → 明确告知 + 建议 web_search 补充

## 核心脚本

### search_law.py（主力）

```bash
# 查询关键词
python scripts/search_law.py <关键词> [--max-per-law 5]

# 列出已收录法律目录
python scripts/search_law.py --list

# 示例
python scripts/search_law.py "宅基地"
python scripts/search_law.py "违约金 合同解除"
python scripts/search_law.py "劳动争议 经济补偿金"
```

**输出特点：**
- 跨 33 部法律全文搜索，按分类分组展示
- 每条结果含条款编号、上下文片段
- UTF-8 编码，纯文本输出，适合 AI 直接处理

### 本地脚本（兜底）

```bash
python scripts/list_files.py <目录>       # 列出本地文件
python scripts/search_kb.py <目录> <关键词>  # 本地全文搜索
python scripts/read_pdf.py <文件> [页码]    # 读 PDF
python scripts/read_docx.py <文件>         # 读 Word
```

## 格式化输出规范

1. **条款引用** — 标注具体条款编号（第XXX条）
2. **来源标注** — 注明"来源：just-laws 法律库"
3. **分类展示** — 结果按法律分类分组
4. **无结果提示** — 告知覆盖范围，建议 web_search 补充

## 扩展说明

如需添加更多法律，可扩展 `scripts/search_law.py` 中的 `LAW_DATABASE` 索引：
```python
{
    'category': '分类名',
    'laws': [
        {'name': '法律名', 'path': 'docs/类别/法律名/README.md'},
    ]
}
```
路径格式：`https://raw.githubusercontent.com/ImCa0/just-laws/master/docs/{path}`
