---
name: Market Research
slug: market-research
version: 1.0.1
homepage: https://clawic.com/skills/market-research
description: "Research markets with sizing, segmentation, competitor mapping, pricing checks, and demand validation that turn fuzzy ideas into decision-ready evidence. Use when (1) you need TAM, SAM, SOM, whitespace, or category sizing; (2) you must compare competitors, pricing, positioning, or customer segments before acting; (3) the user asks whether a niche, launch, expansion, or go-to-market bet is actually worth pursuing."
changelog: "Expanded the guidance and clarified when this skill should activate."
metadata: {"clawdbot":{"emoji":"📊","requires":{"bins":[]},"os":["linux","darwin","win32"]}}
---

## When to Use

Use this skill when the user needs market evidence, not just opinions. It should activate for market sizing, opportunity validation, competitor landscape work, segment selection, pricing research, whitespace mapping, and expansion decisions.

This skill is especially useful when the user asks "is this market worth entering?", "how big is the real opportunity?", "who else is already winning here?", or "what evidence would reduce risk before we build, launch, or invest more time?"

## Quick Reference

Use the smallest relevant file for the task.

| Topic | File |
|-------|------|
| Competitor landscape and gap frameworks | `competitor-analysis.md` |
| Customer validation and pricing methods | `validation.md` |
| Evidence quality and confidence rubric | `evidence-grading.md` |

## Research Brief

Start every serious engagement with a compact brief like this:

```text
MARKET RESEARCH BRIEF
Decision:
Target customer:
Geography:
Category or substitute set:
Time horizon:
Must-answer questions:
Evidence bar:
```

If the brief is weak, the research will drift. Tight questions produce better markets, better comparisons, and better recommendations.

## Research Modes

Pick the lightest mode that still answers the decision well. Depth should follow the decision, not ego.

| Mode | Best For | Minimum Output |
|------|----------|----------------|
| **Quick scan** | Early idea filtering | Market snapshot, top competitors, 2-3 key risks |
| **Decision memo** | Founders, operators, or investors making a next-step call | Sizing view, segment map, competitor comparison, recommendation |
| **Launch validation** | New product, feature, or niche entry | Demand signals, pricing checks, interview findings, no-go risks |
| **Expansion study** | New geography, segment, or adjacent category | SAM filters, local competitors, channel constraints, rollout logic |

## Core Rules

### 1. Define the Decision Before Research Starts

Always anchor the work to one decision:
- enter or avoid a market
- prioritize one segment over another
- shape positioning and pricing
- validate whether to build, launch, or expand

Research without a decision target becomes a document full of facts and no leverage.

### 2. Size the Market in Layers, Not in Headlines

Never stop at a single big number. Separate:

| Layer | Question | Failure Mode |
|-------|----------|--------------|
| **TAM** | How large is the broad category? | Sounds exciting but too abstract |
| **SAM** | Which part is actually reachable for this product and customer? | Overstates opportunity |
| **SOM** | What can realistically be won in a specific window? | Turns fantasy into planning |

Whenever possible, show the formula, assumptions, and confidence level. A smaller defensible number is better than a huge vague one.

### 3. Triangulate Evidence and Grade Source Quality

Use at least three evidence families before making a strong claim:
- market structure data: census, filings, association reports, public benchmarks
- behavior data: search trends, reviews, job posts, product usage proxies
- direct customer evidence: interviews, surveys, waitlists, prepayments, LOIs

See `evidence-grading.md` for the confidence ladder. If all evidence comes from one source type, the conclusion is still fragile.

### 4. Segment Before You Generalize

Do not treat "the market" as one blob. Split by:
- customer type
- company size
- geography
- urgency of problem
- willingness to pay
- existing alternatives

Many bad conclusions come from averaging together segments that behave very differently.

### 5. Map Competition Around Customer Choice, Not Only Brand Names

Competitor analysis includes:
- direct competitors
- indirect substitutes
- internal workarounds such as spreadsheets, agencies, or manual processes
- future entrants with clear adjacency

Use `competitor-analysis.md` to build a positioning map, review-mining matrix, and whitespace view. The real competitor is whatever the customer would choose instead of the proposed offer.

### 6. Favor Revealed Demand Over Stated Enthusiasm

Use interviews and surveys to learn language and patterns, but trust behavior more than compliments.

Strong signals:
- repeated painful workarounds
- urgent problem frequency
- customers introducing others with the same pain
- willingness to pay, pilot, pre-order, or switch

Weak signals:
- "great idea"
- generic survey positivity
- likes, followers, or broad curiosity with no concrete action

See `validation.md` for interview, survey, and pricing research structures.

### 7. Finish with a Decision-Ready Recommendation

Every deliverable should end with:

```text
RECOMMENDATION
- What the evidence supports
- What remains uncertain
- What should happen next
- What would change the recommendation
```

Good market research reduces uncertainty. Great market research makes the next move obvious.

## Common Traps

- **Top-down theater** -> Huge category numbers create false confidence and weak planning.
- **Competitor tunnel vision** -> Looking only at visible brands misses substitutes and status-quo behavior.
- **Segment blur** -> Mixing SMB, enterprise, prosumer, and consumer demand corrupts the conclusion.
- **Source recency failure** -> Old pricing pages and stale reports make current decisions look safer than they are.
- **Opinion inflation** -> Survey excitement without action gets mistaken for demand.
- **No confidence labeling** -> Strong and weak evidence get presented with the same weight.
- **Research with no recommendation** -> User gets a report but no practical decision path.

## Security & Privacy

This skill does NOT:
- make hidden outbound requests
- fabricate customer signals or fake interviews
- access private competitor systems
- create persistent memory or maintain a local workspace by default
- store secrets unless the user explicitly asks for that workflow

Live web research is appropriate only when the task requires current market data or the user asks for external evidence.

## Related Skills
Install with `clawhub install <slug>` if user confirms:
- `pricing` - Convert validation findings into pricing strategy and willingness-to-pay decisions.
- `seo` - Translate validated demand into search-driven positioning and content opportunities.
- `business` - Connect market findings to strategic choices and operating tradeoffs.
- `compare` - Structure side-by-side option analysis when multiple markets or segments compete.
- `data-analysis` - Turn collected numbers into cleaner interpretation and supporting visuals.

## Feedback

- If useful: `clawhub star market-research`
- Stay updated: `clawhub sync`
