---
name: quant-risk-dashboard
description: Professional quantitative trading risk management dashboard. Real-time VaR/CVaR calculation, stress testing, position limits, exposure monitoring, drawdown alerts, and comprehensive risk metrics visualization.
tags:
  - quant
  - trading
  - risk
  - dashboard
  - var
  - monitoring
version: 1.0.0
author: chenq
---

# Quant Risk Dashboard

Professional risk management system for quantitative trading.

## Features

### 1. Risk Metrics
- **VaR (Value at Risk)**: Historical, Parametric, Monte Carlo
- **CVaR (Conditional VaR)**: Expected shortfall
- **Max Drawdown**: Current and historical
- **Volatility**: Realized and implied
- **Beta**: Market sensitivity
- **Sharpe/Sortino/Calar**: Risk-adjusted returns

### 2. Position Management
- **Real-time Positions**: Current holdings with P&L
- **Position Limits**: Per-stock and total limits
- **Concentration Risk**: Single position max%
- **Sector Exposure**: Industry allocation

### 3. Exposure Monitoring
- **Long/Short Ratio**: Net exposure
- **Sector Allocation**: Industry breakdown
- **Factor Exposure**: Style factors (value, growth, momentum)
- **Geographic Exposure**: Market cap breakdown

### 4. Stress Testing
- **Historical Scenarios**: 2008 crash, 2020 covid, etc.
- **Custom Scenarios**: User-defined shocks
- **Scenario Comparison**: Side-by-side analysis
- **Recovery Time**: Estimated recovery from scenarios

### 5. Alerts & Notifications
- **Drawdown Alerts**: Threshold-based warnings
- **Position Breach**: Limit violation alerts
- **Volatility Spikes**: Unusual market moves
- **Custom Rules**: User-defined triggers

### 6. Reporting
- **Daily Risk Report**: Automated PDF/HTML reports
- **Risk Attribution**: P&L explained by factors
- **Compliance Reports**: Regulatory compliance
- **Custom Reports**: Flexible report builder

## Installation

```bash
pip install pandas numpy scipy plotly dash
```

## Usage

### Initialize Dashboard
```python
from quant_risk import RiskDashboard

dashboard = RiskDashboard(
    initial_capital=1000000,
    var_confidence=0.95,
    max_position_pct=0.15,
    max_drawdown_pct=0.20
)
```

### Add Positions
```python
dashboard.add_position(
    symbol='600519',
    shares=1000,
    entry_price=1800.0,
    current_price=1850.0
)

dashboard.add_position(
    symbol='000858',
    shares=5000,
    entry_price=45.0,
    current_price=48.0
)
```

### Get Risk Metrics
```python
metrics = dashboard.get_risk_metrics()

print(f"VaR (95%): {metrics['var_95']:,.2f}")
print(f"CVaR (95%): {metrics['cvar_95']:,.2f}")
print(f"Sharpe Ratio: {metrics['sharpe_ratio']:.2f}")
print(f"Max Drawdown: {metrics['max_drawdown']:.2%}")
print(f"Total Exposure: {metrics['total_exposure']:,.0f}")
```

### Stress Test
```python
scenarios = {
    '2008 Crash': -0.50,
    '2020 Covid': -0.30,
    'Rate Hike': -0.15,
    'Custom': -0.25
}

results = dashboard.stress_test(scenarios)

for name, result in results.items():
    print(f"{name}: P&L = {result['pnl']:,.2f}")
```

### Start Web Dashboard
```python
dashboard.start_dashboard(port=8050)
# Open http://localhost:8050
```

## API Reference

### Core Methods
| Method | Description |
|--------|-------------|
| `add_position(symbol, shares, entry, current)` | Add position |
| `remove_position(symbol)` | Close position |
| `update_price(symbol, price)` | Update market price |
| `get_positions()` | Get all positions |
| `get_risk_metrics()` | Calculate risk metrics |

### Risk Analysis
| Method | Description |
|--------|-------------|
| `calculate_var(method='historical')` | Calculate VaR |
| `calculate_cvar()` | Calculate CVaR |
| `stress_test(scenarios)` | Run stress tests |
| `factor_exposure()` | Calculate factor exposure |
| `sector_allocation()` | Get sector breakdown |

### Alerts
| Method | Description |
|--------|-------------|
| `add_alert(condition, message)` | Create alert |
| `get_alerts()` | Get active alerts |
| `clear_alerts()` | Clear alerts |

### Reports
| Method | Description |
|--------|-------------|
| `generate_report(format='pdf')` | Generate report |
| `get_daily_summary()` | Daily summary |

## Risk Metrics Explained

### VaR (Value at Risk)
- **Definition**: Maximum expected loss at given confidence level
- **Interpretation**: "95% VaR = 50,000" means 95% chance loss < 50,000

### CVaR (Conditional VaR)
- **Definition**: Average loss beyond VaR threshold
- **Interpretation**: More conservative than VaR

### Sharpe Ratio
- **Definition**: Risk-adjusted return
- **Interpretation**: >1.0 good, >2.0 excellent

### Max Drawdown
- **Definition**: Largest peak-to-trough decline
- **Interpretation**: Lower is better

### Sortino Ratio
- **Definition**: Downside risk-adjusted return
- **Interpretation**: Only considers downside risk

## Configuration

### Risk Limits
```python
limits = {
    'max_position_pct': 0.15,    # 15% per position
    'max_sector_pct': 0.30,       # 30% per sector
    'max_leverage': 1.5,          # 1.5x leverage
    'max_drawdown': 0.20,         # 20% stop loss
    'max_var_pct': 0.05,          # 5% VaR limit
}
```

### Alert Thresholds
```python
alerts = {
    'drawdown_warning': 0.10,     # 10% drawdown warning
    'drawdown_critical': 0.15,    # 15% critical
    'var_warning': 0.03,          # 3% VaR warning
    'volatility_spike': 2.0,      # 2x normal volatility
}
```

## Visualization

### Web Dashboard
```python
dashboard.start_dashboard()

# Features:
# - Real-time position table
# - P&L charts
# - Risk metrics gauges
# - Sector pie chart
# - Drawdown curve
# - Factor exposure bar chart
```

### Generate Charts
```python
# P&L Chart
chart = dashboard.plot_pnl_history()

# Risk Decomposition
chart = dashboard.plot_risk_attribution()

# Scenario Comparison
chart = dashboard.plot_scenarios()
```

## Integration

### Connect to Trading System
```python
# From trading system
import asyncio

async def update_positions():
    while True:
        positions = await trading_system.get_positions()
        
        for pos in positions:
            dashboard.update_price(pos.symbol, pos.current_price)
        
        await asyncio.sleep(60)  # Update every minute

asyncio.run(update_positions())
```

### Webhook Alerts
```python
# Send alerts to Slack/WeChat
def on_alert(alert):
    send_webhook(
        url=os.getenv('ALERT_WEBHOOK'),
        message=f"Risk Alert: {alert['message']}"
    )

dashboard.set_alert_callback(on_alert)
```

## Use Cases

- **Live Trading**: Real-time risk monitoring
- **Backtesting**: Post-trade risk analysis
- **Portfolio Management**: Multi-strategy risk
- **Compliance**: Regulatory risk reports
- **Risk Research**: Strategy risk profiling

## Links

- [RiskMetrics VaR](https://www.riskmetrics.com)
- [quantlib](https://quantlib.org)
- [Portfolio Visualizer](https://www.portfoliovisualizer.com)
