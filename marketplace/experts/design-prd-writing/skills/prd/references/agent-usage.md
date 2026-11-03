# Agent Usage Patterns

This document describes how AI coding agents (Claude Code, OpenCode, etc.) can execute PRDs autonomously. **This skill only edits PRDs — agents use this reference to execute them.**

## Unattended Agentic Loop

### Claude Code
```bash
while :; do
  claude --print --dangerously-skip-permissions \
    "Read prd.json, find first story where passes=false, implement it, run checks, update passes=true if successful"
done
```

### OpenCode
```bash
opencode run "Load prd.json, implement next incomplete story, verify, mark complete"
```

### Key Files

| File | Purpose |
|------|---------|
| `prd.json` | Task list with completion status |
| `prompt.md` | Instructions for each iteration |
| `progress.txt` | Append-only learnings log |

## Human-in-the-Loop

### Manual Story-by-Story
```bash
claude "Implement US-001 from prd.json"
# Review, approve, continue to US-002
```

### Git Worktree Strategy
```bash
# Create worktree for feature
git worktree add ../myapp-feature ralph/feature-name

# Run agent in worktree
cd ../myapp-feature
claude "Implement prd.json stories"

# Review in main repo
cd ../myapp && git diff main..ralph/feature-name
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

## Progress Tracking

Append to `progress.txt` after each iteration (never replace):

```markdown
## 2026-01-10 18:00 - US-001
- Implemented: Added priority column to tasks table
- Files changed: migrations/001_add_priority.sql, src/types.ts
- **Learnings:** Use `IF NOT EXISTS` for migrations
---
```

### Codebase Patterns (at top of progress.txt)

```markdown
## Codebase Patterns
- Use `sql<number>` template for aggregations
- Always use `IF NOT EXISTS` for migrations
- Export types from actions.ts for UI components
```

## Checklist Before Running

- [ ] Each story completable in one context window
- [ ] Stories ordered by dependency (schema → backend → UI)
- [ ] Every story has "Typecheck passes" criterion
- [ ] Acceptance criteria are verifiable (not vague)
- [ ] No story depends on a later story

## Tools & Resources

### Official Tools
- [Ralph by snarktank](https://github.com/snarktank/ralph) - Full Ralph implementation
- [Claude Code](https://github.com/anthropics/claude-code) - Anthropic's CLI agent
- [Amp Code](https://ampcode.com) - Another agent runner

### Guides
- [Tips for AI Coding with Ralph Wiggum](https://www.aihero.dev/tips-for-ai-coding-with-ralph-wiggum)
