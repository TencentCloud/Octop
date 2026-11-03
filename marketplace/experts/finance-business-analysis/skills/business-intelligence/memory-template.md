# Memory Template - Business Intelligence

Create `~/business-intelligence/memory.md` with this structure:

```markdown
# Business Intelligence Memory

## Status
status: ongoing
version: 1.0.0
last: YYYY-MM-DD
integration: pending | done | declined

## Operating Context
- Business model:
- Time horizon:
- Primary objective:
- Key stakeholders:
- Decision bottleneck:

## Metric Tree
| Objective | Driver | KPI | Owner | Review Cadence |
|-----------|--------|-----|-------|----------------|
| Example: Improve gross margin | Reduce discount leakage | Net realized price | RevOps lead | Weekly |

## KPI Contracts
| KPI | Formula Version | Source | Refresh | Caveat |
|-----|-----------------|--------|---------|--------|
| Example: Net Revenue Retention | v2.1 | warehouse.finance_mrr | daily | Excludes non-recurring credits |

## Decision Brief Backlog
- Topic:
  Owner:
  Due date:
  Current confidence:

## Notes
- Stable context and constraints worth retaining.
```

## Status Values

| Value | Meaning | Behavior |
|-------|---------|----------|
| `ongoing` | Context still evolving | Keep collecting context while delivering output |
| `complete` | Core BI system is stable | Focus on optimization and exception handling |
| `paused` | User postponed setup depth | Continue work without setup prompts |
| `never_ask` | User opted out permanently | Never ask setup questions again |

## Memory Hygiene

- Store decisions and metric contracts, not raw transcripts.
- Keep entries brief, evidence oriented, and owner oriented.
- Archive retired KPIs instead of deleting context history.
