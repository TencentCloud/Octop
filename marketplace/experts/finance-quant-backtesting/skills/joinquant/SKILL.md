---
name: joinquant
description: 聚宽量化交易平台 - 提供A股、期货、基金数据查询，事件驱动策略回测，支持在线研究与模拟实盘。
version: 1.1.0
homepage: https://www.joinquant.com
metadata: {"clawdbot":{"emoji":"🔬","requires":{"bins":["python3"]}}}
---

# 聚宽量化（JoinQuant）

[聚宽](https://www.joinquant.com) 是中国领先的在线量化交易平台，提供免费数据查询、策略回测和模拟交易。支持A股、期货、基金、指数等品种，采用事件驱动的Python策略框架。

> ⚠️ **需要在 https://www.joinquant.com 注册账号**。策略运行在聚宽云端，也可以通过JQData在本地获取数据。

## 安装 (Local Data SDK)

```bash
pip install jqdatasdk
```

## 本地数据认证

```python
import jqdatasdk as jq

# 使用聚宽账号登录（每日免费数据额度）
jq.auth('your_username', 'your_password')

# 查看剩余数据额度
print(jq.get_query_count())
```

## 策略程序结构（在线回测）

聚宽策略采用事件驱动架构，在平台网页界面编写和运行：

```python
def initialize(context):
    """初始化函数 — 策略启动时调用一次"""
    # 设置基准指数（沪深300）
    set_benchmark('000300.XSHG')
    # 设置手续费 and slippage
    set_order_cost(OrderCost(open_tax=0, close_tax=0.001,
                              open_commission=0.0003, close_commission=0.0003,
                              min_commission=5), type='stock')
    set_slippage(FixedSlippage(0.02))
    # 设置股票池
    g.security = '000001.XSHE'

def handle_data(context, data):
    """盘中事件 — 每个交易频率触发一次"""
    security = g.security
    # 获取最近20天收盘价
    close_data = attribute_history(security, 20, '1d', ['close'])
    ma5 = close_data['close'][-5:].mean()
    ma20 = close_data['close'].mean()

    # 金叉 — buy
    if ma5 > ma20:
        order_target_value(security, context.portfolio.total_value * 0.9)
    # 死叉 — sell
    elif ma5 < ma20:
        order_target(security, 0)
```

---

## 股票代码格式

| 市场 | 后缀 | 示例 |
|---|---|---|
| 上海A股 | `.XSHG` | `600000.XSHG`（浦发银行） |
| 深圳A股 | `.XSHE` | `000001.XSHE`（平安银行） |
| 指数 | `.XSHG/.XSHE` | `000300.XSHG`（沪深300） |
| 期货 | `.XDCE/.XZCE/.XSGE/.CCFX` | `IF2401.CCFX`（股指期货） |
| 基金 | `.XSHG/.XSHE` | `510300.XSHG`（沪深300ETF） |

---

## 数据查询函数（JQData）

### 行情数据

```python
import jqdatasdk as jq

# 获取日K线数据
df = jq.get_price(
    '000001.XSHE',              # 股票代码
    start_date='2024-01-01',    # 开始日期
    end_date='2024-06-30',      # 结束日期
    frequency='daily',          # 频率: daily(日), minute(分钟), 1m, 5m, 15m, 30m, 60m, 120m
    fields=['open', 'close', 'high', 'low', 'volume', 'money'],
    skip_paused=True,           # 跳过停牌日
    fq='pre',                   # 复权: None(不复权), 'pre'(前复权), 'post'(后复权)
    panel=False                 # False返回DataFrame
)

# 获取多只股票数据
df = jq.get_price(['000001.XSHE', '600000.XSHG'],
                   start_date='2024-01-01', end_date='2024-06-30',
                   frequency='daily', fields=['close'], panel=False)

# 获取分钟级数据
df = jq.get_price('000001.XSHE', start_date='2024-06-01 09:30:00',
                   end_date='2024-06-01 15:00:00', frequency='1m')
```

### 获取最近N条数据

```python
# 获取最近20个交易日的收盘价
df = jq.get_bars('000001.XSHE', count=20, unit='1d', fields=['close', 'volume'])
```


### 财务数据

```python
# 查询财务指标
df = jq.get_fundamentals(
    jq.query(
        jq.valuation.code,
        jq.valuation.market_cap,          # 总市值（亿元）
        jq.valuation.pe_ratio,            # 市盈率
        jq.valuation.pb_ratio,            # 市净率
        jq.valuation.turnover_ratio,      # 换手率
        jq.indicator.roe,                 # 净资产收益率（ROE）
        jq.indicator.eps,                 # 每股收益
        jq.indicator.revenue,             # 营业收入
        jq.indicator.net_profit,          # 净利润
    ).filter(
        jq.valuation.pe_ratio > 0,        # 排除亏损股
        jq.valuation.pe_ratio < 30,       # PE小于30
        jq.valuation.market_cap > 100     # 市值大于100亿元
    ).order_by(
        jq.valuation.market_cap.desc()    # 按市值降序排列
    ).limit(50),                          # 取前50
    date='2024-06-30'
)
print(df)
```

### 指数成分股

```python
# 获取沪深300成分股
stocks = jq.get_index_stocks('000300.XSHG')
print(f'沪深300共 {len(stocks)} 只成分股')

# 获取行业成分股
stocks = jq.get_industry_stocks('I64')  # 银行业
```

### 行业分类

```python
# 获取股票所属行业
industry = jq.get_industry('000001.XSHE')
print(industry)

# 获取申万一级行业列表
industries = jq.get_industries(name='sw_l1')
print(industries)
```

### 交易日历

```python
# 获取交易日列表
days = jq.get_trade_days(start_date='2024-01-01', end_date='2024-06-30')

# 获取全部交易日
all_days = jq.get_all_trade_days()
```

### 股票基本信息

```python
# 获取全部A股上市公司
stocks = jq.get_all_securities(types=['stock'], date='2024-06-30')
print(f'A股总数: {len(stocks)}')

# 获取单只股票信息
info = jq.get_security_info('000001.XSHE')
print(f'名称: {info.display_name}, 上市日期: {info.start_date}')

# 获取ST股票
st_stocks = jq.get_extras('is_st', ['000001.XSHE'], start_date='2024-01-01', end_date='2024-06-30')
```

### 龙虎榜数据

```python
# 获取龙虎榜数据
df = jq.get_billboard_list(stock_list=None, start_date='2024-06-01', end_date='2024-06-30')
print(df.head())
```

### 融资融券数据

```python
# 获取融资融券汇总数据
df = jq.get_mtss('000001.XSHE', start_date='2024-01-01', end_date='2024-06-30')
print(df.head())
```

---

## 交易函数（在线策略）

### 按数量下单

```python
# 买入100股
order('000001.XSHE', 100)

# 卖出200股
order('000001.XSHE', -200)

# 限价买入
order('000001.XSHE', 100, LimitOrderStyle(11.50))

# 市价买入
order('000001.XSHE', 100, MarketOrderStyle())
```

### 调仓到目标

```python
# 调仓到目标数量
order_target('000001.XSHE', 1000)     # Adjust to hold 1000 shares
order_target('000001.XSHE', 0)        # Liquidate position

# 调仓到目标金额
order_target_value('000001.XSHE', 100000)  # Adjust to 100,000 CNY market value

# 调仓到目标比例（占总资产）
order_target_percent('000001.XSHE', 0.3)   # Adjust to 30% of total assets
```

### 撤单

```python
# 获取未成交订单
open_orders = get_open_orders()
# 撤销指定订单
cancel_order(order_id)
```


---

## 账户与持仓查询

```python
def handle_data(context, data):
    # 账户信息rmation
    cash = context.portfolio.available_cash       # 可用资金
    total = context.portfolio.total_value          # 总资产
    positions_value = context.portfolio.positions_value  # 持仓市值

    # 查询持仓
    for stock, pos in context.portfolio.positions.items():
        print(f'{stock}: Quantity={pos.total_amount}, '
              f'Sellable={pos.closeable_amount}, '
              f'Cost={pos.avg_cost:.2f}, '
              f'Current price={pos.price:.2f}, '
              f'Market value={pos.value:.2f}')
```

---

## 定时任务

```python
def initialize(context):
    # 每日盘前执行
    run_daily(before_market_open, time='before_open')
    # 每日指定时间执行
    run_daily(market_open, time='09:35')
    run_daily(afternoon_check, time='14:50')
    # 每周执行
    run_weekly(weekly_rebalance, weekday=1, time='09:35')  # 每周一
    # 每月执行
    run_monthly(monthly_rebalance, monthday=1, time='09:35')  # 每月1号

def before_market_open(context):
    log.info('Pre-market preparation')

def market_open(context):
    log.info('Market open trading')
```

---

## 风险管理

```python
def initialize(context):
    g.security = '000001.XSHE'
    set_benchmark('000300.XSHG')

def handle_data(context, data):
    security = g.security
    # 获取当前价格
    current_price = data[security].close

    # 检查持仓盈亏
    if security in context.portfolio.positions:
        pos = context.portfolio.positions[security]
        cost = pos.avg_cost
        pnl_ratio = (current_price - cost) / cost

        # 盈利10%止盈
        if pnl_ratio >= 0.10:
            order_target(security, 0)
            log.info(f'Take profit: {security} gain {pnl_ratio:.2%}')
        # 亏损5%止损
        elif pnl_ratio <= -0.05:
            order_target(security, 0)
            log.info(f'Stop loss: {security} loss {pnl_ratio:.2%}')
```

---

## 完整示例 — Multi-Factor Stock Selection Strategy

```python
def initialize(context):
    set_benchmark('000300.XSHG')
    set_order_cost(OrderCost(open_tax=0, close_tax=0.001,
                              open_commission=0.0003, close_commission=0.0003,
                              min_commission=5), type='stock')
    g.hold_num = 10  # 持股数量
    # 每月第一个交易日调仓
    run_monthly(rebalance, monthday=1, time='09:35')

def rebalance(context):
    # 多因子选股
    df = get_fundamentals(
        query(
            valuation.code,
            valuation.pe_ratio,
            valuation.pb_ratio,
            valuation.market_cap,
            indicator.roe,
        ).filter(
            valuation.pe_ratio > 5,
            valuation.pe_ratio < 25,
            valuation.pb_ratio > 0.5,
            valuation.pb_ratio < 5,
            indicator.roe > 10,
            valuation.market_cap > 100,
        ).order_by(
            valuation.pe_ratio.asc()
        ).limit(g.hold_num)
    )

    target_stocks = list(df['code'])
    log.info(f'Selected {len(target_stocks)} stocks')

    # 卖出不在目标列表中的股票
    for stock in context.portfolio.positions:
        if stock not in target_stocks:
            order_target(stock, 0)

    # 等权重买入目标股票
    if target_stocks:
        per_value = context.portfolio.total_value * 0.95 / len(target_stocks)
        for stock in target_stocks:
            order_target_value(stock, per_value)

def handle_data(context, data):
    pass
```


---

## 进阶示例

### 行业轮动策略

```python
def initialize(context):
    set_benchmark('000300.XSHG')
    g.hold_num = 5
    g.industry_etfs = {
        '512010.XSHG': '医药ETF',
        '512880.XSHG': '证券ETF',
        '512800.XSHG': '银行ETF',
        '515030.XSHG': '新能源车ETF',
        '159995.XSHE': '芯片ETF',
        '512690.XSHG': '白酒ETF',
        '510300.XSHG': '沪深300ETF',
        '159915.XSHE': '创业板ETF',
    }
    run_monthly(rebalance, monthday=1, time='09:35')

def rebalance(context):
    """按20日动量排序，选取最强的前N只ETF"""
    momentum = {}
    for etf, name in g.industry_etfs.items():
        df = attribute_history(etf, 20, '1d', ['close'])
        if len(df) >= 20:
            ret = (df['close'].iloc[-1] / df['close'].iloc[0]) - 1
            momentum[etf] = ret

    # 按动量排序
    sorted_etfs = sorted(momentum.items(), key=lambda x: x[1], reverse=True)
    targets = [etf for etf, _ in sorted_etfs[:g.hold_num]]
    log.info(f'This month selected: {[g.industry_etfs[e] for e in targets]}')

    # 卖出不在目标列表中的持仓
    for stock in context.portfolio.positions:
        if stock not in targets:
            order_target(stock, 0)

    # 等权重买入
    per_value = context.portfolio.total_value * 0.95 / len(targets)
    for etf in targets:
        order_target_value(etf, per_value)

def handle_data(context, data):
    pass
```

### 数据研究 — 全市场财务筛选

```python
import jqdatasdk as jq
import pandas as pd

jq.auth('your_username', 'your_password')

# 全市场财务筛选：低PE + 高ROE + 高成长
df = jq.get_fundamentals(
    jq.query(
        jq.valuation.code,
        jq.valuation.pe_ratio,
        jq.valuation.pb_ratio,
        jq.valuation.market_cap,
        jq.indicator.roe,
        jq.indicator.inc_revenue_year_on_year,    # 营收同比增长率
        jq.indicator.inc_net_profit_year_on_year,  # 净利润同比增长率
    ).filter(
        jq.valuation.pe_ratio > 5,
        jq.valuation.pe_ratio < 20,
        jq.indicator.roe > 15,
        jq.indicator.inc_revenue_year_on_year > 10,
        jq.indicator.inc_net_profit_year_on_year > 10,
        jq.valuation.market_cap > 50,
    ).order_by(
        jq.indicator.roe.desc()
    ).limit(30),
    date='2024-06-30'
)

print(f'筛选出 {len(df)} 只股票:')
print(df.to_string(index=False))

# 导出为CSV
df.to_csv('selected_stocks.csv', index=False)
```

---

## 使用技巧

- 聚宽策略运行在云端 — 无需本地安装交易环境。
- JQData本地SDK有免费每日数据额度，适合数据研究。
- 在策略中使用 `attribute_history` 获取历史数据；在研究环境中使用 `get_price`。
- 回测时使用 `set_order_cost` 设置真实手续费 — 默认手续费为0。
- `g` 对象用于在函数之间持久化变量（类似Ptrade）。
- 文档：https://www.joinquant.com/help/api/help

---

---

## 🤖 AI Agent 高阶使用指南

对于 AI Agent，在使用该量化/数据工具时应遵循以下高阶策略和最佳实践，以确保任务的高效完成：

### 1. 数据校验与错误处理
在获取数据或执行操作后，AI 应当主动检查返回的结果格式是否符合预期，以及是否存在缺失值（NaN）或空数据。
* **示例策略**：在通过 API 获取数据框（DataFrame）后，使用 `if df.empty:` 进行校验；捕获 `Exception` 以防网络或接口错误导致进程崩溃。

### 2. 多步组合分析
AI 经常需要进行宏观经济分析或跨市场对比。应善于将当前接口与其他数据源或工具组合使用。
* **示例策略**：先获取板块或指数的宏观数据，再筛选成分股，最后对具体标的进行深入的财务或技术面分析，形成完整的决策链条。

### 3. 构建动态监控与日志
对于交易和策略类任务，AI 可以定期拉取数据并建立监控机制。
* **示例策略**：使用循环或定时任务检查特定标的的异动（如涨跌停、放量），并在发现满足条件的信号时输出结构化日志或触发预警。

---

## 社区与支持

由 **大佬量化** 维护 — 量化交易教学与策略研发团队。

微信客服: **bossquant1** · [Bilibili](https://space.bilibili.com/48693330) · 搜索 **大佬量化** — 微信公众号 / Bilibili / 抖音
