# Setup - Business Intelligence

Read this when `~/business-intelligence/memory.md` does not exist or is empty.

Answer the user's immediate question first, then gather setup context naturally in the same conversation.

## Integration First

Within the first natural exchanges, confirm how this support should activate:

- Should this activate whenever the user asks about KPIs, business metrics, dashboards, revenue analysis, or executive reporting?
- Should it proactively highlight metric anomalies, or only respond when asked?
- Should BI context and decision history be remembered for future sessions?

If the user declines deeper setup, continue immediately and set integration to `declined`.

## Capture the Minimum Useful Baseline

Collect only high-impact context required for useful BI output:

- Business model and primary revenue motion.
- Current business objectives for this quarter.
- Existing KPI stack and known reliability issues.
- Stakeholder roles and reporting cadence.
- Current decision bottleneck: speed, clarity, alignment, or follow-through.

Ask one focused question at a time and move quickly toward a useful artifact.

## First-Session Output

Before ending setup, produce one concrete output:

- A metric tree linking one objective to drivers and KPIs.
- A KPI contract draft for one critical metric.
- A dashboard specification for one leadership review.
- A weekly decision brief template with owners and due dates.

## Persistence Rules

When memory is enabled:

- Create `~/business-intelligence/memory.md` from `memory-template.md`.
- Update `last` when KPI contracts or decision cadence change.
- Store concise operational context only.
- Never store credentials, secrets, or unrelated personal details.
