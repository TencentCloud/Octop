# 合同智能助手 - 使用指南

## 目录

1. [安装与配置](#安装与配置)
2. [快速开始](#快速开始)
3. [合同审查](#合同审查)
4. [合同生成](#合同生成)
5. [合同对比](#合同对比)
6. [自定义扩展](#自定义扩展)
7. [常见问题](#常见问题)

---

## 安装与配置

### 环境要求

- Python 3.8+
- 推荐安装依赖：`pip install -r requirements.txt`

### 基本安装

```bash
# 克隆技能目录
git clone <skill-repo> contract-assistant
cd contract-assistant

# 安装依赖
pip install python-docx
```

---

## 快速开始

### 示例1：快速审查合同

```python
from scripts.contract_review import ContractReviewer

# 初始化
reviewer = ContractReviewer()

# 合同文本
contract_text = """
劳动合同

甲方：深圳市XX科技有限公司
乙方：张三

第三条 工作内容
乙方同意在技术部门担任高级工程师。

第五条 薪酬待遇
乙方的月工资为税前28000元。
"""

# 执行审查
result = reviewer.review(contract_text)

# 查看结果
print(f"合同类型: {result['contract_type']}")
print(f"综合评级: {result['overall_rating']}")
print(f"高风险条款: {len(result['phases']['risk_detection']['high_risk'])}")
```

### 示例2：从模板生成合同

```python
from scripts.contract_generator import ContractGenerator

generator = ContractGenerator()

# 填充字段
fields = {
    "甲方名称": "深圳市XX科技有限公司",
    "甲方代码": "91440300XXXXXXXXX",
    "甲方法人": "李明",
    "乙方姓名": "张三",
    "乙方身份证": "110101199001011234",
    "合同期限": "3年",
    "试用期": "6个月",
    "月薪": "28000",
    "岗位": "高级工程师",
    "签订日期": "2024-01-01"
}

# 生成合同
contract = generator.generate_from_template("labor_standard", fields)
print(contract.raw_text)
```

---

## 合同审查

### 完整审查流程

```python
from scripts.contract_review import ContractReviewer

reviewer = ContractReviewer(contract_type="劳动合同")

# 执行完整审查
result = reviewer.review(contract_text)

# 生成报告
report = reviewer.generate_report(result, output_path="审查报告.md")
```

### 分步骤审查

如果你需要更细粒度的控制：

```python
from scripts.clause_extraction import ClauseExtractor
from scripts.risk_detection import RiskDetector
from scripts.compliance_check import ComplianceChecker
from scripts.report_generator import ReportGenerator

# 1. 条款提取
extractor = ClauseExtractor()
clauses = extractor.extract(contract_text, "劳动合同")

# 2. 风险检测
detector = RiskDetector()
risks = detector.detect(clauses, "劳动合同")

# 3. 合规检查
checker = ComplianceChecker()
compliance = checker.check(contract_text, clauses, "劳动合同")

# 4. 生成报告
report_gen = ReportGenerator()
report = report_gen.generate({
    "contract_type": "劳动合同",
    "overall_rating": "高危",
    "phases": {
        "clause_extraction": clauses,
        "risk_detection": risks,
        "compliance_check": compliance
    }
})
```

### 命令行使用

```bash
# 基础审查
python scripts/contract_review.py --input "合同文本..." --type 劳动合同

# 从文件审查
python scripts/contract_review.py --file contract.txt --output report.md

# 指定输出格式
python scripts/contract_review.py --file contract.txt --format json

# 查看帮助
python scripts/contract_review.py --help
```

---

## 合同生成

### 模板选择

```python
from scripts.contract_generator import ContractGenerator

generator = ContractGenerator()

# 列出所有模板
all_templates = generator.list_templates()
print(all_templates)

# 按分类列出
labor_templates = generator.list_templates(category="劳动人事类")
print(labor_templates)
```

### 模板生成

```python
from scripts.contract_generator import ContractGenerator

generator = ContractGenerator()

# 填充字段
fields = {
    "甲方名称": "XX公司",
    "乙方姓名": "张三",
    "月薪": "28000",
    "岗位": "工程师",
    # ... 其他字段
}

# 生成合同
contract = generator.generate_from_template("labor_standard", fields)

# 访问结果
print(contract.raw_text)       # 原始文本
print(contract.sections)       # 章节字典
print(contract.warnings)        # 警告信息
```

### 条款建议

```python
from scripts.contract_generator import ContractGenerator

generator = ContractGenerator()

# 获取保密条款建议
suggestions = generator.suggest_clauses("技术岗位", "保密条款")

for s in suggestions:
    print(f"【{s['name']}】")
    print(f"适用场景: {s['applicable']}")
    print(s['content'])
    print()
```

### AI智能起草

```python
from scripts.contract_generator import ContractGenerator

generator = ContractGenerator()

# 描述需求
requirements = """
我需要一份技术开发合同：
- 开发一个电商平台
- 总价100万元
- 工期6个月
- 需要包含知识产权归属条款
"""

# 生成框架
result = generator.generate_with_ai(requirements, "服务合同")

print(result["extracted_info"])          # 提取的关键信息
print(result["recommended_structure"])   # 推荐的合同结构
print(result["key_clauses"])             # 关键条款建议
```

---

## 合同对比

### 版本对比

```python
from scripts.comparison_analysis import ContractComparator

comparator = ContractComparator()

# 两个版本
old_contract = """..."""
new_contract = """..."""

# 执行对比
report = comparator.compare(old_contract, new_contract)

# 统计
print(f"总变更数: {report.total_changes}")
print(f"新增: {report.additions}")
print(f"删除: {report.removals}")
print(f"修改: {report.modifications}")

# 风险变更
print(f"风险增加: {report.risk_summary['risk_increased']}")
print(f"风险降低: {report.risk_summary['risk_decreased']}")

# 生成Markdown报告
markdown = comparator.generate_diff_markdown(report)
print(markdown)
```

### 逐条款对比

```python
for diff in report.clause_diffs:
    print(f"条款: {diff.clause_id}")
    print(f"变更类型: {diff.change_type}")
    print(f"风险影响: {diff.risk_impact}")
    print(f"说明: {diff.diff_summary}")
    
    if diff.change_type == "modified":
        print(f"原内容: {diff.old_content[:100]}...")
        print(f"新内容: {diff.new_content[:100]}...")
```

---

## 自定义扩展

### 添加自定义风险规则

编辑 `data/risk_rules.json`：

```json
{
  "categories": {
    "自定义类": {
      "rules": [
        {
          "id": "CUSTOM001",
          "type": "自定义风险",
          "name": "风险名称",
          "severity": "high",
          "patterns": ["风险模式"],
          "legal_basis": "相关法律",
          "suggestion": "修改建议"
        }
      ]
    }
  }
}
```

### 添加自定义模板

在 `templates/` 目录添加新的模板文件：

```json
{
  "id": "my_template",
  "name": "我的自定义模板",
  "category": "自定义类",
  "content": "模板内容 {占位符}...",
  "required_fields": [
    {"name": "占位符", "type": "text", "required": true}
  ]
}
```

### 扩展条款提取规则

编辑 `scripts/clause_extraction.py` 中的 `_init_clause_patterns` 方法：

```python
def _init_clause_patterns(self) -> Dict:
    patterns = super()._init_clause_patterns()
    
    patterns[ClauseType.NEW_TYPE] = {
        "patterns": [r"第X条[^\n]*新条款"],
        "keywords": ["新关键词"]
    }
    
    return patterns
```

---

## 常见问题

### Q: 如何处理PDF或Word文档？

```python
# PDF处理
import PyPDF2

with open("contract.pdf", "rb") as f:
    reader = PyPDF2.PdfReader(f)
    text = ""
    for page in reader.pages:
        text += page.extract_text()

# Word处理
from docx import Document

doc = Document("contract.docx")
text = "\n".join([p.text for p in doc.paragraphs])
```

### Q: 如何批量审查多个合同？

```python
from pathlib import Path
from scripts.contract_review import ContractReviewer

reviewer = ContractReviewer()

# 遍历目录
for file in Path("contracts/").glob("*.txt"):
    with open(file, "r", encoding="utf-8") as f:
        contract_text = f.read()
    
    result = reviewer.review(contract_text)
    
    # 保存报告
    output_path = f"reports/{file.stem}_report.md"
    reviewer.generate_report(result, output_path)
```

### Q: 如何自定义报告格式？

```python
from scripts.report_generator import ReportGenerator

generator = ReportGenerator()

# 自定义格式化
result = generator.generate(review_result, format="markdown")

# 添加自定义内容
custom_report = f"""
# 自定义报告标题

{result}

---
生成人: XXX
生成时间: {datetime.now()}
"""

with open("custom_report.md", "w") as f:
    f.write(custom_report)
```

### Q: 风险检测的准确度如何提高？

1. **提供完整的合同文本**：越完整的文本分析越准确
2. **指定正确的合同类型**：不同类型有不同的风险规则
3. **更新风险规则库**：定期更新 `data/risk_rules.json`
4. **结合法律咨询**：专业问题建议咨询律师

---

## 联系方式

如有问题或建议，请通过以下方式联系我们：

- 提交Issue
- 发送邮件至 support@example.com
- 访问官方网站

---

*最后更新：2026-04-29*
