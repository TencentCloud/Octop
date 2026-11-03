# 护理监护路径规划 SKILL v3.2

## 📋 简介

本SKILL用于生成完整的护理监护计划HTML报告。用户输入诊断、症状、或病历信息后，系统会：
1. 自动检索中华护理学会团体标准网站（hltb.kxj.org.cn）获取相关护理操作PDF
2. 使用LLM对PDF进行结构化分析
3. 输出完整的护理监护计划HTML报告

## ✨ 主要功能

### 1. 患者信息管理
- 支持患者基本信息手工编辑
- 支持XLS/CSV表格上传批量更新
- 数据自动保存到浏览器本地存储

### 2. 护理操作标准检索
- 按诊断自动匹配相关护理操作标准
- **新增**：按护理操作名称精确搜索标准
- 支持从平台下载标准PDF并分析

### 3. 护理监护计划生成
- 3.1 护理监护医嘱单
- 3.2 护理巡查计划（含每日巡查登记、三测表、体温曲线图）
- **新增**：3.3 护理操作记录支持添加多个操作登记
- 3.4 护理监护风险因素清单（宽度自适应）
- 3.5 护理会诊
- 3.7 护理随访计划

### 4. 护理巡查与监测
- 一级护理：每小时至少一次巡查
- **新增**：异常处理字段支持用户编辑
- 生命体征（T/P/R/BP/SpO2）自动记录
- 三测数据自动同步到三测表和折线图

### 5. 量表评估
- Braden量表（压疮风险）
- Morse量表（跌倒风险）
- NRS量表（疼痛评估）
- NRS2002量表（营养风险）
- Barthel量表（日常生活活动能力）
- **支持多次记录**（操作前/后/入院/出院对比）

## 🚀 使用方法

### 方法一：直接使用（推荐）

1. 运行 `scripts/generate_html.py` 生成HTML文件：
```bash
python scripts/generate_html.py --diagnosis "气管切开" --patient_name "测试患者" --output "护理监护计划.html"
```

2. 在浏览器中打开生成的HTML文件
3. 在网页中填写患者信息、护理记录等
4. 点击"保存数据"按钮保存到本地

### 方法二：先检索标准再生成

1. 检索相关护理操作标准：
```bash
python scripts/fetch_standards.py --operation_name "气管切开" --output_dir "standards/"
```

2. 分析标准PDF：
```bash
python scripts/analyze_pdf.py --pdf_paths standards/*.pdf --standard_names "气管切开非机械通气患者气道护理" --output "analysis.json"
```

3. 根据分析结果生成HTML（需要修改generate_html.py以使用分析结果）

## 📁 文件说明

```
护理监护路径规划/
├── README.md              # 本说明文档
├── SKILL.md               # SKILL定义文件（触发词、版本等）
└── scripts/
    ├── generate_html.py   # HTML生成器（主程序）
    ├── fetch_standards.py # 标准检索与PDF下载
    └── analyze_pdf.py      # PDF结构化分析
```

### scripts/fetch_standards.py

**功能**：从中华护理学会团体标准网站检索和下载护理操作标准

**主要函数**：
- `fetch_all_standards()`: 爬取全部标准列表
- `match_standards(diagnosis, symptoms, all_standards)`: 根据诊断匹配标准
- **新增** `search_standards_by_operation_name(operation_name, all_standards)`: 按操作名称搜索标准

**使用示例**：
```bash
# 按诊断检索
python fetch_standards.py --diagnosis "气管切开" --output_dir "standards/"

# 按操作名称检索
python fetch_standards.py --operation_name "气道护理" --output_dir "standards/"

# 只列出不匹配
python fetch_standards.py --operation_name "氧气吸入" --list_only
```

### scripts/analyze_pdf.py

**功能**：对护理操作标准PDF进行结构化分析

**主要函数**：
- `extract_pdf_text(pdf_path)`: 提取PDF全文
- `rule_based_extract(text, standard_name)`: 基于规则提取
- `llm_structured_extract(text, standard_name, diagnosis)`: 使用LLM提取
- **新增** `analyze_multiple_standards(pdf_paths_or_texts, standard_names, diagnosis)`: 分析多个标准
- **新增** `extract_complications_detailed(text, standard_name)`: 详细提取并发症

**使用示例**：
```bash
# 分析单个PDF
python analyze_pdf.py --pdf_path "standards/std_3.pdf" --standard_name "气管切开非机械通气患者气道护理" --output "analysis.json"

# 分析多个PDF
python analyze_pdf.py --pdf_paths "std1.pdf" "std2.pdf" --standard_names "标准1" "标准2" --output_dir "analysis/"

# 详细提取并发症
python analyze_pdf.py --pdf_path "std_3.pdf" --standard_name "气管切开" --extract_complications --output "complications.json"
```

### scripts/generate_html.py

**功能**：生成完整的护理监护计划HTML报告

**主要函数**：
- `generate_operation_cards_v3()`: 生成护理操作卡片
- `generate_patrol_day_panels_v3()`: 生成每日巡查面板
- `generate_risk_cards()`: 生成风险因素清单
- `generate_scale_cards_v2()`: 生成量表卡片

**新增功能**：
- 患者信息编辑模态框
- XLS/CSV上传功能
- 护理操作记录支持添加多个
- 异常处理字段可编辑

## 🔄 更新日志

### v3.2.0 (2026-06-17)
- ✅ 支持患者基本信息手工编辑及XLS上传
- ✅ 删除3.6护理巡查记录汇总（已合并到3.2）
- ✅ 调整3.4风险因素清单宽度自适应
- ✅ 巡查频率异常处理支持用户编辑
- ✅ 支持添加多个3.3护理操作登记
- ✅ 增强fetch_standards.py支持按操作名称搜索
- ✅ 增强analyze_pdf.py支持多个标准分析
- ✅ 检查并修复量表错误代码

### v3.1.0 (2026-06-16)
- 风险因素清单改为列表式显示
- 合并每日巡查表与3.6巡查记录表
- 量表支持多次记录
- 修复JS代码语法错误

### v3.0.0 (2026-06-15)
- 宣教可单独打印PDF
- 操作记录推荐日期基于临床路径
- 巡查表多选+列宽可调

## 📝 注意事项

1. **网络连接**：检索标准需要访问 hltb.kxj.org.cn，确保网络连接正常
2. **LLM API**：如需使用LLM分析PDF，请设置环境变量 `OPENAI_API_KEY` 或 `DEEPSEEK_API_KEY`
3. **浏览器兼容**：生成的HTML文件支持现代浏览器（Chrome、Edge、Firefox）
4. **数据保存**：数据保存在浏览器本地存储，清除浏览器数据会丢失

## 📧 联系方式

如有问题或建议，请通过WorkBuddy联系。

---
**版本**：v3.2.0  
**最后更新**：2026-06-17  
**作者**：WorkBuddy AI
