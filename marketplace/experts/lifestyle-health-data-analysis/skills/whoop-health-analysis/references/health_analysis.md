# Health Data Analysis Guide

Science-backed framework for interpreting Whoop metrics. Use this when the user asks about their health, trends, or wants insights from their data.

## HRV (Heart Rate Variability) - RMSSD in milliseconds

### What it means
HRV measures the variation in time between heartbeats. It reflects autonomic nervous system (ANS) balance — specifically parasympathetic (rest-and-digest) activity. Higher HRV = more adaptable, resilient nervous system.

### Normal ranges (RMSSD, wrist-based wearable)
| Age | Low | Normal | High |
|-----|-----|--------|------|
| 20-29 | <25ms | 25-105ms | >105ms |
| 30-39 | <20ms | 20-80ms | >80ms |
| 40-49 | <15ms | 15-60ms | >60ms |
| 50-59 | <12ms | 12-45ms | >45ms |
| 60+ | <10ms | 10-35ms | >35ms |

*Note: Wrist-based HRV (like Whoop) tends to read lower than chest strap. Individual baseline matters more than population norms.*

### Interpretation
- **Trend matters more than absolute value** — compare to personal 30-day rolling average
- **Declining HRV trend** (>10% below baseline for 3+ days): suggests accumulated stress, poor recovery, illness onset, or overtraining
- **Rising HRV trend**: improved fitness, better recovery, reduced stress
- **Acute drop**: poor sleep, alcohol, illness, intense training, emotional stress
- **Very low HRV** (<15ms consistently): consider medical consultation — linked to cardiovascular risk, chronic stress, autonomic dysfunction

### Key research findings
- Low HRV is associated with increased cardiovascular mortality (Harvard Health, PMC5624990)
- HRV reflects both physical AND psychological stress load
- 7-day rolling average provides more meaningful context than daily values
- Reduced RMSSD in athletes associated with fatigue and overtraining (Nature, 2025)

---

## Resting Heart Rate (RHR)

### Normal ranges
| Fitness level | RHR (bpm) |
|--------------|-----------|
| Athlete | 40-55 |
| Active adult | 55-65 |
| Average adult | 60-80 |
| Sedentary | 70-90 |
| Concerning | >90 |

### Interpretation
- **Trend matters**: RHR rising 3-5+ bpm above personal baseline for several days suggests accumulated fatigue, stress, illness, or dehydration
- **Acute spike**: alcohol, poor sleep, illness onset, overtraining
- **Decreasing RHR over weeks/months**: improving cardiovascular fitness
- **High RHR + Low HRV**: strong signal of poor recovery or health concern

---

## Sleep Analysis

### Optimal distribution (for 7-8h total sleep)
| Stage | % of total | Ideal duration (8h) | Function |
|-------|-----------|---------------------|----------|
| Deep (SWS) | 15-25% | 1.2-2.0h | Physical restoration, growth hormone, immune function, memory consolidation |
| REM | 20-25% | 1.6-2.0h | Emotional processing, learning, creativity, memory |
| Light | 50-60% | 4.0-4.8h | Transition stage, some memory processing |
| Awake | <10% | <0.8h | Normal brief awakenings |

### Key thresholds
- **Total sleep needed** (adults): 7-9 hours (CDC recommendation)
- **Sleep performance <70%**: consistently getting less sleep than body needs
- **Deep sleep <1h**: concerning — reduced physical recovery, weakened immunity
- **REM sleep <1.2h**: may affect emotional regulation, learning
- **Sleep efficiency <85%**: spending too much time awake in bed — possible sleep hygiene issues
- **High disturbance count** (>15/night): possible environment issues, sleep apnea, stress
- **Sleep consistency <70%**: irregular sleep schedule disrupts circadian rhythm

### Factors that reduce deep sleep
- Alcohol, caffeine (within 6h), late heavy meals, screen time, irregular schedule, aging

### Factors that increase deep sleep
- Exercise (not too close to bedtime), cool room temperature, consistent schedule, stress management

---

## Recovery Score (Whoop-specific, 0-100%)

### Zones
| Zone | Range | Meaning | Recommendation |
|------|-------|---------|---------------|
| Green | 67-100% | Well recovered | Ready for high strain |
| Yellow | 34-66% | Moderate recovery | Light to moderate activity |
| Red | 0-33% | Poor recovery | Rest, active recovery only |

