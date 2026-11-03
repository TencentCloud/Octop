---
name: academic-citation-manager
description: Add real references and standardize citations for research papers and theses (为科研论文和毕业论文添加真实参考文献并规范引用标注)
homepage: https://github.com/YouStudyeveryday/academic-citation-manager
user-invocable: true
version: 1.0.0
tags:
  - academic-writing
  - citation-management
  - bibliography
  - research-tools
  - multi-format
  - crossref-integration
author: YouStudyeveryday
license: MIT
---

# Academic Citation Manager | 学术引用管理器

## 功能说明 | Function Description

【中文】
学术引用管理器是一个专业的科研论文引用管理工具，旨在为科研论文和毕业论文添加真实参考文献并规范引用标注。该工具支持多种国际通用的引用格式，包括APA、MLA、Chicago、GB/T 7714、IEEE、Harvard等，并与Crossref API集成以获取真实的文献元数据。

核心功能包括：
- 多格式引用支持：支持APA 7th、MLA 9th、Chicago 17th、GB/T 7714-2015、IEEE、Harvard等多种引用格式
- 智能元数据获取：通过DOI、ISBN、标题等信息从Crossref等权威数据库自动获取文献元数据
- 文内引用管理：自动生成和插入文中引用标注，支持作者-年份制和序号制
- 参考文献列表生成：自动生成格式规范的参考文献列表，支持多种排序方式
- 批量文献导入：支持批量导入和管理参考文献，提高工作效率
- 格式转换：在不同引用格式间进行快速转换，满足不同期刊要求
- 引用完整性检查：自动检查文中引用与参考文献列表的一致性
- 中英文双语支持：完整支持中文和英文文献的处理和格式化

【English】
Academic Citation Manager is a professional research paper citation management tool designed to add real references and standardize citations for research papers and theses. The tool supports multiple internationally used citation formats, including APA, MLA, Chicago, GB/T 7714, IEEE, Harvard, etc., and integrates with Crossref API to retrieve authentic bibliographic metadata.

Core features include:
- Multi-format citation support: Supports APA 7th, MLA 9th, Chicago 17th, GB/T 7714-2015, IEEE, Harvard and other citation formats
- Intelligent metadata retrieval: Automatically retrieves bibliographic metadata from authoritative databases like Crossref via DOI, ISBN, title, etc.
- In-text citation management: Automatically generates and inserts in-text citations, supporting author-year and numeric systems
- Bibliography list generation: Automatically generates format-compliant bibliography lists with various sorting options
- Batch reference import: Supports batch importing and managing references to improve efficiency
- Format conversion: Fast conversion between different citation formats to meet various journal requirements
- Citation integrity checking: Automatically checks consistency between in-text citations and bibliography lists
- Bilingual support: Complete support for processing and formatting Chinese and English references

## 支持的引用格式 | Supported Citation Formats

【中文】

本工具支持以下主要引用格式：

### APA 7th Edition
- 适用领域：心理学、教育学、社会科学
- 文内引用：(Smith, 2023) 或 Smith (2023)
- 特点：作者-年份制，强调出版年，DOI强制推荐

### MLA 9th Edition
- 适用领域：人文学、语言文学
- 文内引用：(Smith 23) 或 Smith (23)
- 特点：作者-页码制，对"容器"层次要求明确

### Chicago 17th Edition
- 适用领域：历史、艺术、人文学
- 注脚-参考文献制：Superscript¹ 或 Author, Title, p. xx
- 作者-日期制：(Smith 2023, 45)
- 特点：支持两种体系，历史文献注释丰富

### GB/T 7714-2015
- 适用领域：中文学位论文、期刊
- 文内引用：[1] 或 (张, 2023)
- 特点：支持序号与作者-日期双制，强制文献类型标识

### IEEE
- 适用领域：电气、电子、计算机
- 文内引用：[1]
- 特点：方括号数字制，强调出版年、卷期页码

### Harvard
- 适用领域：英联邦高校通用
- 文内引用：(Smith, 1999, p. 23)
- 特点：作者-年份制，页码必加

【English】

This tool supports the following major citation formats:

### APA 7th Edition
- Fields: Psychology, Education, Social Sciences
- In-text citation: (Smith, 2023) or Smith (2023)
- Features: Author-year system, emphasizes publication year, DOI recommended

### MLA 9th Edition
- Fields: Humanities, Language & Literature
- In-text citation: (Smith 23) or Smith (23)
- Features: Author-page system, clear container hierarchy requirements

