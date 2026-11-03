#!/usr/bin/env python3
"""
Apple Health Interactive Dashboard Generator

Reads parsed CSV data and generates a self-contained interactive HTML dashboard
using Plotly.

Usage:
  python3 generate_dashboard.py \
    --data-dir ./health_data/ \
    --output ./health_dashboard.html \
    --modules activity,heartrate,sleep,workout,menstrual,body \
    --special-periods '[{"name":"Pregnancy","start":"YYYY-MM-DD","end":"YYYY-MM-DD"}]'
"""

import csv
import json
import os
import sys
import argparse
import math
import statistics
import traceback
from datetime import datetime, timedelta
from collections import defaultdict

__version__ = '2.1.0'

try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    import plotly.express as px
except ImportError:
    print("Error: plotly is required. Install with: pip install plotly")
    sys.exit(1)

# ============================================================
# Color Palette — Apple Health inspired
# ============================================================
COLORS = {
    'blue': '#007AFF',
    'orange': '#FF9500',
    'green': '#34C759',
    'red': '#FF3B30',
    'purple': '#AF52DE',
    'teal': '#5AC8FA',
    'pink': '#FF2D55',
    'yellow': '#FFCC00',
    'indigo': '#5856D6',
    'gray': '#8E8E93',
    'bg': '#FAFAFA',
    'card_bg': '#FFFFFF',
    'grid': '#E5E5EA',
    'text': '#1C1C1E',
    'text_secondary': '#8E8E93',
}

CHART_COLORS = [COLORS['blue'], COLORS['orange'], COLORS['green'], COLORS['red'],
                COLORS['purple'], COLORS['teal'], COLORS['pink'], COLORS['yellow'],
                COLORS['indigo'], COLORS['gray']]


def read_csv_safe(filepath):
    """Read CSV file, return empty list if not found."""
    if not os.path.exists(filepath):
        return []
    with open(filepath, 'r') as f:
        reader = csv.DictReader(f)
        return list(reader)


def safe_float(val, default=0.0):
    """Convert to float safely."""
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def moving_avg(values, window=7):
    """Simple moving average."""
    result = []
    for i in range(len(values)):
        start = max(0, i - window + 1)
        chunk = [v for v in values[start:i+1] if v is not None]
        result.append(sum(chunk) / len(chunk) if chunk else None)
    return result


def adaptive_xaxis(dates):
    """
    Determine optimal xaxis tick configuration based on the time span of data.
    
    Returns a dict of Plotly xaxis layout properties that ensures readable,
    non-overlapping date labels regardless of data density or time range.
    
    Rules:
        < 3 months   → every month,     format '%Y-%m-%d' (show day)
        3–12 months  → every 1–2 months, format '%Y-%m'
        1–3 years    → every 3 months,   format '%Y-%m'
        3–5 years    → every 6 months,   format '%Y-%m'
        > 5 years    → every 12 months,  format '%Y'
    """
    if not dates or len(dates) < 2:
        return {}
    
    try:
        # Parse first and last dates (handles 'YYYY-MM-DD' or 'YYYY-MM' or datetime objects)
        d_first = dates[0] if isinstance(dates[0], datetime) else datetime.strptime(str(dates[0])[:10], '%Y-%m-%d')
        d_last = dates[-1] if isinstance(dates[-1], datetime) else datetime.strptime(str(dates[-1])[:10], '%Y-%m-%d')
    except (ValueError, TypeError):
        return {}
    
    span_days = (d_last - d_first).days
    
    if span_days < 90:  # < 3 months
        return {'tickformat': '%m-%d', 'dtick': 'M1', 'tickangle': -30, 'tickfont': {'size': 11}}
    elif span_days < 365:  # 3–12 months
        return {'tickformat': '%Y-%m', 'dtick': 'M1', 'tickangle': -30, 'tickfont': {'size': 11}}
    elif span_days < 365 * 3:  # 1–3 years
        return {'tickformat': '%Y-%m', 'dtick': 'M3', 'tickangle': -30, 'tickfont': {'size': 11}}
    elif span_days < 365 * 5:  # 3–5 years
        return {'tickformat': '%Y-%m', 'dtick': 'M6', 'tickangle': -30, 'tickfont': {'size': 11}}
    else:  # > 5 years
        return {'tickformat': '%Y', 'dtick': 'M12', 'tickangle': 0, 'tickfont': {'size': 11}}


def adaptive_category_xaxis(labels):
    """
    Determine optimal tick spacing for category axes (e.g. monthly aggregation).
    Ensures labels don't overlap by selecting an appropriate dtick.
    
    Args:
        labels: list of category labels (e.g. ['2023-01', '2023-02', ...])
    Returns:
        dict of Plotly xaxis layout properties
    """
    n = len(labels) if labels else 0
    if n <= 12:
        dtick = 1
    elif n <= 24:
        dtick = 2
    elif n <= 48:
        dtick = 3
    elif n <= 72:
        dtick = 6
    else:
        dtick = 12
    return {'type': 'category', 'dtick': dtick, 'tickangle': -30, 'tickfont': {'size': 11}}


