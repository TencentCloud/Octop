---
name: simplify
description: "Refactor code for clarity, consistency, and maintainability without changing behavior. Use when the user types /simplify or asks to simplify code."
metadata: {"openclaw": {"emoji": "🧹", "user-invocable": true, "homepage": "https://x.com/bcherny/status/2027534984534544489?s=20"}}
---

# Simplify Code

Refactor code to make it easier to read, simpler to maintain, and more consistent with the surrounding codebase without changing what it does.

Invoke this skill with `/simplify`.

## Purpose

Use this skill when a user wants cleaner code, a more direct implementation, or a readability pass that preserves exact functionality.

## Working Principles

**Preserve functionality.** Never change behavior, outputs, side effects, or public interfaces unless the user explicitly asks for that.

**Apply project standards.** Match the existing conventions, patterns, naming style, and architectural expectations of the codebase.

**Reduce unnecessary complexity.** Flatten avoidable nesting, remove redundant abstractions, and prefer the most direct implementation that remains clear.

**Keep variables intentional.** Avoid introducing extra state unless it materially improves readability or is reused enough to justify it.

**Improve naming and structure.** Prefer clear variable and function names, and group related logic so the code reads in a straightforward way.

## Default Scope

Focus on recently modified code unless the user points to a different file, module, or diff.

## Reference

Inspired by the new Claude Code `/simplify` command:

https://x.com/bcherny/status/2027534984534544489?s=20
