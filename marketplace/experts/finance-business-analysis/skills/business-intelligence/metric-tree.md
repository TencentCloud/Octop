# Objective to Metric Tree

## Purpose

Use this file to convert vague goals into measurable driver maps before building dashboards.

## Build Sequence

1. Define one objective in business terms.
2. List 2-4 controllable drivers that move the objective.
3. Assign one KPI per driver.
4. Add owner and review cadence for each KPI.
5. Add one leading indicator per lagging KPI.

## Template

```markdown
Objective:

| Driver | KPI | Type (Leading/Lagging) | Owner | Review Cadence |
|--------|-----|------------------------|-------|----------------|
|        |     |                        |       |                |
```

## Quality Checks

- Each KPI can be influenced by a named owner.
- KPI formulas can be computed from available sources.
- KPI time grain matches the review cadence.
- Every lagging KPI has at least one leading signal.
- No KPI appears under multiple objectives without explanation.

## Escalation Rule

If a driver has no reliable KPI yet, mark it as a data contract gap and route to `data-contracts.md`.
