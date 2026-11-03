# Analysis Templates & Insight Generation Patterns

Statistical analysis templates for each health module. Each template includes calculation formulas, reference ranges, anomaly detection rules, and insight generation patterns.

## Data Cleaning Utilities (MUST USE)

### Unicode String Normalization
```python
import unicodedata

def normalize_str(s):
    """Normalize Unicode variants — MUST apply to all string fields before matching."""
    if not s:
        return s
    s = unicodedata.normalize('NFKC', s)
    return ' '.join(s.split())
```

### Source Classification by Pattern Matching
```python
def classify_source(source_name):
    """Classify data source using pattern matching (never exact strings)."""
    norm = normalize_str(source_name).lower()
    if 'apple watch' in norm:
        return 'apple_watch'
    elif 'iphone' in norm:
        return 'iphone'
    elif any(app in norm for app in ['pokémon sleep', 'pokemon sleep']):
        return 'pokemon_sleep'
    elif any(app in norm for app in ['autosleep', 'pillow', 'sleep cycle']):
        return 'sleep_tracker_app'
    elif any(app in norm for app in ['oura', 'garmin', 'whoop', 'zepp', 'fitbit']):
        return 'third_party_wearable'
    else:
        return 'other'
```

### Data-Relative Recency (NOT datetime.now())
```python
def recent_n_days(sorted_dates, values, n=30):
    """Get recent N days relative to LAST DATA DATE, not current time."""
    if not sorted_dates:
        return [], []
    last_date = datetime.strptime(str(sorted_dates[-1])[:10], '%Y-%m-%d')
    cutoff = (last_date - timedelta(days=n)).strftime('%Y-%m-%d')
    return zip(*[(d, v) for d, v in zip(sorted_dates, values) if str(d)[:10] >= cutoff]) or ([], [])
```

### Adaptive Axis Configuration
```python
def adaptive_xaxis(dates):
    """Auto-select Plotly xaxis tick config based on data time span."""
    span_days = (parse(dates[-1]) - parse(dates[0])).days
    if span_days < 90:      return {'tickformat': '%m-%d',  'dtick': 'M1'}
    elif span_days < 365:    return {'tickformat': '%Y-%m',  'dtick': 'M1'}
    elif span_days < 365*3:  return {'tickformat': '%Y-%m',  'dtick': 'M3'}
    elif span_days < 365*5:  return {'tickformat': '%Y-%m',  'dtick': 'M6'}
    else:                    return {'tickformat': '%Y',     'dtick': 'M12'}
```

## General Statistical Utilities

### Moving Average
```python
def moving_average(series, window=7):
    """Calculate rolling mean with minimum periods = window // 2"""
    return series.rolling(window=window, min_periods=window // 2).mean()
```

### Trend Detection
```python
from scipy import stats

def detect_trend(dates, values, min_points=14):
    """
    Linear regression trend detection.
    Returns: slope, p_value, direction ('improving'/'declining'/'stable')
    """
    if len(values) < min_points:
        return None, None, 'insufficient_data'
    
    x = np.arange(len(values))
    slope, intercept, r_value, p_value, std_err = stats.linregress(x, values)
    
    if p_value > 0.05:
        return slope, p_value, 'stable'
    return slope, p_value, 'improving' if slope < 0 else 'declining'  # For HR, lower is better
```

### Anomaly Detection
```python
def detect_anomalies(series, window=30, n_std=2.5):
    """Flag values outside rolling mean ± n_std * rolling_std"""
    rolling_mean = series.rolling(window, min_periods=window//2).mean()
    rolling_std = series.rolling(window, min_periods=window//2).std()
    upper = rolling_mean + n_std * rolling_std
    lower = rolling_mean - n_std * rolling_std
    anomalies = (series > upper) | (series < lower)
    return anomalies
```

### Weekday vs Weekend Comparison
```python
def weekday_weekend_compare(df, date_col, value_col):
    """Compare metric between weekdays and weekends"""
    df['is_weekend'] = pd.to_datetime(df[date_col]).dt.dayofweek >= 5
    weekday_mean = df[~df['is_weekend']][value_col].mean()
    weekend_mean = df[df['is_weekend']][value_col].mean()
    diff_pct = (weekend_mean - weekday_mean) / weekday_mean * 100
    return weekday_mean, weekend_mean, diff_pct
```

