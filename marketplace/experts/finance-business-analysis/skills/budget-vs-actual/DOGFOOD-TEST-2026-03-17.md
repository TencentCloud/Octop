# Dogfood Test Report: budget-vs-actual Skill v1.0.0

**Date:** 2026-03-17
**Tester:** PrecisionLedger (Sam Ledger via Claude agent)
**Test Subject:** SB Paulson LLC — Jan–Feb 2026 YTD P&L
**Output Artifact:** `/clients/sb-paulson/2026_01-02_BvA_Analysis.md`

---

## Test Scenario Description

Applied the budget-vs-actual skill to a real client engagement: SB Paulson LLC, a salon/spa business generating ~$210K/month in revenue. Used actual P&L data for Jan–Feb 2026 (from QBO export) as ACTUALS. Constructed a realistic 2-month budget from scratch (no prior budget existed) and ran the full 7-step workflow as specified in SKILL.md. Tested whether the skill's instructions are sufficient for a practitioner to produce quality, actionable variance analysis.

---

## Overall Result: PARTIAL PASS

The skill produces a solid framework and the core workflow is sound. However, several gaps and ambiguities were identified that would cause problems in production use, particularly around budget construction, sign conventions, and expense F/U logic.

---

## What Worked Well

### 1. Workflow Structure (Steps 1-7) — PASS
The 7-step sequential workflow is logical and complete. Each step builds on the prior one naturally. The flow from data collection → normalization → calculation → analysis → commentary → reforecast mirrors how an actual FP&A analyst would work. No missing steps.

### 2. Variance Table Format — PASS
The template in Step 4 is clear, professional, and immediately usable. The column structure (Budget | Actual | $ Var | % Var | F/U | Flag) covers all necessary dimensions. The visual hierarchy with section headers (REVENUE, COGS, OPEX) and indentation works well in markdown.

### 3. Management Commentary Template (WHAT/WHY/ACTION/OUTLOOK) — PASS
This is the strongest part of the skill. The four-part structure forces specificity and prevents the common failure mode of vague commentary ("revenue was lower than expected"). The example in the skill is excellent — concrete numbers, named root causes, specific actions. Easy to replicate.

### 4. Root Cause Taxonomy — PASS
The revenue and expense root cause categories (Volume, Price/Rate, Mix, Timing, etc.) are comprehensive and genuinely useful. They provide a mental checklist that prevents analysts from stopping at the surface-level explanation.

### 5. Materiality Thresholds — PASS
The default thresholds (Revenue: $5K/5%, Expense: $2.5K/10%, EBITDA: $10K/5%) are reasonable and calibrated for a mid-market business. The "customize per engagement" note is appropriate. The dual threshold (dollar OR percentage) correctly catches both large-dollar and high-percentage variances.

### 6. Edge Case Handling — PASS
The $0 budget, restatement, multi-department, and seasonal business sections are practical and address real scenarios. The "never divide by zero" instruction is critical and correctly specified.

---

## What Broke or Was Missing

### Issue 1: No Guidance for Budget Construction — FAIL
**Severity: HIGH**

The skill says it's "NOT for building budgets from scratch" and points to `startup-financial-model`, but the workflow REQUIRES a budget as an input. In practice, many clients (like SB Paulson) arrive with actuals but NO formal budget. The skill provides no guidance on:
- How to construct a quick-and-dirty budget from historical actuals
- What to do when no budget exists (use prior year? use industry benchmarks?)
- Minimum viable budget structure needed for BvA to be meaningful

I had to construct the entire budget myself using domain knowledge of salon economics. This is a gap that will trip up less experienced practitioners.

**Recommended fix:** Add a "Step 0: Budget Preparation" section or a "No Budget Available" edge case that provides guidance on constructing a baseline budget from 3-6 months of actuals, industry benchmarks, or annualized run rates.

### Issue 2: Expense Variance Sign Convention Is Ambiguous — PARTIAL FAIL
**Severity: HIGH**