### Chicago 17th Edition
- Fields: History, Arts, Humanities
- Notes-bibliography: Superscript¹ or Author, Title, p. xx
- Author-date: (Smith 2023, 45)
- Features: Supports two systems, rich historical document annotations

### GB/T 7714-2015
- Fields: Chinese academic papers, journals
- In-text citation: [1] or (Zhang, 2023)
- Features: Supports both numeric and author-date systems, mandatory document type identifiers

### IEEE
- Fields: Electrical, Electronics, Computer Science
- In-text citation: [1]
- Features: Bracketed numeric system, emphasizes publication year, volume, issue, page numbers

### Harvard
- Fields: Commonwealth universities
- In-text citation: (Smith, 1999, p. 23)
- Features: Author-year system, page numbers mandatory

## 使用方法 | Usage

【中文】

### Python API 使用

```python
from academic_citation_skill import AcademicCitationManager

# 创建管理器实例
manager = AcademicCitationManager()

# 方法1：通过DOI获取文献信息
doi = "10.1000/xyz123"
reference = manager.fetch_reference_by_doi(doi)
print(f"标题: {reference['title']}")
print(f"作者: {reference['authors']}")

# 方法2：通过ISBN获取图书信息
isbn = "9780262033848"
reference = manager.fetch_reference_by_isbn(isbn)

# 方法3：通过标题和作者搜索
results = manager.search_references(
    title="Artificial Intelligence",
    author="Russell",
    year=2020
)

# 添加到本地文献库
manager.add_to_library(reference)

# 生成文中引用
citation = manager.generate_citation(
    reference_id=reference['id'],
    style='apa',
    citation_type='author-date'
)
print(f"文中引用: {citation}")

# 生成参考文献列表
bibliography = manager.generate_bibliography(
    style='apa',
    sort_by='alphabetical'
)

# 检查引用完整性
issues = manager.check_citation_integrity(document_text="your document content")
for issue in issues:
    print(f"问题: {issue}")

# 格式转换
converted = manager.convert_citation_style(
    references=[reference],
    from_style='apa',
    to_style='ieee'
)
```

### 命令行使用

```bash
# 通过DOI获取文献信息
python academic_citation_skill.py --fetch-doi 10.1000/xyz123

# 通过ISBN获取图书信息
python academic_citation_skill.py --fetch-isbn 9780262033848

# 批量导入参考文献
python batch_import.py --input references.bib --format bibtex

# 格式转换
python format_converter.py --input apa_refs.txt --from-style apa --to-style ieee

# 检查引用完整性
python citation_checker.py --document paper.docx --bibliography refs.txt

# 生成参考文献列表
python academic_citation_skill.py --generate-bib --style apa --input citations.txt
```

### 集成到写作工作流

```python
# 在LaTeX中使用
from academic_citation_skill import AcademicCitationManager

manager = AcademicCitationManager()

# 生成BibTeX格式
bibtex = manager.export_bibtex()
with open('references.bib', 'w') as f:
    f.write(bibtex)

# 在Word中使用
from academic_citation_skill import WordCitationPlugin

plugin = WordCitationPlugin()
plugin.insert_citation(reference_id="ref1", style="apa")
plugin.generate_bibliography(style="apa")

# 在Markdown中使用
from academic_citation_skill import MarkdownCitationFormatter

formatter = MarkdownCitationFormatter()
formatted_text = formatter.format_markdown(
    text="Your document with @[ref1] citations",
    style="apa"
)
```

【English】

### Python API Usage

```python
from academic_citation_skill import AcademicCitationManager

# Create manager instance
manager = AcademicCitationManager()

# Method 1: Fetch reference by DOI
doi = "10.1000/xyz123"
reference = manager.fetch_reference_by_doi(doi)
print(f"Title: {reference['title']}")
print(f"Authors: {reference['authors']}")

# Method 2: Fetch book information by ISBN
isbn = "9780262033848"
reference = manager.fetch_reference_by_isbn(isbn)

# Method 3: Search by title and author
results = manager.search_references(
    title="Artificial Intelligence",
    author="Russell",
    year=2020
)

# Add to local library
manager.add_to_library(reference)

# Generate in-text citation
citation = manager.generate_citation(
    reference_id=reference['id'],
    style='apa',
    citation_type='author-date'
)
print(f"In-text citation: {citation}")

# Generate bibliography list
bibliography = manager.generate_bibliography(
    style='apa',
    sort_by='alphabetical'
)

# Check citation integrity
issues = manager.check_citation_integrity(document_text="your document content")
for issue in issues:
    print(f"Issue: {issue}")

# Convert citation style
converted = manager.convert_citation_style(
    references=[reference],
    from_style='apa',
    to_style='ieee'
)
```

