---
name: apple-health-analyzer
description: Analyze Apple Health exported data (export.xml / 导出.xml) to produce interactive dashboards and actionable health insights. Triggers when users mention Apple Health, health export, health data analysis, or have export.xml / 导出.xml files in their workspace. Supports users with or without wearable devices (Apple Watch, Oura Ring, etc.), handles data gaps gracefully, and adapts analysis to user goals and life stages.
allowed-tools: 
disable: false
---

# Apple Health Analyzer (v2.2.0)

## Overview

This skill transforms raw Apple Health export data into a **multi-report system** of fully Chinese-localized, interactive health dashboards with cross-correlation analysis, personal dynamic baselines, and personalized recommendations. It handles the full pipeline: XML parsing (with token-efficient streaming), data cleaning, statistical analysis, and interactive Plotly visualization — all while adapting to each user's unique data profile, devices, and health goals.

### What's New in v2.2.0

- **Full Chinese Localization**: All chart labels, legends, axes, hover tooltips, and data type names are in Chinese. English abbreviations (HRV, REM, VO2Max, SWOLF) retained in parentheses for professional context.
- **Multi-Report System**: Three independent, specialized reports covering comprehensive health analysis, sleep deep-dive, and yearly data overview.
- **Cross-Correlation Analysis**: Sleep→recovery, deep sleep→HRV, and stress warning system with personal dynamic baselines (P25-P75 percentile self-assessment).
- **Swimming Depth Analysis**: SWOLF efficiency trends, stroke distribution, water temperature correlation, progress tracking.
- **Personal Dynamic Baselines**: Assess current health state against personal historical percentiles rather than population averages.

## Workflow Decision Tree

When this skill is activated, follow this decision tree:

```
User has Apple Health data?
├── YES: XML file found in workspace
│   ├── Step 1: DATA PROFILING (lightweight scan — never load full XML into context)
│   ├── Step 2: USER INTERVIEW (goals, life stages, preferences)
│   ├── Step 3: ADAPTIVE ANALYSIS PLAN (based on available data + goals)
│   ├── Step 4: PARSE & EXTRACT (streaming XML → aggregated CSV)
│   ├── Step 5: ANALYZE & VISUALIZE (generate dashboard)
│   └── Step 6: INSIGHTS & RECOMMENDATIONS (personalized advice)
│
├── YES: Pre-parsed CSV/JSON files exist
│   ├── Skip to Step 2 (interview)
│   └── Continue from Step 3
│
└── NO: No health data found
    └── Guide user through Apple Health export process
```

## Step 1: Data Profiling — Lightweight Discovery

**CRITICAL: Token Conservation Strategy**

Apple Health XML files are typically 100MB–2GB+. NEVER read the raw XML into the conversation context. Instead:

1. **Run the profiling script** (`scripts/parse_health_xml.py --profile-only`) to generate a compact JSON summary
2. **Read only the JSON summary** into context (typically <5KB)
3. **All subsequent parsing happens via script execution**, not file reading

### Profiling Script Usage

```bash
python3 {SKILL_DIR}/scripts/parse_health_xml.py --profile-only --input "<path_to_export.xml>"
```

This produces a `health_profile.json` containing:
- User demographics (birth date, sex, blood type — if available)
- Device inventory (which Apple devices contributed data)
- Data type inventory with record counts and date ranges
- Data density map (which years/months have data)
- Estimated processing time

### Reading the Profile

After profiling, read ONLY the JSON summary:
```
read_file("<workspace>/health_data/health_profile.json")
```

### Device Tier Detection

The profiler automatically classifies the user's setup into one of three tiers:

| Tier | Devices | Available Data | Analysis Scope |
|------|---------|---------------|----------------|
| **Tier 1: iPhone Only** | iPhone (no wearable) | Steps, distance, flights climbed, walking metrics, headphone audio, sleep (if using phone-based tracking app) | Activity trends, mobility analysis, audio exposure |
| **Tier 2: iPhone + Watch (basic)** | iPhone + Apple Watch (older/SE) | Tier 1 + heart rate, active energy, exercise time, basic sleep stages | + Heart rate analysis, energy expenditure, workout tracking |
| **Tier 3: iPhone + Watch (advanced)** | iPhone + Apple Watch Series 7+ / Ultra | Tier 2 + HRV, blood oxygen, respiratory rate, wrist temperature, sleep breathing disturbances, ECG | + Full cardiovascular analysis, sleep quality deep-dive, cycle tracking correlation |

**Fallback rule**: If a metric is missing, NEVER error out. Gracefully skip that analysis module and note what additional data would unlock.

## Step 2: User Interview — Goals & Context

Before analysis, ask the user about their goals using `ask_followup_question`. Keep it to **2–3 focused questions** based on what the data profile reveals.

### Core Question Template

Always ask about analysis goal. Select remaining questions adaptively based on available data:

**Question 1 (ALWAYS ASK):** Analysis Goal
```
What's your primary goal for this health analysis?
Options:
- General health overview / curiosity
- Fitness optimization (training, performance)
- Sleep improvement
- Weight management / body composition
- Stress & recovery monitoring
- Reproductive health tracking (cycle analysis)
- Health condition monitoring (post-illness recovery, chronic condition)
- Pre/post pregnancy health tracking
```

