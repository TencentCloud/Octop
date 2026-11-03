# Calmar Ratio and Max-Calmar Optimization

This document describes how the **Calmar ratio** is defined and how **Max-Calmar** optimization is implemented in RiskOfficer (ComputeService and construct-portfolio).

## Calmar ratio definition

\[
\text{Calmar} = \frac{\text{CAGR}}{|\text{Max Drawdown}|}.
\]

- **CAGR (Compound Annual Growth Rate):** From **log-returns** \(r_1,\ldots,r_T\):
  \[
  \text{total return} = \exp\Bigl(\sum_t r_t\Bigr) - 1, \qquad
  \text{years} = T / 252, \qquad
  \text{CAGR} = (1 + \text{total return})^{1/\text{years}} - 1.
  \]
  We use 252 trading days per year.
- **Max Drawdown (MDD):** We use **compounded, relative** drawdown. From the cumulative growth series \(C_t = \exp\bigl(\sum_{s=1}^t r_s\bigr)\) and the running maximum \(M_t = \max_{s\le t} C_s\):
  \[
  \text{DD}_t = \frac{C_t - M_t}{M_t}, \qquad
  \text{MDD} = \min_t \text{DD}_t \le 0.
  \]
  So MDD is the largest peak-to-trough decline (as a fraction). This matches the “relative, compounded” convention (similar to MDD_Rel in some libraries).

## Rebalancing (existing portfolio)

- **Endpoint:** `POST /portfolio/{snapshot_id}/optimize-calmar`.
- **Implementation (ComputeService):** `scipy.optimize.minimize(..., method="SLSQP")` with objective \(-\text{Calmar}\) (minimize negative Calmar = maximize Calmar). Constraints: sum of weights (long-only) or net/gross exposure (long-short), plus per-asset bounds. Historical **log-returns** are built from prices; portfolio returns = returns matrix × weights; then CAGR and MDD are computed as above.
- **Data requirement:** At least **200 trading days** of history per ticker (backend requests 252). If insufficient, the API returns `INSUFFICIENT_HISTORY` and we suggest Risk Parity instead.
- **Fallback:** If SLSQP does not converge, we may still return the best weights found (with a warning).

## Construct portfolio (auto-generate): Max Calmar strategy

- **Endpoint:** `POST /portfolio/auto-generate` with `strategy: "max_calmar"`.
- **Implementation (ComputeService construct_portfolio):** Two-stage:
  1. **Warm start:** Run Max Sharpe (skfolio MeanRisk MAXIMIZE_RATIO) to get initial weights. If that fails, use equal weights \(1/n\).
  2. **Refinement:** Run the same SLSQP Calmar maximization as above (objective \(-\text{Calmar}\), CAGR and MDD from log-returns), with long-only bounds and sum = 1.
- **Fallback:** If the Calmar SLSQP step fails, we return the Max Sharpe (warm-start) weights and set `fallback_used: "max_sharpe"`.

## Parameters (typical)

- **Rebalancing:** `min_weight`, `max_weight`, optional `min_expected_return`, `max_drawdown_limit`, `min_calmar_target` (in constraints).
- **Construct:** Uses the same Calmar objective; bounds come from `constraints.min_weight` and `constraints.max_weight` (e.g. 0.02 and 0.25).

## References

- **Calmar ratio:** Young, T. (1991). Calmar Ratio: A Smoother Tool. *Futures* (industry usage).
- **CAGR and compounded drawdown:** Standard in portfolio analytics; our implementation follows the log-return convention used across RiskOfficer and ComputeService (see e.g. `app/utils/returns.py`, `app/utils/optimization.py`).
- **Optimization:** Cornuejols, G. & Tütüncü, R. (2007). *Optimization Methods in Finance*. Cambridge University Press.

See `references/academic-references.md` for a full list.
