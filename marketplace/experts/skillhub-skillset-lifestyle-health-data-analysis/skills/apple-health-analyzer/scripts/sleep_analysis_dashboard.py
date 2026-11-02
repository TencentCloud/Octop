#!/usr/bin/env python3
"""
Sleep Analysis Dashboard — Comprehensive Sleep Health Report
Focus: Sleep improvement with pregnancy period annotation
Time range: 2023-01 to 2026-03
"""

import csv
import json
import os
import sys
from datetime import datetime, timedelta
from collections import defaultdict
import math

# ============================================================
# Data Loading
# ============================================================
DATA_DIR = os.path.join(os.path.dirname(__file__), 'health_data')

def read_csv(filename):
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return []
    with open(path, 'r') as f:
        return list(csv.DictReader(f))

def safe_float(val, default=None):
    try:
        return float(val)
    except (ValueError, TypeError):
        return default

def parse_dt(s):
    """Parse '2023-01-01 00:17:00 +0800' format."""
    try:
        return datetime.strptime(s[:19], '%Y-%m-%d %H:%M:%S')
    except:
        return None

def parse_date(s):
    try:
        return datetime.strptime(s[:10], '%Y-%m-%d').date()
    except:
        return None

# ============================================================
# Pregnancy period
# ============================================================
PREGNANCY_START = datetime(2023, 6, 9).date()
PREGNANCY_END = datetime(2024, 2, 15).date()

def get_period_label(d):
    """Classify a date into pre-pregnancy, pregnancy, or postpartum."""
    if d < PREGNANCY_START:
        return 'pre_pregnancy'
    elif d <= PREGNANCY_END:
        return 'pregnancy'
    else:
        return 'postpartum'

# ============================================================
# Sleep Data Processing
# ============================================================
SLEEP_STAGES = {
    'HKCategoryValueSleepAnalysisInBed': '在床上',
    'HKCategoryValueSleepAnalysisAwake': '清醒',
    'HKCategoryValueSleepAnalysisAsleepCore': '浅睡',
    'HKCategoryValueSleepAnalysisAsleepREM': '快速眼动',
    'HKCategoryValueSleepAnalysisAsleepDeep': '深睡',
    'HKCategoryValueSleepAnalysisAsleepUnspecified': '未分类睡眠',
}

def process_sleep_data():
    """Process sleep analysis records into nightly sessions."""
    rows = read_csv('sleep_analysis.csv')
    if not rows:
        return {}

    # Parse all records
    records = []
    for r in rows:
        start = parse_dt(r['startDate'])
        end = parse_dt(r['endDate'])
        stage = SLEEP_STAGES.get(r['value'], '未知')
        source = r.get('sourceName', '').replace('\xa0', ' ')
        if start and end and start < end:
            records.append({
                'start': start,
                'end': end,
                'stage': stage,
                'source': source,
                'duration_min': (end - start).total_seconds() / 60,
            })

    # Group into nightly sessions: "sleep night" = date of bedtime
    # If bedtime is before 6am, assign to previous day's night
    nightly = defaultdict(list)
    for rec in records:
        night_date = rec['start'].date()
        if rec['start'].hour < 6:
            night_date = night_date - timedelta(days=1)
        nightly[night_date].append(rec)

    # For each night, calculate metrics
    # Data source reliability tiers:
    #   Tier 1 (detailed stages): Apple Watch, Pokémon Sleep, Zepp Life
    #   Tier 2 (InBed only / Unspecified only): zephyrus, 睡宝 Sleepal — EXCLUDED
    # Priority within Tier 1: Apple Watch > Pokémon Sleep > Zepp Life
    RELIABLE_SOURCES = {'陈诗园的Apple Watch', 'Pokémon Sleep', 'Zepp Life'}
    
    nights = {}
    for night_date, recs in sorted(nightly.items()):
        # Check sources for this night
        sources = set(r['source'] for r in recs)
        
        # Only keep reliable sources (with detailed sleep stages)
        reliable_sources = sources & RELIABLE_SOURCES
        
        if not reliable_sources:
            # No reliable source for this night — skip it entirely
            continue
        
        # Prefer Apple Watch > Pokémon Sleep > Zepp Life
        if '陈诗园的Apple Watch' in reliable_sources:
            recs = [r for r in recs if r['source'] == '陈诗园的Apple Watch']
            source = 'Apple Watch'
        elif 'Pokémon Sleep' in reliable_sources:
            recs = [r for r in recs if r['source'] == 'Pokémon Sleep']
            source = 'Pokémon Sleep'
        elif 'Zepp Life' in reliable_sources:
            recs = [r for r in recs if r['source'] == 'Zepp Life']
            source = 'Zepp Life'
        else:
            source = list(reliable_sources)[0]
            recs = [r for r in recs if r['source'] == source]

        # Calculate stage durations
        stage_mins = defaultdict(float)
        for r in recs:
            stage_mins[r['stage']] += r['duration_min']

        total_inbed = sum(stage_mins.values())
        
        # total_asleep excludes InBed and Awake
        asleep_stages = ['Core', 'REM', 'Deep', 'Unspecified']
        total_asleep = sum(stage_mins.get(s, 0) for s in asleep_stages)
        
        # If only Unspecified/InBed data from a "reliable" source, use InBed minus Awake
        if total_asleep == 0 and stage_mins.get('在床上', 0) > 0:
            total_asleep = stage_mins['在床上'] - stage_mins.get('清醒', 0)
            if total_asleep < 0:
                total_asleep = stage_mins['在床上']

        # Find bedtime and wake time
        all_starts = [r['start'] for r in recs]
        all_ends = [r['end'] for r in recs]
        bedtime = min(all_starts)
        waketime = max(all_ends)

        # Sleep efficiency
        efficiency = (total_asleep / total_inbed * 100) if total_inbed > 0 else 0

        if total_inbed < 30 or total_inbed > 1200:  # Skip <30min or >20h sessions
            continue

        nights[night_date] = {
            'date': night_date,
            'source': source,
            'bedtime': bedtime,
            'waketime': waketime,
            'total_inbed_min': total_inbed,
            'total_asleep_min': total_asleep,
            'deep_min': stage_mins.get('Deep', 0),
            'rem_min': stage_mins.get('REM', 0),
            'core_min': stage_mins.get('Core', 0),
            'awake_min': stage_mins.get('Awake', 0),
            'unspecified_min': stage_mins.get('Unspecified', 0),
            'efficiency': efficiency,
            'has_stages': stage_mins.get('Deep', 0) > 0 or stage_mins.get('REM', 0) > 0,
            'period': get_period_label(night_date),
        }

    return nights

def process_hrv_data():
    """Process HRV data into daily averages."""
    rows = read_csv('hrv.csv')
    daily = defaultdict(list)
    for r in rows:
        d = parse_date(r['date'])
        v = safe_float(r['value'])
        if d and v is not None:
            daily[d].append(v)
    return {d: sum(vs)/len(vs) for d, vs in daily.items()}

def process_resting_hr():
    rows = read_csv('restingheartrate.csv')
    result = {}
    for r in rows:
        d = parse_date(r['date'])
        v = safe_float(r['value'])
        if d and v is not None:
            result[d] = v
    return result

def process_wrist_temp():
    rows = read_csv('wristtemp.csv')
    result = {}
    for r in rows:
        d = parse_date(r['date'])
        v = safe_float(r['value'])
        if d and v is not None:
            result[d] = v
    return result

def process_breathing_disturbances():
    rows = read_csv('breathingdisturbances.csv')
    daily = defaultdict(list)
    for r in rows:
        d = parse_date(r['date'])
        v = safe_float(r['value'])
        if d and v is not None:
            daily[d].append(v)
    return {d: sum(vs)/len(vs) for d, vs in daily.items()}

