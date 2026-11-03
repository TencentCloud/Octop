# RiskOfficer Skill for OpenClaw

Manage investment portfolios, calculate risk metrics (VaR, Monte Carlo, Stress Tests), and optimize allocations using Risk Parity, Calmar, or Black-Litterman — all through natural language chat. Includes pre-trade risk checks with sector concentration limits and cross-portfolio correlation analysis.

**Required:** One env var — `RISK_OFFICER_TOKEN` (create in RiskOfficer app → Settings → API Keys).  
**Source:** [github.com/mib424242/riskofficer-openclaw-skill](https://github.com/mib424242/riskofficer-openclaw-skill) · [riskofficer.tech](https://riskofficer.tech)

## Features

- **Ticker Search** — Find any stock by name or symbol (MOEX, NYSE, NASDAQ, Crypto), get current prices and currency info
- **Portfolio Management** — View, create, edit, and delete portfolios; long & short positions supported
- **Batch Portfolios** — Create multiple portfolios in one call (for multi-pod/multi-strategy setups)
- **Risk Calculations** — VaR (free, 3 methods), Monte Carlo simulation, Stress Tests against historical crises
- **Pre-Trade Check** — Validate target portfolio against VaR/exposure/weight/sector concentration constraints before trading (free)
- **Portfolio Optimization** — Risk Parity (ERC, CVaR), Calmar Ratio, Black-Litterman (views + constraints); long-only, long-short, or unconstrained; turnover constraints (soft + hard)
- **Cross-Portfolio Correlation** — PnL correlation matrix across portfolios with crisis regime analysis (re-correlation risk detection)
- **Auto Portfolio Generation** — Automatically construct optimal portfolios (Max Sharpe, HRP, Max Calmar)
- **Broker Integration** — Sync from Tinkoff/T-Bank; connect, refresh, and disconnect brokers
- **Multi-currency** — RUB/USD only; automatic CBR-rate conversion in aggregated portfolio (no other FX provider); aggregated and pre-trade responses include **data_quality** (fx_coverage, dates_dropped, etc.)
- **Active Snapshot Selection** — Run risk calculations on any historical version of your portfolio
- **Per-Portfolio Risk Alerts** — Monitoring checks each portfolio separately; VaR threshold per portfolio (or user default)
- **Pre-trade / BL / Correlation** — Optional `currency` or `analysis_currency` (RUB/USD); BL supports `portfolio_snapshot_id` for turnover constraints

## Installation

### 1. Get your API Token

1. Open RiskOfficer app on iOS
2. Go to **Settings → API Keys**
3. Create a new token named "OpenClaw"
4. Copy the token (starts with `ro_pat_...`)

### 2. Install the Skill

**Option A: Install via ClawHub (recommended)**

```bash
clawhub install riskofficer
```

Skill catalog page: [clawhub.ai/mib424242/riskofficer](https://clawhub.ai/mib424242/riskofficer)

**Option B: Clone to workspace (per-agent)**

```bash
cd ~/.openclaw/workspace/skills
git clone https://github.com/mib424242/riskofficer-openclaw-skill riskofficer
```

**Option C: Clone to managed skills (shared across all agents)**

```bash
cd ~/.openclaw/skills
git clone https://github.com/mib424242/riskofficer-openclaw-skill riskofficer
```

### 3. Configure the Token

Add to `~/.openclaw/openclaw.json`:

```json
{
  "skills": {
    "entries": {
      "riskofficer": {
        "enabled": true,
        "apiKey": "ro_pat_your_token_here"
      }
    }
  }
}
```

Or set environment variable:

```bash
export RISK_OFFICER_TOKEN="ro_pat_your_token_here"
```

## Usage Examples

```
"Show my portfolios"
"What's the current price of Tesla?"
"Find the ticker for Sberbank"
"Calculate VaR for my main portfolio"
"Run Monte Carlo simulation for 1 year"
"Run stress test — COVID scenario"
"Optimize my portfolio using Risk Parity"
"Optimize with CVaR risk budgeting"
"Optimize my portfolio by Calmar Ratio"
"I think Sber will return 15% — optimize with Black-Litterman"
"Check this portfolio before I trade"
"How correlated are my portfolios? Include crisis analysis"
"Create 3 pod portfolios at once"
"Add 50 shares of SBER to my portfolio"
"Create a long-short portfolio: long SBER 100, short YNDX 50"
"Show all my portfolios combined in USD"
"Set VaR alert at 3% for my conservative portfolio"
"Calculate risks for my portfolio as it was last month"
"Compare my portfolio to last week"
"Delete my test portfolio"
"Disconnect Tinkoff broker"

# Russian / Русский
"Покажи мои риски"
"Оптимизируй портфель по Калмару"
"Оптимизируй по Блэку-Литтерману"
"Проверь портфель перед торговлей"
"Какая корреляция между портфелями?"
"Посчитай VaR как было месяц назад"
"Добавь Газпром в портфель"
```

## Subscription

All features are **currently FREE** for all users:

| Feature | Tier |
|---------|------|
| VaR calculation (historical, parametric, GARCH) | Free |
| Pre-Trade Check | Free |
| Batch Portfolio Creation | Free |
| Per-Portfolio Risk Alerts | Free |
| Monte Carlo Simulation | Quant (free during beta) |
| Stress Testing | Quant (free during beta) |
| Portfolio Optimization (Risk Parity / CVaR / Calmar) | Quant (free during beta) |
| Black-Litterman Optimization | Quant (free during beta) |
| Cross-Portfolio Correlation | Quant (free during beta) |
| Auto Portfolio Generation | Quant (free during beta) |

## API Coverage

This skill covers the full RiskOfficer API:

| Category | Endpoints |
|----------|-----------|
| Ticker Search | Search by name/ticker/ISIN, current prices, historical data |
| Portfolio | List, snapshot, history, diff, aggregated, create, update, delete, batch create |
| Broker | Connect, list, sync, disconnect; Tinkoff and Alfa |
| Risk | VaR (3 methods), Monte Carlo, Stress Test, Pre-Trade Check, calculation history |
| Optimization | Risk Parity (ERC/CVaR), Calmar, Black-Litterman, Auto Generate; turnover constraints; long/short/unconstrained modes |
| Correlation | Cross-portfolio PnL correlation, crisis regime analysis |
| Settings | Per-portfolio risk thresholds, include/exclude from aggregated, base currency |
| Active Snapshot | Pin historical snapshot for risk calculations |
| Feature Flags | Check enabled features |
| Subscription | Check status |

**Methodology:** Implementation details and academic references (VaR, Risk Parity, Calmar, Black-Litterman, pre-trade, correlation, aggregated portfolio, HRP, Monte Carlo, stress test, metrics, auto-portfolio) are in the `references/` folder in the skill repository.

## Links

- 📂 **ClawHub:** [clawhub.ai/mib424242/riskofficer](https://clawhub.ai/mib424242/riskofficer) — `clawhub install riskofficer`
- 🔧 **GitHub:** [github.com/mib424242/riskofficer-openclaw-skill](https://github.com/mib424242/riskofficer-openclaw-skill)
- 📱 **App Store:** [RiskOfficer](https://apps.apple.com/ru/app/riskofficer/id6757360596)
- 🌐 **Website:** [riskofficer.tech](https://riskofficer.tech)
- 💬 **Forum:** [forum.riskofficer.tech](https://forum.riskofficer.tech)
- ✉️ **Support:** support@riskofficer.tech

## License

MIT

---

**Security:** This skill contains only Markdown and documented API examples (curl). No executables or scripts — compatible with ClawHub/VirusTotal scanning.

**Skill v4.3.0 — Scope disclaimer: virtual portfolios, analysis and research only; no real broker orders. Currency: RUB/USD only, CBR rates.**

---

**Synced from riskofficer backend v1.16.3**
