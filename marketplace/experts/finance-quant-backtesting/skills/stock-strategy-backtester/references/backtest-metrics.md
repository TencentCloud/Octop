# Backtest Metrics Reference

Use this file when interpreting outputs from `scripts/backtest_strategy.py`.

## Core Performance Metrics

- `total_return_pct`
  - Formula: `(final_equity / initial_capital - 1) * 100`
  - Meaning: End-to-end growth over the tested date range.

- `cagr_pct`
  - Formula: `((final_equity / initial_capital)^(1/years) - 1) * 100`
  - Meaning: Annualized compound growth rate.

- `max_drawdown_pct`
  - Formula: `abs(min(equity / rolling_peak - 1)) * 100`
  - Meaning: Worst peak-to-trough loss.

- `sharpe_ratio`
  - Formula: `(mean(daily_return - rf/252) / stdev(daily_return)) * sqrt(252)`
  - Meaning: Risk-adjusted return using total volatility.

## Trade Quality Metrics

- `trade_count`
  - Number of completed trades.

- `win_rate_pct`
  - Formula: `winning_trades / total_trades * 100`
  - Meaning: Percent of trades with positive return.

- `avg_trade_return_pct`
  - Arithmetic mean of per-trade returns.

- `avg_win_pct` and `avg_loss_pct`
  - Mean gain on winners and mean loss on losers.

- `profit_factor`
  - Formula: `sum(winning_returns_pct) / abs(sum(losing_returns_pct))`
  - Meaning: Return concentration of winners versus losers.
  - Note: `null` means no losing trades in the sample.

## Exposure and Friction

- `exposure_pct`
  - Fraction of bars where capital is invested.
  - Compare strategies with similar exposure when possible.

- `commission_bps` and `slippage_bps`
  - Always include these assumptions in reports.
  - Re-run with higher friction to test robustness.

## Practical Review Checklist

1. Reject strategies with high return but extreme drawdown.
2. Reject strategies with tiny trade count and unstable CAGR.
3. Compare in-sample and out-of-sample periods before final conclusions.
4. Record assumptions (date range, costs, parameter set) with each run.