def process_respiratory_rate():
    rows = read_csv('respiratoryrate.csv')
    daily = defaultdict(list)
    for r in rows:
        d = parse_date(r['date'])
        v = safe_float(r['value'])
        if d and v is not None:
            daily[d].append(v)
    return {d: sum(vs)/len(vs) for d, vs in daily.items()}

def process_spo2():
    rows = read_csv('oxygensaturation.csv')
    daily = defaultdict(list)
    for r in rows:
        d = parse_date(r['date'])
        v = safe_float(r['value'])
        if d and v is not None:
            daily[d].append(v * 100)  # Convert to percentage
    return {d: sum(vs)/len(vs) for d, vs in daily.items()}

def process_heartrate_daily():
    rows = read_csv('heartrate_daily.csv')
    result = {}
    for r in rows:
        d = parse_date(r.get('date',''))
        if d:
            result[d] = {
                'min': safe_float(r.get('min_value')),
                'max': safe_float(r.get('max_value')),
                'avg': safe_float(r.get('avg_value')),
            }
    return result

# ============================================================
# Statistics Computation
# ============================================================
def compute_stats(nights):
    """Compute comprehensive sleep statistics."""
    stats = {}
    
    # Overall stats
    all_nights = sorted(nights.values(), key=lambda x: x['date'])
    if not all_nights:
        return stats
    
    # Monthly aggregation
    monthly = defaultdict(list)
    for n in all_nights:
        key = n['date'].strftime('%Y-%m')
        monthly[key].append(n)
    
    # Weekly aggregation
    weekly = defaultdict(list)
    for n in all_nights:
        # ISO week
        iso = n['date'].isocalendar()
        key = f"{iso[0]}-W{iso[1]:02d}"
        weekly[key].append(n)
    
    # Day-of-week patterns
    dow_data = defaultdict(list)
    for n in all_nights:
        dow = n['date'].weekday()  # 0=Mon
        dow_data[dow].append(n)
    
    # Period comparison
    period_data = defaultdict(list)
    for n in all_nights:
        period_data[n['period']].append(n)
    
    # Bedtime distribution (convert to minutes from midnight)
    def bedtime_minutes(bt):
        hour = bt.hour
        minute = bt.minute
        if hour >= 12:  # PM bedtime
            return (hour - 24) * 60 + minute  # negative = before midnight
        else:  # AM bedtime (after midnight)
            return hour * 60 + minute
    
    stats['monthly'] = {}
    for month, ns in sorted(monthly.items()):
        asleep_vals = [n['total_asleep_min'] for n in ns]
        deep_vals = [n['deep_min'] for n in ns if n['has_stages']]
        rem_vals = [n['rem_min'] for n in ns if n['has_stages']]
        eff_vals = [n['efficiency'] for n in ns]
        bt_vals = [bedtime_minutes(n['bedtime']) for n in ns]
        
        stats['monthly'][month] = {
            'count': len(ns),
            'avg_asleep': sum(asleep_vals)/len(asleep_vals) if asleep_vals else 0,
            'avg_deep': sum(deep_vals)/len(deep_vals) if deep_vals else 0,
            'avg_rem': sum(rem_vals)/len(rem_vals) if rem_vals else 0,
            'avg_efficiency': sum(eff_vals)/len(eff_vals) if eff_vals else 0,
            'avg_bedtime_min': sum(bt_vals)/len(bt_vals) if bt_vals else 0,
            'period': ns[0]['period'],
        }
    
    stats['weekly'] = {}
    for week, ns in sorted(weekly.items()):
        asleep_vals = [n['total_asleep_min'] for n in ns]
        stats['weekly'][week] = {
            'avg_asleep': sum(asleep_vals)/len(asleep_vals) if asleep_vals else 0,
            'count': len(ns),
        }
    
    stats['dow'] = {}
    dow_names = ['周一','周二','周三','周四','周五','周六','周日']
    for dow, ns in sorted(dow_data.items()):
        asleep_vals = [n['total_asleep_min'] for n in ns]
        bt_vals = [bedtime_minutes(n['bedtime']) for n in ns]
        stats['dow'][dow_names[dow]] = {
            'avg_asleep': sum(asleep_vals)/len(asleep_vals) if asleep_vals else 0,
            'avg_bedtime_min': sum(bt_vals)/len(bt_vals) if bt_vals else 0,
            'count': len(ns),
        }
    
    stats['periods'] = {}
    for period, ns in period_data.items():
        asleep_vals = [n['total_asleep_min'] for n in ns]
        deep_vals = [n['deep_min'] for n in ns if n['has_stages']]
        rem_vals = [n['rem_min'] for n in ns if n['has_stages']]
        eff_vals = [n['efficiency'] for n in ns]
        bt_vals = [bedtime_minutes(n['bedtime']) for n in ns]
        
        stats['periods'][period] = {
            'count': len(ns),
            'avg_asleep': sum(asleep_vals)/len(asleep_vals) if asleep_vals else 0,
            'avg_deep': sum(deep_vals)/len(deep_vals) if deep_vals else 0,
            'avg_rem': sum(rem_vals)/len(rem_vals) if rem_vals else 0,
            'avg_efficiency': sum(eff_vals)/len(eff_vals) if eff_vals else 0,
            'avg_bedtime_min': sum(bt_vals)/len(bt_vals) if bt_vals else 0,
        }
    
    return stats

# ============================================================
# HTML Dashboard Generator
# ============================================================
def minutes_to_hhmm(mins):
    """Convert minutes to H:MM format."""
    h = int(mins) // 60
    m = int(mins) % 60
    return f"{h}:{m:02d}"

def bedtime_min_to_str(mins):
    """Convert bedtime minutes (from midnight) to readable time."""
    if mins < 0:
        # Before midnight
        total = 24 * 60 + mins
    else:
        total = mins
    h = int(total) // 60
    m = int(total) % 60
    return f"{h:02d}:{m:02d}"

