# Code Analysis Best Practices

## Analysis Workflow

### 1. Initial Discovery
Always start with understanding the big picture:
- Map directory structure
- Identify main languages
- Find entry points
- Note configuration files

### 2. Architecture Analysis
Understand how the code is organized:
- Module boundaries
- Layer separation (MVC, Clean Architecture, etc.)
- Service dependencies
- Data flow

### 3. Code Quality Analysis
Look for code quality indicators:
- Code duplication
- Complexity hotspots
- Test coverage
- Documentation quality

### 4. Security Analysis
Identify potential security issues:
- Input validation
- Authentication/authorization
- Data exposure
- Dependency vulnerabilities

## Language-Specific Patterns

### Python
- Check for `__init__.py` organization
- Look for virtual environment files
- Identify async/await patterns
- Note type hints usage

### JavaScript/TypeScript
- Check for `package.json` scripts
- Identify framework patterns (React, Vue, etc.)
- Look for build configuration
- Note module system (CommonJS vs ES6)

### Java
- Check for Maven/Gradle structure
- Identify Spring patterns
- Look for package organization
- Note design patterns used

### Go
- Check for `go.mod` dependencies
- Identify package structure
- Look for interface usage
- Note error handling patterns

### Rust
- Check for `Cargo.toml` configuration
- Identify module structure
- Look for unsafe blocks
- Note lifetime annotations

## Common Code Smells

1. **God Objects** - Classes with too many responsibilities
2. **Long Functions** - Functions exceeding 50 lines
3. **Deep Nesting** - Excessive conditional nesting
4. **Duplicate Code** - Copy-pasted logic
5. **Magic Numbers** - Unnamed numeric constants
6. **Feature Envy** - Methods that use another class's data more than their own

## Analysis Checklist

- [ ] Directory structure is clear
- [ ] Entry points are identifiable
- [ ] Dependencies are documented
- [ ] Tests exist and pass
- [ ] No obvious security issues
- [ ] Code follows style guidelines
- [ ] Documentation is adequate
- [ ] No deprecated dependencies

## Output Guidelines

When generating analysis reports:

1. **Start with summary** - High-level findings first
2. **Use concrete examples** - Reference specific files/lines
3. **Prioritize issues** - Critical > High > Medium > Low
4. **Provide recommendations** - Always suggest fixes
5. **Include metrics** - Quantify where possible

## Tools Integration

The analyzer works well with:
- `find` - For file discovery
- `grep` - For pattern searching
- `wc` - For line counting
- `tree` - For structure visualization
- Language-specific linters
