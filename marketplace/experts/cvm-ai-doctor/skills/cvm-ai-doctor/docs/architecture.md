# Architecture & Design

**Purpose**: Technical architecture documentation for developers and maintainers.  
**Audience**: Skill developers, not AI agents.

---

## Overview

standalone-checks is a diagnostic skill with a **modular Quick/Deep architecture** designed for efficient triage and analysis.

---

## Design Principles

### 1. Two-Stage Diagnosis

```
Quick Mode (10s)
  ↓
Conditional Loading
  ↓
Deep Mode (20-60s)
```

**Benefits**:
- Fast triage for common cases
- Detailed analysis only when needed
- Reduced context loading for AI agents

### 2. Modular References

**Before (Monolithic)**:
```
resource-saturation.md (6,000 words)
  - Quick checks (600 words)
  - Deep CPU (600 words)
  - Deep Memory (600 words)
  - Deep Disk (600 words)
  - Deep Network (600 words)
```

Problem: Always loads full file even if only need Quick

**After (Modular)**:
```
resource-saturation-quick.md (600 words)
resource-saturation-deep-cpu.md (600 words)
resource-saturation-deep-memory.md (600 words)
resource-saturation-deep-disk.md (600 words)
resource-saturation-deep-network.md (600 words)
```

Benefit: Load only what's needed

### 3. Conditional Loading Logic

```python
# Step 1: Quick triage
quick_results = load_and_execute("resource-saturation-quick.md")

# Step 2: Conditional Deep loading
if quick_results["cpu"] == "CRITICAL":
    load_and_execute("resource-saturation-deep-cpu.md")
    
if quick_results["memory"] == "WARNING":
    load_and_execute("resource-saturation-deep-memory.md")
    
# Only 1-2 Deep files loaded vs. loading full 6,000-word file
```

---

## File Organization

### Structure

```
skills/standalone-checks/
├── SKILL.md                    # Core usage guide (300 lines)
├── docs/
│   ├── architecture.md         # This file
│   ├── scenario-decision-guide.md  # Extended scenarios
│   └── implementation-notes.md # Developer notes
├── references/
│   ├── 00-scenario-index.md    # Fallback scenario library
│   ├── *-quick.md              # Quick modules (4 files)
│   ├── *-deep-*.md             # Deep modules (15 files)
│   └── time-sync.md            # Special case (Quick+Deep in one)
└── commands/
    └── */                      # 126 action commands
```

### File Types

**SKILL.md** (Core)
- Purpose: AI agent usage guide
- Length: ~300 lines
- Content: When to use, how to use, core scenarios
- Audience: AI agents

