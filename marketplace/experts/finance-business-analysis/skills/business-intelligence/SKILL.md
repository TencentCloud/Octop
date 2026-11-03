---
name: Business Intelligence
slug: business-intelligence
version: 1.0.0
homepage: https://clawic.com/skills/business-intelligence
description: Model business performance, define KPIs, and turn data into decision-ready dashboards, briefings, and operating cadences for teams and executives.
changelog: Initial release with metric tree modeling, KPI contracts, dashboard specifications, and decision briefing workflows.
metadata: {"clawdbot":{"emoji":"B","requires":{"bins":[]},"os":["linux","darwin","win32"]}}
---

## Setup

On first use, read `setup.md` for integration behavior and memory initialization.

## When to Use

Use this skill when the user needs to build or improve business intelligence systems: KPI definitions, metric architecture, dashboard planning, executive reporting, and decision review loops.

This skill is optimized for operators, founders, product leaders, finance leaders, and analysts who need clear answers to "what changed, why it changed, and what to do next".

## Architecture

Working memory lives in `~/business-intelligence/`. See `memory-template.md` for base structure and status behavior.

```
~/business-intelligence/
├── memory.md                # HOT: goals, KPI ownership, active decisions
├── metric-tree/             # WARM: objective -> driver -> metric maps
├── kpi-contracts/           # WARM: metric definitions and formula versions
├── dashboard-specs/         # WARM: visualization and drill-down specifications
├── insight-briefs/          # WARM: weekly and monthly decision briefs
├── operating-cadence/       # WARM: review rituals and escalation rules
└── archive/                 # COLD: retired KPIs and past planning cycles
```

## Quick Reference

Load only the file needed for the current task to keep context focused.

| Topic | File |
|-------|------|
| Setup and integration | `setup.md` |
| Memory schema | `memory-template.md` |
| Objective and metric tree design | `metric-tree.md` |
| KPI definition contracts | `kpi-dictionary.md` |
| Dashboard and drill-down design | `dashboard-specs.md` |
| Decision brief templates | `insight-briefs.md` |
| Review rituals and escalation rules | `decision-cadence.md` |
| Source quality and data contracts | `data-contracts.md` |

## Core Rules

### 1. Start from Decision Questions, Not Charts
Every BI request must begin with one decision question and one owner.

If there is no decision owner, the output is reporting noise and should be reframed before building metrics.

### 2. Build a Metric Tree Before Dashboard Design
Map each business objective to drivers, then drivers to measurable KPIs.

Do not build dashboards first. Dashboards without a metric tree create disconnected charts and contradictory narratives.

### 3. Enforce KPI Contracts
Each KPI needs a written contract: definition, formula, grain, source, refresh cadence, owner, and valid interpretation window.

Never compare KPI values across periods if formula version or source logic changed without annotation.

### 4. Separate Leading and Lagging Indicators
For every lagging KPI, define at least one leading indicator that signals future movement.

If the system only tracks lagging outcomes, intervention happens too late.

### 5. Brief Insights in Decision Format
Every insight output must include:
- What changed
- Why it changed
- Confidence level
- Recommended action
- Action owner and due date

A BI summary without an action owner is incomplete.

### 6. Standardize Dashboard Specs Across Teams
Use consistent metric naming, time windows, segment logic, color semantics, and drill-down paths.

Inconsistent dashboard specs make cross-team comparisons invalid.

### 7. Run a Fixed Operating Cadence
Define daily, weekly, monthly, and quarterly BI rituals with clear participants and escalation triggers.

Without a fixed cadence, KPI review becomes reactive and decision quality degrades.

## Business Intelligence Traps

- Starting with visualization tooling before KPI contracts -> expensive dashboards with weak decisions.
- Tracking too many KPIs per objective -> teams lose focus on actual drivers.
- Blending forecast assumptions with actuals in one number -> executives make false confidence calls.
- Changing formulas without version notes -> historical trend comparisons become invalid.
- Reporting movement without attribution depth -> teams cannot identify correct interventions.
- Sending BI updates without action owners -> insights do not convert into execution.

## External Endpoints

This skill makes NO external network requests.

| Endpoint | Data Sent | Purpose |
|----------|-----------|---------|
| None | None | N/A |

No data is sent externally.

## Security & Privacy

**Data that leaves your machine:**
- Nothing by default.

**Data that stays local:**
- BI context, KPI contracts, and reporting notes under `~/business-intelligence/`.
- Decision cadence and retrospective notes stored locally when memory is enabled.

**This skill does NOT:**
- Access files outside `~/business-intelligence/` for memory storage.
- Transmit metrics or business data to third-party APIs by default.
- Create background automations without explicit user confirmation.
- Modify its own skill definition files.

## Related Skills
Install with `clawhub install <slug>` if user confirms:
- `analytics` - analysis workflows for interpreting performance patterns.
- `data-analysis` - analysis workflows for modeling trends, segments, and causal signals.
- `dashboard` - dashboard implementation for KPI visualization layers.
- `strategy` - strategic planning frameworks tied to business outcomes.
- `report` - structured report generation for stakeholder communication.

## Feedback

- If useful: `clawhub star business-intelligence`
- Stay updated: `clawhub sync`
