---
name: riskofficer
description: Portfolio risk management and analytics. Use when user asks to calculate VaR, run Monte Carlo, stress test, optimize with Risk Parity / Calmar / Black-Litterman, run pre-trade check, check sector concentration, manage portfolios, or analyze cross-portfolio correlation. Also covers ticker search, broker sync, batch portfolio creation, and portfolio comparison.
metadata: {"openclaw":{"requires":{"env":["RISK_OFFICER_TOKEN"]},"primaryEnv":"RISK_OFFICER_TOKEN","emoji":"📊","homepage":"https://riskofficer.tech"}}
---

## RiskOfficer Portfolio Management

Connects to the RiskOfficer API to manage investment portfolios and calculate financial risk metrics.

**Required:** One environment variable — `RISK_OFFICER_TOKEN` (create in RiskOfficer app → Settings → API Keys). No other env vars or binaries are required.

**Source:** Official skill repository: [github.com/mib424242/riskofficer-openclaw-skill](https://github.com/mib424242/riskofficer-openclaw-skill). Product: [riskofficer.tech](https://riskofficer.tech). The token is issued only by the RiskOfficer app; this skill does not collect or store credentials.

### Credentials and token handling

- **This skill does not store or log your token.** The token is sent only in the HTTP `Authorization` header to `api.riskofficer.tech`; it is not written to disk, logged, or sent elsewhere. Where you store the token (environment variable or `~/.openclaw/openclaw.json`) is entirely under your control.
- **Prefer** setting `RISK_OFFICER_TOKEN` as an environment variable for the session rather than saving it in `openclaw.json`. If you use `openclaw.json`, restrict file permissions and be aware which agents or users can read that file.
- **RiskOfficer currently issues account-level tokens** (no scoped tokens). Create a token named for this skill (e.g. "OpenClaw") and revoke it in the RiskOfficer app if you stop using the skill.
- **Token scope:** The token allows the skill to access your RiskOfficer data (portfolios, risk calculations, broker-synced positions for read-only analysis). Revoke or rotate the token if you need to revoke access.
- **Verify links:** Confirm that [github.com/mib424242/riskofficer-openclaw-skill](https://github.com/mib424242/riskofficer-openclaw-skill) and [riskofficer.tech](https://riskofficer.tech) match the publisher you trust before installing or providing a token.

### Scope: analysis and research only (virtual portfolios)

**All portfolio data and operations in this skill take place inside RiskOfficer’s own environment.** Portfolios you create, edit, or optimize here are **virtual** — they are used for analysis and research only. The agent can:

- **Read** your portfolios (including those synced from brokers) to show positions, history, and risk metrics  
- **Create and change** virtual/manual portfolios and run optimizations **inside RiskOfficer**  
- **Run calculations** (VaR, Monte Carlo, stress tests) on these portfolios  

**Nothing in this skill places or executes real orders** in your broker account. Broker sync is read-only for analysis; any rebalancing or trading in the real account is done by you in your broker’s app or in RiskOfficer’s own flows, not by the assistant. The token is used only to access RiskOfficer’s API for this analytical and research use.

### Setup

1. Open RiskOfficer app → Settings → API Keys
2. Create a new token named "OpenClaw"
3. Set environment variable: `RISK_OFFICER_TOKEN=ro_pat_...`

Or configure in `~/.openclaw/openclaw.json`:
```json
{
  "skills": {
    "entries": {
      "riskofficer": {
        "enabled": true,
        "apiKey": "ro_pat_..."
      }
    }
  }
}
```

### API Base URL

```
https://api.riskofficer.tech/api/v1
```

All requests require: `Authorization: Bearer ${RISK_OFFICER_TOKEN}`

### Currency policy

- **Supported currencies:** **RUB** and **USD** only. No EUR/CNY/other in API contracts for base or analysis currency.
- **FX source:** All exchange rates are **CBR (Central Bank of Russia)** via Data Service (MOEX/CBR). There is no alternative provider.
- **Single currency per portfolio:** Each portfolio must contain assets in one currency (all MOEX or all US). Mixed-currency portfolios are not supported; create separate portfolios.
- **Aggregated view:** User chooses `base_currency` (RUB or USD); sub-portfolios in the other currency are converted using CBR rates.

---

## Available Commands

### Ticker Search

#### Search Tickers
Use this **before creating or editing any portfolio** to validate ticker symbols and get their currency/exchange info. Also use when the user mentions a company name instead of a ticker.

```bash
curl -s "https://api.riskofficer.tech/api/v1/tickers/search?q=Apple&limit=10&locale=en" \
  -H "Authorization: Bearer ${RISK_OFFICER_TOKEN}"
```

**Query params:**
- `q` (optional): search query — by ticker, name, or full name (case-insensitive). Omit to get popular tickers sorted by popularity.
- `limit` (optional, default 20, max 50): number of results
- `include_prices` (optional, default `false`): include `current_price`, `price_change_percent`, `price_change_absolute`, `price_date`
- `locale` (optional, default `ru`): `en` for English names, `ru` for Russian names
- `exchange` (optional): filter by exchange — `MOEX`, `NYSE`, `NASDAQ`, `CRYPTO`

**Response:** `tickers` array, each with: `ticker`, `name`, `full_name`, `instrument_type`, `currency`, `exchange`, `popularity_score`, `isin`.

**Instrument types:** `share`, `bond`, `etf`, `futures`, `futures_continuous` (e.g. BR, SI on MOEX), `currency`, `crypto`

**Key rules:**
- Always use ticker search to resolve company names → ticker symbols (e.g. "Apple" → "AAPL", "Sberbank" → "SBER")
- Use `currency` field from the result to check same-currency constraint before adding to a portfolio
- MOEX futures: searching "BR" or "SI" returns the continuous contract, not individual contracts (BRF6, SIM5)
- Use `include_prices=true` to show current price when user asks "how much is X worth?"

```bash
# Search by company name (English)
curl -s "https://api.riskofficer.tech/api/v1/tickers/search?q=Gazprom&locale=en&limit=5" \
  -H "Authorization: Bearer ${RISK_OFFICER_TOKEN}"

# Search by Russian name
curl -s "https://api.riskofficer.tech/api/v1/tickers/search?q=%D0%93%D0%B0%D0%B7%D0%BF%D1%80%D0%BE%D0%BC&locale=ru&limit=5" \
  -H "Authorization: Bearer ${RISK_OFFICER_TOKEN}"

# Get current price for a ticker
curl -s "https://api.riskofficer.tech/api/v1/tickers/search?q=AAPL&include_prices=true" \
  -H "Authorization: Bearer ${RISK_OFFICER_TOKEN}"

# Get popular tickers (no query param)
curl -s "https://api.riskofficer.tech/api/v1/tickers/search?limit=10&include_prices=true" \
  -H "Authorization: Bearer ${RISK_OFFICER_TOKEN}"

# Filter by exchange
curl -s "https://api.riskofficer.tech/api/v1/tickers/search?q=SBER&exchange=MOEX" \
  -H "Authorization: Bearer ${RISK_OFFICER_TOKEN}"
```

#### Get Historical Ticker Prices
When the user asks about price history, chart data, or trends for specific assets:

```bash
curl -s "https://api.riskofficer.tech/api/v1/tickers/historical?tickers=SBER,GAZP,AAPL&days=30" \
  -H "Authorization: Bearer ${RISK_OFFICER_TOKEN}"
```

**Query params:** `tickers` (required, comma-separated, max 50), `days` (optional, default 7, max 252 trading days).

**Response:** `data` object keyed by ticker symbol, each with:
- `prices`: array of `{date, close}` objects
- `current_price`, `price_change_percent`, `price_change_absolute`

---

### Portfolio Management

#### List Portfolios
When the user asks to see their portfolios or wants an overview:

```bash
curl -s "https://api.riskofficer.tech/api/v1/portfolios/list" \
  -H "Authorization: Bearer ${RISK_OFFICER_TOKEN}"
```

**Query params:** `portfolio_type` (optional): `"production"` (manual + live brokers), `"sandbox"` (broker sandbox only), `"all"` (default).

Response: array of portfolios with `snapshot_id`, `name`, `total_value`, `currency`, `positions_count`, `broker`, `sandbox`, `active_snapshot_id` (UUID or null — if set, risk calculations use this historical snapshot instead of the latest).

#### Get Portfolio Details
When the user wants to see positions in a specific portfolio:

```bash
curl -s "https://api.riskofficer.tech/api/v1/portfolio/snapshot/{snapshot_id}" \
  -H "Authorization: Bearer ${RISK_OFFICER_TOKEN}"
```

Response: `name`, `total_value`, `currency`, `positions` (array with `ticker`, `quantity`, `current_price`, `value`, `weight`, `avg_price`).

#### Get Portfolio History
When the user asks how their portfolio changed over time or wants to browse past snapshots:

```bash
curl -s "https://api.riskofficer.tech/api/v1/portfolio/history?days=30" \
  -H "Authorization: Bearer ${RISK_OFFICER_TOKEN}"
```

**Query params:** `days` (optional, default 30, range 1–365).

Response: `snapshots` array with `snapshot_id`, `timestamp`, `total_value`, `positions_count`, `sync_source`, `type` (`aggregated`/`manual`/`broker`), `name`, `broker`, `sandbox`.

#### Get Snapshot Diff (compare two portfolio versions)
When the user wants to compare two portfolio states (e.g. before/after rebalancing, or two dates):

```bash
curl -s "https://api.riskofficer.tech/api/v1/portfolio/snapshot/{snapshot_id}/diff?compare_to={other_snapshot_id}" \
  -H "Authorization: Bearer ${RISK_OFFICER_TOKEN}"
```

Response: `added`/`removed`/`modified` positions, `total_value_delta`. Both snapshots must belong to the user.

#### Get Aggregated Portfolio
When the user asks for their total or combined portfolio across all accounts:

```bash
curl -s "https://api.riskofficer.tech/api/v1/portfolio/aggregated?type=all" \
  -H "Authorization: Bearer ${RISK_OFFICER_TOKEN}"
```

**Query params:**
- `type=production` — manual + broker live accounts
- `type=sandbox` — broker sandbox only
- `type=all` — everything (default)

**Response:**
- `portfolio.positions` — all positions merged across portfolios
- `portfolio.total_value` — total in base currency
- `portfolio.currency` — base currency (`RUB` or `USD`)
- `portfolio.sources_count` — number of portfolios aggregated
- `exchange_rates` (optional): `USD_RUB`, `EUR_RUB`, `CNY_RUB`, `rate_date`, `rate_source` (always `"CBR"`), `base_currency`, `fx_quality` (`"live"` = from CBR/cache, `"default"` = static fallback used when CBR unavailable, `"none"` = no conversion)
- `warnings` — e.g. mixed-currency positions, FX fallback used
- `data_quality` (optional): `fx_coverage` (share of FX lookups with live rate), `fx_live_count`, `fx_default_count`, `fx_unavailable_count`, `portfolios_included`, `portfolios_excluded` — for observability of aggregation and FX usage

**Example response:**
```json
{
  "portfolio": {
    "positions": [
      {"ticker": "SBER", "quantity": 150, "value": 42795, "sources": ["T-Bank", "Manual"]},
      {"ticker": "AAPL", "quantity": 10, "value": 189500, "original_currency": "USD"}
    ],
    "total_value": 1500000,
    "currency": "RUB",
    "sources_count": 3
  },
  "snapshot_id": "uuid-of-aggregated"
}
```

Positions in different currencies are automatically converted using **CBR (Central Bank of Russia)** rates. Only RUB and USD are supported; each sub-portfolio must have assets in a single currency.

#### Change Base Currency (Aggregated Portfolio)
When the user wants to see the aggregated portfolio in a different currency:

```bash
curl -s -X PATCH "https://api.riskofficer.tech/api/v1/portfolio/{aggregated_snapshot_id}/settings" \
  -H "Authorization: Bearer ${RISK_OFFICER_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"base_currency": "USD"}'
```

**Supported currencies:** `RUB`, `USD`. The aggregated portfolio recalculates automatically after change.

**User prompt examples:**
- "Show everything in dollars" / "Покажи всё в долларах" → `base_currency: "USD"`
- "Switch to rubles" / "Переведи в рубли" → `base_currency: "RUB"`

#### Include/Exclude Portfolio from Aggregated
When the user wants to exclude a specific portfolio from total calculations:

```bash
curl -s -X PATCH "https://api.riskofficer.tech/api/v1/portfolio/{snapshot_id}/settings" \
  -H "Authorization: Bearer ${RISK_OFFICER_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"include_in_aggregated": false}'
```

**User prompt examples:**
- "Exclude sandbox from total" / "Не учитывай песочницу в общем портфеле"
- "Remove demo portfolio from calculations" / "Убери демо-портфель из расчёта"

#### Create Manual Portfolio
When the user wants to create a new portfolio with specific positions:

```bash
curl -s -X POST "https://api.riskofficer.tech/api/v1/portfolio/manual" \
  -H "Authorization: Bearer ${RISK_OFFICER_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Portfolio",
    "positions": [
      {"ticker": "SBER", "quantity": 100},
      {"ticker": "GAZP", "quantity": 50, "avg_price": 148.0},
      {"ticker": "YNDX", "quantity": -20}
    ]
  }'
```

**Fields:**
- `ticker` (required): ticker symbol. **Always use `/tickers/search` first** to validate and check currency.
- `quantity` (required): number of shares. **Negative = short position** (e.g. `-20` = short 20 shares).
- `avg_price` (optional): average purchase/entry price for P&L tracking. If omitted on new portfolio → uses current market price. If omitted on edit → inherits from previous snapshot.

**Query params:** `locale` (optional, default `ru`) — affects asset name resolution.

**Currency policy (platform-wide):** Only **RUB** and **USD** are supported. All FX rates come from **CBR (Central Bank of Russia)** via Data Service (MOEX/CBR). There is no choice of FX provider — it is always CBR.

**IMPORTANT — Single Currency Rule:**
All assets in one portfolio must be in the **same currency**.
- RUB assets (MOEX): SBER, GAZP, LKOH, YNDX, etc.
- USD assets (NYSE/NASDAQ): AAPL, MSFT, GOOGL, TSLA, etc.
Cannot mix currencies in a single portfolio! Suggest creating separate portfolios.

**Short positions:**
- Use negative `quantity` for shorts (e.g. `{"ticker": "GAZP", "quantity": -50}`)
- Long + short in the same portfolio is supported (long-short portfolio)
- When optimizing a long-short portfolio, use `optimization_mode: "preserve_directions"` to keep shorts

#### Update Portfolio (Add/Remove Positions)
When the user wants to modify an existing portfolio:

1. Get current positions:
```bash
curl -s "https://api.riskofficer.tech/api/v1/portfolio/snapshot/{snapshot_id}" \
  -H "Authorization: Bearer ${RISK_OFFICER_TOKEN}"
```

2. Repost with the same name and updated full positions list:
```bash
curl -s -X POST "https://api.riskofficer.tech/api/v1/portfolio/manual" \
  -H "Authorization: Bearer ${RISK_OFFICER_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"name": "<same name>", "positions": [<complete updated list>]}'
```

**IMPORTANT:** Always show the user what will change and ask for confirmation before updating. `avg_price` is preserved from previous snapshot unless explicitly specified.

#### Delete Manual Portfolio
When the user wants to delete/remove a manual portfolio entirely:

```bash
curl -s -X DELETE "https://api.riskofficer.tech/api/v1/portfolio/manual/My%20Portfolio" \
  -H "Authorization: Bearer ${RISK_OFFICER_TOKEN}"
```

- Portfolio name must be URL-encoded
- Archives **all** snapshots for that portfolio — **irreversible**
- **ALWAYS confirm with the user before deleting** — cannot be undone
- Response: `archived_snapshots` count, `portfolio_name`, `message`

#### Delete Broker Portfolio Snapshots
When the user wants to clear broker portfolio history without disconnecting the broker:

```bash
curl -s -X DELETE "https://api.riskofficer.tech/api/v1/portfolio/broker/tinkoff?sandbox=false" \
  -H "Authorization: Bearer ${RISK_OFFICER_TOKEN}"
```

- `sandbox=true` for sandbox portfolio, `sandbox=false` for live/production
- Archives snapshots only; broker connection stays active
- Next sync will create a new snapshot
- **ALWAYS confirm before deleting**

---

### Broker Integration

#### List Connected Brokers
When the user asks about their broker connections:

```bash
curl -s "https://api.riskofficer.tech/api/v1/brokers/connections" \
  -H "Authorization: Bearer ${RISK_OFFICER_TOKEN}"
```

#### List Available Broker Providers
When the user asks what brokers are supported:

```bash
curl -s "https://api.riskofficer.tech/api/v1/brokers/available" \
  -H "Authorization: Bearer ${RISK_OFFICER_TOKEN}"
```

#### Sync Portfolio from Broker
When the user wants to refresh/update their portfolio from a connected broker:

```bash
curl -s -X POST "https://api.riskofficer.tech/api/v1/portfolio/proxy/broker/{broker}/portfolio" \
  -H "Authorization: Bearer ${RISK_OFFICER_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"sandbox": false}'
```

- `{broker}`: `tinkoff` or `alfa`
- `sandbox`: `false` for live account, `true` for Tinkoff sandbox

If response is `400` with `missing_api_key`, the broker is not connected. Guide the user:
1. Get API token from https://www.tbank.ru/invest/settings/api/
2. Open RiskOfficer app → Settings → Brokers → Connect Tinkoff
3. Paste token and connect

#### Disconnect Broker
When the user wants to remove a broker connection:

```bash
curl -s -X DELETE "https://api.riskofficer.tech/api/v1/brokers/connections/tinkoff?sandbox=false" \
  -H "Authorization: Bearer ${RISK_OFFICER_TOKEN}"
```

- `sandbox=false` for live connection, `sandbox=true` for sandbox
- Removes the connection and its saved API key; portfolio snapshot **history is preserved**
- To also delete snapshot history, first use `DELETE /portfolio/broker/{broker}?sandbox=false`
- **ALWAYS confirm before disconnecting** — reconnection requires the mobile app

**Difference between the two delete endpoints:**

| Action | DELETE /portfolio/broker/{id} | DELETE /brokers/connections/{id} |
|--------|-------------------------------|----------------------------------|
| Deletes snapshots | ✅ Yes (archives history) | ❌ No (history kept) |
| Deletes connection | ❌ No | ✅ Yes |
| Can sync again without re-connecting | ✅ Yes | ❌ No |

---

### Active Snapshot Selection

By default, all risk calculations use the **latest** snapshot. You can pin a historical snapshot to run calculations on a past portfolio state — useful for backtesting risk or comparing "before vs after" rebalancing.

#### Set Active Snapshot
When the user wants to run risk calculations on a historical version of their portfolio:

```bash
curl -s -X PATCH "https://api.riskofficer.tech/api/v1/portfolio/active-snapshot" \
  -H "Authorization: Bearer ${RISK_OFFICER_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"portfolio_key": "manual:My Portfolio", "snapshot_id": "{historical_snapshot_id}"}'
```

**`portfolio_key` format:**
| Portfolio type | Format | Example |
|---|---|---|
| Aggregated | `aggregated` | `"aggregated"` |
| Manual | `manual:{name}` | `"manual:My Portfolio"` |
| Broker live | `broker:{broker_id}:false` | `"broker:tinkoff:false"` |
| Broker sandbox | `broker:{broker_id}:true` | `"broker:tinkoff:true"` |

**Workflow:**
1. `GET /portfolio/history?days=90` → pick snapshot by date
2. `PATCH /portfolio/active-snapshot` with chosen `snapshot_id` + `portfolio_key`
3. Run VaR / Monte Carlo — uses selected historical snapshot
4. Reset when done (see below)

**In `/portfolios/list`:** `active_snapshot_id` field shows the pinned snapshot (null = using latest).

#### Reset Active Snapshot to Latest

```bash
curl -s -X DELETE "https://api.riskofficer.tech/api/v1/portfolio/active-snapshot?portfolio_key=manual:My%20Portfolio" \
  -H "Authorization: Bearer ${RISK_OFFICER_TOKEN}"
```

**User prompt examples:**
- "Calculate risk for my portfolio as it was a month ago" / "Посчитай риски как было месяц назад" → set active snapshot
- "Go back to current portfolio" / "Сбрось на текущий портфель" → DELETE active-snapshot

---

### Risk Calculations

#### Calculate VaR (FREE)
When the user asks to calculate risk, VaR, or risk metrics:

```bash
curl -s -X POST "https://api.riskofficer.tech/api/v1/risk/calculate-var" \
  -H "Authorization: Bearer ${RISK_OFFICER_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "portfolio_snapshot_id": "{snapshot_id}",
    "method": "historical",
    "confidence": 0.95,
    "horizon_days": 1,
    "force_recalc": false
  }'
```

**Parameters:**
- `method`: `"historical"` (default, recommended), `"parametric"`, or `"garch"`
- `confidence`: confidence level, default `0.95` (range 0.01–0.99)
- `horizon_days`: forecast horizon, default `1` (range 1–30 days)
- `force_recalc` (optional, default `false`): set `true` to bypass cache and force a fresh calculation (use when user says "recalculate" or "refresh")

**Response:**
- If `reused_existing: true` and `status: "done"` → result is already in response (`var_95`, `cvar_95`, `sharpe_ratio`), no polling needed
- Otherwise → returns `calculation_id`, poll for result:

```bash
curl -s "https://api.riskofficer.tech/api/v1/risk/calculation/{calculation_id}" \
  -H "Authorization: Bearer ${RISK_OFFICER_TOKEN}"
```

Wait until `status: "done"`, then present results.

#### Get VaR / Risk Calculation History
When the user asks for past risk calculations:

```bash
curl -s "https://api.riskofficer.tech/api/v1/risk/history?limit=50" \
  -H "Authorization: Bearer ${RISK_OFFICER_TOKEN}"
```

**Query params:** `limit` (optional, default 50, max 100).

Response: `calculations` array with `calculation_id`, `portfolio_snapshot_id`, `status`, `method`, `var_95`, `cvar_95`, `sharpe_ratio`, `created_at`, `completed_at`.

#### Run Monte Carlo (QUANT — currently free for all users)
When the user asks for a Monte Carlo simulation:

```bash
curl -s -X POST "https://api.riskofficer.tech/api/v1/risk/monte-carlo" \
  -H "Authorization: Bearer ${RISK_OFFICER_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "portfolio_snapshot_id": "{snapshot_id}",
    "simulations": 1000,
    "horizon_days": 365,
    "model": "gbm",
    "force_recalc": false
  }'
```

**Parameters:**
- `simulations`: number of paths, default `1000` (range 100–10000)
- `horizon_days`: forecast horizon, default `365` (range 1–365)
- `model`: `"gbm"` (Geometric Brownian Motion — **only this is implemented**) or `"garch"` (accepted but not yet implemented; will behave as GBM)
- `confidence_levels` (optional): array of percentiles, default `[0.05, 0.50, 0.95]`
- `force_recalc` (optional, default `false`): bypass cache

Poll: `GET /api/v1/risk/monte-carlo/{simulation_id}`

#### Run Stress Test (QUANT — currently free for all users)
When the user asks for a stress test against historical crises:

First, get available crises:
```bash
curl -s "https://api.riskofficer.tech/api/v1/risk/stress-test/crises" \
  -H "Authorization: Bearer ${RISK_OFFICER_TOKEN}"
```

Then run:
```bash
curl -s -X POST "https://api.riskofficer.tech/api/v1/risk/stress-test" \
  -H "Authorization: Bearer ${RISK_OFFICER_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "portfolio_snapshot_id": "{snapshot_id}",
    "crisis": "covid_19",
    "force_recalc": false
  }'
```

**Parameters:**
- `crisis`: crisis scenario ID from `/stress-test/crises` (e.g. `covid_19`, `2008_crisis`)
- `force_recalc` (optional, default `false`): bypass cache

Poll: `GET /api/v1/risk/stress-test/{stress_test_id}`

---

### Portfolio Optimization (QUANT — currently free for all users)

#### Risk Parity Optimization
When the user asks to optimize their portfolio or balance risks:

```bash
curl -s -X POST "https://api.riskofficer.tech/api/v1/portfolio/{snapshot_id}/optimize" \
  -H "Authorization: Bearer ${RISK_OFFICER_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "optimization_mode": "preserve_directions",
    "constraints": {
      "max_weight": 0.30,
      "min_weight": 0.02
    },
    "options": {
      "risk_measure": "variance",
      "turnover_limit": 0.3,
      "turnover_penalty": 0.1
    }
  }'
```

**`optimization_mode`:**
- `"long_only"`: all weights ≥ 0 (shorts are flipped to long before optimization)
- `"preserve_directions"`: keeps long/short directions as-is (default)
- `"unconstrained"`: weights can change sign freely

**`options.risk_measure`** (optional, default `"variance"`):
- `"variance"`: classic ERC (Maillard, Roncalli, Teïletche 2010)
- `"cvar"`: CVaR Risk Budgeting via skfolio (convex optimization, CLARABEL solver). Better for fat-tailed distributions

**Turnover constraints** (optional, require `current_weights` in portfolio):
- `turnover_limit`: hard constraint — `sum(|w_new - w_old|) <= limit`. Optimizer stays within budget
- `turnover_penalty`: soft L1 penalty in objective — trades off improvement vs turnover cost

Poll: `GET /api/v1/portfolio/optimizations/{optimization_id}`
Result: `GET /api/v1/portfolio/optimizations/{optimization_id}/result`

**IMPORTANT:** For optimization, use `active_snapshot_id || snapshot_id` from the portfolio list entry (respects the user's selected historical snapshot if set).

#### Calmar Ratio Optimization
When the user asks to maximize Calmar Ratio (CAGR / |Max Drawdown|):

**Requires 200+ trading days of price history per ticker** (backend requests 252 days). If the portfolio has short history, suggest Risk Parity instead.

```bash
curl -s -X POST "https://api.riskofficer.tech/api/v1/portfolio/{snapshot_id}/optimize-calmar" \
  -H "Authorization: Bearer ${RISK_OFFICER_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "optimization_mode": "long_only",
    "constraints": {
      "max_weight": 0.50,
      "min_weight": 0.05,
      "min_expected_return": 0.0,
      "max_drawdown_limit": 0.15,
      "min_calmar_target": 0.5
    },
    "options": {
      "turnover_limit": 0.3,
      "turnover_penalty": 0.1
    }
  }'
```

Poll: `GET /api/v1/portfolio/optimizations/{optimization_id}` (check `optimization_type === "calmar_ratio"`).
Result: `GET /api/v1/portfolio/optimizations/{optimization_id}/result` — includes `current_metrics` and `optimized_metrics` (CAGR, max drawdown, Calmar ratio, recovery time in days).
Apply: same as Risk Parity → `POST /api/v1/portfolio/optimizations/{optimization_id}/apply`.

**Error `INSUFFICIENT_HISTORY`:** not enough price history → explain the 200+ days requirement and suggest Risk Parity as alternative.

#### Apply Optimization
**IMPORTANT:** Always show the full rebalancing plan and ask for explicit user confirmation before applying!

```bash
curl -s -X POST "https://api.riskofficer.tech/api/v1/portfolio/optimizations/{optimization_id}/apply" \
  -H "Authorization: Bearer ${RISK_OFFICER_TOKEN}"
```

Response: `new_snapshot_id`. Can only be applied once per optimization.

#### Black-Litterman Optimization (QUANT)
When the user has views (expected returns with confidence) on specific assets and wants an optimal portfolio:

```bash
curl -s -X POST "https://api.riskofficer.tech/api/v1/portfolio/optimize-bl" \
  -H "Authorization: Bearer ${RISK_OFFICER_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "tickers": ["SBER", "GAZP", "LKOH", "ROSN"],
    "views": [
      {"ticker": "SBER", "expected_return": 0.15, "confidence": 0.7},
      {"ticker": "ROSN", "expected_return": -0.05, "confidence": 0.5}
    ],
    "constraints": { ... },
    "options": { "risk_free_rate": 0.16, "tau": 0.05 },
    "portfolio_snapshot_id": null,
    "currency": "RUB"
  }'
```

**Parameters:**
- `tickers` (required, min 2): ticker symbols for universe
- `views` (required, min 1): investor views — `expected_return` is annual (0.15 = 15%), `confidence` 0.01–1.0 (Idzorek method scales Omega)
- `constraints.weight_bound_lower`: min weight per asset (negative allows shorts, default -0.15)
- `constraints.weight_bound_upper`: max weight per asset (default 0.25)
- `constraints.max_gross_exposure`: max sum(|w_i|) (default 2.0)
- `constraints.target_net_exposure`: exact sum(w_i) target (e.g. 1.0 for fully invested). Mutually exclusive with `max_net_exposure`
- `constraints.max_net_exposure`: max |sum(w_i)|
- `constraints.turnover_limit` / `constraints.turnover_penalty`: same as Risk Parity (see above). **To enforce turnover vs current portfolio**, pass `portfolio_snapshot_id` (see below).
- `options.risk_free_rate`: annual risk-free rate (default 0.16 for MOEX)
- `options.tau`: uncertainty scaling (default 0.05)
- `portfolio_snapshot_id` (optional): snapshot UUID of the portfolio to compute *current weights* from. When set, turnover constraints are applied relative to this portfolio. Omit for greenfield optimization.
- `currency` (optional, default `"RUB"`): market data universe — `"RUB"` or `"USD"`. Use USD for US-listed tickers.

**Response:** `optimization_id`, `status: "pending"`. Poll via `GET /portfolio/optimizations/{id}`, result via `GET /portfolio/optimizations/{id}/result`.

**Result contains:** `target_portfolio` (tickers with weights and directions), `metrics` (expected return, volatility, Sharpe, net/gross exposure, portfolio_type), `bl_posterior_returns`.

**Apply:** `POST /portfolio/optimizations/{id}/apply` — creates a new manual portfolio "BL Optimized".

**User prompt examples:**
- "I think Sber will return 15% with high confidence, optimize my portfolio" → BL with view
- "Build a long-short portfolio: long on banks, short on oil" → BL with positive/negative views
- "Optimize with Black-Litterman" → ask user for views (expected returns + confidence per ticker)

---

### Pre-Trade Check (FREE)

#### Run Pre-Trade Risk Check
When the user or AI agent wants to validate a target portfolio before execution. **VaR is computed using historical method** (empirical distribution from market data).

```bash
curl -s -X POST "https://api.riskofficer.tech/api/v1/risk/pre-trade-check" \
  -H "Authorization: Bearer ${RISK_OFFICER_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "target_portfolio": {"SBER": 0.15, "GAZP": 0.10, "LKOH": 0.12, "ROSN": -0.08},
    "amount": 1000000,
    "currency": "RUB",
    "constraints": {
      "max_var_pct": 5.0,
      "weight_bound_upper": 0.25,
      "weight_bound_lower": -0.15,
      "max_gross_exposure": 2.0,
      "max_net_exposure": 0.5,
      "max_sector_concentration": 0.35,
      "sector_limits": {"Energy": 0.30, "Finance": 0.25}
    }
  }'
```

**Parameters:**
- `target_portfolio` (required): dict of `{ticker: weight}` — negative weight = short
- `amount` (required): portfolio notional value for VaR calculation
- `currency` (optional, default `"RUB"`): currency of the portfolio — `"RUB"` or `"USD"`. Determines which market data universe is used for historical VaR.
- `constraints` (optional):
  - `max_var_pct`: maximum allowed VaR as % (e.g. 5.0 = 5%)
  - `weight_bound_upper` / `weight_bound_lower`: per-position weight limits
  - `max_gross_exposure` / `max_net_exposure`: exposure limits
  - `max_sector_concentration`: global maximum sector weight (e.g. 0.35 = no single sector above 35%). Sector data is fetched from Data Service. If Data Service is unavailable, a warning is returned instead of an error.
  - `sector_limits`: per-sector max weight as `{sector_name: max_weight}` (e.g. `{"Energy": 0.30}`). Case-insensitive matching. Can be used together with `max_sector_concentration`.

**Response (synchronous, no polling):**
```json
{
  "verdict": "pass",
  "num_positions": 4,
  "max_position_weight": 0.15,
  "var_95_pct": 3.21,
  "currency": "RUB",
  "exposure_metrics": {
    "net_exposure": 0.29,
    "gross_exposure": 0.45,
    "long_exposure": 0.37,
    "short_exposure": 0.08
  },
  "constraint_violations": [],
  "sector_exposures": {
    "Energy": 0.488889,
    "Finance": 0.333333,
    "Other": 0.177778
  },
  "result_hash": "0x...",
  "data_quality": {
    "tickers_requested": 4,
    "tickers_with_data": 4,
    "tickers_missing": [],
    "total_dates": 252,
    "dates_dropped": 0
  }
}
```
**`sector_exposures`** (optional, present when `max_sector_concentration` or `sector_limits` is set): maps sector name to its share of gross exposure. Formula: `sector_exposure[s] = sum(abs(w[t]) for t in sector) / gross_exposure`. For long/short portfolios, `abs(weight)` is used so both long and short contribute proportionally.

**`data_quality`** (optional): `tickers_requested`, `tickers_with_data`, `tickers_missing`, `total_dates`, `dates_dropped` — reflects alignment of historical data used for VaR (inner-join by date; no zero-fill). May also include `tickers_without_sector` if sector metadata was unavailable for some tickers.

**`verdict`:** `"pass"` (all OK), `"fail"` (hard constraint violations), `"warning"` (soft issues)

**User prompt examples:**
- "Check if this portfolio is safe" / "Проверь портфель перед торговлей"
- "Run pre-trade check for: SBER 15%, GAZP 10%, ROSN -8%"
- After BL optimization: "Check the result before applying"

---

### Batch Portfolio Creation (FREE)

#### Create Multiple Portfolios
When the user or platform wants to create several portfolios at once:

```bash
curl -s -X POST "https://api.riskofficer.tech/api/v1/portfolio/manual/batch" \
  -H "Authorization: Bearer ${RISK_OFFICER_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "portfolios": [
      {
        "name": "Pod Alpha",
        "positions": [{"ticker": "SBER", "quantity": 100}, {"ticker": "GAZP", "quantity": -50}],
        "currency": "RUB"
      },
      {
        "name": "Pod Beta",
        "positions": [{"ticker": "LKOH", "quantity": 30}],
        "currency": "RUB"
      }
    ]
  }'
```

**Response:** array of `{name, snapshot_id, status}` per portfolio. Partial success is possible — one portfolio can fail without affecting others.

---

### Cross-Portfolio Correlation (QUANT)

#### Compute PnL Correlation Between Portfolios
When the user asks about diversification across portfolios/pods or re-correlation risk:

```bash
curl -s -X POST "https://api.riskofficer.tech/api/v1/portfolio/correlation" \
  -H "Authorization: Bearer ${RISK_OFFICER_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "portfolio_ids": null,
    "window_days": 60,
    "include_crisis_regime": true,
    "analysis_currency": "RUB"
  }'
```

**Parameters:**
- `portfolio_ids` (optional): list of snapshot UUIDs. `null` = all user's portfolios (latest snapshot per portfolio)
- `window_days` (optional, default 60, range 20–252): rolling window for PnL correlation
- `include_crisis_regime` (optional, default false): compare normal vs crisis correlations (crisis = days with aggregate PnL < μ-2σ)
- `analysis_currency` (optional, default `"RUB"`): currency to normalize all PnL series into before correlation — `"RUB"` or `"USD"`. Use when portfolios are in different currencies; rates are CBR historical.

**Response:** async — poll via `GET /portfolio/optimizations/{id}`, result via `GET /portfolio/optimizations/{id}/result`.

**Result contains:**
```json
{
  "result_data": {
    "portfolio_names": ["Pod Alpha", "Pod Beta", "T-Bank"],
    "correlation_matrix": [[1.0, 0.35, 0.12], [0.35, 1.0, 0.48], [0.12, 0.48, 1.0]],
    "pairs": [ ... ],
    "avg_pairwise_correlation": 0.317,
    "analysis_currency": "RUB",
    "fx_source": "CBR",
    "fx_coverage": 1.0,
    "fx_conversions": { "Pod Alpha": "USD->RUB", "Pod Beta": "RUB" },
    "crisis_regime": {
      "available": true,
      "avg_normal_correlation": 0.25,
      "avg_crisis_correlation": 0.72,
      "re_correlation_delta": 0.47,
      "n_crisis_days": 8,
      "n_normal_days": 52
    }
  }
}
```

**Key metric:** `re_correlation_delta` — how much correlations increase during stress. > 0.2 = significant re-correlation risk (pods lose diversification under stress).

**User prompt examples:**
- "How correlated are my portfolios?" / "Какая корреляция между портфелями?"
- "Check re-correlation risk" / "Center Book analysis"
- "Compare normal vs crisis correlations"

---

### Per-Portfolio Risk Settings (FREE)

#### Set Individual VaR Threshold
When the user wants a different risk alert threshold for a specific portfolio:

```bash
curl -s -X PATCH "https://api.riskofficer.tech/api/v1/portfolio/{snapshot_id}/settings" \
  -H "Authorization: Bearer ${RISK_OFFICER_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"risk_threshold_var": 5.0}'
```

**Parameters:**
- `risk_threshold_var`: VaR threshold in percent (5.0 = 5%). When VaR exceeds this, a push notification / alert is triggered for this specific portfolio

**User prompt examples:**
- "Set VaR alert at 3% for my conservative portfolio"
- "Raise the risk threshold to 7% for the aggressive pod"

---

### Feature Flags

#### Get Feature Flags
Check which features are enabled:

```bash
curl -s "https://api.riskofficer.tech/api/v1/feature-flags" \
  -H "Authorization: Bearer ${RISK_OFFICER_TOKEN}"
```

**Response:**
```json
{
  "websocket_enabled": true,
  "subscription_required_for_quant": false,
  "pre_trade_check_enabled": true,
  "black_litterman_enabled": true,
  "cross_correlation_enabled": true,
  "cvar_risk_parity_enabled": true
}
```

---

### Subscription Status

> **Note:** Quant subscription is currently **FREE for all users**. All features work without payment.

```bash
curl -s "https://api.riskofficer.tech/api/v1/subscription/status" \
  -H "Authorization: Bearer ${RISK_OFFICER_TOKEN}"
```

Currently all users return `has_subscription: true`.

---

## Async Operations

VaR, Monte Carlo, Stress Test, and Optimization are **asynchronous**.

**Polling pattern:**
1. POST endpoint → get `calculation_id` / `simulation_id` / `optimization_id`
2. Poll GET endpoint every 2–3 seconds
3. Check `status`:
   - `pending` or `processing` → keep polling
   - `done` → present results
   - `failed` → show error

**Typical times:**
| Operation | Typical time |
|-----------|-------------|
| VaR | 3–10 seconds |
| Monte Carlo | 10–30 seconds |
| Stress Test | 5–15 seconds |
| Optimization | 10–30 seconds |

**User communication:**
- Show "Calculating..." immediately after starting
- If polling takes > 10 seconds: "Still calculating, please wait..."
- Always show the final result or error

---

## Important Rules

0. **Virtual / analytical scope:** Portfolios and all operations (create, optimize, delete, sync) exist only inside RiskOfficer. This skill is for analysis and research; it does not place or execute real broker orders.

1. **Single Currency Rule (manual/broker portfolios):** Each portfolio must contain same-currency assets. Cannot mix SBER (RUB) with AAPL (USD). Aggregated portfolio is the exception — it auto-converts using CBR rates.

2. **Short Positions:** Negative `quantity` creates a short. For long-short portfolios, use `optimization_mode: "preserve_directions"` to keep short positions when optimizing.

3. **Always search tickers first:** Before creating or editing portfolios, use `/tickers/search` to validate ticker symbols and check their currency.

4. **Confirmations:** Always show what will change and ask for confirmation before: updating/deleting portfolios, applying optimizations, disconnecting brokers. These actions can be irreversible.

5. **Async:** VaR, Monte Carlo, Stress Test, and Optimization are async. Poll for results.

6. **Subscription:** Monte Carlo, Stress Test, and Optimization are Quant features (currently free). VaR is always free.

7. **Broker Integration:** Users must connect brokers via the RiskOfficer mobile app first. Cannot connect via chat (security).

8. **Error Handling:**
   - `401 Unauthorized` → Token invalid or expired; user needs to recreate it
   - `403 subscription_required` → Need Quant subscription (currently free for all)
   - `400 missing_api_key` → Broker not connected via app
   - `400 currency_mismatch` → Mixed currencies in a single portfolio
   - `400 INSUFFICIENT_HISTORY` → Not enough price history for Calmar (200+ trading days needed); suggest Risk Parity
   - `400 MVO infeasible` → BL constraints too tight; suggest relaxing weight bounds or exposure limits
   - `404 Not Found` → Portfolio or snapshot not found (may have been deleted)
   - `429 Too Many Requests` → Optimization rate limit reached (per-tier: free 30/h, quant 100/h, pro 1000/h)

9. **Active Snapshot:** `active_snapshot_id` from `/portfolios/list` takes priority over `snapshot_id` when running calculations. Use `active_snapshot_id || snapshot_id` for optimization calls.

10. **result_hash (ERC-8004):** Optimize and VaR responses include `result_hash` — a keccak256 hash for deterministic verification. Informational; safe to ignore unless building on-chain verification.

11. **Pre-trade check before apply:** For AI agents building autonomous trade pipelines, always run `POST /risk/pre-trade-check` on the BL optimization result before calling apply. This catches constraint violations the optimizer may not enforce (sector limits, VaR limits). Use `currency: "RUB"` or `"USD"` to match the portfolio (default RUB).

12. **Currency in APIs:** Pre-trade accepts optional `currency` (RUB/USD). BL accepts optional `currency` (market data universe) and `portfolio_snapshot_id` (for turnover vs current portfolio). Correlation accepts optional `analysis_currency` (RUB/USD) — PnL is normalized to this currency using CBR historical rates.

**Methodology and references:** This skill includes a `references/` folder with implementation notes and academic sources. When users ask *how* VaR, Risk Parity, Calmar, Black-Litterman, pre-trade check, correlation, or aggregated portfolio are implemented, you can cite the matching file: `methodology-var.md`, `methodology-risk-parity.md`, `methodology-calmar.md`, `methodology-black-litterman.md`, `methodology-pre-trade.md`, `methodology-correlation.md`, `methodology-aggregation.md`, `methodology-hrp.md`, `methodology-monte-carlo.md`, `methodology-stress-test.md`, `methodology-metrics.md`, `methodology-auto-portfolio.md`. For a consolidated list of papers and libraries, see `references/academic-references.md`.

---

## Example Conversations

### User wants to see their portfolios
"Show my portfolios" / "Покажи мои портфели"
→ `GET /portfolios/list`
→ Format nicely: name, total value, positions count, currency, last updated

### User wants the combined total across all accounts
"Show total portfolio" / "Total across all accounts" / "Сколько у меня всего?"
→ `GET /portfolio/aggregated?type=all`
→ Show total value, merged positions, number of sources
→ Note positions converted from other currencies

### User wants to change display currency
"Show everything in dollars" / "Покажи в долларах"
→ `PATCH /portfolio/{aggregated_id}/settings` with `{"base_currency": "USD"}`
→ `GET /portfolio/aggregated` again
→ Show portfolio in new currency

### User asks about a company by name (not ticker)
"Add Sberbank to my portfolio" / "What's the ticker for Gazprom?" / "Добавь Газпром"
→ `GET /tickers/search?q=Sberbank&locale=en`
→ Found: ticker `SBER`, currency `RUB`, exchange `MOEX`
→ Confirm with user, then proceed to create/update portfolio

### User asks for a current price
"How much is Tesla?" / "Сколько стоит Газпром?"
→ `GET /tickers/search?q=TSLA&include_prices=true`
→ Show `current_price`, `price_change_percent`, exchange

### User wants to create a long-short portfolio
"Create portfolio: long SBER 100 shares, short YNDX 50 shares"
→ `GET /tickers/search` for both tickers → confirm both are RUB/MOEX
→ `POST /portfolio/manual` with `[{"ticker":"SBER","quantity":100},{"ticker":"YNDX","quantity":-50}]`
→ Show created portfolio with positions

### User wants to analyze portfolio risk
"What are the risks of my portfolio?" / "Analyze the risk"
→ `GET /portfolios/list` → find portfolio
→ `POST /risk/calculate-var` with `method: "historical"`
→ Poll until done
→ Present VaR, CVaR, volatility, risk contributions per ticker
→ Offer optimization if risks are concentrated

### User wants Calmar optimization
"Optimize by Calmar ratio" / "Maximize return per drawdown" / "Оптимизируй по Калмару"
→ Get `snapshot_id` from portfolios list
→ `POST /portfolio/{snapshot_id}/optimize-calmar`
→ If `INSUFFICIENT_HISTORY`: explain 200+ trading days needed, suggest Risk Parity
→ Poll until done
→ Show `current_metrics` vs `optimized_metrics` (Calmar ratio, CAGR, max drawdown)
→ Show rebalancing plan and ask for confirmation before apply

### User wants Monte Carlo simulation
"Run Monte Carlo for 1 year" / "Запусти Монте-Карло"
→ `POST /risk/monte-carlo` with `simulations: 1000, horizon_days: 365, model: "gbm"`
→ Poll until done
→ Present percentile projections (5th, 50th, 95th)

### User wants a stress test
"Run stress test" / "How would my portfolio survive 2008 crisis?"
→ `GET /risk/stress-test/crises` → show available scenarios
→ User picks crisis (or default to most relevant)
→ `POST /risk/stress-test`
→ Poll, then present results

### User wants to calculate risk for a historical portfolio
"Calculate risk for my portfolio as it was last month" / "Посчитай риски как было месяц назад"
→ `GET /portfolio/history?days=45` → find snapshot from ~30 days ago
→ `PATCH /portfolio/active-snapshot` with that `snapshot_id` and `portfolio_key`
→ `POST /risk/calculate-var` → poll → present results
→ Offer to reset: `DELETE /portfolio/active-snapshot`

### User tries to mix currencies
"Add Apple to my RUB portfolio"
→ `GET /tickers/search?q=AAPL` → currency: USD, exchange: NASDAQ
→ Portfolio is RUB → cannot mix
→ Explain the single-currency rule, suggest creating a separate USD portfolio

### User wants to compare two portfolio snapshots
"What changed in my portfolio?" / "Compare to last week" / "Что изменилось в портфеле?"
→ `GET /portfolio/history` → get two snapshot IDs
→ `GET /portfolio/snapshot/{id}/diff?compare_to={other_id}`
→ Present added/removed/modified positions, total value delta

### User wants to delete a portfolio
"Delete my test portfolio" / "Удали портфель 'Тест'"
→ Confirm: "This will permanently delete all N snapshots for 'Test'. Cannot be undone. Continue?"
→ On confirmation: `DELETE /portfolio/manual/Test`
→ Report `archived_snapshots` count

### User wants to disconnect a broker
"Disconnect Tinkoff" / "Отключи Тинькофф"
→ Confirm: "This will remove the Tinkoff connection. Portfolio history will be kept. Continue?"
→ On confirmation: `DELETE /brokers/connections/tinkoff?sandbox=false`
→ Inform that reconnection requires the mobile app

### User wants Black-Litterman optimization
"I think Sber will return 15% and Gazprom 10%" / "Оптимизируй по Блэку-Литтерману"
→ Collect views: ask for tickers, expected returns, and confidence
→ `POST /portfolio/optimize-bl` with views + constraints
→ Poll until done
→ Show target portfolio (tickers, weights, directions), metrics (Sharpe, expected return, volatility)
→ Ask confirmation before `POST /portfolio/optimizations/{id}/apply`

### User wants to check a portfolio before trading
"Check this before I trade" / "Проверь портфель перед исполнением"
→ `POST /risk/pre-trade-check` with target weights + amount + constraints
→ Show verdict (pass/fail/warning), VaR, exposure metrics, violations
→ If "fail" → explain which constraints are violated

### User wants to create multiple portfolios at once
"Create 3 pod portfolios" / "Создай несколько портфелей"
→ `POST /portfolio/manual/batch` with array of portfolios
→ Show per-portfolio status (created/error)

### User asks about cross-portfolio correlation
"How diversified are my pods?" / "Какая корреляция между портфелями?"
→ `POST /portfolio/correlation` with `include_crisis_regime: true`
→ Poll until done
→ Show avg pairwise correlation, matrix, pairs detail
→ If crisis data available: show normal vs crisis correlation and re-correlation delta
→ If `re_correlation_delta > 0.2`: warn about re-correlation risk

### User wants CVaR Risk Parity
"Optimize with CVaR" / "Оптимизируй по CVaR"
→ `POST /portfolio/{snapshot_id}/optimize` with `options: { risk_measure: "cvar" }`
→ Explain: CVaR is better for fat-tailed distributions, accounts for tail risk beyond VaR
