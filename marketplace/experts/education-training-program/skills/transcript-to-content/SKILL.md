---
name: transcript-to-content
description: This skill transforms training and onboarding meeting transcripts into structured learning materials, documentation, and actionable review content. Use this skill when processing meeting transcripts from onboarding sessions, training meetings, or knowledge transfer conversations to extract key information and generate study guides, quick reference sheets, checklists, FAQ documents, action item lists, and training effectiveness assessments.
---

# Transcript to Content

Transform raw meeting transcripts and training session recordings into structured learning materials, documentation, and actionable insights.

## When to Use This Skill

Use this skill when:
- User provides meeting transcripts, training session recordings, or onboarding notes
- User requests structured learning materials from verbal/conversational data
- User asks to extract key information, procedures, or action items from meetings
- User needs to create training documentation, SOPs, or reference materials from transcripts
- User wants to generate study guides, checklists, or FAQ documents from training sessions

## Core Workflow

### Step 1: Understand the Request

Identify what type of content the user needs:

| Output Type | When to Use |
|------------|-------------|
| **Master Knowledge Source** | Comprehensive structured learning module with metadata, terminology, SOPs, nuances, and assessments |
| **Presentation/Slide Deck** | Visual training presentation for delivery or reference |
| **SOP Document** | Step-by-step procedural documentation |
| **Quick Reference Sheet** | Concise one-page summary of key points and procedures |
| **Study Guide** | Organized review material for learners |
| **Checklist** | Actionable task list extracted from procedures |
| **FAQ Document** | Common questions and answers from training content |
| **Action Items List** | Tasks, owners, and deadlines from meeting discussions |

### Step 2: Locate and Analyze Source Material

**If transcripts are in project directory:**
```bash
ls -lah /home/ubuntu/projects/[project-name]/
```

**Search for relevant content by keyword:**
```bash
grep -ri "keyword" /home/ubuntu/projects/[project-name]/*.md
```

**Read and identify:**
- Main topics and concepts
- Step-by-step procedures
- Critical warnings or nuances
- Terminology and definitions
- Real examples or scenarios
- Action items and decisions
- Questions and answers

### Step 3: Extract Structured Content

Apply **Chain of Thought processing:**

1. **Read entire transcript(s)** for macro-context and overall themes
2. **Isolate distinct topics** and group related information
3. **Extract facts, steps, and definitions** with precision
4. **Remove conversational filler** ("um," "uh," "I think," "maybe," "let's try")
5. **Convert to imperative, authoritative language** (use action verbs)
6. **Flag unknowns** with `[MISSING INFO]` rather than fabricating

**For Master Knowledge Source format:**

Read `/home/ubuntu/skills/transcript-to-content/references/master-knowledge-source-format.md` for complete schema and examples.

Extract these sections:
- **Module Metadata:** Topic and learning objective (1 sentence)
- **Key Terminology:** Definitions of jargon, acronyms, tools
- **Standard Operating Procedures:** Numbered steps in "Action > Result" format
- **Critical Nuances:** Warnings, consequences, best practices, context
- **Assessment Data:** 3-5 multiple-choice questions based strictly on content

**For other document types:**

- **Checklists:** Extract sequential action items with checkboxes
- **FAQs:** Identify questions asked and answers provided
- **Study Guides:** Organize by topic with key concepts and examples
- **Action Items:** Extract tasks with owners and deadlines

### Step 4: Apply Branding (if applicable)

**If user provides brand assets:**
- Ask for logo file, brand colors, and font preferences
- Store logo in working directory
- Apply brand colors consistently (primary color for accents, highlights, charts)
- Use specified fonts or professional web fonts (Inter, Roboto, Open Sans)

**If no branding provided:**
- Use clean, professional neutral palette
- Focus on clarity and readability
- Apply consistent styling throughout

### Step 5: Create Deliverables

#### For Presentations

Read `/home/ubuntu/skills/transcript-to-content/references/presentation-guidelines.md` for detailed guidelines.

**Workflow:**
1. Initialize presentation using `slide_initialize` tool
2. Create outline (max 12 slides by default unless user specifies)
3. Copy logo to project directory if provided:
   ```bash
   cp [logo-path] [project-dir]/logo.png
   ```
4. Edit slides one by one using `slide_edit` tool
5. Present using `slide_present` tool
6. Export to PDF if requested:
   ```bash
   manus-export-slides manus-slides://[version-id] pdf
   ```