# ============================================================
# Module Generators — Each returns a list of Plotly figures
# ============================================================

def generate_activity_module(data_dir, special_periods=None):
    """Generate activity/steps charts."""
    figures = []
    insights = []
    
    # Step count
    steps_data = read_csv_safe(os.path.join(data_dir, 'stepcount_daily.csv'))
    if steps_data:
        dates = [r['date'] for r in steps_data]
        daily_sums = [safe_float(r['sum']) for r in steps_data]
        ma7 = moving_avg(daily_sums, 7)
        ma30 = moving_avg(daily_sums, 30)
        
        fig = go.Figure()
        fig.add_trace(go.Bar(x=dates, y=daily_sums, name='Daily Steps',
                            marker_color=COLORS['blue'], opacity=0.3))
        fig.add_trace(go.Scatter(x=dates, y=ma7, name='7-day Avg',
                                line=dict(color=COLORS['orange'], width=2)))
        fig.add_trace(go.Scatter(x=dates, y=ma30, name='30-day Avg',
                                line=dict(color=COLORS['red'], width=2.5)))
        
        # Reference line at 10,000
        fig.add_hline(y=10000, line_dash="dash", line_color=COLORS['green'],
                     annotation_text="10,000 steps goal")
        
        _add_special_period_markers(fig, special_periods)
        
        fig.update_layout(
            title='Daily Step Count',
            xaxis_title='Date', yaxis_title='Steps',
            template='plotly_white',
            height=400,
            xaxis=adaptive_xaxis(dates),
        )
        figures.append(('Steps Trend', fig))
        
        # Calculate insights
        avg_steps = sum(daily_sums) / len(daily_sums)
        days_10k = sum(1 for s in daily_sums if s >= 10000)
        insights.append(f"Average daily steps: {avg_steps:,.0f}")
        insights.append(f"Days reaching 10K+: {days_10k}/{len(daily_sums)} ({days_10k/len(daily_sums)*100:.0f}%)")
        
        # Recent 30-day stats (relative to last data date, NOT datetime.now())
        _, recent_vals = recent_n_days(dates, daily_sums, 30)
        if recent_vals:
            recent_avg = sum(recent_vals) / len(recent_vals)
            insights.append(f"Recent 30-day avg steps: {recent_avg:,.0f}")
    
    # Flights climbed
    flights_data = read_csv_safe(os.path.join(data_dir, 'flightsclimbed_daily.csv'))
    if flights_data:
        dates = [r['date'] for r in flights_data]
        daily_sums = [safe_float(r['sum']) for r in flights_data]
        ma30 = moving_avg(daily_sums, 30)
        
        fig = go.Figure()
        fig.add_trace(go.Bar(x=dates, y=daily_sums, name='Daily Flights',
                            marker_color=COLORS['green'], opacity=0.4))
        fig.add_trace(go.Scatter(x=dates, y=ma30, name='30-day Avg',
                                line=dict(color=COLORS['green'], width=2.5)))
        fig.update_layout(
            title='Flights Climbed', xaxis_title='Date', yaxis_title='Flights',
            template='plotly_white', height=300,
            xaxis=adaptive_xaxis(dates),
        )
        figures.append(('Flights Climbed', fig))
    
    return figures, insights


