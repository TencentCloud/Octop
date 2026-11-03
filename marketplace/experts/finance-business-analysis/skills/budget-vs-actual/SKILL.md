---
name: budget-vs-actual
description: >
  Monthly and quarterly budget vs. actual variance analysis for businesses. Compare planned vs. realized
  revenue, expenses, and margins. Identify favorable/unfavorable variances, root-cause material variances
  (>5% or >$X threshold), produce management commentary, and generate actionable reforecast recommendations.
  Outputs: variance table, waterfall narrative, and updated rolling forecast. Use when a CFO, controller,
  or analyst needs to close the books for a period, explain results to management or investors, or update
  the annual operating plan mid-year.
  NOT for: building budgets from scratch (use startup-financial-model), tax preparation, transactional
  bookkeeping, or real-time cash tracking.
version: 1.0.0
author: PrecisionLedger
tags:
  - finance
  - accounting
  - budgeting
  - variance
  - FP&A
  - management-reporting
---

# Budget vs. Actual Variance Analysis Skill

Perform rigorous period-end budget vs. actual analysis. This skill guides Sam Ledger through pulling actuals, comparing against budget, calculating variances, identifying root causes, drafting management commentary, and producing a reforecast update.

---

## When to Use This Skill

**Trigger phrases:**
- "Run budget vs. actual for [month/quarter]"
- "Explain our variances this month"
- "Why did we miss/beat revenue?"
- "Prepare the management report for [period]"
- "Update the rolling forecast based on actuals"
- "Board needs BvA commentary"
- "What drove the EBITDA miss?"
- "Reforecast the rest of the year"

**NOT for:**
- Building the original budget — use `startup-financial-model`
- Tax filings or tax provision work — use compliance workflows
- Real-time bookkeeping or transaction categorization — use `qbo-automation` or `expense-categorization`
- Multi-entity consolidations with intercompany eliminations (requires dedicated consolidation tooling)
- Strategic planning or multi-year long-range planning (LRP)

---

## Core Concepts

### Variance Types

| Type | Formula | Meaning |
|---|---|---|
| Absolute Variance | Actual − Budget | Dollar difference |
| Percentage Variance | (Actual − Budget) / Budget × 100 | Magnitude relative to budget |
| Favorable (F) | Revenue: Actual > Budget / Expense: Actual < Budget | Better than plan |
| Unfavorable (U) | Revenue: Actual < Budget / Expense: Actual > Budget | Worse than plan |

### Materiality Thresholds (Default — customize per engagement)

```
Revenue line items:    ≥ $5,000 or ≥ 5% of budgeted line → investigate
Expense line items:    ≥ $2,500 or ≥ 10% of budgeted line → investigate
Total EBITDA:          ≥ $10,000 or ≥ 5% of budgeted EBITDA → board commentary required
YTD cumulative:        Carry forward monthly variances; flag if YTD > full-year materiality
```

### Variance Root Causes — Taxonomy

**Revenue Variances:**
- Volume variance: More/fewer units/customers than planned
- Price/rate variance: ASP or pricing differed from assumption
- Mix variance: Different product/segment mix than modeled
- Timing variance: Deal closed in wrong period (pulled forward or pushed out)
- New vs. existing: Over/under-performance in specific cohort

**Expense Variances:**
- Headcount timing: Hire later/earlier than budgeted
- Contractor/vendor: Over/under-spend vs. plan
- One-time items: Non-recurring expenses not in budget
- Volume-linked: COGS, sales commission scaled with revenue
- Pricing/inflation: Vendor price changes not modeled

---

## Step-by-Step Workflow

### Step 1: Collect Inputs

```
Required:
□ Period (Month, Quarter, YTD)
□ Budget/forecast file (CSV, Sheets, or typed data)
□ Actuals file or QBO export (same period, same account mapping)
□ Chart of Accounts mapping (if budget and actuals use different labels)
□ Materiality threshold (use defaults if not specified)
□ Audience (internal management, board, investors)

Optional:
□ Prior period actuals (for trend context)
□ Prior year same period (for YoY context)
□ Existing narrative from last period
```

### Step 2: Normalize Data

Map actuals to budget line items. Standard P&L mapping:

```
Budget Label          → QBO/Actuals Equivalent
-------------------------------------------------
Revenue               → Total Income
COGS                  → Cost of Goods Sold / Direct Costs
Gross Profit          → (calculated)
Sales & Marketing     → Advertising, Sales Commissions, Marketing Expenses
R&D / Engineering     → Contract Labor (tech), Software Tools
G&A                   → Payroll (admin), Legal, Accounting, Insurance
Total OpEx            → (sum of above)
EBITDA                → (Gross Profit − Total OpEx)
```

### Step 3: Calculate Variances

For each line item:

```python
# Variance calculation logic
for each line_item:
    absolute_var = actual - budget
    pct_var = (actual - budget) / abs(budget) * 100  # handle $0 budget edge case
    
    if is_revenue_line:
        favorable = actual > budget
    else:  # expense line
        favorable = actual < budget
    
    flag = abs(pct_var) >= threshold_pct or abs(absolute_var) >= threshold_dollar
```

