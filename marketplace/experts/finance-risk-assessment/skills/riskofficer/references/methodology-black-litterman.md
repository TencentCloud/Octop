# Black-Litterman Optimization Methodology

This document describes how **Black-Litterman (BL)** portfolio optimization is implemented in RiskOfficer. The logic runs in **ComputeService** (`optimize_bl`); the RiskOfficer backend fetches market data from the Data Service and passes it to ComputeService.

## Goal

Combine **market equilibrium** (implied returns from market-cap weights) with **investor views** (absolute return forecasts on specific assets) into a posterior expected return vector, then solve **Mean-Variance Optimization (MVO)** with constraints (weight bounds, exposure limits, optional turnover).

## Mathematical setup

### 1. Equilibrium prior (implied excess returns)

- **Market weights:** \(w_{\text{mkt}}\) from Data Service (market-cap weights, normalized to sum 1).
- **Covariance:** \(\Sigma\) = daily covariance (Ledoit–Wolf from Data Service); \(\Sigma_{\text{ann}} = \Sigma \times \text{annualization\_factor}\) (default 252).
- **Prior (CAPM equilibrium):**  
  \[
  \Pi = \delta \cdot \Sigma_{\text{ann}} \cdot w_{\text{mkt}}.
  \]
  \(\Pi\) is the vector of implied annual excess returns; \(\delta\) is the risk-aversion coefficient.

### 2. Risk aversion (delta)

- **Formula:** \(\delta = (E[R_{\text{market}}] - R_f) / \text{Var}(R_{\text{market}})\).
- **Auto-calibration:** If `delta` is not provided, we use `expected_returns` from the Data Service (annualized per-asset expected returns). Then:
  - \(E[R_{\text{market}}] = w_{\text{mkt}}^\top \mu_{\text{hist}}\),
  - \(\text{Var}(R_{\text{market}}) = w_{\text{mkt}}^\top \Sigma_{\text{ann}} w_{\text{mkt}}\),
  - \(\delta = \text{excess} / \text{market\_var}\), clipped to \([0.5, 20]\).
- **Fallback:** If `expected_returns` is not available, \(\delta = 2.5\).

### 3. Views and uncertainty (P, Q, Omega)

- **Views:** Each view is a ticker + expected (annual) return + confidence in \([0.01, 1]\).
- **Pick matrix P:** One row per view; \(P_{j,i} = 1\) if view \(j\) refers to asset \(i\), else 0 (absolute views only: one asset per view).
- **View returns Q:** \(Q_j\) = expected return for the asset in view \(j\).
- **Omega (Idzorek):** Diagonal uncertainty matrix. For each view \(j\):
  - He & Litterman base: \(\sigma^2_j = p_j^\top (\tau \Sigma_{\text{ann}}) p_j\).
  - Idzorek scaling: \(\omega_j = \sigma^2_j \cdot (1 - \text{confidence}) / \text{confidence}\).  
  So higher confidence → smaller \(\omega_j\) → view has more weight in the posterior.

**Numerical stability (implementation):** To avoid singular or ill-conditioned \(\Omega\) when confidence is near 0 or 1, the implementation (ComputeService `optimize_bl`) clamps confidence to \([10^{-4}, 1 - 10^{-4}]\) before computing \(\omega_j\), and applies a diagonal floor \(\omega_j \leftarrow \max(\omega_j, 10^{-10})\) so that \(\Omega\) remains positive-definite and invertible. This ensures the BL posterior and MVO step are stable for all user-supplied confidence values (e.g. 0.99, 1.0).

### 4. BL posterior

- **Posterior precision and mean:**
  \[
  \text{precision} = (\tau \Sigma_{\text{ann}})^{-1} + P^\top \Omega^{-1} P, \qquad
  \mu_{\text{BL}} = \text{posterior\_cov} \cdot \bigl( (\tau \Sigma_{\text{ann}})^{-1} \Pi + P^\top \Omega^{-1} Q \bigr).
  \]
- **Annualization:** \(\tau\) and \(\Sigma\) use the same `annualization_factor` (e.g. 252) everywhere so that \(\Pi\), \(Q\), and \(\mu_{\text{BL}}\) are in annual terms.

### 5. MVO (CVXPY)

- **Objective:** \(\max\; \mu_{\text{BL}}^\top w - (\lambda/2) w^\top \Sigma_{\text{ann}} w - \text{penalty} \cdot \|w - w_{\text{old}}\|_1\) (if turnover penalty set).
- **Constraints:**
  - Per-asset bounds: `weight_bound_lower` \(\le w_i \le\) `weight_bound_upper`.
  - Optional: `max_gross_exposure` (\(\|w\|_1\)), `target_net_exposure` or `max_net_exposure`.
  - **Hard turnover:** If `turnover_limit` is set: \(\|w - w_{\text{old}}\|_1 \le \text{limit}\).
- **Solvers:** CLARABEL first; on failure, SCS. If status is infeasible, the API returns an error asking the user to relax constraints.

## API and data flow

- **Endpoint (RiskOfficer):** `POST /portfolio/optimize-bl` with tickers, views, constraints/options, and optional `portfolio_snapshot_id` (for turnover baseline) + `currency`. Backend gets covariance, market-cap weights, and optional expected returns from Data Service; subsets by tickers; calls ComputeService `optimize_bl`.
- **ComputeService:** Receives `OptimizeBLRequest` (tickers, views, constraints, options, market_data, current_weights). Returns target weights, BL posterior returns, metrics (expected return, vol, Sharpe, exposures), and convergence info.

## Parameters (typical)

- **options:** `tau` (e.g. 0.05), `risk_free_rate`, `annualization_factor` (252), `delta` (null = auto), `risk_aversion_lambda`.
- **constraints:** `weight_bound_lower` / `weight_bound_upper`, `max_gross_exposure`, `max_net_exposure` or `target_net_exposure`, `turnover_penalty` (soft L1), `turnover_limit` (hard).

## References

- **Black, F. & Litterman, R. (1992).** Global Portfolio Optimization. *Financial Analysts Journal* 48(5), 28–43.
- **He, G. & Litterman, R. (1999).** The intuition behind Black-Litterman model portfolios. Goldman Sachs Investment Management Research.
- **Idzorek, T. (2004).** A step-by-step guide to the Black-Litterman model. Working paper; confidence-based scaling of \(\Omega\).
- **MVO and constraints:** Cornuejols, G. & Tütüncü, R. (2007). *Optimization Methods in Finance*. Cambridge University Press.

For a consolidated list, see `references/academic-references.md`.
