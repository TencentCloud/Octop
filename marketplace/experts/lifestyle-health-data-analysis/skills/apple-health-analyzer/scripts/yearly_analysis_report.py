#!/usr/bin/env python3
"""
Apple Health 数据年份分布可视化报告 + 分析策略推荐
"""

import json
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px

# 读取统计数据
with open('/Users/shiyuan/Documents/Personal/apple_health_export/yearly_stats.json', 'r') as f:
    data = json.load(f)

stats = data['stats']
total_by_type = data['total_by_type']
date_range = data['date_range']
all_years = data['all_years']
yearly_totals = data['yearly_totals']
yearly_type_count = data['yearly_type_count']

# ============================================================
# 颜色方案
# ============================================================
COLOR_IPHONE = '#007AFF'      # Apple蓝
COLOR_WATCH = '#FF9500'       # Apple橙
COLOR_MANUAL = '#34C759'      # Apple绿
COLOR_WATCH_NEW = '#FF3B30'   # Apple红 (新款Watch)
COLOR_BG = '#FAFAFA'
COLOR_GRID = '#E5E5EA'
COLORS_YEAR = px.colors.sequential.Sunset

# ============================================================
# 数据分类
# ============================================================
iphone_types = ['StepCount', 'DistanceWalkingRunning', 'FlightsClimbed',
                'WalkingSpeed', 'WalkingStepLength', 'WalkingDoubleSupportPercentage',
                'WalkingAsymmetryPercentage', 'HeadphoneAudioExposure']

watch_early_types = ['HeartRate', 'ActiveEnergyBurned', 'SleepAnalysis']

watch_2025_types = ['RestingHeartRate', 'HeartRateVariabilitySDNN', 'WalkingHeartRateAverage',
                    'OxygenSaturation', 'RespiratoryRate', 'AppleSleepingWristTemperature',
                    'AppleSleepingBreathingDisturbances', 'TimeInDaylight', 'PhysicalEffort',
                    'BasalEnergyBurned', 'AppleExerciseTime', 'AppleStandTime', 'AppleStandHour',
                    'EnvironmentalAudioExposure', 'VO2Max']

manual_types_list = ['BodyMass', 'BodyMassIndex', 'BodyFatPercentage', 'MenstrualFlow']

# ============================================================
# 图1: 每年总记录数 + 数据类型数 (双轴)
# ============================================================
fig1 = make_subplots(specs=[[{"secondary_y": True}]])

# 按数据来源分段着色
colors_bar = []
for y in all_years:
    yi = int(y)
    if yi <= 2020:
        colors_bar.append(COLOR_IPHONE)
    elif yi <= 2024:
        colors_bar.append(COLOR_WATCH)
    else:
        colors_bar.append(COLOR_WATCH_NEW)

totals = [yearly_totals.get(y, 0) for y in all_years]
type_counts = [yearly_type_count.get(y, 0) for y in all_years]

fig1.add_trace(
    go.Bar(
        x=all_years, y=totals,
        name='总记录数',
        marker_color=colors_bar,
        text=[f'{t/1000:.0f}K' if t >= 1000 else str(t) for t in totals],
        textposition='outside',
        textfont=dict(size=11),
    ),
    secondary_y=False
)

fig1.add_trace(
    go.Scatter(
        x=all_years, y=type_counts,
        name='活跃数据类型数',
        mode='lines+markers+text',
        line=dict(color='#AF52DE', width=3),
        marker=dict(size=10),
        text=type_counts,
        textposition='top center',
        textfont=dict(size=11, color='#AF52DE'),
    ),
    secondary_y=True
)

# 添加阶段标注
fig1.add_vrect(x0=-0.5, x1=4.5, fillcolor=COLOR_IPHONE, opacity=0.05, line_width=0,
               annotation_text="📱 iPhone 阶段", annotation_position="top left",
               annotation_font_size=12)
fig1.add_vrect(x0=4.5, x1=8.5, fillcolor=COLOR_WATCH, opacity=0.05, line_width=0,
               annotation_text="⌚ Watch 过渡期", annotation_position="top left",
               annotation_font_size=12)