### Command Line Usage

```bash
# Fetch reference by DOI
python academic_citation_skill.py --fetch-doi 10.1000/xyz123

# Fetch book information by ISBN
python academic_citation_skill.py --fetch-isbn 9780262033848

# Batch import references
python batch_import.py --input references.bib --format bibtex

# Format conversion
python format_converter.py --input apa_refs.txt --from-style apa --to-style ieee

# Check citation integrity
python citation_checker.py --document paper.docx --bibliography refs.txt

# Generate bibliography
python academic_citation_skill.py --generate-bib --style apa --input citations.txt
```

### Integration into Writing Workflow

```python
# Using with LaTeX
from academic_citation_skill import AcademicCitationManager

manager = AcademicCitationManager()

# Generate BibTeX format
bibtex = manager.export_bibtex()
with open('references.bib', 'w') as f:
    f.write(bibtex)

# Using with Word
from academic_citation_skill import WordCitationPlugin

plugin = WordCitationPlugin()
plugin.insert_citation(reference_id="ref1", style="apa")
plugin.generate_bibliography(style="apa")

# Using with Markdown
from academic_citation_skill import MarkdownCitationFormatter

formatter = MarkdownCitationFormatter()
formatted_text = formatter.format_markdown(
    text="Your document with @[ref1] citations",
    style="apa"
)
```

## 配置选项 | Configuration Options

【中文】

### 引用格式配置 (citation_styles.json)

主要配置项：

```json
{
  "apa": {
    "name": "APA 7th Edition",
    "in_text": {
      "format": "parenthetical",
      "separator": ", ",
      "year_position": "after_author",
      "page_number_format": "p. {page}"
    },
    "bibliography": {
      "sort_by": "alphabetical",
      "author_format": "last_first",
      "title_format": "sentence_case",
      "doi_required": true,
      "url_format": "available_at"
    },
    "document_type_codes": {
      "book": "",
      "journal": "",
      "conference": "",
      "thesis": "",
      "report": ""
    }
  },
  "gbt7714": {
    "name": "GB/T 7714-2015",
    "in_text": {
      "format": "numeric_bracket",
      "separator": ", ",
      "prefix": "[",
      "suffix": "]"
    },
    "bibliography": {
      "sort_by": "citation_order",
      "author_format": "chinese_name_order",
      "document_type_codes": {
        "book": "[M]",
        "journal": "[J]",
        "conference": "[C]",
        "thesis": "[D]",
        "report": "[R]",
        "newspaper": "[N]"
      }
    },
    "chinese_authors": {
      "name_order": "last_first",
      "separator": ", "
    }
  }
}
```

### Crossref API配置 (crossref_config.json)

```json
{
  "api_base": "https://api.crossref.org",
  "endpoints": {
    "works": "/works",
    "journals": "/journals",
    "types": "/types",
    "fields": "/fields"
  },
  "rate_limiting": {
    "requests_per_second": 10,
    "backoff_strategy": "exponential",
    "max_retries": 3
  },
  "filters": {
    "default": {
      "has_full_text": true,
      "state": "active"
    },
    "journals": {
      "type": "journal-article"
    },
    "books": {
      "type": "monograph"
    }
  },
  "cache": {
    "enabled": true,
    "ttl_seconds": 86400,
    "max_size": 1000
  }
}
```

### 本地文献库配置 (reference_database.json)

```json
{
  "metadata": {
    "version": "1.0.0",
    "created_date": "2026-03-01",
    "last_updated": "2026-03-01"
  },
  "references": {
    "ref_001": {
      "id": "ref_001",
      "type": "journal_article",
      "title": "Deep Learning",
      "authors": [
        {
          "given": "Yann",
          "family": "LeCun",
          "sequence": "first"
        },
        {
          "given": "Yoshua",
          "family": "Bengio",
          "sequence": "additional"
        }
      ],
      "container_title": "Nature",
      "volume": "521",
      "issue": "7553",
      "page": "436-444",
      "published_date": "2015-05-27",
      "year": 2015,
      "doi": "10.1038/nature14539",
      "issn": ["0028-0836", "1476-4687"],
      "language": "en",
      "tags": ["machine learning", "neural networks"]
    }
  },
  "citation_mappings": {
    "ref_001": [
      {"document_id": "doc1", "positions": [45, 89, 234]},
      {"document_id": "doc2", "positions": [12, 156]}
    ]
  }
}
```