## Module: Daily Activity

### Step Count Analysis

**Daily Summary Calculation:**
```python
# After deduplication, calculate daily totals
daily_steps = step_df.groupby('date')['value'].sum()

# Key metrics
avg_daily_steps = daily_steps.mean()
median_daily_steps = daily_steps.median()
days_above_10k = (daily_steps >= 10000).sum()
total_days = len(daily_steps)
pct_above_10k = days_above_10k / total_days * 100
```

**Insight Templates:**
- "Your average daily step count is {avg:,.0f} steps ({relation} the commonly recommended 10,000 steps)."
- "You hit 10,000+ steps on {pct:.0f}% of days ({days} out of {total})."
- "Weekends average {weekend:,.0f} steps vs weekdays {weekday:,.0f} ({diff:+.0f}%)."
- "Your most active month was {month} with {max_avg:,.0f} average daily steps."
- "Step count has been {trend} over the past {period} (slope: {slope:+.0f} steps/month)."

**Streak Detection:**
```python
def find_streaks(daily_steps, threshold=10000):
    """Find consecutive days above threshold"""
    above = daily_steps >= threshold
    groups = above.ne(above.shift()).cumsum()
    streaks = above.groupby(groups).sum()
    streaks = streaks[streaks > 0]
    return streaks.max(), streaks.idxmax()  # longest streak and when
```

### Step Count Source Deduplication

```python
def deduplicate_steps(records_df):
    """
    Apple Health records steps from multiple sources (iPhone, Watch, 3rd-party).
    Apple's approach: the Health app already deduplicates when displaying.
    But raw export contains ALL records including overlapping.
    
    Strategy:
    1. Group by source
    2. For each time window, prefer Watch > iPhone > 3rd party
    3. Alternatively: just pick the source with the most data and use that exclusively
    """
    # Simple approach: pick one source per day
    source_priority = {
        'Apple Watch': 1,
        'iPhone': 2,
    }
    
    # Or: use Apple's approach — for each 15-minute window,
    # take the maximum value from any source
    records_df['time_bucket'] = records_df['startDate'].dt.floor('15min')
    deduped = records_df.groupby(['date', 'time_bucket'])['value'].max().reset_index()
    daily = deduped.groupby('date')['value'].sum()
    return daily
```

## Module: Workout Analysis

### Workout Frequency Analysis

```python
# Monthly workout frequency
monthly_freq = workout_df.groupby(workout_df['date'].dt.to_period('M')).size()

# Most common workout types
type_dist = workout_df['type'].value_counts()

# Preferred workout days
day_dist = workout_df['date'].dt.day_name().value_counts()
```

**Insight Templates:**
- "You've completed {total} workouts over {months} months (average {avg:.1f}/month)."
- "Your top workout types: {type1} ({n1}x), {type2} ({n2}x), {type3} ({n3}x)."
- "You exercise most on {day} and least on {day}."
- "Your workout frequency has {trend} from {old_avg:.1f}/month to {new_avg:.1f}/month."
- "Longest workout streak: {streak} consecutive days ({start} to {end})."

### Sport Evolution Timeline

```python
def sport_timeline(workout_df):
    """When did the user start each sport type"""
    first_dates = workout_df.groupby('type')['date'].min().sort_values()
    return first_dates
```

**Insight Template:**
- "You started {sport} in {month_year}, adding it to your {existing} routine."

## Module: Heart Rate

### Resting Heart Rate Analysis

```python
# RHR trend with 30-day MA
rhr_trend = rhr_df.set_index('date')['value'].resample('D').mean()
rhr_ma30 = rhr_trend.rolling(30, min_periods=15).mean()

# Current RHR (last 7-day average)
current_rhr = rhr_trend.tail(7).mean()

# 3-month trend
recent_slope = detect_trend(rhr_trend.tail(90).index, rhr_trend.tail(90).values)
```

