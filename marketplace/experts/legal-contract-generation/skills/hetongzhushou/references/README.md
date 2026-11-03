# 合同智能助手 1.0.2

## 技能概述

合同智能助手是一款全能型合同管理工具，集合同生成、审查、管理于一体。支持从合同起草到归档的全流程管理，包括智能生成、风险识别、合规审查、条款对比、修改建议等专业功能。适用于企业法务、个人签约、合同管理等场景。

---

## 🎯 核心能力矩阵

### 生成能力（新增）
- ✨ 合同生成：支持各行业合同智能生成
- ✨ 模板库：100+专业合同模板即选即用
- ✨ 对话引导填写：智能对话收集合同信息
- ✨ AI智能起草：根据需求自动生成合同条款
- ✨ 条款建议：针对特定场景提供专业条款建议
- ✨ Word导出：一键导出标准Word文档
- ✨ 合同存档：合同分类管理与历史版本追溯

### 审查能力（原有）
- 🔍 合同识别：自动识别合同类型和基本信息
- 🔍 条款提取：智能提取关键条款要素
- 🔍 风险预警：逐条风险评估与隐患识别
- 🔍 合规检查：核对法律强制性规定
- 🔍 对比分析：多版本合同差异对比
- 🔍 修改建议：专业条款修改建议
- 🔍 智能问答：合同相关问题即时解答
- 🔍 报告生成：结构化审查报告输出

---

## 📁 目录结构

```
contract-assistant/
├── SKILL.md                 # 技能主说明文件
├── scripts/                 # 核心脚本目录
│   ├── __init__.py         # 脚本包初始化
│   ├── contract_review.py   # 合同审查主脚本
│   ├── clause_extraction.py # 条款提取脚本
│   ├── risk_detection.py    # 风险检测脚本
│   ├── compliance_check.py   # 合规检查脚本
│   ├── contract_generator.py # 合同生成脚本
│   ├── comparison_analysis.py # 对比分析脚本
│   ├── report_generator.py   # 报告生成脚本
│   └── utils.py             # 工具函数
├── templates/               # 合同模板目录
│   ├── template_index.json  # 模板索引
│   ├── labor_standard.json  # 标准劳动合同模板
│   ├── labor_tech.json      # 技术岗劳动合同模板
│   ├── sale_standard.json    # 标准买卖合同模板
│   └── rental_house.json     # 房屋租赁合同模板
├── data/                    # 数据目录
│   ├── risk_rules.json      # 风险规则库
│   └── legal_database.json  # 法规数据库
└── references/              # 参考文档目录
    ├── README.md            # 本文件
    └── USAGE.md             # 使用指南
```

---

## 🚀 快速开始

### 基本使用

```python
from scripts.contract_review import ContractReviewer

# 初始化审查器
reviewer = ContractReviewer()

# 执行审查
contract_text = """
劳动合同

第三条 工作内容
乙方同意在技术部门担任高级工程师。

第五条 薪酬待遇
乙方的月工资为税前28000元。
"""

result = reviewer.review(contract_text)
print(result)
```

### 命令行使用

```bash
# 基础审查
python scripts/contract_review.py --input "合同文本..." --type 劳动合同

# 从文件审查
python scripts/contract_review.py --file contract.txt --output report.md

# 指定输出格式
python scripts/contract_review.py --file contract.txt --format json
```

---

## 📋 脚本功能详解

### 1. contract_review.py - 合同审查主脚本

主入口脚本，整合所有审查功能：

```python
from scripts.contract_review import ContractReviewer

reviewer = ContractReviewer(contract_type="劳动合同")
result = reviewer.review(contract_text)

# 生成报告
report = reviewer.generate_report(result, output_path="report.md")
```

### 2. clause_extraction.py - 条款提取

自动识别并提取合同中的各类条款：

```python
from scripts.clause_extraction import ClauseExtractor

extractor = ClauseExtractor()
result = extractor.extract(contract_text, contract_type="劳动合同")

# 返回结构
{
    "contract_type": "劳动合同",
    "clauses": [...],        # 提取的条款列表
    "key_elements": {...},   # 关键要素
    "completeness": {...},   # 完整性检查
    "total_clauses": 15
}
```

支持的条款类型：
- 基础信息条款
- 标的条款
- 价款条款
- 期限条款
- 违约责任条款
- 保密条款
- 竞业限制条款
- 争议解决条款
- 等等

### 3. risk_detection.py - 风险检测

智能检测合同中的风险条款：