【English】

### Citation Style Configuration (citation_styles.json)

Main configuration items:

```json
{
  "apa": {
    "name": "APA 7th Edition",
    "in_text": {
      "format": "parenthetical",
      "separator": ", ",
      "year_position": "after_author",
      "page_number_format": "p. {page}"
    },
    "bibliography": {
      "sort_by": "alphabetical",
      "author_format": "last_first",
      "title_format": "sentence_case",
      "doi_required": true,
      "url_format": "available_at"
    },
    "document_type_codes": {
      "book": "",
      "journal": "",
      "conference": "",
      "thesis": "",
      "report": ""
    }
  },
  "gbt7714": {
    "name": "GB/T 7714-2015",
    "in_text": {
      "format": "numeric_bracket",
      "separator": ", ",
      "prefix": "[",
      "suffix": "]"
    },
    "bibliography": {
      "sort_by": "citation_order",
      "author_format": "chinese_name_order",
      "document_type_codes": {
        "book": "[M]",
        "journal": "[J]",
        "conference": "[C]",
        "thesis": "[D]",
        "report": "[R]",
        "newspaper": "[N]"
      }
    },
    "chinese_authors": {
      "name_order": "last_first",
      "separator": ", "
    }
  }
}
```

### Crossref API Configuration (crossref_config.json)

```json
{
  "api_base": "https://api.crossref.org",
  "endpoints": {
    "works": "/works",
    "journals": "/journals",
    "types": "/types",
    "fields": "/fields"
  },
  "rate_limiting": {
    "requests_per_second": 10,
    "backoff_strategy": "exponential",
    "max_retries": 3
  },
  "filters": {
    "default": {
      "has_full_text": true,
      "state": "active"
    },
    "journals": {
      "type": "journal-article"
    },
    "books": {
      "type": "monograph"
    }
  },
  "cache": {
    "enabled": true,
    "ttl_seconds": 86400,
    "max_size": 1000
  }
}
```

### Local Reference Database Configuration (reference_database.json)

```json
{
  "metadata": {
    "version": "1.0.0",
    "created_date": "2026-03-01",
    "last_updated": "2026-03-01"
  },
  "references": {
    "ref_001": {
      "id": "ref_001",
      "type": "journal_article",
      "title": "Deep Learning",
      "authors": [
        {
          "given": "Yann",
          "family": "LeCun",
          "sequence": "first"
        },
        {
          "given": "Yoshua",
          "family": "Bengio",
          "sequence": "additional"
        }
      ],
      "container_title": "Nature",
      "volume": "521",
      "issue": "7553",
      "page": "436-444",
      "published_date": "2015-05-27",
      "year": 2015,
      "doi": "10.1038/nature14539",
      "issn": ["0028-0836", "1476-4687"],
      "language": "en",
      "tags": ["machine learning", "neural networks"]
    }
  },
  "citation_mappings": {
    "ref_001": [
      {"document_id": "doc1", "positions": [45, 89, 234]},
      {"document_id": "doc2", "positions": [12, 156]}
    ]
  }
}
```

## 使用示例 | Usage Examples

【中文】

### 示例1：通过DOI获取文献并生成APA格式引用

```python
from academic_citation_skill import AcademicCitationManager

manager = AcademicCitationManager()

# 获取文献信息
ref = manager.fetch_reference_by_doi("10.1038/nature14539")

# 生成文中引用
in_text = manager.generate_citation(
    reference_id=ref['id'],
    style='apa',
    citation_type='author-date'
)
print(f"文中引用: {in_text}")
# 输出: (LeCun, Bengio, & Hinton, 2015)

# 生成参考文献条目
bib_entry = manager.format_bibliography_entry(ref, style='apa')
print(f"参考文献条目: {bib_entry}")
# 输出: LeCun, Y., Bengio, Y., & Hinton, G. (2015). Deep learning. Nature, 521(7553), 436–444. https://doi.org/10.1038/nature14539
```

### 示例2：批量导入和格式转换