fig1.add_vrect(x0=8.5, x1=10.5, fillcolor=COLOR_WATCH_NEW, opacity=0.05, line_width=0,
               annotation_text="⌚ Watch 完整期", annotation_position="top left",
               annotation_font_size=12)

fig1.update_layout(
    title=dict(text='Apple Health 数据量随时间变化<br><sub>不同颜色代表不同的数据采集设备阶段</sub>',
               font_size=18, x=0.5),
    xaxis_title='年份',
    yaxis_title='总记录数',
    yaxis2_title='活跃数据类型数',
    template='plotly_white',
    height=500,
    legend=dict(orientation='h', yanchor='bottom', y=1.08, xanchor='center', x=0.5),
    margin=dict(t=120),
)

# ============================================================
# 图2: 关键数据类型的年份分布热力图
# ============================================================
key_types = [
    'StepCount', 'DistanceWalkingRunning', 'FlightsClimbed',
    'HeartRate', 'ActiveEnergyBurned', 'BasalEnergyBurned',
    'SleepAnalysis', 'HeadphoneAudioExposure',
    'WalkingSpeed', 'WalkingStepLength',
    'RestingHeartRate', 'HeartRateVariabilitySDNN',
    'OxygenSaturation', 'RespiratoryRate',
    'AppleSleepingWristTemperature', 'AppleSleepingBreathingDisturbances',
    'MenstrualFlow', 'BodyMass',
    'PhysicalEffort', 'AppleExerciseTime',
    'TimeInDaylight', 'VO2Max',
]

# 标注来源
source_labels = {
    'StepCount': '📱', 'DistanceWalkingRunning': '📱', 'FlightsClimbed': '📱',
    'HeartRate': '⌚', 'ActiveEnergyBurned': '⌚', 'BasalEnergyBurned': '⌚',
    'SleepAnalysis': '⌚', 'HeadphoneAudioExposure': '📱',
    'WalkingSpeed': '📱', 'WalkingStepLength': '📱',
    'RestingHeartRate': '⌚', 'HeartRateVariabilitySDNN': '⌚',
    'OxygenSaturation': '⌚', 'RespiratoryRate': '⌚',
    'AppleSleepingWristTemperature': '⌚', 'AppleSleepingBreathingDisturbances': '⌚',
    'MenstrualFlow': '✏️', 'BodyMass': '✏️',
    'PhysicalEffort': '⌚', 'AppleExerciseTime': '⌚',
    'TimeInDaylight': '⌚', 'VO2Max': '⌚',
}

z_data = []
hover_data = []
y_labels = []
for t in key_types:
    row = []
    hover_row = []
    # 中文名映射
    TYPE_CN = {
        'StepCount': '步数', 'DistanceWalkingRunning': '步行+跑步距离',
        'FlightsClimbed': '爬楼层数', 'HeartRate': '心率',
        'ActiveEnergyBurned': '活动能量', 'BasalEnergyBurned': '基础代谢',
        'SleepAnalysis': '睡眠分析', 'HeadphoneAudioExposure': '耳机音量',
        'WalkingSpeed': '步行速度', 'WalkingStepLength': '步长',
        'RestingHeartRate': '静息心率', 'HeartRateVariabilitySDNN': '心率变异性(HRV)',
        'OxygenSaturation': '血氧饱和度', 'RespiratoryRate': '呼吸频率',
        'AppleSleepingWristTemperature': '睡眠腕温', 'AppleSleepingBreathingDisturbances': '睡眠呼吸扰动',
        'MenstrualFlow': '月经记录', 'BodyMass': '体重',
        'PhysicalEffort': '体力消耗', 'AppleExerciseTime': '运动时长',
        'TimeInDaylight': '日照时间', 'VO2Max': '最大摄氧量(VO2Max)',
    }
    cn_name = TYPE_CN.get(t, t)
    label = f"{source_labels.get(t, '')} {cn_name}"
    y_labels.append(label)
    for y in all_years:
        val = stats.get(t, {}).get(y, 0)
        row.append(val if val > 0 else None)
        hover_row.append(f"{cn_name}<br>年份: {y}<br>记录数: {val:,}")
    z_data.append(row)
    hover_data.append(hover_row)

