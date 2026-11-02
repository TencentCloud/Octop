# Clean Architecture — Detailed Guide

## The Core Idea

Separate the software into layers. Each layer has a specific role. Dependencies point inward.

```
┌──────────────────────────────────────────┐
│         Frameworks & Drivers             │  ← DB, Web, UI, devices
│  ┌────────────────────────────────────┐  │
│  │       Interface Adapters           │  │  ← Controllers, Gateways, Presenters
│  │  ┌──────────────────────────────┐  │  │
│  │  │        Use Cases             │  │  │  ← Application business rules
│  │  │  ┌────────────────────────┐  │  │  │
│  │  │  │      Entities          │  │  │  │  ← Enterprise business rules
│  │  │  └────────────────────────┘  │  │  │
│  │  └──────────────────────────────┘  │  │
│  └────────────────────────────────────┘  │
└──────────────────────────────────────────┘
```

## The Dependency Rule

Source code dependencies must only point **inward**. Nothing in an inner ring can know anything about an outer ring. This includes functions, classes, variables, types, or any named entity.

## Layer Details

### Entities (Innermost)

- Encapsulate enterprise-wide business rules.
- Could be used by many applications in the enterprise.
- Least likely to change when something external changes.
- Pure domain objects with business logic. No framework dependencies.

```typescript
// Pure entity — no imports from outer layers
class Account {
  constructor(
    readonly id: string,
    private balance: number,
  ) {}

  deposit(amount: number) {
    if (amount <= 0) throw new DomainError('Amount must be positive')
    this.balance += amount
  }

  withdraw(amount: number) {
    if (amount > this.balance) throw new InsufficientFundsError()
    this.balance -= amount
  }

  getBalance() { return this.balance }
}
```

### Use Cases

- Application-specific business rules.
- Orchestrate the flow of data to and from entities.
- Direct entities to use their enterprise-wide business rules.
- Changes to this layer should not affect entities.
- Changes to external layers (DB, UI) should not affect use cases.

```typescript
// Use case — depends on entities and port interfaces, nothing else
class TransferFundsUseCase {
  constructor(
    private accountRepo: AccountRepository,  // Port (interface)
    private notifier: TransferNotifier,       // Port (interface)
  ) {}

  async execute(fromId: string, toId: string, amount: number) {
    const from = await this.accountRepo.findById(fromId)
    const to = await this.accountRepo.findById(toId)

    from.withdraw(amount)
    to.deposit(amount)

    await this.accountRepo.save(from)
    await this.accountRepo.save(to)
    await this.notifier.notify(fromId, toId, amount)
  }
}
```

### Interface Adapters

- Convert data between the format most convenient for use cases/entities and the format most convenient for external things (DB, web).
- Controllers, presenters, gateways live here.
- No business logic — only translation.

```typescript
// Controller (adapter) — converts HTTP to use case input
class TransferController {
  constructor(private useCase: TransferFundsUseCase) {}

  async handle(req: HttpRequest): Promise<HttpResponse> {
    const { fromId, toId, amount } = req.body
    await this.useCase.execute(fromId, toId, amount)
    return { status: 200, body: { success: true } }
  }
}

// Repository implementation (adapter) — converts use case port to DB
class PostgresAccountRepository implements AccountRepository {
  async findById(id: string): Promise<Account> {
    const row = await this.db.query('SELECT * FROM accounts WHERE id = $1', [id])
    return new Account(row.id, row.balance)
  }

  async save(account: Account): Promise<void> {
    await this.db.query('UPDATE accounts SET balance = $1 WHERE id = $2',
      [account.getBalance(), account.id])
  }
}
```

### Frameworks & Drivers (Outermost)

- Glue code. Minimal.
- Web framework config, database drivers, HTTP server setup.
- This is where all the details go. Keep them out of the inner circles.

## Ports and Adapters (Hexagonal Architecture)

Clean Architecture is compatible with hexagonal architecture:

- **Ports**: interfaces defined by the use case layer (what it needs from the outside).
- **Adapters**: implementations in the outer layer that fulfill ports.

```typescript
// PORT — defined in use case layer
interface AccountRepository {
  findById(id: string): Promise<Account>
  save(account: Account): Promise<void>
}

// ADAPTER — defined in infrastructure layer
class DrizzleAccountRepository implements AccountRepository {
  // Implementation using Drizzle ORM
}
```

## Crossing Boundaries

When data crosses a boundary, it should be in the form most convenient for the **inner** circle. Never pass database rows or HTTP request objects into use cases.

Use simple DTOs or value objects:

```typescript
// Input DTO for use case
interface TransferInput {
  fromAccountId: string
  toAccountId: string
  amount: number
}

// Output DTO from use case
interface TransferResult {
  success: boolean
  newBalance: number
}
```

## The Composition Root

All dependency wiring happens at the outermost layer — the "main" or "composition root":

```typescript
// main.ts — the only place that knows about ALL concrete implementations
const db = new PostgresDatabase(config.dbUrl)
const accountRepo = new PostgresAccountRepository(db)
const notifier = new EmailTransferNotifier(config.smtp)
const transferUseCase = new TransferFundsUseCase(accountRepo, notifier)
const controller = new TransferController(transferUseCase)

app.post('/transfer', (req, res) => controller.handle(req, res))
```

## Testing Benefits

Each layer can be tested independently:

- **Entities**: pure unit tests, no mocks needed.
- **Use Cases**: mock the ports (repositories, services).
- **Adapters**: integration tests against real infrastructure.
- **End-to-end**: full stack through the composition root.

## Common Mistakes

- Letting entities import from frameworks (ORM decorators on domain objects).
- Putting business logic in controllers.
- Use cases that know about HTTP status codes or database queries.
- Skipping the adapter layer and having use cases talk directly to the DB.
- Over-engineering: not every project needs all four layers. Scale the architecture to the complexity.

## Pragmatic Application

- Start with two layers (domain + infrastructure) for small projects.
- Add use case and adapter layers as complexity grows.
- The dependency rule is the non-negotiable part. Everything else is negotiable.
- Frameworks are details. Design your system so switching a framework is possible (even if you never do).