**Question 2 (CONDITIONAL):** Special Life Periods
Ask ONLY IF the data contains MenstrualFlow, Pregnancy, or Lactation records, OR if the user profile indicates female sex:
```
Were there any special health periods during the data timeframe we should account for?
Options:
- Pregnancy / postpartum
- Breastfeeding period
- Major illness or surgery recovery
- Significant lifestyle change (new job, relocation, etc.)
- Menopause transition
- None / prefer not to specify
```

**Question 3 (CONDITIONAL):** Analysis Depth
Ask ONLY IF data spans 3+ years:
```
What time period should we focus on?
Options:
- Full history (comprehensive longitudinal view)
- Last 12 months (recent trends)
- Year-over-year comparison
- Specific period (I'll specify dates)
```

### Interview Adaptations

- **Tier 1 users (iPhone only)**: Skip heart rate and sleep stage questions; focus on activity and mobility
- **Short data history (<1 year)**: Skip longitudinal comparison options
- **Male users or no cycle data**: Skip reproductive health options
- **Users with 3rd-party app data** (detected via diverse `sourceName` values): Inform the user which sources were auto-detected and which will be prioritized. Only ask for manual override if auto-detection finds conflicting sources with similar data quality. Source identification uses pattern matching (see Data Robustness Rule 2), not exact string matching.

## Step 3: Adaptive Analysis Plan

Based on the data profile + user answers, construct an analysis plan. The plan selects from these **analysis modules**:

### Module Registry

| Module | Required Data | Tier | Priority |
|--------|--------------|------|----------|
| **Daily Activity** | StepCount, DistanceWalkingRunning, FlightsClimbed | 1+ | P0 |
| **Workout Analysis** | Workout records | 1+ | P0 |
| **Heart Rate Overview** | HeartRate (daily aggregates) | 2+ | P0 |
| **Resting HR Trend** | RestingHeartRate | 3 | P0 |
| **HRV & Recovery** | HeartRateVariabilitySDNN | 3 | P1 |
| **Sleep Duration** | SleepAnalysis | 1+ | P0 |
| **Sleep Stages** | SleepAnalysis (with stage values) | 2+ | P1 |
| **Sleep Quality** | SleepAnalysis + AppleSleepingWristTemperature | 3 | P2 |
| **Body Composition** | BodyMass, BodyFatPercentage | 1+ | P1 |
| **Menstrual Cycle** | MenstrualFlow | 1+ | P1 |
| **Cycle-Vital Correlation** | MenstrualFlow + RestingHeartRate + HRV | 3 | P2 |
| **Cardio Fitness** | VO2Max | 3 | P1 |
| **Respiratory** | RespiratoryRate, OxygenSaturation | 3 | P2 |
| **Audio Exposure** | HeadphoneAudioExposure, EnvironmentalAudioExposure | 1+ | P2 |
| **Mobility & Gait** | WalkingSpeed, WalkingStepLength, WalkingAsymmetryPercentage | 1+ | P2 |
| **Swimming Analysis** (v2.2.0) | Workout (Swimming) + SwimmingStrokeCount + SwimmingDistance + WaterTemperature | 2+ | P1 |
| **Cross-Correlation** (v2.2.0) | SleepAnalysis + RestingHeartRate + HRV | 3 | P1 |
| **Personal Dynamic Baselines** (v2.2.0) | Any long-term metric (30+ days) | 1+ | P1 |

### Plan Construction Rules

1. **Always include** all P0 modules that have sufficient data
2. **Include P1 modules** if the user's goal aligns (e.g., "cycle analysis" → include Menstrual Cycle)
3. **Include P2 modules** only if user requests deep analysis or "general overview"
4. **Data sufficiency threshold**: A module requires at least 14 data points to produce meaningful analysis. Below that, show a "limited data" warning but still display what's available.
5. **Special period handling**: If user declared a pregnancy/illness period, mark those date ranges for:
   - Separate analysis (before/during/after comparison)
   - Exclusion from "normal" baseline calculations
   - Special annotations on all time-series charts

### Report the Plan

Before executing, briefly tell the user which modules will run and which are skipped (with reason). Example:

> Based on your data, I'll analyze: **Daily Activity** (N years of step data), **Workouts** (N sessions), **Heart Rate** (from YYYY), **Sleep** (YYYY–present), **Menstrual Cycles** (N records). Skipping: Blood Oxygen (insufficient data), Respiratory Rate (limited data). Special period (if any) will be handled separately in trend analysis.

## Step 4: Parse & Extract

### Execution Strategy

Run the parsing script to extract data into lightweight CSV files:

```bash
python3 {SKILL_DIR}/scripts/parse_health_xml.py \
  --input "<path_to_export.xml>" \
  --output-dir "<workspace>/health_data/" \
  --modules "activity,workout,heartrate,sleep,menstrual,body" \
  --start-date "2016-01-01"
```

### Critical XML Parsing Rules

1. **Streaming parse with `iterparse`** — never `ET.parse()` the full tree for files >50MB
2. **`elem.clear()` after processing** — release memory immediately
3. **Aggregate high-frequency data during parsing**:
   - HeartRate: 1M+ records → aggregate to daily min/max/mean/std/count
   - StepCount: Deduplicate overlapping sources, sum per day
   - ActiveEnergyBurned: Sum per day
   - PhysicalEffort: Aggregate to daily summary