def generate_heartrate_module(data_dir, special_periods=None):
    """Generate heart rate charts."""
    figures = []
    insights = []
    
    # Resting Heart Rate
    rhr_data = read_csv_safe(os.path.join(data_dir, 'restingheartrate.csv'))
    if rhr_data:
        dates = [r['date'] for r in rhr_data]
        values = [safe_float(r['value']) for r in rhr_data]
        ma30 = moving_avg(values, 30)
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=dates, y=values, name='Daily RHR', mode='markers',
                                marker=dict(color=COLORS['red'], size=4, opacity=0.5)))
        fig.add_trace(go.Scatter(x=dates, y=ma30, name='30-day Avg',
                                line=dict(color=COLORS['red'], width=3)))
        
        # Reference bands
        fig.add_hrect(y0=60, y1=100, fillcolor=COLORS['green'], opacity=0.05,
                     line_width=0, annotation_text="Normal range")
        
        _add_special_period_markers(fig, special_periods)
        
        fig.update_layout(
            title='Resting Heart Rate Trend',
            xaxis_title='Date', yaxis_title='BPM',
            template='plotly_white', height=400,
            xaxis=adaptive_xaxis(dates),
        )
        figures.append(('Resting Heart Rate', fig))
        
        if values:
            avg_rhr = sum(values) / len(values)
            # Use recent_n_days for consistency with other modules (review issue #3)
            _, recent_vals = recent_n_days(dates, values, 7)
            recent_rhr = sum(recent_vals) / len(recent_vals) if recent_vals else avg_rhr
            insights.append(f"Average resting HR: {avg_rhr:.0f} bpm")
            insights.append(f"Current (7-day avg): {recent_rhr:.0f} bpm")
    
    # HRV
    hrv_data = read_csv_safe(os.path.join(data_dir, 'hrv.csv'))
    if hrv_data:
        dates = [r['date'] for r in hrv_data]
        values = [safe_float(r['value']) for r in hrv_data]
        ma7 = moving_avg(values, 7)
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=dates, y=values, name='Daily HRV', mode='markers',
                                marker=dict(color=COLORS['purple'], size=4, opacity=0.5)))
        fig.add_trace(go.Scatter(x=dates, y=ma7, name='7-day Avg',
                                line=dict(color=COLORS['purple'], width=3)))
        
        _add_special_period_markers(fig, special_periods)
        
        fig.update_layout(
            title='Heart Rate Variability (SDNN)',
            xaxis_title='Date', yaxis_title='ms',
            template='plotly_white', height=400,
            xaxis=adaptive_xaxis(dates),
        )
        figures.append(('HRV Trend', fig))
        
        if values:
            avg_hrv = sum(values) / len(values)
            insights.append(f"Average HRV: {avg_hrv:.0f} ms SDNN")
    
    # Daily heart rate range
    hr_daily = read_csv_safe(os.path.join(data_dir, 'heartrate_daily.csv'))
    if hr_daily:
        dates = [r['date'] for r in hr_daily]
        mins = [safe_float(r['min']) for r in hr_daily]
        maxs = [safe_float(r['max']) for r in hr_daily]
        means = [safe_float(r['mean']) for r in hr_daily]
        
        fig = go.Figure()
        # Min-max range band
        fig.add_trace(go.Scatter(
            x=dates + dates[::-1],
            y=maxs + mins[::-1],
            fill='toself', fillcolor=f'rgba(255,59,48,0.1)',
            line=dict(color='rgba(255,255,255,0)'),
            name='Daily Range'
        ))
        fig.add_trace(go.Scatter(x=dates, y=means, name='Daily Mean HR',
                                line=dict(color=COLORS['red'], width=1.5)))
        
        fig.update_layout(
            title='Daily Heart Rate Range',
            xaxis_title='Date', yaxis_title='BPM',
            template='plotly_white', height=350,
            xaxis=adaptive_xaxis(dates),
        )
        figures.append(('Heart Rate Range', fig))
    
    # VO2Max
    vo2_data = read_csv_safe(os.path.join(data_dir, 'vo2max.csv'))
    if vo2_data:
        dates = [r['date'] for r in vo2_data]
        values = [safe_float(r['value']) for r in vo2_data]
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=dates, y=values, name='VO2 Max',
                                mode='lines+markers',
                                line=dict(color=COLORS['teal'], width=3),
                                marker=dict(size=8)))
        fig.update_layout(
            title='VO2 Max (Cardio Fitness)',
            xaxis_title='Date', yaxis_title='mL/min·kg',
            template='plotly_white', height=300,
            xaxis=adaptive_xaxis(dates),
        )
        figures.append(('VO2 Max', fig))
    
    return figures, insights


