# Stress Test Methodology

This document describes how **stress tests** are implemented in RiskOfficer. They use **historical crisis periods** and re-use the same portfolio valuation and drawdown logic as elsewhere.

## Idea

- A **stress test** answers: “What would have happened to this portfolio during a past crisis?”
- We take a **crisis configuration** (start date, trough date, recovery date, market) and fetch **historical prices** for the portfolio’s tickers over that window. We then compute the portfolio’s equity curve and drawdown as if it had been held over that period.

## Crisis configurations

- Crises are defined in **stress_test_config** (e.g. `CRISES`). Each has:
  - **id** (e.g. `covid_19`, `ukrainian_conflict_2022`, `financial_2008`, `russian_crisis_1998`, `dotcom_2000`, `black_monday_1987`),
  - **start_date**, **trough_date**, **recovery_date**, **duration_days**,
  - **available_for_markets** (e.g. US, RU),
  - **status** (e.g. `available`, `coming_soon`).
- Only crises with **status `available`** and matching the portfolio’s market are offered. The API exposes `GET /risk/stress-test/crises` to list them.

## Implementation

- **Weights:** Current portfolio weights are computed from positions and portfolio value (same as elsewhere: long/short, gross exposure).
- **Price data:** Backend (or Data Service) provides **historical prices** for the stress window. For multi-currency portfolios, prices are converted to the portfolio’s base currency before building the equity curve.
- **Equity curve:** For each date in the window, portfolio value = sum over assets of (weight × price). We reuse the same weighting and price logic as in other risk calculations.
- **Drawdown and metrics:** We compute **max drawdown** (peak-to-trough, relative/compounded) over the window, plus trough value, recovery value, “recovered” (yes/no), recovery days, worst/best day, and a **resilience score/rank/color/icon** for presentation.
- **Comparison:** Optionally we compare portfolio performance vs a market index over the same period (e.g. “vs market”).
- **Missing data:** If an asset has no history for the crisis window, it is skipped in the current MVP (no synthetic fill).

## API

- **Create:** `POST /risk/stress-test` with `portfolio_snapshot_id`, `crisis_id`. Returns **stress_test_id**; calculation is asynchronous.
- **Get result:** `GET /risk/stress-test/{stress_test_id}` to poll status and get the result (portfolio_simulation, comparison, metadata).
- **List crises:** `GET /risk/stress-test/crises` to list available crises for the user’s context.

## References

- Stress testing is standard in Basel/risk frameworks; we follow the “historical scenario” approach (apply past crisis returns to current portfolio). No separate academic citation is required for the basic design; implementation details are in the backend and `stress_test_config`.

See `references/academic-references.md` for general risk references.
