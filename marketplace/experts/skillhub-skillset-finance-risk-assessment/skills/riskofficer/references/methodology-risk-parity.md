# Risk Parity (Equal Risk Contribution) Methodology

This document describes how **Risk Parity** (Equal Risk Contribution, ERC) optimization is implemented in RiskOfficer. The logic runs in **ComputeService** (rebalancing) and is also used as the fallback for Max Sharpe in the construct-portfolio flow.

## Goal

We want each asset to contribute **the same amount of risk** to the portfolio. For the variance-based formulation, that means equal **risk contributions** \(RC_i\) in the sense below.

## Mathematical setup

- **Portfolio variance:** \(\sigma_P^2 = w^\top \Sigma w\), so \(\sigma_P = \sqrt{w^\top \Sigma w}\).
- **Marginal contribution to volatility:** \(\partial \sigma_P / \partial w = \Sigma w / \sigma_P\).
- **Risk contribution of asset \(i\):**  
  \[
  RC_i = w_i \cdot (\Sigma w)_i / \sigma_P.
  \]
  (In our code we use \(RC_i = |w_i| \cdot |(\Sigma w)_i| / \sigma_P\) so that both long and short positions contribute positively to the objective.)
- **ERC target:** Each asset should contribute a fraction \(1/n\) of total risk, i.e. \(RC_i / \sum_j RC_j = 1/n\), or equivalently \(RC_i = \sigma_P / n\).

## Implementation

- **Solver:** `scipy.optimize.minimize` with method **SLSQP**.
- **Objective:** Minimize the sum of squared deviations from equal contribution:
  \[
  \min_w \sum_i \bigl( RC_i^{\text{norm}} - 1/n \bigr)^2,
  \]
  where \(RC_i^{\text{norm}} = RC_i / \sum_j RC_j\) (so risk contributions are normalized to sum to 1). In the code, the objective is implemented with portfolio vol \(\sigma_P\), marginal contributions \(\Sigma w\), and the formula above; optional turnover penalty (L1 in weight change) can be added.
- **Constraints:**
  - **Long-only:** \(\sum_i w_i = 1\), \(w_i \in [\text{min\_weight}, \text{max\_weight}]\).
  - **Long-short (preserve_directions):** Net exposure in \([\text{min\_net}, \text{max\_net}]\), gross exposure \(\leq \text{max\_gross}\), and per-asset bounds keep the sign of the current position (longs stay long, shorts stay short).
  - **Unconstrained:** Weights can change sign within bounds and net/gross limits.
- **Bounds:** `min_weight` and `max_weight` are enforced per asset. For small \(n\), `max_weight` is automatically relaxed so that a feasible solution exists (see Maillard et al.: ERC does not impose upper bounds; we do it for diversification).
- **Initial guess:** Long-only: equal weights \(1/n\). Long-short: current weights or equal split respecting net exposure.

## Optional features (in code)

- **Turnover:** Hard limit on \(\sum_i |w_i - w_i^{\text{current}}|\) or soft L1 penalty.
- **Net and gross exposure:** Configurable for long-short portfolios.

## CVaR Risk Budgeting (risk_measure: "cvar")

When the API option `risk_measure` is set to `"cvar"`, ComputeService uses **CVaR (Expected Shortfall) risk budgeting** instead of variance-based ERC:

- **Library:** **skfolio** — `RiskBudgeting` with `RiskMeasure.CVAR`. The solver is **CLARABEL** (convex optimization). Do not use SLSQP for CVaR risk budgeting; the problem is not smooth and SLSQP may converge to poor local minima.
- **Input:** Historical returns matrix (e.g. log-returns), min/max weight bounds. CVaR is computed at a configurable confidence (e.g. 95%); the same confidence is used for risk contributions.
- **Output:** Long-only weights (or long-short if constraints allow) that equalize **CVaR contributions** across assets, subject to bounds.
- **Turnover:** CVaR Risk Budgeting in skfolio does not natively support turnover constraints. If the user sets `turnover_limit`, ComputeService runs CVaR optimization and then **clips** the solution to satisfy the turnover limit (post-optimization), with a warning in logs. `turnover_penalty` is not applied in the CVaR path.
- **Where used:** Same rebalancing endpoint `POST /portfolio/{snapshot_id}/optimize` with risk measure `cvar`; backend passes `risk_measure` to ComputeService risk-parity.

## Where it is used

- **Rebalancing:** `POST /portfolio/{snapshot_id}/optimize` with default risk measure (variance). ComputeService builds the covariance matrix from historical (log-)returns, then runs the ERC optimizer above.
- **Construct portfolio (auto-generate):** If Max Sharpe (skfolio MeanRisk) fails, we fall back to this ERC formulation with the same covariance matrix and long-only bounds.

## Academic reference

- **Maillard, S., Roncalli, T., Teïletche, J. (2010).** The Properties of Equally Weighted Risk Contribution Portfolios. *The Journal of Portfolio Management* 36(4), 60–70.  
  This paper defines Equal Risk Contribution (ERC) and the variance-based risk contribution formula we use.
- **CVaR risk budgeting:** Rockafellar, R.T. & Uryasev, S. (2000). Optimization of conditional value-at-risk. *Journal of Risk* 2, 21–42. skfolio implements CVaR-based risk budgeting; we use `RiskMeasure.CVAR` with CLARABEL.

For more references, see `references/academic-references.md`.
