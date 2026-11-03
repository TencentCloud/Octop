---
name: workout
description: Track workouts, log sets, manage exercises and templates with workout-cli. Supports multi-user profiles. Use when helping users record gym sessions, view history, or analyze strength progression.
metadata: {"clawdbot":{"emoji":"🏋️","requires":{"bins":["workout"]}}}
---

# Workout CLI

## Multi-User Profiles

Multiple people can track workouts independently using profiles.

```bash
workout profile list               # List all profiles
workout profile create sarah       # Create new profile
workout profile delete old         # Delete profile
```

When multiple profiles exist, specify which one:
```bash
workout --profile mike start push-day
workout --profile mike log bench-press 185 8
workout --profile mike done
```

- **Single profile**: Commands work without `--profile` (backwards compatible)
- **Shared exercises**: Exercise library shared across profiles
- **Per-user data**: Templates, workouts, config are per-profile

## CRITICAL RULES

### 1. Always Add New Exercises First
If user mentions an exercise not in library, **add it before logging**:
```bash
workout exercises add "Dumbbell RDL" --muscles hamstrings,glutes --type compound --equipment dumbbell
```
Never skip this — unknown exercises will fail to log.

### 2. Log Accurate Numbers — Notes Are NOT a Substitute
Sets require **correct weight and reps**. Numbers feed statistical analysis (PRs, volume, progression).
- ❌ WRONG: Log 0 lbs then add a note with the real weight
- ✅ RIGHT: Log the actual weight used

If user doesn't specify weight, **ASK** before logging. Don't assume 0.

### 3. Notes Are Metadata Only
Use notes for context (injuries, form cues, equipment notes), not to correct bad data:
```bash
workout note "Left elbow tender today"
workout note bench-press "Used close grip"
```

## Core Commands
```bash
workout start --empty              # Start freestyle session
workout start push                 # Start from template
workout log bench-press 135 8      # Log set (weight reps)
workout log bench-press 135 8,8,7  # Log multiple sets
workout note "Session note"        # Add note
workout note bench-press "Note"    # Note on exercise
workout swap bench-press db-bench  # Swap exercise
workout done                       # Finish session
workout cancel                     # Discard
```

## Editing & Fixing Logged Sets
```bash
workout undo                       # Remove last logged set
workout undo bench-press           # Remove last set of specific exercise
workout edit bench-press 2 155 8   # Edit set 2: weight=155, reps=8
workout edit bench-press 2 --reps 10 --rir 2  # Edit reps and RIR
workout delete bench-press 3       # Delete set 3 entirely
```
Set numbers are 1-indexed. Use these to fix mistakes during a session.

## Exercises
```bash
workout exercises list
workout exercises list --muscle chest
workout exercises add "Name" --muscles biceps --type isolation --equipment cable
```
⚠️ `exercises add` requires: `--muscles`, `--type`, `--equipment`

Equipment options: barbell, dumbbell, cable, machine, bodyweight, kettlebell, band, other

## Templates
```bash
workout templates list
workout templates show push
workout templates create "Push" --exercises "bench-press:4x8,ohp:3x8"
```

## History & PRs
```bash
workout last                       # Last workout
workout history bench-press        # Exercise history
workout pr                         # All PRs
workout pr bench-press             # Exercise PRs
workout volume --week              # Weekly volume
workout progression bench-press    # Progress over time
```

## Typical Session Flow
```bash
# 1. Start
workout start push

# 2. Log with REAL numbers
workout log bench-press 135 8
workout log bench-press 145 8
workout log bench-press 155 6

# 3. Notes for context only
workout note bench-press "Felt strong today"

# 4. Finish
workout done
```

## Equipment Variants
Use specific exercises for equipment variants to track properly:
- `bench-press` (barbell) vs `dumbbell-bench-press`
- `romanian-deadlift` (barbell) vs `dumbbell-rdl`
- `shoulder-press` (barbell) vs `dumbbell-shoulder-press`

## Notes
- Weights in **lbs**
- Multiple `log` calls at different weights OK
- `swap` moves all logged sets to new exercise
- All commands support `--json`