import numpy as np

# 对数变换以便显示差异较大的数值
z_log = []
for row in z_data:
    z_log.append([np.log10(v) if v and v > 0 else None for v in row])

fig2 = go.Figure(data=go.Heatmap(
    z=z_log,
    x=all_years,
    y=y_labels,
    customdata=z_data,
    hovertemplate='%{y}<br>年份: %{x}<br>记录数: %{customdata:,}<extra></extra>',
    colorscale=[
        [0, '#F2F2F7'],
        [0.2, '#FFD60A'],
        [0.4, '#FF9500'],
        [0.6, '#FF6B35'],
        [0.8, '#FF3B30'],
        [1.0, '#AF1B3F'],
    ],
    colorbar=dict(
        title='log₁₀(记录数)',
        tickvals=[0, 1, 2, 3, 4, 5, 6],
        ticktext=['1', '10', '100', '1K', '10K', '100K', '1M'],
    ),
    zmin=0,
    zmax=6.2,
))

fig2.update_layout(
    title=dict(text='关键数据类型 × 年份 分布热力图<br><sub>📱=iPhone  ⌚=Apple Watch  ✏️=手动记录 | 颜色深度 = 记录数(对数)</sub>',
               font_size=18, x=0.5),
    xaxis_title='年份',
    yaxis=dict(autorange='reversed'),
    template='plotly_white',
    height=700,
    margin=dict(l=250, t=100),
)

# ============================================================
# 图3: 三个时间阶段的数据能力对比 (雷达图)
# ============================================================
categories = ['步数/距离', '心率监测', '睡眠分析', '运动追踪', 
              '身体成分', '月经追踪', '呼吸/血氧', 'HRV/体温',
              '环境感知', '步态分析']

# 评估每个阶段的数据能力 (0-5分)
phase1_scores = [4, 0, 1, 1, 1, 2, 0, 0, 0, 0]  # 2016-2020 iPhone
phase2_scores = [5, 5, 4, 3, 3, 3, 0, 0, 2, 4]  # 2021-2024 Watch过渡
phase3_scores = [5, 5, 5, 5, 3, 3, 5, 5, 5, 5]  # 2025-2026 Watch完整

fig3 = go.Figure()

fig3.add_trace(go.Scatterpolar(
    r=phase1_scores + [phase1_scores[0]],
    theta=categories + [categories[0]],
    fill='toself',
    name='2016-2020 (iPhone)',
    line=dict(color=COLOR_IPHONE, width=2),
    fillcolor='rgba(0,122,255,0.1)',
))

fig3.add_trace(go.Scatterpolar(
    r=phase2_scores + [phase2_scores[0]],
    theta=categories + [categories[0]],
    fill='toself',
    name='2021-2024 (Watch过渡期)',
    line=dict(color=COLOR_WATCH, width=2),
    fillcolor='rgba(255,149,0,0.1)',
))

fig3.add_trace(go.Scatterpolar(
    r=phase3_scores + [phase3_scores[0]],
    theta=categories + [categories[0]],
    fill='toself',
    name='2025-2026 (Watch完整期)',
    line=dict(color=COLOR_WATCH_NEW, width=2),
    fillcolor='rgba(255,59,48,0.1)',
))

fig3.update_layout(
    title=dict(text='三个数据阶段的健康监测能力对比', font_size=18, x=0.5),
    polar=dict(
        radialaxis=dict(visible=True, range=[0, 5.5], tickvals=[1, 2, 3, 4, 5],
                        ticktext=['极少', '少量', '中等', '丰富', '完整']),
    ),
    template='plotly_white',
    height=550,
    legend=dict(orientation='h', yanchor='bottom', y=-0.15, xanchor='center', x=0.5),
    margin=dict(t=80, b=100),
)

