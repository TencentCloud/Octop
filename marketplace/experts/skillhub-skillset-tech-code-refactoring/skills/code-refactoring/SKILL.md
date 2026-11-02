---
name: code-refactoring
description: Code refactoring patterns and techniques for improving code quality without changing behavior. Use for cleaning up legacy code, reducing complexity, or improving maintainability.
source: wshobson/agents
license: MIT
domain: engineering
homepage: https://github.com/soponcd/timeflow-skills/tree/main/teams/skills/code-refactoring
metadata:
  clawdbot:
    emoji: ♻️
---

# Code Refactoring

## Refactoring Principles

### When to Refactor
- Before adding new features (make change easy, then make easy change)
- After getting tests passing (red-green-refactor)
- When you see code smells
- During code review feedback

### When NOT to Refactor
- Without tests covering the code
- Under tight deadlines with no safety net
- Code that will be replaced soon
- When you don't understand what the code does

## Common Code Smells

### Long Methods
```typescript
// BEFORE: Method doing too much
function processOrder(order: Order) {
  // 100 lines of validation, calculation, notification, logging...
}

// AFTER: Extract into focused methods
function processOrder(order: Order) {
  validateOrder(order);
  const total = calculateTotal(order);
  saveOrder(order, total);
  notifyCustomer(order);
}
```

### Deeply Nested Conditionals
```typescript
// BEFORE: Arrow code
function getDiscount(user: User, order: Order) {
  if (user) {
    if (user.isPremium) {
      if (order.total > 100) {
        if (order.items.length > 5) {
          return 0.2;
        }
      }
    }
  }
  return 0;
}

// AFTER: Early returns (guard clauses)
function getDiscount(user: User, order: Order) {
  if (!user) return 0;
  if (!user.isPremium) return 0;
  if (order.total <= 100) return 0;
  if (order.items.length <= 5) return 0;
  return 0.2;
}
```

### Primitive Obsession
```typescript
// BEFORE: Primitives everywhere
function createUser(name: string, email: string, phone: string) {
  if (!email.includes('@')) throw new Error('Invalid email');
  // more validation...
}

// AFTER: Value objects
class Email {
  constructor(private value: string) {
    if (!value.includes('@')) throw new Error('Invalid email');
  }
  toString() { return this.value; }
}

function createUser(name: string, email: Email, phone: Phone) {
  // Email is already validated
}
```

### Feature Envy
```typescript
// BEFORE: Method uses another object's data extensively
function calculateShipping(order: Order) {
  const address = order.customer.address;
  const weight = order.items.reduce((sum, i) => sum + i.weight, 0);
  const distance = calculateDistance(address.zip);
  return weight * distance * 0.01;
}

// AFTER: Move method to where the data is
class Order {
  calculateShipping() {
    return this.totalWeight * this.customer.shippingDistance * 0.01;
  }
}
```

## Refactoring Techniques

### Extract Method
```typescript
// Identify a code block that does one thing
// Move it to a new method with a descriptive name
// Replace original code with method call

function printReport(data: ReportData) {
  // Extract this block...
  const header = `Report: ${data.title}\nDate: ${data.date}\n${'='.repeat(40)}`;
  console.log(header);

  // ...into a method
  printHeader(data);
}
```

### Replace Conditional with Polymorphism
```typescript
// BEFORE: Switch on type
function getArea(shape: Shape) {
  switch (shape.type) {
    case 'circle': return Math.PI * shape.radius ** 2;
    case 'rectangle': return shape.width * shape.height;
    case 'triangle': return shape.base * shape.height / 2;
  }
}

// AFTER: Polymorphic classes
interface Shape {
  getArea(): number;
}

class Circle implements Shape {
  constructor(private radius: number) {}
  getArea() { return Math.PI * this.radius ** 2; }
}

class Rectangle implements Shape {
  constructor(private width: number, private height: number) {}
  getArea() { return this.width * this.height; }
}
```

### Introduce Parameter Object
```typescript
// BEFORE: Too many parameters
function searchProducts(
  query: string,
  minPrice: number,
  maxPrice: number,
  category: string,
  inStock: boolean,
  sortBy: string,
  sortOrder: string
) { ... }

// AFTER: Parameter object
interface SearchParams {
  query: string;
  priceRange: { min: number; max: number };
  category?: string;
  inStock?: boolean;
  sort?: { by: string; order: 'asc' | 'desc' };
}

function searchProducts(params: SearchParams) { ... }
```

### Replace Magic Numbers with Constants
```typescript
// BEFORE
if (user.age >= 18 && order.total >= 50) {
  applyDiscount(order, 0.1);
}

// AFTER
const MINIMUM_AGE = 18;
const DISCOUNT_THRESHOLD = 50;
const STANDARD_DISCOUNT = 0.1;

if (user.age >= MINIMUM_AGE && order.total >= DISCOUNT_THRESHOLD) {
  applyDiscount(order, STANDARD_DISCOUNT);
}
```

## Safe Refactoring Process

1. **Ensure tests exist** - Write tests if they don't
2. **Make small changes** - One refactoring at a time
3. **Run tests after each change** - Catch regressions immediately
4. **Commit frequently** - Easy to revert if something breaks
5. **Review the diff** - Make sure behavior hasn't changed

## Refactoring Checklist

- [ ] Tests pass before starting
- [ ] Each change is small and focused
- [ ] Tests pass after each change
- [ ] No behavior changes (only structure)
- [ ] Code is more readable than before
- [ ] Commit message explains the refactoring
