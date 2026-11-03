# Master Knowledge Source Format

This format is used for extracting structured learning content from raw transcripts, meeting notes, and training sessions.

## Purpose

Transform unstructured, raw verbal data (transcripts, meeting notes, shadowing sessions, training recordings) into structured, pedagogical learning assets that can be used to generate interactive websites, slide decks, training manuals, and documentation.

## Core Principles

1. **No Preamble/Postscript:** Output ONLY the structured content. No introduction, summary of what was done, or conclusion.
2. **Objectivity:** Remove all subjective conversational filler ("I think," "Maybe," "Let's try," "um," "uh"). Convert into imperative, authoritative instructions.
3. **Format:** Use strict Markdown.
4. **Unknowns:** If a process seems incomplete in the transcript, flag it with `[MISSING INFO]` rather than hallucinating the rest of the step.

## Processing Method

Apply **Chain of Thought processing**:
1. Read the entire transcript to understand the macro-context
2. Isolate specific distinct topics
3. Extract facts, steps, and definitions
4. Format into the schema below

## Output Schema

Each transcript should produce a structured **Learning Module** containing:

### 1. Module Metadata
A concise title and a 1-sentence learning objective.

**Format:**
```markdown
# Module Metadata
**Topic:** [Concise topic name]
**Objective:** [Single sentence describing what learner will be able to do]
```

### 2. Key Terminology
A definition list of any acronyms, proprietary software names, or industry jargon mentioned.

**Format:**
```markdown
## Key Terminology
* **[Term]:** [Clear, concise definition]
* **[Acronym]:** [Full expansion and meaning]
```

### 3. Standard Operating Procedures (SOPs)
Convert narrative explanations into numbered, step-by-step instructions. Use "Action > Result" format.

**Format:**
```markdown
## Standard Operating Procedures (SOPs)
**Procedure: [Procedure Name]**
1. [Action step with clear imperative verb]
2. [Next action step]
3. **CRITICAL:** [Highlight critical steps with bold prefix]
4. [Continue with remaining steps]
```

### 4. Critical Nuances
Extract specific advice given during shadowing (e.g., "Don't click X until Y happens," or "Clients usually ask about Z here").

**Format:**
```markdown
## Critical Nuances
* **Warning:** [Specific warning or caution]
* **Consequence:** [What happens if warning is ignored]
* **Best Practice:** [Recommended approach or tip]
* **Context:** [When/why this matters]
```

### 5. Assessment Data
Create 3-5 multiple-choice questions based *strictly* on the transcript content to be used for interactive quizzes later.

**Format:**
```markdown
## Assessment Data
**Q1: [Question text]**
A) [Option A]
B) [Option B]
C) [Option C]
D) [Option D]
**Correct Answer:** [Letter]

**Q2: [Next question]**
[Continue format...]
```

## Example

**Input:** "Okay, so when you're in the CRM, um, specifically Salesforce, you don't want to just hit save immediately. You gotta check the 'Active' box first. If you don't, the account goes into a dormant state and IT has to fix it, which takes days. So, click 'Edit', find the 'Active' checkbox, tick it, and then hit 'Save'. Oh, and BDR stands for Business Development Rep, they usually own these leads."

**Output:**
```markdown
# Module Metadata
**Topic:** Salesforce Account Activation
**Objective:** Learn the correct procedure for saving active accounts to prevent data dormancy.

## Key Terminology
* **CRM:** Salesforce (Customer Relationship Management system).
* **Dormant State:** A locked account status requiring IT intervention to resolve.
* **BDR:** Business Development Representative (Owner of leads).

## Standard Operating Procedures (SOPs)
**Procedure: Saving an Account**
1. Navigate to the specific Account page.
2. Click the **Edit** button.
3. Locate the **Active** checkbox.
4. **CRITICAL:** Ensure the **Active** checkbox is ticked *before* saving.
5. Click **Save**.

## Critical Nuances
* **Warning:** Failing to check "Active" before saving triggers a "Dormant State."
* **Consequence:** Dormant states require IT intervention and have a multi-day resolution time.

## Assessment Data
**Q1: What happens if you save an account without checking the 'Active' box?**
A) The BDR is notified.
B) The account becomes Dormant and requires IT fix.
C) The page refreshes automatically.
D) Nothing, it saves as a draft.
**Correct Answer:** B
```
