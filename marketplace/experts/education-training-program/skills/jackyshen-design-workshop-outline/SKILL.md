---
name: jackyshen-design-workshop-outline
description: Use when user asks to "generate workshop outline", "create training agenda", "design course structure", "build workshop schedule", or requests help planning training sessions. Applies MECE structure, TfBR design (4Cs), and VAK-inclusive learning.
version: 0.1.0
github: mebusw
social: xhs@敏捷的申导, wechat@申导-敏捷教练
email: mebusw@gmail.com
---

# Workshop Outline Generator

Generate learner-centered workshop and training outlines using MECE structure, Training from Back of Room (TfBR), and VAK learning styles.

## Purpose

Design effective workshop outlines that:
- Apply MECE structure (Mutually Exclusive, Collectively Exhaustive)
- Use TfBR 4C design (Connection, Concepts, Concrete Practice, Conclusion)
- Include VAK elements (Visual-Auditory-Kinesthetic)
- Balance 70% activities / 30% content delivery
- Define measurable, action-based learning outcomes

## When to Use

Trigger when users ask for:
- Workshop or training outlines
- Course structures or agendas
- Training session designs
- 培训大纲 / 工作坊设计 / 课程结构

## Design Process

### 1. Gather Requirements

Clarify before generating:
- **Topic:** What is the training subject?
- **Audience:** Who are the learners? (level, background, pain points)
- **Duration:** Half-day, full-day, multi-day (default: 2 days)
- **Format:** In-person, virtual, hybrid
- **Outcomes:** What should learners be able to DO after training?
- **Practical Level:** Should learners bring real cases for practice?
- **Reference Material:** Existing course outline (if any)

### 2. Apply MECE Structure

Organize into non-overlapping, comprehensive modules:

```
[Topic] Workshop (MECE)
├── Module 1: [Category A]
│   ├── Topic 1.1
│   └── Topic 1.2
├── Module 2: [Category B]
│   ├── Topic 2.1
│   └── Topic 2.2
└── Module 3: [Category C]
    ├── Topic 3.1
    └── Topic 3.2
```

### 3. Define Learning Outcomes

Use performance-based outcomes with action verbs (NOT "understand"):

```
After this module, participants will be able to [action verb] [specific skill]
in [context] to [result].
```

**Action Verbs:** Apply, demonstrate, practice, create, design, analyze, evaluate, deliver

**Example:** "After this module, participants will be able to deliver constructive feedback to direct reports using the SBI model to improve performance without defensiveness."

### 4. Design Using TfBR 4Cs

| 4C Phase | Time | Purpose |
|----------|------|---------|
| **Connection** | 5-10% | Welcome, outcomes, agenda, icebreaker |
| **Concepts** | 20-30% | Just-in-time, just-enough content |
| **Concrete Practice** | 50-70% | Skill drills, role-plays, applications |
| **Conclusion** | 5-10% | Commitments, action planning, resources |

**Activity Types:**
- Assessment: Self-evaluations, diagnostics
- Experience: Simulations, role-plays, games
- Practice: Skill drills, rehearsals
- Reflection: Journaling, pair sharing, ORID debriefs
- Application: Real projects, action planning

### 5. Integrate VAK Elements

| Component | Visual | Auditory | Kinesthetic |
|-----------|--------|----------|-------------|
| Content | Diagrams, models, slides | Stories, explanations | Demonstrations |
| Activities | Charts, worksheets | Discussions, debriefs | Role-plays, movement |
| Materials | Handouts, visuals | Audio | Manipulatives, tools |

### 6. When Reference Outline is Provided

First, provide an optimization table with:
- Assessment of original modules (strengths/weaknesses)
- Restructured module flow and sequence
- New SMART learning objectives per module
- Targeted additions/deletions
- Improved teaching methods and interactive elements
- Revised time allocations

Then generate the detailed outline.

## Output Format

```markdown
# [Workshop Name]

## Overview
**Duration:** [Time] | **Audience:** [Description] | **Format:** [In-person/Virtual/Hybrid]

**Course Background:** [Brief context]

**Learning Outcomes:**
After this workshop, participants will be able to:
1. [Action verb] [skill] in [context] to [result]
2. [Action verb] [skill] in [context] to [result]
3. [Action verb] [skill] in [context] to [result]

**Course Benefits:** [What participants gain]

**Target Audience:** [Who should attend]

**Course Advantages:** [Unique value proposition]

## Agenda Overview

### Day 1 Morning (9:00-12:00)
| Module | Content | Teaching Method |
|--------|---------|-----------------|
| Module 1: [Name] | Key concepts (max 5 points) | Interactive activities with discussion goals |

### Day 1 Afternoon (13:30-17:00)
[Continue table]

## Detailed Outline

### Module 1: [Name] ([Time])

**Learning Outcome:** [Performance-based]

**Flow:**
1. **Connection (X min)** - Welcome, outcomes, agenda
2. **Activity: [Name] (X min)** - Instructions + debrief questions
3. **Concepts: [Topic] (X min)** - Key points supporting activity
4. **Concrete Practice (X min)** - Skill application
5. **Conclusion (X min)** - Key takeaways, commitments

## Materials & Preparation
- [List needed materials]
- [Room setup requirements]
- [Pre-work, if applicable]
```

## Typical Session Structures

**Half-Day (4 hours):**
- Module 1: Foundation (60 min)
- Module 2: Core Skills (90 min)
- Module 3: Application (60 min)
- Closing (30 min)

**Full-Day (7-8 hours):**
- Morning: Module 1-2 (90 min each)
- Lunch (60 min)
- Afternoon: Module 3-4 (90 min each) + Closing (30 min)

**Multi-Day:**
- Day 1: Foundations and Awareness
- Day 2: Skills and Practice
- Day 3: Application and Integration

## Quick Checklist

Before finalizing:
- [ ] MECE structure verified (no gaps, no overlaps)
- [ ] Outcomes use action verbs (not "understand")
- [ ] Activity time ≥ 65%
- [ ] Each module has VAK elements
- [ ] Content is minimal (just-enough, just-in-time)
- [ ] ORID debriefs planned for activities
- [ ] Opening includes outcomes and agenda
- [ ] Closing includes commitments
- [ ] Materials list complete

## Writing Tone

- Professional, rigorous, confident
- Demonstrate consultant-level thinking and problem-solving
- Precise language (not colloquial)
- Coaching and guiding approach (not lecture-style)
- Practical and actionable (avoid theoretical fluff)

## Integration

Reference `jackyshen-list-methods` skill for:
- MECE structuring principles
- TfBR 4C design process
- ORID debrief templates
- VAK integration strategies
