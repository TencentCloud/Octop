---
name: Exam
description: Generate practice tests, flashcards, study schedules, and timed simulations from any study material.
---

## What This Skill Does

Complete exam preparation from your content:
- **Practice tests** — Multiple choice, short answer, essay questions
- **Flashcards** — Key concepts for spaced repetition, Anki-exportable
- **Simulations** — Timed mock exams matching real format
- **Gap analysis** — Identify weak areas, prioritize weak topics
- **Study schedules** — Realistic calendars based on exam date and availability
- **Summaries** — Condense chapters to 1-2 pages of exam-relevant content
- **Concept maps** — Visualize how topics connect
- **Quick review sheets** — Last-minute "cheat sheets" for 30-min pre-exam review

Works for: university exams, certifications (AWS, PMP, etc.), standardized tests, professional licensing.

---

## Quick Reference

| Task | Load |
|------|------|
| Question generation patterns | `questions.md` |
| Flashcard formats and strategies | `flashcards.md` |
| Timed simulation setup | `simulations.md` |
| Performance tracking | `tracking.md` |

---

## Core Workflow

### 1. Provide Source Material
User shares: notes, textbook chapters, slides, documentation, past exams.

### 2. Generate Questions
Agent creates questions at specified difficulty:
- **Easy** — Recall, definitions, basic concepts
- **Medium** — Application, comparison, analysis
- **Hard** — Synthesis, edge cases, multi-step reasoning

### 3. Practice & Track
User answers, agent scores and tracks performance by topic.

### 4. Focus Weak Areas
Agent identifies gaps, generates targeted practice.

---

## Question Types

| Type | Format | Best For |
|------|--------|----------|
| Multiple choice | 4 options, 1 correct | Quick assessment, certifications |
| Multiple select | N options, M correct | Complex topics |
| True/False | Statement + T/F | Fast review |
| Short answer | 1-3 sentences | Definitions, explanations |
| Fill blank | Sentence with ___ | Terminology |
| Matching | Connect pairs | Relationships |
| Essay | Open response | Deep understanding |

---

## Generating Questions

**From notes:**
```
User: "Generate 10 questions from these AWS S3 notes"
Agent: Creates mix of types, varying difficulty
```

**By topic:**
```
User: "5 hard questions on database normalization"
Agent: Generates challenging application questions
```

**Exam style:**
```
User: "Make questions like the PMP exam"
Agent: Matches official format, question style, difficulty
```

---

## Practice Session

```
📝 Practice: AWS S3 (10 questions)

Q1/10 [Medium]
Which S3 storage class has the lowest cost for infrequently accessed data with millisecond retrieval?

A) S3 Standard
B) S3 Intelligent-Tiering
C) S3 Standard-IA ✓
D) S3 Glacier

Your answer: _
```

After answer:
```
✅ Correct!

S3 Standard-IA is designed for infrequently accessed data 
but requires rapid access when needed. Glacier has lower 
cost but retrieval takes minutes to hours.

[Next] [Skip] [End session]
```

---

## Storage

```
~/exams/
├── {subject}/
│   ├── questions.jsonl    # Question bank
│   ├── sessions.jsonl     # Practice history
│   ├── performance.json   # Stats by topic
│   └── flashcards.json    # Generated cards
```

---

## Study Planning

```
"Create a study schedule — exam in 2 weeks, 3 hours/day available"
"Summarize chapter 5 focusing on what's likely to be on the exam"
"Make a concept map for [topic]"
"Generate a 1-page quick review sheet for [subject]"
"Remind me to study at 7pm daily" (uses cron)
```

---

## Commands

```
"Generate 20 questions from [material]"
"Quiz me on [topic]"
"Start a timed simulation (50 questions, 60 minutes)"
"Show my weak areas"
"Create flashcards for [topic]"
"Review mistakes from last session"
"Grade my essay answer and suggest improvements"
```

---

### Active Subjects
<!-- Subjects being studied -->

### Performance Summary
<!-- Overall stats and trends -->

### Focus Areas
<!-- Topics needing more practice -->
