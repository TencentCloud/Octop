---
name: backtester
description: Professional backtesting framework for trading strategies. Tests SMA crossover, RSI, MACD, Bollinger Bands, and custom strategies on historical data. Generates equity curves, drawdown analysis, and performance metrics. Use when validating trading strategies, comparing backtest results, or optimizing strategy parameters.
metadata:
  openclaw:
    emoji: "📈"
    requires:
      bins: [python3]
    always: false
---

# Beta Backtester

Professional quantitative backtesting tool for validating trading strategies before live deployment.

## Design Patterns Applied

### 1. 迭代式优化模式 (Iterative Optimization Pattern)
回测框架采用参数优化迭代流程，逐步优化策略参数：
- **参数扫描**: 自动遍历参数空间（如SMA的fast/slow、RSI的超买/超卖阈值）
- **网格搜索**: 测试不同参数组合，找到最优风险收益比
- **验证集**: 使用walk-forward分析避免过拟合

### 2. 情境感知工具选择 (Context-Aware Tool Selection)
根据数据类型和市场特性自动选择合适的数据源：
- **数据源适配**: A股使用本地SQLite数据库，美股/加密货币使用Yahoo Finance
- **时间框架感知**: 15分钟K线用于短线策略，日线用于中长线策略
- **资产类别识别**: 自动处理股票代码格式转换（如000001 → 000001.SZ）

### 3. 特定领域智能 (Domain-Specific Intelligence)
内置专业金融指标计算和风险评估：
- **性能指标**: Sharpe、Sortino、最大回撤、胜率、期望收益
- **风险调整**: 考虑手续费和滑点的实盘模拟
- **权益曲线**: 可视化回测结果，支持多策略对比

## What It Does

- Tests strategies on historical OHLCV data (stocks, crypto, forex)
- Calculates performance metrics (Sharpe, Sortino, Max Drawdown, Win Rate)
- Generates equity curves and drawdown charts
- Compares multiple strategies side-by-side
- Optimizes parameters for best risk-adjusted returns
- Error handling with fallback data sources
- A/B testing support for strategy comparison

## Strategies Supported

| Strategy | Description | Key Parameters | Best For |
|----------|-------------|----------------|----------|
| SMA Crossover | Fast/slow moving average crossover | fast (8-14), slow (21-65) | Trend following |
| RSI | RSI overbought/oversold reversals | period (14), upper (70), lower (30) | Mean reversion |
| MACD | MACD signal line crossovers | fast (12), slow (26), signal (9) | Momentum trading |
| Bollinger Bands | Mean reversion at bands | period (20), std (2) | Volatility trading |
| Custom | User-defined entry/exit logic | Custom | Specialized strategies |

## Usage Examples

### Basic Backtest
```bash
python3 backtest.py --strategy sma_crossover --ticker 600036 --start 2025-01-01 --end 2025-03-31
```

### Parameter Optimization
```bash
python3 backtest.py --strategy rsi --ticker 000001 --start 2025-01-01 --end 2025-03-31 --upper 65 --lower 35
```

### Multi-Strategy Comparison
```bash
# Run multiple strategies and compare
python3 backtest.py --strategy sma_crossover --ticker 600519 --start 2025-01-01 --end 2025-03-31
python3 backtest.py --strategy macd --ticker 600519 --start 2025-01-01 --end 2025-03-31
python3 backtest.py --strategy rsi --ticker 600519 --start 2025-01-01 --end 2025-03-31
```

## Output Example

