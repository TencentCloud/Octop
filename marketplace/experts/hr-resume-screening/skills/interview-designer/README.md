# Interview Designer

**Evidence-Based Interview Planning**

Design interview questions using Scorecard → Forensic Scan → Future Simulation. Avoid confirmation bias and produce structured interview guides (Scorecard + Red Flags/Green Signals + Pressure Tests + Future Scenarios) with Geoff Smart, Lou Adler, and Daniel Kahneman as the default expert panel.

---

## When to Use This Skill

Use this skill when:

- You need to design interview questions for a specific role
- You want to avoid confirmation bias in interview planning
- You're creating a structured interview guide (Scorecard + Questions + Pressure Tests)
- You need to balance past validation with future simulation

---

## Methodology: Scorecard → Forensic → Future

| Phase           | Expert        | What You Define                                                                 |
|-----------------|---------------|-----------------------------------------------------------------------------------|
| **1. Scorecard**| Geoff Smart   | Mission, Outcomes, Competencies — *before* looking at any resume                 |
| **2. Forensic Scan** | Smart + Domain | Resume gaps vs. highlights; "Too Good To Be True" / "Driver vs Passenger" heuristics |
| **3. Future Simulation** | Lou Adler  | Performance problems the candidate would face in your context; week-one scenarios |

---

## What You Get

| Output            | Template                           | Purpose                                              |
|-------------------|------------------------------------|------------------------------------------------------|
| **Interview Guide** | `templates/interview_guide_template.md` | Scorecard + Red Flags/Green Signals + Pressure Tests + Future Scenarios |

The guide includes both concerns (**Red Flags**) and highlight verification (**Green Signals**) for objective assessment.

---

## Design Principles

1. **Cannot Be Memorized** — Questions force real-time thinking (simulation) or concrete recall (pressure test).
2. **Forced Trade-offs** — Choose between two "correct" options to surface values, not just knowledge.
3. **Detail Granularity** — Probe to "what exact words did you say" or "what diagram did you draw."

---

## Quick Reference

| Interview Goal      | Question Type       | Example                                                                 |
|---------------------|---------------------|-------------------------------------------------------------------------|
| Validate past claims| Pressure Test (STAR) | "Walk me through the specific metrics you tracked and how you used them." |
| Predict future fit  | Future Simulation   | "Here's our Q1 challenge. How would you approach it in your first week?" |
| Detect blind spots  | Trade-off Question  | "Speed vs. quality — which would you sacrifice here, and why?"         |

---

## Install

**ClawHub (OpenClaw)**:
```bash
npx clawhub@latest install interview-designer
```

**Other (e.g. skills.sh)**:
```bash
npx skills add mikonos/interview-designer
```

Compatible with Cursor, Claude Code, OpenClaw, and other agents that support the skills protocol.
