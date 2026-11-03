# Workflow Patterns for PRD Skills

## Sequential Workflow Pattern

When a skill involves multi-step processes with dependencies, use sequential workflows.

### Structure
```
## Workflow Decision Tree
## Step 1: [First Step]
## Step 2: [Second Step]
## ...
```

### Example: PRD Creation Workflow
```
## Step 1: Ask Clarifying Questions
Gather context before writing...

## Step 2: Generate Markdown PRD
Save to `tasks/prd-[feature-name].md`...

## Step 3: Convert to prd.json
...

## Step 4: Run Agentic Loop
...
```

## Conditional Logic Pattern

Use branching logic when different paths depend on user choices.

### Structure
```markdown
## Decision: [What is the user trying to do?]

- **Option A**: [Description] → See [Section A]
- **Option B**: [Description] → See [Section B]
```

### Example
```markdown
## Decision: What type of PRD do you need?

- **Quick PRD**: Single file with basic structure → See [Quick Template]
- **Detailed PRD**: Multi-section with full specs → See [Detailed Template]
- **AI-Ready PRD**: Optimized for autonomous agents → See [AI-Ready Format]
```

## Iteration Pattern

For processes that repeat until a condition is met.

### Structure
```markdown
## Repeat Until: [Stop Condition]

1. [Step 1]
2. [Step 2]
...

**Stop when:** [Condition description]
```

### Example (Agentic Loop)
```markdown
## Repeat Until: All stories have passes=true

1. Read prd.json, find first incomplete story
2. Implement the story
3. Run checks (typecheck, tests)
4. If checks pass, mark passes=true
5. Append to progress.txt

**Stop when:** `jq '.userStories[].passes' | grep -q "false"` is false
```

## Progressive Disclosure Pattern

Show overview first, link to details.

```markdown
## Creating Documents

Use docx-js for new documents. See [DOCX-JS.md](DOCX-JS.md) for details.

## Editing Documents

For simple edits, modify XML directly.
- **Tracked changes**: See [REDLINING.md](REDLINING.md)
- **OOXML details**: See [OOXML.md](OOXML.md)
```

## Validation Pattern

Include validation steps throughout.

```markdown
## Step 1: Create Schema

1. Define table structure
2. **Validate**: Run migration, verify no errors

## Step 2: Add Backend Logic

1. Create server action
2. **Validate**: Typecheck passes
3. **Validate**: Integration test passes
```
