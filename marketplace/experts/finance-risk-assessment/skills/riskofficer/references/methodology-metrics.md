# Portfolio Metrics (Sharpe, Volatility, Max Drawdown)

This document describes how **Sharpe ratio**, **volatility**, **max drawdown**, and related metrics are computed in RiskOfficer. They appear in VaR responses, optimization results, and construct-portfolio outputs.

## Where metrics are computed

- **RiskOfficer backend (risk_service):** Sharpe ratio (and optionally rolling Sharpe history) when completing a VaR calculation; same formulas for ex-post portfolio returns.
- **ComputeService (construct_portfolio):** After optimizing weights, we compute expected return, volatility, Sharpe, Calmar, VaR/CVaR 95% (parametric), max drawdown, and HHI from the same inputs (covariance, expected returns, historical returns).
- **ComputeService (risk_parity / calmar):** Current and optimized volatility and other metrics for comparison.

---

## Sharpe ratio

- **Definition:** Annualized excess return per unit of annualized volatility, \(\text{Sharpe} = (\mu_{\text{ann}} - r_f) / \sigma_{\text{ann}}\).
- **Backend implementation (risk_service):**
  - Input: daily portfolio returns (e.g. from historical prices × weights).
  - \(\mu_{\text{daily}} = \text{mean(returns)}\), \(\sigma_{\text{daily}} = \text{std(returns)}\).
  - \(\mu_{\text{ann}} = \mu_{\text{daily}} \times 252\), \(\sigma_{\text{ann}} = \sigma_{\text{daily}} \times \sqrt{252}\).
  - \(\text{Sharpe} = (\mu_{\text{ann}} - \text{risk\_free\_rate}) / \sigma_{\text{ann}}\). Default risk-free rate is 0.
  - If \(\sigma_{\text{ann}} = 0\), we return 0.
- **ComputeService (construct_portfolio _compute_metrics):**
  - Expected annual return = `weights @ expected_returns` (from the Data Service / input expected returns vector).
  - Annual volatility = \(\sqrt{w^\top \Sigma w} \times \sqrt{252}\) (from covariance matrix; 252 is the annualization factor).
  - Sharpe = (expected_annual_return − risk_free_rate) / annual_volatility; if volatility &lt; 1e-10 we return 0.
- **Rolling Sharpe (backend):** `calculate_sharpe_history` uses a rolling window (default 252 days, step 5 days), computes the same annualized Sharpe for each window, and returns a list of { date, sharpe }.

---

## Volatility

- **Annualized volatility:** \(\sigma_{\text{ann}} = \sigma_{\text{daily}} \times \sqrt{252}\) when derived from daily returns (backend). When derived from covariance, \(\sigma_{\text{ann}} = \sqrt{w^\top \Sigma w} \times \sqrt{\text{annualization\_factor}}\) (ComputeService).
- **Units:** Decimal (e.g. 0.15 = 15% per year). Used consistently in Sharpe, VaR scaling, and optimization.

---

## Max drawdown (relative, compounded)

- **Definition:** Largest peak-to-trough decline in portfolio value, expressed as a fraction of the running maximum.
- **Implementation (ComputeService returns.py, risk_service):**
  - From **log-returns** \(r_1,\ldots,r_T\): cumulative growth \(C_t = \exp\bigl(\sum_{s=1}^t r_s\bigr)\), running maximum \(M_t = \max_{s\le t} C_s\).
  - Drawdown series: \(\text{DD}_t = (C_t - M_t) / M_t\).
  - Max drawdown: \(\text{MDD} = \min_t \text{DD}_t \le 0\) (stored as a negative number, e.g. −0.15 for −15%).
- **Usage:** Calmar ratio = CAGR / |MDD|; stress test and construct metrics use the same MDD logic.

---

## Construct-portfolio metrics (ComputeService)

After running a strategy (max_sharpe, hrp, max_calmar), we return `ConstructPortfolioMetrics`:

- **expected_annual_return:** \(w^\top \mu\) (weights × expected returns from input).
- **expected_volatility:** \(\sqrt{w^\top \Sigma w} \times \sqrt{\text{annualization\_factor}}\).
- **sharpe_ratio:** (expected_annual_return − risk_free_rate) / expected_volatility.
- **calmar_ratio:** If historical returns are available, CAGR and MDD are computed from portfolio log-returns; then Calmar = CAGR / |MDD| (see `methodology-calmar.md`). Otherwise null.
- **max_drawdown:** From historical portfolio returns (same compounded relative formula as above); null if no history.
- **var_95_daily, cvar_95_daily:** Parametric 95% VaR and CVaR on daily portfolio volatility: \(\sigma_{\text{daily}} = \sqrt{w^\top \Sigma w}\), VaR_95 = −1.645 × σ_daily, CVaR_95 = −σ_daily × φ(1.645) / 0.05\) (normal assumption).
- **hhi:** Herfindahl–Hirschman index of weights (concentration).

---

## References

- **Sharpe ratio:** Sharpe, W. F. (1966). Mutual fund performance. *Journal of Business* 39(1), 119–138. We use the ex-post, annualized form.
- **Volatility annualization:** Standard: \(\sigma_{\text{ann}} = \sigma_{\text{daily}} \sqrt{252}\) for i.i.d. daily returns.
- **Max drawdown:** Standard definition; our implementation uses log-returns and compounded equity curve (see `app/utils/returns.py` in ComputeService, and risk_service in backend).

See `references/academic-references.md` for a full list.