def generate_sleep_module(data_dir, special_periods=None):
    """Generate sleep analysis charts."""
    figures = []
    insights = []
    
    sleep_data = read_csv_safe(os.path.join(data_dir, 'sleep_analysis.csv'))
    if not sleep_data:
        return figures, insights
    
    # Calculate nightly sleep
    nightly = _calculate_nightly_sleep(sleep_data)
    if not nightly:
        return figures, insights
    
    dates = sorted(nightly.keys())
    durations = [nightly[d]['total_asleep_hrs'] for d in dates]
    ma7 = moving_avg(durations, 7)
    
    # Sleep duration trend
    fig = go.Figure()
    fig.add_trace(go.Bar(x=dates, y=durations, name='Nightly Sleep',
                        marker_color=COLORS['indigo'], opacity=0.3))
    fig.add_trace(go.Scatter(x=dates, y=ma7, name='7-day Avg',
                            line=dict(color=COLORS['indigo'], width=2.5)))
    fig.add_hline(y=7, line_dash="dash", line_color=COLORS['green'],
                 annotation_text="7 hours recommended")
    fig.add_hline(y=9, line_dash="dash", line_color=COLORS['orange'],
                 annotation_text="9 hours upper")
    
    _add_special_period_markers(fig, special_periods)
    
    fig.update_layout(
        title='Nightly Sleep Duration',
        xaxis_title='Date', yaxis_title='Hours',
        template='plotly_white', height=400,
        xaxis=adaptive_xaxis(dates),
    )
    figures.append(('Sleep Duration', fig))
    
    # Sleep stages stacked (if available)
    has_stages = any(nightly[d].get('deep_hrs', 0) > 0 for d in dates)
    if has_stages:
        deep = [nightly[d].get('deep_hrs', 0) for d in dates]
        core = [nightly[d].get('core_hrs', 0) for d in dates]
        rem = [nightly[d].get('rem_hrs', 0) for d in dates]
        awake = [nightly[d].get('awake_hrs', 0) for d in dates]
        
        fig = go.Figure()
        fig.add_trace(go.Bar(x=dates, y=deep, name='Deep', marker_color='#1C3D5A'))
        fig.add_trace(go.Bar(x=dates, y=core, name='Core', marker_color='#5B7FB1'))
        fig.add_trace(go.Bar(x=dates, y=rem, name='REM', marker_color='#8AB8E8'))
        fig.add_trace(go.Bar(x=dates, y=awake, name='Awake', marker_color='#FFB347'))
        
        fig.update_layout(
            barmode='stack',
            title='Sleep Stages',
            xaxis_title='Date', yaxis_title='Hours',
            template='plotly_white', height=400,
            xaxis=adaptive_xaxis(dates),
        )
        figures.append(('Sleep Stages', fig))
    
    # Insights
    if durations:
        avg_sleep = sum(durations) / len(durations)
        below_7 = sum(1 for d in durations if d < 7)
        insights.append(f"Average sleep: {avg_sleep:.1f} hours/night")
        insights.append(f"Nights below 7 hours: {below_7}/{len(durations)} ({below_7/len(durations)*100:.0f}%)")
        
        # Recent 30-day stats (relative to last data date, NOT datetime.now())
        _, recent_vals = recent_n_days(dates, durations, 30)
        if recent_vals:
            recent_avg = sum(recent_vals) / len(recent_vals)
            insights.append(f"Recent 30-day avg: {recent_avg:.1f} hours/night")
    
    return figures, insights


def generate_workout_module(data_dir, special_periods=None):
    """Generate workout analysis charts."""
    figures = []
    insights = []
    
    workout_data = read_csv_safe(os.path.join(data_dir, 'workouts.csv'))
    if not workout_data:
        return figures, insights
    
    # Workout type distribution
    type_counts = defaultdict(int)
    for w in workout_data:
        wtype = w.get('type', 'Unknown')
        # Clean up type names
        wtype = wtype.replace('HKWorkoutActivityType', '')
        type_counts[wtype] += 1
    
    sorted_types = sorted(type_counts.items(), key=lambda x: -x[1])
    
    fig = go.Figure(go.Pie(
        labels=[t[0] for t in sorted_types],
        values=[t[1] for t in sorted_types],
        hole=0.4,
        marker_colors=CHART_COLORS[:len(sorted_types)],
    ))
    fig.update_layout(title=f'Workout Types ({len(workout_data)} total)', height=400)
    figures.append(('Workout Types', fig))
    
    # Monthly workout frequency
    monthly_counts = defaultdict(int)
    for w in workout_data:
        month = w.get('date', '')[:7]
        if month:
            monthly_counts[month] += 1
    
    months = sorted(monthly_counts.keys())
    counts = [monthly_counts[m] for m in months]
    
    fig = go.Figure()
    fig.add_trace(go.Bar(x=months, y=counts, marker_color=COLORS['orange']))
    fig.update_layout(
        title='Monthly Workout Frequency',
        xaxis_title='Month', yaxis_title='Workouts',
        template='plotly_white', height=350,
        xaxis=adaptive_category_xaxis(months),
    )
    figures.append(('Workout Frequency', fig))
    
    # Insights
    total = len(workout_data)
    if months:
        months_span = len(months)
        avg_monthly = total / months_span
        insights.append(f"Total workouts: {total}")
        insights.append(f"Average: {avg_monthly:.1f} workouts/month")
        insights.append(f"Top type: {sorted_types[0][0]} ({sorted_types[0][1]} sessions)")
    
    return figures, insights


