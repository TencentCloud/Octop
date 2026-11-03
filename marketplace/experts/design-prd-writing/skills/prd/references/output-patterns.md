# Output Patterns and Templates

## prd.json Template

### Basic Structure
```json
{
  "project": "ProjectName",
  "branchName": "ralph/feature-slug",
  "description": "Brief feature description",
  "userStories": [
    {
      "id": "US-001",
      "title": "Clear action title",
      "description": "As a [user], I want [feature] so that [benefit].",
      "acceptanceCriteria": [
        "Specific, verifiable criterion 1",
        "Specific, verifiable criterion 2",
        "Typecheck passes"
      ],
      "priority": 1,
      "passes": false,
      "notes": ""
    }
  ]
}
```

### Example: Database Field Addition
```json
{
  "project": "TaskApp",
  "branchName": "ralph/add-task-priority",
  "description": "Add priority levels to tasks",
  "userStories": [
    {
      "id": "US-001",
      "title": "Add priority column to database",
      "description": "As a developer, I need to store task priority so it persists across sessions.",
      "acceptanceCriteria": [
        "Add priority column: 'high' | 'medium' | 'low' (default 'medium')",
        "Generate and run migration successfully",
        "Typecheck passes"
      ],
      "priority": 1,
      "passes": false,
      "notes": ""
    }
  ]
}
```

### Example: UI Component Addition
```json
{
  "id": "US-002",
  "title": "Display priority indicator on task cards",
  "description": "As a user, I want to see task priority at a glance.",
  "acceptanceCriteria": [
    "Each task card shows colored priority badge",
    "Badge colors: red=high, yellow=medium, gray=low",
    "Priority visible without hovering",
    "Typecheck passes",
    "Verify in browser using dev-browser skill"
  ],
  "priority": 2,
  "passes": false,
  "notes": ""
}
```

## Markdown PRD Template

```markdown
# PRD: [Feature Name]

## Introduction
[Brief description of the feature]

## Goals
- [Goal 1]
- [Goal 2]
- [Goal 3]

## User Stories

### US-001: [Story Title]
**Description:** As a [user], I want [feature] so that [benefit].

**Acceptance Criteria:**
- [ ] [Criterion 1]
- [ ] [Criterion 2]
- [ ] [Criterion 3]

### US-002: [Story Title]
...

## Non-Goals
- [What this PRD does NOT cover]
- [What is explicitly out of scope]

## Technical Considerations
- [Technical constraints or patterns to follow]
- [Dependencies or prerequisites]
```

## Agent Prompt Template

```markdown
# Agent Instructions

You are an autonomous coding agent.

## Your Task

1. Read `prd.json`
2. Read `progress.txt` (check Codebase Patterns first)
3. Checkout/create branch from PRD `branchName`
4. Pick highest priority story where `passes: false`
5. Implement that single story
6. Run quality checks (typecheck, lint, test)
7. If checks pass, commit: `feat: [Story ID] - [Story Title]`
8. Update prd.json: set `passes: true`
9. Append progress to `progress.txt`

## Quality Requirements

- ALL commits must pass typecheck
- Keep changes focused and minimal
- Follow existing code patterns

## Stop Condition

When ALL stories have `passes: true`, output:
<promise>COMPLETE</promise>
```

## Progress.txt Template

```markdown
## Codebase Patterns
- [Pattern 1: reusable insight from earlier iterations]
- [Pattern 2]
- [Pattern 3]

---

## [YYYY-MM-DD HH:MM] - [Story ID]
- **Implemented:** [What was done]
- **Files changed:** [List files]
- **Learnings:**
  - [Insight 1]
  - [Insight 2]
---
```

## Acceptance Criteria Patterns

### Database Changes
```
- Add [column/table] with type [type] and default [value]
- Generate and run migration successfully
- Typecheck passes
```

### API Endpoints
```
- Endpoint [method] [path] returns [expected response]
- Returns [status code] for valid requests
- Returns [status code] for invalid requests
- Typecheck passes
```

### UI Components
```
- [Component] is rendered on [page/section]
- Shows [expected content/behavior]
- [Interactive element] works as expected
- Typecheck passes
- Verify in browser using dev-browser skill
```

### Bug Fixes
```
- [Expected behavior] now occurs when [trigger]
- Regression: [Related functionality] still works
- Typecheck passes
```
