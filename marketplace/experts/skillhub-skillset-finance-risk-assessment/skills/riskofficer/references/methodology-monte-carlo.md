# Monte Carlo Simulation Methodology

This document describes how **Monte Carlo** portfolio forecasts are implemented in RiskOfficer. The logic runs in the **RiskOfficer backend** (risk_service).

## Model

- **Implemented model:** **Geometric Brownian Motion (GBM)** only. The API accepts a `model` parameter (`gbm` or `garch`), but **only `gbm` is implemented**; GARCH-based Monte Carlo is not yet available.
- **GBM:** Portfolio value is modelled as  
  \[
  S(t) = S(0) \exp\bigl((\mu - \sigma^2/2)\,t + \sigma\sqrt{t}\,Z\bigr), \quad Z \sim N(0,1).
  \]
  So log-return over horizon \(t\) (in years) is \((\mu - \sigma^2/2)t + \sigma\sqrt{t}\,Z\).

## Implementation details

- **Inputs:** Portfolio snapshot (positions and value), **historical portfolio returns** (daily), horizon in days, number of **simulations** (e.g. 1000, max 10000), and **confidence levels** (e.g. 0.05, 0.50, 0.95) for percentiles.
- **Parameters:**  
  - \(\mu\) = annualized mean return = mean(daily returns) × 252.  
  - \(\sigma\) = annualized volatility = std(daily returns) × √252.  
  - Time step: \(dt = 1/252\) (one day in years).
- **Simulation:** For each horizon (e.g. 30, 90, 180, 365 days), we draw **independent** \(Z \sim N(0,1)\) of size `simulations`. Portfolio log-return over the horizon is  
  \[
  R = \mu_{\text{ann}} \cdot (n_{\text{steps}} \cdot dt) - \frac{1}{2}\sigma_{\text{ann}}^2 (n_{\text{steps}} \cdot dt) + \sigma_{\text{ann}} \sqrt{n_{\text{steps}} \cdot dt} \cdot Z.
  \]  
  Portfolio values are \(S(0) \exp(R)\). We then compute percentiles (e.g. p5, median, p95), mean, and std of simulated values.
- **Probability of loss:** For selected horizons (e.g. 30, 90, 180, 365 days), we count how many simulated portfolio values are **below** the initial portfolio value and report the fraction as “probability of loss”.
- **Minimum data:** At least **30** days of portfolio returns; otherwise the backend returns an error.

## Outputs

- **Forecast:** For each horizon step, we return median, mean, std, and percentile values (e.g. p5, p50, p95).
- **Volatility forecast:** Annualized volatility (constant in this GBM setup).
- **Probability of loss:** List of { days_ahead, probability } for key horizons.
- **Expected annualized return / volatility:** The \(\mu\) and \(\sigma\) used above.

## Async and caching

- The API returns a **simulation_id** immediately; the actual run is asynchronous (e.g. Celery). Results can be cached by (snapshot_id, horizon, simulations, model, data hash).

## References

- **GBM:** Hull, J. (2018). *Options, Futures, and Other Derivatives*, 10th ed. Pearson.  
- **Monte Carlo in risk:** Jorion, P. *Value at Risk*, 3rd ed.; standard industry practice.

See `references/academic-references.md` for more.
