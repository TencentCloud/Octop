# Auto Portfolio Generation Methodology

This document describes how **automatic portfolio generation** works in RiskOfficer: data preparation, strategies, and where each calculation runs.

## Overview

- **User flow:** User chooses a universe (e.g. US large cap), strategy, and optional constraints. Backend requests market data, calls ComputeService to construct weights, then optionally **applies** the result as a new portfolio (after user confirmation).
- **Components:**  
  - **Data Service:** Prepares and caches market data (prices, log-returns, covariance, expected returns, clusters).  
  - **Backend (RiskOfficer):** Orchestrates auto-generate, calls Data Service and ComputeService, stores results and applies snapshots.  
  - **ComputeService:** Runs the actual optimization (construct-portfolio) and returns weights and metrics.

## Data preparation (Data Service)

- **Returns:** We use **log-returns** for consistency across VaR, optimization, and risk metrics.
- **Covariance:** **Ledoit–Wolf** shrinkage estimator is used to stabilize the sample covariance matrix (important for small samples and many assets). Implemented in Data Service as `sklearn.covariance.LedoitWolf().fit(log_returns)`; the fitted covariance matrix is returned and passed to ComputeService for optimization.
- **Universe:** The backend requests universe stats and market data for the chosen universe; Data Service returns historical returns, covariance, expected returns, prices, lot sizes, and optional cluster information.

## Strategies (ComputeService construct_portfolio)

Three strategies are implemented in `ConstructPortfolioService`:

### 1. Max Sharpe (`max_sharpe`)

- **Primary:** **skfolio** `MeanRisk` with `ObjectiveFunction.MAXIMIZE_RATIO` (maximize Sharpe with a risk-free rate). Fitted on the historical returns matrix; min/max weights and daily risk-free rate are passed.
- **Fallback:** If MeanRisk fails or returns invalid weights, we fall back to **ERC (Equal Risk Contribution)** using the same covariance matrix and long-only bounds (see `methodology-risk-parity.md`).

### 2. Hierarchical Risk Parity (`hrp`)

- **Primary:** **skfolio** `HierarchicalRiskParity` fitted on historical returns, with min/max weights.
- **Fallback:** Equal weight \(1/n\) if HRP fails.
- See `methodology-hrp.md`.

### 3. Max Calmar (`max_calmar`)

- **Two-stage:**  
  1. **Warm start:** Max Sharpe (same as above); if it fails, use equal weights.  
  2. **Refinement:** SLSQP optimization to maximize Calmar ratio (CAGR / |Max Drawdown|) using historical log-returns; long-only, sum of weights = 1.
- **Fallback:** If the Calmar step fails, we return the Max Sharpe weights and set `fallback_used: "max_sharpe"`.
- See `methodology-calmar.md`.

## Position sizing and rounding

- After optimization, weights are converted to **positions** (quantities and values) using current prices and **lot sizes**. Residual cash is reported.
- **Metrics:** Sharpe, volatility, max drawdown, etc., are computed from the same historical returns and final weights.

## Apply step

- The skill and API support an explicit **apply** step: after the user sees the proposed weights/positions, they confirm and the backend creates a **new portfolio snapshot** with those positions. The skill instructs the bot to ask for confirmation before applying.

## References

- **Ledoit–Wolf:** Ledoit, O. & Wolf, M. (2004). A well-conditioned estimator for large-dimensional covariance matrices. *Journal of Multivariate Analysis* 88(2), 365–411.  
- **Max Sharpe (skfolio):** Mean-variance ratio optimization; see skfolio documentation.  
- **HRP:** de Prado (2016); see `methodology-hrp.md`.  
- **Calmar:** See `methodology-calmar.md`.

For a consolidated list, see `references/academic-references.md`.
