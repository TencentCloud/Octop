---
name: stock-strategy-backtester
description: Backtest stock trading strategies on historical OHLCV data and report win rate, return, CAGR, drawdown, Sharpe ratio, and trade logs. Use when evaluating or comparing strategy rules (SMA crossover, RSI mean reversion, breakout), quantifying transaction-cost impact, tuning parameters, or generating performance summaries from CSV data. Trigger for requests like "回测股票策略胜率", "测收益率", "compare two strategy backtests", and "build a strategy report from historical prices".
---

# Stock Strategy Backtester

## Version Notice

- `1.0.0` and `1.0.1` are deprecated.
- Use `1.0.2` or newer only.
- Deprecation reason: early versions bundled non-core marketplace automation files and may trigger security scanner warnings in some environments.

## Overview

Run repeatable, long-only stock strategy backtests from daily OHLCV CSV files.
Use bundled scripts to generate consistent metrics and trade-level output, then summarize with investor-friendly conclusions.

## Quick Start

1. Prepare a CSV with at least `Date` and `Close` columns.
2. Run a baseline backtest:

```bash
python scripts/backtest_strategy.py \
  --csv /path/to/prices.csv \
  --strategy sma-crossover \
  --fast-window 20 \
  --slow-window 60
```

3. Export artifacts for review:

```bash
python scripts/backtest_strategy.py \
  --csv /path/to/prices.csv \
  --strategy rsi-reversion \
  --rsi-period 14 \
  --rsi-entry 30 \
  --rsi-exit 55 \
  --commission-bps 5 \
  --slippage-bps 2
```

## Workflow

1. Validate data
- Ensure `Date` is parseable and sorted ascending.
- Ensure `Open/High/Low/Close` are numeric; missing `Open/High/Low` falls back to `Close`.

2. Pick strategy logic
- `sma-crossover`: trend-following with fast/slow moving averages.
- `rsi-reversion`: buy oversold and exit on momentum recovery.
- `breakout`: enter on highs breakout and exit on lows breakdown.

3. Set realistic assumptions
- Always set `--commission-bps` and `--slippage-bps`.
- Avoid reporting cost-free backtests as production-ready.

4. Compare variants
- Change one parameter block at a time.
- Compare on the same date range and same cost model.

5. Produce final summary
- Report: `total_return_pct`, `cagr_pct`, `win_rate_pct`, `max_drawdown_pct`, `sharpe_ratio`, `profit_factor`, and trade count.
- Use trade CSV to explain where alpha is coming from.

## Supported Commands

- Baseline SMA strategy:

```bash
python scripts/backtest_strategy.py \
  --csv /path/to/prices.csv \
  --strategy sma-crossover \
  --fast-window 10 \
  --slow-window 50
```

- Breakout strategy:

```bash
python scripts/backtest_strategy.py \
  --csv /path/to/prices.csv \
  --strategy breakout \
  --lookback 20
```

- JSON-only output (for automation pipelines):

```bash
python scripts/backtest_strategy.py \
  --csv /path/to/prices.csv \
  --strategy rsi-reversion \
  --quiet
```

## Output Contract

- Script prints a JSON object to stdout with:
- `strategy`
- `period`
- `metrics`
- `config`
- `trades`

## Analysis Guardrails

1. Use out-of-sample logic
- Prefer walk-forward validation over one-shot tuning.

2. Avoid leakage
- Compute signals from bar `t`, execute at bar `t+1` open.

3. Report downside with upside
- Never present return without drawdown and trade count.

4. Treat results as research
- Backtests are not guarantees and should not be framed as financial advice.

## References

- Metrics details: `references/backtest-metrics.md`
