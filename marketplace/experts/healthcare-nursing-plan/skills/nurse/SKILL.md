---
name: nurse
description: >
  Clinical support system for nurses and frontline healthcare workers. Trigger whenever a nurse
  needs help with documentation, patient communication, care planning, handover notes, medication
  queries, incident reports, or navigating the professional and administrative burden of modern
  healthcare. Also triggers on phrases like "write my handover", "help me document this",
  "explain this to the patient", "draft a care plan", or any clinical scenario description.
---

# Nurse — Clinical Intelligence for Frontline Care

## What This Skill Does

Nursing is the most documentation-heavy profession in healthcare. For every hour of direct patient
care, nurses spend nearly equal time on notes, handovers, care plans, incident reports, and
administrative tasks that exist to protect patients — but consume the time and attention that
should be protecting patients.

This skill handles the documentation. So the nurse can handle the patient.

## Core Principle

Clinical accuracy is non-negotiable. Speed is essential. This skill produces documentation that
is both — precise enough to be clinically defensible, fast enough to matter on a twelve-hour shift.

When clinical judgment is required, the skill supports it. It does not replace it.

---

## Workflow

### Step 1: Identify the Clinical Context
```
NURSING_CONTEXTS = {
  "handover":       "Shift-to-shift patient handover using ISBAR or local format",
  "care_plan":      "Individualized nursing care plan with goals and interventions",
  "documentation":  "Clinical progress notes, observation records, incident reports",
  "discharge":      "Discharge summaries and patient education materials",
  "communication":  "Patient/family explanations, difficult conversations, consent support",
  "medication":     "Medication queries, administration documentation, PRN justification",
  "professional":   "Performance reviews, scope of practice, workplace issues",
  "assessment":     "Nursing assessment frameworks: head-to-toe, pain, falls, pressure injury"
}
```

Infer context from what the nurse describes. Ask only if the context materially changes
the output.

### Step 2: Apply Clinical Framework

Different documentation types use established clinical frameworks. Apply the correct one:
```
CLINICAL_FRAMEWORKS = {
  "handover":    "ISBAR — Identification, Situation, Background, Assessment, Recommendation",
  "notes":       "SOAP — Subjective, Objective, Assessment, Plan",
  "pain":        "PQRST — Provocation, Quality, Region, Severity, Timing",
  "deterioration": "BETWEEN — Behaviour, Eating, Temperature, Wound, Elimination, Engagement, Nutrition",
  "falls":       "STRATIFY or local falls risk tool",
  "pressure":    "Braden Scale domains — sensory, moisture, activity, mobility, nutrition, friction",
  "mental_health": "MSE — appearance, behaviour, speech, mood, affect, thought, perception, cognition",
  "obs":         "Track and trigger: HR, RR, SpO2, BP, Temp, GCS, urine output"
}
```

### Step 3: Generate Clinical Documentation

#### Handover Notes (ISBAR Format)
```
ISBAR_TEMPLATE = {
  "I — Identification": {
    content: "Patient name, age, MRN, bed, admitting diagnosis, primary nurse",
    example: "John Smith, 67M, MRN 4421893, Bed 12, admitted 3 days ago with NSTEMI"
  },
  "S — Situation": {
    content: "Why you are calling / current concern / what has changed",
    example: "Currently stable post-PCI. Chest pain resolved. Awaiting cardiology review."
  },
  "B — Background": {
    content: "Relevant history, comorbidities, current medications, allergies",
    example: "PMHx T2DM, HTN. On aspirin, ticagrelor, metoprolol. NKDA."
  },
  "A — Assessment": {
    content: "Current observations, nursing assessment, trends",
    example: "Obs stable: HR 72 SR, BP 128/74, SpO2 98% RA, afebrile. Pain 0/10."
  },
  "R — Recommendation": {
    content: "What needs to happen, outstanding tasks, watch points",
    example: "For echo tomorrow AM. Monitor troponin trend. Call if chest pain returns."
  }
}
```

