# Parallel Research with sessions_spawn

Use parallel sub-agents when themes are independent.

## When to Use
- Themes do not depend on each other.
- Time constraints require speed.
- Token budget allows parallel work.

## Workflow

1. Spawn sub-agents with explicit instructions for two cycles.
2. Each sub-agent returns findings, confidence, gaps, and sources.
3. Integrate results across themes.

## Example

```
Theme A: Market landscape
→ sessions_spawn(task="Research market landscape with 2 cycles... return findings, gaps, sources")

Theme B: Security
→ sessions_spawn(task="Research security/compliance with 2 cycles... return findings, gaps, sources")
```