4. **Preserve low-frequency data as-is**:
   - RestingHeartRate, HRV, VO2Max: one per day, keep individual records
   - MenstrualFlow: keep individual records
   - Workout: keep individual records with full metadata
5. **Handle timezone**: Apple Health stores dates in format `2025-03-30 08:15:23 +0800`. **Current limitation**: the scripts truncate timezone info for simplicity — all dates are treated as local time at the moment of recording. This works correctly for users who stay in one timezone. For users who travel across timezones, some date attributions may be slightly off. A future version will parse full timezone offsets and convert to user's home timezone.
6. **Handle duplicate sources**: When multiple devices record the same metric (e.g., iPhone + Watch both record steps), use this priority:
   - Apple Watch > iPhone (for motion data)
   - Prefer the source with continuous data
   - If same source, deduplicate overlapping time ranges
7. **Normalize all string fields**: Apple Health exports may contain Unicode whitespace variants (non-breaking space `\xa0`, narrow no-break space `\u202F`, figure space `\u2007`, etc.) in `sourceName` and other text fields. **Always** apply `unicodedata.normalize('NFKC', s)` and collapse whitespace before any string matching or comparison. The `normalize_str()` helper in `parse_health_xml.py` handles this.

### Output CSV Schema

See `references/health_data_types.md` for complete field definitions of each output CSV.

## Step 5: Analyze & Visualize

### Dashboard Generation

**Core Dashboard (v2.1.0 pipeline):**
```bash
python3 {SKILL_DIR}/scripts/generate_dashboard.py \
  --data-dir "<workspace>/health_data/" \
  --output "<workspace>/health_dashboard.html" \
  --modules "<comma-separated module list>" \
  --special-periods '<JSON array of special period configs>'
```

**Multi-Report System (v2.2.0):**

In addition to the core dashboard, v2.2.0 provides three specialized, independent analysis reports. Each report reads from the parsed CSV files in `health_data/` and generates a self-contained HTML file. Run these after Step 4 (Parse & Extract) completes.

**Report 1: Comprehensive Health Analysis**
```bash
python3 {SKILL_DIR}/scripts/health_analysis.py
```
- Input: `health_data/*.csv` (in current working directory)
- Output: `health_report.html`
- Includes: Heart rate trends, RHR/HRV, VO2Max, sleep analysis, daily activity, workout statistics, menstrual cycle, swimming depth analysis, cross-correlations, personal dynamic baselines, actionable insights
- Note: Paths are relative to the working directory. Run from the workspace where `health_data/` exists.

**Report 2: Sleep Deep-Dive Dashboard**
```bash
python3 {SKILL_DIR}/scripts/sleep_analysis_dashboard.py
```
- Input: `health_data/*.csv` (in current working directory)
- Output: `sleep_analysis_report.html`
- Includes: Multi-source sleep deduplication, sleep stages/efficiency/scoring, monthly statistics, pregnancy period comparison, physiological indicators (RHR/HRV/SpO2/respiratory rate/wrist temperature)

**Report 3: Yearly Data Overview**
```bash
# Step 1: Extract yearly statistics
python3 {SKILL_DIR}/scripts/yearly_stats.py
# Step 2: Generate the report
python3 {SKILL_DIR}/scripts/yearly_analysis_report.py
```
- Input: `导出.xml` or `export.xml` (for yearly_stats.py), `yearly_stats.json` (for yearly_analysis_report.py)
- Output: `yearly_stats.json`, then `yearly_analysis_report.html`
- Includes: Data type × year heatmap, annual data volume trends, type distribution, device source breakdown, analysis strategy recommendations

**Data Exploration (utility):**
```bash
python3 {SKILL_DIR}/scripts/data_exploration.py
```
- For ad-hoc inspection of swimming details, device inventory, or data type specifics

### Visualization Standards

1. **Use Plotly exclusively** for interactive HTML dashboards
2. **Color scheme**: Apple Health inspired palette
   - Primary: `#007AFF` (blue), `#FF9500` (orange), `#34C759` (green), `#FF3B30` (red), `#AF52DE` (purple)
   - Background: `#FAFAFA`, Grid: `#E5E5EA`
