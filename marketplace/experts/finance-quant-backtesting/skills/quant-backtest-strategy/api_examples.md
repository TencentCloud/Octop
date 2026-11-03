# OneQuant 4.0 API 调用示例

> 服务地址：`http://127.0.0.1:5001`（默认端口5001）

---

## 目录

1. [大盘分析](#1-大盘分析)
2. [K线数据](#2-k线数据)
3. [技术信号](#3-技术信号)
4. [量化选股](#4-量化选股)
5. [策略回测](#5-策略回测)
6. [模拟交易](#6-模拟交易)
7. [风控管理](#7-风控管理)
8. [策略管理](#8-策略管理)
9. [错误码说明](#9-错误码说明)

---

## 1. 大盘分析

### GET `/api/market/overview`

三大指数行情卡片（上证/深证/创业板）。

**请求示例：**
```bash
curl "http://127.0.0.1:5001/api/market/overview"
```

**响应示例（成功）：**
```json
{
  "success": true,
  "data": {
    "sh_index": {"code": "000001", "name": "上证指数", "price": 3120.45, "change": 15.20, "change_pct": 0.49},
    "sz_index": {"code": "399001", "name": "深证成指", "price": 9456.78, "change": -23.10, "change_pct": -0.24},
    "cyb_index": {"code": "399006", "name": "创业板指", "price": 1823.56, "change": 8.90, "change_pct": 0.49}
  },
  "message": "ok",
  "timestamp": "2026-06-13T15:30:00"
}
```

**注意事项：**
- 非交易时段返回最新收盘数据
- 数据来源：AkShare（默认）/ JQData / RQData

---

## 2. K线数据

### GET `/api/market/kline`

获取指定股票的K线数据。

**请求参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `symbol` | string | 是 | 6位股票代码（如 `600519`） |
| `frequency` | string | 否 | 周期：`1min`/`5min`/`15min`/`30min`/`60min`/`120min`/`daily`/`weekly`/`monthly`，默认 `daily` |

**请求示例：**
```bash
# 日线
curl "http://127.0.0.1:5001/api/market/kline?symbol=600519&frequency=daily"

# 5分钟线
curl "http://127.0.0.1:5001/api/market/kline?symbol=600519&frequency=5min"
```

**Python 示例：**
```python
import requests

BASE = "http://127.0.0.1:5001"
r = requests.get(f"{BASE}/api/market/kline", params={
    "symbol": "600519",
    "frequency": "daily"
})
data = r.json()
if data["success"]:
    klines = data["data"]["klines"]
    for k in klines[:3]:
        print(f"{k['date']} 收盘:{k['close']} 成交量:{k['volume']}")
```

**响应示例（成功）：**
```json
{
  "success": true,
  "data": {
    "code": "600519",
    "name": "贵州茅台",
    "frequency": "daily",
    "klines": [
      {"date": "2026-06-10", "open": 1580.00, "close": 1592.00, "high": 1600.00, "low": 1575.00, "volume": 1234567, "amount": 1956000000},
      {"date": "2026-06-11", "open": 1592.00, "close": 1605.00, "high": 1610.00, "low": 1588.00, "volume": 987654, "amount": 1582000000}
    ]
  },
  "message": "ok"
}
```

**错误响应：**
```json
{
  "success": false,
  "data": null,
  "message": "股票代码格式错误，需要6位数字代码（如 600519）"
}
```

---

## 3. 技术信号

### GET `/api/signal/technical`

获取MACD/KDJ/RSI技术指标和买卖点信号。

**请求参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `symbol` | string | 是 | 6位股票代码 |
| `frequency` | string | 否 | 周期，默认 `daily` |

**请求示例：**
```bash
curl "http://127.0.0.1:5001/api/signal/technical?symbol=600519&frequency=daily"
```

**响应示例（成功）：**
```json
{
  "success": true,
  "data": {
    "code": "600519",
    "name": "贵州茅台",
    "macd": {
      "dif": 12.34,
      "dea": 10.56,
      "macd": 1.78,
      "signal": "golden_cross",
      "signal_desc": "MACD金叉，短期买入信号"
    },
    "kdj": {
      "k": 65.2,
      "d": 58.9,
      "j": 77.8,
      "signal": "neutral"
    },
    "rsi": {
      "rsi_6": 55.3,
      "rsi_12": 52.1,
      "signal": "neutral"
    }
  }
}
```

---

## 4. 量化选股

### GET `/api/selection/list`

条件选股结果。

**请求参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `strategy` | string | 是 | 策略名：`limit_up`（涨停板）/ `ma_golden`（均线金叉）/ `rsi_oversold`（RSI超卖） |

**请求示例：**
```bash
# 涨停板选股
curl "http://127.0.0.1:5001/api/selection/list?strategy=limit_up"

# 均线金叉选股
curl "http://127.0.0.1:5001/api/selection/list?strategy=ma_golden"
```

**响应示例（成功）：**
```json
{
  "success": true,
  "data": {
    "strategy": "limit_up",
    "count": 2,
    "stocks": [
      {"code": "000858", "name": "五粮液", "price": 125.60, "limit_up_time": "09:31:02", "bid_volume": 1234567},
      {"code": "600519", "name": "贵州茅台", "price": 1605.00, "limit_up_time": "09:32:15", "bid_volume": 98765}
    ]
  }
}
```

**注意：** 非交易时段返回空列表（`"count": 0, "stocks": []`），属于正常行为。

---

## 5. 策略回测

### GET `/api/backtest/ma`

MA均线金叉死叉策略回测。

**请求参数：**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `symbol` | string | 是 | — | 6位股票代码 |
| `short` | int | 否 | 5 | 短期均线周期 |
| `long` | int | 否 | 20 | 长期均线周期 |
| `start_date` | string | 否 | 1年前 | 回测开始日期 `YYYY-MM-DD` |
| `end_date` | string | 否 | 今天 | 回测结束日期 `YYYY-MM-DD` |

**请求示例：**
```bash
curl "http://127.0.0.1:5001/api/backtest/ma?symbol=600519&short=5&long=20&start_date=2024-01-01&end_date=2024-12-31"
```

**响应示例（成功）：**
```json
{
  "success": true,
  "data": {
    "symbol": "600519",
    "name": "贵州茅台",
    "strategy": "MA(5,20)金叉死叉",
    "params": {"short": 5, "long": 20},
    "backtest_period": {"start": "2024-01-01", "end": "2024-12-31"},
    "performance": {
      "total_return": 15.23,
      "annual_return": 8.76,
      "max_drawdown": -12.45,
      "sharpe_ratio": 0.85,
      "win_rate": 52.3,
      "trade_count": 23
    },
    "trades": [
      {"date": "2024-03-15", "action": "buy", "price": 1520.00, "volume": 100},
      {"date": "2024-04-20", "action": "sell", "price": 1580.00, "volume": 100, "pnl": 6000.00, "pnl_pct": 3.95}
    ],
    "equity_curve": [
      {"date": "2024-01-01", "equity": 100000},
      {"date": "2024-12-31", "equity": 115230}
    ]
  },
  "message": "回测完成",
  "disclaimer": "过去表现不代表未来收益，本结果仅供参考，不构成投资建议"
}
```

**注意：** 回测结果**不包含交易成本**（佣金、印花税、滑点），实盘需自行折算。

---

## 6. 模拟交易

### POST `/api/trade/buy`

限价买入。

**请求参数（JSON Body）：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `code` | string | 是 | 6位股票代码 |
| `price` | float | 是 | 买入限价 |
| `volume` | int | 是 | 买入股数（必须是100的整数倍） |

**请求示例：**
```bash
curl -X POST "http://127.0.0.1:5001/api/trade/buy" \
  -H "Content-Type: application/json" \
  -d '{"code": "600519", "price": 1600.00, "volume": 100}'
```

**Python 示例：**
```python
import requests

BASE = "http://127.0.0.1:5001"
r = requests.post(f"{BASE}/api/trade/buy", json={
    "code": "600519",
    "price": 1600.00,
    "volume": 100
})
print(r.json())
```

**响应示例（成功）：**
```json
{
  "success": true,
  "data": {
    "order_id": "ORD-20260613-001",
    "code": "600519",
    "name": "贵州茅台",
    "action": "buy",
    "price": 1600.00,
    "volume": 100,
    "amount": 160000.00,
    "status": "filled",
    "fill_time": "2026-06-13T14:30:15"
  },
  "message": "买入委托已成交"
}
```

**响应示例（失败 - 余额不足）：**
```json
{
  "success": false,
  "data": null,
  "message": "账户余额不足，需要 160000.00 元，当前余额 50000.00 元"
}
```

### GET `/api/trade/holdings`

持仓列表 + 账户概览。

**请求示例：**
```bash
curl "http://127.0.0.1:5001/api/trade/holdings"
```

**响应示例（成功）：**
```json
{
  "success": true,
  "data": {
    "account": {
      "total_assets": 185000.00,
      "cash": 25000.00,
      "market_value": 160000.00,
      "today_pnl": 3200.00,
      "today_pnl_pct": 1.76
    },
    "holdings": [
      {
        "code": "600519",
        "name": "贵州茅台",
        "volume": 100,
        "cost_price": 1580.00,
        "current_price": 1605.00,
        "pnl": 2500.00,
        "pnl_pct": 1.58,
        "market_value": 160500.00
      }
    ]
  }
}
```

---

## 7. 风控管理

### GET `/api/risk/overview`

风险概览（权益/比例/预警）。

**请求示例：**
```bash
curl "http://127.0.0.1:5001/api/risk/overview"
```

**响应示例（成功）：**
```json
{
  "success": true,
  "data": {
    "total_assets": 185000.00,
    "max_single_position_pct": 86.76,
    "max_single_position_code": "600519",
    "warning": "单只持仓占比超过80%，建议关注集中风险",
    "stop_loss_triggered": [],
    "today_pnl": 3200.00
  }
}
```

---

## 8. 策略管理

### GET `/api/strategy/list`

已保存策略列表（系统启动时自动初始化3个默认策略）。

**请求示例：**
```bash
curl "http://127.0.0.1:5001/api/strategy/list"
```

**响应示例（成功）：**
```json
{
  "success": true,
  "data": {
    "count": 3,
    "strategies": [
      {"id": 1, "name": "MA双均线交叉", "type": "ma", "active": true, "params": {"short": 5, "long": 20}},
      {"id": 2, "name": "RSI超买超卖", "type": "rsi", "active": false, "params": {"oversold": 30, "overbought": 70}},
      {"id": 3, "name": "MACD金叉死叉", "type": "macd", "active": true, "params": {}}
    ]
  }
}
```

---

## 9. 错误码说明

### 标准错误响应格式

```json
{
  "success": false,
  "data": null,
  "message": "错误原因的具体说明",
  "error_code": "ERR_XXX",
  "suggestion": "建议用户采取的措施"
}
```

### 常见错误码

| 错误码 | HTTP状态码 | 说明 | 处理建议 |
|---------|-----------|------|-----------|
| `ERR_CONNECTION_REFUSED` | — | Flask未启动 | 运行 `start.bat` 或 `python run.py` |
| `ERR_INVALID_CODE` | 400 | 股票代码格式错误 | 使用6位数字代码（如 `600519`） |
| `ERR_DATA_SOURCE_TIMEOUT` | 200(success=false) | 数据源请求超时（8秒） | 等待1分钟后重试，或切换数据源 |
| `ERR_BROKER_NOT_CONNECTED` | 200(success=false) | 券商未连接 | 系统会自动连接Mock券商，或手动调用 `/api/broker/connect` |
| `ERR_INSUFFICIENT_BALANCE` | 200(success=false) | 账户余额不足 | 减少买入数量，或卖出其他持仓 |
| `ERR_STRATEGY_NOT_FOUND` | 200(success=false) | 策略不存在 | 系统已自动初始化3个默认策略，刷新列表 |
| `ERR_SANDBOX_WRITE_FAILED` | 200(success=false) | 沙箱环境文件写入失败 | 系统已自动回退到workspace目录，属正常行为 |

### 超时与降级机制

- **AkShare请求超时**：8秒后自动返回Mock数据（不影响前端展示）
- **沙箱文件写入**：失败自动回退到workspace可写目录
- **券商未连接**：自动连接Mock券商（模拟环境）

---

*本文档最后更新：2026-06-13*
