#!/usr/bin/env python3
"""
Whoop Chart Generator - Creates interactive HTML charts from Whoop data (ApexCharts)

Usage:
    # Sleep chart (last 30 days)
    python3 whoop_chart.py sleep [--days N] [--start DATE] [--end DATE] [--output FILE]

    # Recovery chart
    python3 whoop_chart.py recovery [--days N] [--output FILE]

    # Strain chart
    python3 whoop_chart.py strain [--days N] [--output FILE]

    # Combined dashboard (all metrics)
    python3 whoop_chart.py dashboard [--days N] [--output FILE]

    # HRV trend
    python3 whoop_chart.py hrv [--days N] [--output FILE]

Output: Interactive HTML file (opens in browser by default)
"""

import argparse
import json
import os
import sys
import tempfile
import webbrowser
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from whoop_data import get_sleep, get_recovery, get_cycles, get_workouts

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Whoop - {title}</title>
    <script src="https://cdn.jsdelivr.net/npm/apexcharts"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #1a1a2e;
            color: #eee;
            padding: 20px;
            min-height: 100vh;
        }}
        .header {{
            text-align: center;
            margin-bottom: 30px;
        }}
        .header h1 {{
            font-size: 1.8em;
            color: #00f5d4;
            margin-bottom: 5px;
        }}
        .header p {{
            color: #888;
            font-size: 0.9em;
        }}
        .stats {{
            display: flex;
            gap: 15px;
            flex-wrap: wrap;
            justify-content: center;
            margin-bottom: 30px;
        }}
        .stat-card {{
            background: #16213e;
            border-radius: 12px;
            padding: 15px 25px;
            text-align: center;
            min-width: 140px;
            border: 1px solid #0f3460;
        }}
        .stat-card .value {{
            font-size: 1.8em;
            font-weight: bold;
            color: #00f5d4;
        }}
        .stat-card .label {{
            font-size: 0.8em;
            color: #888;
            margin-top: 4px;
        }}
        .chart-container {{
            background: #16213e;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 20px;
            border: 1px solid #0f3460;
        }}
        .chart-container h3 {{
            color: #ccc;
            font-size: 0.95em;
            margin-bottom: 10px;
            padding-left: 5px;
        }}
        .dashboard-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }}
        @media (max-width: 768px) {{
            .dashboard-grid {{ grid-template-columns: 1fr; }}
        }}
        .recovery-green {{ color: #00c853; }}
        .recovery-yellow {{ color: #ffd600; }}
        .recovery-red {{ color: #ff1744; }}
        .no-data {{
            text-align: center;
            color: #888;
            padding: 40px 10px;
            font-size: 1rem;
        }}
        .footer {{
            text-align: center;
            color: #555;
            font-size: 0.75em;
            margin-top: 30px;
            padding-top: 15px;
            border-top: 1px solid #0f3460;
        }}
        .apexcharts-tooltip {{
            background: #16213e !important;
            border: 1px solid #0f3460 !important;
            color: #eee !important;
        }}
        .apexcharts-tooltip-title {{
            background: #0f3460 !important;
            color: #eee !important;
            border-bottom: 1px solid #1a1a2e !important;
        }}
        .apexcharts-xaxistooltip {{
            background: #16213e !important;
            border: 1px solid #0f3460 !important;
            color: #eee !important;
        }}
        .apexcharts-xaxistooltip-bottom::before,
        .apexcharts-xaxistooltip-bottom::after {{
            border-bottom-color: #0f3460 !important;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🏋️ {title}</h1>
        <p>{subtitle}</p>
    </div>
    {stats_html}
    {charts_html}
    <div class="footer">Last updated: {timestamp}</div>
    <script>
        const chartData = {chart_data};
        {chart_scripts}
    </script>
</body>
</html>"""


def format_date_short(iso_date):
    """Convert ISO date string to short format like 'Jan 24'."""
    dt = datetime.strptime(iso_date[:10], "%Y-%m-%d")
    return dt.strftime("%b %d").replace(" 0", " ")


def recovery_color(score):
    if score >= 67:
        return "#00c853"
    elif score >= 34:
        return "#ffd600"
    return "#ff1744"


def compute_moving_average(values, window=7):
    """Compute a simple moving average with given window size."""
    result = []
    for i in range(len(values)):
        start = max(0, i - window + 1)
        window_vals = [v for v in values[start:i+1] if v is not None]
        if window_vals:
            result.append(round(sum(window_vals) / len(window_vals), 1))
        else:
            result.append(None)
    return result


def build_sleep_chart(days=30, start=None, end=None):
    """Build sleep chart data."""
    data = get_sleep(days=days, start=start, end=end)
    records = sorted(data["records"], key=lambda r: r["start"])

    dates = []
    short_dates = []
    performances = []
    hours_slept = []
    deep_sleep = []
    rem_sleep = []
    light_sleep = []

    for r in records:
        if not r.get("score") or r.get("nap"):
            continue
        dates.append(r["start"][:10])
        short_dates.append(format_date_short(r["start"][:10]))
        performances.append(r["score"].get("sleep_performance_percentage"))
        ss = r["score"].get("stage_summary", {})
        total = ss.get("total_in_bed_time_milli", 0)
        awake = ss.get("total_awake_time_milli", 0)
        hours_slept.append(round((total - awake) / 3600000, 1))
        deep_sleep.append(round(ss.get("total_slow_wave_sleep_time_milli", 0) / 3600000, 2))
        rem_sleep.append(round(ss.get("total_rem_sleep_time_milli", 0) / 3600000, 2))
        light_sleep.append(round(ss.get("total_light_sleep_time_milli", 0) / 3600000, 2))

    avg_perf = round(sum(p for p in performances if p) / max(len([p for p in performances if p]), 1), 1)
    avg_hours = round(sum(hours_slept) / max(len(hours_slept), 1), 1)

    stats = f"""
    <div class="stats">
        <div class="stat-card"><div class="value">{avg_perf}%</div><div class="label">Avg Performance</div></div>
        <div class="stat-card"><div class="value">{avg_hours}h</div><div class="label">Avg Sleep</div></div>
        <div class="stat-card"><div class="value">{len(records)}</div><div class="label">Nights</div></div>
    </div>"""

    charts = '<div class="chart-container"><h3>Sleep Performance & Duration</h3><div id="sleepChart"></div></div>'
    charts += '<div class="chart-container"><h3>Sleep Stages</h3><div id="sleepStagesChart"></div></div>'

    chart_data = {
        "dates": dates,
        "short_dates": short_dates,
        "performances": performances,
        "hours": hours_slept,
        "deep": deep_sleep,
        "rem": rem_sleep,
        "light": light_sleep,
    }

    scripts = """
    var sleepOpts = {
        chart: {
            type: 'line',
            height: 350,
            background: 'transparent',
            toolbar: { show: true, tools: { download: true, zoom: true, zoomin: true, zoomout: true, pan: true, reset: true } },
            zoom: { enabled: true },
            animations: { enabled: true, easing: 'easeinout', speed: 800, dynamicAnimation: { speed: 350 } }
        },
        series: [{
            name: 'Sleep Performance',
            type: 'line',
            data: chartData.performances
        }, {
            name: 'Hours Slept',
            type: 'line',
            data: chartData.hours
        }],
        xaxis: {
            categories: chartData.short_dates,
            labels: { style: { colors: '#888' } },
            axisBorder: { color: '#333' },
            axisTicks: { color: '#333' }
        },
        yaxis: [{
            title: { text: 'Performance %', style: { color: '#888' } },
            min: 0, max: 100,
            labels: { style: { colors: '#888' } }
        }, {
            opposite: true,
            title: { text: 'Hours', style: { color: '#888' } },
            min: 0,
            labels: { style: { colors: '#888' } }
        }],
        colors: ['#00f5d4', '#7b68ee'],
        stroke: { curve: 'smooth', width: [3, 3] },
        fill: {
            type: 'gradient',
            gradient: { shadeIntensity: 1, opacityFrom: 0.4, opacityTo: 0.05, stops: [0, 90, 100] }
        },
        grid: { borderColor: '#333', strokeDashArray: 3 },
        tooltip: {
            theme: 'dark',
            shared: true,
            x: { formatter: function(val, opts) { return chartData.dates[opts.dataPointIndex] ? chartData.dates[opts.dataPointIndex] : val; } },
            y: { formatter: function(val, opts) { return opts.seriesIndex === 0 ? val + '%' : val + 'h'; } }
        },
        legend: { labels: { colors: '#eee' } },
        theme: { mode: 'dark' }
    };
    new ApexCharts(document.getElementById('sleepChart'), sleepOpts).render();

    var sleepStagesOpts = {
        chart: {
            type: 'area',
            height: 350,
            stacked: true,
            background: 'transparent',
            toolbar: { show: true, tools: { download: true, zoom: true, zoomin: true, zoomout: true, pan: true, reset: true } },
            zoom: { enabled: true },
            animations: { enabled: true, easing: 'easeinout', speed: 800 }
        },
        series: [{
            name: 'Deep Sleep',
            data: chartData.deep
        }, {
            name: 'REM Sleep',
            data: chartData.rem
        }, {
            name: 'Light Sleep',
            data: chartData.light
        }],
        xaxis: {
            categories: chartData.short_dates,
            labels: { style: { colors: '#888' } },
            axisBorder: { color: '#333' },
            axisTicks: { color: '#333' }
        },
        yaxis: {
            title: { text: 'Hours', style: { color: '#888' } },
            labels: { style: { colors: '#888' } }
        },
        colors: ['#1a237e', '#7b68ee', '#4fc3f7'],
        stroke: { curve: 'smooth', width: 2 },
        fill: {
            type: 'gradient',
            gradient: { shadeIntensity: 1, opacityFrom: 0.7, opacityTo: 0.3, stops: [0, 90, 100] }
        },
        grid: { borderColor: '#333', strokeDashArray: 3 },
        tooltip: {
            theme: 'dark',
            shared: true,
            y: { formatter: function(val) { return val ? val.toFixed(1) + 'h' : '0h'; } }
        },
        legend: { labels: { colors: '#eee' } },
        theme: { mode: 'dark' }
    };
    new ApexCharts(document.getElementById('sleepStagesChart'), sleepStagesOpts).render();
    """

    return "Sleep Analysis", f"Last {days} days", stats, charts, chart_data, scripts


def build_recovery_chart(days=30, start=None, end=None):
    """Build recovery chart data."""
    data = get_recovery(days=days, start=start, end=end)
    records = sorted(data["records"], key=lambda r: r["created_at"])

    dates = []
    short_dates = []
    scores = []
    hrvs = []
    rhrs = []
    colors = []

    for r in records:
        if not r.get("score"):
            continue
        dates.append(r["created_at"][:10])
        short_dates.append(format_date_short(r["created_at"][:10]))
        score = r["score"].get("recovery_score", 0)
        scores.append(score)
        hrvs.append(round(r["score"].get("hrv_rmssd_milli", 0), 1))
        rhrs.append(r["score"].get("resting_heart_rate", 0))
        colors.append(recovery_color(score))

    avg_score = round(sum(scores) / max(len(scores), 1), 1)
    avg_hrv = round(sum(hrvs) / max(len(hrvs), 1), 1)
    avg_rhr = round(sum(rhrs) / max(len(rhrs), 1))

    stats = f"""
    <div class="stats">
        <div class="stat-card"><div class="value">{avg_score}%</div><div class="label">Avg Recovery</div></div>
        <div class="stat-card"><div class="value">{avg_hrv}ms</div><div class="label">Avg HRV</div></div>
        <div class="stat-card"><div class="value">{avg_rhr}bpm</div><div class="label">Avg RHR</div></div>
    </div>"""

    charts = '<div class="chart-container"><h3>Recovery Score</h3><div id="recoveryChart"></div></div>'

    chart_data = {"dates": dates, "short_dates": short_dates, "scores": scores, "hrvs": hrvs, "rhrs": rhrs, "colors": colors}

    scripts = """
    var recoveryOpts = {
        chart: {
            type: 'bar',
            height: 380,
            background: 'transparent',
            toolbar: { show: true, tools: { download: true, zoom: true, zoomin: true, zoomout: true, pan: true, reset: true } },
            zoom: { enabled: true },
            animations: { enabled: true, easing: 'easeinout', speed: 800, dynamicAnimation: { speed: 350 } }
        },
        series: [{ name: 'Recovery', data: chartData.scores }],
        xaxis: {
            categories: chartData.short_dates,
            labels: { style: { colors: '#888' } },
            axisBorder: { color: '#333' },
            axisTicks: { color: '#333' }
        },
        yaxis: {
            min: 0, max: 100,
            title: { text: 'Recovery %', style: { color: '#888' } },
            labels: { style: { colors: '#888' } }
        },
        plotOptions: {
            bar: {
                borderRadius: 4,
                distributed: true,
                columnWidth: '70%'
            }
        },
        colors: chartData.colors,
        grid: { borderColor: '#333', strokeDashArray: 3 },
        tooltip: {
            theme: 'dark',
            x: { formatter: function(val, opts) { return chartData.dates[opts.dataPointIndex]; } },
            y: { formatter: function(val) { return val + '%'; } }
        },
        annotations: {
            yaxis: [{
                y: 67, y2: 100,
                borderColor: 'transparent',
                fillColor: '#00c853',
                opacity: 0.08,
                label: { text: 'Green', style: { color: '#00c853', background: 'transparent', fontSize: '10px' }, position: 'front', offsetX: -5 }
            }, {
                y: 34, y2: 66.9,
                borderColor: 'transparent',
                fillColor: '#ffd600',
                opacity: 0.06,
                label: { text: 'Yellow', style: { color: '#ffd600', background: 'transparent', fontSize: '10px' }, position: 'front', offsetX: -5 }
            }, {
                y: 0, y2: 33.9,
                borderColor: 'transparent',
                fillColor: '#ff1744',
                opacity: 0.06,
                label: { text: 'Red', style: { color: '#ff1744', background: 'transparent', fontSize: '10px' }, position: 'front', offsetX: -5 }
            }]
        },
        legend: { show: false },
        theme: { mode: 'dark' }
    };
    new ApexCharts(document.getElementById('recoveryChart'), recoveryOpts).render();
    """

    return "Recovery", f"Last {days} days", stats, charts, chart_data, scripts


def build_strain_chart(days=30, start=None, end=None):
    """Build strain chart data."""
    data = get_cycles(days=days, start=start, end=end)
    records = sorted(data["records"], key=lambda r: r["start"])

    dates = []
    short_dates = []
    strains = []
    cals = []

    for r in records:
        if not r.get("score"):
            continue
        dates.append(r["start"][:10])
        short_dates.append(format_date_short(r["start"][:10]))
        strains.append(round(r["score"].get("strain", 0), 1))
        cals.append(round(r["score"].get("kilojoule", 0) / 4.184))  # kJ to kcal

    avg_strain = round(sum(strains) / max(len(strains), 1), 1)
    avg_cals = round(sum(cals) / max(len(cals), 1))

    stats = f"""
    <div class="stats">
        <div class="stat-card"><div class="value">{avg_strain}</div><div class="label">Avg Strain</div></div>
        <div class="stat-card"><div class="value">{avg_cals}</div><div class="label">Avg Calories</div></div>
        <div class="stat-card"><div class="value">{len(records)}</div><div class="label">Days</div></div>
    </div>"""

    charts = '<div class="chart-container"><h3>Strain & Calories</h3><div id="strainChart"></div></div>'

    chart_data = {"dates": dates, "short_dates": short_dates, "strains": strains, "cals": cals}

    scripts = """
    var strainOpts = {
        chart: {
            type: 'line',
            height: 380,
            background: 'transparent',
            toolbar: { show: true, tools: { download: true, zoom: true, zoomin: true, zoomout: true, pan: true, reset: true } },
            zoom: { enabled: true },
            animations: { enabled: true, easing: 'easeinout', speed: 800, dynamicAnimation: { speed: 350 } }
        },
        series: [{
            name: 'Day Strain',
            data: chartData.strains
        }, {
            name: 'Calories',
            data: chartData.cals
        }],
        xaxis: {
            categories: chartData.short_dates,
            labels: { style: { colors: '#888' } },
            axisBorder: { color: '#333' },
            axisTicks: { color: '#333' }
        },
        yaxis: [{
            title: { text: 'Strain', style: { color: '#888' } },
            min: 0,
            labels: { style: { colors: '#888' } }
        }, {
            opposite: true,
            title: { text: 'Calories', style: { color: '#888' } },
            min: 0,
            labels: { style: { colors: '#888' } }
        }],
        colors: ['#ff6b35', '#ffd600'],
        stroke: { curve: 'smooth', width: [3, 3] },
        fill: {
            type: 'gradient',
            gradient: { shadeIntensity: 1, opacityFrom: 0.4, opacityTo: 0.05, stops: [0, 90, 100] }
        },
        grid: { borderColor: '#333', strokeDashArray: 3 },
        tooltip: {
            theme: 'dark',
            shared: true,
            x: { formatter: function(val, opts) { return chartData.dates[opts.dataPointIndex] || val; } },
            y: { formatter: function(val, opts) { return opts.seriesIndex === 1 ? val + ' kcal' : val.toFixed(1); } }
        },
        legend: { labels: { colors: '#eee' } },
        theme: { mode: 'dark' }
    };
    new ApexCharts(document.getElementById('strainChart'), strainOpts).render();
    """

    return "Strain & Calories", f"Last {days} days", stats, charts, chart_data, scripts


def build_hrv_chart(days=30, start=None, end=None):
    """Build HRV trend chart."""
    data = get_recovery(days=days, start=start, end=end)
    records = sorted(data["records"], key=lambda r: r["created_at"])

    dates = []
    short_dates = []
    hrvs = []
    rhrs = []

    for r in records:
        if not r.get("score"):
            continue
        dates.append(r["created_at"][:10])
        short_dates.append(format_date_short(r["created_at"][:10]))
        hrvs.append(round(r["score"].get("hrv_rmssd_milli", 0), 1))
        rhrs.append(r["score"].get("resting_heart_rate", 0))

    # Compute 7-day moving average
    hrv_ma = compute_moving_average(hrvs, window=7)

    avg_hrv = round(sum(hrvs) / max(len(hrvs), 1), 1)
    min_hrv = round(min(hrvs)) if hrvs else 0
    max_hrv = round(max(hrvs)) if hrvs else 0

    stats = f"""
    <div class="stats">
        <div class="stat-card"><div class="value">{avg_hrv}ms</div><div class="label">Avg HRV</div></div>
        <div class="stat-card"><div class="value">{min_hrv}ms</div><div class="label">Min HRV</div></div>
        <div class="stat-card"><div class="value">{max_hrv}ms</div><div class="label">Max HRV</div></div>
    </div>"""

    charts = '<div class="chart-container"><h3>HRV & Resting Heart Rate</h3><div id="hrvChart"></div></div>'

    chart_data = {"dates": dates, "short_dates": short_dates, "hrvs": hrvs, "hrv_ma": hrv_ma, "rhrs": rhrs}

    scripts = """
    var hrvOpts = {
        chart: {
            type: 'line',
            height: 380,
            background: 'transparent',
            toolbar: { show: true, tools: { download: true, zoom: true, zoomin: true, zoomout: true, pan: true, reset: true } },
            zoom: { enabled: true },
            animations: { enabled: true, easing: 'easeinout', speed: 800, dynamicAnimation: { speed: 350 } }
        },
        series: [{
            name: 'HRV',
            data: chartData.hrvs
        }, {
            name: 'HRV 7-day Avg',
            data: chartData.hrv_ma
        }, {
            name: 'Resting HR',
            data: chartData.rhrs
        }],
        xaxis: {
            categories: chartData.short_dates,
            labels: { style: { colors: '#888' } },
            axisBorder: { color: '#333' },
            axisTicks: { color: '#333' }
        },
        yaxis: [{
            title: { text: 'HRV (ms)', style: { color: '#888' } },
            min: 0,
            labels: { style: { colors: '#888' } }
        }, {
            show: false,
            min: 0
        }, {
            opposite: true,
            title: { text: 'RHR (bpm)', style: { color: '#888' } },
            min: 0,
            labels: { style: { colors: '#888' } }
        }],
        colors: ['#00f5d4', '#00a896', '#ff6b6b'],
        stroke: { curve: 'smooth', width: [2, 3, 2], dashArray: [0, 0, 0] },
        fill: {
            type: ['gradient', 'none', 'gradient'],
            gradient: { shadeIntensity: 1, opacityFrom: 0.3, opacityTo: 0.05, stops: [0, 90, 100] }
        },
        grid: { borderColor: '#333', strokeDashArray: 3 },
        tooltip: {
            theme: 'dark',
            shared: true,
            x: { formatter: function(val, opts) { return chartData.dates[opts.dataPointIndex] || val; } },
            y: { formatter: function(val, opts) { return opts.seriesIndex === 2 ? val + ' bpm' : val + ' ms'; } }
        },
        legend: { labels: { colors: '#eee' } },
        theme: { mode: 'dark' }
    };
    new ApexCharts(document.getElementById('hrvChart'), hrvOpts).render();
    """

    return "HRV & Resting Heart Rate", f"Last {days} days", stats, charts, chart_data, scripts


def build_dashboard(days=30, start=None, end=None):
    """Build combined dashboard."""
    # Fetch all data
    sleep_data = get_sleep(days=days, start=start, end=end)
    recovery_data = get_recovery(days=days, start=start, end=end)
    cycles_data = get_cycles(days=days, start=start, end=end)

    sleep_records = sorted(sleep_data["records"], key=lambda r: r["start"])
    recovery_records = sorted(recovery_data["records"], key=lambda r: r["created_at"])
    cycle_records = sorted(cycles_data["records"], key=lambda r: r["start"])

    # Process sleep data
    dates_sleep = []
    short_dates_sleep = []
    performances = []
    hours = []
    for r in sleep_records:
        if not r.get("score") or r.get("nap"):
            continue
        dates_sleep.append(r["start"][:10])
        short_dates_sleep.append(format_date_short(r["start"][:10]))
        performances.append(r["score"].get("sleep_performance_percentage"))
        ss = r["score"].get("stage_summary", {})
        total = ss.get("total_in_bed_time_milli", 0)
        awake = ss.get("total_awake_time_milli", 0)
        hours.append(round((total - awake) / 3600000, 1))

    # Process recovery data
    dates_rec = []
    short_dates_rec = []
    scores = []
    hrvs = []
    rec_colors = []
    for r in recovery_records:
        if not r.get("score"):
            continue
        dates_rec.append(r["created_at"][:10])
        short_dates_rec.append(format_date_short(r["created_at"][:10]))
        score = r["score"].get("recovery_score", 0)
        scores.append(score)
        hrvs.append(round(r["score"].get("hrv_rmssd_milli", 0), 1))
        rec_colors.append(recovery_color(score))

    # Process strain data
    dates_strain = []
    short_dates_strain = []
    strains = []
    for r in cycle_records:
        if not r.get("score"):
            continue
        dates_strain.append(r["start"][:10])
        short_dates_strain.append(format_date_short(r["start"][:10]))
        strains.append(round(r["score"].get("strain", 0), 1))

    # Compute HRV moving average
    hrv_ma = compute_moving_average(hrvs, window=7)

    # Stats
    avg_perf = round(sum(p for p in performances if p) / max(len([p for p in performances if p]), 1), 1)
    avg_score = round(sum(scores) / max(len(scores), 1), 1)
    avg_strain = round(sum(strains) / max(len(strains), 1), 1)
    avg_hrv = round(sum(hrvs) / max(len(hrvs), 1), 1)

    stats = f"""
    <div class="stats">
        <div class="stat-card"><div class="value">{avg_score}%</div><div class="label">Avg Recovery</div></div>
        <div class="stat-card"><div class="value">{avg_perf}%</div><div class="label">Avg Sleep Perf</div></div>
        <div class="stat-card"><div class="value">{avg_strain}</div><div class="label">Avg Strain</div></div>
        <div class="stat-card"><div class="value">{avg_hrv}ms</div><div class="label">Avg HRV</div></div>
    </div>"""

    charts = """
    <div class="dashboard-grid">
        <div class="chart-container"><h3>Recovery</h3><div id="recoveryChart"></div></div>
        <div class="chart-container"><h3>Sleep Performance</h3><div id="sleepChart"></div></div>
        <div class="chart-container"><h3>Day Strain</h3><div id="strainChart"></div></div>
        <div class="chart-container"><h3>HRV Trend</h3><div id="hrvChart"></div></div>
    </div>"""

    chart_data = {
        "dates_sleep": dates_sleep, "short_dates_sleep": short_dates_sleep,
        "performances": performances, "hours": hours,
        "dates_rec": dates_rec, "short_dates_rec": short_dates_rec,
        "scores": scores, "rec_colors": rec_colors,
        "dates_strain": dates_strain, "short_dates_strain": short_dates_strain,
        "strains": strains,
        "hrvs": hrvs, "hrv_ma": hrv_ma,
    }

    scripts = """
    // Recovery chart with zone annotations
    new ApexCharts(document.getElementById('recoveryChart'), {
        chart: { type: 'bar', height: 280, background: 'transparent',
            toolbar: { show: true, tools: { download: true, zoom: true, pan: true, reset: true } },
            zoom: { enabled: true },
            animations: { enabled: true, easing: 'easeinout', speed: 800 }
        },
        series: [{ name: 'Recovery', data: chartData.scores }],
        xaxis: { categories: chartData.short_dates_rec, labels: { style: { colors: '#888' }, rotate: -45 }, axisBorder: { color: '#333' } },
        yaxis: { min: 0, max: 100, labels: { style: { colors: '#888' } } },
        plotOptions: { bar: { borderRadius: 3, distributed: true, columnWidth: '75%' } },
        colors: chartData.rec_colors,
        grid: { borderColor: '#333', strokeDashArray: 3 },
        annotations: {
            yaxis: [
                { y: 67, y2: 100, fillColor: '#00c853', opacity: 0.07 },
                { y: 34, y2: 66.9, fillColor: '#ffd600', opacity: 0.05 },
                { y: 0, y2: 33.9, fillColor: '#ff1744', opacity: 0.05 }
            ]
        },
        tooltip: { theme: 'dark', y: { formatter: function(val) { return val + '%'; } } },
        legend: { show: false },
        theme: { mode: 'dark' }
    }).render();

    // Sleep performance chart
    new ApexCharts(document.getElementById('sleepChart'), {
        chart: { type: 'area', height: 280, background: 'transparent',
            toolbar: { show: true, tools: { download: true, zoom: true, pan: true, reset: true } },
            zoom: { enabled: true },
            animations: { enabled: true, easing: 'easeinout', speed: 800 }
        },
        series: [{ name: 'Sleep Performance', data: chartData.performances }, { name: 'Hours Slept', data: chartData.hours }],
        xaxis: { categories: chartData.short_dates_sleep, labels: { style: { colors: '#888' }, rotate: -45 }, axisBorder: { color: '#333' } },
        yaxis: [
            { min: 0, max: 100, title: { text: '%', style: { color: '#888' } }, labels: { style: { colors: '#888' } } },
            { opposite: true, min: 0, max: 12, title: { text: 'Hours', style: { color: '#888' } }, labels: { style: { colors: '#888' } } }
        ],
        colors: ['#7b68ee', '#00f5d4'],
        stroke: { curve: 'smooth', width: [3, 2] },
        fill: { type: 'gradient', gradient: { shadeIntensity: 1, opacityFrom: 0.35, opacityTo: 0.0, stops: [0, 95, 100] } },
        grid: { borderColor: '#333', strokeDashArray: 3 },
        tooltip: { theme: 'dark', shared: true },
        legend: { labels: { colors: '#eee' } },
        theme: { mode: 'dark' }
    }).render();

    // Strain chart
    new ApexCharts(document.getElementById('strainChart'), {
        chart: { type: 'area', height: 280, background: 'transparent',
            toolbar: { show: true, tools: { download: true, zoom: true, pan: true, reset: true } },
            zoom: { enabled: true },
            animations: { enabled: true, easing: 'easeinout', speed: 800 }
        },
        series: [{ name: 'Day Strain', data: chartData.strains }],
        xaxis: { categories: chartData.short_dates_strain, labels: { style: { colors: '#888' }, rotate: -45 }, axisBorder: { color: '#333' } },
        yaxis: { min: 0, max: 21, title: { text: 'Strain', style: { color: '#888' } }, labels: { style: { colors: '#888' } } },
        colors: ['#ff6b35'],
        stroke: { curve: 'smooth', width: 3 },
        fill: { type: 'gradient', gradient: { shadeIntensity: 1, opacityFrom: 0.35, opacityTo: 0.0, stops: [0, 95, 100] } },
        grid: { borderColor: '#333', strokeDashArray: 3 },
        tooltip: { theme: 'dark', y: { formatter: function(val) { return val.toFixed(1); } } },
        legend: { labels: { colors: '#eee' } },
        theme: { mode: 'dark' }
    }).render();

    // HRV chart with 7-day moving average
    new ApexCharts(document.getElementById('hrvChart'), {
        chart: { type: 'line', height: 280, background: 'transparent',
            toolbar: { show: true, tools: { download: true, zoom: true, pan: true, reset: true } },
            zoom: { enabled: true },
            animations: { enabled: true, easing: 'easeinout', speed: 800 }
        },
        series: [{ name: 'HRV', type: 'area', data: chartData.hrvs }, { name: '7-day Avg', type: 'line', data: chartData.hrv_ma }],
        xaxis: { categories: chartData.short_dates_rec, labels: { style: { colors: '#888' }, rotate: -45 }, axisBorder: { color: '#333' } },
        yaxis: { min: 0, title: { text: 'HRV (ms)', style: { color: '#888' } }, labels: { style: { colors: '#888' } } },
        colors: ['#00f5d4', '#00a896'],
        stroke: { curve: 'smooth', width: [2, 3] },
        fill: { type: ['gradient', 'solid'], gradient: { shadeIntensity: 1, opacityFrom: 0.3, opacityTo: 0.0, stops: [0, 95, 100] }, opacity: [1, 0] },
        grid: { borderColor: '#333', strokeDashArray: 3 },
        tooltip: { theme: 'dark', shared: true, y: { formatter: function(val) { return val.toFixed(1) + ' ms'; } } },
        legend: { labels: { colors: '#eee' } },
        theme: { mode: 'dark' }
    }).render();
    """

    return "Health Dashboard", f"Last {days} days", stats, charts, chart_data, scripts


def generate_html(title, subtitle, stats_html, charts_html, chart_data, chart_scripts, output=None):
    """Generate and optionally open the HTML file."""
    has_data = any(
        isinstance(value, (list, tuple)) and len(value) > 0
        for value in (chart_data or {}).values()
    )
    if not has_data:
        stats_html = ""
        charts_html = '<div class="chart-container"><div class="no-data">No data available</div></div>'
        chart_data = {}
        chart_scripts = ""

    timestamp = datetime.now().strftime("%b %d, %Y at %I:%M %p")

    html = HTML_TEMPLATE.format(
        title=title,
        subtitle=subtitle,
        stats_html=stats_html,
        charts_html=charts_html,
        chart_data=json.dumps(chart_data),
        chart_scripts=chart_scripts,
        timestamp=timestamp,
    )

    if output:
        filepath = os.path.abspath(output)
        output_dir = os.path.dirname(filepath)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
    else:
        fd, filepath = tempfile.mkstemp(suffix=".html", prefix="whoop_")
        os.close(fd)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Chart saved to: {filepath}")

    # Open in browser
    try:
        webbrowser.open(f"file://{filepath}")
    except Exception:
        pass
    return filepath


def main():
    parser = argparse.ArgumentParser(description="Generate Whoop health charts")
    sub = parser.add_subparsers(dest="command")

    for cmd in ["sleep", "recovery", "strain", "hrv", "dashboard"]:
        p = sub.add_parser(cmd)
        p.add_argument("--days", type=int, default=30)
        p.add_argument("--start", help="ISO date")
        p.add_argument("--end", help="ISO date")
        p.add_argument("--output", "-o", help="Output HTML file path")

    args = parser.parse_args()

    builders = {
        "sleep": build_sleep_chart,
        "recovery": build_recovery_chart,
        "strain": build_strain_chart,
        "hrv": build_hrv_chart,
        "dashboard": build_dashboard,
    }

    if args.command not in builders:
        parser.print_help()
        sys.exit(1)

    title, subtitle, stats, charts, data, scripts = builders[args.command](
        days=args.days, start=args.start, end=args.end
    )
    generate_html(title, subtitle, stats, charts, data, scripts, args.output)


if __name__ == "__main__":
    main()