The variance formula in Step 3 is `absolute_var = actual - budget` universally. But the F/U logic then says expenses favorable when `actual < budget`. This creates a confusing output situation:

- For an expense that's $2,400 OVER budget: `actual - budget = +$2,400` and it's flagged Unfavorable
- For an expense that's $1,500 UNDER budget: `actual - budget = -$1,500` and it's flagged Favorable

The problem: **a negative number on an expense line is favorable, but a negative number on a revenue line is unfavorable.** The Step 4 template example shows expense overruns as positive numbers (S&M: $2,400 / +9.6% U), which is correct — but the sign convention is never explicitly stated, and it contradicts how many accounting systems present "favorable" expense variances (as positive/favorable).

In producing the SB Paulson analysis, I had to make judgment calls about sign presentation that the skill doesn't resolve. Specifically: should the table show `+$20,423 U` (actual minus budget, raw) or `($20,423) U` (unfavorable in parentheses)? The example table in the skill uses BOTH conventions inconsistently — revenue miss shows ($11,500) in parentheses, but expense overrun shows $2,400 without parentheses.

**Recommended fix:** Add an explicit sign convention rule:
```
Sign convention:
- Positive $ Var = Actual exceeded Budget (favorable for revenue, unfavorable for expenses)
- Negative $ Var = Actual was below Budget (unfavorable for revenue, favorable for expenses)
- Always show the raw (Actual - Budget) in the $ Var column
- The F/U column disambiguates direction
- Use parentheses for negative numbers only, not to indicate unfavorable
```

### Issue 3: YTD vs. Monthly Granularity Not Addressed — PARTIAL FAIL
**Severity: MEDIUM**

The skill's example is a single-month analysis. When running a multi-month YTD analysis (as I did for Jan–Feb), several questions arise that the skill doesn't address:
- Should the variance table show monthly columns, YTD only, or both?
- How do you handle a variance that is material in one month but not YTD (or vice versa)?
- The SB Paulson data showed January rent at $27K and February at $21K — the YTD average looks reasonable, but January alone is a material variance. The skill doesn't guide this.

**Recommended fix:** Add a "Multi-Period Analysis" subsection to Step 4 that specifies:
- Always show both monthly and YTD columns for periods > 1 month
- Flag at both granularities independently
- Note if a YTD variance is concentrated in one month (timing) vs. persistent (structural)

### Issue 4: The P&L Mapping Table Doesn't Fit Service Businesses — PARTIAL FAIL
**Severity: MEDIUM**

The Step 2 normalization table maps to a SaaS/tech budget structure (S&M, R&D, G&A). SB Paulson's salon P&L has completely different categories: Technical Payroll (in COGS), Non-Technical Payroll, Salon Operating, Vehicle, Occupancy. The skill provides no guidance on industry-specific mappings.

**Recommended fix:** Either:
(a) Make the mapping table generic (e.g., "Direct Labor → COGS line items linked to service delivery"), or
(b) Add 2-3 industry mapping templates (tech/SaaS, professional services, retail/hospitality), or
(c) Add a note: "If the business doesn't map to the standard template, create a custom mapping that preserves the Revenue → Gross Profit → OpEx → EBITDA waterfall structure."

### Issue 5: Reforecast Table Missing "Prior Forecast" Column — MINOR
**Severity: LOW**

The Step 7 reforecast summary template has four columns: Original Budget, Prior Forecast, Current Forecast, Change (vs Prior). But in a first-time BvA engagement (like this one), there IS no prior forecast — only the original budget. The skill doesn't address this case. I dropped the "Prior Forecast" column in my output, which is fine, but the template implies it's always needed.

**Recommended fix:** Add a note: "For first BvA of the year, the Prior Forecast equals the Original Budget. Omit the Prior Forecast column to avoid redundancy."

### Issue 6: No Guidance on Interest Expense / Below-the-Line Items — MINOR
**Severity: LOW**

The skill's P&L structure stops at EBITDA. SB Paulson has $35.6K in interest expense — by far its most important financial issue. The skill's materiality thresholds only cover Revenue, Expense, and EBITDA lines. Interest expense, depreciation, taxes, and other below-EBITDA items have no threshold guidance.

