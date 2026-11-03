# JoinQuant 聚宽量化 Skill

[![Version](https://img.shields.io/badge/version-1.2.0-blue.svg)](https://www.joinquant.com)
[![License](https://img.shields.io/badge/license-Apache--2.0-green.svg)](LICENSE)
[![ClawHub](https://img.shields.io/badge/ClawHub-BossQuant-purple.svg)](https://clawhub.com)

聚宽量化交易平台，提供 A 股数据查询、事件驱动策略回测、模拟实盘。

## ✨ 特性

- ☁️ **云端策略运行** - 无需本地部署，云端回测与模拟交易
- 🆓 **免费数据额度** - 注册即享免费数据查询额度
- ⚡ **事件驱动框架** - initialize / handle_data 标准策略结构
- 💰 **财务数据查询** - 完整的 A 股财务报表与估值数据

## 📥 安装

```bash
pip install jqdatasdk
```

## 🔑 配置

1. 访问 [聚宽官网](https://www.joinquant.com) 注册账号
2. 配置认证信息：

```bash
export JQ_USERNAME="your_username"
export JQ_PASSWORD="your_password"
```

## 🚀 快速开始

```python
import jqdatasdk as jq

# 认证
jq.auth("your_username", "your_password")

# 获取行情数据
df = jq.get_price("000001.XSHE", start_date="2024-01-01", end_date="2024-12-31", frequency="daily")
print(df.head())

# 获取指数成分股
stocks = jq.get_index_stocks("000300.XSHG")
print(stocks[:10])
```

## 📊 支持的数据类型

| 类别 | 说明 | 示例接口 |
|------|------|----------|
| 行情数据 | 日/分钟行情 | `get_price()` |
| 财务数据 | 财务报表 | `get_fundamentals()` |
| 指数成分 | 指数成分股 | `get_index_stocks()` |
| 行业分类 | 行业板块 | `get_industry_stocks()` |
| 概念板块 | 概念分类 | `get_concept_stocks()` |
| 估值数据 | PE/PB等 | `get_valuation()` |
| 交易日历 | 交易日查询 | `get_trade_days()` |

## 📖 策略回测示例

```python
def initialize(context):
    g.security = "000001.XSHE"
    set_benchmark("000300.XSHG")

def handle_data(context, data):
    security = g.security
    current_price = data[security].close
    avg_price = data[security].mavg(20, 'close')

    if current_price > avg_price:
        order_target_value(security, context.portfolio.total_value * 0.9)
    else:
        order_target_value(security, 0)
```

## 📄 许可证

Apache License 2.0

## 📊 更新日志

### v1.2.0 (2026-03-23)
- 🎉 增加更丰富的AI Agent演示和高阶使用指南
- 🔄 更新版本号并清理失效链接


### v1.1.0 (2026-03-15)
- 🎉 初始版本发布
- 📊 支持聚宽数据查询与策略回测

---

## 🤝 社区与支持

- **维护者**：大佬量化 (Boss Quant)
- **主页**：https://www.joinquant.com
- **ClawHub**：https://clawhub.com
