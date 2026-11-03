---
name: earnings-reader
description: A股财报研读助手 - 解读利润表/资产负债表/现金流量表
keywords:
  - 财报
  - 利润表
  - 资产负债表
  - 现金流
  - 估值
---

# Earnings Reader — 财报研读

## 数据获取
```bash
PYTHON=python3.12
EARNINGS=skills/akshare-finance/scripts/earnings.py

# 获取财报摘要
$PYTHON $EARNINGS report <股票代码>
# 例: $PYTHON $EARNINGS report 600519

# 查看业绩预告
$PYTHON $EARNINGS earnings

# 行业概览
$PYTHON $EARNINGS industry
```

## 财报分析框架

### 三表分析
1. **利润表**: 营收增速、毛利率、净利率趋势
2. **资产负债表**: 资产负债率、流动比率、商誉占比
3. **现金流量表**: 经营现金流/净利润比、自由现金流

### 关键指标
| 指标 | 健康范围 | 红灯 |
|------|----------|------|
| ROE | >15% | <8% |
| 净利率 | >10% | <3% |
| 资产负债率 | <60% | >80% |
| 营收增速 | >10% | <0% |
| 经营现金流/净利润 | >0.8 | <0.5 |

### 估值对比
- PE/PB 历史分位
- 同行业对比
- PEG 合理性

## 输出格式

### 个股财报速读
```
## {公司名} 财报速读

### 核心数据 (最近4个季度)
| 指标 | Q3 | Q2 | Q1 | 全年 |
|------|----|----|----|----|
| 营收 | xx亿 | xx亿 | xx亿 | xx亿 |
| 净利 | xx亿 | xx亿 | xx亿 | xx亿 |
| ROE  | xx% | xx% | xx% | xx% |

### 趋势判断
- 增长性: [加速/稳定/减速]
- 盈利质量: [优/良/中/差]
- 风险点: [具体描述]

### 投资观点 (仅供参考)
```

## 注意
- 财报数据来源: AKShare (东方财富)
- 仅用于研究分析，不构成投资建议
- Macro agent 关注行业趋势，个股交易建议由 trading agent 负责