**docs/** (Extended)
- Purpose: Technical documentation
- Length: Varies
- Content: Architecture, extended scenarios, dev notes
- Audience: Developers, advanced users

**references/** (Diagnostic)
- Purpose: Diagnostic procedures
- Length: 300-1,000 words per file
- Content: Commands, analysis patterns, examples
- Audience: AI agents (loaded on-demand)

**commands/** (Actions)
- Purpose: Executable actions
- Length: Short command specs
- Content: Specific fix/check commands
- Audience: AI agents (fallback)

---

## Module Design

### Quick Modules

**Characteristics**:
- Execution time: 10 seconds
- Commands: 5-10 lightweight commands
- Output: Status codes (OK/WARNING/CRITICAL) per component
- Purpose: Fast triage, identify problem areas

**Example: resource-saturation-quick.md**
```bash
# CPU check (3s)
top -bn1 | head -5

# Memory check (2s)
free -h

# Disk check (3s)
df -h
iostat -x 1 2

# Network check (2s)
netstat -s | grep -i error
```

Output format:
```yaml
cpu: CRITICAL (95%)
memory: OK (40%)
disk: OK (I/O normal)
network: OK (no errors)
```

### Deep Modules

**Characteristics**:
- Execution time: 20-60 seconds
- Commands: 10-30 detailed commands
- Output: Root cause analysis + recommendations
- Purpose: Diagnose specific component issues

**Example: resource-saturation-deep-cpu.md**
```bash
# Process analysis (10s)
ps aux --sort=-%cpu | head -20

# Thread analysis (10s)
top -Hp <pid>

# System call analysis (20s)
strace -c -p <pid>

# CPU scheduling (10s)
vmstat 1 5

# Historical data (10s)
sar -u 1 10
```

Output format:
```yaml
root_cause: "Process java (PID 1234) consuming 90% CPU"
duration: "> 2 hours"
analysis: "Thread pool exhausted, tight loop detected"
recommendations:
  - "Check application logs"
  - "Analyze thread dump: jstack 1234"
  - "Consider scaling up"
```

---

## Decision Architecture

### Three-Tier System

```
Tier 1: SKILL.md (80% coverage)
  ↓ If no match
Tier 2: docs/scenario-decision-guide.md (95% coverage)
  ↓ If no match
Tier 3: references/00-scenario-index.md (99% coverage)
```

**Tier 1 - Core Scenarios**:
- 10-15 built-in scenarios in SKILL.md
- Covers most common cases
- AI always has this in context

**Tier 2 - Extended Scenarios**:
- 60+ scenarios in separate doc
- Load only if Tier 1 doesn't match
- Detailed workflows and keywords

**Tier 3 - Fallback**:
- Complete scenario library + command mappings
- Last resort before giving up
- Includes rare/edge cases

### Why Three Tiers?

**Problem**: Cannot put all 60+ scenarios in SKILL.md
- Too long (1,000+ lines)
- AI context pollution
- Slow to parse

**Solution**: Hierarchical loading
- Always load: SKILL.md (~300 lines)
- Conditionally load: Extended docs
- Fallback: Complete library

---

## Cross-Platform Support

### Approach

**Challenge**: Different commands on Linux/macOS/Windows

**Solution**: Platform adapters + conditional logic

```bash
# Example from references
OS=$(uname -s)

case $OS in
  Linux)
    # Use iostat
    iostat -x 1 2
    ;;
  Darwin)
    # macOS alternative
    vm_stat | grep Pages
    ;;
  MINGW*|MSYS*|CYGWIN*)
    # Windows (Git Bash)
    wmic cpu get loadpercentage
    ;;
esac
```

### Platform Coverage

- **Linux**: Full support (primary platform)
- **macOS**: Full support (via adapters)
- **Windows**: Basic support (Git Bash + PowerShell hybrid)

---

## Performance Optimization

### Context Efficiency

**Before modularization**:
```
User: "Check health"
AI loads: 11,000 words (4 full reference files)
AI needs: 1,200 words (only Quick sections)
Waste: 89%
```

**After modularization**:
```
User: "Check health"
AI loads: 1,200 words (2 Quick modules)
AI needs: 1,200 words
Waste: 0%
```

### Scenarios

| Scenario | Before | After | Efficiency Gain |
|----------|--------|-------|----------------|
| Health check (all OK) | 11,000 words | 1,200 words | 89% |
| Single issue (CPU) | 6,000 words | 1,200 words | 80% |
| Multiple issues (2) | 11,000 words | 2,400 words | 78% |
| Complex (4 issues) | 11,000 words | 3,600 words | 67% |

---

## Maintenance Guidelines

### Adding New Scenarios

1. **Determine frequency**
   - High frequency → Add to SKILL.md
   - Medium frequency → Add to scenario-decision-guide.md
   - Low frequency → Add to 00-scenario-index.md

2. **Keep SKILL.md lean**
   - Core scenarios only (10-15)
   - Each scenario: 3-5 lines max
   - Focus on decision logic

3. **Extended docs for details**
   - Put workflows in scenario-decision-guide.md
   - Put examples in reference files
   - Put commands in commands/

### Adding New Modules

**When to add Quick module**:
- New diagnostic domain (e.g., GPU monitoring)
- 10s execution target
- Returns status codes

**When to add Deep module**:
- Existing Quick identifies issues in new area
- 20-60s execution target
- Provides root cause analysis

**When NOT to modularize**:
- File < 2,000 words
- No clear Quick/Deep separation
- Single-purpose check (e.g., time-sync.md)

---

## Design Decisions

### Why not put all scenarios in SKILL.md?

**Pros of putting everything in SKILL.md**:
- Single source of truth
- No external dependencies

**Cons**:
- AI context bloat (1,000+ lines)
- Slow to parse
- Violates single responsibility
- Hard to maintain

**Decision**: Hierarchical loading wins

### Why separate Quick/Deep files?

**Alternative**: Keep Quick/Deep in same file, use offset/limit

**Pros of separation**:
- Clear module boundaries
- Easier to maintain
- Explicit conditional loading
- Better file organization

**Cons of separation**:
- More files (19 vs 4)
- Slightly more complex navigation

**Decision**: Separation wins (clarity > file count)

### Why keep time-sync.md unsplit?

**Reason**: File only 1,800 words
- Already small enough
- Quick/Deep clearly separated in sections
- Splitting would add overhead with little gain
- Can use offset/limit if needed

---

## Future Improvements

### Potential Enhancements

1. **GPU monitoring module**
   - Quick: nvidia-smi basic check
   - Deep: GPU memory, utilization, temperature

2. **Container-specific checks**
   - Quick: docker stats summary
   - Deep: Container resource limits, OOM analysis

3. **Database-specific diagnostics**
   - Quick: Connection pool, query latency
   - Deep: Slow query analysis, lock contention

### Backward Compatibility

- Keep index files for 1-2 releases
- Deprecation warnings in old files
- Migration guide in CHANGELOG

---

**Last Updated**: 2026-03-24  
**Maintainer**: AI diagnostics team  
**Version**: 2.2 (Modular architecture)