**Insight Templates:**
- "Your current resting heart rate is {rhr:.0f} bpm ({category} range)."
- "Over the past {months} months, your RHR has {trend} from {old:.0f} to {new:.0f} bpm."
- "This {change} may be associated with {probable_cause}."

**Probable Cause Detection:**
```
RHR decreasing + Workout frequency increasing → "increased fitness from regular exercise"
RHR increasing + No workout change → "possible stress, illness, or detraining"
RHR spike + Returns to normal → "likely transient (illness, travel, poor sleep)"
```

### HRV Analysis

```python
# HRV trend
hrv_ma7 = hrv_df.set_index('date')['value'].rolling(7, min_periods=4).mean()

# Weekly pattern (HRV often dips mid-week, recovers on weekends)
hrv_by_dow = hrv_df.groupby(hrv_df['date'].dt.dayofweek)['value'].mean()
```

**Insight Templates:**
- "Your average HRV is {avg:.0f} ms (SDNN). For your age ({age}), this is {percentile}."
- "HRV tends to be lowest on {day} ({low:.0f} ms) and highest on {day} ({high:.0f} ms)."
- "Higher HRV generally indicates better recovery and lower stress."

### Heart Rate Zones (Age-Based)

```python
def hr_zones(age):
    """Calculate HR zones based on age-estimated max HR (220 - age)"""
    max_hr = 220 - age
    return {
        'Zone 1 (Recovery)': (0.50 * max_hr, 0.60 * max_hr),
        'Zone 2 (Endurance)': (0.60 * max_hr, 0.70 * max_hr),
        'Zone 3 (Tempo)': (0.70 * max_hr, 0.80 * max_hr),
        'Zone 4 (Threshold)': (0.80 * max_hr, 0.90 * max_hr),
        'Zone 5 (Maximum)': (0.90 * max_hr, max_hr),
    }
```

## Module: Sleep

### Sleep Duration Calculation

```python
def calculate_nightly_sleep(sleep_records):
    """
    Group sleep records into nightly sessions.
    
    Key challenge: Sleep records span midnight.
    Strategy: Group records by "sleep date" = the date you went to bed.
    - Records between 18:00 and 05:59+1d belong to the same night.
    - The "sleep date" is the calendar date of bedtime.
    """
    for record in sleep_records:
        bedtime = record['startDate']
        if bedtime.hour < 18:
            sleep_date = bedtime.date() - timedelta(days=1)
        else:
            sleep_date = bedtime.date()
        record['sleep_date'] = sleep_date
    
    # Group by sleep_date
    nightly = {}
    for date, group in groupby(sleep_records, key=lambda r: r['sleep_date']):
        records = list(group)
        total_inbed = sum((r['endDate'] - r['startDate']).total_seconds() 
                         for r in records if r['value'] == 'InBed') / 3600
        total_asleep = sum((r['endDate'] - r['startDate']).total_seconds() 
                          for r in records 
                          if r['value'] in ['AsleepCore', 'AsleepDeep', 'AsleepREM', 'AsleepUnspecified']) / 3600
        
        # Sleep stages
        deep = sum((r['endDate'] - r['startDate']).total_seconds() 
                   for r in records if r['value'] == 'AsleepDeep') / 3600
        rem = sum((r['endDate'] - r['startDate']).total_seconds() 
                  for r in records if r['value'] == 'AsleepREM') / 3600
        core = sum((r['endDate'] - r['startDate']).total_seconds() 
                   for r in records if r['value'] == 'AsleepCore') / 3600
        awake = sum((r['endDate'] - r['startDate']).total_seconds() 
                    for r in records if r['value'] == 'Awake') / 3600
        
        bedtime = min(r['startDate'] for r in records)
        waketime = max(r['endDate'] for r in records)
        
        efficiency = (total_asleep / total_inbed * 100) if total_inbed > 0 else 0
        
        nightly[date] = {
            'total_inbed_hrs': total_inbed,
            'total_asleep_hrs': total_asleep,
            'deep_hrs': deep,
            'rem_hrs': rem,
            'core_hrs': core,
            'awake_hrs': awake,
            'bedtime': bedtime,
            'waketime': waketime,
            'efficiency': efficiency,
        }
    return nightly
```

### Sleep Score (Composite)