# ============================================================
# 图4: Watch 关键指标的起始时间线
# ============================================================
timeline_data = [
    ('HeartRate', '2021-08-07', '心率', COLOR_WATCH),
    ('ActiveEnergyBurned', '2021-01-01', '活动能量', COLOR_WATCH),
    ('SleepAnalysis (Watch)', '2021-01-01', '睡眠分析(Watch精度)', COLOR_WATCH),
    ('BasalEnergyBurned', '2022-09-12', '基础代谢', COLOR_WATCH),
    ('RestingHeartRate', '2025-01-28', '静息心率', COLOR_WATCH_NEW),
    ('HeartRateVariabilitySDNN', '2025-01-28', 'HRV', COLOR_WATCH_NEW),
    ('OxygenSaturation', '2025-01-28', '血氧', COLOR_WATCH_NEW),
    ('RespiratoryRate', '2025-01-28', '呼吸频率', COLOR_WATCH_NEW),
    ('AppleSleepingWristTemperature', '2025-01-29', '睡眠腕温', COLOR_WATCH_NEW),
    ('PhysicalEffort', '2025-01-28', '体力消耗', COLOR_WATCH_NEW),
    ('TimeInDaylight', '2025-01-28', '日照时间', COLOR_WATCH_NEW),
    ('VO2Max', '2025-02-14', '最大摄氧量', COLOR_WATCH_NEW),
    ('AppleSleepingBreathingDisturbances', '2025-04-12', '睡眠呼吸紊乱', COLOR_WATCH_NEW),
    ('DistanceSwimming', '2025-11-13', '游泳距离', COLOR_WATCH_NEW),
]

fig4 = go.Figure()

for i, (name, start, label, color) in enumerate(timeline_data):
    fig4.add_trace(go.Scatter(
        x=[start, '2026-03-30'],
        y=[i, i],
        mode='lines',
        line=dict(color=color, width=8),
        name=label,
        showlegend=False,
        hovertemplate=f'{label}<br>起始: {start}<extra></extra>',
    ))
    fig4.add_trace(go.Scatter(
        x=[start],
        y=[i],
        mode='markers+text',
        marker=dict(color=color, size=10, symbol='diamond'),
        text=[f' {label} ({start})'],
        textposition='middle right',
        textfont=dict(size=11),
        showlegend=False,
    ))

# 添加分界线（用shape代替vline避免plotly版本兼容问题）
fig4.add_shape(type="line", x0='2025-01-28', x1='2025-01-28', y0=-0.5, y1=len(timeline_data)-0.5,
               line=dict(color='red', width=2, dash='dash'))
fig4.add_annotation(x='2025-01-28', y=-0.8, text='⌚ 新Watch开始', showarrow=False,
                    font=dict(size=11, color='red'))

fig4.add_shape(type="line", x0='2021-08-07', x1='2021-08-07', y0=-0.5, y1=len(timeline_data)-0.5,
               line=dict(color='orange', width=2, dash='dash'))
fig4.add_annotation(x='2021-08-07', y=-0.8, text='⌚ 首次心率数据', showarrow=False,
                    font=dict(size=11, color='orange'))

fig4.update_layout(
    title=dict(text='Apple Watch 各指标数据起始时间线<br><sub>橙色=早期Watch数据 | 红色=2025年新Watch数据</sub>',
               font_size=18, x=0.5),
    xaxis_title='日期',
    yaxis=dict(showticklabels=False),
    template='plotly_white',
    height=550,
    margin=dict(l=20, t=100),
)

