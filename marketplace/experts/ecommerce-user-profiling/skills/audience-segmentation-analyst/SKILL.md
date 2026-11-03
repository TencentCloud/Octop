---
name: audience-segmentation-analyst
description: Build audience segmentation and targeting plans for Meta (Facebook/Instagram), Google Ads, TikTok Ads, YouTube Ads, and DSP/programmatic campaigns.
---

# Ads Audience Targeting

## Purpose
Define ICP segments, audience labels, exclusions, and targeting hypotheses that are ready for ad setup.

## When To Trigger
Use this skill when the user asks to:
- run ads or execute advertising campaigns with clear operational next steps
- grow revenue or profit, improve roas, reduce cpa, or optimize budget and bidding
- analyze market, traffic, conversion funnel, and campaign performance signals
- apply this specific capability: icp segmentation, audience labels, exclusion strategy

Typical trigger keywords:
- ads, advertising, campaign, growth, strategy
- revenue, profit, roi, roas, cpa
- budget, bidding, traffic, conversion, funnel
- meta, googleads, tiktokads, youtubeads, amazonads, shopifyads, dsp

## Input Contract
Required:
- business_goal: primary objective (sales, leads, traffic, awareness, retention)
- scope: campaign range, market, timeline, and platform scope
- context: URL, account context, historical performance, or request text

Optional:
- kpi_targets: target cpa, roas, revenue, roi, ltv, cvr
- constraints: budget, policy, brand rules, timeline, resource limits
- platform_preference: preferred channels and priority
- baseline_metrics: existing benchmark metrics

## Output Contract
Return an execution-ready result with:
1. Intent Summary (goal, KPI, scope)
2. Findings (key observations and assumptions)
3. Action Plan (prioritized next steps)
4. Risks and Guardrails (what can break and what to monitor)
5. Handoff Payload (structured fields for downstream skills)

## Workflow
1. Normalize request and confirm objective.
2. Validate available inputs and list missing critical data.
3. Analyze according to this skill focus: icp segmentation, audience labels, exclusion strategy.
4. Generate prioritized actions tied to KPI impact.
5. Add platform-specific notes and constraints.
6. Emit a compact handoff payload for execution.

## Decision Rules
- If KPI is missing, infer likely primary KPI from goal and mark assumption explicitly.
- If data quality is low, return conservative recommendations and required follow-up checks.
- If platform context is unclear, provide platform-agnostic baseline plus channel variants.
- If policy or account risk appears high, require compliance or account checks before scale.
- If urgency is high and uncertainty is high, prioritize reversible low-risk actions first.

## Platform Notes
Primary platform scope:
- Meta (Facebook/Instagram), Google Ads, TikTok Ads, YouTube Ads, DSP/programmatic

Guidance:
- Use platform-specific recommendations only when evidence supports them.
- Keep naming explicit: Meta, Google Ads, TikTok Ads, YouTube Ads, Amazon Ads, Shopify Ads, DSP.
- If request is cross-channel, provide channel order and budget split rationale.

## Constraints And Guardrails
- Do not fabricate data, performance outcomes, or policy approvals.
- Separate facts from assumptions in every recommendation.
- Keep recommendations measurable and tied to explicit KPIs.
- Avoid irreversible changes without validation checkpoints.

## Failure Handling And Escalation
- If required inputs are missing, request concise follow-up fields before final recommendation.
- If data sources conflict, report conflict and provide a safe default path.
- If request implies unsupported account actions, escalate with an exact handoff checklist.
- If compliance risk is detected, route to Ads Compliance Review before launch.

## Examples
### Example 1: Meta ecommerce optimization
Input:
- Goal: sales growth with lower cpa
- Platform: Meta (Facebook/Instagram)

Output focus:
- top blockers
- prioritized fixes
- week-1 actions and expected KPI movement

### Example 2: Google Ads lead generation
Input:
- Goal: improve lead quality and stabilize cpl
- Platform: Google Ads

Output focus:
- search intent structure
- budget and bidding adjustments
- lead-routing handoff fields

### Example 3: TikTok plus YouTube scale test
Input:
- Goal: scale traffic while protecting roas
- Platforms: TikTok Ads and YouTube Ads

Output focus:
- test matrix
- risk guardrails
- monitoring and rollback triggers

## Quality Checklist
- [ ] All required sections are present
- [ ] At least 3 registry keywords appear in When To Trigger
- [ ] Input and output contracts are explicit and actionable
- [ ] Workflow is step-based and execution ready
- [ ] Platform references are concrete when applicable
- [ ] At least 3 examples are included