def generate_menstrual_module(data_dir, special_periods=None):
    """Generate menstrual cycle analysis charts."""
    figures = []
    insights = []
    
    menstrual_data = read_csv_safe(os.path.join(data_dir, 'menstrualflow.csv'))
    if not menstrual_data:
        return figures, insights
    
    # Calculate cycles
    flow_dates = sorted(set(r['date'] for r in menstrual_data))
    
    if len(flow_dates) < 2:
        return figures, insights
    
    # Group into periods
    periods = []
    current = [flow_dates[0]]
    for i in range(1, len(flow_dates)):
        d1 = datetime.strptime(flow_dates[i-1], '%Y-%m-%d')
        d2 = datetime.strptime(flow_dates[i], '%Y-%m-%d')
        gap = (d2 - d1).days
        if gap > 5:
            periods.append(current)
            current = [flow_dates[i]]
        else:
            current.append(flow_dates[i])
    periods.append(current)
    
    # Calculate cycle lengths
    cycle_starts = [p[0] for p in periods]
    cycle_lengths = []
    for i in range(1, len(cycle_starts)):
        d1 = datetime.strptime(cycle_starts[i-1], '%Y-%m-%d')
        d2 = datetime.strptime(cycle_starts[i], '%Y-%m-%d')
        length = (d2 - d1).days
        if 15 <= length <= 60:  # Filter unreasonable values
            cycle_lengths.append({'start': cycle_starts[i-1], 'length': length})
    
    if cycle_lengths:
        start_dates = [c['start'] for c in cycle_lengths]
        lengths = [c['length'] for c in cycle_lengths]
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=start_dates, y=lengths, mode='lines+markers',
            line=dict(color=COLORS['pink'], width=2),
            marker=dict(size=8, color=COLORS['pink']),
        ))
        fig.add_hline(y=28, line_dash="dash", line_color=COLORS['gray'],
                     annotation_text="28-day reference")
        
        _add_special_period_markers(fig, special_periods)
        
        fig.update_layout(
            title='Menstrual Cycle Length',
            xaxis_title='Cycle Start Date', yaxis_title='Days',
            template='plotly_white', height=350,
            xaxis=adaptive_xaxis(start_dates),
        )
        figures.append(('Cycle Length', fig))
        
        # Period duration
        period_durations = [len(p) for p in periods]
        avg_period = sum(period_durations) / len(period_durations)
        avg_cycle = sum(lengths) / len(lengths)
        
        cv = (statistics.stdev(lengths) / avg_cycle * 100) if len(lengths) > 2 else 0
        regularity = 'Very regular' if cv < 10 else ('Moderate' if cv < 20 else 'Irregular')
        
        insights.append(f"Average cycle length: {avg_cycle:.0f} days")
        insights.append(f"Cycle regularity: {regularity} (CV={cv:.1f}%)")
        insights.append(f"Average period duration: {avg_period:.1f} days")
        insights.append(f"Total cycles tracked: {len(cycle_lengths)}")
    
    return figures, insights


def generate_body_module(data_dir, special_periods=None):
    """Generate body composition charts."""
    figures = []
    insights = []
    
    weight_data = read_csv_safe(os.path.join(data_dir, 'bodymass.csv'))
    if weight_data:
        dates = [r['date'] for r in weight_data]
        values = [safe_float(r['value']) for r in weight_data]
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=dates, y=values, mode='lines+markers',
            line=dict(color=COLORS['blue'], width=2),
            marker=dict(size=6),
            name='Weight',
        ))
        
        _add_special_period_markers(fig, special_periods)
        
        fig.update_layout(
            title='Weight Trend',
            xaxis_title='Date', yaxis_title='kg',
            template='plotly_white', height=350,
            xaxis=adaptive_xaxis(dates),
        )
        figures.append(('Weight', fig))
        
        if values:
            current = values[-1]
            change = values[-1] - values[0]
            insights.append(f"Current weight: {current:.1f} kg")
            insights.append(f"Total change: {change:+.1f} kg over {len(values)} measurements")
    
    # Body fat
    bf_data = read_csv_safe(os.path.join(data_dir, 'bodyfat.csv'))
    if bf_data:
        dates = [r['date'] for r in bf_data]
        raw_values = [safe_float(r['value']) for r in bf_data]
        # Smart detection: Apple Health BodyFatPercentage may be 0-1 (fraction)
        # or 0-100 (already percentage), depending on the data source device.
        # If max value <= 1, assume fraction and convert; otherwise already percentage.
        if raw_values and max(raw_values) <= 1.0:
            values = [v * 100 for v in raw_values]
        else:
            values = raw_values
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=dates, y=values, mode='lines+markers',
            line=dict(color=COLORS['teal'], width=2),
            marker=dict(size=6),
            name='Body Fat %',
        ))
        fig.update_layout(
            title='Body Fat Percentage Trend',
            xaxis_title='Date', yaxis_title='%',
            template='plotly_white', height=300,
            xaxis=adaptive_xaxis(dates),
        )
        figures.append(('Body Fat', fig))
    
    return figures, insights


# ============================================================
# Helper Functions
# ============================================================