```python
def sleep_score(nightly):
    """
    Composite sleep score (0-100) based on:
    - Duration (40%): 7-9 hrs optimal
    - Efficiency (20%): >85% good
    - Deep sleep ratio (20%): 15-20% of total sleep
    - Consistency (20%): Low variance in bedtime
    """
    duration_score = min(nightly['total_asleep_hrs'] / 8.0 * 100, 100) * 0.4
    efficiency_score = min(nightly['efficiency'] / 100 * 100, 100) * 0.2
    
    deep_ratio = nightly['deep_hrs'] / nightly['total_asleep_hrs'] if nightly['total_asleep_hrs'] > 0 else 0
    deep_score = min(deep_ratio / 0.20 * 100, 100) * 0.2  # 20% deep = 100 score
    
    # Consistency requires multiple nights — calculate externally
    consistency_score = 50 * 0.2  # placeholder
    
    return duration_score + efficiency_score + deep_score + consistency_score
```

**Insight Templates:**
- "You average {avg:.1f} hours of sleep per night ({relation} the recommended 7-9 hours)."
- "Your average bedtime is {bedtime} and wake time is {waketime}."
- "Sleep efficiency is {eff:.0f}% (time asleep / time in bed). Above 85% is considered good."
- "Deep sleep makes up {deep_pct:.0f}% of your total sleep ({relation} the recommended 15-20%)."
- "Your sleep is most consistent on {days} and most variable on {days}."
- "Weekend bedtime is {diff:+.0f} minutes later than weekday bedtime on average."

## Module: Menstrual Cycle

### Cycle Length Calculation

```python
def calculate_cycles(menstrual_df):
    """
    Calculate cycle lengths from menstrual flow records.
    
    A cycle starts on the first day of flow.
    Cycle length = days between two consecutive first days.
    
    Challenge: Users may not record every day of their period.
    Strategy: Identify the first day of each period by finding gaps >5 days between flow records.
    """
    flow_dates = sorted(menstrual_df['date'].unique())
    
    # Group consecutive flow days into periods
    periods = []
    current_period = [flow_dates[0]]
    
    for i in range(1, len(flow_dates)):
        gap = (flow_dates[i] - flow_dates[i-1]).days
        if gap > 5:  # New period
            periods.append({
                'start': current_period[0],
                'end': current_period[-1],
                'duration': (current_period[-1] - current_period[0]).days + 1
            })
            current_period = [flow_dates[i]]
        else:
            current_period.append(flow_dates[i])
    
    # Last period
    periods.append({
        'start': current_period[0],
        'end': current_period[-1],
        'duration': (current_period[-1] - current_period[0]).days + 1
    })
    
    # Calculate cycle lengths
    for i in range(1, len(periods)):
        periods[i]['cycle_length'] = (periods[i]['start'] - periods[i-1]['start']).days
    
    return periods
```

### Cycle Regularity Score

```python
def cycle_regularity(cycle_lengths):
    """
    Regularity score based on coefficient of variation.
    CV < 10%: Very regular
    CV 10-20%: Moderately regular  
    CV > 20%: Irregular
    """
    if len(cycle_lengths) < 3:
        return 'insufficient_data'
    
    cv = np.std(cycle_lengths) / np.mean(cycle_lengths) * 100
    
    if cv < 10:
        return 'very_regular', cv
    elif cv < 20:
        return 'moderate', cv
    else:
        return 'irregular', cv
```

### Cycle Phase Estimation (for correlation analysis)

```python
def estimate_cycle_phases(periods, reference_date):
    """
    Estimate which cycle phase a given date falls in.
    Approximation (actual varies per individual):
    - Menstrual: Days 1-5
    - Follicular: Days 6-13
    - Ovulation: Days 14-16
    - Luteal: Days 17-28
    """
    for i, period in enumerate(periods):
        cycle_start = period['start']
        cycle_length = period.get('cycle_length', 28)
        
        day_in_cycle = (reference_date - cycle_start).days + 1
        
        if 1 <= day_in_cycle <= 5:
            return 'menstrual'
        elif 6 <= day_in_cycle <= 13:
            return 'follicular'
        elif 14 <= day_in_cycle <= 16:
            return 'ovulation'
        elif 17 <= day_in_cycle <= cycle_length:
            return 'luteal'
    
    return 'unknown'
```

