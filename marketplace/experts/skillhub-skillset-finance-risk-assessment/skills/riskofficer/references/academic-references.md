# Academic and Technical References

This file lists the main papers and sources that underpin RiskOfficer’s methodologies. Use it when users ask *how* we compute something or *which* methods we use; the bot can cite these and point to the matching `methodology-*.md` files.

## VaR and CVaR

- **Jorion, P.** *Value at Risk*, 3rd ed. McGraw-Hill. — Standard reference for historical, parametric, and simulation-based VaR.
- **Bollerslev, T. (1986).** Generalized Autoregressive Conditional Heteroskedasticity. *Journal of Econometrics* 31, 307–327. — GARCH(1,1).
- **RiskMetrics Technical Document** (e.g. JP Morgan / MSCI). — Square-root-of-time scaling for multi-day VaR.
- **Hansen, P.R. & Lunde, A. (2005).** A forecast comparison of volatility models. *Journal of Applied Econometrics* 20(7), 873–889. — Volatility forecasting, √T scaling.
- **Rockafellar, R.T. & Uryasev, S. (2000).** Optimization of conditional value-at-risk. *Journal of Risk* 2, 21–42. — CVaR (Expected Shortfall) definition and optimization.
- **Implementation:** Python `arch` library for GARCH(1,1) and ARCH(1) fallback.

## Risk Parity (ERC)

- **Maillard, S., Roncalli, T., Teïletche, J. (2010).** The Properties of Equally Weighted Risk Contribution Portfolios. *The Journal of Portfolio Management* 36(4), 60–70. — Equal Risk Contribution (ERC), variance-based risk contributions, no mandatory upper bounds on weights.
- **CVaR risk budgeting:** Rockafellar, R.T. & Uryasev, S. (2000). Optimization of conditional value-at-risk. *Journal of Risk* 2, 21–42. — Used for `risk_measure: "cvar"` in Risk Parity; skfolio RiskBudgeting with CLARABEL.

## Calmar and drawdown

- **Young, T. (1991).** Calmar Ratio: A Smoother Tool. *Futures*. — Calmar ratio (CAGR / |Max Drawdown|).
- **Cornuejols, G. & Tütüncü, R. (2007).** *Optimization Methods in Finance*. Cambridge University Press. — Optimization background for ratio and constraint handling.

## Sharpe ratio and portfolio metrics

- **Sharpe, W. F. (1966).** Mutual fund performance. *Journal of Business* 39(1), 119–138. — Ex-post Sharpe ratio; we use annualized (mean×252, std×√252) with optional risk-free rate.
- **Calculation base (VaR/CVaR):** GIPS Standards 2.A.7; CFA Institute (2015) Hedge Fund Performance Measurement Guidelines; Barth, D., Monin, P. (2020). Leverage and Risk in Hedge Funds (SEC Form PF). — Adaptive base: notional, gross (high leverage / market-neutral), or net equity.

## Covariance and shrinkage

- **Ledoit, O. & Wolf, M. (2004).** A well-conditioned estimator for large-dimensional covariance matrices. *Journal of Multivariate Analysis* 88(2), 365–411. — Ledoit–Wolf shrinkage (used in Data Service for covariance).

## Hierarchical Risk Parity (HRP)

- **de Prado, M. (2016).** Building Diversified Portfolios that Outperform Out-of-Sample. *Journal of Portfolio Management* 42(4), 59–69. — HRP: clustering and recursive bisection.
- **Implementation:** `skfolio` (Python) — HierarchicalRiskParity, MeanRisk.

## Black-Litterman

- **Black, F. & Litterman, R. (1992).** Global Portfolio Optimization. *Financial Analysts Journal* 48(5), 28–43. — Equilibrium prior and posterior with investor views.
- **He, G. & Litterman, R. (1999).** The intuition behind Black-Litterman model portfolios. Goldman Sachs Investment Management Research. — Omega and view uncertainty.
- **Idzorek, T. (2004).** A step-by-step guide to the Black-Litterman model. — Confidence-based scaling of view uncertainty (Omega). Implementation: ComputeService uses Idzorek method; delta auto-calibration from Data Service expected returns when available.

## Monte Carlo

- **Hull, J. (2018).** *Options, Futures, and Other Derivatives*, 10th ed. Pearson. — GBM and Monte Carlo simulation.
- **Implementation:** GBM only; portfolio-level \(\mu\) and \(\sigma\) from historical returns, 252 trading days annualization.

## Libraries

- **skfolio:** Portfolio optimization (MeanRisk, HierarchicalRiskParity, etc.).  
  https://github.com/skfolio/skfolio
- **arch:** GARCH/ARCH models in Python.  
  https://arch.readthedocs.io/
- **scipy.optimize:** SLSQP and other solvers for ERC and Calmar.

---

When answering users: prefer citing the **methodology file** (e.g. `methodology-var.md`, `methodology-risk-parity.md`, `methodology-black-litterman.md`, `methodology-pre-trade.md`, `methodology-correlation.md`, `methodology-aggregation.md`) for our exact implementation, and this file for academic and library references. If the user’s language is not English, the bot can translate the explanation while keeping paper titles and journal names in the original form.