```
BACKTEST RESULTS: SMA_CROSSOVER | 600036 | 2025-01-01 to 2025-03-31
============================================================
📊 Performance Metrics
Total Return:        +18.2%
Annual Return:        +9.8%
Sharpe Ratio:         1.45 (Good)
Max Drawdown:        -8.7% (Acceptable)
Win Rate:             62% (Above average)
Total Trades:         32
Best Trade:          +6.8%
Worst Trade:         -3.2%
Avg Hold Time:        10 days

📈 Equity Curve
2025-01-15: $10,000 → $10,350 (Entry: SMA cross up)
2025-01-28: $10,350 → $10,520 (Exit: SMA cross down)
2025-02-10: $10,520 → $10,890 (Entry: SMA cross up)
2025-03-05: $10,890 → $11,820 (Exit: SMA cross down)
2025-03-20: $11,820 → $11,820 (Current position)

⚙️ Strategy Parameters
Fast SMA: 8
Slow SMA: 21
Commission: 0.05%
Slippage: 0.1%
Initial Capital: $100,000
```

## Iterative Optimization Example

Step 1: Baseline with default parameters
```bash
python3 backtest.py --strategy sma_crossover --ticker 600036 --start 2025-01-01 --end 2025-03-31
# Result: Sharpe 1.25, Return +12.3%
```

Step 2: Test parameter variations
```bash
# Test fast=8, slow=21
python3 backtest.py --strategy sma_crossover --ticker 600036 --fast 8 --slow 21
# Result: Sharpe 1.45, Return +18.2%

# Test fast=10, slow=30
python3 backtest.py --strategy sma_crossover --ticker 600036 --fast 10 --slow 30
# Result: Sharpe 1.18, Return +14.5%
```

Step 3: Select optimal parameters (fast=8, slow=21)
Step 4: Validate on out-of-sample data (2025-04-01 to 2025-06-30)

## Error Handling & Validation

### Data Validation
- ✅ Checks database existence before query
- ✅ Validates date range is valid
- ✅ Handles empty result sets gracefully
- ✅ Converts stock codes (e.g., 000001 → 000001.SZ)

### Error Recovery
- ❌ Database not found → Shows error with path
- ❌ No data in date range → Warns user
- ❌ Invalid stock code → Tries format conversion
- ❌ Query error → Returns None and logs exception

### Input Validation Checklist
- [ ] Start date < End date
- [ ] Stock code has valid format (6 digits)
- [ ] Strategy name is supported
- [ ] Initial capital > 0
- [ ] Commission rate is reasonable (0.0001-0.005)

## Metrics Explained

- **Sharpe Ratio**: Risk-adjusted return (>1 is good, >2 is excellent)
  Formula: (Return - RiskFree) / StdDev
- **Max Drawdown**: Largest peak-to-trough loss (-10% is acceptable)
  Shows worst-case loss scenario
- **Win Rate**: % of profitable trades (>50% with good R:R is profitable)
- **Sortino Ratio**: Like Sharpe but only penalizes downside volatility
  Better for asymmetric return distributions
- **R-Multiple**: Return normalized by risk (1R = max loss per trade)
  Allows comparing trades of different sizes

## Requirements

- Python 3.8+
- pandas, numpy, matplotlib (auto-installed)
- SQLite database with OHLCV data (a_stock_complete.db)
- Stock symbols in format: XXXXXX.SH (Shanghai) or XXXXXX.SZ (Shenzhen)

## Data Sources

- Default: Local SQLite (a_stock_complete.db)
  Location: ~/.openclaw/workspace/trading/a_stock_complete.db
- CSV upload: Provide your own OHLCV data
- API: Tiger API for professional data

## A/B Testing Support

Compare multiple strategies on same dataset:

```bash
# Strategy A: SMA Crossover
python3 backtest.py --strategy sma_crossover --ticker 600036 --start 2025-01-01 --end 2025-03-31 > sma_results.txt

# Strategy B: RSI
python3 backtest.py --strategy rsi --ticker 600036 --start 2025-01-01 --end 2025-03-31 > rsi_results.txt

# Compare
cat sma_results.txt rsi_results.txt | grep "Sharpe\|Return\|Drawdown"
```

## Best Practices

