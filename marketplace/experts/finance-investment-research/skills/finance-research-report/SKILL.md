---
name: finance-research-report
description: "A股每周金融投研报告生成器 — 基于 AKShare / 新浪财经 / 东方财富数据源，自动生成包含技术分析、交易信号、风险评估的专业 PDF 研报。Triggers: '生成周报', '金融报告', '投研报告', '股票分析', 'A股研报'。"
user-invocable: true
argument-hint: "股票代码(逗号分隔) [--date YYYY-MM-DD] [--author 名字]"
metadata: {"clawdbot":{"emoji":"📊","requires":{"bins":["python3"]},"os":["darwin","linux"],"files":["scripts/generate_weekly_report.py","scripts/data_fetcher.py","scripts/technical_analysis.py","scripts/chart_generator.py","scripts/report_generator.py"]}}
---

# 每周金融投研报告生成器

生成专业券商研报风格的 A 股投研 PDF 报告，包含技术分析、交易信号、风险评估。

## Quick Start

**生成报告（默认跳过全市场统计，更快）：**
```bash
pip3 install -r {baseDir}/requirements.txt
python3 {baseDir}/scripts/generate_weekly_report.py --stocks 000001,600519,000858 --skip-breadth
```

**完整报告（含全市场涨跌统计，约多1分钟）：**
```bash
python3 {baseDir}/scripts/generate_weekly_report.py --stocks 000001,600519,000858
```

**指定日期和作者：**
```bash
python3 {baseDir}/scripts/generate_weekly_report.py --stocks 600519 --date 2026-03-14 --author 投研团队
```

---

## How It Works

`generate_weekly_report.py` 脚本自动完成以下步骤：

1. **获取主要指数数据** — 上证指数、深证成指、沪深300、创业板指
2. **获取市场情绪** — 全市场涨跌家数、涨停跌停统计（可选）
3. **获取北向资金** — 本周净流入/净流出
4. **个股技术分析** — 均线、RSI、MACD、KDJ、ATR、量价等
5. **获取持仓新闻** — 个股相关新闻 + 全球宏观要闻
6. **生成 PDF 报告** — HTML+CSS → weasyprint → Ghostscript 优化

### Analysis Framework

技术指标体系参考 `{baseDir}/scripts/technical_analysis.py`：

```
标的: 贵州茅台 (600519)
收盘价: ¥1,856.00  (+2.3%)
趋势: 多头排列 (MA5 > MA10 > MA20)

技术指标:
  RSI(14): 62.5 — 正常区间
  MACD: 金叉，柱状翻红
  KDJ: K=68, D=55, J=94

交易信号:
  🟢 买入信号 x3  |  🔴 卖出信号 x0
  信号强度: 强

风险评估:
  风险评分: 4/10
  止损位: ¥1,812.00
  止盈位: ¥1,920.00
  建议仓位: 60%
```

---

## 报告内容结构

生成的 PDF 报告（A4 页面）包含以下章节：

1. **封面与投资要点** — 核心观点、看多/看空/中性统计、数据来源
2. **目录**
3. **市场概览** — 大盘指数、涨跌家数、北向资金、持仓资讯、宏观要闻
4. **个股技术分析** — 含价格走势图、MACD+RSI 图表
5. **交易信号汇总** — 买入/卖出信号、信号强度
6. **风险评估与仓位建议** — 风险评分、止损止盈、仓位系数
7. **风险提示与免责声明**

---

## 技术指标体系

| 类别 | 指标 | 说明 |
|------|------|------|
| 均线 | MA5, MA10, MA20 | 趋势与排列判断 |
| 动量 | RSI(14) | 相对强弱，超买>80 / 超卖<20 |
| 动量 | MACD(12,26,9) | 趋势强度，金叉/死叉 |
| 动量 | KDJ(9,3,3) | 超买超卖判断 |
| 波动率 | ATR(14) | 真实波动幅度 |
| 波动率 | 标准差(20日) | 价格离散度 |
| 量价 | 量比(5日) | 成交活跃度 |
| 量价 | 换手率 | 交易活跃程度 |

### 交易信号

- **买入信号**：MA5 金叉 MA10、价格突破 MA10、量价齐升、RSI 50-70、MACD 翻红
- **卖出信号**：MA5 死叉 MA10、放量跌破 MA5、RSI>80、5日涨幅>15%、KDJ 超买

### 风险控制

- 止损位：min(前日低点×0.995, MA10×0.99, 入场价×0.95)
- 止盈位：当前价 + ATR × 2
- 仓位系数：(10 - 风险评分) / 10

---

## 数据来源

数据通过 AKShare 开源接口获取：

| 数据类型 | 来源 |
|----------|------|
| A 股日线行情（前复权） | 新浪财经 |
| 主要指数日线数据 | 新浪财经 |
| 个股实时行情与名称 | 新浪财经 |
| 全市场涨跌统计 | 新浪财经 |
| 北向资金数据 | 东方财富 |
| 个股相关新闻 | 东方财富 |
| 全球财经要闻 | 东方财富 |

---

## 系统依赖

- `python3` on PATH
- `pango`（macOS: `brew install pango`）— weasyprint 渲染依赖
- `ghostscript`（macOS: `brew install ghostscript`）— PDF 兼容性优化
- Python 包：`pip3 install -r {baseDir}/requirements.txt`

---

## Output Format Rules

- 输出为 PDF 文件，保存在 `output/` 目录
- 文件名格式：`周报_YYYY-MM-DD.pdf`
- 样式参考券商研报（红色主题、专业表格、技术图表）
- 每份报告末尾附风险提示与免责声明

---

## Limitations & Notes

- 数据通过公开接口获取，部分数据可能有 15 分钟延迟
- 行业板块资金流向受网络环境限制可能不可用
- 本技能不执行交易操作，所有建议仅供参考
- 全市场涨跌统计（`--skip-breadth` 可跳过）约需 1 分钟
- 需要系统安装 pango 和 ghostscript

---

## Security & Privacy

- **无需 API Key**：所有数据通过 AKShare 公开接口获取
- **本地生成**：PDF 报告在本地生成，不上传至任何服务器
- **仅供参考**：交易信号为技术分析结果，不构成投资建议

*免责声明：本报告基于公开市场数据的技术分析，不构成任何投资建议。投资有风险，入市需谨慎。*