### Step 4: Build the Variance Table

**Standard Output Format:**

```
PERIOD: March 2026 | Budget vs. Actual

Line Item          | Budget    | Actual    | $ Var     | % Var  | F/U | Flag
-------------------|-----------|-----------|-----------|--------|-----|------
REVENUE            |           |           |           |        |     |
  Product Revenue  | $120,000  | $108,500  | ($11,500) | -9.6%  |  U  |  ⚠️
  Service Revenue  |  $30,000  |  $34,200  |  $4,200   | +14.0% |  F  |  ⚠️
  Total Revenue    | $150,000  | $142,700  |  ($7,300) | -4.9%  |  U  |
                   |           |           |           |        |     |
COGS               |  $45,000  |  $43,100  |  $1,900   | +4.2%  |  F  |
Gross Profit       | $105,000  |  $99,600  |  ($5,400) | -5.1%  |  U  |  ⚠️
Gross Margin %     |   70.0%   |   69.8%   |   -0.2pp  |        |     |
                   |           |           |           |        |     |
OPERATING EXPENSES |           |           |           |        |     |
  S&M              |  $25,000  |  $27,400  |  $2,400   | +9.6%  |  U  |  ⚠️
  R&D              |  $20,000  |  $18,500  | ($1,500)  | -7.5%  |  F  |
  G&A              |  $15,000  |  $16,200  |  $1,200   | +8.0%  |  U  |
  Total OpEx       |  $60,000  |  $62,100  |  $2,100   | +3.5%  |  U  |
                   |           |           |           |        |     |
EBITDA             |  $45,000  |  $37,500  |  ($7,500) | -16.7% |  U  |  🚨
EBITDA Margin      |   30.0%   |   26.3%   |   -3.7pp  |        |     |
```

### Step 5: Root Cause Analysis

For each flagged variance, drill down:

**Revenue miss example (Product Revenue -$11,500 / -9.6%):**
```
Root cause analysis:
- Volume: Closed 8 deals vs. 10 budgeted = -2 deals
- Price: Avg deal size $13,563 vs. $12,000 budget → +$1,563 per deal (favorable mix)
- Net: 2 fewer deals × $12,000 ASP = -$24,000 volume miss
       + 8 deals × $1,563 price premium = +$12,500 price/mix offset
       = ($11,500) net as reported ✓

Assessment: Volume issue, not pricing. Sales pipeline slipped — 2 deals moved to April.
```

**S&M overrun example ($2,400 / +9.6% unfavorable):**
```
Root cause analysis:
- Planned: $15k paid ads + $10k salaries
- Actual: $15k paid ads + $10k salaries + $2,400 conference registration (unbudgeted)
- Classification: One-time / non-recurring — will not repeat next month
Assessment: Benign. Budget for next year; no action required.
```

### Step 6: Management Commentary

Draft in this structure for each material variance:

```
[LINE ITEM] — [VARIANCE DIRECTION] by $[AMOUNT] ([PERCENT]%)

WHAT: [What the number shows in plain English]
WHY:  [Root cause — specific, not generic]
ACTION: [What we're doing about it, or why no action needed]
OUTLOOK: [Impact on full-year forecast]
```

**Example commentary:**

> **EBITDA — Unfavorable $7,500 (-16.7%)**
>
> WHAT: March EBITDA of $37,500 missed the $45,000 budget by $7,500, driven by a revenue shortfall partially offset by lower R&D spend.
>
> WHY: Product revenue missed by $11,500 due to 2 enterprise deals slipping to April (pipeline confirmed, not lost). S&M ran $2,400 over budget on a one-time conference registration. R&D came in $1,500 favorable as one contractor engagement started late.
>
> ACTION: The 2 slipped deals are expected to close in April (both in final contract stage). Conference registration expensed — not recurring. R&D contractor now onboarded; expect full burn starting April.
>
> OUTLOOK: Revising Q2 forecast to front-load the 2 slipped deals. Full-year EBITDA forecast unchanged at $540,000.

### Step 7: Update Rolling Forecast

After analyzing actuals, update the remainder of the year:

```
Reforecast logic:
1. Lock actuals for closed periods (do not re-budget history)
2. Roll forward: identify permanent vs. timing variances
   - Timing: shift to next period (deal slippage, late hire)
   - Permanent: adjust full-year assumption (market softness, new run rate)
3. Update full-year totals:
   - YTD actuals + remaining budget (adjusted)
   - Recalculate runway/cash if applicable
4. Flag changes from last forecast:
   - Revenue: +/- $X vs. prior forecast
   - EBITDA: +/- $X vs. prior forecast
   - Cash EOY: +/- $X vs. prior forecast
```

**Reforecast summary table:**

```
                   | Original  | Prior     | Current   | Change
                   | Budget    | Forecast  | Forecast  | (vs Prior)
-------------------|-----------|-----------|-----------|----------
Full-Year Revenue  | $1,800,000| $1,750,000| $1,762,000| +$12,000
Full-Year EBITDA   |  $540,000 |  $510,000 |  $512,500 |  +$2,500
Year-End Cash      |  $850,000 |  $790,000 |  $793,000 |  +$3,000
```