```python
# 从BibTeX文件导入
from batch_import import BatchImporter

importer = BatchImporter()
references = importer.import_from_file('references.bib', format='bibtex')

# 添加到文献库
for ref in references:
    manager.add_to_library(ref)

# 转换为IEEE格式
from format_converter import FormatConverter

converter = FormatConverter()
ieee_refs = converter.convert_references(
    references=references,
    from_style='bibtex',
    to_style='ieee'
)

# 保存到文件
converter.save_to_file(ieee_refs, 'references_ieee.txt')
```

### 示例3：检查论文引用完整性

```python
from citation_checker import CitationChecker

checker = CitationChecker()

# 加载论文和参考文献
with open('paper.txt', 'r') as f:
    paper_text = f.read()

# 检查引用完整性
report = checker.check_paper(
    document_text=paper_text,
    bibliography_file='references.txt'
)

# 打印报告
print(f"总引用数: {report['total_citations']}")
print(f"参考文献数: {report['total_references']}")
print(f"不一致项: {report['inconsistencies']}")

if report['missing_in_bibliography']:
    print("\n文中引用但参考文献列表缺失:")
    for item in report['missing_in_bibliography']:
        print(f"  - {item}")

if report['unused_references']:
    print("\n参考文献列表中未使用的条目:")
    for item in report['unused_references']:
        print(f"  - {item}")
```

### 示例4：处理中文文献（GB/T 7714格式）

```python
# 添加中文文献
chinese_ref = {
    'type': 'journal_article',
    'title': '深度学习在自然语言处理中的应用',
    'authors': [
        {'family': '张', 'given': '三'},
        {'family': '李', 'given': '四'}
    ],
    'container_title': '计算机学报',
    'year': 2023,
    'volume': 46,
    'issue': 3,
    'page': '1-15',
    'language': 'zh'
}

manager.add_to_library(chinese_ref)

# 生成GB/T 7714格式引用
bib_entry = manager.format_bibliography_entry(
    chinese_ref,
    style='gbt7714'
)
print(f"GB/T 7714格式: {bib_entry}")
# 输出: 张三, 李四. 深度学习在自然语言处理中的应用[J]. 计算机学报, 2023, 46(3): 1-15.
```

【English】

### Example 1: Fetch Reference by DOI and Generate APA Format Citation

```python
from academic_citation_skill import AcademicCitationManager

manager = AcademicCitationManager()

# Fetch reference information
ref = manager.fetch_reference_by_doi("10.1038/nature14539")

# Generate in-text citation
in_text = manager.generate_citation(
    reference_id=ref['id'],
    style='apa',
    citation_type='author-date'
)
print(f"In-text citation: {in_text}")
# Output: (LeCun, Bengio, & Hinton, 2015)

# Generate bibliography entry
bib_entry = manager.format_bibliography_entry(ref, style='apa')
print(f"Bibliography entry: {bib_entry}")
# Output: LeCun, Y., Bengio, Y., & Hinton, G. (2015). Deep learning. Nature, 521(7553), 436–444. https://doi.org/10.1038/nature14539
```

### Example 2: Batch Import and Format Conversion

```python
# Import from BibTeX file
from batch_import import BatchImporter

importer = BatchImporter()
references = importer.import_from_file('references.bib', format='bibtex')

# Add to library
for ref in references:
    manager.add_to_library(ref)

# Convert to IEEE format
from format_converter import FormatConverter

converter = FormatConverter()
ieee_refs = converter.convert_references(
    references=references,
    from_style='bibtex',
    to_style='ieee'
)

# Save to file
converter.save_to_file(ieee_refs, 'references_ieee.txt')
```

### Example 3: Check Paper Citation Integrity

```python
from citation_checker import CitationChecker

checker = CitationChecker()

# Load paper and references
with open('paper.txt', 'r') as f:
    paper_text = f.read()

# Check citation integrity
report = checker.check_paper(
    document_text=paper_text,
    bibliography_file='references.txt'
)

# Print report
print(f"Total citations: {report['total_citations']}")
print(f"Total references: {report['total_references']}")
print(f"Inconsistencies: {report['inconsistencies']}")

if report['missing_in_bibliography']:
    print("\nCited in text but missing from bibliography:")
    for item in report['missing_in_bibliography']:
        print(f"  - {item}")

if report['unused_references']:
    print("\nUnused entries in bibliography:")
    for item in report['unused_references']:
        print(f"  - {item}")
```

