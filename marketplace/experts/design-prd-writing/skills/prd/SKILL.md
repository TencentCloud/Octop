---
name: prd
description: Create and manage Product Requirements Documents (PRDs). Use when: (1) Creating structured task lists with user stories, (2) Specifying features with acceptance criteria, (3) Planning feature implementation for AI agents or human developers.
author: Benjamin Jesuiter <bjesuiter@gmail.com>
metadata:
  clawdbot:
    emoji: "📋"
    os: ["darwin", "linux"]
---

# PRD Skill

Create and manage Product Requirements Documents (PRDs) for feature planning.

## What is a PRD?

A **PRD (Product Requirements Document)** is a structured specification that:

1. Breaks a feature into **small, independent user stories**
2. Defines **verifiable acceptance criteria** for each story
3. Orders tasks by **dependency** (schema → backend → UI)

## Quick Start

1. Create/edit `agents/prd.json` in the project
2. Define user stories with acceptance criteria
3. Track progress by updating `passes: false` → `true`

## prd.json Format

```json
{
  "project": "MyApp",
  "branchName": "ralph/feature-name",
  "description": "Short description of the feature",
  "userStories": [
    {
      "id": "US-001",
      "title": "Add priority field to database",
      "description": "As a developer, I need to store task priority.",
      "acceptanceCriteria": [
        "Add priority column: 'high' | 'medium' | 'low'",
        "Generate and run migration",
        "Typecheck passes"
      ],
      "priority": 1,
      "passes": false,
      "notes": ""
    }
  ]
}
```

### Field Descriptions

| Field | Description |
|-------|-------------|
| `project` | Project name for context |
| `branchName` | Git branch for this feature (prefix with `ralph/`) |
| `description` | One-line feature summary |
| `userStories` | List of stories to complete |
| `userStories[].id` | Unique identifier (US-001, US-002) |
| `userStories[].title` | Short descriptive title |
| `userStories[].description` | "As a [user], I want [feature] so that [benefit]" |
| `userStories[].acceptanceCriteria` | Verifiable checklist items |
| `userStories[].priority` | Execution order (1 = first) |
| `userStories[].passes` | Completion status (`false` → `true` when done) |
| `userStories[].notes` | Runtime notes added by agent |

## Story Sizing

**Each story should be completable in one context window.**

### ✅ Right-sized:
- Add a database column and migration
- Add a UI component to an existing page
- Update a server action with new logic
- Add a filter dropdown to a list

### ❌ Too large (split these):
- "Build the entire dashboard" → Split into: schema, queries, UI, filters
- "Add authentication" → Split into: schema, middleware, login UI, session

## Story Ordering

Stories execute in priority order. Earlier stories must NOT depend on later ones.

**Correct order:**
1. Schema/database changes (migrations)
2. Server actions / backend logic
3. UI components that use the backend
4. Dashboard/summary views

## Acceptance Criteria

Must be verifiable, not vague.

### ✅ Good:
- "Add `status` column to tasks table with default 'pending'"
- "Filter dropdown has options: All, Active, Completed"
- "Typecheck passes"

### ❌ Bad:
- "Works correctly"
- "User can do X easily"

**Always include:** `"Typecheck passes"`

## Progress Tracking

Update `passes: true` when a story is complete. Use `notes` field for runtime observations:

```json
"notes": "Used IF NOT EXISTS for migrations"
```

## Quick Reference

| Action | Command |
|--------|---------|
| Create PRD | Save to `agents/prd.json` |
| Check status | `cat prd.json | jq '.userStories[] | {id, passes}'` |
| View incomplete | `jq '.userStories[] | select(.passes == false)' prd.json` |

## Resources

See `references/` for detailed documentation:
- `agent-usage.md` - How AI agents execute PRDs (Claude Code, OpenCode, etc.)
- `workflows.md` - Sequential workflow patterns
- `output-patterns.md` - Templates and examples