#### Progress Notes (SOAP Format)
```
SOAP_NOTE_RULES = [
  "S: Use patient's own words in quotes where possible",
  "O: Objective data only — observations, vitals, physical findings, results",
  "A: Nursing assessment conclusion — what this data means clinically",
  "P: Specific interventions with timeframes — not vague intentions",
  "Avoid: 'Patient appears comfortable' → use measurable data instead",
  "Avoid: 'Will continue to monitor' → specify what, how often, and triggers for escalation"
]
```

#### Care Plan Structure
```
CARE_PLAN = {
  "nursing_diagnosis": "Problem + etiology + evidence (PES format)",
  "goal":              "SMART: Specific, Measurable, Achievable, Relevant, Time-bound",
  "interventions":     "Specific nursing actions with rationale",
  "evaluation":        "How and when progress will be measured",

  "example": {
    "diagnosis":  "Impaired skin integrity related to immobility as evidenced by 2cm Stage 2 sacral pressure injury",
    "goal":       "Wound will show signs of healing (reduced size, no infection) within 7 days",
    "interventions": [
      "2-hourly repositioning with documentation",
      "Pressure-relieving mattress in use",
      "Wound assessment and dressing change per protocol daily",
      "Nutritional support: dietitian referral completed"
    ],
    "evaluation": "Wound measurement and photography every 48 hours"
  }
}
```

### Step 4: Patient and Family Communication

Plain language translation is one of the highest-value things a nurse does and one of the
hardest to do well under time pressure.
```
PLAIN_LANGUAGE_RULES = {
  "reading_level":  "Aim for Grade 6-8 reading level",
  "sentence_length": "Maximum 15 words per sentence for key instructions",
  "avoid":          ["medical jargon without explanation", "passive voice", "double negatives"],
  "structure":      ["What is happening", "Why it matters", "What the patient needs to do", "When to call for help"],
  "teach_back":     "End with: 'Can you tell me in your own words what you will do when...'",

  "example_translation": {
    "clinical":   "The patient is experiencing acute decompensated heart failure requiring diuresis",
    "plain":      "Your heart is not pumping as strongly as it should be, so fluid is building up
                   in your lungs. We are giving you medication through the drip to help your body
                   remove the extra fluid. You may need to urinate more than usual — that means
                   the medication is working."
  }
}
```

---

## Specialty Adaptations
```
SPECIALTY_ADJUSTMENTS = {
  "ICU":         "Prioritize: ventilator documentation, sedation scoring, MAP targets, fluid balance",
  "Emergency":   "Prioritize: triage documentation, time-critical interventions, rapid handover",
  "Paediatrics": "Adjust: weight-based calculations, developmental language, parent communication",
  "Aged Care":   "Prioritize: falls prevention, cognitive assessment, advance care planning",
  "Mental Health": "Prioritize: MSE documentation, therapeutic communication, risk assessment",
  "Community":   "Prioritize: home assessment, functional independence, carer support documentation"
}
```

---

## Professional Support

Beyond clinical documentation, nurses navigate a profession with significant workplace complexity.
```
PROFESSIONAL_SCENARIOS = {
  "performance_review":  "Structure achievements using STAR: Situation, Task, Action, Result",
  "incident_report":     "Factual, chronological, first-person, no blame language",
  "scope_of_practice":  "Flag tasks outside scope. Never document performing tasks not within license.",
  "workplace_conflict":  "Structured communication using DESC: Describe, Express, Specify, Consequence",
  "burnout_recognition": "Identify signs, provide language for conversations with management"
}
```

---

## Quality and Safety Standards
```
DOCUMENTATION_STANDARDS = {
  "timeliness":   "Document as close to the event as possible. Note if retrospective.",
  "accuracy":     "Record what was observed and done — not what was planned or assumed",
  "objectivity":  "Avoid interpretive language unless clearly labeled as assessment",
  "completeness": "If it was not documented, it was not done",
  "corrections":  "Single line through errors, initial and date. Never delete.",
  "escalation":   "Always document clinical concerns communicated and to whom"
}
```

## Safety Flags

The skill automatically flags when:
- A query involves medication calculations → verify with pharmacy or senior clinician
- A query involves scope of practice uncertainty → escalate before acting
- Documentation involves a sentinel event → follow incident reporting protocol
- A patient communication involves informed consent → ensure RN or medical staff involvement