# ============================================================
# 图5: 推荐分析策略 - 数据类型 vs 建议时间范围
# ============================================================
strategy_data = [
    # (分析主题, 建议起始年, 建议结束年, 数据质量, 优先级, 说明)
    ('步数/日常活动趋势', 2016, 2026, '中等→高', 'P1', '10年长期趋势，iPhone即可采集'),
    ('心率综合分析', 2025, 2026, '高', 'P0', '静息心率+HRV仅2025起，建议聚焦'),
    ('睡眠质量深度分析', 2025, 2026, '高', 'P0', '包含腕温/呼吸/HRV等完整睡眠数据'),
    ('运动训练分析', 2025, 2026, '高', 'P0', '运动类型最丰富，含VO2Max/心率恢复'),
    ('月经周期分析', 2019, 2026, '中等', 'P1', '2019起记录较连续，含孕期信息'),
    ('身体成分追踪', 2022, 2026, '中等', 'P2', '体重/体脂2022起记录密集'),
    ('步态健康评估', 2020, 2026, '高', 'P1', 'iPhone步态从iOS14开始采集'),
    ('听力健康监测', 2019, 2026, '高', 'P2', '耳机音量6年+数据'),
    ('心率长期趋势', 2021, 2026, '中等→高', 'P1', '心率5年数据可看长期变化'),
    ('游泳训练分析', 2025, 2026, '高', 'P2', '2025.11起有游泳专项数据'),
]

fig5 = go.Figure()

priority_colors = {'P0': '#FF3B30', 'P1': '#FF9500', 'P2': '#34C759'}

for i, (theme, start, end, quality, priority, desc) in enumerate(strategy_data):
    fig5.add_trace(go.Scatter(
        x=[start, end],
        y=[i, i],
        mode='lines',
        line=dict(color=priority_colors[priority], width=16),
        name=f'{priority} {theme}',
        showlegend=False,
        hovertemplate=f'<b>{theme}</b><br>'
                      f'建议时间范围: {start}-{end}<br>'
                      f'数据质量: {quality}<br>'
                      f'优先级: {priority}<br>'
                      f'说明: {desc}<extra></extra>',
    ))
    fig5.add_annotation(
        x=start - 0.1, y=i,
        text=f'<b>[{priority}] {theme}</b>',
        showarrow=False, xanchor='right',
        font=dict(size=12, color=priority_colors[priority]),
    )

fig5.update_layout(
    title=dict(text='推荐分析策略 — 各主题的建议分析时间范围<br><sub>🔴 P0=最高优先级（数据最完整）| 🟠 P1=推荐 | 🟢 P2=可选</sub>',
               font_size=18, x=0.5),
    xaxis=dict(title='年份', tickvals=list(range(2016, 2027)), dtick=1),
    yaxis=dict(showticklabels=False, autorange='reversed'),
    template='plotly_white',
    height=550,
    margin=dict(l=280, t=100),
)