def _add_special_period_markers(fig, special_periods):
    """Add shaded regions for special periods (pregnancy, illness, etc.)"""
    if not special_periods:
        return
    
    period_colors = {
        'Pregnancy': 'rgba(255,45,85,0.1)',
        'Illness': 'rgba(255,149,0,0.1)',
        'Recovery': 'rgba(52,199,89,0.1)',
        'default': 'rgba(88,86,214,0.1)',
    }
    
    for period in special_periods:
        color = period_colors.get(period.get('name', ''), period_colors['default'])
        fig.add_vrect(
            x0=period['start'], x1=period['end'],
            fillcolor=color, line_width=0,
            annotation_text=period.get('name', ''),
            annotation_position="top left",
            annotation_font_size=10,
        )


def _calculate_nightly_sleep(sleep_records):
    """
    Group sleep records into nightly sessions with multi-source deduplication.
    
    Design principles (general, not user-specific):
    - Night date attribution: records starting before 18:00 belong to previous night
    - Source deduplication: when multiple sources exist for the same night,
      pick the richest one (most sleep stage detail) to avoid double-counting
    - Source normalization: handle Unicode whitespace variants in sourceName
    - Reasonable bounds: filter out nights with < 1h or > 18h total sleep
    """
    import unicodedata
    
    # Step 1: Group records by (sleep_date, source)
    # {sleep_date: {source: [records]}}
    by_date_source = defaultdict(lambda: defaultdict(list))
    
    for rec in sleep_records:
        start_str = rec.get('startDate', '')
        end_str = rec.get('endDate', '')
        value = rec.get('value', '')
        source = rec.get('sourceName', '')
        
        # Normalize source name for consistent matching
        if source:
            source = unicodedata.normalize('NFKC', source)
            source = ' '.join(source.split())
        
        start_dt = parse_datetime(start_str)
        end_dt = parse_datetime(end_str)
        
        if not start_dt or not end_dt:
            continue
        
        # Determine sleep date (the night you went to bed)
        if start_dt.hour < 18:
            sleep_date = (start_dt - timedelta(days=1)).strftime('%Y-%m-%d')
        else:
            sleep_date = start_dt.strftime('%Y-%m-%d')
        
        hours = (end_dt - start_dt).total_seconds() / 3600
        if hours <= 0 or hours > 24:
            continue
        
        by_date_source[sleep_date][source].append({
            'value': value,
            'hours': hours,
        })
    
    # Step 2: For each night, pick the best source then aggregate
    nightly = {}
    
    for sleep_date, sources_data in by_date_source.items():
        if len(sources_data) == 1:
            # Only one source — use it directly
            best_source = next(iter(sources_data.keys()))
            records = sources_data[best_source]
        else:
            # Multiple sources — pick the richest one (most sleep stage detail)
            def _source_quality(source_records):
                """Score a source by data quality: detailed stages > basic > none."""
                has_stages = any(
                    any(stage in r['value'] for stage in ['AsleepDeep', 'AsleepREM', 'AsleepCore'])
                    for r in source_records
                )
                total_sleep = sum(
                    r['hours'] for r in source_records
                    if 'Asleep' in r['value']
                )
                # Score: stage data is primary, total sleep time is tiebreaker
                return (1 if has_stages else 0, total_sleep)
            
            best_source = max(
                sources_data.keys(),
                key=lambda src: _source_quality(sources_data[src])
            )
            records = sources_data[best_source]
        
        # Aggregate the winning source's records
        entry = {
            'total_inbed_hrs': 0, 'total_asleep_hrs': 0,
            'deep_hrs': 0, 'rem_hrs': 0, 'core_hrs': 0, 'awake_hrs': 0,
        }
        
        for r in records:
            value = r['value']
            hours = r['hours']
            if 'InBed' in value:
                entry['total_inbed_hrs'] += hours
            elif 'AsleepDeep' in value:
                entry['total_asleep_hrs'] += hours
                entry['deep_hrs'] += hours
            elif 'AsleepREM' in value:
                entry['total_asleep_hrs'] += hours
                entry['rem_hrs'] += hours
            elif 'AsleepCore' in value:
                entry['total_asleep_hrs'] += hours
                entry['core_hrs'] += hours
            elif 'AsleepUnspecified' in value or 'Asleep' in value:
                entry['total_asleep_hrs'] += hours
            elif 'Awake' in value:
                entry['awake_hrs'] += hours
        
        # Filter unreasonable nights
        if 1 < entry['total_asleep_hrs'] < 18:
            entry['has_stages'] = entry['deep_hrs'] > 0 or entry['rem_hrs'] > 0 or entry['core_hrs'] > 0
            entry['source'] = best_source
            nightly[sleep_date] = entry
    
    return nightly


