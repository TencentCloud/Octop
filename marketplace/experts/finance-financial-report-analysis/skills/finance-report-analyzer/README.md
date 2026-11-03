# 📊 Finance Report Analyzer

从 Excel/PDF 财务数据自动生成交互式分析报告，支持 SVG 迷你趋势图和多格式输出。

[![ClawHub](https://img.shields.io/badge/ClawHub-finance--report--analyzer-blue)](https://clawhub.com)

## ✨ 功能特性

- 📥 **多源数据获取** — 支持飞书聊天文件附件、飞书云文档、本地 Excel/PDF
- 📈 **SVG 迷你趋势图** — 每个指标行内嵌 sparkline，一眼看清变化趋势
- 🔮 **预测值标识** — 盈利预测数据用 ⟡ 符号和黄色背景特别标注
- 📄 **多格式输出** — HTML（始终生成）+ PDF / DOCX / Markdown
- 🌐 **联网对标** — 可选搜索行业数据进行竞品对比
- 📱 **响应式设计** — 适配桌面和移动端，支持打印

## 🚀 快速开始

### 安装

```bash
# 作为 OpenClaw Skill 安装
clawhub install finance-report-analyzer

# 或直接克隆
git clone https://github.com/qiujiahong/finance-report-analyzer.git
```

### 使用

```bash
# 生成 HTML + PDF 报告（默认）
python3 scripts/generate_report.py 财务数据.xlsx -o pdf --company "公司名" --ticker "000001.SZ"

# 仅生成 HTML
python3 scripts/generate_report.py data.xlsx -o html --company "Company" --ticker "TICKER"

# 生成 Word 文档
python3 scripts/generate_report.py data.xlsx -o doc --output-dir ./reports

# 生成 Markdown
python3 scripts/generate_report.py data.xlsx -o md
```

### 参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `input` | 输入 Excel 文件路径 | (必填) |
| `-o, --output-format` | 输出格式：`pdf` / `doc` / `md` / `html` | `pdf` |
| `--output-dir` | 输出目录 | `.` |
| `--company` | 公司名称 | (空) |
| `--ticker` | 股票代码 | (空) |

### 格式转换依赖

| 输出格式 | 需要安装 |
|----------|----------|
| HTML | 无（内置） |
| PDF | `wkhtmltopdf` 或 `chromium` |
| DOCX | `pandoc` |
| Markdown | `pandoc` 或 `pip install markdownify` |

## 📋 报告内容

报告包含以下分析板块：

1. **核心摘要** — 营收、净利润、毛利率等关键指标卡片
2. **盈利能力分析** — 收入利润趋势 + 利润率指标（毛利率/净利率/ROE/ROA）
3. **资产负债分析** — 资产/负债/权益结构及杠杆率
4. **现金流分析** — 经营/投资/筹资现金流 + 自由现金流
5. **每股指标与效率** — EPS/BPS/资产周转率

每个指标行末尾附带 **SVG 迷你趋势图**：
- 🟢 实线 = 实际值
- 🟡 虚线 = 预测值
- ⟡ 标记 = 预测数据点

## 📁 项目结构

```
finance-report-analyzer/
├── SKILL.md                          # OpenClaw Skill 说明
├── README.md                         # 本文件
├── scripts/
│   └── generate_report.py            # 报告生成脚本
├── references/
│   └── metrics.md                    # 财务指标定义参考
└── assets/
    └── report-theme.css              # 报告主题样式
```

## 🔧 数据格式要求

输入 Excel 文件应包含：
- 第一列为指标名称（如"营业总收入"、"净利润"等）
- 后续列为各报告期数据
- 包含"报告期"行用于识别年报/季报/预测

支持的指标关键词（自动匹配）：

| 类别 | 关键词 |
|------|--------|
| 收入 | 营业总收入, 营业收入 |
| 利润 | 营业利润, 净利润, 归属母公司股东的净利润 |
| 资产 | 资产总计, 流动资产, 固定资产 |
| 负债 | 负债合计, 流动负债 |
| 现金流 | 经营活动现金净流量, 投资活动现金净流量 |
| 比率 | 销售毛利率, ROE, ROA, 资产负债率 |
| 每股 | EPS, 每股净资产 |

## 📝 License

MIT