3. **Responsive layout**: Dashboard must work on both desktop and mobile
4. **Full Chinese localization** (v2.2.0): All chart labels, legends, axes, hover tooltips, and metric names MUST be in Chinese. Use the following standard mappings:

   **Data Type Name Mappings:**
   | English Identifier | Chinese Name |
   |-------------------|-------------|
   | StepCount | 步数 |
   | DistanceWalkingRunning | 步行+跑步距离 |
   | FlightsClimbed | 已爬楼层 |
   | ActiveEnergyBurned | 活动能量 |
   | HeartRate | 心率 |
   | RestingHeartRate | 静息心率 |
   | HeartRateVariabilitySDNN | 心率变异性(HRV) |
   | VO2Max | 最大摄氧量(VO2Max) |
   | OxygenSaturation | 血氧饱和度 |
   | RespiratoryRate | 呼吸频率 |
   | BodyMass | 体重 |
   | BodyFatPercentage | 体脂率 |
   | SleepAnalysis | 睡眠分析 |
   | MenstrualFlow | 月经 |
   | BodyTemperature | 体温 |
   | AppleSleepingWristTemperature | 腕部温度 |
   | WalkingSpeed | 步速 |
   | WalkingStepLength | 步幅 |
   | WalkingAsymmetryPercentage | 步行不对称性 |
   | HeadphoneAudioExposure | 耳机音量 |
   | EnvironmentalAudioExposure | 环境声级 |
   | SwimmingStrokeCount | 游泳划水次数 |

   **Unit Mappings:**
   | English | Chinese |
   |---------|---------|
   | bpm | 次/分 |
   | ms | 毫秒 |
   | kcal | 千卡 |
   | mL/(kg·min) | 毫升/(千克·分钟) |
   | km | 公里 |
   | count | 次 |
   | % | % |

   **Sleep Stage Mappings:**
   | English | Chinese |
   |---------|---------|
   | InBed | 在床上 |
   | Asleep / Core | 浅睡 |
   | Deep | 深睡 |
   | REM | 快速眼动(REM) |
   | Awake | 清醒 |

   English abbreviations (HRV, REM, VO2Max, SWOLF, BMI) are retained in parentheses after the Chinese name for professional context.

5. **Chart types by data**:
   - Time series trends: Line chart with 7-day / 30-day moving averages
   - Distributions: Box plots or violin plots
   - Proportions: Donut charts
   - Calendar patterns: Heatmap (GitHub-contribution style)
   - Correlations: Scatter with trendline
   - Comparisons: Grouped bar charts

### Module-Specific Analysis Guidelines

#### Daily Activity Module
- Calculate daily step count with proper source deduplication
- Show weekly/monthly aggregation options
- Weekday vs. weekend comparison
- Year-over-year overlay for seasonal patterns
- Highlight streaks and personal records

#### Workout Module
- Workout type distribution (donut chart)
- Frequency heatmap (calendar view)
- Duration and calorie trends by month
- Sport-type evolution timeline (when did user start each sport)
- For users with GPS routes: map visualization of workout routes

#### Heart Rate Module
- Resting heart rate long-term trend with 30-day moving average
- Daily min/max/mean band chart
- Heart rate zone distribution (Zone 1–5 based on age-estimated max HR)
- HRV trend with recovery insights
- Anomaly detection: flag days with unusually high/low resting HR

#### Sleep Module
- **Duration**: Daily sleep hours with 7-day rolling average, weekday vs. weekend
- **Timing**: Bedtime and wake time scatter plot with drift detection
- **Stages** (if available): Stacked area chart of Core/Deep/REM/Awake
- **Quality metrics**: Sleep efficiency = sleep time / in-bed time
- **Cross-device handling**: Different sleep trackers (Apple Watch, iPhone, 3rd-party) may have different stage classification. Normalize by source.
- **Key insight**: Compare against age-adjusted recommendations (adults: 7–9 hours, deep sleep: 15–20%)

#### Menstrual Cycle Module
- Cycle length calculation (days between first day of consecutive periods)
- Cycle regularity score (coefficient of variation of cycle lengths)
- Period duration tracking
- **Correlation analysis** (if Tier 3 data available):
  - Resting HR across cycle phases (follicular vs. luteal)
  - HRV pattern across cycle
  - Wrist temperature changes (basal body temperature proxy)
  - Sleep quality across cycle phases

#### Body Composition Module
- Weight trend with moving average
- BMI tracking (with healthy range reference bands)
- Body fat percentage trend (if available)
- Correlation with activity levels

#### Swimming Analysis Module (v2.2.0)
- **Progress tracking**: Distance, pace, heart rate, energy burn four-dimensional trend analysis
- **SWOLF efficiency**: Median + best value + P25-P75 range visualization
- **Stroke distribution**: Freestyle/breaststroke/backstroke/butterfly distance breakdown
- **Water temperature correlation**: Scatter plot analyzing water temperature impact on exercise heart rate
- **Comprehensive swim log**: Net swim time, rest ratio, primary stroke, detailed record table
- Data extracted from `Workout` records where `workoutActivityType` contains `Swimming`
- SWOLF calculated from workout metadata `HKSWOLFScore` or derived from `HKLapLength` and stroke count

#### Cross-Correlation Analysis Module (v2.2.0)
- **Sleep → Next-Day Recovery**: Analyze correlation between sleep duration and next-day resting HR / HRV
  - Quantify body response to insufficient sleep
  - Show scatter plot with regression and Pearson correlation coefficient
- **Deep Sleep % → HRV**: Analyze relationship between deep sleep proportion and next-day heart rate variability
  - Stronger deep sleep → higher HRV (better recovery) expected
- **Exercise Load → Recovery**: Analyze workout volume impact on HR/HRV recovery trends
- **Stress Warning System**: Dual-indicator detection combining elevated RHR + depressed HRV
  - Flag days where RHR > personal P75 AND HRV < personal P25
  - Provide actionable recovery recommendations for flagged periods

#### Personal Dynamic Baselines Module (v2.2.0)
- Calculate P25, P50 (median), and P75 percentiles from user's own historical data (minimum 30 data points)
- Assess current state against personal historical range rather than population averages
- Applies to: resting HR, HRV, sleep duration, deep sleep %, step count, active energy
- Visual indicators: "Below personal average" / "Within normal range" / "Above personal average"
- Enables truly personalized insights (e.g., "Your HRV of 45ms is at your P30 — below your typical P50 of 52ms, suggesting possible recovery deficit")