def recent_n_days(sorted_dates, values, n=30):
    """
    Get the most recent N days of data, using the LAST date in the data
    as the reference point (not datetime.now()).
    
    This is critical for correctness because:
    - Users may export data days/weeks before running analysis
    - The script may be re-run on old exports
    - Using datetime.now() as reference would yield empty results for old data
    
    Args:
        sorted_dates: list of date strings in 'YYYY-MM-DD' format, sorted ascending
        values: list of corresponding values
        n: number of days to look back (default 30)
    
    Returns:
        (recent_dates, recent_values) tuple
    """
    if not sorted_dates:
        return [], []
    
    last_date = datetime.strptime(str(sorted_dates[-1])[:10], '%Y-%m-%d')
    cutoff = last_date - timedelta(days=n)
    cutoff_str = cutoff.strftime('%Y-%m-%d')
    
    recent_dates = []
    recent_values = []
    for d, v in zip(sorted_dates, values):
        if str(d)[:10] >= cutoff_str:
            recent_dates.append(d)
            recent_values.append(v)
    return recent_dates, recent_values


def parse_datetime(dt_str):
    """Parse datetime string from Apple Health format."""
    if not dt_str:
        return None
    try:
        return datetime.strptime(dt_str[:19], '%Y-%m-%d %H:%M:%S')
    except (ValueError, IndexError):
        return None


# ============================================================
# Dashboard Assembly
# ============================================================

def generate_dashboard(data_dir, output_path, modules, special_periods=None):
    """Generate the full interactive HTML dashboard."""
    
    MODULE_GENERATORS = {
        'activity': generate_activity_module,
        'heartrate': generate_heartrate_module,
        'sleep': generate_sleep_module,
        'workout': generate_workout_module,
        'menstrual': generate_menstrual_module,
        'body': generate_body_module,
    }
    
    all_figures = []
    all_insights = []
    
    for module in modules:
        generator = MODULE_GENERATORS.get(module)
        if not generator:
            print(f"Warning: Unknown module '{module}', skipping.")
            continue
        
        print(f"Generating {module} module...")
        try:
            figs, insights = generator(data_dir, special_periods)
            all_figures.extend(figs)
            all_insights.extend(insights)
        except Exception as e:
            print(f"  Error in {module}: {e}")
            traceback.print_exc()
    
    if not all_figures:
        print("No data to visualize. Check your data directory.")
        return
    
    # Detect data date range from all CSV files in data_dir
    data_min_date, data_max_date = _detect_data_range(data_dir)
    
    # Build the HTML — embed Plotly JS for true offline support
    html_parts = [_dashboard_header(data_min_date, data_max_date)]
    
    # KPI cards
    html_parts.append(_kpi_section(all_insights[:6]))
    
    # Charts — first chart includes full Plotly JS, rest skip it
    for i, (title, fig) in enumerate(all_figures):
        fig.update_layout(margin=dict(l=40, r=40, t=60, b=40))
        html_parts.append(f'<div class="chart-container">')
        # Embed Plotly JS in the first chart div only (include_plotlyjs=True),
        # subsequent charts skip it (include_plotlyjs=False)
        html_parts.append(fig.to_html(
            full_html=False,
            include_plotlyjs=True if i == 0 else False,
        ))
        html_parts.append('</div>')
    
    # Insights section
    if all_insights:
        html_parts.append('<div class="insights-section">')
        html_parts.append('<h2>Key Insights</h2>')
        html_parts.append('<ul>')
        for insight in all_insights:
            html_parts.append(f'<li>{insight}</li>')
        html_parts.append('</ul>')
        html_parts.append('</div>')
    
    # Disclaimer
    html_parts.append(_disclaimer_section())
    html_parts.append(_dashboard_footer())
    
    # Write output
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(html_parts))
    
    print(f"\nDashboard saved to: {output_path}")
    print(f"Charts generated: {len(all_figures)}")
    print(f"Insights: {len(all_insights)}")


