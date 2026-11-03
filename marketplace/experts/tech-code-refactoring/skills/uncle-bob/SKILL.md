---
name: uncle-bob
description: 'Apply Robert C. Martin (Uncle Bob) principles for clean code, SOLID design, and clean architecture. Use when: (1) reviewing or refactoring code for quality, (2) designing modules, classes, or functions, (3) asked to "clean up" or improve code structure, (4) evaluating architectural boundaries, (5) naming things, (6) reducing coupling or increasing cohesion. Triggers on phrases like "clean code", "SOLID", "uncle bob", "clean architecture", "refactor for quality", "code smells", "single responsibility", "dependency inversion".'
---

# Uncle Bob — Clean Code & Architecture Principles

Apply these principles when writing, reviewing, or refactoring code. They are not rules to follow blindly — use judgment, but default to clean.

## The Boy Scout Rule

Leave the code cleaner than you found it. Every commit should improve the codebase, even if slightly.

## Clean Code Fundamentals

### Naming

- Names reveal intent. If a name requires a comment, the name is wrong.
- Use pronounceable, searchable names. Avoid abbreviations, single letters (except loop counters), and prefixes.
- Classes/types: noun or noun phrase (`AccountManager`, `OrderRepository`).
- Functions/methods: verb or verb phrase (`calculateTotal`, `fetchUser`, `isValid`).
- Booleans: read as a question (`isActive`, `hasPermission`, `canExecute`).
- Avoid mental mapping. `r` is not a URL. Say `url`.

### Functions

- Small. Then smaller. A function does **one thing**.
- Ideally 0-2 arguments. 3+ is a smell — extract an options object or rethink the design.
- No side effects. A function named `checkPassword` must not also initialize a session.
- Command-Query Separation: a function either does something (command) or answers something (query), never both.
- Don't Repeat Yourself (DRY) — but don't abstract prematurely. Three instances of duplication is the threshold.
- Extract till you drop: if you can extract a meaningful sub-function, do it.

### Comments

- Good code is self-documenting. Comments compensate for failure to express in code.
- Legal, informative, clarifying intent, warning of consequences, and TODO comments are acceptable.
- Delete commented-out code. Version control remembers.
- Never write comments that restate what the code does (`// increment i` before `i++`).

### Formatting

- Vertical: newspaper metaphor — high-level summary at top, details below.
- Related functions stay close. Caller above callee.
- Horizontal: avoid scrolling. Keep lines short.
- Consistent formatting across the team trumps personal preference.

### Error Handling

- Prefer exceptions/Result types over error codes.
- Don't return null. Don't pass null.
- Write try-catch at the top level of a function, not scattered throughout.
- Error handling is **one thing** — a function that handles errors should do little else.
- Define exception classes in terms of the caller's needs, not the thrower's implementation.

### Objects vs. Data Structures

- Objects hide data, expose behavior. Data structures expose data, have no behavior.
- Don't mix them. A class with public fields AND business methods is the worst of both worlds.
- Law of Demeter: a method should only call methods on its own object, its parameters, objects it creates, or its direct dependencies. No `a.getB().getC().doThing()`.

## SOLID Principles

For detailed explanations and examples, see [references/solid.md](references/solid.md).

- **S — Single Responsibility**: A class has one reason to change. One actor, one responsibility.
- **O — Open/Closed**: Open for extension, closed for modification. Use polymorphism, not conditionals.
- **L — Liskov Substitution**: Subtypes must be substitutable for their base types without breaking behavior.
- **I — Interface Segregation**: Many specific interfaces beat one general-purpose interface. Clients should not depend on methods they don't use.
- **D — Dependency Inversion**: Depend on abstractions, not concretions. High-level modules must not depend on low-level modules.

## Clean Architecture

For the full architecture guide, see [references/clean-architecture.md](references/clean-architecture.md).

### The Dependency Rule

Source code dependencies must point **inward** — toward higher-level policies.

```
Frameworks & Drivers → Interface Adapters → Use Cases → Entities
(outer)                                                  (inner)
```

- **Entities**: enterprise business rules, pure domain objects.
- **Use Cases**: application-specific business rules (orchestrate entities).
- **Interface Adapters**: convert between use case format and external format (controllers, presenters, gateways).
- **Frameworks & Drivers**: the outermost layer (DB, web framework, UI). Details. Replaceable.

### Key Rules

- Nothing in an inner circle knows about anything in an outer circle.
- Data crossing boundaries is simple DTOs or value objects — never framework-specific types.
- The database is a detail. The web is a detail. Frameworks are details.

## Component Principles

- **Common Closure Principle (CCP)**: classes that change together belong together.
- **Common Reuse Principle (CRP)**: don't force users to depend on things they don't use.
- **Stable Dependencies Principle**: depend in the direction of stability.
- **Stable Abstractions Principle**: stable components should be abstract.

## Code Smells (Red Flags)

- Rigidity: small change causes cascade of changes elsewhere.
- Fragility: change in one place breaks unrelated code.
- Immobility: can't reuse a module without dragging its dependencies.
- Needless complexity: speculative generality, premature abstraction.
- Needless repetition: copy-paste code (DRY violation).
- Opacity: code is hard to understand.
- Long functions, large classes, long parameter lists, boolean flags, switch/case on type.

## Testing (TDD)

- **Three Laws of TDD**: (1) Write a failing test first. (2) Write only enough test to fail. (3) Write only enough production code to pass.
- Tests are first-class code. Keep them clean, readable, fast.
- One assert per test (guideline, not dogma). One concept per test.
- F.I.R.S.T.: Fast, Independent, Repeatable, Self-validating, Timely.
- Test boundaries, not implementations. Test behavior, not methods.

## Applying These Principles

When reviewing or writing code, check in this order:

1. **Readability**: Can someone understand this in 30 seconds?
2. **Naming**: Do names reveal intent?
3. **Function size**: Can anything be extracted?
4. **Single Responsibility**: Does each unit have one reason to change?
5. **Dependencies**: Do they point toward stability/abstraction?
6. **Coupling**: Is anything unnecessarily coupled?
7. **Error handling**: Is it clean and consistent?
8. **Tests**: Are they present, clean, and testing behavior?
