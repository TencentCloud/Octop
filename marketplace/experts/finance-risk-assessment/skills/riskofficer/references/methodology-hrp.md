# Hierarchical Risk Parity (HRP) Methodology

This document describes how **Hierarchical Risk Parity (HRP)** is implemented in RiskOfficer for portfolio construction (auto-generate flow).

## Role in the product

- HRP is one of the **construct-portfolio** strategies: we build a **new** long-only portfolio from a universe of tickers and precomputed market data (covariance, expected returns, historical returns). It is **not** used for rebalancing an existing portfolio; for that we use Risk Parity (ERC) or Calmar.
- **Endpoint:** `POST /portfolio/auto-generate` with `strategy: "hrp"` (or the construct-portfolio API with strategy `hrp`).

## Implementation

- **Library:** **skfolio** — we use the built-in **HierarchicalRiskParity** estimator.
- **Input:** A matrix of **historical returns** (e.g. log-returns) and optional **min_weight** / **max_weight** constraints.
- **Call:**  
  `HierarchicalRiskParity(min_weights=min_weight, max_weights=max_weight).fit(hist_returns)`  
  then we take `estimator.weights_`.
- **Output:** A vector of long-only weights that sum to 1, satisfying the min/max bounds. No explicit covariance input is required; the estimator uses the structure of returns (and internally, distance/clustering) to allocate risk in a hierarchical way.
- **Fallback:** If HRP fails (e.g. invalid or non-finite weights), we fall back to **equal weight** \(1/n\).

## Data flow

- **Data Service** (or equivalent) provides the universe and precomputed market data (e.g. covariance, expected returns, historical returns). For auto-generate, the backend requests this data and passes it to ComputeService.
- **ComputeService** runs the chosen strategy; for HRP it only needs the historical returns matrix and constraints.

## Academic background

- **de Prado, M. (2016).** Building Diversified Portfolios that Outperform Out-of-Sample. *Journal of Portfolio Management* 42(4), 59–69.  
  Introduces HRP: hierarchical clustering of assets and recursive bisection to allocate weights so that risk is spread across the hierarchy.
- **skfolio:** Implements HRP (and related methods) in a scikit-learn style API; we rely on its default linkage and allocation rules.

For more references, see `references/academic-references.md`.