**Recommended fix:** Add a "Below EBITDA" section to the materiality thresholds:
```
Interest / D&A / Tax:   ≥ $2,500 or ≥ 10% of budgeted line → investigate
Net Income:             Same threshold as EBITDA
```

### Issue 7: Emoji Flags in Markdown — MINOR
**Severity: LOW**

The skill uses ⚠️ and 🚨 as materiality indicators. These render inconsistently across terminals, markdown renderers, and PDF exports. In some environments they appear as empty boxes or are stripped entirely.

**Recommended fix:** Offer a fallback: `[!]` for material and `[!!]` for critical, with a note that emoji versions are optional for environments that support them.

---

## Variance Formula Correctness

| Formula | As Written in SKILL.md | Correct? | Notes |
|---|---|---|---|
| Absolute Variance | Actual - Budget | YES | Standard |
| Percentage Variance | (Actual - Budget) / abs(budget) * 100 | YES | The `abs(budget)` is correct — prevents sign flip on negative budget lines (rare but possible) |
| Favorable (Revenue) | Actual > Budget | YES | |
| Favorable (Expense) | Actual < Budget | YES | |
| Flag threshold | abs(pct_var) >= threshold OR abs(absolute_var) >= threshold | YES | Dual threshold is correct |
| $0 budget edge case | Mentioned in pseudo-code comment | PARTIAL | Mentioned but not handled in the formula. Should explicitly say: `if budget == 0: pct_var = "N/A"` in the code block, not just in edge cases section. |

---

## Output Format Usability

| Format | Provided in SKILL.md | Usable? | Notes |
|---|---|---|---|
| Variance Table | Yes, with example | YES | Clean, professional. Minor sign convention issue noted above. |
| Root Cause Analysis | Yes, with 2 examples | YES | Excellent. The "decomposition then assessment" format is strong. |
| Management Commentary | Yes, WHAT/WHY/ACTION/OUTLOOK | YES | Best part of the skill. Forces accountability. |
| Reforecast Table | Yes, with example | YES | Works but needs "no prior forecast" handling. |
| Quick Flash | Yes, 3-section format | YES | Good for exec summary. |
| Structured JSON | Yes, full schema | YES | Well-structured for downstream use. |

---

## Summary of Recommended Fixes (Priority Order)

| # | Fix | Severity | Effort |
|---|---|---|---|
| 1 | Add "No Budget Available" guidance / Step 0 | HIGH | Medium — needs a new section |
| 2 | Explicitly define sign convention for $ Var column | HIGH | Low — add 5-line rule block |
| 3 | Add multi-period (YTD) analysis guidance | MEDIUM | Low — add subsection to Step 4 |
| 4 | Generalize the P&L mapping table or add industry variants | MEDIUM | Medium — rework Step 2 |
| 5 | Handle "first BvA" case in reforecast template | LOW | Trivial — add one note |
| 6 | Add below-EBITDA materiality thresholds | LOW | Trivial — add 2 lines |
| 7 | Provide non-emoji flag alternatives | LOW | Trivial — add fallback note |
| 8 | Move $0 budget handling into the main formula block | LOW | Trivial — add 1 line to pseudo-code |

---

## Final Assessment

The budget-vs-actual skill v1.0.0 is a **strong v1 that is usable in production** for practitioners with FP&A experience. The core workflow, formulas, and output templates are correct and professional. The management commentary framework (WHAT/WHY/ACTION/OUTLOOK) is genuinely excellent and should be preserved exactly as-is.

The two high-severity gaps (no budget construction guidance, ambiguous sign conventions) will cause friction for less experienced users or for engagements where a formal budget doesn't exist. These should be fixed before v1.1.

For the SB Paulson test specifically: the skill successfully guided production of a complete, actionable BvA analysis that identified the three real issues in the business (tech payroll structure, legal spend, and gross margin compression). The output would be board-presentable with minor formatting polish.
