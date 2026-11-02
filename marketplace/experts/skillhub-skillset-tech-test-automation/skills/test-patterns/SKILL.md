---
name: test-patterns
description: Write and run tests across languages and frameworks. Use when setting up test suites, writing unit/integration/E2E tests, measuring coverage, mocking dependencies, or debugging test failures. Covers Node.js (Jest/Vitest), Python (pytest), Go, Rust, and Bash.
metadata: {"clawdbot":{"emoji":"🧪","requires":{"anyBins":["node","python3","go","cargo","bash"]},"os":["linux","darwin","win32"]}}
---

# Test Patterns

Write, run, and debug tests across languages. Covers unit tests, integration tests, E2E tests, mocking, coverage, and TDD workflows.

## When to Use

- Setting up a test suite for a new project
- Writing unit tests for functions or modules
- Writing integration tests for APIs or database interactions
- Setting up code coverage measurement
- Mocking external dependencies (APIs, databases, file system)
- Debugging flaky or failing tests
- Implementing test-driven development (TDD)

## Node.js (Jest / Vitest)

### Setup

```bash
# Jest
npm install -D jest
# Add to package.json: "scripts": { "test": "jest" }

# Vitest (faster, ESM-native)
npm install -D vitest
# Add to package.json: "scripts": { "test": "vitest" }
```

### Unit Tests

```javascript
// math.js
export function add(a, b) { return a + b; }
export function divide(a, b) {
  if (b === 0) throw new Error('Division by zero');
  return a / b;
}

// math.test.js
import { add, divide } from './math.js';

describe('add', () => {
  test('adds two positive numbers', () => {
    expect(add(2, 3)).toBe(5);
  });

  test('handles negative numbers', () => {
    expect(add(-1, 1)).toBe(0);
  });

  test('handles zero', () => {
    expect(add(0, 0)).toBe(0);
  });
});

describe('divide', () => {
  test('divides two numbers', () => {
    expect(divide(10, 2)).toBe(5);
  });

  test('throws on division by zero', () => {
    expect(() => divide(10, 0)).toThrow('Division by zero');
  });

  test('handles floating point', () => {
    expect(divide(1, 3)).toBeCloseTo(0.333, 3);
  });
});
```

### Async Tests

```javascript
// api.test.js
import { fetchUser } from './api.js';

test('fetches user by id', async () => {
  const user = await fetchUser('123');
  expect(user).toHaveProperty('id', '123');
  expect(user).toHaveProperty('name');
  expect(user.name).toBeTruthy();
});

test('throws on missing user', async () => {
  await expect(fetchUser('nonexistent')).rejects.toThrow('Not found');
});
```

### Mocking

```javascript
// Mock a module
jest.mock('./database.js');
import { getUser } from './database.js';
import { processUser } from './service.js';

test('processes user from database', async () => {
  // Setup mock return value
  getUser.mockResolvedValue({ id: '1', name: 'Alice', active: true });

  const result = await processUser('1');
  expect(result.processed).toBe(true);
  expect(getUser).toHaveBeenCalledWith('1');
  expect(getUser).toHaveBeenCalledTimes(1);
});

// Mock fetch
global.fetch = jest.fn();

test('calls API with correct params', async () => {
  fetch.mockResolvedValue({
    ok: true,
    json: async () => ({ data: 'test' }),
  });

  const result = await myApiCall('/endpoint');
  expect(fetch).toHaveBeenCalledWith('/endpoint', expect.objectContaining({
    method: 'GET',
  }));
});

// Spy on existing method (don't replace, just observe)
const consoleSpy = jest.spyOn(console, 'log').mockImplementation();
// ... run code ...
expect(consoleSpy).toHaveBeenCalledWith('expected message');
consoleSpy.mockRestore();
```

### Coverage

```bash
# Jest
npx jest --coverage

# Vitest
npx vitest --coverage

# Check coverage thresholds (jest.config.js)
# coverageThreshold: { global: { branches: 80, functions: 80, lines: 80, statements: 80 } }
```

## Python (pytest)

### Setup

```bash
pip install pytest pytest-cov
```

### Unit Tests

```python
# calculator.py
def add(a, b):
    return a + b

def divide(a, b):
    if b == 0:
        raise ValueError("Division by zero")
    return a / b

# test_calculator.py
import pytest
from calculator import add, divide

def test_add():
    assert add(2, 3) == 5

def test_add_negative():
    assert add(-1, 1) == 0

def test_divide():
    assert divide(10, 2) == 5.0

def test_divide_by_zero():
    with pytest.raises(ValueError, match="Division by zero"):
        divide(10, 0)

def test_divide_float():
    assert divide(1, 3) == pytest.approx(0.333, abs=0.001)
```

### Parametrized Tests

```python
@pytest.mark.parametrize("a,b,expected", [
    (2, 3, 5),
    (-1, 1, 0),
    (0, 0, 0),
    (100, -50, 50),
])
def test_add_cases(a, b, expected):
    assert add(a, b) == expected
```