### Example 4: Process Chinese Literature (GB/T 7714 Format)

```python
# Add Chinese reference
chinese_ref = {
    'type': 'journal_article',
    'title': '深度学习在自然语言处理中的应用',
    'authors': [
        {'family': '张', 'given': '三'},
        {'family': '李', 'given': '四'}
    ],
    'container_title': '计算机学报',
    'year': 2023,
    'volume': 46,
    'issue': 3,
    'page': '1-15',
    'language': 'zh'
}

manager.add_to_library(chinese_ref)

# Generate GB/T 7714 format citation
bib_entry = manager.format_bibliography_entry(
    chinese_ref,
    style='gbt7714'
)
print(f"GB/T 7714 format: {bib_entry}")
# Output: 张三, 李四. 深度学习在自然语言处理中的应用[J]. 计算机学报, 2023, 46(3): 1-15.
```

## 注意事项 | Notes

【中文】

### 使用建议

1. **DOI使用**
   - DOI（数字对象标识符）是获取准确文献信息的最佳方式
   - 建议优先使用DOI而不是仅用标题搜索
   - 如果DOI无法解析，可以尝试使用标题和作者信息搜索

2. **文献类型选择**
   - 正确选择文献类型（期刊、图书、会议论文、学位论文等）
   - 不同文献类型在引用格式上有重要差异
   - GB/T 7714要求使用文献类型标识符如[M][J][C][D]

3. **中文文献处理**
   - GB/T 7714-2015是中文文献的标准格式
   - 注意中文作者姓名的正确格式（姓前名后）
   - 期刊名称建议使用标准中文期刊名称

4. **引用完整性**
   - 使用引用检查功能确保所有文中引用都有对应的参考文献条目
   - 定期检查以避免遗漏或重复
   - 删除未使用的参考文献条目

5. **格式转换注意事项**
   - 不同引用格式的规则差异较大，转换后需人工检查
   - 特殊字段（如DOI、URL）在不同格式中的显示方式不同
   - 建议在最终定稿前再次核对期刊的具体格式要求

### 限制说明

1. **API限制**
   - Crossref API有速率限制（建议每秒不超过10次请求）
   - 大批量查询时建议使用本地缓存
   - 某些出版商的文献可能无法通过Crossref获取

2. **元数据准确性**
   - Crossref返回的元数据可能存在错误或不完整
   - 重要文献建议人工核实关键信息
   - 中文文献的元数据可能不如英文文献完整

3. **格式兼容性**
   - 某些期刊可能使用自定义格式
   - 特殊字符（如重音符号）可能需要特别处理
   - 非拉丁文字符（中文、阿拉伯文等）的显示可能因格式而异

4. **性能考虑**
   - 批量处理大量文献时，建议分批进行
   - 使用本地缓存可以显著提高处理速度
   - 网络延迟会影响在线查询的速度

### 常见问题

**Q: 如何获取文献的DOI？**
A: DOI通常可以在以下位置找到：
- 文献的首页或PDF文件的第一页
- 期刊网站的文献页面
- Crossref或出版社网站
- 如果找不到，可以尝试使用标题和作者信息搜索

**Q: 支持哪些文献导入格式？**
A: 当前支持：
- BibTeX (.bib)
- EndNote (.enw, .xml)
- RIS (.ris)
- CSV (.csv)
- JSON (.json)

**Q: 如何处理没有DOI的文献？**
A: 可以使用以下方法：
1. 使用ISBN（仅适用于图书）
2. 使用标题和作者信息搜索
3. 手动输入完整文献信息
4. 从PDF或其他来源提取元数据

**Q: 转换格式后需要人工检查吗？**
A: 是的，强烈建议：
1. 核对所有作者姓名
2. 检查标题的大小写格式
3. 验证卷号、期号、页码的格式
4. 确认DOI或URL的显示方式
5. 检查特殊字符和非拉丁文字符的显示

【English】

### Usage Recommendations

1. **DOI Usage**
   - DOI (Digital Object Identifier) is the best way to obtain accurate bibliographic information
   - It is recommended to prioritize using DOI rather than just searching by title
   - If DOI cannot be resolved, try searching using title and author information

2. **Document Type Selection**
   - Correctly select document type (journal article, book, conference paper, thesis, etc.)
   - Different document types have significant differences in citation formats
   - GB/T 7714 requires document type identifiers such as [M][J][C][D]

