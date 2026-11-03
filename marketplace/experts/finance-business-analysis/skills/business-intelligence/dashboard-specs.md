# Dashboard Specifications

## Design Standard

Each dashboard must answer one core decision question and support a deterministic drill-down path.

## Required Blocks

- Decision Question
- KPI Summary Strip (3-7 KPIs)
- Driver Decomposition Panel
- Segment Breakdown Panel
- Diagnostic Notes and Caveats
- Action Queue with owner and due date

## Dashboard Contract

```markdown
Dashboard Name:
Decision owner:
Primary decision question:
Audience:
Refresh cadence:
Core KPIs:
Drill-down path:
Alert thresholds:
Escalation route:
```

## Visual Consistency Rules

- Use identical KPI names across all dashboards.
- Keep time filters visible at top level.
- Reserve red for threshold breach only.
- Do not mix absolute values and rates in one axis without labels.
- Display last refresh timestamp in the header.

## Drill-Down Requirements

Every anomaly tile must support:

1. Period comparison
2. Segment decomposition
3. Source-level traceability

If any step is missing, the dashboard is not decision ready.
