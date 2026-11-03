# Aggregated Portfolio (Center Book) Methodology

This document describes how the **aggregated portfolio** (combined view across user portfolios) and its **daily PnL** are implemented in RiskOfficer. The logic runs in the **RiskOfficer backend** (`portfolio_service.get_aggregated_portfolio`, pure helpers in `aggregation_math`).

## Goal

Merge positions from multiple portfolios (manual + broker) into one view in a chosen **base currency** (RUB or USD), with correct FX conversion, position netting (same ticker across portfolios), and a single **daily PnL** figure for the combined book.

## Scope

- **Included:** Manual portfolios and broker-synced portfolios (live and sandbox) that have `include_in_aggregated !== false` in their snapshot metadata.
- **Excluded:** The aggregated snapshot itself (no recursion); portfolios whose latest (or active) snapshot has `include_in_aggregated: false`.

## FX and base currency

- **Base currency:** User setting `base_currency` (RUB or USD) for the aggregated portfolio. All position values and PnL are expressed in this currency.
- **Per-position conversion:** For each position, `current_price` and `avg_price` are converted from the position’s currency to the base currency using a **resolved FX rate** (see below). PnL is then computed in base currency from these converted prices.
- **FX resolution (three-tier):**  
  1. **Live rate** from Data Service (CBR/MOEX).  
  2. If unavailable, **default static rate** (e.g. config fallback) with a warning.  
  3. If no rate is available, the position is skipped from aggregation (or error, depending on policy).  
- **Quality:** Responses can include `data_quality`: `fx_coverage`, `fx_live_count`, `fx_default_count`, `fx_unavailable_count`, `portfolios_included`, `portfolios_excluded` for observability.

## Position netting and average price

- Positions with the same **ticker** across portfolios are merged: quantities are summed (long and short net); **average price** is the **quantity-weighted average** by **absolute** quantity:  
  \(\text{avg\_price} = \bigl(\sum |q_i| \cdot \text{avg}_i\bigr) / \sum |q_i|\).  
  If a new leg has no `avg_price`, the existing aggregated `avg_price` is kept (and vice versa when the existing leg has no avg_price).

## Daily PnL

- **Per position:** After converting `current_price` and `avg_price` to base currency, PnL for that position is  
  \(\text{PnL} = (\text{current\_price} - \text{avg\_price}) \times \text{quantity}\)  
  (in base currency). Short positions (negative quantity) follow the same formula.
- **Aggregate:** Total daily PnL = sum of per-position PnLs (all already in base currency). This avoids the previous pitfall of applying a single portfolio-level FX rate to a pre-summed multi-currency PnL.
- **Implementation:** Pure functions in `aggregation_math` (`normalize_position_to_base`, `calculate_position_pnl`, `calculate_daily_pnl_base`, `aggregate_positions_netting`) are used so that aggregation and PnL logic are testable and consistent.

## Response and data quality

- **Portfolio:** Merged positions, `total_value`, `currency` (base), `sources_count`, optional `daily_pnl`.
- **data_quality:** Optional metrics: `fx_coverage`, `fx_live_count`, `fx_default_count`, `fx_unavailable_count`, `portfolios_included`, `portfolios_excluded` — so clients can see how much of the aggregation used live vs default FX and which portfolios were included or excluded.

## References

- No single academic citation; aggregation and multi-currency consolidation follow standard practice (e.g. fund administration, multi-strategy books). For VaR and risk metrics on the aggregated book, see `methodology-var.md`. For correlation across sub-portfolios, see `methodology-correlation.md`.

See `references/academic-references.md` for general risk and portfolio references.
