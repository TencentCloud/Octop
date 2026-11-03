---
name: e2e-testing-patterns
model: standard
category: testing
description: Build reliable, fast E2E test suites with Playwright and Cypress. Critical user journey coverage, flaky test elimination, CI/CD integration.
version: 1.0
keywords: [e2e, end-to-end, playwright, cypress, browser testing, integration tests, test automation, flaky tests, visual regression]
---

# E2E Testing Patterns

> Test what users do, not how code works. E2E tests prove the system works as a whole — they're your confidence to ship.


## Installation

### OpenClaw / Moltbot / Clawbot

```bash
npx clawhub@latest install e2e-testing-patterns
```


---

## WHAT This Skill Does

Provides patterns for building end-to-end test suites that:
- Catch regressions before users do
- Run fast enough for CI/CD
- Remain stable (no flaky failures)
- Cover critical user journeys without over-testing

## WHEN To Use

- **Implementing E2E test automation** for a web application
- **Debugging flaky tests** that fail intermittently
- **Setting up CI/CD test pipelines** with browser tests
- **Testing critical user workflows** (auth, checkout, signup)
- **Choosing what to test with E2E** vs unit/integration tests

---

## Test Pyramid — Know Your Layer

```
        /\
       /E2E\         ← FEW: Critical paths only (this skill)
      /─────\
     /Integr\        ← MORE: Component interactions, API contracts
    /────────\
   /Unit Tests\      ← MANY: Fast, isolated, cover edge cases
  /────────────\
```

### What E2E Tests Are For

| E2E Tests ✓ | NOT E2E Tests ✗ |
|-------------|-----------------|
| Critical user journeys (login → dashboard → action → logout) | Unit-level logic (use unit tests) |
| Multi-step flows (checkout, onboarding wizard) | API contracts (use integration tests) |
| Cross-browser compatibility | Edge cases (too slow, use unit tests) |
| Real API integration | Internal implementation details |
| Authentication flows | Component visual states (use Storybook) |

**Rule of thumb:** If it would devastate your business to break, E2E test it. If it's just inconvenient, test it faster with unit/integration tests.

---

## Core Principles

| Principle | Why | How |
|-----------|-----|-----|
| **Test behavior, not implementation** | Survives refactors | Assert on user-visible outcomes, not DOM structure |
| **Independent tests** | Parallelizable, debuggable | Each test creates its own data, cleans up after |
| **Deterministic waits** | No flakiness | Wait for conditions, not fixed timeouts |
| **Stable selectors** | Survives UI changes | Use `data-testid`, roles, labels — never CSS classes |
| **Fast feedback** | Developers run them | Mock external services, parallelize, shard |

---

## Playwright Patterns

### Configuration

```typescript
// playwright.config.ts
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30000,
  expect: { timeout: 5000 },
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [["html"], ["junit", { outputFile: "results.xml" }]],
  use: {
    baseURL: "http://localhost:3000",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "firefox", use: { ...devices["Desktop Firefox"] } },
    { name: "webkit", use: { ...devices["Desktop Safari"] } },
    { name: "mobile", use: { ...devices["iPhone 13"] } },
  ],
});
```

### Pattern: Page Object Model

Encapsulate page logic. Tests read like user stories.

```typescript
// pages/LoginPage.ts
import { Page, Locator } from "@playwright/test";

export class LoginPage {
  readonly page: Page;
  readonly emailInput: Locator;
  readonly passwordInput: Locator;
  readonly loginButton: Locator;
  readonly errorMessage: Locator;

  constructor(page: Page) {
    this.page = page;
    this.emailInput = page.getByLabel("Email");
    this.passwordInput = page.getByLabel("Password");
    this.loginButton = page.getByRole("button", { name: "Login" });
    this.errorMessage = page.getByRole("alert");
  }

  async goto() {
    await this.page.goto("/login");
  }

  async login(email: string, password: string) {
    await this.emailInput.fill(email);
    await this.passwordInput.fill(password);
    await this.loginButton.click();
  }
}

// tests/login.spec.ts
import { test, expect } from "@playwright/test";
import { LoginPage } from "../pages/LoginPage";

test("successful login redirects to dashboard", async ({ page }) => {
  const loginPage = new LoginPage(page);
  await loginPage.goto();
  await loginPage.login("user@example.com", "password123");

  await expect(page).toHaveURL("/dashboard");
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
});
```

