---
name: ad-budget-rebalancer
description: Analyze ecommerce ad spend notes across Meta Ads, Google Ads, TikTok Ads, Amazon Sponsored, and Xiaohongshu promotional feeds, then recommend budget reallocation across channels, campaign types, and audience segments. Use when operators need a budget review, underperforming-channel diagnosis, or channel-mix rebalancing brief without live ad platform API access.
---

# Ad Budget Rebalancer

## Overview

Use this skill to diagnose ad spend patterns and generate a budget-rebalancing brief that prioritizes channels, campaign types, and audience segments based on efficiency signals. It applies a built-in efficiency framework and channel-mix matrix to surface reallocation recommendations.

This MVP is heuristic. It does **not** connect to live ad platforms, campaign managers, or analytics dashboards. It relies on the user's provided spend notes, performance context, and channel mix.

## Trigger

Use this skill when the user wants to:
- review ad spend efficiency across multiple channels (Meta, Google, Amazon, TikTok, Xiaohongshu)
- diagnose why a channel or campaign is underperforming relative to spend
- rebalance budget across awareness, consideration, and conversion campaign types
- prepare a monthly or quarterly media budget review brief
- identify where to cut spend or where to scale based on ROAS or MER signals

### Example prompts

- "Our Meta Ads ROAS dropped this month — should we reallocate budget?"
- "Help me review and rebalance our Q1 ad spend across Amazon, Google, and TikTok"
- "Diagnose why our TikTok campaign is burning budget without conversions"
- "Create a budget rebalancing brief for a $50k monthly ad spend"

## Workflow

1. Capture the total budget, channel mix, campaign types, and performance signals.
2. Apply the efficiency framework to score each channel and campaign type.
3. Identify underperforming channels, audience segments, and campaign types.
4. Generate rebalancing recommendations with expected impact.
5. Return a markdown rebalancing brief.

## Inputs

The user can provide any mix of:
- total ad budget and channel breakdown: e.g., Meta 40%, Google 30%, Amazon 20%, TikTok 10%
- campaign type mix: awareness, consideration, conversion, retargeting
- performance signals: ROAS, MER, CPM, CPC, CPA, CTR, conversion rate by channel
- audience segment notes: demographic, interest, lookalike, retarget
- business context: seasonal window, product launch, clearance, brand campaign
- constraints: minimum spend requirements, creative constraints, platform policies

## Outputs

Return a markdown brief with:
- budget health summary (total spend, channel mix, overall efficiency)
- channel efficiency scorecard (ROAS/MER, CPM, CPC, CPA per channel)
- campaign type efficiency breakdown (awareness vs. conversion)
- audience segment performance notes
- rebalancing recommendations with specific reallocation percentages
- expected impact estimates and risk notes
- creative or landing-page considerations that may affect efficiency

## Safety

- No live ad platform, campaign manager, or analytics API access.
- Efficiency scores are directional unless complete spend and revenue data is provided.
- Do not claim guaranteed ROAS improvements or budget savings.
- Budget decisions remain human-approved; automated bid or budget changes are out of scope.

## Best-fit Scenarios

- SMB and mid-market teams managing $10k-$500k monthly ad budgets
- operators running multi-channel campaigns without a dedicated media buyer
- teams needing a regular budget review cadence without heavy BI tooling

## Not Ideal For

- real-time bid management, automated campaign optimization, or live spend control
- businesses with incomplete or inconsistent spend reporting
- highly complex attribution scenarios requiring multi-touch modeling

## Acceptance Criteria

- Return markdown text.
- Include channel efficiency scorecard and rebalancing recommendations.
- Make efficiency assumptions explicit when data is partial.
- Keep the brief practical for ecommerce operators and media buyers.