**Standard presentation structure:**
1. Title slide
2. Definition/overview
3. Step-by-step content (4-6 steps)
4. Critical success factors
5. Common pitfalls
6. Key takeaways
7. Closing slide

**Design requirements:**
- Use brand color (if provided) or professional neutral palette
- Include logo on every slide (if provided)
- Maintain 720px height limit
- Use clean, grid-based layouts
- No excessive shadows, rounded corners, or animations

#### For SOP Documents

Create Markdown documents with:
- Clear hierarchical structure (H1, H2, H3)
- Numbered procedures with imperative language
- Warning/caution callouts in blockquotes
- Tables for reference data
- Inline citations where applicable

**Example structure:**
```markdown
# [Procedure Name]

## Overview
[Brief description]

## Prerequisites
- [Required items or conditions]

## Procedure
1. [Action step]
2. [Action step]
3. **CRITICAL:** [Important step with warning]

## Troubleshooting
- **Issue:** [Problem]
  **Solution:** [Resolution]
```

#### For Quick Reference Sheets

Create concise one-page documents with:
- Key terminology in definition list format
- Essential steps in numbered lists
- Critical warnings in highlighted boxes
- Common scenarios with solutions

#### For Study Guides

Organize by topic with:
- Learning objectives
- Key concepts with explanations
- Examples and scenarios
- Practice questions
- Additional resources

#### For Checklists

Extract action items with:
- Checkbox format (`- [ ]`)
- Clear, actionable language
- Logical sequence
- Optional: Priority indicators or time estimates

#### For FAQ Documents

Structure as:
- Question in bold
- Answer in clear, concise language
- Optional: Related questions or resources

#### For Master Knowledge Source

Follow the schema in `references/master-knowledge-source-format.md` exactly:
- Output ONLY the structured content (no preamble or postscript)
- Use strict Markdown formatting
- Convert all conversational language to authoritative instructions
- Flag unknowns with `[MISSING INFO]`

## Quality Standards

**Content Accuracy:**
- Base all content strictly on source material
- Never fabricate steps, data, or information
- Flag incomplete procedures clearly with `[MISSING INFO]`
- Verify terminology definitions against source

**Clarity and Readability:**
- Use imperative voice for instructions ("Click", "Navigate", "Set")
- Maintain clear visual hierarchy
- Ensure scannability with headings and lists
- Remove all conversational filler

**Consistency:**
- Apply formatting standards throughout
- Use consistent terminology
- Maintain uniform structure across similar sections

**Branding (if applicable):**
- Use brand colors consistently
- Include logo on all branded materials
- Apply specified fonts
- Follow brand style guidelines

## Common Patterns

### Pattern 1: Single Topic Training Presentation
User provides transcript(s) on one topic → Extract key content → Create 8-12 slide presentation

### Pattern 2: Multiple Topics to Learning Modules
User provides multiple transcripts → Extract each as separate module → Deliver as structured documents

### Pattern 3: Quick Reference SOP
User needs specific procedure → Extract relevant steps → Create concise SOP document

### Pattern 4: Training Overview Summary
User requests summary of topic → Search transcripts → Extract and synthesize key points → Deliver as Markdown

### Pattern 5: Onboarding Checklist
User provides onboarding transcript → Extract sequential tasks → Create checklist with checkboxes

### Pattern 6: Meeting Action Items
User provides meeting notes → Extract decisions and tasks → Create action items list with owners

## Troubleshooting

**Issue:** Slide appears empty in PDF
**Solution:** Check padding values. Reduce padding, adjust spacing, ensure content fits within 720px height.

**Issue:** Logo not displaying
**Solution:** Verify logo was copied to project directory. Use absolute path in HTML.

**Issue:** Content seems incomplete
**Solution:** Flag with `[MISSING INFO]` rather than guessing. Ask user for clarification if critical.

**Issue:** Presentation exceeds height limit
**Solution:** Reduce font sizes, decrease spacing, condense content, or split into additional slides.

**Issue:** Too much conversational filler in output
**Solution:** Apply stricter filtering. Remove phrases like "I think," "maybe," "um," "uh," "let's try."

**Issue:** Procedures lack clarity
**Solution:** Convert to imperative voice. Use action verbs. Add "CRITICAL" prefix to important steps.

## Resources

- **Master Knowledge Source Format:** `references/master-knowledge-source-format.md` - Complete schema for structured learning modules
- **Presentation Guidelines:** `references/presentation-guidelines.md` - Detailed presentation design and creation guidelines
