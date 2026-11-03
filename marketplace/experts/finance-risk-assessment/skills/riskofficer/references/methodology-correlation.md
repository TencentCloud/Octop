# Cross-Portfolio PnL Correlation Methodology

This document describes how **cross-portfolio PnL correlation** and optional **crisis regime analysis** are implemented in RiskOfficer. The logic runs in the **RiskOfficer backend** (Celery task `correlation.run_correlation_analysis`); market data (historical prices) comes from the Data Service.

## Goal

Compute the **correlation matrix of daily PnL** across multiple portfolios. This is a standard multi-strategy fund metric (e.g. Citadel, Millennium): correlation is between **portfolio-level daily P&L series**, not between individual asset returns. Optionally, split days into "normal" vs "crisis" and compare correlations to detect **re-correlation risk** (correlations rising in stress).

## Snapshot selection: one per portfolio

To avoid correlating multiple historical versions of the same portfolio, we **group snapshots by portfolio** and keep only the **latest** snapshot per portfolio:

- **Portfolio key:** `manual:{name}` for manual portfolios, `broker:{broker}:{sandbox}` for broker-synced, or `snap:{id}` as fallback. Aggregated snapshots are excluded.
- For each key we take the snapshot with the latest `snapshot_timestamp`.
- User can pass explicit `portfolio_ids` or use "all non-archived" (then ordered by `created_at` and grouped as above).

At least **2** portfolios (after grouping) are required.

## PnL series per portfolio

For each selected snapshot:

- Decrypt snapshot and get positions (ticker, quantity).
- Request **historical prices** from Data Service for all tickers, over `window_days + 5` (e.g. 65 days for 60-day window).
- For each date, portfolio value = sum over tickers of (quantity × close price).
- **Daily PnL** = change in portfolio value day-over-day. We keep one PnL series per portfolio (keyed by portfolio name or key).

If a portfolio has no positions or price fetch fails, it is skipped. We need at least 2 portfolios with valid PnL series.

## Correlation matrix

- **Align** all PnL series to **common dates** (intersection of dates across portfolios).
- Require at least **5** common dates; otherwise the API returns an error (not enough data for reliable correlation).
- **Matrix:** For the aligned PnL matrix (portfolios × dates), compute the sample correlation matrix via `np.corrcoef`. Any NaN (e.g. constant series) is replaced by 0.
- **Output:** `portfolio_names`, `correlation_matrix` (2D), `pairs` (list of portfolio pairs with correlation), `avg_pairwise_correlation`, `window_days`, `num_portfolios`.

## Crisis regime (optional)

When `include_crisis_regime` is true:

- **Aggregate PnL:** For each day, sum PnL across all portfolios. This is a proxy for "fund-level" daily PnL.
- **Crisis threshold:** \(\mu - 2\sigma\) of this aggregate PnL series (μ = mean, σ = std). Days with aggregate PnL **below** this threshold are labelled **crisis**; the rest **normal**.
- **Minimum counts:** We need at least 3 crisis days and 3 normal days. If not, we return `crisis_regime.available: false` with counts and reason.
- **Separate correlations:** Compute correlation matrix **on crisis days only** and **on normal days only** (same PnL matrix, different column masks).
- **Output in result:**
  - `avg_normal_correlation`, `avg_crisis_correlation` (average pairwise in each regime).
  - `re_correlation_delta` = avg_crisis − avg_normal (positive = correlations rise in stress = re-correlation risk).
  - `crisis_matrix`, `normal_matrix` (full matrices for the two regimes).
  - `n_crisis_days`, `n_normal_days`, `crisis_threshold`.

Interpretation: if `re_correlation_delta` is large and positive, portfolios tend to move together more in bad days, which increases tail risk for the combined book.

## API

- **Endpoint (RiskOfficer):** `POST /portfolio/correlation` with optional `portfolio_ids`, `window_days` (default 60), `include_crisis_regime` (default false), `analysis_currency` (default `"RUB"`: `"RUB"` or `"USD"`). All PnL series are converted to this currency (CBR historical rates) before computing the correlation matrix. The call starts an **asynchronous** optimization; result is polled via the standard optimization status/result endpoints (e.g. WebSocket or GET).
- **Task:** `optimization.run_correlation_analysis` (Celery); runs `_compute_pnl_correlation_async` and stores encrypted result in optimization result table.

## References

- **PnL correlation across strategies:** Standard in fund-of-funds and multi-strategy risk (e.g. CFTC/SEC reporting, manager due diligence). We follow the convention: daily PnL per portfolio, then Pearson correlation.
- **Crisis regime / re-correlation:** Stressed correlations are a well-known risk (e.g. during 2008, correlations spiked). Our crisis definition (aggregate PnL &lt; μ − 2σ) is a simple heuristic; no single academic citation. For tail risk and CVaR, see `methodology-var.md`.

See `references/academic-references.md` for general risk references.