### Fixtures

```python
import pytest
import json
import tempfile
import os

@pytest.fixture
def sample_users():
    """Provide test user data."""
    return [
        {"id": 1, "name": "Alice", "email": "alice@test.com"},
        {"id": 2, "name": "Bob", "email": "bob@test.com"},
    ]

@pytest.fixture
def temp_db(tmp_path):
    """Provide a temporary SQLite database."""
    import sqlite3
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, email TEXT)")
    conn.commit()
    yield conn
    conn.close()

def test_insert_users(temp_db, sample_users):
    for user in sample_users:
        temp_db.execute("INSERT INTO users VALUES (?, ?, ?)",
                       (user["id"], user["name"], user["email"]))
    temp_db.commit()
    count = temp_db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    assert count == 2

# Fixture with cleanup
@pytest.fixture
def temp_config_file():
    path = tempfile.mktemp(suffix=".json")
    with open(path, "w") as f:
        json.dump({"key": "value"}, f)
    yield path
    os.unlink(path)
```

### Mocking

```python
from unittest.mock import patch, MagicMock, AsyncMock

# Mock a function
@patch('mymodule.requests.get')
def test_fetch_data(mock_get):
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {"data": "test"}

    result = fetch_data("https://api.example.com")
    assert result == {"data": "test"}
    mock_get.assert_called_once_with("https://api.example.com")

# Mock async
@patch('mymodule.aiohttp.ClientSession.get', new_callable=AsyncMock)
async def test_async_fetch(mock_get):
    mock_get.return_value.__aenter__.return_value.json = AsyncMock(return_value={"ok": True})
    result = await async_fetch("/endpoint")
    assert result["ok"] is True

# Context manager mock
def test_file_reader():
    with patch("builtins.open", MagicMock(return_value=MagicMock(
        read=MagicMock(return_value='{"key": "val"}'),
        __enter__=MagicMock(return_value=MagicMock(read=MagicMock(return_value='{"key": "val"}'))),
        __exit__=MagicMock(return_value=False),
    ))):
        result = read_config("fake.json")
        assert result["key"] == "val"
```

### Coverage

```bash
# Run with coverage
pytest --cov=mypackage --cov-report=term-missing

# HTML report
pytest --cov=mypackage --cov-report=html
# Open htmlcov/index.html

# Fail if coverage below threshold
pytest --cov=mypackage --cov-fail-under=80
```

## Go

### Unit Tests

```go
// math.go
package math

import "errors"

func Add(a, b int) int { return a + b }

func Divide(a, b float64) (float64, error) {
    if b == 0 {
        return 0, errors.New("division by zero")
    }
    return a / b, nil
}

// math_test.go
package math

import (
    "testing"
    "math"
)

func TestAdd(t *testing.T) {
    tests := []struct {
        name     string
        a, b     int
        expected int
    }{
        {"positive", 2, 3, 5},
        {"negative", -1, 1, 0},
        {"zeros", 0, 0, 0},
    }
    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            got := Add(tt.a, tt.b)
            if got != tt.expected {
                t.Errorf("Add(%d, %d) = %d, want %d", tt.a, tt.b, got, tt.expected)
            }
        })
    }
}

func TestDivide(t *testing.T) {
    result, err := Divide(10, 2)
    if err != nil {
        t.Fatalf("unexpected error: %v", err)
    }
    if math.Abs(result-5.0) > 0.001 {
        t.Errorf("Divide(10, 2) = %f, want 5.0", result)
    }
}

func TestDivideByZero(t *testing.T) {
    _, err := Divide(10, 0)
    if err == nil {
        t.Error("expected error for division by zero")
    }
}
```

### Run Tests

```bash
# All tests
go test ./...

# Verbose
go test -v ./...

# Specific package
go test ./pkg/math/

# With coverage
go test -cover ./...
go test -coverprofile=coverage.out ./...
go tool cover -html=coverage.out

# Run specific test
go test -run TestAdd ./...

# Race condition detection
go test -race ./...

# Benchmark
go test -bench=. ./...
```

## Rust

### Unit Tests

```rust
// src/math.rs
pub fn add(a: i64, b: i64) -> i64 { a + b }

pub fn divide(a: f64, b: f64) -> Result<f64, String> {
    if b == 0.0 { return Err("division by zero".into()); }
    Ok(a / b)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_add() {
        assert_eq!(add(2, 3), 5);
        assert_eq!(add(-1, 1), 0);
    }

    #[test]
    fn test_divide() {
        let result = divide(10.0, 2.0).unwrap();
        assert!((result - 5.0).abs() < f64::EPSILON);
    }

    #[test]
    fn test_divide_by_zero() {
        assert!(divide(10.0, 0.0).is_err());
    }

    #[test]
    #[should_panic(expected = "overflow")]
    fn test_overflow_panics() {
        let _ = add(i64::MAX, 1); // Will panic on overflow in debug
    }
}
```