### Components that drive recovery
1. HRV (primary driver)
2. Resting heart rate
3. Sleep performance
4. SpO2
5. Skin temperature

### Patterns to flag
- **3+ consecutive red days**: accumulated fatigue — recommend rest, check for illness
- **Yellow average over 2+ weeks**: chronic under-recovery — review sleep, stress, training load
- **Recovery drops on specific weekdays**: lifestyle pattern (e.g., alcohol on weekends, poor Monday sleep)

---

## Strain (0-21 scale)

### Ranges
| Level | Strain | Description |
|-------|--------|-------------|
| Light | 0-8 | Rest day, low activity |
| Moderate | 8-14 | Normal active day, light workout |
| High | 14-18 | Intense workout |
| Overreaching | 18-21 | Maximal effort, needs significant recovery |

### Strain vs Recovery balance
- **Strain consistently > Recovery capacity**: overtraining risk
- **Strain always < 8**: sedentary — may benefit from more activity
- **Optimal**: match strain to recovery — push on green days, rest on red days

---

## SpO2 (Blood Oxygen Saturation)

### Normal ranges
- **Normal**: 95-100%
- **Mild concern**: 92-95% (especially if persistent)
- **Concerning**: <92% — suggest medical evaluation
- **Sleep apnea indicator**: frequent dips below 90% during sleep

### Context
- Whoop measures SpO2 during sleep
- Altitude affects SpO2 (lower at elevation)
- Consistently low SpO2 + high disturbance count: possible sleep apnea

---

## Skin Temperature

### Interpretation
- Measured relative to personal baseline
- **Elevated** (>0.5°C above baseline): possible illness onset, hormonal changes, poor recovery
- **Consistent elevation for 2+ days**: monitor for illness symptoms
- **Normal fluctuations**: ±0.3°C day to day

---

## Analysis Framework

When analyzing user data, follow this structure:

### 1. Quick Status (current state)
- Latest recovery score + zone
- Last night's sleep performance + hours
- Current strain level
- Any immediate flags (very low HRV, high RHR, low SpO2)

### 2. Trend Analysis (7-30 day window)
- HRV trend (rising/stable/declining vs 30-day avg)
- RHR trend
- Sleep consistency
- Recovery zone distribution (% green/yellow/red)
- Strain load balance

### 3. Pattern Detection
- Day-of-week patterns (weekend effects, Monday drops)
- Sleep debt accumulation
- Strain-recovery mismatch
- Correlation between poor sleep → low recovery → next day

### 4. Actionable Insights (science-backed)
- Based on data, suggest specific improvements:
  - Sleep: timing, duration, environment, consistency
  - Recovery: rest days, stress management, hydration
  - Training: strain matching to recovery, periodization
  - Lifestyle: alcohol impact, screen time, schedule regularity

### 5. Flags / Alerts
- Consistently low HRV (<15ms) → suggest medical check
- SpO2 <92% regularly → possible sleep apnea, suggest evaluation
- RHR elevated 5+ bpm for 3+ days → illness/overtraining watch
- Sleep <6h average for 5+ days → serious sleep debt, health risk
- Recovery red for 3+ consecutive days → forced rest recommended

---

## Prompt Template for Analysis

When asked "how am I doing?" or similar, fetch summary data and analyze:

```
Based on [USER]'s Whoop data for the last [N] days:

METRICS:
- Avg Recovery: X% (zone)
- Avg HRV: Xms (vs 30-day baseline: Xms, trend: rising/falling)
- Avg RHR: Xbpm (vs baseline: Xbpm)
- Avg Sleep: Xh, performance X%
- Deep sleep avg: Xh (X% of total)
- REM avg: Xh (X% of total)
- Avg Strain: X
- SpO2 avg: X%

ANALYSIS:
[Apply the framework above — status, trends, patterns, insights, flags]
```

## Important Disclaimers
- This is NOT medical advice — always recommend consulting a doctor for health concerns
- Wearable data has limitations in accuracy
- Individual baselines matter more than population norms
- One bad day doesn't indicate a problem — look for patterns over 3+ days
- Context matters: travel, altitude, menstrual cycle, medication can all affect metrics
