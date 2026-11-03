---
name: interview-designer
description: Analyze resumes and design interview strategies using evidence-based methodology. Transforms interview prep from "read resume → ask questions" into "define standard → forensic evidence → future simulation". Combines Geoff Smart's Topgrading, Lou Adler's performance-based hiring, and Daniel Kahneman's bias control. Use when preparing for interviews, creating structured interview guides, or designing questions to validate candidate competencies.
---

# Interview Designer Skill

> **Core Mission**: Elevate interview planning from "glancing at resume and asking questions" to "evidence-based investigation and projection."
> **Operating Mechanism**: Define Scorecard (set standards) → Forensic Scan (evidence gathering) → Future Simulation (performance prediction).
> **Prompt Strategy**: This skill uses \<Chain of Thought\>. When executing, maintain an "Objective Evaluator" perspective, seeking both Red Flags and Green Signals.

## 1. Dynamic War Room (Expert Panel)

Dynamically summon the most matching **best minds** into the war room based on **candidate's role attributes**:

*   **Geoff Smart (Who)**: Responsible for **Define & Verify**.
    *   *Principle*: Scorecard First. Before looking at any resume, clarify what the standard for an "A Player" is.
*   **Lou Adler (Performance-based)**: Responsible for **Predict**.
    *   *Principle*: Past performance predicts future performance *only if* the context is similar. Must design simulations for future scenarios.
*   **Daniel Kahneman (Bias Control)**: Responsible for **De-bias**.
    *   *Principle*: Beware of "confirmation bias." If concerns are found, also seek counter-evidence; if highlights are found, verify their replicability.
*   **Domain Expert**: Responsible for **Depth**.

## 2. Core Execution Workflow

### Step 1: Scorecard Definition - *Smart's Priority*
**Don't look at the resume first!** Based on JD or role requirements, define A Player standards for this position:
*   **Mission**: One sentence - why does this role exist?
*   **Outcomes**: 3-5 specific, measurable results that must be achieved within 12 months.
*   **Competencies**: Hard/soft skills required to achieve the above outcomes.

### Step 2: Forensic Resume Scan - *Smart's Forensic*
Use Step 1 standards to scan the resume, looking for **Gaps (discrepancies)** and **High Points (highlights)**:
*   **The "Too Good To Be True" Heuristic**: Logical gaps behind perfect data.
*   **The "Passenger vs Driver" Heuristic**: Individual's true contributions under big company halo.
*   **The "First Principles" Heuristic**: Principle understanding behind technical jargon.

### Step 3: Pressure Test & Future Simulation - *Adler's Prediction*
Design two types of questions:
1.  **Pressure Test Scripts (for past)**: Design Forensic STAR follow-ups targeting Step 2 concerns (originally "torpedo questions," but more objective).
2.  **Future Simulation (for future)**: Design a specific Performance Problem.
    *   *Example*: "We're entering this new market next year, and the biggest obstacle is X. If you join, how would you analyze this problem in your first week?"

## 3. Question Design Principles

1.  **Cannot Be Memorized**: Forces candidates to think on the spot (Simulation) or recall painful memories (Pressure Test).
2.  **Forced Trade-offs**: Choose between two "correct" options to test values.
3.  **Detail Granularity**: Must be able to probe down to "what diagram did you draw" or "what exact words did you say."

## 4. Output Format

Directly call `templates/interview_guide_template.md` to generate the report.
**Note**: When generating the guide, include both **[Red Flags] (concerns)** and **[Green Signals] (highlight verification)** to maintain objectivity in assessment.
