# Pre-Trade Check Methodology

This document describes how the **pre-trade risk check** is implemented in RiskOfficer. It runs in the **RiskOfficer backend** (risk API); the endpoint is **synchronous** and **FREE** (no subscription required).

## Goal

Before applying a target portfolio (e.g. after Black-Litterman optimization), validate it against configurable constraints and compute key risk metrics. Return a **verdict** (pass / warning / fail) and list of constraint violations so the user or AI agent can decide whether to proceed.

## API

- **Endpoint:** `POST /api/v1/risk/pre-trade-check`
- **Request body:**
  - `target_portfolio`: object mapping ticker → weight (e.g. `{"SBER": 0.15, "GAZP": 0.10, "ROSN": -0.08}`).
  - `amount`: portfolio amount in base currency (used to convert VaR to absolute and percentage).
  - `currency` (optional): `"RUB"` or `"USD"` — determines which market data universe is used for historical VaR; default `"RUB"`.
  - `constraints`: optional `PreTradeConstraints` (see below).
- **Response:** `verdict` ("pass" | "warning" | "fail"), `var_95_pct`, `currency`, `exposure_metrics`, `constraint_violations`, `result_hash` (ERC-8004 deterministic hash for verification), optional `data_quality` (see below), optional `sector_exposures` (dict mapping sector name to its share of gross exposure; present when sector constraints are used).

## Exposure metrics

Computed from the target weights only (no market data):

- **Long exposure:** sum of positive weights.
- **Short exposure:** sum of absolute values of negative weights.
- **Gross exposure:** long + short.
- **Net exposure:** sum of all weights.

All are returned in the response as decimals (e.g. 1.0 = 100%).

## Constraint checks

Each constraint is optional (null = not checked). If present, a violation is appended to `constraint_violations` with `constraint` name, `message`, and `severity` ("error" or "warning").

| Constraint | Check | Severity |
|------------|--------|----------|
| `weight_bound_upper` | For each ticker, weight ≤ upper bound | error |
| `weight_bound_lower` | For each ticker, weight ≥ lower bound | error |
| `max_gross_exposure` | gross_exposure ≤ limit | error |
| `max_net_exposure` | \|net_exposure\| ≤ limit | error |
| `max_var_pct` | VaR (95%, as % of amount) ≤ limit; see below | error if VaR available, warning if VaR unavailable |
| `max_sector_concentration` | No single sector's exposure exceeds the limit | error (or warning if Data Service unavailable) |
| `sector_limits` | Per-sector limits `{sector_name: max_weight}` — each named sector must not exceed its specific limit. Case-insensitive matching. | error per sector exceeded |

## Sector concentration check

When `max_sector_concentration` or `sector_limits` is provided, the backend fetches sector metadata from Data Service and computes each sector's share of gross exposure.

### Data source

1. **Primary:** `DataServiceClient.get_autoportfolio_market_data(currency)` — returns the full `universe` with a `sector` field per ticker. This is a single request cached in Redis (TTL 48h).
2. **Fallback:** For tickers not found in the universe (e.g. foreign stocks), `DataServiceClient.get_symbol_details(ticker)` is called per ticker.
3. Tickers with no sector after both attempts are classified as `"Other"` and listed in `data_quality.tickers_without_sector`.

### Sector exposure formula

$$\text{sector\_exposure}(s) = \frac{\sum_{t \in s} |w_t|}{\text{gross\_exposure}}$$

where $\text{gross\_exposure} = \sum_t |w_t|$.

Using absolute weights ensures the metric is meaningful for long/short portfolios — both long and short positions contribute proportionally to sector concentration.

### Graceful degradation

If Data Service is unreachable (connection error, timeout, 503), the check returns a single **warning** violation (`"Sector data unavailable; cannot verify sector concentration constraints"`) instead of failing with 500. This allows the pre-trade check to complete with other constraints even when sector data is temporarily unavailable.

## VaR calculation (for max_var_pct)

- **Method:** Historical or parametric (implementation may use historical empirical distribution or variance–covariance). In both cases, portfolio returns (or the underlying price series) are built using **inner-join alignment**: only dates where **all** requested tickers have data are used. No zero-fill is applied — this avoids bias when tickers have different history lengths.
- **Data:** Backend fetches historical prices per ticker (via Data Service). Prices are combined into a returns DataFrame aligned by common dates (dropna / inner join). For parametric: portfolio variance = \(w^\top \Sigma w\) (daily), VaR_abs = \(z_{0.95} \cdot \sigma_{\text{daily}} \cdot \text{amount}\). For historical: VaR from the \((1-\alpha)\) percentile of aligned daily returns.
- **VaR %:** (VaR_abs / amount) × 100; loss is reported as positive.
- **If VaR fails:** e.g. ticker not in market data, or insufficient common dates — no VaR is returned; `var_95_pct` is -1 and `max_var_pct` constraint yields a **warning** (cannot verify) rather than error.

## Data quality (response)

- **`data_quality`** (optional): `tickers_requested`, `tickers_with_data`, `tickers_missing`, `total_dates`, `dates_dropped`. Indicates how many tickers had history, how many dates were used after alignment, and how many were dropped — useful to interpret VaR when series lengths differ. May also contain `tickers_without_sector` — list of tickers for which sector metadata was unavailable.

## Verdict logic

- **fail:** At least one violation with severity **error**.
- **warning:** No errors, but at least one **warning** (e.g. sector data unavailable, or VaR unavailable).
- **pass:** No violations.

## Result hash (ERC-8004)

The response includes `result_hash`: a deterministic hash (e.g. keccak256 of canonical JSON) of the result payload. Clients can recompute it to verify integrity. See ERC-8004 integration docs in the backend.

## Where it is used

- **Skill / AI agents:** Before calling apply on an optimized portfolio, the skill instructs to run pre-trade check and only apply if verdict is pass or accepted warning.
- **iOS app:** PreTradeCheckSheet; user enters or pastes target weights and amount, sets constraints, and sees verdict and violations.

## References

- Pre-trade checks are standard in institutional trading (risk gates before order submission). This implementation is a lightweight, synchronous gate; no separate academic citation. For VaR methodology, see `methodology-var.md`. For ERC-8004, see backend docs.

See `references/academic-references.md` for VaR and general risk references.