def generate_dashboard(nights, hrv, rhr, wrist_temp, breathing, resp_rate, spo2, hr_daily, stats):
    """Generate interactive HTML dashboard."""
    
    sorted_nights = sorted(nights.values(), key=lambda x: x['date'])
    
    # Prepare daily data arrays for charts
    dates = [n['date'].isoformat() for n in sorted_nights]
    total_sleep = [round(n['total_asleep_min']/60, 2) for n in sorted_nights]
    deep_sleep = [round(n['deep_min']/60, 2) for n in sorted_nights]
    rem_sleep = [round(n['rem_min']/60, 2) for n in sorted_nights]
    core_sleep = [round(n['core_min']/60, 2) for n in sorted_nights]
    awake_time = [round(n['awake_min']/60, 2) for n in sorted_nights]
    efficiency = [round(n['efficiency'], 1) for n in sorted_nights]
    sources = [n['source'] for n in sorted_nights]
    
    # Detect data gaps: find months with no data between first and last record
    from datetime import date as date_type
    all_dates = sorted(nights.keys())
    first_date = all_dates[0]
    last_date = all_dates[-1]
    
    # Generate all months between first and last date
    all_months_set = set()
    d = first_date.replace(day=1)
    while d <= last_date:
        all_months_set.add(d.strftime('%Y-%m'))
        if d.month == 12:
            d = d.replace(year=d.year+1, month=1)
        else:
            d = d.replace(month=d.month+1)
    
    # Months with data
    months_with_data = set(n['date'].strftime('%Y-%m') for n in sorted_nights)
    
    # Gap months
    gap_months = sorted(all_months_set - months_with_data)
    
    # Detect source transitions
    source_transitions = []
    prev_source = None
    for n in sorted_nights:
        if prev_source and n['source'] != prev_source:
            source_transitions.append({
                'date': n['date'].isoformat(),
                'from': prev_source,
                'to': n['source'],
            })
        prev_source = n['source']
    
    # Bedtime as decimal hours (for chart)
    bedtimes = []
    waketimes = []
    for n in sorted_nights:
        bt = n['bedtime']
        wt = n['waketime']
        bt_hour = bt.hour + bt.minute/60
        if bt_hour < 12:
            bt_hour += 24
        bedtimes.append(round(bt_hour, 2))
        wt_hour = wt.hour + wt.minute/60
        waketimes.append(round(wt_hour, 2))
    
    # Period markers for pregnancy
    period_colors = []
    for n in sorted_nights:
        p = n['period']
        if p == 'pregnancy':
            period_colors.append('#FF2D5540')
        else:
            period_colors.append('#007AFF20')
    
    # Monthly chart data — include gap months as null for proper chart breaks
    monthly_labels_raw = list(stats['monthly'].keys())
    # Build complete month list from first to last, inserting nulls for gaps
    monthly_labels = []
    monthly_asleep = []
    monthly_deep = []
    monthly_rem = []
    monthly_eff = []
    monthly_periods = []
    monthly_sources = []  # dominant source per month
    monthly_is_gap = []
    
    # First get the dominant source per month from actual data
    from collections import Counter
    month_source_counter = defaultdict(Counter)
    for n in sorted_nights:
        m = n['date'].strftime('%Y-%m')
        month_source_counter[m][n['source']] += 1
    
    if monthly_labels_raw:
        first_m = monthly_labels_raw[0]
        last_m = monthly_labels_raw[-1]
        # Generate all months
        fy, fm = int(first_m[:4]), int(first_m[5:7])
        ly, lm = int(last_m[:4]), int(last_m[5:7])
        cy, cm = fy, fm
        while (cy, cm) <= (ly, lm):
            m_key = f"{cy:04d}-{cm:02d}"
            monthly_labels.append(m_key)
            if m_key in stats['monthly']:
                v = stats['monthly'][m_key]
                monthly_asleep.append(round(v['avg_asleep']/60, 2))
                monthly_deep.append(round(v['avg_deep']/60, 2))
                monthly_rem.append(round(v['avg_rem']/60, 2))
                monthly_eff.append(round(v['avg_efficiency'], 1))
                monthly_periods.append(v['period'])
                monthly_is_gap.append(False)
                # Find dominant source
                if month_source_counter[m_key]:
                    monthly_sources.append(month_source_counter[m_key].most_common(1)[0][0])
                else:
                    monthly_sources.append('')
            else:
                monthly_asleep.append(None)
                monthly_deep.append(None)
                monthly_rem.append(None)
                monthly_eff.append(None)
                monthly_periods.append(get_period_label(datetime(cy, cm, 15).date()))
                monthly_is_gap.append(True)
                monthly_sources.append('')
            cm += 1
            if cm > 12:
                cm = 1
                cy += 1
    
    # Day-of-week data
    dow_labels = list(stats['dow'].keys())
    dow_asleep = [round(v['avg_asleep']/60, 2) for v in stats['dow'].values()]
    dow_bedtime = [round(v['avg_bedtime_min'], 0) for v in stats['dow'].values()]
    
    # HRV daily data
    hrv_dates = [d.isoformat() for d in sorted(hrv.keys())]
    hrv_values = [round(hrv[d], 1) for d in sorted(hrv.keys())]
    
    # Resting HR
    rhr_dates = [d.isoformat() for d in sorted(rhr.keys())]
    rhr_values = [round(rhr[d], 1) for d in sorted(rhr.keys())]
    
    # Wrist temp
    wt_dates = [d.isoformat() for d in sorted(wrist_temp.keys())]
    wt_values = [round(wrist_temp[d], 2) for d in sorted(wrist_temp.keys())]
    
    # Breathing disturbances
    bd_dates = [d.isoformat() for d in sorted(breathing.keys())]
    bd_values = [round(breathing[d], 2) for d in sorted(breathing.keys())]
    
    # Respiratory rate
    rr_dates = [d.isoformat() for d in sorted(resp_rate.keys())]
    rr_values = [round(resp_rate[d], 1) for d in sorted(resp_rate.keys())]
    
    # SpO2
    spo2_dates = [d.isoformat() for d in sorted(spo2.keys())]
    spo2_values = [round(spo2[d], 1) for d in sorted(spo2.keys())]
    
    # Period comparison stats
    period_names_map = {
        'pre_pregnancy': '孕前 (2023.01-06)',
        'pregnancy': '孕期 (2023.06-2024.02)',
        'postpartum': '产后 (2024.02至今)',
    }
    
    # Compute 7-day and 30-day moving averages for sleep
    def moving_avg(values, window):
        result = []
        for i in range(len(values)):
            start = max(0, i - window + 1)
            chunk = [v for v in values[start:i+1] if v is not None and v > 0]
            result.append(round(sum(chunk)/len(chunk), 2) if chunk else None)
        return result
    
    sleep_ma7 = moving_avg(total_sleep, 7)
    sleep_ma30 = moving_avg(total_sleep, 30)
    
    # Calculate summary KPIs
    recent_30 = [n for n in sorted_nights if n['date'] >= (datetime.now().date() - timedelta(days=30))]
    recent_avg_sleep = sum(n['total_asleep_min'] for n in recent_30) / len(recent_30) / 60 if recent_30 else 0
    recent_avg_deep = sum(n['deep_min'] for n in recent_30 if n['has_stages']) / max(1, len([n for n in recent_30 if n['has_stages']])) / 60
    recent_avg_eff = sum(n['efficiency'] for n in recent_30) / len(recent_30) if recent_30 else 0
    recent_avg_bt = sum(
        (n['bedtime'].hour + n['bedtime'].minute/60 + (24 if n['bedtime'].hour < 12 else 0))
        for n in recent_30
    ) / len(recent_30) if recent_30 else 0
    
    all_avg_sleep = sum(n['total_asleep_min'] for n in sorted_nights) / len(sorted_nights) / 60
    
    # Score calculation (simple)
    def sleep_score(sleep_hrs, deep_hrs, eff):
        score = 0
        # Duration (40 pts): 7-9h ideal
        if 7 <= sleep_hrs <= 9:
            score += 40
        elif 6 <= sleep_hrs < 7 or 9 < sleep_hrs <= 10:
            score += 30
        else:
            score += max(0, 40 - abs(sleep_hrs - 8) * 10)
        # Deep sleep (30 pts): 1-2h ideal
        if deep_hrs >= 1.0:
            score += min(30, deep_hrs * 20)
        else:
            score += deep_hrs * 30
        # Efficiency (30 pts): 85%+ ideal
        score += min(30, eff / 100 * 30)
        return min(100, max(0, round(score)))
    
    recent_score = sleep_score(recent_avg_sleep, recent_avg_deep, recent_avg_eff)
    
    # Generate HTML
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>睡眠健康分析报告</title>
<script src="https://cdn.plot.ly/plotly-2.35.0.min.js"></script>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Helvetica Neue', sans-serif;
    background: #F2F2F7;
    color: #1C1C1E;
    line-height: 1.5;
}}
.header {{
    background: linear-gradient(135deg, #1C1C2E 0%, #2C2C4E 100%);
    color: white;
    padding: 40px 20px 30px;
    text-align: center;
}}
.header h1 {{
    font-size: 28px;
    font-weight: 700;
    margin-bottom: 8px;
}}
.header .subtitle {{
    font-size: 15px;
    opacity: 0.7;
}}
.container {{
    max-width: 1200px;
    margin: 0 auto;
    padding: 20px;
}}

/* KPI Cards */
.kpi-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 12px;
    margin: -40px 0 20px;
    position: relative;
    z-index: 10;
}}
.kpi-card {{
    background: white;
    border-radius: 16px;
    padding: 20px;
    text-align: center;
    box-shadow: 0 2px 12px rgba(0,0,0,0.08);
}}
.kpi-card .score {{
    font-size: 36px;
    font-weight: 700;
    line-height: 1.2;
}}
.kpi-card .label {{
    font-size: 13px;
    color: #8E8E93;
    margin-top: 4px;
}}
.kpi-card .sub {{
    font-size: 11px;
    color: #8E8E93;
    margin-top: 2px;
}}
.score-blue {{ color: #007AFF; }}
.score-purple {{ color: #AF52DE; }}
.score-green {{ color: #34C759; }}
.score-orange {{ color: #FF9500; }}
.score-red {{ color: #FF3B30; }}
.score-teal {{ color: #5AC8FA; }}

/* Section */
.section {{
    background: white;
    border-radius: 16px;
    padding: 24px;
    margin-bottom: 16px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.04);
}}
.section h2 {{
    font-size: 20px;
    font-weight: 700;
    margin-bottom: 16px;
    display: flex;
    align-items: center;
    gap: 8px;
}}
.section h3 {{
    font-size: 16px;
    font-weight: 600;
    margin: 16px 0 8px;
    color: #3A3A3C;
}}

/* Period comparison */
.period-grid {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 12px;
    margin: 16px 0;
}}
.period-card {{
    border-radius: 12px;
    padding: 16px;
    text-align: center;
}}
.period-card.pre {{ background: #E8F5E9; border: 2px solid #34C759; }}
.period-card.preg {{ background: #FFF3E0; border: 2px solid #FF9500; }}
.period-card.post {{ background: #E3F2FD; border: 2px solid #007AFF; }}
.period-card .period-title {{
    font-size: 14px;
    font-weight: 600;
    margin-bottom: 8px;
}}
.period-card .metric {{
    font-size: 13px;
    margin: 4px 0;
    color: #3A3A3C;
}}
.period-card .metric strong {{
    font-size: 18px;
}}

/* Chart container */
.chart-container {{
    width: 100%;
    margin: 12px 0;
}}

/* Insights */
.insight-box {{
    background: #F0F4FF;
    border-left: 4px solid #007AFF;
    border-radius: 8px;
    padding: 14px 16px;
    margin: 12px 0;
    font-size: 14px;
    line-height: 1.6;
}}
.insight-box.warning {{
    background: #FFF8E1;
    border-left-color: #FF9500;
}}
.insight-box.good {{
    background: #E8F5E9;
    border-left-color: #34C759;
}}
.insight-box .insight-title {{
    font-weight: 600;
    margin-bottom: 4px;
}}

/* Pregnancy band annotation */
.preg-legend {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
    color: #8E8E93;
    margin: 8px 0;
}}
.preg-legend .dot {{
    width: 12px;
    height: 12px;
    border-radius: 3px;
    display: inline-block;
}}

/* Footer */
.footer {{
    text-align: center;
    padding: 20px;
    color: #8E8E93;
    font-size: 12px;
}}

/* Responsive */
@media (max-width: 768px) {{
    .kpi-grid {{ grid-template-columns: repeat(3, 1fr); }}
    .period-grid {{ grid-template-columns: 1fr; }}
    .container {{ padding: 12px; }}
}}

/* Recommendations */
.rec-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 12px;
    margin-top: 12px;
}}
.rec-card {{
    border-radius: 12px;
    padding: 16px;
    background: #F8F8FA;
    border: 1px solid #E5E5EA;
}}
.rec-card .rec-title {{
    font-weight: 600;
    font-size: 15px;
    margin-bottom: 6px;
    color: #1C1C1E;
}}
.rec-card .rec-text {{
    font-size: 13px;
    color: #3A3A3C;
    line-height: 1.5;
}}
</style>
</head>
<body>

<div class="header">
    <h1>🌙 睡眠健康分析报告</h1>
    <div class="subtitle">数据范围: 2023年1月 — 2026年3月 · 共 {len(sorted_nights)} 晚可靠数据 · 仅使用有详细睡眠阶段的数据源</div>
</div>

<div class="container">

<!-- KPI Cards -->
<div class="kpi-grid">
    <div class="kpi-card">
        <div class="score score-blue">{recent_score}</div>
        <div class="label">睡眠评分</div>
        <div class="sub">近30天综合</div>
    </div>
    <div class="kpi-card">
        <div class="score score-purple">{recent_avg_sleep:.1f}<span style="font-size:16px">h</span></div>
        <div class="label">平均睡眠</div>
        <div class="sub">近30天</div>
    </div>
    <div class="kpi-card">
        <div class="score score-green">{recent_avg_deep*60:.0f}<span style="font-size:16px">min</span></div>
        <div class="label">平均深睡</div>
        <div class="sub">近30天</div>
    </div>
    <div class="kpi-card">
        <div class="score score-orange">{recent_avg_eff:.0f}<span style="font-size:16px">%</span></div>
        <div class="label">睡眠效率</div>
        <div class="sub">近30天</div>
    </div>
    <div class="kpi-card">
        <div class="score score-teal">{int(recent_avg_bt)}:{int((recent_avg_bt%1)*60):02d}</div>
        <div class="label">平均入睡</div>
        <div class="sub">近30天</div>
    </div>
    <div class="kpi-card">
        <div class="score score-red">{len(sorted_nights)}</div>
        <div class="label">有效记录</div>
        <div class="sub">总夜数</div>
    </div>
</div>

<!-- Section 1: Period Comparison -->
<div class="section">
    <h2>📊 孕期前后睡眠对比</h2>
    <div class="preg-legend">
        <span class="dot" style="background:#34C759"></span> 孕前 (2023.01-06)
        <span class="dot" style="background:#FF9500; margin-left:12px"></span> 孕期 (2023.06-2024.02)
        <span class="dot" style="background:#007AFF; margin-left:12px"></span> 产后 (2024.02至今)
    </div>
    <div class="period-grid">
"""
    
    for period_key, css_class in [('pre_pregnancy', 'pre'), ('pregnancy', 'preg'), ('postpartum', 'post')]:
        p = stats['periods'].get(period_key, {})
        if p:
            name = period_names_map.get(period_key, period_key)
            avg_sleep_h = p['avg_asleep'] / 60
            avg_deep_m = p['avg_deep']
            avg_rem_m = p['avg_rem']
            avg_eff = p['avg_efficiency']
            bt = bedtime_min_to_str(p['avg_bedtime_min'])
            html += f"""
        <div class="period-card {css_class}">
            <div class="period-title">{name}</div>
            <div class="metric">睡眠时长: <strong>{avg_sleep_h:.1f}h</strong></div>
            <div class="metric">深睡: <strong>{avg_deep_m:.0f}min</strong></div>
            <div class="metric">快速眼动: <strong>{avg_rem_m:.0f}min</strong></div>
            <div class="metric">效率: <strong>{avg_eff:.0f}%</strong></div>
            <div class="metric">入睡: <strong>{bt}</strong></div>
            <div class="metric" style="font-size:12px;color:#8E8E93">{p['count']}晚数据</div>
        </div>"""
    
    html += """
    </div>
    <div id="chart_period_compare" class="chart-container"></div>
</div>

<!-- Section 2: Sleep Duration Trend -->
<div class="section">
    <h2>⏱️ 睡眠时长趋势</h2>
    <div class="preg-legend">
        <span class="dot" style="background:#FF950040"></span> 橙色区域 = 孕期
    </div>
    <div id="chart_sleep_trend" class="chart-container"></div>
</div>

<!-- Section 3: Sleep Stages -->
<div class="section">
    <h2>🧠 睡眠阶段分析</h2>
    <div id="chart_stages_monthly" class="chart-container"></div>
    <div id="chart_stages_stacked" class="chart-container"></div>
</div>

<!-- Section 4: Bedtime & Wake time -->
<div class="section">
    <h2>🕐 入睡与起床时间</h2>
    <div id="chart_bedtime" class="chart-container"></div>
    <h3>星期几的睡眠模式</h3>
    <div id="chart_dow" class="chart-container"></div>
</div>

<!-- Section 5: Sleep Efficiency -->
<div class="section">
    <h2>💤 睡眠效率</h2>
    <div class="insight-box">
        <div class="insight-title">数据源说明</div>
        仅使用具有详细睡眠阶段（深睡/快速眼动/浅睡）的可靠数据源计算效率。
        <strong>已排除</strong>: zephyrus（仅记录"在床上"，效率恒为 100% 不可信）、睡宝 Sleepal（仅"未分类"）。
        灰色区域表示<strong>数据缺失</strong>期间，不同颜色表示不同数据源。
    </div>
    <div id="chart_efficiency" class="chart-container"></div>
</div>

<!-- Section 6: Physiological Indicators -->
<div class="section">
    <h2>❤️ 睡眠相关生理指标</h2>
    <div id="chart_rhr" class="chart-container"></div>
    <div id="chart_hrv" class="chart-container"></div>
    <div id="chart_wrist_temp" class="chart-container"></div>
    <div id="chart_breathing" class="chart-container"></div>
    <div id="chart_spo2" class="chart-container"></div>
</div>

<!-- Section 7: Monthly Heatmap -->
<div class="section">
    <h2>📅 睡眠日历热力图</h2>
    <div id="chart_heatmap" class="chart-container"></div>
</div>

<!-- Section 8: Insights & Recommendations -->
<div class="section">
    <h2>💡 分析洞察与改善建议</h2>
    <div id="insights_container"></div>
</div>

</div>

<div class="footer">
    数据来源: Apple Health · 生成时间: """ + datetime.now().strftime('%Y-%m-%d %H:%M') + """
</div>

<script>
const PREG_START = '2023-06-09';
const PREG_END = '2024-02-15';

// Pregnancy band shape for Plotly
function pregBand(yref) {
    return {
        type: 'rect', xref: 'x', yref: yref || 'paper',
        x0: PREG_START, x1: PREG_END,
        y0: 0, y1: 1,
        fillcolor: 'rgba(255,149,0,0.12)', line: {width: 0},
        layer: 'below'
    };
}

const layoutDefaults = {
    font: { family: '-apple-system, BlinkMacSystemFont, sans-serif', size: 13 },
    paper_bgcolor: 'transparent',
    plot_bgcolor: 'transparent',
    margin: { l: 50, r: 20, t: 40, b: 50 },
    hovermode: 'x unified',
    xaxis: { gridcolor: '#E5E5EA', showgrid: true, tickformat: '%Y-%m', dtick: 'M3', tickangle: 0, tickfont: { size: 11 } },
    yaxis: { gridcolor: '#E5E5EA', showgrid: true },
};

// Helper: daily xaxis config (for charts with many daily data points)
const dailyXaxis = {
    ...layoutDefaults.xaxis,
    tickformat: '%Y-%m',
    dtick: 'M3',
    tickangle: 0,
    tickfont: { size: 11 },
};

// ---- Data ----
const dates = """ + json.dumps(dates) + """;
const totalSleep = """ + json.dumps(total_sleep) + """;
const deepSleep = """ + json.dumps(deep_sleep) + """;
const remSleep = """ + json.dumps(rem_sleep) + """;
const coreSleep = """ + json.dumps(core_sleep) + """;
const awakeTm = """ + json.dumps(awake_time) + """;
const effData = """ + json.dumps(efficiency) + """;
const bedtimes = """ + json.dumps(bedtimes) + """;
const waketimes = """ + json.dumps(waketimes) + """;
const sleepMA7 = """ + json.dumps(sleep_ma7) + """;
const sleepMA30 = """ + json.dumps(sleep_ma30) + """;

const monthLabels = """ + json.dumps(monthly_labels) + """;
const monthAsleep = """ + json.dumps(monthly_asleep) + """;
const monthDeep = """ + json.dumps(monthly_deep) + """;
const monthREM = """ + json.dumps(monthly_rem) + """;
const monthEff = """ + json.dumps(monthly_eff) + """;
const monthPeriods = """ + json.dumps(monthly_periods) + """;
const monthIsGap = """ + json.dumps(monthly_is_gap) + """;
const monthSources = """ + json.dumps(monthly_sources) + """;
const gapMonths = """ + json.dumps(gap_months) + """;
const sourceTransitions = """ + json.dumps(source_transitions) + """;
const dailySources = """ + json.dumps(sources) + """;

const dowLabels = """ + json.dumps(dow_labels) + """;
const dowAsleep = """ + json.dumps(dow_asleep) + """;
const dowBedtime = """ + json.dumps(dow_bedtime) + """;

const hrvDates = """ + json.dumps(hrv_dates) + """;
const hrvValues = """ + json.dumps(hrv_values) + """;
const rhrDates = """ + json.dumps(rhr_dates) + """;
const rhrValues = """ + json.dumps(rhr_values) + """;
const wtDates = """ + json.dumps(wt_dates) + """;
const wtValues = """ + json.dumps(wt_values) + """;
const bdDates = """ + json.dumps(bd_dates) + """;
const bdValues = """ + json.dumps(bd_values) + """;
const rrDates = """ + json.dumps(rr_dates) + """;
const rrValues = """ + json.dumps(rr_values) + """;
const spo2Dates = """ + json.dumps(spo2_dates) + """;
const spo2Values = """ + json.dumps(spo2_values) + """;

// ---- Period Comparison Bar ----
(function() {
    const periods = """ + json.dumps({period_names_map.get(k,k): v for k,v in stats['periods'].items()}) + """;
    const names = Object.keys(periods);
    const colors = ['#34C759', '#FF9500', '#007AFF'];
    
    const metrics = ['avg_asleep', 'avg_deep', 'avg_rem'];
    const metricNames = ['总睡眠(分钟)', '深睡(分钟)', '快速眼动(分钟)'];
    const traces = metrics.map((m, i) => ({
        x: names,
        y: names.map(n => Math.round(periods[n][m])),
        name: metricNames[i],
        type: 'bar',
    }));
    
    Plotly.newPlot('chart_period_compare', traces, {
        ...layoutDefaults,
        barmode: 'group',
        title: { text: '孕前 / 孕期 / 产后 睡眠关键指标对比', font: { size: 15 } },
        yaxis: { ...layoutDefaults.yaxis, title: '分钟' },
    }, {responsive: true});
})();

// ---- Sleep Duration Trend ----
(function() {
    // Color scatter points by source
    const sourceColorMap = {
        'Zepp Life': '#34C759',
        'Pokémon Sleep': '#FF9500',
        'Apple Watch': '#007AFF',
    };
    const ptColors = dailySources.map(s => sourceColorMap[s] || '#8E8E93');
    
    // Gap annotations on the trend chart
    const gapAnns = [];
    if (gapMonths.length > 0) {
        // Find contiguous gap ranges
        const gapRanges = [];
        let rangeStart = gapMonths[0];
        for (let i = 1; i <= gapMonths.length; i++) {
            if (i < gapMonths.length) {
                // Check if consecutive month
                const prev = gapMonths[i-1];
                const curr = gapMonths[i];
                const py = parseInt(prev.substring(0,4)), pm = parseInt(prev.substring(5,7));
                const cy = parseInt(curr.substring(0,4)), cm = parseInt(curr.substring(5,7));
                const nextM = pm === 12 ? 1 : pm + 1;
                const nextY = pm === 12 ? py + 1 : py;
                if (cy === nextY && cm === nextM) continue;
            }
            gapRanges.push([rangeStart, gapMonths[i-1]]);
            if (i < gapMonths.length) rangeStart = gapMonths[i];
        }
        
        for (const [gs, ge] of gapRanges) {
            gapAnns.push({
                x: gs + '-15', y: 12, text: gs === ge ? `数据缺失<br>${gs}` : `数据缺失<br>${gs} ~ ${ge}`,
                showarrow: true, arrowhead: 0, ax: 0, ay: -20,
                font: { size: 10, color: '#8E8E93' },
                bgcolor: 'rgba(255,255,255,0.85)',
                borderpad: 3,
            });
        }
    }
    
    // Source transition vertical lines
    const transShapes = sourceTransitions.map(t => ({
        type: 'line', xref: 'x', yref: 'paper',
        x0: t.date, x1: t.date, y0: 0, y1: 1,
        line: { color: '#C7C7CC', dash: 'dot', width: 1 },
        layer: 'below'
    }));
    const transAnns = sourceTransitions.map(t => ({
        x: t.date, y: 13, text: `${t.to}`,
        showarrow: false, font: { size: 9, color: '#636366' },
        bgcolor: 'rgba(255,255,255,0.8)',
        borderpad: 2,
    }));
    
    Plotly.newPlot('chart_sleep_trend', [
        { x: dates, y: totalSleep, type: 'scatter', mode: 'markers',
          name: '每夜睡眠', marker: { size: 3, color: ptColors, opacity: 0.4 } },
        { x: dates, y: sleepMA7, type: 'scatter', mode: 'lines',
          name: '7日均线', line: { color: '#007AFF', width: 2 }, connectgaps: false },
        { x: dates, y: sleepMA30, type: 'scatter', mode: 'lines',
          name: '30日均线', line: { color: '#FF9500', width: 2.5 }, connectgaps: false },
    ], {
        ...layoutDefaults,
        title: { text: '每夜睡眠时长趋势（小时）— 仅可靠数据源', font: { size: 15 } },
        shapes: [pregBand(), ...transShapes],
        xaxis: dailyXaxis,
        yaxis: { ...layoutDefaults.yaxis, title: '小时', range: [0, 14] },
        annotations: [
            { x: '2023-10-15', y: 13, text: '🤰 孕期', showarrow: false,
              font: { size: 12, color: '#FF9500' } },
            ...gapAnns,
            ...transAnns,
        ],
    }, {responsive: true});
})();

// ---- Monthly Stages ----
(function() {
    const monthColors = monthPeriods.map(p => p === 'pregnancy' ? '#FF9500' : p === 'pre_pregnancy' ? '#34C759' : '#007AFF');
    
    // For gap months, values are null — Plotly will skip them in bar charts
    const deepVals = monthDeep;
    const remVals = monthREM;
    const coreVals = monthAsleep.map((v, i) => {
        if (v === null) return null;
        return Math.max(0, v - (monthDeep[i] || 0) - (monthREM[i] || 0));
    });
    
    // Gap shapes
    const gapShapes = [];
    for (let i = 0; i < monthLabels.length; i++) {
        if (monthIsGap[i]) {
            gapShapes.push({
                type: 'rect', xref: 'x', yref: 'paper',
                x0: i - 0.5, x1: i + 0.5,
                y0: 0, y1: 1,
                fillcolor: 'rgba(142,142,147,0.12)',
                line: { width: 0 }, layer: 'below'
            });
        }
    }
    
    Plotly.newPlot('chart_stages_monthly', [
        { x: monthLabels, y: deepVals, name: '深睡', type: 'bar', marker: { color: '#5856D6' } },
        { x: monthLabels, y: remVals, name: 'REM', type: 'bar', marker: { color: '#5AC8FA' } },
        { x: monthLabels, y: coreVals, name: '浅睡(Core)', type: 'bar', marker: { color: '#007AFF' } },
    ], {
        ...layoutDefaults,
        barmode: 'stack',
        title: { text: '月均睡眠阶段构成（小时）— 仅可靠数据源', font: { size: 15 } },
        xaxis: { ...layoutDefaults.xaxis, type: 'category', dtick: 3, tickangle: -30, tickfont: { size: 11 } },
        yaxis: { ...layoutDefaults.yaxis, title: '小时' },
        shapes: gapShapes,
    }, {responsive: true});
})();

// ---- Daily Stacked Area ----
(function() {
    // Filter for nights with stage data
    const stageDates = [];
    const stageDeep = [];
    const stageREM = [];
    const stageCore = [];
    const stageAwake = [];
    
    for (let i = 0; i < dates.length; i++) {
        if (deepSleep[i] > 0 || remSleep[i] > 0) {
            stageDates.push(dates[i]);
            stageDeep.push(deepSleep[i]);
            stageREM.push(remSleep[i]);
            stageCore.push(coreSleep[i]);
            stageAwake.push(awakeTm[i]);
        }
    }
    
    Plotly.newPlot('chart_stages_stacked', [
        { x: stageDates, y: stageDeep, name: '深睡', stackgroup: 'one', fillcolor: 'rgba(88,86,214,0.6)', line: {width: 0} },
        { x: stageDates, y: stageREM, name: '快速眼动(REM)', stackgroup: 'one', fillcolor: 'rgba(90,200,250,0.6)', line: {width: 0} },
        { x: stageDates, y: stageCore, name: '浅睡', stackgroup: 'one', fillcolor: 'rgba(0,122,255,0.4)', line: {width: 0} },
        { x: stageDates, y: stageAwake, name: '清醒', stackgroup: 'one', fillcolor: 'rgba(255,59,48,0.3)', line: {width: 0} },
    ], {
        ...layoutDefaults,
        title: { text: '每夜睡眠阶段明细（小时）', font: { size: 15 } },
        xaxis: dailyXaxis,
        yaxis: { ...layoutDefaults.yaxis, title: '小时' },
        shapes: [pregBand()],
    }, {responsive: true});
})();

// ---- Bedtime / Wake time ----
Plotly.newPlot('chart_bedtime', [
    { x: dates, y: bedtimes, type: 'scatter', mode: 'markers',
      name: '入睡时间', marker: { size: 2, color: '#5856D6', opacity: 0.3 } },
    { x: dates, y: waketimes, type: 'scatter', mode: 'markers',
      name: '起床时间', marker: { size: 2, color: '#FF9500', opacity: 0.3 } },
], {
    ...layoutDefaults,
    title: { text: '入睡与起床时间', font: { size: 15 } },
    shapes: [pregBand()],
    xaxis: dailyXaxis,
    yaxis: {
        ...layoutDefaults.yaxis, title: '时间',
        tickvals: [21, 22, 23, 24, 25, 26, 27, 28, 29, 30],
        ticktext: ['21:00', '22:00', '23:00', '00:00', '01:00', '02:00', '03:00', '04:00', '05:00', '06:00'],
        range: [20, 33],
    },
}, {responsive: true});

// ---- Day-of-week ----
Plotly.newPlot('chart_dow', [
    { x: dowLabels, y: dowAsleep, type: 'bar', name: '平均睡眠(h)',
      marker: { color: '#007AFF' } },
], {
    ...layoutDefaults,
    title: { text: '星期几的平均睡眠时长（小时）', font: { size: 15 } },
    yaxis: { ...layoutDefaults.yaxis, title: '小时' },
}, {responsive: true});

// ---- Efficiency ----
(function() {
    // Build per-source color mapping for efficiency
    const sourceColorMap = {
        'Zepp Life': '#34C759',
        'Pokémon Sleep': '#FF9500',
        'Apple Watch': '#007AFF',
    };
    
    // Create separate traces per source segment for different colors
    const effTraces = [];
    let currentSrc = null;
    let segDates = [];
    let segVals = [];
    
    function flushSegment() {
        if (segDates.length > 0 && currentSrc) {
            effTraces.push({
                x: segDates,
                y: segVals,
                type: 'scatter',
                mode: 'lines+markers',
                name: currentSrc,
                line: { color: sourceColorMap[currentSrc] || '#8E8E93', width: 2 },
                marker: { size: 5 },
                showlegend: !effTraces.some(t => t.name === currentSrc),
                legendgroup: currentSrc,
                connectgaps: false,
            });
        }
    }
    
    for (let i = 0; i < monthLabels.length; i++) {
        if (monthIsGap[i]) {
            // Flush current segment
            flushSegment();
            segDates = [];
            segVals = [];
            currentSrc = null;
        } else {
            const src = monthSources[i];
            if (src !== currentSrc) {
                // If switching source, overlap the last point for continuity
                const prevDate = segDates.length > 0 ? segDates[segDates.length - 1] : null;
                const prevVal = segVals.length > 0 ? segVals[segVals.length - 1] : null;
                flushSegment();
                segDates = [];
                segVals = [];
                // Bridge: add the previous point to new segment for connected line
                if (prevDate && prevVal !== null) {
                    segDates.push(prevDate);
                    segVals.push(prevVal);
                }
                currentSrc = src;
            }
            segDates.push(monthLabels[i]);
            segVals.push(monthEff[i]);
        }
    }
    flushSegment();
    
    // Gap annotations
    const gapShapes = [];
    const gapAnnotations = [];
    for (let i = 0; i < monthLabels.length; i++) {
        if (monthIsGap[i]) {
            gapShapes.push({
                type: 'rect', xref: 'x', yref: 'paper',
                x0: i - 0.5, x1: i + 0.5,
                y0: 0, y1: 1,
                fillcolor: 'rgba(142,142,147,0.15)',
                line: { width: 0 },
                layer: 'below'
            });
        }
    }
    
    // Find contiguous gap ranges for annotations
    let gapStart = null;
    for (let i = 0; i <= monthLabels.length; i++) {
        if (i < monthLabels.length && monthIsGap[i]) {
            if (gapStart === null) gapStart = i;
        } else {
            if (gapStart !== null) {
                const gapEnd = i - 1;
                const midIdx = (gapStart + gapEnd) / 2;
                const gapCount = gapEnd - gapStart + 1;
                gapAnnotations.push({
                    x: midIdx, y: 75, xref: 'x', yref: 'y',
                    text: gapCount === 1 ? '无数据' : `无数据 (${gapCount}个月)`,
                    showarrow: false,
                    font: { size: 11, color: '#8E8E93' },
                    bgcolor: 'rgba(255,255,255,0.8)',
                    borderpad: 3,
                });
                gapStart = null;
            }
        }
    }
    
    // Source transition annotations
    const transAnnotations = [];
    for (const t of sourceTransitions) {
        const idx = monthLabels.indexOf(t.date.substring(0, 7));
        if (idx >= 0) {
            transAnnotations.push({
                x: idx, y: monthEff[idx] || 80, xref: 'x', yref: 'y',
                text: `${t.from} → ${t.to}`,
                showarrow: true, arrowhead: 2, arrowsize: 0.8,
                ax: 0, ay: -35,
                font: { size: 10, color: '#636366' },
                bgcolor: 'rgba(255,255,255,0.9)',
                borderpad: 2,
            });
        }
    }
    
    Plotly.newPlot('chart_efficiency', effTraces, {
        ...layoutDefaults,
        title: { text: '月均睡眠效率趋势 (%) — 按数据源着色', font: { size: 15 } },
        xaxis: { ...layoutDefaults.xaxis, type: 'category', dtick: 3, tickangle: -30, tickfont: { size: 11 } },
        yaxis: { ...layoutDefaults.yaxis, title: '%', range: [40, 105] },
        shapes: [
            { type: 'line', xref: 'paper', yref: 'y',
              x0: 0, x1: 1, y0: 85, y1: 85,
              line: { color: '#34C759', dash: 'dash', width: 1 } },
            ...gapShapes,
        ],
        annotations: [
            {
                xref: 'paper', x: 0.98, y: 85,
                text: '85% 良好基准', showarrow: false,
                font: { size: 11, color: '#34C759' }, yshift: 10, xanchor: 'right',
            },
            ...gapAnnotations,
            ...transAnnotations,
        ],
    }, {responsive: true});
})();

// ---- Physiological: RHR ----
if (rhrDates.length > 0) {
    Plotly.newPlot('chart_rhr', [
        { x: rhrDates, y: rhrValues, type: 'scatter', mode: 'lines',
          name: '静息心率', line: { color: '#FF3B30', width: 1.2 } },
    ], {
        ...layoutDefaults,
        title: { text: '静息心率趋势 (bpm)', font: { size: 15 } },
        xaxis: dailyXaxis,
        yaxis: { ...layoutDefaults.yaxis, title: 'bpm' },
        shapes: [pregBand()],
    }, {responsive: true});
}

// ---- HRV ----
if (hrvDates.length > 0) {
    Plotly.newPlot('chart_hrv', [
        { x: hrvDates, y: hrvValues, type: 'scatter', mode: 'lines',
          name: 'HRV (SDNN)', line: { color: '#AF52DE', width: 1.2 } },
    ], {
        ...layoutDefaults,
        title: { text: '心率变异性 HRV (毫秒)', font: { size: 15 } },
        xaxis: dailyXaxis,
        yaxis: { ...layoutDefaults.yaxis, title: '毫秒' },
        shapes: [pregBand()],
    }, {responsive: true});
}

// ---- Wrist Temperature ----
if (wtDates.length > 0) {
    Plotly.newPlot('chart_wrist_temp', [
        { x: wtDates, y: wtValues, type: 'scatter', mode: 'lines',
          name: '睡眠腕温', line: { color: '#FF9500', width: 1.2 } },
    ], {
        ...layoutDefaults,
        title: { text: '睡眠腕部温度 (°C)', font: { size: 15 } },
        xaxis: dailyXaxis,
        yaxis: { ...layoutDefaults.yaxis, title: '°C' },
    }, {responsive: true});
}

// ---- Breathing Disturbances ----
if (bdDates.length > 0) {
    Plotly.newPlot('chart_breathing', [
        { x: bdDates, y: bdValues, type: 'scatter', mode: 'lines',
          name: '呼吸扰动', line: { color: '#5AC8FA', width: 1.2 } },
    ], {
        ...layoutDefaults,
        title: { text: '睡眠呼吸扰动次数', font: { size: 15 } },
        xaxis: dailyXaxis,
        yaxis: { ...layoutDefaults.yaxis, title: '次/小时' },
        shapes: [{
            type: 'line', xref: 'paper', yref: 'y',
            x0: 0, x1: 1, y0: 5, y1: 5,
            line: { color: '#FF9500', dash: 'dash', width: 1 }
        }],
    }, {responsive: true});
}

// ---- SpO2 ----
if (spo2Dates.length > 0) {
    Plotly.newPlot('chart_spo2', [
        { x: spo2Dates, y: spo2Values, type: 'scatter', mode: 'lines',
          name: '血氧饱和度', line: { color: '#FF2D55', width: 1.2 } },
    ], {
        ...layoutDefaults,
        title: { text: '血氧饱和度 SpO2 (%)', font: { size: 15 } },
        xaxis: dailyXaxis,
        yaxis: { ...layoutDefaults.yaxis, title: '%', range: [90, 100] },
    }, {responsive: true});
}

// ---- Heatmap: Calendar ----
(function() {
    // Create a heatmap of sleep duration by day
    const sleepByDate = {};
    for (let i = 0; i < dates.length; i++) {
        sleepByDate[dates[i]] = totalSleep[i];
    }
    
    // Group by month for y-axis, day for x-axis
    const months = [...new Set(dates.map(d => d.substring(0, 7)))].sort();
    const zData = [];
    const xLabels = [];
    for (let d = 1; d <= 31; d++) xLabels.push(d.toString());
    
    for (const month of months) {
        const row = [];
        for (let d = 1; d <= 31; d++) {
            const key = month + '-' + String(d).padStart(2, '0');
            row.push(sleepByDate[key] || null);
        }
        zData.push(row);
    }
    
    Plotly.newPlot('chart_heatmap', [{
        z: zData, x: xLabels, y: months,
        type: 'heatmap',
        colorscale: [
            [0, '#FF3B30'], [0.3, '#FF9500'], [0.5, '#FFCC00'],
            [0.7, '#34C759'], [1, '#5856D6']
        ],
        zmin: 3, zmax: 10,
        colorbar: { title: '小时', thickness: 15 },
        hoverongaps: false,
    }], {
        ...layoutDefaults,
        title: { text: '每日睡眠时长热力图', font: { size: 15 } },
        xaxis: { ...layoutDefaults.xaxis, title: '日', dtick: 2, tickfont: { size: 10 } },
        yaxis: { ...layoutDefaults.yaxis, title: '', autorange: 'reversed', dtick: 3, tickfont: { size: 10 } },
        height: Math.max(400, months.length * 22 + 100),
    }, {responsive: true});
})();

// ---- Insights & Recommendations ----
(function() {
    const container = document.getElementById('insights_container');
    const insights = [];
    const periods = """ + json.dumps({k: v for k, v in stats['periods'].items()}) + """;
    
    // Analyze pregnancy impact
    const pre = periods.pre_pregnancy;
    const preg = periods.pregnancy;
    const post = periods.postpartum;
    
    if (pre && preg) {
        const sleepDiff = (preg.avg_asleep - pre.avg_asleep);
        const direction = sleepDiff > 0 ? '增加' : '减少';
        insights.push({
            type: sleepDiff > 0 ? 'good' : 'warning',
            title: '孕期睡眠变化',
            text: `孕期平均睡眠时长相比孕前${direction}了 ${Math.abs(sleepDiff).toFixed(0)} 分钟。` +
                  `孕前平均 ${(pre.avg_asleep/60).toFixed(1)}h，孕期 ${(preg.avg_asleep/60).toFixed(1)}h。` +
                  (sleepDiff < -30 ? ' 孕期睡眠减少较多，可能与孕期不适、夜尿增多等因素有关。' : 
                   sleepDiff > 30 ? ' 孕期睡眠增加，身体可能需要更多休息来支持胎儿发育。' : '')
        });
    }
    
    if (preg && post) {
        const effDiff = post.avg_efficiency - preg.avg_efficiency;
        insights.push({
            type: effDiff > 0 ? 'good' : 'warning',
            title: '产后恢复情况',
            text: `产后睡眠效率为 ${post.avg_efficiency.toFixed(0)}%，` +
                  `相比孕期(${preg.avg_efficiency.toFixed(0)}%)` +
                  `${effDiff > 0 ? '提高' : '下降'}了 ${Math.abs(effDiff).toFixed(1)} 个百分点。` +
                  `产后平均睡眠 ${(post.avg_asleep/60).toFixed(1)}h。`
        });
    }
    
    // Recent sleep quality
    const recentAvg = """ + json.dumps(round(recent_avg_sleep, 1)) + """;
    if (recentAvg < 7) {
        insights.push({
            type: 'warning',
            title: '近期睡眠不足',
            text: `近30天平均睡眠 ${recentAvg}h，低于成年人推荐的 7-9 小时。长期睡眠不足会影响免疫力、认知功能和情绪调节。建议尝试提前30分钟上床。`
        });
    } else {
        insights.push({
            type: 'good',
            title: '近期睡眠充足',
            text: `近30天平均睡眠 ${recentAvg}h，处于推荐范围（7-9小时）。继续保持良好的作息习惯！`
        });
    }
    
    // Bedtime consistency
    const btStd = bedtimes.reduce((sum, v) => sum + Math.pow(v - bedtimes.reduce((a,b)=>a+b,0)/bedtimes.length, 2), 0) / bedtimes.length;
    const btStdDev = Math.sqrt(btStd);
    if (btStdDev > 1.5) {
        insights.push({
            type: 'warning',
            title: '作息不规律',
            text: `入睡时间波动较大（标准差 ${(btStdDev*60).toFixed(0)} 分钟），规律的作息时间是良好睡眠的基础。建议设置固定的"睡前仪式"提醒，即使周末也保持相近的作息。`
        });
    }
    
    // Recommendations
    insights.push({
        type: 'info',
        title: '📋 个性化改善建议',
        text: ''
    });
    
    let recHTML = '<div class="rec-grid">';
    
    const recs = [
        { title: '🌡️ 优化睡眠环境', text: '保持卧室温度在 18-22°C，使用遮光窗帘。腕温数据显示体温变化可作为睡眠质量的指标。' },
        { title: '📱 限制蓝光暴露', text: '睡前1小时减少电子屏幕使用，或使用夜间模式。蓝光会抑制褪黑素分泌。' },
        { title: '🏃‍♀️ 运动时间优化', text: '你有丰富的运动数据（力量训练+游泳），建议将高强度运动安排在下午，避免睡前3小时内剧烈运动。' },
        { title: '☕ 控制咖啡因摄入', text: '下午2点后避免咖啡因。咖啡因的半衰期约5-6小时，会影响深睡眠质量。' },
        { title: '🧘 建立睡前仪式', text: '建议睡前30分钟开始"降档"：调暗灯光、轻度伸展或呼吸练习，帮助身体进入睡眠准备状态。' },
        { title: '📊 持续监测', text: '继续佩戴 Apple Watch 监测睡眠。关注 HRV、呼吸扰动等指标的变化趋势，它们是睡眠质量的敏感指标。' },
    ];
    
    recs.forEach(r => {
        recHTML += `<div class="rec-card"><div class="rec-title">${r.title}</div><div class="rec-text">${r.text}</div></div>`;
    });
    recHTML += '</div>';
    
    let html = '';
    insights.forEach(ins => {
        if (ins.text === '') {
            html += recHTML;
        } else {
            const cls = ins.type === 'warning' ? 'warning' : ins.type === 'good' ? 'good' : '';
            html += `<div class="insight-box ${cls}"><div class="insight-title">${ins.title}</div>${ins.text}</div>`;
        }
    });
    
    container.innerHTML = html;
})();

</script>
</body>
</html>"""
    
    return html


# ============================================================
# Main
# ============================================================
def main():
    print("Processing sleep data...")
    nights = process_sleep_data()
    print(f"  Processed {len(nights)} valid nights")
    
    print("Processing auxiliary data...")
    hrv = process_hrv_data()
    rhr = process_resting_hr()
    wrist_temp = process_wrist_temp()
    breathing = process_breathing_disturbances()
    resp_rate = process_respiratory_rate()
    spo2 = process_spo2()
    hr_daily = process_heartrate_daily()
    
    print(f"  HRV: {len(hrv)} days, RHR: {len(rhr)} days")
    print(f"  WristTemp: {len(wrist_temp)} days, Breathing: {len(breathing)} days")
    print(f"  RespRate: {len(resp_rate)} days, SpO2: {len(spo2)} days")
    
    print("Computing statistics...")
    stats = compute_stats(nights)
    
    print("Generating dashboard...")
    html = generate_dashboard(nights, hrv, rhr, wrist_temp, breathing, resp_rate, spo2, hr_daily, stats)
    
    output_path = os.path.join(os.path.dirname(__file__), 'sleep_analysis_report.html')
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"\nDashboard saved to: {output_path}")
    print(f"Open in browser to view interactive charts.")


if __name__ == '__main__':
    main()