### Special Period Handling

When the user has declared special periods (pregnancy, illness, etc.):

1. **Visual markers**: Add vertical shaded regions on all time-series charts with labels
2. **Separate statistics**: Calculate summary stats for before/during/after periods
3. **Adjusted baselines**: When computing "normal ranges" or anomaly detection, exclude special periods from the baseline
4. **Narrative callouts**: In the insights section, explicitly discuss how metrics changed during special periods

Example pregnancy handling:
```
Pregnancy detected: YYYY-MM-DD (from health records)
→ Mark charts with pregnancy period (approx. start to end)
→ Expect: elevated resting HR, altered sleep patterns, paused menstrual tracking
→ Post-pregnancy: track recovery metrics vs. pre-pregnancy baseline
```

## Step 6: Insights & Recommendations

After generating the dashboard, provide a written summary with:

### Structure

1. **Health Snapshot** (2–3 sentences): Overall health status at a glance
2. **Key Findings** (3–5 bullet points): Most notable patterns or changes
3. **Metric-Specific Insights**: For each analyzed module, provide:
   - Current status vs. recommended ranges
   - Trend direction (improving / stable / declining)
   - Notable patterns (seasonal, weekly, etc.)
4. **Actionable Recommendations** (3–5 items): Specific, evidence-based suggestions
5. **Data Quality Notes**: What's missing, what would improve the analysis

### Recommendation Guidelines

- **Be specific**: "Try to get 30 more minutes of deep sleep by avoiding screens 1 hour before bed" rather than "Sleep more"
- **Reference the data**: "Your resting HR has decreased from 72 to 65 bpm over 6 months, coinciding with your increased strength training frequency"
- **Respect limitations**: Always add "This analysis is for informational purposes only and is not medical advice"
- **Consider the user's goal**: Weight management user gets different recommendations than a fitness optimizer
- **Life stage awareness**: Recommendations for a pregnant user differ from a marathon trainer

### Recommendation Categories

Based on user goals, emphasize relevant categories:

| User Goal | Primary Recommendation Focus |
|-----------|------------------------------|
| General health | Balance of activity, sleep, stress metrics |
| Fitness optimization | Training load, recovery, VO2Max improvement |
| Sleep improvement | Sleep hygiene, consistency, stage optimization |
| Weight management | Activity-calorie balance, trend correlation |
| Stress & recovery | HRV optimization, activity-rest balance |
| Cycle tracking | Cycle regularity, phase-specific adjustments |
| Condition monitoring | Trend stability, anomaly awareness |

## Data Gap Handling — Fallback Rules

Data gaps are extremely common in Apple Health data. Handle them at every level:

### Missing Data Classification

| Gap Type | Definition | Handling Strategy |
|----------|-----------|-------------------|
| **Device transition** | No Watch data before purchase date | Show "data available from [date]" marker; don't interpolate |
| **Sporadic recording** | Random missing days/weeks | Use available data with appropriate caution notes |
| **Metric not available** | Entire metric type is absent (e.g., no VO2Max) | Skip the analysis module; suggest how to enable it |
| **Source conflict** | Multiple devices recording same metric | Deduplicate using source priority rules |
| **Low-frequency manual entry** | Body weight recorded only occasionally | Show raw points + moving average; don't interpolate aggressively |

### Fallback Hierarchy

When a preferred metric is unavailable, fall back to alternatives:

```
RestingHeartRate unavailable?
  → Calculate from HeartRate records (min HR during 2am–5am window)
  → If HeartRate also unavailable → skip HR analysis

SleepAnalysis stages unavailable?
  → Use total InBed/Asleep duration only
  → If no sleep data at all → analyze rest patterns from activity gaps

VO2Max unavailable?
  → Estimate fitness level from resting HR trend + activity level
  → Note: "Estimated fitness level (not clinical VO2Max)"

BodyMass infrequent?
  → Show sparse data points connected, no interpolation
  → Note: "Weight recorded [N] times over [M] months — consider more frequent tracking"

MenstrualFlow incomplete?
  → Calculate available cycle lengths with confidence intervals
  → Note which cycles might have missing data
```

### Visualization with Gaps

- **NEVER connect data points across large gaps** (>30 days) with a line — use dotted line or leave gap
- **Show data density indicator** on time-series charts (e.g., background heatmap of data availability)
- **Distinguish zero from missing**: 0 steps on a day ≠ missing data; check if any other records exist for that day

## Token & Performance Optimization

### Rules for Context Management

1. **NEVER read export.xml content into conversation** — always use scripts
2. **NEVER read large CSV files into conversation** — read summary statistics or small samples only
3. **Profile first, parse second** — know what data exists before extracting
4. **Script-based processing** — all heavy computation happens in Python scripts, not in conversation
5. **Incremental output** — generate dashboard HTML progressively; don't build it all in context
6. **Summary-driven communication** — show users summary numbers and chart screenshots, not raw data tables

### Script Execution Pattern