# ============================================================
# 组装最终报告 HTML
# ============================================================
html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Apple Health 数据年份分布分析报告</title>
    <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Helvetica Neue', sans-serif;
            background: #F5F5F7;
            color: #1D1D1F;
            line-height: 1.6;
        }}
        .hero {{
            background: linear-gradient(135deg, #1D1D1F 0%, #2C2C2E 50%, #3A3A3C 100%);
            color: white;
            padding: 60px 40px;
            text-align: center;
        }}
        .hero h1 {{
            font-size: 36px;
            font-weight: 700;
            margin-bottom: 12px;
            letter-spacing: -0.5px;
        }}
        .hero p {{
            font-size: 18px;
            opacity: 0.8;
            max-width: 700px;
            margin: 0 auto;
        }}
        .container {{
            max-width: 1100px;
            margin: 0 auto;
            padding: 20px;
        }}
        .section {{
            background: white;
            border-radius: 18px;
            padding: 32px;
            margin: 24px 0;
            box-shadow: 0 2px 12px rgba(0,0,0,0.06);
        }}
        .section h2 {{
            font-size: 24px;
            font-weight: 600;
            margin-bottom: 8px;
            color: #1D1D1F;
        }}
        .section .subtitle {{
            font-size: 15px;
            color: #86868B;
            margin-bottom: 20px;
        }}
        .chart-container {{
            width: 100%;
            margin: 16px 0;
        }}
        .key-finding {{
            background: #F5F5F7;
            border-left: 4px solid #FF9500;
            padding: 16px 20px;
            margin: 16px 0;
            border-radius: 0 12px 12px 0;
            font-size: 15px;
        }}
        .key-finding strong {{ color: #FF9500; }}
        .phase-cards {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 16px;
            margin: 20px 0;
        }}
        .phase-card {{
            border-radius: 14px;
            padding: 20px;
            text-align: center;
        }}
        .phase-card.iphone {{ background: linear-gradient(135deg, #007AFF20, #007AFF10); border: 1px solid #007AFF40; }}
        .phase-card.watch-mid {{ background: linear-gradient(135deg, #FF950020, #FF950010); border: 1px solid #FF950040; }}
        .phase-card.watch-full {{ background: linear-gradient(135deg, #FF3B3020, #FF3B3010); border: 1px solid #FF3B3040; }}
        .phase-card h3 {{ font-size: 16px; margin-bottom: 8px; }}
        .phase-card .years {{ font-size: 13px; color: #86868B; }}
        .phase-card .count {{ font-size: 28px; font-weight: 700; margin: 8px 0; }}
        .phase-card .types {{ font-size: 13px; color: #86868B; }}
        .strategy-table {{
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
            margin: 16px 0;
            font-size: 14px;
        }}
        .strategy-table th {{
            background: #F5F5F7;
            padding: 12px 16px;
            text-align: left;
            font-weight: 600;
            border-bottom: 2px solid #E5E5EA;
        }}
        .strategy-table td {{
            padding: 12px 16px;
            border-bottom: 1px solid #F2F2F7;
        }}
        .strategy-table tr:hover td {{ background: #F9F9FB; }}
        .priority-badge {{
            display: inline-block;
            padding: 2px 10px;
            border-radius: 12px;
            font-weight: 600;
            font-size: 12px;
            color: white;
        }}
        .priority-badge.p0 {{ background: #FF3B30; }}
        .priority-badge.p1 {{ background: #FF9500; }}
        .priority-badge.p2 {{ background: #34C759; }}
        .summary-box {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 18px;
            padding: 32px;
            color: white;
            margin: 24px 0;
        }}
        .summary-box h2 {{ color: white; margin-bottom: 16px; }}
        .summary-box ul {{ list-style: none; padding: 0; }}
        .summary-box li {{
            padding: 8px 0;
            font-size: 15px;
            border-bottom: 1px solid rgba(255,255,255,0.2);
        }}
        .summary-box li:last-child {{ border: none; }}
        .timeline-note {{
            background: #FFF3CD;
            border: 1px solid #FFE69C;
            border-radius: 12px;
            padding: 16px 20px;
            margin: 16px 0;
            font-size: 14px;
        }}
    </style>
</head>
<body>

<div class="hero">
    <h1>Apple Health 数据年份分布分析</h1>
    <p>基于 3,142,667 条健康记录 · 67 种数据类型 · 2016-2026 十年跨度</p>
</div>

<div class="container">

    <!-- 三阶段概览 -->
    <div class="section">
        <h2>数据采集三阶段</h2>
        <p class="subtitle">你的健康数据明确分为三个阶段，设备不同决定了数据丰富度</p>
        
        <div class="phase-cards">
            <div class="phase-card iphone">
                <h3>📱 iPhone 阶段</h3>
                <div class="years">2016.04 — 2020.12</div>
                <div class="count" style="color:#007AFF">231K</div>
                <div class="types">6-11 种数据类型</div>
                <p style="font-size:13px; margin-top:8px; color:#666">以步数、距离、楼层等被动采集为主</p>
            </div>
            <div class="phase-card watch-mid">
                <h3>⌚ Watch 过渡期</h3>
                <div class="years">2021.08 — 2024.12</div>
                <div class="count" style="color:#FF9500">1.76M</div>
                <div class="types">18-31 种数据类型</div>
                <p style="font-size:13px; margin-top:8px; color:#666">新增心率、睡眠，但缺少HRV/血氧等</p>
            </div>
            <div class="phase-card watch-full">
                <h3>⌚ Watch 完整期</h3>
                <div class="years">2025.01 — 至今</div>
                <div class="count" style="color:#FF3B30">1.15M</div>
                <div class="types">44-57 种数据类型</div>
                <p style="font-size:13px; margin-top:8px; color:#666">全量健康数据：HRV、血氧、腕温、呼吸率等</p>
            </div>
        </div>
        
        <div class="key-finding">
            <strong>关键发现：</strong>你的数据呈现明显的"三级跳"。2025年1月28日是一个关键节点——
            从这一天起，静息心率、HRV、血氧、呼吸率、腕温等 20+ 种新指标同时上线，
            标志着你换了一块功能更完整的 Apple Watch（推测为 Ultra 2 或 Series 10）。
        </div>
    </div>

    <!-- 图1 -->
    <div class="section">
        <h2>数据量随时间变化</h2>
        <p class="subtitle">柱状图=总记录数 | 折线=活跃数据类型数</p>
        <div id="chart1" class="chart-container"></div>
    </div>

    <!-- 图2 -->
    <div class="section">
        <h2>关键数据类型 × 年份 分布热力图</h2>
        <p class="subtitle">颜色越深 = 记录数越多（对数尺度） | 空白 = 该年无此类数据</p>
        <div id="chart2" class="chart-container"></div>
        
        <div class="timeline-note">
            <strong>数据空白规律：</strong>
            热力图清晰显示，2016-2020年仅有步数/距离/楼层等 iPhone 基础数据（最上方几行有色）；
            心率在2021年突然出现并爆发；而HRV、血氧、呼吸率等指标在2025年才开始有数据。
        </div>
    </div>

    <!-- 图3 -->
    <div class="section">
        <h2>三个阶段的健康监测能力对比</h2>
        <p class="subtitle">雷达图展示不同阶段可进行的分析维度和数据完整性</p>
        <div id="chart3" class="chart-container"></div>
    </div>

    <!-- 图4 -->
    <div class="section">
        <h2>Apple Watch 各指标数据起始时间线</h2>
        <p class="subtitle">展示每种Watch指标从何时开始有数据</p>
        <div id="chart4" class="chart-container"></div>
    </div>

    <!-- 分析策略推荐 -->
    <div class="section">
        <h2>推荐分析策略</h2>
        <p class="subtitle">基于数据完整性和质量，为不同分析主题推荐最佳时间范围</p>
        
        <div id="chart5" class="chart-container"></div>
        
        <table class="strategy-table">
            <thead>
                <tr>
                    <th>优先级</th>
                    <th>分析主题</th>
                    <th>建议时间范围</th>
                    <th>数据质量</th>
                    <th>核心说明</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td><span class="priority-badge p0">P0</span></td>
                    <td><strong>心率综合分析</strong></td>
                    <td>2025.01 — 至今</td>
                    <td>⭐⭐⭐⭐⭐</td>
                    <td>静息心率 + HRV + 步行心率 + 恢复心率，仅2025年起数据完整</td>
                </tr>
                <tr>
                    <td><span class="priority-badge p0">P0</span></td>
                    <td><strong>睡眠质量深度分析</strong></td>
                    <td>2025.01 — 至今</td>
                    <td>⭐⭐⭐⭐⭐</td>
                    <td>睡眠阶段 + 腕温 + 呼吸紊乱 + HRV + 呼吸率，全维度分析</td>
                </tr>
                <tr>
                    <td><span class="priority-badge p0">P0</span></td>
                    <td><strong>运动训练分析</strong></td>
                    <td>2025.01 — 至今</td>
                    <td>⭐⭐⭐⭐⭐</td>
                    <td>16种运动类型 + VO2Max + 心率区间 + 运动能量，运动种类最丰富</td>
                </tr>
                <tr>
                    <td><span class="priority-badge p1">P1</span></td>
                    <td><strong>步数/日常活动长期趋势</strong></td>
                    <td>2016 — 至今</td>
                    <td>⭐⭐⭐⭐</td>
                    <td>10年连续数据，可观察长期活动量变化趋势和季节模式</td>
                </tr>
                <tr>
                    <td><span class="priority-badge p1">P1</span></td>
                    <td><strong>月经周期分析</strong></td>
                    <td>2019 — 至今</td>
                    <td>⭐⭐⭐</td>
                    <td>2019起记录较连续，含2023年孕期信息，可分析周期规律</td>
                </tr>
                <tr>
                    <td><span class="priority-badge p1">P1</span></td>
                    <td><strong>步态健康评估</strong></td>
                    <td>2020.09 — 至今</td>
                    <td>⭐⭐⭐⭐</td>
                    <td>步速、步长、对称性等6年数据，iPhone即可采集</td>
                </tr>
                <tr>
                    <td><span class="priority-badge p1">P1</span></td>
                    <td><strong>心率长期趋势</strong></td>
                    <td>2021.08 — 至今</td>
                    <td>⭐⭐⭐⭐</td>
                    <td>125万条心率数据，可分析5年心率变化和运动/孕期影响</td>
                </tr>
                <tr>
                    <td><span class="priority-badge p2">P2</span></td>
                    <td><strong>身体成分追踪</strong></td>
                    <td>2022 — 至今</td>
                    <td>⭐⭐⭐</td>
                    <td>体重/BMI/体脂从2022起记录密集（可能是智能秤数据）</td>
                </tr>
                <tr>
                    <td><span class="priority-badge p2">P2</span></td>
                    <td><strong>听力健康监测</strong></td>
                    <td>2019.10 — 至今</td>
                    <td>⭐⭐⭐⭐</td>
                    <td>6.5万条耳机音量数据，可评估听力风险</td>
                </tr>
                <tr>
                    <td><span class="priority-badge p2">P2</span></td>
                    <td><strong>游泳训练分析</strong></td>
                    <td>2025.11 — 至今</td>
                    <td>⭐⭐⭐⭐</td>
                    <td>游泳距离+划水次数+水温，数据时间短但精度高</td>
                </tr>
            </tbody>
        </table>
    </div>

    <!-- 结论 -->
    <div class="summary-box">
        <h2>核心结论与建议</h2>
        <ul>
            <li><strong>最核心分析周期：2025年1月 — 至今（约14个月）</strong>—— 这是你数据最完整的时期，57种数据类型全面覆盖，应作为深度分析的重点</li>
            <li><strong>次要分析周期：2021年8月 — 2024年12月</strong>—— 心率和睡眠数据丰富，可做长期趋势对比，但缺少HRV/血氧等高阶指标</li>
            <li><strong>补充分析周期：2016年 — 2020年</strong>—— 仅值得分析步数/距离的长期趋势、月经周期数据，其他维度数据太稀疏</li>
            <li><strong>早期数据价值：★★☆☆☆</strong>—— 2016-2020年的数据以iPhone被动采集为主（步数、距离、楼层），对深度健康分析贡献有限，但10年步数趋势仍有参考价值</li>
            <li><strong>建议策略</strong>—— P0级分析（心率/睡眠/运动）聚焦2025年至今；P1级分析（步数趋势/月经/步态）可回溯到更早；P2级分析按需进行</li>
        </ul>
    </div>

</div>

<script>
    var chart1Data = {fig1.to_json()};
    var chart2Data = {fig2.to_json()};
    var chart3Data = {fig3.to_json()};
    var chart4Data = {fig4.to_json()};
    var chart5Data = {fig5.to_json()};
    
    Plotly.newPlot('chart1', chart1Data.data, chart1Data.layout, {{responsive: true}});
    Plotly.newPlot('chart2', chart2Data.data, chart2Data.layout, {{responsive: true}});
    Plotly.newPlot('chart3', chart3Data.data, chart3Data.layout, {{responsive: true}});
    Plotly.newPlot('chart4', chart4Data.data, chart4Data.layout, {{responsive: true}});
    Plotly.newPlot('chart5', chart5Data.data, chart5Data.layout, {{responsive: true}});
</script>

</body>
</html>
"""

with open('/Users/shiyuan/Documents/Personal/apple_health_export/yearly_analysis_report.html', 'w', encoding='utf-8') as f:
    f.write(html_content)

print("报告已生成: yearly_analysis_report.html")