```bash
cargo test
cargo test -- --nocapture  # Show println output
cargo test test_add        # Run specific test
cargo tarpaulin            # Coverage (install: cargo install cargo-tarpaulin)
```

## Bash Tests

### Simple Test Runner

```bash
#!/bin/bash
# test.sh - Minimal bash test framework
PASS=0 FAIL=0

assert_eq() {
  local actual="$1" expected="$2" label="$3"
  if [ "$actual" = "$expected" ]; then
    echo "  PASS: $label"
    ((PASS++))
  else
    echo "  FAIL: $label (got '$actual', expected '$expected')"
    ((FAIL++))
  fi
}

assert_exit_code() {
  local cmd="$1" expected="$2" label="$3"
  eval "$cmd" >/dev/null 2>&1
  assert_eq "$?" "$expected" "$label"
}

assert_contains() {
  local actual="$1" substring="$2" label="$3"
  if echo "$actual" | grep -q "$substring"; then
    echo "  PASS: $label"
    ((PASS++))
  else
    echo "  FAIL: $label ('$actual' does not contain '$substring')"
    ((FAIL++))
  fi
}

# --- Tests ---
echo "Running tests..."

# Test your scripts
output=$(./my-script.sh --help 2>&1)
assert_exit_code "./my-script.sh --help" "0" "help flag exits 0"
assert_contains "$output" "Usage" "help shows usage"

output=$(./my-script.sh --invalid 2>&1)
assert_exit_code "./my-script.sh --invalid" "1" "invalid flag exits 1"

# Test command outputs
assert_eq "$(echo 'hello' | wc -c | tr -d ' ')" "6" "echo hello is 6 bytes"

echo ""
echo "Results: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
```

## Integration Testing Patterns

### API Integration Test (any language)

```bash
#!/bin/bash
# test-api.sh - Start server, run tests, tear down
SERVER_PID=""
cleanup() { [ -n "$SERVER_PID" ] && kill "$SERVER_PID" 2>/dev/null; }
trap cleanup EXIT

# Start server in background
npm start &
SERVER_PID=$!
sleep 2  # Wait for server

# Run tests against live server
BASE_URL=http://localhost:3000 npx jest --testPathPattern=integration
EXIT_CODE=$?

exit $EXIT_CODE
```

### Database Integration Test (Python)

```python
import pytest
import sqlite3

@pytest.fixture
def db():
    """Fresh database for each test."""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT, price REAL)")
    yield conn
    conn.close()

def test_insert_and_query(db):
    db.execute("INSERT INTO items (name, price) VALUES (?, ?)", ("Widget", 9.99))
    db.commit()
    row = db.execute("SELECT name, price FROM items WHERE name = ?", ("Widget",)).fetchone()
    assert row == ("Widget", 9.99)

def test_empty_table(db):
    count = db.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    assert count == 0
```

## TDD Workflow

The red-green-refactor cycle:

1. **Red**: Write a failing test for the next piece of behavior
2. **Green**: Write the minimum code to make it pass
3. **Refactor**: Clean up without changing behavior (tests stay green)

```bash
# Tight feedback loop
# Jest watch mode
npx jest --watch

# Vitest watch (default)
npx vitest

# pytest watch (with pytest-watch)
pip install pytest-watch
ptw

# Go (with air or entr)
ls *.go | entr -c go test ./...
```

## Debugging Failed Tests

### Common Issues

**Test passes alone, fails in suite** → shared state. Check for:
- Global variables modified between tests
- Database not cleaned up
- Mocks not restored (`afterEach` / `teardown`)

**Test fails intermittently (flaky)** → timing or ordering issue:
- Async operations without proper `await`
- Tests depending on execution order
- Time-dependent logic (use clock mocking)
- Network calls in unit tests (should be mocked)

**Coverage shows uncovered branches** → missing edge cases:
- Error paths (what if the API returns 500?)
- Empty inputs (empty string, null, empty array)
- Boundary values (0, -1, MAX_INT)

### Run Single Test

```bash
# Jest
npx jest -t "test name substring"

# pytest
pytest -k "test_divide_by_zero"

# Go
go test -run TestDivideByZero ./...

# Rust
cargo test test_divide
```

## Tips

- Test behavior, not implementation. Tests should survive refactors.
- One assertion per concept (not necessarily one `assert` per test, but one logical check).
- Name tests descriptively: `test_returns_empty_list_when_no_users_exist` beats `test_get_users_2`.
- Don't mock what you don't own — write thin wrappers around external libraries, mock the wrapper.
- Integration tests catch bugs unit tests miss. Don't skip them.
- Use `tmp_path` (pytest), `t.TempDir()` (Go), or `tempfile` (Node) for file-based tests.
- Snapshot tests are great for detecting unintended changes, bad for evolving formats.
