# VaR and CVaR Methodology (RiskOfficer Implementation)

This document describes how Value at Risk (VaR) and Conditional VaR (CVaR / Expected Shortfall) are calculated in RiskOfficer. All calculations run in the **RiskOfficer backend**; portfolio returns are built from position weights and historical prices (log-returns where applicable).

## VaR: Three Methods

We support three methods, selectable via the API parameter `method`: `historical`, `parametric`, `garch`.

### 1. Historical VaR

- **Definition:** VaR is the loss level that would be exceeded with probability \(1 - \alpha\) (e.g. 5% for 95% confidence) under the **empirical distribution** of past portfolio returns.
- **Implementation:** Portfolio daily returns are computed from historical prices and current weights. Only **dates where all tickers have data** are used (inner-join alignment); no zero-fill is applied, so that differing history lengths across tickers do not bias the return series. We take the \((1 - \alpha)\) percentile of this return series (e.g. 5th percentile for 95% VaR). VaR in currency units is:
  \[
  \text{VaR}_{\text{abs}} = -\bigl(\text{percentile of returns}\bigr) \times \text{calculation base}.
  \]
- **Calculation base:** We use an **adaptive base** so that VaR/CVaR are expressed relative to a stable denominator. The logic (see `_get_calculation_base` in risk_service) is:
  1. **Notional capital:** If the user provides a notional capital, that is used.
  2. **Gross exposure** is used when: net equity ≤ 0 (short-dominant), or leverage > 3× (gross / |net equity|), or net equity < 25% of gross (market-neutral). This follows GIPS/CFA guidelines and Barth & Monin (2020) so that percentage risk does not blow up for leveraged/short portfolios.
  3. **Net equity** (long − short) is used otherwise.
- **Output names:** `calculation_base_used` can be `"Notional Capital (User-defined)"`, `"Gross Exposure (High Leverage)"`, `"Gross Exposure (Market Neutral)"`, or `"Net Equity"`.
- **Output:** `var_absolute`, `var_percent`, `var_percent_of_portfolio`, plus metadata (calculation_base_used, confidence).
- **Typical use:** No distributional assumption; good when history is representative. Default in the skill is `historical`.

### 2. Parametric VaR (Variance–Covariance)

- **Definition:** Portfolio return is assumed **normal**. VaR is derived from the mean and standard deviation of portfolio returns.
- **Implementation:** Mean and standard deviation of daily portfolio returns are computed. For confidence \(\alpha\), we use the normal quantile \(z = \Phi^{-1}(1-\alpha)\) (e.g. ≈ −1.645 for 95%). Then:
  \[
  \text{VaR}_{\text{abs}} = -z \cdot \sigma_{\text{daily}} \cdot \text{calculation base}.
  \]
  The mean is not used for the standard short-horizon VaR (focus on volatility).
- **Zero volatility:** If standard deviation is zero, VaR is returned as 0.
- **Output:** Same shape as historical, plus `mean_return`, `std_return`, `z_score`.

### 3. GARCH(1,1) VaR

- **Definition:** Conditional volatility is modelled with **GARCH(1,1)**; VaR uses the one-step-ahead conditional standard deviation, then scaled to the requested horizon.
- **Implementation:**
  - We fit GARCH(1,1) to portfolio daily returns using the `arch` library (`arch_model(..., vol="GARCH", p=1, q=1)`).
  - One-day conditional volatility \(\sigma_{t+1}\) is taken from the model forecast.
  - For a horizon of \(h\) days we use the square-root-of-time rule: \(\sigma_h = \sigma_{t+1} \sqrt{h}\) (see e.g. RiskMetrics, Hansen & Lunde (2005)).
  - VaR at confidence \(\alpha\):
    \[
    \text{VaR}_{\text{abs}} = -z \cdot \sigma_h \cdot \text{calculation base}.
    \]
- **Data requirements:** At least **100** observations recommended. If fewer, we fall back to **ARCH(1)** (GARCH with q=0). If GARCH(1,1) fails to converge, we also fall back to ARCH(1).
- **Output:** Same as parametric, plus `conditional_volatility`, `model_params` (omega, alpha, beta), and optionally `fallback: "ARCH(1)"`.

## CVaR (Expected Shortfall)

- **Definition:** CVaR is the **expected loss given that the loss exceeds the VaR threshold** (tail average).
- **Implementation (historical):**
  - The \((1-\alpha)\) percentile of portfolio returns defines the VaR threshold.
  - We take all returns **below** this threshold and compute their mean.
  - CVaR in currency units: \(\text{CVaR}_{\text{abs}} = -\bigl(\text{mean of tail returns}\bigr) \times \text{calculation base}\).
- **Empty tail:** If no return falls below the threshold, CVaR is set equal to VaR (threshold loss).
- **Output:** `cvar_absolute`, `cvar_percent`, `cvar_percent_of_portfolio`, `var_threshold`, plus calculation base metadata.

## Risk contributions (Euler allocation)

- For **historical** VaR we use **CVaR (Expected Shortfall) contributions** so that they add up to portfolio CVaR.
- For **parametric** and **garch** we use **VaR contributions** (marginal contribution to VaR); for GARCH, the conditional volatility is already reflected in the portfolio VaR, and contributions reuse the same parametric-style logic.

## References (academic)

- **Historical / parametric VaR:** Jorion, P., *Value at Risk*, 3rd ed. McGraw-Hill.
- **GARCH:** Bollerslev, T. (1986). Generalized Autoregressive Conditional Heteroskedasticity. *Journal of Econometrics* 31, 307–327.  
  Implementation: `arch` (Python) — GARCH(1,1), fallback ARCH(1).
- **Square-root-of-time for multi-day VaR:** RiskMetrics Technical Document; Hansen, P.R. & Lunde, A. (2005). A forecast comparison of volatility models. *Journal of Applied Econometrics* 20(7), 873–889.
- **CVaR:** Rockafellar, R.T. & Uryasev, S. (2000). Optimization of conditional value-at-risk. *Journal of Risk* 2, 21–42.

- **Calculation base (adaptive):** GIPS Standards 2.A.7; CFA Institute (2015) Hedge Fund Performance Measurement Guidelines; Barth, D., Monin, P. (2020). Leverage and Risk in Hedge Funds (SEC Form PF). Thresholds: leverage 3×, net/gross 25%.

For a single consolidated list of papers and links, see `references/academic-references.md`.