**Insight Templates:**
- "Your average cycle length is {avg:.0f} days (typical range: 21-35 days)."
- "Cycle regularity: {regularity} (CV = {cv:.1f}%). {interpretation}."
- "Average period duration: {dur:.1f} days."
- "Cycle length has {trend} over the tracked period."
- **If correlation data available:**
  - "Resting HR is {diff:+.1f} bpm higher in the luteal phase compared to follicular."
  - "HRV drops by {diff:.0f} ms during the luteal phase, consistent with higher sympathetic activity."
  - "Wrist temperature rises {diff:+.2f}°C after estimated ovulation, consistent with progesterone effects."

## Module: Body Composition

### Weight Trend Analysis

```python
def weight_analysis(weight_df):
    """
    Handle sparse weight data gracefully.
    Don't interpolate — show actual data points with trend line.
    """
    # Rate of change
    if len(weight_df) >= 2:
        total_change = weight_df['value'].iloc[-1] - weight_df['value'].iloc[0]
        days = (weight_df['date'].iloc[-1] - weight_df['date'].iloc[0]).days
        weekly_change = total_change / (days / 7) if days > 0 else 0
    
    return {
        'current': weight_df['value'].iloc[-1],
        'min': weight_df['value'].min(),
        'max': weight_df['value'].max(),
        'total_change': total_change,
        'weekly_rate': weekly_change,
    }
```

**Insight Templates:**
- "Current weight: {current:.1f} kg (BMI: {bmi:.1f})."
- "Weight has changed {change:+.1f} kg over {period} ({rate:+.2f} kg/week)."
- "Weight was recorded {count} times over {months} months. More frequent tracking would improve trend accuracy."

## Special Period Handling Templates

### Pregnancy Period

```python
PREGNANCY_EXPECTED_CHANGES = {
    'resting_hr': 'Increase of 10-20 bpm by third trimester is normal',
    'hrv': 'May decrease due to increased sympathetic activity',
    'sleep': 'Duration may increase in first trimester, decrease in third',
    'steps': 'Gradual decrease in activity is common',
    'weight': 'Expected gain of 11-16 kg total (BMI-dependent)',
    'menstrual': 'Absent during pregnancy',
}
```

### Illness/Surgery Recovery

```python
RECOVERY_MARKERS = {
    'resting_hr': 'Elevated during illness, gradual return to baseline indicates recovery',
    'hrv': 'Depressed during illness, recovery tracked by return to pre-illness levels',
    'steps': 'Reduced activity during recovery, track return to baseline',
    'sleep': 'May see increased sleep need during recovery',
}
```

## Dashboard Layout Template

```
┌─────────────────────────────────────────────────────────┐
│                    HEALTH DASHBOARD                      │
│              [Date Range: YYYY-MM-DD to YYYY-MM-DD]     │
├─────────┬─────────┬─────────┬──────────┬────────────────┤
│ Avg Steps│ Avg Sleep│ Avg RHR │ Workouts │ Avg Cycle Len │
│  8,234   │  7.2 hrs │ 65 bpm │  12/mo   │   28 days     │
├──────────┴─────────┴─────────┴──────────┴────────────────┤
│ [Tab: Activity] [Tab: Heart] [Tab: Sleep] [Tab: More]   │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  [Main Chart Area — responsive, interactive Plotly]      │
│                                                          │
├─────────────────────────────────────────────────────────┤
│                    KEY INSIGHTS                          │
│  • Insight 1 with supporting data                       │
│  • Insight 2 with supporting data                       │
│  • Insight 3 with supporting data                       │
├─────────────────────────────────────────────────────────┤
│               RECOMMENDATIONS                            │
│  Based on your goal: [User Goal]                        │
│  1. Specific recommendation with reasoning              │
│  2. Specific recommendation with reasoning              │
│  3. Specific recommendation with reasoning              │
├─────────────────────────────────────────────────────────┤
│ ⚠️ This is not medical advice.                          │
└─────────────────────────────────────────────────────────┘
```
