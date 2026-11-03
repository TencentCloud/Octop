# Academic Citation Manager | 学术引用管理器

一个专业的科研论文引用管理工具，支持多种引用格式和Crossref API集成

[![Python Version](https://img.shields.io/badge/python-3.6%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![GitHub Issues](https://img.shields.io/badge/issues-open-red.svg)](https://github.com/YouStudyeveryday/academic-citation-manager/issues)

## 目录

- [功能特性](#功能特性)
- [支持的引用格式](#支持的引用格式)
- [安装指南](#安装指南)
- [快速开始](#快速开始)
- [使用方法](#使用方法)
- [配置说明](#配置说明)
- [API文档](#api文档)
- [常见问题](#常见问题)
- [贡献指南](#贡献指南)
- [许可证](#许可证)

## 功能特性

【中文】
- **多格式支持**：支持APA 7th、MLA 9th、Chicago 17th、GB/T 7714-2015、IEEE、Harvard等主流引用格式
- **智能元数据获取**：通过DOI、ISBN、标题等信息从Crossref等权威数据库自动获取文献元数据
- **文内引用管理**：自动生成和插入文中引用标注，支持作者-年份制和序号制
- **参考文献列表生成**：自动生成格式规范的参考文献列表，支持多种排序方式
- **批量文献导入**：支持从BibTeX、RIS、JSON、CSV等多种格式批量导入参考文献
- **格式转换**：在不同引用格式间进行快速转换，满足不同期刊要求
- **引用完整性检查**：自动检查文中引用与参考文献列表的一致性
- **中英文双语支持**：完整支持中文和英文文献的处理和格式化
- **本地文献库管理**：本地SQLite数据库存储和管理参考文献
- **命令行工具**：提供完整的命令行接口，方便批量处理和自动化脚本

【English】
- **Multi-format Support**: Supports major citation styles including APA 7th, MLA 9th, Chicago 17th, GB/T 7714-2015, IEEE, Harvard, and more
- **Intelligent Metadata Retrieval**: Automatically fetches bibliographic metadata from authoritative databases like Crossref via DOI, ISBN, title, etc.
- **In-text Citation Management**: Automatically generates and inserts in-text citations, supporting author-year and numeric systems
- **Bibliography List Generation**: Automatically generates format-compliant bibliography lists with various sorting options
- **Batch Reference Import**: Supports batch import from BibTeX, RIS, JSON, CSV and other formats
- **Format Conversion**: Fast conversion between different citation styles to meet various journal requirements
- **Citation Integrity Checking**: Automatically checks consistency between in-text citations and bibliography lists
- **Bilingual Support**: Complete support for processing and formatting Chinese and English references
- **Local Reference Database**: Local SQLite database for storing and managing references
- **Command Line Tools**: Complete command line interface for batch processing and automation scripts

## 支持的引用格式

| 格式 | 版本 | 文内引用风格 | 主要特点 | 适用领域 |
|------|--------|----------------|----------|----------|
| APA | 7th Edition | (Author, 2023) 或 Author (2023) | 作者-年份制，强调出版年，DOI强制推荐 | 心理学、教育学、社会科学 |
| MLA | 9th Edition | (Author 23) 或 Author (23) | 作者-页码制，对"容器"层次要求明确 | 人文学、语言文学 |
| Chicago (NB) | 17th Edition | Superscript¹ | 注脚-参考文献制，历史文献注释丰富 | 历史、艺术、人文学 |
| Chicago (A-D) | 17th Edition | (Author 2023, 45) | 注脚可选，作者-日期格式 | 社会科学、商科 |
| GB/T 7714 | 2015 | [1] 或 (张, 2023) | 支持序号与作者-日期双制，强制文献类型标识 | 中文学位论文、期刊 |
| IEEE | - | [1] | 方括号数字制，强调出版年、卷期页码 | 电气、电子、计算机 |
| Harvard | - | (Author, 1999, p. 23) | 作者-年份制，页码必加 | 英联邦高校通用 |

## 安装指南

### 环境要求

【中文】
- Python 3.6 或更高版本
- pip（Python包管理器）
- 互联网连接（用于Crossref API访问）

【English】
- Python 3.6 or higher
- pip (Python package manager)
- Internet connection (for Crossref API access)

### 从源码安装

【中文】
```bash
# 克隆仓库
git clone https://github.com/YouStudyeveryday/academic-citation-manager.git
cd academic-citation-manager

# 安装依赖
pip install -r requirements.txt

# 安装到系统（可选）
pip install -e .
```

【English】
```bash
# Clone repository
git clone https://github.com/YouStudyeveryday/academic-citation-manager.git
cd academic-citation-manager

# Install dependencies
pip install -r requirements.txt

# Install to system (optional)
pip install -e .
```

### 依赖包

【中文】
```txt
requests>=2.28.0
```

【English】
```txt
requests>=2.28.0
```

## 快速开始

【中文】

### 基础使用

```python
from academic_citation_skill import AcademicCitationManager

# 创建管理器实例
manager = AcademicCitationManager()

# 通过DOI获取文献信息
ref = manager.fetch_reference_by_doi("10.1038/nature14539")
print(f"标题: {ref['title']}")
print(f"作者: {', '.join([f\"{a.get('family', '')} {a.get('given', '')}\" for a in ref.get('authors', [])])}")

# 添加到本地文献库
ref_id = manager.add_to_library(ref)

# 生成文中引用
citation = manager.generate_citation(ref_id, style='apa')
print(f"文中引用: {citation}")

# 生成参考文献列表
bibliography = manager.generate_bibliography(style='apa')
for entry in bibliography:
    print(entry)
```

### 命令行使用

```bash
# 通过DOI获取文献
python academic_citation_skill.py --fetch-doi 10.1038/nature14539

# 搜索文献
python academic_citation_skill.py --search "Deep Learning" --author "LeCun"

# 生成参考文献列表
python academic_citation_skill.py --generate-bib --style apa --sort alphabetical

# 检查引用完整性
python academic_citation_skill.py --check document.txt
```

【English】

### Basic Usage

```python
from academic_citation_skill import AcademicCitationManager

# Create manager instance
manager = AcademicCitationManager()

# Fetch reference by DOI
ref = manager.fetch_reference_by_doi("10.1038/nature14539")
print(f"Title: {ref['title']}")
print(f"Authors: {', '.join([f\"{a.get('family', '')} {a.get('given', '')}\" for a in ref.get('authors', [])])}")

# Add to local library
ref_id = manager.add_to_library(ref)

# Generate in-text citation
citation = manager.generate_citation(ref_id, style='apa')
print(f"In-text citation: {citation}")

# Generate bibliography list
bibliography = manager.generate_bibliography(style='apa')
for entry in bibliography:
    print(entry)
```

### Command Line Usage

```bash
# Fetch reference by DOI
python academic_citation_skill.py --fetch-doi 10.1038/nature14539

# Search references
python academic_citation_skill.py --search "Deep Learning" --author "LeCun"

# Generate bibliography list
python academic_citation_skill.py --generate-bib --style apa --sort alphabetical

# Check citation integrity
python academic_citation_skill.py --check document.txt
```

## 使用方法

### Python API

【中文】

#### 创建管理器实例

```python
from academic_citation_skill import AcademicCitationManager

# 使用默认配置
manager = AcademicCitationManager()

# 指定配置目录
manager = AcademicCitationManager(config_dir="/path/to/config")
```

【English】

#### Create Manager Instance

```python
from academic_citation_skill import AcademicCitationManager

# Use default configuration
manager = AcademicCitationManager()

# Specify configuration directory
manager = AcademicCitationManager(config_dir="/path/to/config")
```

#### 通过DOI获取文献 | Fetch Reference by DOI

【中文】
```python
doi = "10.1038/nature14539"
reference = manager.fetch_reference_by_doi(doi)

if reference:
    print(f"文献已找到: {reference['title']}")
    print(f"作者: {', '.join([f\"{a.get('family', '')} {a.get('given', '')}\" for a in reference['authors']])}")
    print(f"年份: {reference['year']}")
    print(f"DOI: {reference.get('doi', 'N/A')}")
else:
    print("未找到文献信息")
```

【English】
```python
doi = "10.1038/nature14539"
reference = manager.fetch_reference_by_doi(doi)

if reference:
    print(f"Reference found: {reference['title']}")
    print(f"Authors: {', '.join([f\"{a.get('family', '')} {a.get('given', '')}\" for a in reference['authors']])}")
    print(f"Year: {reference['year']}")
    print(f"DOI: {reference.get('doi', 'N/A')}")
else:
    print("Reference not found")
```

#### 通过ISBN获取图书 | Fetch Book by ISBN

【中文】
```python
isbn = "9780262033848"
reference = manager.fetch_reference_by_isbn(isbn)

if reference:
    print(f"图书已找到: {reference['title']}")
    print(f"出版社: {reference.get('publisher', 'N/A')}")
    print(f"ISBN: {reference.get('isbn', 'N/A')}")
```

【English】
```python
isbn = "9780262033848"
reference = manager.fetch_reference_by_isbn(isbn)

if reference:
    print(f"Book found: {reference['title']}")
    print(f"Publisher: {reference.get('publisher', 'N/A')}")
    print(f"ISBN: {reference.get('isbn', 'N/A')}")
```

#### 搜索文献 | Search References

【中文】
```python
results = manager.search_references(
    title="Deep Learning",
    author="LeCun",
    year=2015,
    max_results=10
)

print(f"找到 {len(results)} 篇文献:")
for ref in results:
    print(f"  - {ref['title']} ({ref['year']})")
```

【English】
```python
results = manager.search_references(
    title="Deep Learning",
    author="LeCun",
    year=2015,
    max_results=10
)

print(f"Found {len(results)} references:")
for ref in results:
    print(f"  - {ref['title']} ({ref['year']})")
```

#### 生成文中引用 | Generate In-text Citations

【中文】
```python
# 添加文献到库
ref_data = {
    'type': 'journal_article',
    'title': 'Deep Learning',
    'authors': [
        {'given': 'Yann', 'family': 'LeCun', 'sequence': 'first'},
        {'given': 'Yoshua', 'family': 'Bengio', 'sequence': 'additional'},
        {'given': 'Geoffrey', 'family': 'Hinton', 'sequence': 'additional'}
    ],
    'container_title': 'Nature',
    'volume': '521',
    'issue': '7553',
    'page': '436-444',
    'year': 2015,
    'doi': '10.1038/nature14539'
}

ref_id = manager.add_to_library(ref_data)

# APA格式 - 括号式
citation_parenthetical = manager.generate_citation(
    ref_id, 
    style='apa',
    citation_type='parenthetical'
)
print(f"APA括号式: {citation_parenthetical}")
# 输出: (LeCun, Bengio, & Hinton, 2015)

# APA格式 - 叙述式
citation_narrative = manager.generate_citation(
    ref_id,
    style='apa',
    citation_type='narrative'
)
print(f"APA叙述式: {citation_narrative}")
# 输出: LeCun, Bengio, and Hinton (2015)

# IEEE格式
citation_ieee = manager.generate_citation(
    ref_id,
    style='ieee'
)
print(f"IEEE格式: {citation_ieee}")
# 输出: [ref_1]
```

【English】
```python
# Add reference to library
ref_data = {
    'type': 'journal_article',
    'title': 'Deep Learning',
    'authors': [
        {'given': 'Yann', 'family': 'LeCun', 'sequence': 'first'},
        {'given': 'Yoshua', 'family': 'Bengio', 'sequence': 'additional'},
        {'given': 'Geoffrey', 'family': 'Hinton', 'sequence': 'additional'}
    ],
    'container_title': 'Nature',
    'volume': '521',
    'issue': '7553',
    'page': '436-444',
    'year': 2015,
    'doi': '10.1038/nature14539'
}

ref_id = manager.add_to_library(ref_data)

# APA style - Parenthetical
citation_parenthetical = manager.generate_citation(
    ref_id, 
    style='apa',
    citation_type='parenthetical'
)
print(f"APA Parenthetical: {citation_parenthetical}")
# Output: (LeCun, Bengio, & Hinton, 2015)

# APA style - Narrative
citation_narrative = manager.generate_citation(
    ref_id,
    style='apa',
    citation_type='narrative'
)
print(f"APA Narrative: {citation_narrative}")
# Output: LeCun, Bengio, and Hinton (2015)

# IEEE style
citation_ieee = manager.generate_citation(
    ref_id,
    style='ieee'
)
print(f"IEEE style: {citation_ieee}")
# Output: [ref_1]
```

#### 生成参考文献列表 | Generate Bibliography List

【中文】
```python
# APA格式参考文献列表
bibliography_apa = manager.generate_bibliography(style='apa', sort_by='alphabetical')
print("\nAPA格式参考文献:\n")
for i, entry in enumerate(bibliography_apa, 1):
    print(f"{i}. {entry}")

# IEEE格式参考文献列表
bibliography_ieee = manager.generate_bibliography(style='ieee', sort_by='citation_order')
print("\nIEEE格式参考文献:\n")
for i, entry in enumerate(bibliography_ieee, 1):
    print(f"{i}. {entry}")

# GB/T 7714格式（中文文献）
bibliography_gbt = manager.generate_bibliography(style='gbt7714', sort_by='citation_order')
print("\nGB/T 7714格式参考文献:\n")
for i, entry in enumerate(bibliography_gbt, 1):
    print(f"{i}. {entry}")
```

【English】
```python
# APA style bibliography
bibliography_apa = manager.generate_bibliography(style='apa', sort_by='alphabetical')
print("\nAPA Style Bibliography:\n")
for i, entry in enumerate(bibliography_apa, 1):
    print(f"{i}. {entry}")

# IEEE style bibliography
bibliography_ieee = manager.generate_bibliography(style='ieee', sort_by='citation_order')
print("\nIEEE Style Bibliography:\n")
for i, entry in enumerate(bibliography_ieee, 1):
    print(f"{i}. {entry}")

# GB/T 7714 style (Chinese references)
bibliography_gbt = manager.generate_bibliography(style='gbt7714', sort_by='citation_order')
print("\nGB/T 7714 Style Bibliography:\n")
for i, entry in enumerate(bibliography_gbt, 1):
    print(f"{i}. {entry}")
```

#### 检查引用完整性 | Check Citation Integrity

【中文】
```python
# 加载论文文本
with open('paper.txt', 'r', encoding='utf-8') as f:
    paper_text = f.read()

# 检查引用完整性
report = manager.check_citation_integrity(paper_text)

print(f"\n引用完整性报告:")
print(f"  文中引用总数: {report['total_citations']}")
print(f"  参考文献总数: {report['total_references']}")
print(f"  不一致项数量: {report['inconsistencies']}")

if report['missing_in_bibliography']:
    print(f"\n  文中引用但参考文献列表缺失 ({len(report['missing_in_bibliography'])} 项):")
    for item in report['missing_in_bibliography']:
        print(f"    - {item}")

if report['unused_references']:
    print(f"\n  参考文献列表中未使用 ({len(report['unused_references'])} 项):")
    for item in report['unused_references']:
        print(f"    - {item}")

if report['inconsistencies'] == 0:
    print("\n  ✓ 引用完整性检查通过！")
```

【English】
```python
# Load paper text
with open('paper.txt', 'r', encoding='utf-8') as f:
    paper_text = f.read()

# Check citation integrity
report = manager.check_citation_integrity(paper_text)

print(f"\nCitation Integrity Report:")
print(f"  Total in-text citations: {report['total_citations']}")
print(f"  Total bibliography entries: {report['total_references']}")
print(f"  Inconsistencies: {report['inconsistencies']}")

if report['missing_in_bibliography']:
    print(f"\n  Cited but missing from bibliography ({len(report['missing_in_bibliography'])} items):")
    for item in report['missing_in_bibliography']:
        print(f"    - {item}")

if report['unused_references']:
    print(f"\n  Unused in bibliography ({len(report['unused_references'])} items):")
    for item in report['unused_references']:
        print(f"    - {item}")

if report['inconsistencies'] == 0:
    print("\n  ✓ Citation integrity check passed!")
```

#### 格式转换 | Format Conversion

【中文】
```python
# 获取所有参考文献
references = manager.database.get_all_references()

# 转换为IEEE格式
converted = manager.convert_citation_style(
    references=references,
    from_style='apa',
    to_style='ieee'
)

print("\n格式转换结果:")
for item in converted:
    print(f"\nID: {item['id']}")
    print(f"  原格式: {item.get('original', '')[:100]}...")
    print(f"  新格式: {item.get('converted', '')[:100]}...")
    print(f"  转换: {item['from_style']} -> {item['to_style']}")
```

【English】
```python
# Get all references
references = manager.database.get_all_references()

# Convert to IEEE style
converted = manager.convert_citation_style(
    references=references,
    from_style='apa',
    to_style='ieee'
)

print("\nFormat Conversion Results:")
for item in converted:
    print(f"\nID: {item['id']}")
    print(f"  Original: {item.get('original', '')[:100]}...")
    print(f"  Converted: {item.get('converted', '')[:100]}...")
    print(f"  Conversion: {item['from_style']} -> {item['to_style']}")
```

#### BibTeX导入导出 | BibTeX Import/Export

【中文】
```python
# 导出为BibTeX格式
success = manager.export_bibtex('references.bib')
if success:
    print("BibTeX文件已成功导出: references.bib")

# 从BibTeX文件导入
count = manager.import_from_bibtex('references.bib')
print(f"成功导入 {count} 篇文献")
```

【English】
```python
# Export to BibTeX format
success = manager.export_bibtex('references.bib')
if success:
    print("BibTeX file successfully exported: references.bib")

# Import from BibTeX file
count = manager.import_from_bibtex('references.bib')
print(f"Successfully imported {count} references")
```

### 命令行工具 | Command Line Tools

【中文】

#### 通过DOI获取文献信息
```bash
python academic_citation_skill.py --fetch-doi 10.1038/nature14539
```

#### 通过ISBN获取图书信息
```bash
python academic_citation_skill.py --fetch-isbn 9780262033848
```

#### 搜索文献
```bash
# 基本搜索
python academic_citation_skill.py --search "Deep Learning"

# 指定作者搜索
python academic_citation_skill.py --search "Deep Learning" --author "LeCun"

# 指定年份搜索
python academic_citation_skill.py --search "Deep Learning" --year 2015

# 限制结果数量
python academic_citation_skill.py --search "Deep Learning" --max-results 20
```

#### 生成参考文献列表
```bash
# APA格式，字母排序
python academic_citation_skill.py --generate-bib --style apa --sort alphabetical

# IEEE格式，引用顺序排序
python academic_citation_skill.py --generate-bib --style ieee --sort citation_order

# GB/T 7714格式
python academic_citation_skill.py --generate-bib --style gbt7714 --sort citation_order --output refs.txt
```

#### 批量导入参考文献
```bash
# 导入BibTeX文件
python batch_import.py --bibtex references.bib

# 导入RIS文件
python batch_import.py --ris references.ris

# 导入JSON文件
python batch_import.py --json references.json

# 导入CSV文件
python batch_import.py --csv references.csv

# 批量导入整个目录
python batch_import.py --directory ./references --pattern "*.bib"
```

#### 格式转换
```bash
# APA转IEEE
python academic_citation_skill.py --convert --from-style apa --to-style ieee --input apa_refs.txt --output ieee_refs.txt

# Chicago转Harvard
python academic_citation_skill.py --convert --from-style chicago --to-style harvard --input chicago_refs.txt
```

#### 检查引用完整性
```bash
# 检查文档引用
python academic_citation_skill.py --check paper.txt

# 生成详细报告
python academic_citation_skill.py --check paper.txt --verbose
```

#### 文献库管理
```bash
# 显示统计信息
python academic_citation_skill.py --stats

# 导出为JSON
python academic_citation_skill.py --export-json library.json

# 从JSON导入
python academic_citation_skill.py --import-json library.json
```

【English】

#### Fetch Reference Information by DOI
```bash
python academic_citation_skill.py --fetch-doi 10.1038/nature14539
```

#### Fetch Book Information by ISBN
```bash
python academic_citation_skill.py --fetch-isbn 9780262033848
```

#### Search References
```bash
# Basic search
python academic_citation_skill.py --search "Deep Learning"

# Search with author
python academic_citation_skill.py --search "Deep Learning" --author "LeCun"

# Search with year
python academic_citation_skill.py --search "Deep Learning" --year 2015

# Limit results
python academic_citation_skill.py --search "Deep Learning" --max-results 20
```

#### Generate Bibliography List
```bash
# APA style, alphabetical sort
python academic_citation_skill.py --generate-bib --style apa --sort alphabetical

# IEEE style, citation order sort
python academic_citation_skill.py --generate-bib --style ieee --sort citation_order

# GB/T 7714 style
python academic_citation_skill.py --generate-bib --style gbt7714 --sort citation_order --output refs.txt
```

#### Batch Import References
```bash
# Import BibTeX file
python batch_import.py --bibtex references.bib

# Import RIS file
python batch_import.py --ris references.ris

# Import JSON file
python batch_import.py --json references.json

# Import CSV file
python batch_import.py --csv references.csv

# Batch import entire directory
python batch_import.py --directory ./references --pattern "*.bib"
```

#### Format Conversion
```bash
# APA to IEEE
python academic_citation_skill.py --convert --from-style apa --to-style ieee --input apa_refs.txt --output ieee_refs.txt

# Chicago to Harvard
python academic_citation_skill.py --convert --from-style chicago --to-style harvard --input chicago_refs.txt
```

#### Check Citation Integrity
```bash
# Check document citations
python academic_citation_skill.py --check paper.txt

# Generate detailed report
python academic_citation_skill.py --check paper.txt --verbose
```

#### Library Management
```bash
# Show statistics
python academic_citation_skill.py --stats

# Export to JSON
python academic_citation_skill.py --export-json library.json

# Import from JSON
python academic_citation_skill.py --import-json library.json
```

## 配置说明

【中文】

### 配置文件结构

项目使用以下配置文件：

1. **citation_styles.json** - 引用格式定义
   - 定义各种引用格式的规则
   - 包括文内引用和参考文献列表格式
   - 支持自定义样式

2. **crossref_config.json** - Crossref API配置
   - API端点和请求参数
   - 速率限制和重试策略
   - 缓存设置

3. **reference_database.json** - 本地文献数据库
   - 存储所有参考文献信息
   - 引用映射关系
   - 统计信息

### 自定义引用格式

【中文】

可以通过编辑 `citation_styles.json` 文件来自定义引用格式。每个格式包含以下配置：

```json
{
  "style_name": {
    "name": "格式显示名称",
    "in_text": {
      "format": "parenthetical|footnote|numeric",
      "separator": ", ",
      "et_al": "et al.",
      "multiple_authors": {...}
    },
    "bibliography": {
      "sort_by": "alphabetical|citation_order|year",
      "author_format": "last_first|given_first",
      "title_format": "sentence_case|title_case",
      "document_type_codes": {...}
    }
  }
}
```

【English】

Customize citation styles by editing the `citation_styles.json` file. Each format includes the following configuration:

```json
{
  "style_name": {
    "name": "Format Display Name",
    "in_text": {
      "format": "parenthetical|footnote|numeric",
      "separator": ", ",
      "et_al": "et al.",
      "multiple_authors": {...}
    },
    "bibliography": {
      "sort_by": "alphabetical|citation_order|year",
      "author_format": "last_first|given_first",
      "title_format": "sentence_case|title_case",
      "document_type_codes": {...}
    }
  }
}
```

### Crossref API配置

【中文】

`crossref_config.json` 文件包含Crossref API的配置选项：

- **api_base**: API基础URL
- **endpoints**: 各个API端点
- **request_config**: 请求参数配置
- **rate_limiting**: 速率限制设置
- **filters**: 默认查询过滤器
- **cache**: 缓存配置

```json
{
  "api_base": "https://api.crossref.org",
  "rate_limiting": {
    "requests_per_second": 10,
    "enabled": true
  },
  "cache": {
    "enabled": true,
    "ttl_seconds": 86400
  }
}
```

【English】

The `crossref_config.json` file contains Crossref API configuration options:

- **api_base**: API base URL
- **endpoints**: Various API endpoints
- **request_config**: Request parameter configuration
- **rate_limiting**: Rate limiting settings
- **filters**: Default query filters
- **cache**: Cache configuration

```json
{
  "api_base": "https://api.crossref.org",
  "rate_limiting": {
    "requests_per_second": 10,
    "enabled": true
  },
  "cache": {
    "enabled": true,
    "ttl_seconds": 86400
  }
}
```

## API文档

### AcademicCitationManager类

【中文】

主要的学术引用管理器类，提供完整的引用管理功能。

#### 方法

##### `__init__(config_dir=None)`
初始化管理器。

**参数：**
- `config_dir` (str, 可选): 配置文件目录路径

**返回：**
- `AcademicCitationManager` 实例

##### `fetch_reference_by_doi(doi)`
通过DOI获取文献信息。

**参数：**
- `doi` (str): DOI标识符

**返回：**
- `dict` 或 `None`: 文献信息字典

**示例：**
```python
manager = AcademicCitationManager()
ref = manager.fetch_reference_by_doi("10.1038/nature14539")
```

##### `search_references(title, author=None, year=None, max_results=10)`
通过标题和作者搜索文献。

**参数：**
- `title` (str): 文献标题
- `author` (str, 可选): 作者姓名
- `year` (int, 可选): 出版年份
- `max_results` (int, 可选): 最大结果数

**返回：**
- `list`: 匹配的文献列表

##### `add_to_library(reference)`
添加文献到本地库。

**参数：**
- `reference` (Reference或dict): 文献对象或字典

**返回：**
- `str`: 文献ID

##### `generate_citation(reference_id, style='apa', citation_type='parenthetical', page=None)`
生成文中引用。

**参数：**
- `reference_id` (str): 文献ID
- `style` (str): 引用格式
- `citation_type` (str): 引用类型
- `page` (str, 可选): 页码

**返回：**
- `str`: 格式化的引用字符串

##### `generate_bibliography(style='apa', sort_by='alphabetical')`
生成参考文献列表。

**参数：**
- `style` (str): 引用格式
- `sort_by` (str): 排序方式

**返回：**
- `list`: 格式化的参考文献条目列表

##### `check_citation_integrity(document_text)`
检查文档引用完整性。

**参数：**
- `document_text` (str): 文档文本

**返回：**
- `dict`: 完整性报告

##### `convert_citation_style(references, from_style, to_style)`
转换引用格式。

**参数：**
- `references` (list): 文献列表
- `from_style` (str): 源格式
- `to_style` (str): 目标格式

**返回：**
- `list`: 转换结果列表

【English】

Main academic citation manager class providing complete citation management functionality.

#### Methods

##### `__init__(config_dir=None)`
Initialize the manager.

**Parameters:**
- `config_dir` (str, optional): Configuration file directory path

**Returns:**
- `AcademicCitationManager` instance

##### `fetch_reference_by_doi(doi)`
Fetch reference information by DOI.

**Parameters:**
- `doi` (str): DOI identifier

**Returns:**
- `dict` or `None`: Reference information dictionary

**Example:**
```python
manager = AcademicCitationManager()
ref = manager.fetch_reference_by_doi("10.1038/nature14539")
```

##### `search_references(title, author=None, year=None, max_results=10)`
Search references by title and author.

**Parameters:**
- `title` (str): Reference title
- `author` (str, optional): Author name
- `year` (int, optional): Publication year
- `max_results` (int, optional): Maximum number of results

**Returns:**
- `list`: List of matching references

##### `add_to_library(reference)`
Add reference to local library.

**Parameters:**
- `reference` (Reference or dict): Reference object or dictionary

**Returns:**
- `str`: Reference ID

##### `generate_citation(reference_id, style='apa', citation_type='parenthetical', page=None)`
Generate in-text citation.

**Parameters:**
- `reference_id` (str): Reference ID
- `style` (str): Citation style
- `citation_type` (str): Citation type
- `page` (str, optional): Page number

**Returns:**
- `str`: Formatted citation string

##### `generate_bibliography(style='apa', sort_by='alphabetical')`
Generate bibliography list.

**Parameters:**
- `style` (str): Citation style
- `sort_by` (str): Sorting method

**Returns:**
- `list`: List of formatted bibliography entries

##### `check_citation_integrity(document_text)`
Check document citation integrity.

**Parameters:**
- `document_text` (str): Document text

**Returns:**
- `dict`: Integrity report

##### `convert_citation_style(references, from_style, to_style)`
Convert citation styles.

**Parameters:**
- `references` (list): List of references
- `from_style` (str): Source style
- `to_style` (str): Target style

**Returns:**
- `list`: List of conversion results

### Reference类

【中文】

参考文献信息的数据类。

#### 属性

- `id` (str): 唯一标识符
- `type` (str): 文献类型
- `title` (str): 标题
- `authors` (List[Author]): 作者列表
- `year` (int): 出版年份
- `doi` (str, 可选): DOI
- `isbn` (str, 可选): ISBN
- `container_title` (str, 可选): 容器标题（期刊名等）
- `volume` (str, 可选): 卷号
- `issue` (str, 可选): 期号
- `page` (str, 可选): 页码
- `publisher` (str, 可选): 出版社
- `url` (str, 可选): URL
- `language` (str): 语言
- `tags` (List[str]): 标签列表
- `abstract` (str, 可选): 摘要
- `issn` (List[str], 可选): ISSN

【English】

Data class for reference information.

#### Attributes

- `id` (str): Unique identifier
- `type` (str): Reference type
- `title` (str): Title
- `authors` (List[Author]): List of authors
- `year` (int): Publication year
- `doi` (str, optional): DOI
- `isbn` (str, optional): ISBN
- `container_title` (str, optional): Container title (journal name, etc.)
- `volume` (str, optional): Volume number
- `issue` (str, optional): Issue number
- `page` (str, optional): Page numbers
- `publisher` (str, optional): Publisher
- `url` (str, optional): URL
- `language` (str): Language
- `tags` (List[str]): List of tags
- `abstract` (str, optional): Abstract
- `issn` (List[str], optional): ISSN

## 常见问题

【中文】

### 使用问题

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

**Q: 中文文献的GB/T 7714格式支持哪些文献类型？**
A: GB/T 7714-2015支持以下文献类型标识：
- [M] 专著
- [J] 期刊文章
- [C] 会议论文
- [D] 学位论文
- [R] 报告
- [N] 报纸文章
- [S] 标准
- [P] 专利
- [DB] 数据库
- [CP] 计算机程序

### 技术问题

**Q: Crossref API调用失败怎么办？**
A: 可能的原因和解决方案：
1. 网络连接问题：检查网络连接
2. API速率限制：程序已内置速率限制，自动重试
3. DOI不存在：确认DOI格式正确
4. 文献不在Crossref数据库中：尝试使用标题搜索

**Q: BibTeX导入失败怎么办？**
A: 检查以下事项：
1. 确认BibTeX文件编码为UTF-8
2. 检查文件格式是否正确
3. 查看错误日志获取具体错误信息
4. 尝试使用其他格式（如JSON）导入

**Q: 如何提高批量导入性能？**
A: 优化建议：
1. 使用本地缓存减少API调用
2. 分批处理大量文献
3. 关闭详细日志减少I/O
4. 使用SSD存储数据库

**Q: 中文文献的作者姓名格式如何处理？**
A: GB/T 7714标准要求：
- 中文作者姓名：姓在前，名在后（如：张三）
- 英文作者姓名：与APA格式相同（如：Smith, J.）
- 程序会自动根据语言调整格式

【English】

### Usage Questions

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

**Q: Which document types does GB/T 7714 support for Chinese references?**
A: GB/T 7714-2015 supports the following document type identifiers:
- [M] Monograph
- [J] Journal article
- [C] Conference paper
- [D] Dissertation/Thesis
- [R] Report
- [N] Newspaper article
- [S] Standard
- [P] Patent
- [DB] Database
- [CP] Computer program

### Technical Questions

**Q: What to do if Crossref API call fails?**
A: Possible causes and solutions:
1. Network connection issues: Check network connection
2. API rate limiting: Program includes built-in rate limiting with automatic retry
3. DOI does not exist: Confirm DOI format is correct
4. Reference not in Crossref database: Try searching by title

**Q: What to do if BibTeX import fails?**
A: Check the following:
1. Confirm BibTeX file encoding is UTF-8
2. Check if file format is correct
3. Check error log for specific error messages
4. Try importing with other formats (like JSON)

**Q: How to improve batch import performance?**
A: Optimization recommendations:
1. Use local caching to reduce API calls
2. Process large volumes in batches
3. Disable verbose logging to reduce I/O
4. Use SSD for database storage

**Q: How are Chinese author name formats handled?**
A: GB/T 7714 standard requires:
- Chinese author names: Surname before given name (e.g., 张三)
- English author names: Same as APA format (e.g., Smith, J.)
- Program automatically adjusts format based on language

## 贡献指南

【中文】

欢迎各种形式的贡献！

### 报告Bug

如果您发现了bug，请：

1. 在GitHub上创建issue：https://github.com/YouStudyeveryday/academic-citation-manager/issues
2. 提供清晰的bug描述
3. 包含复现步骤
4. 提供系统信息和Python版本

### 提交新功能

如果您有新功能建议：

1. 先在GitHub上搜索是否已有类似的issue
2. 如果没有，创建新issue
3. 详细描述新功能
4. 说明使用场景和预期效果

### 代码贡献

欢迎提交Pull Request！

1. Fork本仓库
2. 创建您的功能分支 (`git checkout -b my-feature`)
3. 提交您的更改 (`git commit -am 'Add some feature'`)
4. 推送到分支 (`git push origin my-feature`)
5. 创建Pull Request

### 代码规范

- 遵循PEP 8代码风格
- 添加适当的文档字符串
- 添加单元测试
- 确保所有测试通过

【English】

All forms of contributions are welcome!

### Reporting Bugs

If you find a bug:

1. Create an issue on GitHub: https://github.com/YouStudyeveryday/academic-citation-manager/issues
2. Provide a clear bug description
3. Include reproduction steps
4. Provide system information and Python version

### Submitting New Features

If you have suggestions for new features:

1. Search GitHub for similar issues first
2. If none exists, create a new issue
3. Describe the new feature in detail
4. Explain use cases and expected behavior

### Code Contributions

Pull Requests are welcome!

1. Fork this repository
2. Create your feature branch (`git checkout -b my-feature`)
3. Commit your changes (`git commit -am 'Add some feature'`)
4. Push to the branch (`git push origin my-feature`)
5. Create a Pull Request

### Code Standards

- Follow PEP 8 code style
- Add appropriate docstrings
- Add unit tests
- Ensure all tests pass

## 许可证

本项目采用 MIT 许可证。详见 [LICENSE](LICENSE) 文件。

This project is licensed under the MIT License. See [LICENSE](LICENSE) file for details.

## 致谢

感谢以下项目和资源为本项目提供的基础和支持：

- [Crossref](https://www.crossref.org/) - 提供免费的DOI元数据查询服务
- [citation-style-language](https://citationstyles.org/) - Citation Style Language规范
- [Open Source Community](https://github.com) - 开源社区的各种贡献

特别感谢所有为学术引用管理工具做出贡献的开发者。

Thanks to the following projects and resources for providing the foundation and support for this project:

- [Crossref](https://www.crossref.org/) - Providing free DOI metadata query service
- [citation-style-language](https://citationstyles.org/) - Citation Style Language specification
- [Open Source Community](https://github.com) - Various contributions from the open source community

Special thanks to all developers who have contributed to academic citation management tools.

## 联系方式

- 项目主页：https://github.com/YouStudyeveryday/academic-citation-manager
- 问题反馈：https://github.com/YouStudyeveryday/academic-citation-manager/issues
- 技术支持：youstudyeveryday@example.com

---

**最后更新**: 2026-03-01  
**版本**: 1.0.0