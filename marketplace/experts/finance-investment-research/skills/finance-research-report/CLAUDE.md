# finance-research-report

## 项目简介
A股每周金融投研报告自动生成工具（OpenClaw / ClawHub 技能）。输出专业 PDF 研报，参考券商研报格式，集成日频短期技术分析框架。

## 项目结构
```
finance-research-report/
├── SKILL.md               # OpenClaw 技能定义（主入口）
├── README.md              # 技能说明文档
├── _meta.json             # ClawHub 发布元数据
├── CLAUDE.md              # 项目说明
├── requirements.txt       # Python 依赖
├── sample.pdf             # 参考研报模板（西南证券）
├── scripts/
│   ├── generate_weekly_report.py  # 主入口脚本
│   ├── data_fetcher.py            # 数据获取模块（AKShare / 新浪 / 东方财富）
│   ├── technical_analysis.py      # 技术分析模块
│   ├── chart_generator.py         # matplotlib 图表生成模块
│   └── report_generator.py        # PDF 报告生成模块（HTML+CSS → weasyprint）
└── output/                # 生成的 PDF 报告输出目录
```

## 快速使用

### 命令行方式
```bash
cd scripts && python3 generate_weekly_report.py --stocks 000001,600519,000858
```

### OpenClaw 技能
```
/finance-research-report 000001,600519,000858
```

## 依赖
- Python 3.10+
- akshare, pandas, numpy, weasyprint, matplotlib
- 系统依赖：pango (`brew install pango`), ghostscript (`brew install ghostscript`)

## 输出格式
PDF（A4 页面），样式参考西南证券研报，包含：
- 封面（投资要点、信号统计）
- 目录
- 市场概览（指数、情绪、北向资金、宏观要闻）
- 个股技术分析卡片（含图表）
- 交易信号汇总
- 风险评估与仓位建议
- 风险提示与免责声明

## 技术指标体系
- 均线：MA5/MA10/MA20 + 排列判断
- 动量：RSI(14), MACD(12,26,9), KDJ(9,3,3)
- 波动率：ATR(14), 标准差(20日)
- 量价：量比(5日), 换手率
- 信号：金叉/死叉、量价配合、超买超卖
- 风控：止损止盈、风险评分、仓位系数
