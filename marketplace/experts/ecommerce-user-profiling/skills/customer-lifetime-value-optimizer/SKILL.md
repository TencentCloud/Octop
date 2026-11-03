---
name: customer-lifetime-value-optimizer
description: Segment ecommerce customers by repeat behavior, margin quality, membership depth, and churn or return risk, then turn rough order-history notes into a prioritized LTV growth plan. Use when CRM, membership, lifecycle, or retention teams need segment-specific growth actions without live CDP, ESP, or data-warehouse integrations.
---

# Customer Lifetime Value Optimizer

## Overview

Use this skill to convert customer-segment notes, order-history summaries, gross-margin signals, and retention context into a practical LTV action plan. It is built for operators who need fast prioritization across new-customer nurture, repeat purchase growth, margin protection, and winback strategy.

This MVP is heuristic. It does **not** connect to live CRM, CDP, ESP, loyalty, or analytics systems. It relies on the user's segment notes, exported summaries, and lifecycle context.

## Trigger

Use this skill when the user wants to:
- identify which customer segments deserve the most retention investment
- design different lifecycle moves for high-value, price-sensitive, dormant, or return-risk customers
- rank LTV levers such as repeat rate, AOV, margin mix, or churn reduction
- turn rough order-history notes into a CRM or membership action brief
- separate revenue growth ideas from margin-quality and retention-quality risks

### Example prompts
- "Which segments should we prioritize to improve LTV this quarter?"
- "Create a retention plan for VIP, new, and dormant customers"
- "How can we grow LTV without overusing discounts?"
- "Turn these order and membership notes into an LTV roadmap"

## Workflow
1. Capture the customer segments, order behavior, and whether the main tension is repeat rate, AOV, churn, or margin quality.
2. Normalize the likely LTV signals: order history, repurchase cycle, segment mix, return behavior, and offer sensitivity.
3. Separate customer groups into different action lanes instead of giving one generic lifecycle answer.
4. Rank the highest-value LTV levers and attach practical plays, owners, and success metrics.
5. Return a markdown plan with segment diagnosis, lever ranking, and action packages.

## Inputs
The user can provide any mix of:
- customer segments or membership tiers
- order history and repeat-cycle notes
- AOV, gross margin, bundle rate, or attach-rate context
- churn, dormancy, or lapsed-customer notes
- refund or return-risk observations
- lifecycle messaging constraints and incentive constraints

## Outputs
Return a markdown plan with:
- a segment diagnosis table
- ranked LTV levers
- action packages by segment
- short, medium, and longer-horizon priorities
- measurement notes, assumptions, and limits

## Safety
- Do not claim access to live CRM, ESP, loyalty, or analytics systems.
- Do not auto-send discounts, coupons, or lifecycle messages.
- Keep revenue lift and margin impact separate in the recommendations.
- Downgrade certainty when user-level order history is incomplete.
- Treat financial LTV models and operator-facing lifecycle plans as related but not identical.

## Best-fit Scenarios
- CRM and membership planning for ecommerce teams
- repeat-purchase and lifecycle improvement reviews
- retention strategy design when data is partial but usable
- operator-led businesses that need an action plan before building a deeper model

## Not Ideal For
- formal finance-grade LTV forecasting
- automatic customer scoring or trigger orchestration
- businesses with no segment or order-history visibility at all
- scenarios that require privacy-reviewed activation logic

## Acceptance Criteria
- Return markdown text.
- Include segment diagnosis, lever ranking, action packages, and limits.
- Show at least one short-term, one medium-term, and one longer-term move.
- Keep the plan practical for CRM, lifecycle, and retention operators.
