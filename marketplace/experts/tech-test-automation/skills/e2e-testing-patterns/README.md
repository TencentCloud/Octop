# E2E Testing Patterns

Build reliable, fast end-to-end test suites with Playwright and Cypress. Critical user journey coverage, flaky test elimination, and CI/CD integration.

## What's Inside

- Test pyramid guidance (what E2E tests are for vs. not for)
- Core principles (behavior over implementation, independent tests, deterministic waits, stable selectors)
- Playwright patterns (config, Page Object Model, fixtures, smart waiting, network mocking)
- Cypress patterns (custom commands, network intercepts)
- Selector strategy with priority ranking (roles → labels → data-testid → text)
- Visual regression testing
- Accessibility testing with axe-core
- Debugging failed tests (headed mode, trace viewer, test steps)
- Flaky test diagnosis checklist
- CI/CD integration with GitHub Actions

## When to Use

- Implementing E2E test automation for a web application
- Debugging flaky tests that fail intermittently
- Setting up CI/CD test pipelines with browser tests
- Testing critical user workflows (auth, checkout, signup)
- Choosing what to test with E2E vs unit/integration tests

## Installation

```bash
npx add https://github.com/wpank/ai/tree/main/skills/testing/e2e-testing-patterns
```

### OpenClaw / Moltbot / Clawbot

```bash
npx clawhub@latest install e2e-testing-patterns
```

### Manual Installation

#### Cursor (per-project)

From your project root:

```bash
mkdir -p .cursor/skills
cp -r ~/.ai-skills/skills/testing/e2e-testing-patterns .cursor/skills/e2e-testing-patterns
```

#### Cursor (global)

```bash
mkdir -p ~/.cursor/skills
cp -r ~/.ai-skills/skills/testing/e2e-testing-patterns ~/.cursor/skills/e2e-testing-patterns
```

#### Claude Code (per-project)

From your project root:

```bash
mkdir -p .claude/skills
cp -r ~/.ai-skills/skills/testing/e2e-testing-patterns .claude/skills/e2e-testing-patterns
```

#### Claude Code (global)

```bash
mkdir -p ~/.claude/skills
cp -r ~/.ai-skills/skills/testing/e2e-testing-patterns ~/.claude/skills/e2e-testing-patterns
```

## Related Skills

- [testing-patterns](../testing-patterns/) — Unit and integration testing patterns
- [testing-workflow](../testing-workflow/) — Orchestrates E2E testing within the full testing strategy
- [quality-gates](../quality-gates/) — CI/CD quality checkpoints including E2E gates

---

Part of the [Testing](..) skill category.
