# Python Development Standards

## Code Style (PEP 8)
- Use **snake_case** for variables, functions, and methods.
- Use **PascalCase** for classes.
- Use **UPPER_CASE** for constants.
- Indent using **4 spaces**.
- Maximum line length: **88 characters** (Black standard) or 79 (PEP 8 strict).

## Structure
- Use `src/` for source code.
- Use `tests/` for unit tests (pytest recommended).
- Include `pyproject.toml` for modern packaging.
- Use `if __name__ == "__main__":` for scripts.

## Tools
- **Formatter**: `black` or `ruff`.
- **Linter**: `pylint` or `ruff`.
- **Type Checking**: `mypy` (strict mode).