```
1. Run profiling script → read small JSON profile
2. Interview user → decide analysis modules
3. Run parsing script → generates CSV files (don't read them)
4. Run dashboard script → generates HTML file
5. Preview HTML in browser
6. Read any small summary files for insights text
```

### Performance Estimates

| File Size | Profile Time | Parse Time | Dashboard Time |
|-----------|-------------|------------|----------------|
| <100MB | <10s | <30s | <15s |
| 100MB–500MB | <30s | 1–3 min | <30s |
| 500MB–1GB | <1 min | 3–5 min | <30s |
| >1GB | 1–2 min | 5–10 min | <1 min |

## Multi-User Adaptations

This skill must work for diverse user profiles. Key adaptations:

### By Device Setup
- **iPhone only**: No continuous heart rate. Activity analysis relies on step counter and motion coprocessor. Sleep may come from 3rd-party apps (Pillow, Sleep Cycle, AutoSleep) synced to Health — detected via `sourceName`.
- **iPhone + basic Watch**: Heart rate available but no advanced metrics. Workout detection is automatic.
- **iPhone + advanced Watch**: Full suite. Wrist temperature enables menstrual cycle prediction. ECG data may be available.
- **Third-party wearables** (Oura, Whoop, Garmin via Health sync): Data types and naming may differ. The parser handles standard HK type identifiers regardless of source.

### By Data History Length
- **<3 months**: Focus on baselines and initial patterns. No trend analysis. Set expectations.
- **3–12 months**: Seasonal patterns may emerge. Weekly patterns are solid.
- **1–3 years**: Good longitudinal trends. Year-over-year comparisons meaningful.
- **3+ years**: Long-term health trajectory. Lifestyle change impacts detectable. Device transitions visible.

### By User Demographics
- **Age-adjusted references**: Heart rate zones, sleep duration recommendations, VO2Max percentiles all depend on age
- **Sex-aware analysis**: Menstrual cycle module activates automatically when data exists; never assume
- **Fitness level detection**: Infer from resting HR, workout frequency, and VO2Max to calibrate recommendations

### By Cultural/Regional Context
- **Unit handling**: Detect from XML whether metric or imperial; output in user's preferred units
- **Language**: Support both Chinese (导出.xml) and English (export.xml) file names
- **Date format**: Follow user's locale for date display

## Error Handling

| Error | Recovery |
|-------|----------|
| XML file too large for memory | Switch from `ET.parse()` to `iterparse()` streaming |
| XML file not found | Guide user: Settings → Health → Export All Health Data |
| Malformed XML (invalid schema) | Attempt lenient parsing; report unparseable sections |
| No data for requested module | Show empty state with explanation of what's needed |
| Script execution fails | Fall back to in-context Python with small data samples |
| Plotly not installed | Guide `pip install plotly` (pandas is optional, only needed for custom analysis beyond the scripts) |
| CSV generation fails mid-way | Partial results are still usable; report which modules succeeded |

## Data Robustness Rules — CRITICAL

These rules address common failure modes in Apple Health data processing. They are **general-purpose** and must be followed regardless of the specific user, device, or data history.

### Rule 1: Unicode String Normalization

Apple Health exports frequently contain Unicode whitespace variants in text fields, especially `sourceName`. This is caused by iOS localization, firmware changes, or device-specific formatting. The most common case is non-breaking space (`\xa0` / U+00A0) instead of regular space in device names like "XXX的Apple\xa0Watch", but other Unicode spaces also occur.

**MUST DO**:
- Apply `unicodedata.normalize('NFKC', s)` followed by whitespace collapsing to **all string fields** before any comparison, matching, or filtering operation
- Use the `normalize_str()` helper provided in `parse_health_xml.py`
- **NEVER** use exact string literals for source name matching. Always normalize first.
- This applies to: `sourceName`, `value` (for category types), workout `type`, and any user-facing text

### Rule 2: Data Source Identification — Pattern Matching, Not Hardcoding

**NEVER hardcode specific device names** (like "John's Apple Watch" or "陈XX的Apple Watch"). Device names contain personal information and change when users rename devices, switch languages, or upgrade hardware.

**MUST DO**:
- Identify data sources using **keyword pattern matching** after normalization:
  - Apple Watch: check if normalized `sourceName` contains `"Apple Watch"` (case-insensitive)
  - iPhone: contains `"iPhone"` 
  - Third-party apps: match known app identifiers like `"Pokémon Sleep"`, `"AutoSleep"`, `"Oura"`, `"Garmin"`, etc.
- For sleep data specifically, prioritize sources by **data quality** (richness of sleep stages), not by name:
  1. Sources that provide detailed sleep stages (Deep/REM/Core) → highest priority
  2. Sources that provide at least InBed/Asleep distinction → medium priority
  3. Sources with only basic sleep records → lowest priority
- When multiple sources exist for the same night, use the richest one
- Allow users to override source preferences via configuration, but **auto-detection must work without any user input**

Example of correct pattern matching:
```python
import unicodedata

def classify_source(source_name):
    """Classify a data source by pattern matching, not exact strings."""
    normalized = unicodedata.normalize('NFKC', source_name).lower()
    normalized = ' '.join(normalized.split())  # collapse whitespace
    
    if 'apple watch' in normalized:
        return 'apple_watch'
    elif 'iphone' in normalized:
        return 'iphone'
    elif any(app in normalized for app in ['pokémon sleep', 'pokemon sleep']):
        return 'pokemon_sleep'
    elif any(app in normalized for app in ['autosleep', 'pillow', 'sleep cycle']):
        return 'sleep_tracker_app'
    elif any(app in normalized for app in ['oura', 'garmin', 'whoop', 'zepp', 'fitbit']):
        return 'third_party_wearable'
    else:
        return 'other'
```