def _detect_data_range(data_dir):
    """Scan all CSV files in data_dir to find the overall min/max date."""
    min_date = None
    max_date = None
    
    if not os.path.isdir(data_dir):
        return None, None
    
    # Date field candidates: 'date' is the primary field for most CSVs,
    # but sleep_analysis.csv uses 'startDate' / 'endDate' instead.
    DATE_FIELDS = ['date', 'startDate', 'endDate']
    
    for fname in os.listdir(data_dir):
        if not fname.endswith('.csv'):
            continue
        fpath = os.path.join(data_dir, fname)
        try:
            with open(fpath, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    for field in DATE_FIELDS:
                        d = row.get(field, '')[:10]
                        if not d or len(d) < 10:
                            continue
                        # Quick sanity check: must look like YYYY-MM-DD
                        if d[4] != '-' or d[7] != '-':
                            continue
                        if min_date is None or d < min_date:
                            min_date = d
                        if max_date is None or d > max_date:
                            max_date = d
        except Exception:
            continue
    
    return min_date, max_date


def _dashboard_header(data_min_date=None, data_max_date=None):
    date_range_text = ''
    if data_min_date and data_max_date:
        date_range_text = f'Data Range: {data_min_date} to {data_max_date}'
    elif data_max_date:
        date_range_text = f'Data through {data_max_date}'
    
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Apple Health Dashboard</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #F2F2F7;
    color: #1C1C1E;
    line-height: 1.6;
}}
.header {{
    background: linear-gradient(135deg, #007AFF, #5856D6);
    color: white;
    padding: 2rem;
    text-align: center;
}}
.header h1 {{ font-size: 2rem; font-weight: 700; }}
.header p {{ opacity: 0.8; margin-top: 0.5rem; }}
.header .date-range {{ opacity: 0.7; margin-top: 0.3rem; font-size: 0.9rem; }}
.container {{ max-width: 1200px; margin: 0 auto; padding: 1rem; }}
.kpi-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 1rem;
    margin: 1.5rem 0;
}}
.kpi-card {{
    background: white;
    border-radius: 12px;
    padding: 1.2rem;
    text-align: center;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}}
.kpi-card .label {{ font-size: 0.8rem; color: #8E8E93; text-transform: uppercase; }}
.kpi-card .value {{ font-size: 1.4rem; font-weight: 700; color: #1C1C1E; margin: 0.3rem 0; }}
.chart-container {{
    background: white;
    border-radius: 12px;
    padding: 1rem;
    margin: 1rem 0;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}}
.insights-section {{
    background: white;
    border-radius: 12px;
    padding: 1.5rem;
    margin: 1rem 0;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}}
.insights-section h2 {{ color: #007AFF; margin-bottom: 1rem; }}
.insights-section li {{ margin: 0.5rem 0; padding-left: 0.5rem; }}
.disclaimer {{
    background: #FFF3CD;
    border-radius: 12px;
    padding: 1rem 1.5rem;
    margin: 1rem 0;
    font-size: 0.85rem;
    color: #856404;
}}
.footer {{ text-align: center; padding: 2rem; color: #8E8E93; font-size: 0.85rem; }}
</style>
</head>
<body>
<div class="header">
    <h1>Apple Health Dashboard</h1>
    <p>Interactive Health Data Analysis</p>
    <p class="date-range">{date_range_text}</p>
</div>
<div class="container">'''


def _kpi_section(insights):
    """Generate KPI cards from top insights."""
    if not insights:
        return ''
    html = '<div class="kpi-grid">'
    for insight in insights[:6]:
        # Try to split "label: value" format
        if ':' in insight:
            parts = insight.split(':', 1)
            label = parts[0].strip()
            value = parts[1].strip()
        else:
            label = ''
            value = insight
        html += f'''<div class="kpi-card">
            <div class="label">{label}</div>
            <div class="value">{value}</div>
        </div>'''
    html += '</div>'
    return html


def _disclaimer_section():
    return '''<div class="disclaimer">
⚠️ <strong>Disclaimer:</strong> This analysis is generated from Apple Health export data and is for informational purposes only. 
This is not medical advice. Consult a healthcare professional for medical decisions. 
Data accuracy depends on device sensors and wearing compliance.
</div>'''


def _dashboard_footer():
    return f'''</div>
<div class="footer">
    Generated on {datetime.now().strftime("%Y-%m-%d %H:%M")} by Apple Health Analyzer v{__version__}<br>
    <em>Note: "Recent" statistics are relative to the last date in your data, not today's date.</em>
</div>
</body>
</html>'''


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='Apple Health Dashboard Generator')
    parser.add_argument('--data-dir', '-d', required=True, help='Directory containing parsed CSV files')
    parser.add_argument('--output', '-o', default='./health_dashboard.html', help='Output HTML path')
    parser.add_argument('--modules', '-m', default='activity,heartrate,sleep,workout,menstrual,body',
                       help='Comma-separated modules to include')
    parser.add_argument('--special-periods', '-p', default=None,
                       help='JSON array of special periods: [{"name":"Pregnancy","start":"YYYY-MM-DD","end":"YYYY-MM-DD"}]')
    
    args = parser.parse_args()
    
    modules = [m.strip() for m in args.modules.split(',')]
    
    special_periods = None
    if args.special_periods:
        try:
            special_periods = json.loads(args.special_periods)
        except json.JSONDecodeError:
            print("Warning: Could not parse special-periods JSON. Ignoring.")
    
    generate_dashboard(args.data_dir, args.output, modules, special_periods)


if __name__ == '__main__':
    main()
