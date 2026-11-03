# Question Generation

How to create effective practice questions.

---

## From Source Material

### Process
1. User provides content (notes, docs, slides)
2. Extract key concepts, facts, relationships
3. Generate questions at multiple difficulty levels
4. Include distractors (wrong answers) that test understanding

### Extraction Targets
- **Definitions** → What is X?
- **Facts** → When/where/who?
- **Processes** → Steps, sequences
- **Comparisons** → Differences between X and Y
- **Applications** → When would you use X?
- **Relationships** → How does X affect Y?

---

## Question Patterns

### Multiple Choice
```
[Difficulty: Medium]
Question: {Clear, unambiguous question}

A) {Plausible distractor}
B) {Correct answer}
C) {Common misconception}
D) {Partially correct}

Answer: B
Explanation: {Why B is correct, why others are wrong}
```

**Distractor quality matters:**
- Should be plausible to someone who doesn't know
- Test common misconceptions
- Similar length to correct answer
- No obvious tells ("always", "never")

### Short Answer
```
[Difficulty: Medium]
Question: Explain the difference between TCP and UDP.

Expected: {Key points that should be covered}
- TCP is connection-oriented, UDP is connectionless
- TCP guarantees delivery, UDP does not
- TCP has higher overhead

Scoring: {Partial credit criteria}
```

### Scenario-Based
```
[Difficulty: Hard]
Scenario: A company needs to store 10TB of log files that 
are accessed once per month for compliance audits.

Question: Which storage solution minimizes cost while 
meeting access requirements?

A) S3 Standard
B) S3 Standard-IA
C) S3 Glacier Flexible Retrieval
D) S3 Glacier Deep Archive

Answer: C
Explanation: Monthly access rules out Deep Archive (12h+ retrieval).
Glacier Flexible allows hours retrieval at lower cost than IA.
```

---

## Difficulty Calibration

| Level | Cognitive Skill | Example |
|-------|-----------------|---------|
| Easy | Remember, Define | "What does ACID stand for?" |
| Medium | Apply, Analyze | "Which isolation level prevents phantom reads?" |
| Hard | Evaluate, Create | "Design a schema that balances normalization with query performance for..." |

**Distribution for practice:**
- First session: 40% easy, 40% medium, 20% hard
- After basics: 20% easy, 50% medium, 30% hard
- Pre-exam: 10% easy, 40% medium, 50% hard

---

## Avoiding Bad Questions

❌ **Ambiguous:** "Describe databases" (too vague)
❌ **Trivial:** "Is SQL a language?" (yes/no, no learning)
❌ **Trick questions:** Testing attention, not knowledge
❌ **Double negatives:** "Which is NOT incorrect?"
❌ **All of the above:** Lazy question design

✅ **Good questions:**
- One clear correct answer
- Test understanding, not memorization
- Plausible distractors
- Appropriate difficulty
- Actionable feedback on wrong answers

---

## Question Bank Management

**Storage format (questions.jsonl):**
```json
{"id": "q001", "topic": "s3", "type": "mc", "difficulty": "medium", "question": "...", "options": [...], "answer": "B", "explanation": "..."}
{"id": "q002", "topic": "ec2", "type": "short", "difficulty": "easy", "question": "...", "expected": [...]}
```

**Avoiding repeats:**
- Track questions shown in sessions.jsonl
- Rotate through bank before repeating
- Prioritize questions user got wrong