### Rule 3: Temporal Reference — Always Use Data-Relative Dates

**NEVER use `datetime.now()` as a reference point** for "recent N days" calculations or any time-relative analysis. Users frequently:
- Export data days or weeks before running the analysis
- Re-run analysis on the same export multiple times
- Share export files with others

**MUST DO**:
- Use the **last date in the actual data** as the reference point:
  ```python
  last_date = sorted_dates[-1]  # NOT datetime.now()
  recent_30 = [d for d in data if d['date'] >= (last_date - timedelta(days=30))]
  ```
- The `recent_n_days()` helper in `generate_dashboard.py` implements this correctly
- This applies to ALL "recent" calculations: KPI cards, moving averages, trend comparisons, etc.
- Display the actual data date range in the dashboard header so users know what period they're looking at

### Rule 4: Adaptive Visualization — Scale to Data

Chart configurations MUST adapt to the actual data being displayed. Never use fixed tick intervals that assume a specific data range.

**MUST DO**:
- Use `adaptive_xaxis(dates)` for all time-series charts — it automatically selects appropriate `tickformat` and `dtick` based on data span:
  | Data Span | dtick | tickformat | Example |
  |-----------|-------|------------|---------|
  | < 3 months | M1 | %m-%d | 03-15 |
  | 3–12 months | M1 | %Y-%m | 2025-03 |
  | 1–3 years | M3 | %Y-%m | 2025-03 |
  | 3–5 years | M6 | %Y-%m | 2025-06 |
  | > 5 years | M12 | %Y | 2025 |
- Use `adaptive_category_xaxis(labels)` for monthly/categorical aggregation charts
- Always set `tickangle` to prevent label overlap on dense axes
- Set explicit `tickfont.size` (recommended: 11px) for consistency

### Rule 5: Anomaly and Outlier Handling

**NEVER silently discard data without documentation.** Extreme values may be genuine (marathon day, illness, jet lag) or data errors.

**MUST DO**:
- Define reasonable bounds per metric (e.g., sleep: 1–18 hours, steps: 0–100,000)
- Records outside bounds should be **flagged** (not deleted) when possible
- In charts, show flagged outliers with distinct markers or annotations
- In insights text, mention how many records were excluded and why
- For sleep specifically: nights with only InBed/Awake data (no sleep stages) should still be included in duration analysis but marked as "no stage data" in stage breakdowns

### Rule 6: Night Date Attribution for Sleep

Sleep sessions that start before a cutoff hour belong to the **previous calendar date**'s night. The current implementation uses 18:00 (6 PM) as the cutoff — any sleep session starting before 18:00 is attributed to the previous day's night.

This handles common cases:
- Going to bed at 11 PM → attributed to that day
- Napping at 2 PM → attributed to previous day (may need filtering)
- Falling asleep at 2 AM → attributed to previous day ✓

**Improvement consideration**: In a future version, distinguish naps from main sleep sessions by duration (naps typically < 2 hours) and time of day. For now, the cutoff approach works for the primary use case of nightly sleep tracking.



### scripts/
- `parse_health_xml.py` (v2.1.0) — Streaming XML parser with profiling mode. Handles data extraction, daily aggregation, **source-based deduplication for additive metrics** (steps, distance, energy, flights), Unicode normalization, and CSV generation.
- `generate_dashboard.py` (v2.1.0) — Plotly-based interactive dashboard generator. Reads CSV files and produces **self-contained offline HTML** (Plotly JS embedded). Features include **multi-source sleep deduplication**, adaptive axis scaling, data-relative time calculations, data range header display, and smart body fat percentage detection.
- `health_analysis.py` (v2.2.0) — Comprehensive health analysis report generator. Produces `health_report.html` with heart rate/HRV/sleep/workout/menstrual/swimming analysis, cross-correlations, personal dynamic baselines, and fully Chinese-localized chart labels. Includes swimming depth analysis (SWOLF, stroke distribution, water temperature correlation) and stress warning system.
- `sleep_analysis_dashboard.py` (v2.2.0) — Sleep-focused dashboard with multi-source deduplication, sleep stage/efficiency/scoring analysis, pregnancy period three-phase comparison (before/during/after), and physiological indicators (RHR/HRV/SpO2/respiratory rate/wrist temperature). All labels fully Chinese-localized.
- `yearly_analysis_report.py` (v2.2.0) — Yearly data overview report. Generates heatmap of data types × years, annual data volume trends, data type distribution, device source breakdown, and automated analysis strategy recommendations. Chinese data type name mapping included.
- `yearly_stats.py` (v2.2.0) — Yearly statistics extractor using streaming XML parsing. Produces `yearly_stats.json` with per-year record counts by data type.
- `data_exploration.py` (v2.2.0) — Data exploration utility for investigating swimming details, device inventory, and data type specifics. Useful for ad-hoc data inspection during analysis.

