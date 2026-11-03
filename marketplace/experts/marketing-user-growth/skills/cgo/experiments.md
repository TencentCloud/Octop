# Experimentation Frameworks

## Hypothesis Structure

```
We believe [change]
will result in [outcome]
because [rationale]
measured by [metric]
success threshold [number]
```

## Experiment Types

### A/B Tests
- **Single variable** — Change one thing, measure impact
- **Sample size** — Calculate required users before starting
- **Duration** — Full business cycles, weekday/weekend coverage
- **Segmentation** — New vs returning, paid vs free, geography

### Multivariate Tests
- **Multiple variables** — Test combinations simultaneously
- **Higher traffic required** — Need volume for statistical power
- **Interaction effects** — Discover how changes combine

### Sequential Tests
- **Limited traffic** — Test ideas quickly with early stopping
- **Exploration** — Find promising directions before full tests
- **Bandit algorithms** — Optimize while learning

## Prioritization Framework

### ICE Score
- **Impact** — How big if it works? (1-10)
- **Confidence** — How sure are you? (1-10)
- **Ease** — How fast to implement? (1-10)
- **Score** — Average of three, rank by score

### RICE Score
- **Reach** — How many users affected per time period
- **Impact** — How much effect per user (0.25, 0.5, 1, 2, 3)
- **Confidence** — How sure (10%-100%)
- **Effort** — Person-weeks to implement
- **Score** — (Reach × Impact × Confidence) / Effort

## Statistical Rigor

### Before Launch
- Define primary metric
- Calculate sample size needed
- Set experiment duration
- Document hypothesis

### During Experiment
- No peeking with decisions
- Check for data quality issues
- Monitor for bugs/errors

### After Experiment
- Statistical significance check
- Practical significance check
- Segment analysis
- Document learnings

## Velocity Optimization

- **Test ideas, not perfection** — 80% solutions ship faster
- **Parallel experiments** — Multiple tests in different areas
- **Reusable infrastructure** — Feature flags, analytics, dashboards
- **Learning loops** — Failed tests still generate knowledge
