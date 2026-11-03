# SOLID Principles — Detailed Guide

## S — Single Responsibility Principle (SRP)

> "A module should have one, and only one, reason to change."

More precisely: a module should be responsible to one, and only one, actor (stakeholder).

### Violation

```typescript
class Employee {
  calculatePay()    // CFO's team cares about this
  reportHours()     // COO's team cares about this
  save()            // CTO's team cares about this
}
```

Three actors, three reasons to change. A change for payroll could break hour reporting.

### Fix

Separate into three classes, each responsible to one actor. Use a facade if you need a single entry point.

```typescript
class PayCalculator { calculatePay(employee: Employee) {} }
class HourReporter  { reportHours(employee: Employee) {} }
class EmployeeSaver { save(employee: Employee) {} }
```

### Heuristic

If you describe a class and use "and" — it probably has multiple responsibilities.

---

## O — Open/Closed Principle (OCP)

> "Software entities should be open for extension, closed for modification."

Add new behavior by adding new code, not changing existing code.

### Violation

```typescript
function calculateArea(shape: Shape) {
  if (shape.type === 'circle') return Math.PI * shape.radius ** 2
  if (shape.type === 'rectangle') return shape.width * shape.height
  // Every new shape = modify this function
}
```

### Fix

Use polymorphism:

```typescript
interface Shape { area(): number }

class Circle implements Shape {
  constructor(private radius: number) {}
  area() { return Math.PI * this.radius ** 2 }
}

class Rectangle implements Shape {
  constructor(private width: number, private height: number) {}
  area() { return this.width * this.height }
}
```

New shapes extend the system without modifying `calculateArea`.

### Heuristic

If adding a feature requires modifying a switch/case or if-else chain, consider OCP.

---

## L — Liskov Substitution Principle (LSP)

> "Subtypes must be substitutable for their base types."

If `S` extends `T`, anywhere you use `T` you should be able to use `S` without surprises.

### Classic Violation: Square/Rectangle

```typescript
class Rectangle {
  setWidth(w: number)  { this.width = w }
  setHeight(h: number) { this.height = h }
}

class Square extends Rectangle {
  setWidth(w: number)  { this.width = w; this.height = w }
  setHeight(h: number) { this.width = h; this.height = h }
}

// Breaks expectations:
function resize(r: Rectangle) {
  r.setWidth(5)
  r.setHeight(10)
  assert(r.area() === 50) // Fails for Square!
}
```

### Fix

Don't model Square as a subtype of Rectangle. Use composition or separate types.

### Heuristic

If a subclass overrides a method to do something the caller wouldn't expect, it violates LSP.

---

## I — Interface Segregation Principle (ISP)

> "Clients should not be forced to depend on methods they don't use."

### Violation

```typescript
interface Worker {
  work(): void
  eat(): void
  sleep(): void
}

// A Robot worker doesn't eat or sleep
class Robot implements Worker {
  work() { /* ... */ }
  eat()  { throw new Error('Robots do not eat') }
  sleep() { throw new Error('Robots do not sleep') }
}
```

### Fix

Split into focused interfaces:

```typescript
interface Workable { work(): void }
interface Feedable { eat(): void }
interface Restable { sleep(): void }

class Human implements Workable, Feedable, Restable { /* ... */ }
class Robot implements Workable { /* ... */ }
```

### Heuristic

If implementing an interface forces you to write empty methods or throw "not supported", the interface is too fat.

---

## D — Dependency Inversion Principle (DIP)

> "Depend on abstractions, not concretions."

High-level modules (policy) must not depend on low-level modules (details). Both should depend on abstractions.

### Violation

```typescript
class OrderService {
  private db = new PostgresDatabase() // Concrete dependency

  createOrder(order: Order) {
    this.db.insert('orders', order)
  }
}
```

### Fix

Depend on an abstraction; inject the implementation:

```typescript
interface OrderRepository {
  save(order: Order): Promise<void>
}

class OrderService {
  constructor(private repository: OrderRepository) {}

  createOrder(order: Order) {
    this.repository.save(order)
  }
}

// Inject at composition root:
const service = new OrderService(new PostgresOrderRepository())
```

### Heuristic

If a class instantiates its own dependencies with `new`, it's likely violating DIP. Inject dependencies through the constructor.

---

## Applying SOLID Together

These principles reinforce each other:

- SRP keeps classes focused → easier to apply OCP
- OCP uses polymorphism → requires LSP-compliant subtypes
- ISP keeps interfaces thin → makes DIP practical
- DIP enables testing → which validates LSP

Don't apply them dogmatically. They're tools for managing complexity. A simple script doesn't need SOLID. A growing system does.
