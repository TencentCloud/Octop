# KPI Dictionary and Contracts

## KPI Contract Template

Use this contract for every KPI before reporting it:

```markdown
KPI Name:
Business definition:
Formula:
Numerator:
Denominator:
Time grain:
Segment dimensions:
Source tables:
Refresh cadence:
Owner:
Known caveats:
Version:
```

## Versioning Rules

- Increment patch when fixing logic bugs with same interpretation.
- Increment minor when changing interpretation scope or segmentation.
- Keep a short migration note for each version change.

## Contract Validation Checklist

- Formula can be reproduced by another analyst.
- Inputs are available without manual spreadsheet work.
- Time window boundaries are explicit.
- Exclusions are documented.
- Owner agrees with business definition.

## Common Contract Failures

- Two teams use the same KPI name with different formulas.
- Source freshness is lower than review cadence.
- Denominator changes by segment but documentation does not mention it.
- Formula includes forecast fields while KPI is labeled as actual.