3. **Chinese Literature Processing**
   - GB/T 7714-2015 is the standard format for Chinese literature
   - Pay attention to the correct format of Chinese author names (surname before given name)
   - Use standard Chinese journal names for journal titles

4. **Citation Integrity**
   - Use citation checking function to ensure all in-text citations have corresponding bibliography entries
   - Check regularly to avoid omissions or duplicates
   - Remove unused bibliography entries

5. **Format Conversion Considerations**
   - Rules vary significantly between different citation formats, manual review after conversion is recommended
   - Special fields (such as DOI, URL) display differently in different formats
   - It is recommended to verify the journal's specific format requirements before final submission

### Limitations

1. **API Limitations**
   - Crossref API has rate limits (recommended not exceeding 10 requests per second)
   - Use local cache for large batch queries
   - Some publishers' works may not be available through Crossref

2. **Metadata Accuracy**
   - Metadata returned by Crossref may contain errors or be incomplete
   - It is recommended to manually verify key information for important references
   - Metadata for Chinese literature may not be as complete as for English literature

3. **Format Compatibility**
   - Some journals may use custom formats
   - Special characters (such as diacritics) may require special handling
   - Display of non-Latin characters (Chinese, Arabic, etc.) may vary by format

4. **Performance Considerations**
   - When processing large volumes of literature in batch, it is recommended to process in batches
   - Using local cache can significantly improve processing speed
   - Network latency affects the speed of online queries

### Frequently Asked Questions

**Q: How to get the DOI of a reference?**
A: DOIs can usually be found in the following locations:
- The first page of the article or PDF file
- The article page on the journal website
- Crossref or publisher websites
- If not found, try searching using title and author information

**Q: Which bibliography import formats are supported?**
A: Currently supported:
- BibTeX (.bib)
- EndNote (.enw, .xml)
- RIS (.ris)
- CSV (.csv)
- JSON (.json)

**Q: How to handle references without DOI?**
A: You can use the following methods:
1. Use ISBN (applicable only to books)
2. Search using title and author information
3. Manually enter complete reference information
4. Extract metadata from PDF or other sources

**Q: Is manual review needed after format conversion?**
A: Yes, strongly recommended:
1. Verify all author names
2. Check title case formatting
3. Validate volume, issue, and page number formats
4. Confirm DOI or URL display
5. Check display of special characters and non-Latin characters

## 更新日志 | Changelog

### Version 1.0.0 (2026-03-01)

【中文】
- 初始版本发布
- 支持6种主要引用格式（APA、MLA、Chicago、GB/T 7714、IEEE、Harvard）
- 集成Crossref API获取真实文献元数据
- 支持DOI、ISBN、标题搜索等多种获取方式
- 实现文中引用和参考文献列表生成
- 提供批量导入、格式转换、引用检查等辅助功能
- 完整支持中英文文献
- 提供Python API和命令行接口
- 包含完整的测试和文档

【English】
- Initial release
- Support for 6 major citation formats (APA, MLA, Chicago, GB/T 7714, IEEE, Harvard)
- Integration with Crossref API to retrieve authentic bibliographic metadata
- Support for multiple retrieval methods including DOI, ISBN, title search
- Implementation of in-text citations and bibliography list generation
- Provision of auxiliary functions such as batch import, format conversion, citation checking
- Complete support for Chinese and English references
- Provision of Python API and command line interface
- Complete testing and documentation included

## 许可证 | License

【中文】
本项目采用 MIT 许可证。详见 LICENSE 文件。

【English】
This project is licensed under MIT License. See LICENSE file for details.

## 联系方式 | Contact

【中文】
- 项目主页：https://github.com/YouStudyeveryday/academic-citation-manager
- 问题反馈：https://github.com/YouStudyeveryday/academic-citation-manager/issues
- 技术支持：youstudyeveryday@example.com

【English】
- Project homepage: https://github.com/YouStudyeveryday/academic-citation-manager
- Issue tracker: https://github.com/YouStudyeveryday/academic-citation-manager/issues
- Technical support: youstudyeveryday@example.com

## 致谢 | Acknowledgments

【中文】
感谢Crossref提供免费的DOI元数据查询服务，以及所有为学术引用管理工具做出贡献的开发者。特别感谢开源社区在citation-style-language等项目上的贡献。

【English】
Thanks to Crossref for providing free DOI metadata query services, and all developers who have contributed to academic citation management tools. Special thanks to the open source community for their contributions to projects like citation-style-language.