### Pattern: Fixtures for Test Data

Create and clean up test data automatically.

```typescript
// fixtures/test-data.ts
import { test as base } from "@playwright/test";

export const test = base.extend<{ testUser: TestUser }>({
  testUser: async ({}, use) => {
    // Setup: Create user
    const user = await createTestUser({
      email: `test-${Date.now()}@example.com`,
      password: "Test123!@#",
    });

    await use(user);

    // Teardown: Clean up
    await deleteTestUser(user.id);
  },
});

// Usage — testUser is created before, deleted after
test("user can update profile", async ({ page, testUser }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill(testUser.email);
  // ...
});
```

### Pattern: Smart Waiting

Never use fixed timeouts. Wait for specific conditions.

```typescript
// ❌ FLAKY: Fixed timeout
await page.waitForTimeout(3000);

// ✅ STABLE: Wait for conditions
await page.waitForLoadState("networkidle");
await page.waitForURL("/dashboard");

// ✅ BEST: Auto-waiting assertions
await expect(page.getByText("Welcome")).toBeVisible();
await expect(page.getByRole("button", { name: "Submit" })).toBeEnabled();

// Wait for API response
const responsePromise = page.waitForResponse(
  (r) => r.url().includes("/api/users") && r.status() === 200
);
await page.getByRole("button", { name: "Load" }).click();
await responsePromise;
```

### Pattern: Network Mocking

Isolate tests from real external services.

```typescript
test("shows error when API fails", async ({ page }) => {
  // Mock the API response
  await page.route("**/api/users", (route) => {
    route.fulfill({
      status: 500,
      body: JSON.stringify({ error: "Server Error" }),
    });
  });

  await page.goto("/users");
  await expect(page.getByText("Failed to load users")).toBeVisible();
});

test("handles slow network gracefully", async ({ page }) => {
  await page.route("**/api/data", async (route) => {
    await new Promise((r) => setTimeout(r, 3000)); // Simulate delay
    await route.continue();
  });

  await page.goto("/dashboard");
  await expect(page.getByText("Loading...")).toBeVisible();
});
```

---

## Cypress Patterns

### Custom Commands

```typescript
// cypress/support/commands.ts
declare global {
  namespace Cypress {
    interface Chainable {
      login(email: string, password: string): Chainable<void>;
      dataCy(value: string): Chainable<JQuery<HTMLElement>>;
    }
  }
}

Cypress.Commands.add("login", (email, password) => {
  cy.visit("/login");
  cy.get('[data-testid="email"]').type(email);
  cy.get('[data-testid="password"]').type(password);
  cy.get('[data-testid="login-button"]').click();
  cy.url().should("include", "/dashboard");
});

Cypress.Commands.add("dataCy", (value) => {
  return cy.get(`[data-cy="${value}"]`);
});

// Usage
cy.login("user@example.com", "password");
cy.dataCy("submit-button").click();
```

### Network Intercepts

```typescript
// Mock API
cy.intercept("GET", "/api/users", {
  statusCode: 200,
  body: [{ id: 1, name: "John" }],
}).as("getUsers");

cy.visit("/users");
cy.wait("@getUsers");
cy.get('[data-testid="user-list"]').children().should("have.length", 1);
```

---

## Selector Strategy

| Priority | Selector Type | Example | Why |
|----------|--------------|---------|-----|
| 1 | **Role + name** | `getByRole("button", { name: "Submit" })` | Accessible, user-facing |
| 2 | **Label** | `getByLabel("Email address")` | Accessible, semantic |
| 3 | **data-testid** | `getByTestId("checkout-form")` | Stable, explicit for testing |
| 4 | **Text content** | `getByText("Welcome back")` | User-facing |
| ❌ | CSS classes | `.btn-primary` | Breaks on styling changes |
| ❌ | DOM structure | `div > form > input:nth-child(2)` | Breaks on any restructure |

```typescript
// ❌ BAD: Brittle selectors
cy.get(".btn.btn-primary.submit-button").click();
cy.get("div > form > div:nth-child(2) > input").type("text");

// ✅ GOOD: Stable selectors
page.getByRole("button", { name: "Submit" }).click();
page.getByLabel("Email address").fill("user@example.com");
page.getByTestId("email-input").fill("user@example.com");
```