### 1. Avoid Overfitting
- Use walk-forward analysis (train on past, validate on future)
- Keep parameter search space reasonable (don't optimize too many parameters)
- Use multiple instruments to validate strategy robustness

### 2. Include Transaction Costs
- Always include commission (0.05%) and slippage (0.1%)
- Real trading will have these costs - backtest should reflect reality
- Test sensitivity: run with 0.02%, 0.05%, 0.1% commission

### 3. Check for Look-Ahead Bias
- Ensure indicators only use past data
- No peeking at future prices
- Use `.shift(1)` when necessary for signal lag

### 4. Validate Data Quality
- Check for missing bars or gaps
- Verify OHLC consistency (high ≥ open/close ≥ low)
- Remove outliers (>10% daily moves usually errors)

### 5. Test Edge Cases
- Market crashes (e.g., 2020 COVID crash)
- Low volatility periods (e.g., 2017)
- Choppy sideways markets (e.g., 2023)

## Workflow Example: Full Strategy Development

1. **Data Preparation**
   - Load historical data from database
   - Clean and validate data quality
   - Check for missing bars

2. **Strategy Definition**
   - Choose entry/exit criteria
   - Define position sizing
   - Set stop-loss/take-profit rules

3. **Initial Backtest**
   - Run with default parameters
   - Analyze basic metrics (Sharpe, drawdown)

4. **Parameter Optimization** (Iterative)
   - Grid search parameter space
   - Find optimal risk-adjusted return
   - Avoid overfitting

5. **Out-of-Sample Validation**
   - Test on unseen data
   - Compare in-sample vs out-of-sample performance
   - Check for degradation

6. **Robustness Testing**
   - Test on different instruments
   - Test in different market regimes
   - Add noise to parameters (±10%)

7. **Risk Analysis**
   - Calculate VaR and CVaR
   - Stress test extreme scenarios
   - Check correlation with market

8. **Production Deployment**
   - Paper trade for 1-2 weeks
   - Start with small position size
   - Monitor and adjust

## Common Pitfalls

❌ **Look-ahead bias**: Using future data in indicators
❌ **Survivorship bias**: Only testing current stocks (excluding delisted)
❌ **Overfitting**: Too many parameters, curve-fitting noise
❌ **Ignoring costs**: Forgetting commission and slippage
❌ **Small sample**: <50 trades is statistically insignificant
❌ **Data snooping**: Testing too many strategies until one works

## Advanced Features

### Custom Strategy Template
```python
def calculate_custom_strategy(df: pd.DataFrame, param1: int, param2: float) -> pd.DataFrame:
    """User-defined strategy"""
    df = df.copy()
    
    # Your logic here
    df['signal'] = 0
    df.loc[entry_condition, 'signal'] = 1  # Buy
    df.loc[exit_condition, 'signal'] = -1  # Sell
    
    df['position'] = df['signal'].diff()
    return df
```

### Monte Carlo Simulation
Add noise to price data to test strategy robustness:
```python
def add_noise(df: pd.DataFrame, noise_pct: float = 0.01) -> pd.DataFrame:
    """Add random noise to prices"""
    df = df.copy()
    noise = np.random.normal(0, noise_pct, len(df))
    df['close'] = df['close'] * (1 + noise)
    return df
```

## Troubleshooting

**Problem**: "Database not found"
→ Check: `ls ~/.openclaw/workspace/trading/a_stock_complete.db`
→ Fix: Import data using data ingestion pipeline

**Problem**: "No data in date range"
→ Check: Verify stock code format (e.g., 600036 → 600036.SH)
→ Check: Verify date format (YYYY-MM-DD)
→ Check: Database has data for that period

**Problem**: "Low Sharpe ratio (<0.5)"
→ Check: Strategy might be overfit
→ Check: Transaction costs too high
→ Check: Wrong time frame (try different bars)

**Problem**: "Too few trades (<20)"
→ Check: Parameter too restrictive
→ Check: Date range too short
→ Fix: Extend backtest period or relax entry criteria

## Disclaimer

Backtested results do NOT guarantee future performance. Past performance is not indicative of future results. Always paper trade before going live. Test strategies in multiple market conditions before risking real capital.

---

*Built by Beta — AI Trading Research Agent*