### references/
- `health_data_types.md` — Complete mapping of Apple Health data type identifiers to human-readable names, units, expected ranges, and analysis notes.
- `analysis_templates.md` — Statistical analysis templates for each module, including formulas, reference ranges, and insight generation patterns.

### assets/
(Reserved — all output is generated dynamically. No static assets required.)

## Implementation Status Reference

This section clarifies which features are fully implemented in the scripts vs. described in this document as guidelines for the LLM to implement via custom code during analysis.

### Implemented in Scripts (v2.1.0 — Core Pipeline)

| Feature | Script | Status |
|---------|--------|--------|
| Streaming XML parse + profiling | parse_health_xml.py | Done |
| Unicode NFKC normalization | parse_health_xml.py | Done |
| Pattern-based source classification | parse_health_xml.py | Done |
| Step/distance/energy source deduplication | parse_health_xml.py | Done |
| Sample standard deviation (Bessel's correction) | parse_health_xml.py | Done |
| Sleep multi-source deduplication | generate_dashboard.py | Done |
| Sleep night-date attribution (18:00 cutoff) | generate_dashboard.py | Done |
| Data-relative `recent_n_days()` | generate_dashboard.py | Done |
| Adaptive x-axis scaling | generate_dashboard.py | Done |
| Body fat smart % detection | generate_dashboard.py | Done |
| Data date range in dashboard header | generate_dashboard.py | Done |
| Offline-capable HTML (Plotly embedded) | generate_dashboard.py | Done |
| Activity module (steps, flights) | generate_dashboard.py | Done |
| Heart rate module (RHR, HRV, HR range, VO2Max) | generate_dashboard.py | Done |
| Sleep module (duration, stages) | generate_dashboard.py | Done |
| Workout module (types, frequency) | generate_dashboard.py | Done |
| Menstrual cycle module | generate_dashboard.py | Done |
| Body composition module (weight, body fat) | generate_dashboard.py | Done |

### Implemented in Scripts (v2.2.0 — Multi-Report System & Advanced Analysis)

| Feature | Script | Status |
|---------|--------|--------|
| **Full Chinese localization** (all labels/legends/tooltips/axes) | health_analysis.py, sleep_analysis_dashboard.py, yearly_analysis_report.py | Done |
| **Comprehensive health analysis report** (HR/HRV/sleep/workout/menstrual) | health_analysis.py → health_report.html | Done |
| **Swimming depth analysis** (SWOLF, stroke distribution, water temp, progress) | health_analysis.py | Done |
| **Cross-correlation analysis** (sleep→recovery, deep sleep→HRV) | health_analysis.py | Done |
| **Personal dynamic baselines** (P25-P75 percentile self-assessment) | health_analysis.py | Done |
| **Stress warning system** (RHR↑ + HRV↓ dual-indicator detection) | health_analysis.py | Done |
| **Actionable health insights** (data-driven recommendations) | health_analysis.py | Done |
| **Sleep-focused dashboard** (stages/efficiency/scoring) | sleep_analysis_dashboard.py → sleep_analysis_report.html | Done |
| **Pregnancy period comparison** (before/during/after three-phase analysis) | sleep_analysis_dashboard.py | Done |
| **Sleep physiological indicators** (RHR/HRV/SpO2/respiratory rate/wrist temp) | sleep_analysis_dashboard.py | Done |
| **Multi-source sleep deduplication** (in sleep dashboard) | sleep_analysis_dashboard.py | Done |
| **Yearly data overview** (heatmap, type distribution, device breakdown) | yearly_analysis_report.py → yearly_analysis_report.html | Done |
| **Chinese data type name mapping** (22+ types) | yearly_analysis_report.py | Done |
| **Analysis strategy recommendations** (auto-generated from data distribution) | yearly_analysis_report.py | Done |
| **Yearly statistics extraction** (streaming XML → JSON) | yearly_stats.py → yearly_stats.json | Done |
| **Data exploration utility** (swimming/device/type inspection) | data_exploration.py | Done |

### Not Yet in Scripts (LLM should implement via custom code if needed)

| Feature | Notes |
|---------|-------|
| Mobility module visualization | Parser extracts data to CSV; dashboard generator not yet implemented |
| Audio exposure module visualization | Parser extracts data to CSV; dashboard generator not yet implemented |
| GitHub-style calendar heatmap | Described in guidelines; implement with Plotly heatmap if user wants |
| Bedtime/waketime scatter plot | Implement from sleep_analysis.csv data |
| Heart rate zone distribution | Implement using age-based HR zones from analysis_templates.md |
| Weekday vs weekend comparison charts | Stats templates available; charts not auto-generated |
| Year-over-year overlay | Implement for users with 2+ years of data |
| Data density indicator on charts | Nice-to-have background heatmap |
| Large gap (>30 days) dotted line | Currently draws solid lines across all gaps |
| Full timezone parsing | Current: timezone truncated; works for single-timezone users |
| Tab navigation in dashboard | All modules displayed vertically; tabs not yet implemented |

## Important Disclaimers

Always include in generated reports:
1. "This analysis is generated from Apple Health export data and is for informational purposes only."
2. "This is not medical advice. Consult a healthcare professional for medical decisions."
3. "Data accuracy depends on device sensors and wearing compliance."