```python
from scripts.risk_detection import RiskDetector

detector = RiskDetector()
risks = detector.detect(clauses_data, contract_type="劳动合同")

# 返回结构
{
    "high_risk": [...],      # 高风险条款
    "medium_risk": [...],    # 中风险条款
    "low_risk": [...],       # 低风险条款
    "risk_summary": {...}    # 风险摘要
}
```

### 4. compliance_check.py - 合规检查

核对合同是否符合法律法规：

```python
from scripts.compliance_check import ComplianceChecker

checker = ComplianceChecker()
result = checker.check(contract_text, clauses_data, contract_type)

# 返回结构
{
    "issues": [...],              # 所有问题
    "mandatory_violations": [...], # 强制性规定违反
    "format_clause_issues": [...], # 格式条款问题
    "is_compliant": True/False,
    "compliance_score": 85.5
}
```

### 5. contract_generator.py - 合同生成

支持多种合同生成方式：

```python
from scripts.contract_generator import ContractGenerator

generator = ContractGenerator()

# 方式一：从模板生成
fields = {
    "甲方名称": "XX公司",
    "乙方姓名": "张三",
    "月薪": "28000"
}
contract = generator.generate_from_template("labor_standard", fields)

# 方式二：条款建议
suggestions = generator.suggest_clauses("技术岗位", "保密条款")

# 方式三：AI起草框架
framework = generator.generate_with_ai("需要一份销售合同", "买卖合同")
```

### 6. comparison_analysis.py - 对比分析

对比两个版本合同的差异：

```python
from scripts.comparison_analysis import ContractComparator

comparator = ContractComparator()
report = comparator.compare(old_contract, new_contract)

# 生成Markdown报告
markdown_report = comparator.generate_diff_markdown(report)
```

### 7. report_generator.py - 报告生成

生成结构化审查报告：

```python
from scripts.report_generator import ReportGenerator

generator = ReportGenerator()

# 支持多种格式
markdown_report = generator.generate(review_result, format="markdown")
json_report = generator.generate(review_result, format="json")
html_report = generator.generate(review_result, format="html")
text_report = generator.generate(review_result, format="text")
```

---

## 📚 数据文件

### risk_rules.json - 风险规则库

包含各类合同的风险检测规则：

```json
{
  "categories": {
    "劳动人事类": {
      "rules": [
        {
          "id": "LAB001",
          "type": "竞业限制",
          "name": "竞业限制期限过长",
          "severity": "high",
          "legal_basis": "《劳动合同法》第24条"
        }
      ]
    }
  }
}
```

### legal_database.json - 法规数据库

包含常用法律法规条文：

```json
{
  "regulations": {
    "劳动法": {
      "articles": {
        "第44条": {
          "title": "延长工作时间的工资报酬",
          "content": "..."
        }
      }
    }
  }
}
```

---

## 📝 模板文件

模板文件位于 `templates/` 目录：

| 文件 | 名称 | 适用场景 |
|------|------|---------|
| labor_standard.json | 标准劳动合同 | 普通员工入职 |
| labor_tech.json | 技术岗劳动合同 | 研发/技术岗位 |
| sale_standard.json | 标准买卖合同 | 商品交易 |
| rental_house.json | 房屋租赁合同 | 住宅/商铺出租 |

模板使用方式：

```python
from scripts.contract_generator import ContractGenerator

generator = ContractGenerator()

# 列出所有模板
templates = generator.list_templates()
for t in templates:
    print(f"{t['id']}: {t['name']}")
```

---

## ⚠️ 注意事项

1. **知识截止日期**：模型知识有截止日期，最新法规变化可能未包含
2. **地域性差异**：不同地区可能有地方性法规差异
3. **专业复杂度**：极专业的法律问题建议咨询执业律师
4. **非诉业务**：本技能侧重合同生成与审查，不提供诉讼代理服务

---

## 📞 支持与反馈

如有问题或建议，请通过虾评平台提交反馈。

---

## 版本更新记录

### v1.0.2 (2026.04.29)
- ✨ 新增：完整的scripts脚本目录
- ✨ 新增：templates/合同模板目录
- ✨ 新增：data/风险规则库和法规数据库
- ✨ 新增：references/参考文档目录

### v1.0.1 (2026.04.25)
- ✨ 新增：合同智能生成功能（AI起草+模板选择）
- ✨ 新增：100+合同模板库（7大类全面覆盖）
- ✨ 新增：对话引导填写功能
- ✨ 新增：条款智能建议功能
- ✨ 新增：Word文档导出功能
- ✨ 新增：合同存档管理功能

### v1.0.0 (2026.04.24)
- 初始版本：基础合同审查功能
