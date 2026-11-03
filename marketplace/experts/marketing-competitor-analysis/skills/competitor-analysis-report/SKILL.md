---
name: competitor-analysis-report
description: Generate structured competitive analysis reports with feature comparisons, pricing analysis, SWOT, and strategic recommendations. Use when analyzing competitors, creating market research reports, or delivering competitive intelligence for clients.
argument-hint: "[business-or-product] [competitor1] [competitor2] [competitor3]"
allowed-tools: Read, Write, Edit, Grep, Glob, Bash, WebFetch, WebSearch
---

# Competitor Analysis Report

Generate professional, client-ready competitive analysis reports. Researches competitors, compares features and pricing, performs SWOT analysis, and delivers actionable recommendations.

## How to Use

```
/competitor-analysis-report "Notion" "Obsidian" "Coda" "Roam Research"
/competitor-analysis-report "My SaaS product" --competitors "Competitor A, Competitor B, Competitor C"
/competitor-analysis-report brief.txt
```

- `$ARGUMENTS[0]` = The primary business/product being analyzed (client's product or a focus company)
- Remaining arguments = 2-5 competitors to analyze

## Report Generation Process

### Step 1: Research Each Competitor

For each company/product, gather:
- **Product overview**: What they do, who they serve
- **Features**: Core features and capabilities
- **Pricing**: Plans, tiers, free tier availability
- **Target audience**: Who they market to
- **Positioning**: How they describe themselves (tagline, value prop)
- **Strengths**: What they're known for
- **Weaknesses**: Common complaints, gaps, negative reviews
- **Recent changes**: New features, pricing changes, pivots

Use web search and publicly available information only.

### Step 2: Generate the Report

Structure the report as follows:

```markdown
# Competitive Analysis Report
**Prepared for**: [Client/Product Name]
**Date**: [Today's date]
**Competitors Analyzed**: [List]

---

## Executive Summary
[3-5 sentence overview of the competitive landscape.
Key finding. Biggest opportunity. Primary threat.]

---

## Competitor Profiles

### [Competitor 1]
- **Founded**: [Year]
- **Headquarters**: [Location]
- **Positioning**: "[Their tagline or value prop]"
- **Target Market**: [Who they serve]
- **Key Differentiator**: [What makes them unique]

[Repeat for each competitor]

---

## Feature Comparison Matrix

| Feature | [Your Product] | [Comp 1] | [Comp 2] | [Comp 3] |
|---------|---------------|----------|----------|----------|
| [Feature 1] | ✅ | ✅ | ❌ | ✅ |
| [Feature 2] | ✅ | ✅ | ✅ | ❌ |
| [Feature 3] | ❌ | ✅ | ✅ | ✅ |
| ... | | | | |

**Key Takeaway**: [1-2 sentences on where you lead and lag]

---

## Pricing Analysis

| Plan | [Your Product] | [Comp 1] | [Comp 2] | [Comp 3] |
|------|---------------|----------|----------|----------|
| Free Tier | [Details] | [Details] | [Details] | [Details] |
| Basic/Starter | $X/mo | $X/mo | $X/mo | $X/mo |
| Professional | $X/mo | $X/mo | $X/mo | $X/mo |
| Enterprise | Custom | Custom | $X/mo | Custom |

**Price Positioning**: [Where client sits relative to market — premium, mid-market, value]
**Key Takeaway**: [Pricing opportunity or risk]

---

## SWOT Analysis

For each competitor:

### [Competitor 1] SWOT

| Strengths | Weaknesses |
|-----------|------------|
| • [Point] | • [Point] |
| • [Point] | • [Point] |

| Opportunities | Threats |
|--------------|---------|
| • [Point] | • [Point] |
| • [Point] | • [Point] |

---

## Market Positioning Map

```
                    HIGH PRICE
                        │
          Enterprise    │    Premium
          [Comp 3]      │    [Comp 1]
                        │
   LOW ─────────────────┼───────────────── HIGH
   FEATURES             │              FEATURES
                        │
          Budget        │    Best Value
          [Comp 2]      │    [You]
                        │
                    LOW PRICE
```

---

## Opportunities & Threats

### Opportunities (Where You Can Win)
1. **[Gap in competitor offerings]**: [How to exploit it]
2. **[Underserved segment]**: [How to capture it]
3. **[Competitor weakness]**: [How to position against it]

### Threats (What to Watch)
1. **[Competitor advantage]**: [How to defend against it]
2. **[Market trend]**: [How it could impact you]
3. **[New entrant risk]**: [Who might enter the space]

---

## Strategic Recommendations

### Immediate Actions (Next 30 Days)
1. [Specific, actionable recommendation]
2. [Specific, actionable recommendation]

### Medium-Term (Next Quarter)
1. [Strategic initiative]
2. [Feature/positioning change]

### Long-Term (Next 6-12 Months)
1. [Market positioning play]
2. [Competitive moat building]

---

## Appendix
- Data sources and methodology
- Detailed feature descriptions
- Competitor screenshots/examples (described, not included)
```

### Step 3: Output

Save to `output/competitor-analysis/`:

```
output/competitor-analysis/
  report.md                    # Full report in Markdown
  report.html                  # Professional HTML version
  executive-summary.md         # Standalone exec summary (1 page)
  feature-matrix.csv           # Spreadsheet-ready comparison
```

The HTML version should have:
- Professional styling (clean typography, tables with borders)
- Print-friendly layout
- Table of contents with anchor links
- Page breaks between major sections

## Quality Standards

- [ ] All data points are from publicly available sources
- [ ] Feature comparison covers at least 10 features
- [ ] Pricing is current and accurate
- [ ] SWOT analysis has at least 3 points per quadrant
- [ ] Recommendations are specific and actionable (not generic advice)
- [ ] Executive summary can stand alone (client can forward to their boss)
- [ ] No speculation presented as fact — clearly label assumptions
- [ ] Report is professional enough to present to stakeholders
