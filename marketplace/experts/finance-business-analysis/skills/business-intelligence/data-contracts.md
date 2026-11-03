# Data Contracts and Reliability

## Purpose

Keep BI outputs trustworthy by making source assumptions explicit.

## Source Contract Template

```markdown
Source Name:
Owner:
Update schedule:
Latency expectation:
Schema dependencies:
Quality checks:
Failure alert channel:
```

## Minimum Quality Gates

- Freshness: source updated within expected SLA.
- Completeness: row counts within expected range.
- Uniqueness: primary keys have no duplicates.
- Validity: critical dimensions use approved values only.
- Reconciliation: totals align with financial or operational ground truth.

## Incident Policy

When quality gate fails:

1. Mark impacted KPIs as degraded.
2. Block high-confidence claims in briefs.
3. Notify owner with expected recovery time.
4. Publish post-incident note in weekly brief.

## Reliability Score

Use a simple reliability score per source:

- Green: all gates pass.
- Yellow: minor breach with known impact bounds.
- Red: severe breach, decision use restricted.