---

## Output Formats

### 1. Management Report (Narrative + Table)
Full commentary with variance table, root causes, and reforecast. For CFO/CEO/Board use.

### 2. Quick BvA Flash (1 Page)
Three sections only:
- Headline KPIs: Revenue, Gross Margin, EBITDA, Cash (actual vs budget, one line each)
- Top 3 variances with one-sentence explanations
- Reforecast change vs. prior

### 3. Structured JSON (for downstream processing)
```json
{
  "period": "2026-03",
  "period_type": "month",
  "generated_at": "2026-04-02",
  "summary": {
    "total_revenue_budget": 150000,
    "total_revenue_actual": 142700,
    "total_revenue_variance_abs": -7300,
    "total_revenue_variance_pct": -4.87,
    "ebitda_budget": 45000,
    "ebitda_actual": 37500,
    "ebitda_variance_abs": -7500,
    "ebitda_variance_pct": -16.67
  },
  "line_items": [
    {
      "name": "Product Revenue",
      "budget": 120000,
      "actual": 108500,
      "variance_abs": -11500,
      "variance_pct": -9.58,
      "favorable": false,
      "material": true,
      "root_cause": "2 enterprise deals slipped to April (pipeline confirmed)",
      "action": "Deals expected April close; no change to full-year forecast"
    }
  ],
  "reforecast": {
    "full_year_revenue_original": 1800000,
    "full_year_revenue_current": 1762000,
    "full_year_ebitda_original": 540000,
    "full_year_ebitda_current": 512500
  }
}
```

---

## QBO Integration Workflow

When actuals come from QuickBooks Online (via `qbo-automation`):

```
1. Export: QBO → Reports → Profit & Loss (select period, compare to prior)
2. Or via API: GET /v3/company/{id}/reports/ProfitAndLoss?start_date=&end_date=&summarize_column_by=Month
3. Map QBO account names to budget line items using COA mapping table
4. Validate totals: QBO Revenue total must match sum of line items (catch mapping errors)
5. Feed into variance calculation above
```

**Common QBO mapping pitfalls:**
- QBO may break out subcategories that are lumped in budget → aggregate up
- Owner draws in QBO are not an expense → exclude from P&L analysis
- Payroll taxes may be in separate QBO accounts → roll up to loaded headcount cost

---

## Handling Common Edge Cases

### Budget is $0 for a line item that has actuals
```
Never divide by zero. Instead:
  variance_pct = "N/A (no budget)"
  Flag as material if actual > materiality dollar threshold
  Commentary: "Unbudgeted spend of $X in [account]"
```

### Prior period restatements
```
If actuals from a prior period changed:
  Flag the restatement explicitly
  Show: prior reported → restated → delta
  Update YTD accordingly
  Note audit trail in commentary
```

### Multiple departments / cost centers
```
Run variance analysis at:
  1. Consolidated company level (always)
  2. Department level (if cost center tracking exists)
  Highlight cross-departmental offsets where applicable
  (e.g., R&D under-spend masked by G&A over-spend at total level)
```

### Seasonal businesses
```
Include YoY comparison alongside BvA:
  March 2026 Actual vs. March 2026 Budget (primary)
  March 2026 Actual vs. March 2025 Actual (context)
  Flag: is variance seasonal (expected) or structural (new issue)?
```

---

## Metrics Glossary

| Term | Definition |
|---|---|
| BvA | Budget vs. Actual |
| F | Favorable (better than plan) |
| U | Unfavorable (worse than plan) |
| pp | Percentage points (for margin comparisons) |
| YTD | Year-to-date (cumulative from Jan 1) |
| QTD | Quarter-to-date |
| MTD | Month-to-date |
| Reforecast | Updated projection for remainder of year, based on actuals to date |
| Flash | Quick preliminary BvA before full close (estimates OK) |
| Hard close | Final, locked actuals (no further adjustments) |
| Soft close | Preliminary actuals, subject to accruals and adjustments |

---

## Integration Points

- **`qbo-automation`** — Pull actuals directly from QuickBooks Online
- **`startup-financial-model`** — Original budget/forecast data source
- **`kpi-alert-system`** — Trigger alerts when variance thresholds are breached
- **`report-generator`** — Format BvA output into board-ready PDF or deck
- **`financial-analysis-agent`** — Deep-dive trend analysis when root cause isn't obvious

---

## Example Intake Prompt

> "March is closed. Budget had us at $150k revenue and $45k EBITDA. Actuals came in at $142k revenue and $37.5k EBITDA. Product was $11.5k short — two enterprise deals slipped. Service came in $4.2k over. S&M ran $2.4k over on a conference. R&D was $1.5k under — contractor started late. Draft the BvA table, root cause summary, and board commentary. Flag reforecast impact."

Sam will:
1. Build the variance table with F/U flags and materiality indicators
2. Write root-cause summaries for all flagged lines
3. Draft management commentary in WHAT/WHY/ACTION/OUTLOOK format
4. Produce the reforecast delta (timing vs. structural adjustments)
5. Output structured JSON if downstream processing is needed