---

## Visual Regression Testing

```typescript
// Playwright visual comparisons
test("homepage looks correct", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveScreenshot("homepage.png", {
    fullPage: true,
    maxDiffPixels: 100,
  });
});

test("button states", async ({ page }) => {
  const button = page.getByRole("button", { name: "Submit" });

  await expect(button).toHaveScreenshot("button-default.png");

  await button.hover();
  await expect(button).toHaveScreenshot("button-hover.png");
});
```

---

## Accessibility Testing

```typescript
// npm install @axe-core/playwright
import AxeBuilder from "@axe-core/playwright";

test("page has no accessibility violations", async ({ page }) => {
  await page.goto("/");

  const results = await new AxeBuilder({ page })
    .exclude("#third-party-widget")  // Exclude things you can't control
    .analyze();

  expect(results.violations).toEqual([]);
});
```

---

## Debugging Failed Tests

```bash
# Run in headed mode (see the browser)
npx playwright test --headed

# Debug mode (step through)
npx playwright test --debug

# Show trace viewer for failed tests
npx playwright show-report
```

```typescript
// Add test steps for better failure reports
test("checkout flow", async ({ page }) => {
  await test.step("Add item to cart", async () => {
    await page.goto("/products");
    await page.getByRole("button", { name: "Add to Cart" }).click();
  });

  await test.step("Complete checkout", async () => {
    await page.goto("/checkout");
    // ... if this fails, you know which step
  });
});

// Pause for manual inspection
await page.pause();
```

---

## Flaky Test Checklist

When a test fails intermittently, check:

| Issue | Fix |
|-------|-----|
| Fixed `waitForTimeout()` calls | Replace with `waitForSelector()` or expect assertions |
| Race conditions on page load | Wait for `networkidle` or specific elements |
| Test data pollution | Ensure tests create/clean their own data |
| Animation timing | Wait for animations to complete or disable them |
| Viewport inconsistency | Set explicit viewport in config |
| Random test order issues | Tests must be independent |
| Third-party service flakiness | Mock external APIs |

---

## CI/CD Integration

```yaml
# GitHub Actions example
name: E2E Tests
on: [push, pull_request]

jobs:
  e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
      - run: npm ci
      - run: npx playwright install --with-deps
      - run: npm run build
      - run: npm run start & npx wait-on http://localhost:3000
      - run: npx playwright test
      - uses: actions/upload-artifact@v4
        if: failure()
        with:
          name: playwright-report
          path: playwright-report/
```

---

## NEVER Do

1. **NEVER use fixed `waitForTimeout()` or `cy.wait(ms)`** — they cause flaky tests and slow down suites
2. **NEVER rely on CSS classes or DOM structure for selectors** — use roles, labels, or data-testid
3. **NEVER share state between tests** — each test must be completely independent
4. **NEVER test implementation details** — test what users see and do, not internal structure
5. **NEVER skip cleanup** — always delete test data you created, even on failure
6. **NEVER test everything with E2E** — reserve for critical paths; use faster tests for edge cases
7. **NEVER ignore flaky tests** — fix them immediately or delete them; a flaky test is worse than no test
8. **NEVER hardcode test data in selectors** — use dynamic waits for content that varies

---

## Quick Reference

### Playwright Commands

```typescript
// Navigation
await page.goto("/path");
await page.goBack();
await page.reload();

// Interactions
await page.click("selector");
await page.fill("selector", "text");
await page.type("selector", "text");  // Types character by character
await page.selectOption("select", "value");
await page.check("checkbox");

// Assertions
await expect(page).toHaveURL("/expected");
await expect(locator).toBeVisible();
await expect(locator).toHaveText("expected");
await expect(locator).toBeEnabled();
await expect(locator).toHaveCount(3);
```

### Cypress Commands

```typescript
// Navigation
cy.visit("/path");
cy.go("back");
cy.reload();

// Interactions
cy.get("selector").click();
cy.get("selector").type("text");
cy.get("selector").clear().type("text");
cy.get("select").select("value");
cy.get("checkbox").check();

// Assertions
cy.url().should("include", "/expected");
cy.get("selector").should("be.visible");
cy.get("selector").should("have.text", "expected");
cy.get("selector").should("have.length", 3);
```
