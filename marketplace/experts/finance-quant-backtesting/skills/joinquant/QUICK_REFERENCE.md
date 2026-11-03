# JoinQuant 聚宽 快速参考

本文档提供最常用的聚宽 API 接口和代码示例。

**维护者**: 大佬量化 (Boss Quant)

## 认证登录

```python
import jqdatasdk as jq

jq.auth("your_username", "your_password")

# 查询剩余额度
print(jq.get_query_count())
```

## 行情数据

```python
# 单只股票日线
df = jq.get_price("000001.XSHE", start_date="2024-01-01", end_date="2024-12-31", frequency="daily")

# 多只股票
df = jq.get_price(["000001.XSHE", "600000.XSHG"], start_date="2024-01-01", end_date="2024-12-31", frequency="daily", panel=False)

# 分钟数据
df = jq.get_price("000001.XSHE", start_date="2024-12-30", end_date="2024-12-31", frequency="1m")
```

## 财务数据

```python
# 查询财务数据
q = jq.query(jq.valuation).filter(jq.valuation.code == "000001.XSHE")
df = jq.get_fundamentals(q, date="2024-12-31")

# 查询多只股票估值
q = jq.query(
    jq.valuation.code,
    jq.valuation.market_cap,
    jq.valuation.pe_ratio,
    jq.valuation.pb_ratio
).filter(jq.valuation.code.in_(["000001.XSHE", "600000.XSHG"]))
df = jq.get_fundamentals(q, date="2024-12-31")
```

## 指数成分股

```python
# 沪深300成分股
stocks = jq.get_index_stocks("000300.XSHG")

# 中证500成分股
stocks = jq.get_index_stocks("000905.XSHG")

# 上证50成分股
stocks = jq.get_index_stocks("000016.XSHG")
```

## 策略框架 - 下单

```python
# 按股数下单
order("000001.XSHE", 100)       # 买入100股
order("000001.XSHE", -100)      # 卖出100股

# 按目标金额下单
order_target_value("000001.XSHE", 50000)  # 调整到5万元

# 按目标比例下单
order_target_percent("000001.XSHE", 0.3)  # 调整到30%仓位
```

## 账户信息

```python
# 在策略中访问
def handle_data(context, data):
    # 总资产
    total = context.portfolio.total_value
    # 可用资金
    cash = context.portfolio.available_cash
    # 持仓
    positions = context.portfolio.positions
    for stock, pos in positions.items():
        print(f"{stock}: 数量={pos.total_amount}, 成本={pos.avg_cost}")
```

## 代码格式说明

- 上交所股票：`600000.XSHG`
- 深交所股票：`000001.XSHE`
- 上交所指数：`000300.XSHG`

## 更多资源

- [聚宽官方文档](https://www.joinquant.com/help/api/help)
- [聚宽社区](https://www.joinquant.com/community)
