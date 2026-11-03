#!/usr/bin/env python3
"""
Apple Health 综合分析报告
- P0: 心率（静息心率趋势 + HRV）、睡眠（分两段）、运动（步数+锻炼）
- P1: 月经周期规律性
- 专题: 游泳深度分析
时间范围: 2021.08 起
"""

import xml.etree.ElementTree as ET
from collections import defaultdict, Counter
from datetime import datetime, timedelta
import json
import math
import os

# ============================================================
# 数据解析
# ============================================================
XML_FILE = "/Users/shiyuan/Documents/Personal/apple_health_export/导出.xml"
START_DATE = "2021-08-01"

print("正在解析 XML 数据文件...")
tree = ET.parse(XML_FILE)
root = tree.getroot()
print("XML 解析完成")

# --- 心率相关 ---
heart_rate_daily = defaultdict(list)        # date -> [bpm]
resting_hr_daily = {}                        # date -> bpm (一般每天一个值)
hrv_daily = defaultdict(list)                # date -> [ms]
walking_hr_daily = defaultdict(list)         # date -> [bpm]
vo2max_records = []                          # [(date, value)]

# --- 睡眠相关 ---
sleep_records = []   # [(start_dt, end_dt, value, source)]

# --- 运动/步数 ---
step_count_daily = defaultdict(float)        # date -> total steps
step_records_raw = []                        # 原始步数记录，用于去重
active_energy_daily = defaultdict(float)     # date -> kcal
exercise_time_daily = defaultdict(float)     # date -> min
distance_daily = defaultdict(float)          # date -> km

# --- 月经 ---
menstrual_records = []  # [(date, flow_value)]

# --- 游泳专用指标 ---
swim_distance_daily = defaultdict(float)     # date -> meters
swim_stroke_daily = defaultdict(float)       # date -> count

print("正在提取各指标数据...")

type_handlers = {
    'HKQuantityTypeIdentifierHeartRate': 'heart_rate',
    'HKQuantityTypeIdentifierRestingHeartRate': 'resting_hr',
    'HKQuantityTypeIdentifierHeartRateVariabilitySDNN': 'hrv',
    'HKQuantityTypeIdentifierWalkingHeartRateAverage': 'walking_hr',
    'HKQuantityTypeIdentifierVO2Max': 'vo2max',
    'HKQuantityTypeIdentifierStepCount': 'step_count',
    'HKQuantityTypeIdentifierActiveEnergyBurned': 'active_energy',
    'HKQuantityTypeIdentifierAppleExerciseTime': 'exercise_time',
    'HKQuantityTypeIdentifierDistanceWalkingRunning': 'distance',
    'HKQuantityTypeIdentifierDistanceSwimming': 'swim_distance',
    'HKQuantityTypeIdentifierSwimmingStrokeCount': 'swim_stroke',
    'HKCategoryTypeIdentifierSleepAnalysis': 'sleep',
    'HKCategoryTypeIdentifierMenstrualFlow': 'menstrual',
}

record_count = 0
for elem in root.iter('Record'):
    rtype = elem.get('type', '')
    handler = type_handlers.get(rtype)
    if not handler:
        continue
    
    start_str = elem.get('startDate', '')
    if not start_str or start_str[:10] < START_DATE:
        continue
    
    date = start_str[:10]
    value = elem.get('value', '')
    record_count += 1
    
    try:
        if handler == 'heart_rate':
            heart_rate_daily[date].append(float(value))
        elif handler == 'resting_hr':
            resting_hr_daily[date] = float(value)
        elif handler == 'hrv':
            hrv_daily[date].append(float(value))
        elif handler == 'walking_hr':
            walking_hr_daily[date].append(float(value))
        elif handler == 'vo2max':
            vo2max_records.append((date, float(value)))
        elif handler == 'step_count':
            source = elem.get('sourceName', '')
            end_str = elem.get('endDate', '')
            step_records_raw.append((start_str, end_str, source, float(value)))
        elif handler == 'active_energy':
            active_energy_daily[date] += float(value)
        elif handler == 'exercise_time':
            exercise_time_daily[date] += float(value)
        elif handler == 'distance':
            distance_daily[date] += float(value)
        elif handler == 'swim_distance':
            swim_distance_daily[date] += float(value)
        elif handler == 'swim_stroke':
            swim_stroke_daily[date] += float(value)
        elif handler == 'sleep':
            end_str = elem.get('endDate', '')
            source = elem.get('sourceName', '')
            sleep_records.append((start_str, end_str, value, source))
        elif handler == 'menstrual':
            menstrual_records.append((date, value))
    except (ValueError, TypeError):
        pass

print(f"共提取 {record_count} 条相关记录")

# --- 步数去重处理 ---
# Apple Health 导出的步数来自多个来源（iPhone、手环、手表），可能有：
# 1. 完全重复的记录（同一来源/开始/结束时间记录多次）
# 2. 不同来源对同一时间段的重复计数
# 策略：先按 (source, startDate, endDate) 去掉完全重复，再按来源优先级去重
print("正在进行步数去重处理...")
step_dedup = {}  # (source, start, end) -> value，去掉完全重复
for start_str, end_str, source, value in step_records_raw:
    key = (source, start_str, end_str)
    if key not in step_dedup:
        step_dedup[key] = value

print(f"  去除完全重复前: {len(step_records_raw)} 条, 去除后: {len(step_dedup)} 条")

# 来源优先级：Apple Watch > iPhone(zephyrus) > 手环(Zepp Life) > 其他
SOURCE_PRIORITY = {
    '陈诗园的Apple\xa0Watch': 1,
    'zephyrus': 2,
    'Zepp Life': 3,
    '乐心健康': 4,
}

# 按日期和大致时间段分组，同一时间段只保留优先级最高的来源
from datetime import datetime as _dt

# 将每条记录按日期分组
daily_records = defaultdict(list)
for (source, start_str, end_str), value in step_dedup.items():
    date = start_str[:10]
    daily_records[date].append((start_str, end_str, source, value))

for date, records in daily_records.items():
    # 检查当天是否有多个来源
    sources_today = set(r[2] for r in records)
    if len(sources_today) <= 1:
        # 单来源，直接累加
        step_count_daily[date] = sum(r[3] for r in records)
    else:
        # 多来源：选择当天优先级最高（数值最小）的来源
        best_source = min(sources_today, key=lambda s: SOURCE_PRIORITY.get(s, 99))
        step_count_daily[date] = sum(r[3] for r in records if r[2] == best_source)

total_deduped = sum(step_count_daily.values())
print(f"  去重后总步数: {total_deduped:.0f}, 单日最高: {max(step_count_daily.values()):.0f}")
del step_records_raw, step_dedup, daily_records  # 释放内存

# --- 游泳 Workout 数据 ---
swim_workouts = []
all_workouts = []

for elem in root.iter('Workout'):
    wtype = elem.get('workoutActivityType', '').split('/')[-1]
    # 去掉 HKWorkoutActivityType 前缀以简化匹配
    wtype = wtype.replace('HKWorkoutActivityType', '')
    start_str = elem.get('startDate', '')
    if not start_str or start_str[:10] < START_DATE:
        continue
    
    end_str = elem.get('endDate', '')
    duration = float(elem.get('duration', '0') or '0')
    
    # 获取统计指标
    stats = {}
    for stat in elem.iter('WorkoutStatistics'):
        stat_type = stat.get('type', '').split('/')[-1]
        # 去掉 HKQuantityTypeIdentifier 前缀以简化匹配
        stat_type = stat_type.replace('HKQuantityTypeIdentifier', '')
        stats[stat_type] = {
            'sum': stat.get('sum', ''),
            'avg': stat.get('average', ''),
            'min': stat.get('minimum', ''),
            'max': stat.get('maximum', ''),
            'unit': stat.get('unit', '')
        }
    
    # 获取元数据
    metadata = {}
    for meta in elem.iter('MetadataEntry'):
        key = meta.get('key', '').split('/')[-1]
        metadata[key] = meta.get('value', '')
    
    workout_info = {
        'type': wtype,
        'date': start_str[:10],
        'start': start_str,
        'end': end_str,
        'duration_min': duration,
        'stats': stats,
        'metadata': metadata,
    }
    
    all_workouts.append(workout_info)
    
    if 'Swimming' in wtype:
        swim_workouts.append(workout_info)

print(f"Workout 记录: {len(all_workouts)} 条, 其中游泳 {len(swim_workouts)} 条")

# ============================================================
# 数据聚合与计算
# ============================================================
print("正在聚合计算...")

def to_week(date_str):
    """日期转周标签 (YYYY-WNN)"""
    d = datetime.strptime(date_str, '%Y-%m-%d')
    iso = d.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"

def to_month(date_str):
    return date_str[:7]

def moving_avg(values, window=7):
    """简单移动平均"""
    result = []
    for i in range(len(values)):
        start = max(0, i - window + 1)
        result.append(sum(values[start:i+1]) / (i - start + 1))
    return result

# --- 1. 心率分析数据 ---
# 每日平均心率
hr_dates = sorted(heart_rate_daily.keys())
hr_daily_avg = [(d, sum(heart_rate_daily[d]) / len(heart_rate_daily[d])) for d in hr_dates]

# 静息心率
rhr_dates = sorted(resting_hr_daily.keys())
rhr_values = [(d, resting_hr_daily[d]) for d in rhr_dates]

# HRV 每日平均
hrv_dates = sorted(hrv_daily.keys())
hrv_daily_avg = [(d, sum(hrv_daily[d]) / len(hrv_daily[d])) for d in hrv_dates]

# 按月聚合心率
hr_monthly = defaultdict(list)
for d, vals in heart_rate_daily.items():
    m = to_month(d)
    hr_monthly[m].extend(vals)

hr_monthly_stats = {}
for m in sorted(hr_monthly.keys()):
    vals = hr_monthly[m]
    hr_monthly_stats[m] = {
        'avg': sum(vals) / len(vals),
        'min': min(vals),
        'max': max(vals),
        'count': len(vals),
    }

# --- 2. 睡眠分析数据 ---
# 分两段处理
WATCH_DATE = "2025-01-28"

# 睡眠值映射
sleep_value_map = {
    'HKCategoryValueSleepAnalysisInBed': 'InBed',
    'HKCategoryValueSleepAnalysisAsleepUnspecified': 'AsleepUnspecified',
    'HKCategoryValueSleepAnalysisAsleepCore': 'Core',
    'HKCategoryValueSleepAnalysisAsleepDeep': 'Deep',
    'HKCategoryValueSleepAnalysisAsleepREM': 'REM',
    'HKCategoryValueSleepAnalysisAwake': 'Awake',
}

def parse_dt(s):
    """解析日期时间字符串"""
    try:
        # 格式: 2025-01-28 23:15:30 +0800
        return datetime.strptime(s[:19], '%Y-%m-%d %H:%M:%S')
    except:
        return None

# 按"睡眠夜"聚合 (以当天18:00为分界，18:00后算下一天的睡眠)
sleep_nights = defaultdict(lambda: defaultdict(float))  # night_date -> {stage: hours}

for start_str, end_str, value, source in sleep_records:
    start_dt = parse_dt(start_str)
    end_dt = parse_dt(end_str)
    if not start_dt or not end_dt:
        continue
    
    stage = sleep_value_map.get(value, 'Other')
    if stage == 'Other':
        continue
    
    # 计算时长（小时）
    duration_hours = (end_dt - start_dt).total_seconds() / 3600
    if duration_hours <= 0 or duration_hours > 24:
        continue
    
    # 判断属于哪个"睡眠夜" 
    if start_dt.hour >= 18:
        night_date = start_dt.strftime('%Y-%m-%d')
    else:
        night_date = (start_dt - timedelta(days=1)).strftime('%Y-%m-%d')
    
    if night_date < START_DATE:
        continue
    
    sleep_nights[night_date][stage] += duration_hours

# 计算每夜总睡眠时长
sleep_nightly_data = []
for night_date in sorted(sleep_nights.keys()):
    stages = sleep_nights[night_date]
    
    # 总睡眠 = 所有 Asleep 类型（不含 InBed 和 Awake）
    asleep_stages = ['AsleepUnspecified', 'Core', 'Deep', 'REM']
    total_asleep = sum(stages.get(s, 0) for s in asleep_stages)
    
    if total_asleep < 1 or total_asleep > 16:  # 过滤异常值
        continue
    
    sleep_nightly_data.append({
        'date': night_date,
        'total_hours': total_asleep,
        'in_bed': stages.get('InBed', 0),
        'core': stages.get('Core', 0),
        'deep': stages.get('Deep', 0),
        'rem': stages.get('REM', 0),
        'awake': stages.get('Awake', 0),
        'unspecified': stages.get('AsleepUnspecified', 0),
        'is_watch_period': night_date >= WATCH_DATE,
    })

# 按月聚合
sleep_monthly = defaultdict(list)
for s in sleep_nightly_data:
    m = to_month(s['date'])
    sleep_monthly[m].append(s)

sleep_monthly_stats = {}
for m in sorted(sleep_monthly.keys()):
    nights = sleep_monthly[m]
    totals = [n['total_hours'] for n in nights]
    deeps = [n['deep'] for n in nights if n['deep'] > 0]
    rems = [n['rem'] for n in nights if n['rem'] > 0]
    cores = [n['core'] for n in nights if n['core'] > 0]
    
    sleep_monthly_stats[m] = {
        'avg_total': sum(totals) / len(totals) if totals else 0,
        'nights': len(nights),
        'avg_deep': sum(deeps) / len(deeps) if deeps else 0,
        'avg_rem': sum(rems) / len(rems) if rems else 0,
        'avg_core': sum(cores) / len(cores) if cores else 0,
    }

# --- 3. 运动/步数分析数据 ---
# 每日步数
step_dates = sorted(step_count_daily.keys())

# 按月聚合
step_monthly = defaultdict(list)
for d in step_dates:
    m = to_month(d)
    step_monthly[m].append(step_count_daily[d])

step_monthly_stats = {}
for m in sorted(step_monthly.keys()):
    vals = step_monthly[m]
    step_monthly_stats[m] = {
        'avg': sum(vals) / len(vals),
        'total': sum(vals),
        'max': max(vals),
        'days': len(vals),
    }

# Workout 按类型按月统计
workout_monthly = defaultdict(lambda: defaultdict(int))
workout_type_totals = Counter()
for w in all_workouts:
    m = to_month(w['date'])
    wtype = w['type']
    workout_monthly[m][wtype] += 1
    workout_type_totals[wtype] += 1

# 活动能量按月
energy_monthly = defaultdict(list)
for d in sorted(active_energy_daily.keys()):
    m = to_month(d)
    energy_monthly[m].append(active_energy_daily[d])

energy_monthly_stats = {}
for m in sorted(energy_monthly.keys()):
    vals = energy_monthly[m]
    energy_monthly_stats[m] = {
        'avg': sum(vals) / len(vals),
        'total': sum(vals),
    }

# --- 4. 月经周期分析 ---
menstrual_dates = sorted(set(r[0] for r in menstrual_records))

# 识别每次月经的开始日期（连续记录中的第一天）
period_starts = []
if menstrual_dates:
    period_starts.append(menstrual_dates[0])
    for i in range(1, len(menstrual_dates)):
        d1 = datetime.strptime(menstrual_dates[i-1], '%Y-%m-%d')
        d2 = datetime.strptime(menstrual_dates[i], '%Y-%m-%d')
        if (d2 - d1).days > 5:  # 超过5天算新一次月经
            period_starts.append(menstrual_dates[i])

# 计算周期长度
cycle_lengths = []
for i in range(1, len(period_starts)):
    d1 = datetime.strptime(period_starts[i-1], '%Y-%m-%d')
    d2 = datetime.strptime(period_starts[i], '%Y-%m-%d')
    days = (d2 - d1).days
    if 15 <= days <= 90:  # 过滤异常值（孕期等）
        cycle_lengths.append({
            'start': period_starts[i-1],
            'end': period_starts[i],
            'days': days,
        })

# --- 5. 游泳深度分析（含 SWOLF / 泳姿 / 水温 / 间歇） ---
# 泳姿代码映射（修正版）
# Apple Watch 泳姿自动识别存在偏差：
#   代码 2 (Apple标记为仰泳) → 实际为自由泳（最高频主力泳姿，307趟）
#   代码 4 (Apple标记为蝶泳) → 实际为蛙泳（第二主力泳姿，263趟）
# 修正依据：用户确认主要游自由泳和蛙泳，从未游过蝶泳
STROKE_NAMES = {0: '未识别', 1: '自由泳', 2: '自由泳', 3: '蛙泳', 4: '蛙泳', 5: '混合', 6: '浮板'}
STROKE_NAMES_EN = {0: 'Unknown', 1: 'Freestyle', 2: 'Freestyle', 3: 'Breaststroke', 4: 'Breaststroke', 5: 'Mixed', 6: 'Kickboard'}

# 按次整理游泳数据，提取 Lap 级别详情
swim_analysis = []
for w in swim_workouts:
    # 提取距离
    dist_m = 0
    if 'DistanceSwimming' in w['stats']:
        try:
            dist_m = float(w['stats']['DistanceSwimming']['sum'])
        except:
            pass
    
    # 提取划水次数
    strokes = 0
    if 'SwimmingStrokeCount' in w['stats']:
        try:
            strokes = float(w['stats']['SwimmingStrokeCount']['sum'])
        except:
            pass
    
    # 心率
    hr_avg = 0
    hr_max = 0
    if 'HeartRate' in w['stats']:
        try:
            hr_avg = float(w['stats']['HeartRate']['avg'])
            hr_max = float(w['stats']['HeartRate']['max'])
        except:
            pass
    
    # 活动能量
    energy = 0
    if 'ActiveEnergyBurned' in w['stats']:
        try:
            energy = float(w['stats']['ActiveEnergyBurned']['sum'])
        except:
            pass
    
    # 水温
    water_temp_avg = 0
    if 'WaterTemperature' in w['stats']:
        try:
            water_temp_avg = float(w['stats']['WaterTemperature']['avg'])
        except:
            pass
    
    # 泳池长度
    pool_len = w['metadata'].get('HKLapLength', '')
    pool_len_m = 25  # 默认25米
    if pool_len:
        try:
            pool_len_m = float(pool_len.split()[0])
        except:
            pass
    
    # 室内/室外
    is_outdoor = w['metadata'].get('HKIndoorWorkout', '1') == '0'
    
    swim_analysis.append({
        'date': w['date'],
        'start': w['start'],
        'duration_min': w['duration_min'],
        'distance_m': dist_m,
        'strokes': strokes,
        'hr_avg': hr_avg,
        'hr_max': hr_max,
        'energy_kcal': energy,
        'pool_length': pool_len,
        'pool_len_m': pool_len_m,
        'pace_per_100m': (w['duration_min'] / (dist_m / 100)) if dist_m > 0 else 0,
        'strokes_per_100m': (strokes / (dist_m / 100)) if dist_m > 0 else 0,
        'water_temp': water_temp_avg,
        'is_outdoor': is_outdoor,
        'laps': [],           # 每趟详情
        'net_swim_min': 0,    # 净游泳时间
        'rest_min': 0,        # 休息时间
        'rest_pct': 0,        # 休息占比
        'stroke_dist': {},    # 泳姿分布 {style_code: lap_count}
        'swolf_scores': [],   # 所有有效 SWOLF 分数
        'swolf_by_stroke': {},# 按泳姿分类的 SWOLF {style_code: [scores]}
    })

# 第二遍解析：提取 Lap 级别事件（SWOLF、泳姿、间歇）
swim_workout_idx = 0
for elem in root.iter('Workout'):
    wtype = elem.get('workoutActivityType', '').split('/')[-1].replace('HKWorkoutActivityType', '')
    start_str = elem.get('startDate', '')
    if not start_str or start_str[:10] < START_DATE:
        continue
    if 'Swimming' not in wtype:
        continue
    
    if swim_workout_idx >= len(swim_analysis):
        break
    sa = swim_analysis[swim_workout_idx]
    swim_workout_idx += 1
    
    lap_total_min = 0
    for event in elem.iter('WorkoutEvent'):
        etype = event.get('type', '').replace('HKWorkoutEventType', '')
        edur = float(event.get('duration', '0') or '0')
        
        if etype == 'Lap':
            lap_info = {'duration_min': edur, 'stroke': -1, 'swolf': None, 'stroke_name': ''}
            for emeta in event.iter('MetadataEntry'):
                k = emeta.get('key', '')
                v = emeta.get('value', '')
                if k == 'HKSwimmingStrokeStyle':
                    lap_info['stroke'] = int(v)
                    lap_info['stroke_name'] = STROKE_NAMES.get(int(v), '?')
                elif k == 'HKSWOLFScore':
                    try:
                        lap_info['swolf'] = float(v)
                    except:
                        pass
            
            sa['laps'].append(lap_info)
            lap_total_min += edur
            
            # 泳姿分布
            if lap_info['stroke'] >= 0:
                sa['stroke_dist'][lap_info['stroke']] = sa['stroke_dist'].get(lap_info['stroke'], 0) + 1
            
            # SWOLF 收集（过滤异常值：正常范围 20~120）
            if lap_info['swolf'] is not None and 20 <= lap_info['swolf'] <= 120:
                sa['swolf_scores'].append(lap_info['swolf'])
                s_code = lap_info['stroke']
                if s_code not in sa['swolf_by_stroke']:
                    sa['swolf_by_stroke'][s_code] = []
                sa['swolf_by_stroke'][s_code].append(lap_info['swolf'])
    
    # 净游泳时间 vs 休息时间
    sa['net_swim_min'] = lap_total_min
    sa['rest_min'] = max(0, sa['duration_min'] - lap_total_min)
    sa['rest_pct'] = sa['rest_min'] / sa['duration_min'] * 100 if sa['duration_min'] > 0 else 0

swim_analysis.sort(key=lambda x: x['date'])

# ---- 游泳专项深度计算 ----
print("正在进行游泳专项深度分析...")

# A. SWOLF 技术一致性分析
swim_swolf_trend = []  # 每次游泳的 SWOLF 中位数和标准差
all_valid_swolf = []
for sa in swim_analysis:
    if sa['swolf_scores']:
        scores = sorted(sa['swolf_scores'])
        median_swolf = scores[len(scores) // 2]
        mean_swolf = sum(scores) / len(scores)
        std_swolf = (sum((x - mean_swolf)**2 for x in scores) / len(scores)) ** 0.5
        cv_swolf = std_swolf / mean_swolf * 100 if mean_swolf > 0 else 0  # 变异系数
        swim_swolf_trend.append({
            'date': sa['date'],
            'median': median_swolf,
            'mean': mean_swolf,
            'std': std_swolf,
            'cv': cv_swolf,
            'count': len(scores),
        })
        all_valid_swolf.extend(scores)

# SWOLF 一致性洞察
swolf_consistency_insight = ""
if len(swim_swolf_trend) >= 3:
    recent_cvs = [s['cv'] for s in swim_swolf_trend[-5:]]
    avg_cv = sum(recent_cvs) / len(recent_cvs)
    
    first_half_swolf = [s['mean'] for s in swim_swolf_trend[:len(swim_swolf_trend)//2]]
    second_half_swolf = [s['mean'] for s in swim_swolf_trend[len(swim_swolf_trend)//2:]]
    avg_first_swolf = sum(first_half_swolf) / len(first_half_swolf)
    avg_second_swolf = sum(second_half_swolf) / len(second_half_swolf)
    swolf_trend_diff = avg_second_swolf - avg_first_swolf
    
    swolf_consistency_insight = f"<strong>SWOLF 技术一致性分析：</strong>"
    swolf_consistency_insight += f"<br>SWOLF（Swim Golf = 每 25m 用时秒数 + 划水次数）是衡量游泳技术效率的核心指标，数值越低代表技术越好。"
    swolf_consistency_insight += f"<br><br>你的有效 SWOLF 记录共 {len(all_valid_swolf)} 趟，整体均值 {sum(all_valid_swolf)/len(all_valid_swolf):.0f}，中位数 {sorted(all_valid_swolf)[len(all_valid_swolf)//2]:.0f}。"
    
    if swolf_trend_diff < -3:
        swolf_consistency_insight += f"<br><br>进步趋势明显：前半程游泳均值 SWOLF {avg_first_swolf:.0f}，后半程 {avg_second_swolf:.0f}，下降了 {abs(swolf_trend_diff):.0f}，说明游泳技术在持续改善。"
    elif swolf_trend_diff > 3:
        swolf_consistency_insight += f"<br><br>后半程 SWOLF 略有上升（{avg_first_swolf:.0f} → {avg_second_swolf:.0f}），可能是尝试了更多技术动作或训练强度变化导致。"
    else:
        swolf_consistency_insight += f"<br>前后期 SWOLF 保持稳定，技术水平一致性好。"
    
    swolf_consistency_insight += f"<br><br>近 5 次游泳的 SWOLF 变异系数平均为 {avg_cv:.0f}%。"
    if avg_cv < 15:
        swolf_consistency_insight += "一致性很好（CV<15%），说明你在每次训练中能保持稳定的技术输出。"
    elif avg_cv < 25:
        swolf_consistency_insight += "一致性尚可（CV 15-25%），部分波动是正常的，可能反映了热身/放松阶段与高强度阶段的差异。"
    else:
        swolf_consistency_insight += "波动较大（CV>25%），建议在训练中更注重节奏控制。长距离连续游时，试着保持「匀速划水」而非忽快忽慢。"

# B. 泳姿效率对比
stroke_efficiency_insight = ""
# 泳姿代码合并映射（Apple Watch 误识别修正）
# 代码2(被标为仰泳)→实际自由泳，合并到代码1；代码4(被标为蝶泳)→实际蛙泳，合并到代码3
STROKE_MERGE = {0: 0, 1: 1, 2: 1, 3: 3, 4: 3, 5: 5, 6: 6}

all_stroke_data = {}  # merged_code -> {'swolf': [], 'count': 0}
for sa in swim_analysis:
    for s_code, s_swolfs in sa['swolf_by_stroke'].items():
        merged = STROKE_MERGE.get(s_code, s_code)
        if merged not in all_stroke_data:
            all_stroke_data[merged] = {'swolf': [], 'count': 0}
        all_stroke_data[merged]['swolf'].extend(s_swolfs)
    for s_code, s_count in sa['stroke_dist'].items():
        merged = STROKE_MERGE.get(s_code, s_code)
        if merged not in all_stroke_data:
            all_stroke_data[merged] = {'swolf': [], 'count': 0}
        all_stroke_data[merged]['count'] += s_count
    # 同步更新 session 级别的 stroke_dist 为合并后版本
    merged_dist = {}
    for s_code, s_count in sa['stroke_dist'].items():
        merged = STROKE_MERGE.get(s_code, s_code)
        merged_dist[merged] = merged_dist.get(merged, 0) + s_count
    sa['stroke_dist'] = merged_dist
    # 同步更新 swolf_by_stroke
    merged_swolf = {}
    for s_code, s_swolfs in sa['swolf_by_stroke'].items():
        merged = STROKE_MERGE.get(s_code, s_code)
        if merged not in merged_swolf:
            merged_swolf[merged] = []
        merged_swolf[merged].extend(s_swolfs)
    sa['swolf_by_stroke'] = merged_swolf

# 只分析有足够数据的泳姿（排除打腿板和未识别，合并后只有1=自由泳, 3=蛙泳）
real_strokes = {k: v for k, v in all_stroke_data.items() if k in (1, 3) and v['swolf']}
if len(real_strokes) >= 2:
    stroke_efficiency_insight = f"<strong>泳姿效率对比：</strong>"
    stroke_efficiency_insight += "<br><br>"
    
    stroke_rows = []
    for s_code in sorted(real_strokes.keys()):
        data = real_strokes[s_code]
        swolfs = data['swolf']
        avg_sw = sum(swolfs) / len(swolfs)
        med_sw = sorted(swolfs)[len(swolfs)//2]
        best_sw = min(swolfs)
        total_laps = all_stroke_data[s_code]['count']
        stroke_rows.append({
            'code': s_code,
            'name': STROKE_NAMES[s_code],
            'avg_swolf': avg_sw,
            'med_swolf': med_sw,
            'best_swolf': best_sw,
            'total_laps': total_laps,
            'swolf_count': len(swolfs),
        })
    
    # 找出最高效的泳姿
    best_stroke = min(stroke_rows, key=lambda x: x['med_swolf'])
    worst_stroke = max(stroke_rows, key=lambda x: x['med_swolf'])
    
    for row in sorted(stroke_rows, key=lambda x: x['med_swolf']):
        is_best = "🏆" if row == best_stroke else ""
        stroke_efficiency_insight += f"{row['name']}{is_best}：中位 SWOLF {row['med_swolf']:.0f}，最佳 {row['best_swolf']:.0f}，共 {row['total_laps']} 趟（{row['swolf_count']} 趟有效 SWOLF）<br>"
    
    if best_stroke['code'] != worst_stroke['code']:
        diff_pct = (worst_stroke['med_swolf'] - best_stroke['med_swolf']) / best_stroke['med_swolf'] * 100
        stroke_efficiency_insight += f"<br>你的{best_stroke['name']}效率最高（SWOLF 中位数 {best_stroke['med_swolf']:.0f}），而{worst_stroke['name']}还有提升空间（比{best_stroke['name']}高 {diff_pct:.0f}%）。"
        stroke_efficiency_insight += f"<br>建议：在{worst_stroke['name']}训练中可重点关注划距（每划前进距离），减少无效划水。"

# C. 水温与心率基准的关系
water_temp_insight = ""
temp_hr_data = [(sa['water_temp'], sa['hr_avg']) for sa in swim_analysis if sa['water_temp'] > 0 and sa['hr_avg'] > 0]
if len(temp_hr_data) >= 5:
    temps = [t for t, h in temp_hr_data]
    hrs = [h for t, h in temp_hr_data]
    avg_temp = sum(temps) / len(temps)
    temp_range = max(temps) - min(temps)
    
    water_temp_insight = f"<strong>水温环境分析：</strong>"
    water_temp_insight += f"<br>记录水温范围 {min(temps):.1f}~{max(temps):.1f}°C（均值 {avg_temp:.1f}°C），均为室外泳池。"
    
    if temp_range >= 1.5:
        # 按水温分两组对比心率
        sorted_by_temp = sorted(temp_hr_data, key=lambda x: x[0])
        low_temp_group = sorted_by_temp[:len(sorted_by_temp)//2]
        high_temp_group = sorted_by_temp[len(sorted_by_temp)//2:]
        avg_hr_low = sum(h for _, h in low_temp_group) / len(low_temp_group)
        avg_hr_high = sum(h for _, h in high_temp_group) / len(high_temp_group)
        avg_temp_low = sum(t for t, _ in low_temp_group) / len(low_temp_group)
        avg_temp_high = sum(t for t, _ in high_temp_group) / len(high_temp_group)
        
        water_temp_insight += f"<br><br>水温较低时（均 {avg_temp_low:.1f}°C）平均心率 {avg_hr_low:.0f} bpm，水温较高时（均 {avg_temp_high:.1f}°C）{avg_hr_high:.0f} bpm。"
        hr_diff = avg_hr_high - avg_hr_low
        if abs(hr_diff) > 3:
            if hr_diff > 0:
                water_temp_insight += f"水温高时心率偏高 {hr_diff:.0f} bpm，这是正常的体温调节反应——水温越高，身体散热越困难，心率会相应升高。"
            else:
                water_temp_insight += f"水温低时心率反而偏高 {abs(hr_diff):.0f} bpm，可能是低温刺激导致的血管收缩反应。"
        else:
            water_temp_insight += "心率差异不大，说明你的水温范围内体温调节适应良好。"
    else:
        water_temp_insight += " 水温波动范围较小，暂无法做有意义的水温-心率对比分析。"

# D. 间歇分析：净游泳时间 vs 休息时间
interval_insight = ""
if len(swim_analysis) >= 3:
    rest_pcts = [sa['rest_pct'] for sa in swim_analysis if sa['rest_pct'] > 0]
    net_swims = [sa['net_swim_min'] for sa in swim_analysis if sa['net_swim_min'] > 0]
    
    if rest_pcts:
        avg_rest_pct = sum(rest_pcts) / len(rest_pcts)
        avg_net = sum(net_swims) / len(net_swims)
        avg_total_dur = sum(sa['duration_min'] for sa in swim_analysis) / len(swim_analysis)
        
        interval_insight = f"<strong>间歇模式分析（净游泳 vs 休息）：</strong>"
        interval_insight += f"<br>平均每次游泳总时长 {avg_total_dur:.0f} 分钟，其中净游泳 {avg_net:.0f} 分钟，休息 {avg_total_dur - avg_net:.0f} 分钟（占比 {avg_rest_pct:.0f}%）。"
        
        if avg_rest_pct > 50:
            interval_insight += "<br>休息占比超过一半，说明训练以间歇模式为主。间歇训练对提升速度和心肺能力很有效，但建议偶尔加入连续长距离游（如不间断 400-800m）来提升耐力基础。"
        elif avg_rest_pct > 35:
            interval_insight += "<br>休息占比在合理范围（35-50%），兼顾了间歇恢复和持续训练负荷。"
        else:
            interval_insight += "<br>休息占比较低（<35%），说明你的持续游泳能力不错！可以考虑适当增加组间休息以保证每趟的技术质量。"
        
        # 近期 vs 早期的休息占比变化
        if len(swim_analysis) >= 6:
            first_half_rest = [sa['rest_pct'] for sa in swim_analysis[:len(swim_analysis)//2] if sa['rest_pct'] > 0]
            second_half_rest = [sa['rest_pct'] for sa in swim_analysis[len(swim_analysis)//2:] if sa['rest_pct'] > 0]
            if first_half_rest and second_half_rest:
                avg_first_rest = sum(first_half_rest) / len(first_half_rest)
                avg_second_rest = sum(second_half_rest) / len(second_half_rest)
                rest_diff = avg_second_rest - avg_first_rest
                if abs(rest_diff) > 5:
                    if rest_diff > 0:
                        interval_insight += f"<br><br>后期休息占比有所增加（{avg_first_rest:.0f}% → {avg_second_rest:.0f}%），这可能意味着训练强度增大了（更注重单趟质量），或者在尝试更难的技术动作。"
                    else:
                        interval_insight += f"<br><br>后期休息占比减少（{avg_first_rest:.0f}% → {avg_second_rest:.0f}%），持续游泳能力在提升！"

# E. 泳姿演变趋势（分析训练前后泳姿比例变化）
stroke_evolution_insight = ""
if len(swim_analysis) >= 6:
    first_half = swim_analysis[:len(swim_analysis)//2]
    second_half = swim_analysis[len(swim_analysis)//2:]
    
    def count_strokes(sessions):
        total = {}
        for sa in sessions:
            for code, cnt in sa['stroke_dist'].items():
                total[code] = total.get(code, 0) + cnt
        return total
    
    first_strokes = count_strokes(first_half)
    second_strokes = count_strokes(second_half)
    
    # 计算各泳姿占比
    first_total = sum(first_strokes.values()) or 1
    second_total = sum(second_strokes.values()) or 1
    
    significant_changes = []
    for code in set(list(first_strokes.keys()) + list(second_strokes.keys())):
        if code == 6:  # 跳过打腿板
            continue
        pct1 = first_strokes.get(code, 0) / first_total * 100
        pct2 = second_strokes.get(code, 0) / second_total * 100
        if abs(pct2 - pct1) > 8:
            significant_changes.append((code, pct1, pct2))
    
    if significant_changes:
        stroke_evolution_insight = "<strong>泳姿演变趋势：</strong><br>"
        for code, pct1, pct2 in sorted(significant_changes, key=lambda x: abs(x[2]-x[1]), reverse=True):
            name = STROKE_NAMES.get(code, '?')
            direction = "增加" if pct2 > pct1 else "减少"
            stroke_evolution_insight += f"<br>{name}：{pct1:.0f}% → {pct2:.0f}%（{direction} {abs(pct2-pct1):.0f} 个百分点）"
        stroke_evolution_insight += "<br><br>泳姿结构的变化反映了训练重点的调整。不同泳姿对肌群的要求不同，保持多样化训练有助于全身均衡发展。"

print(f"  SWOLF 趋势: {len(swim_swolf_trend)} 次")
print(f"  泳姿数据: {len(real_strokes) if 'real_strokes' in dir() else 0} 种有效泳姿")
print(f"  水温记录: {len(temp_hr_data) if 'temp_hr_data' in dir() else 0} 次")

print(f"数据聚合完成:")
print(f"  心率日数据: {len(hr_dates)} 天")
print(f"  静息心率: {len(rhr_values)} 天")
print(f"  HRV: {len(hrv_daily_avg)} 天")
print(f"  睡眠夜数据: {len(sleep_nightly_data)} 夜")
print(f"  步数日数据: {len(step_dates)} 天")
print(f"  月经周期: {len(cycle_lengths)} 个")
print(f"  游泳记录: {len(swim_analysis)} 次")

# ============================================================
# 生成 Plotly JSON 数据
# ============================================================
print("正在生成图表数据...")

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px

# 全局颜色
C_PRIMARY = '#007AFF'
C_SECONDARY = '#FF9500'
C_ACCENT = '#FF3B30'
C_GREEN = '#34C759'
C_PURPLE = '#AF52DE'
C_TEAL = '#5AC8FA'
C_PINK = '#FF2D55'
C_YELLOW = '#FFD60A'

# ---- 图表1: 月平均心率趋势 (2021.08 ~ now) ----
months_hr = sorted(hr_monthly_stats.keys())
fig_hr_trend = go.Figure()

fig_hr_trend.add_trace(go.Scatter(
    x=months_hr,
    y=[hr_monthly_stats[m]['avg'] for m in months_hr],
    mode='lines+markers',
    name='月平均心率',
    line=dict(color=C_ACCENT, width=2),
    marker=dict(size=4),
    hovertemplate='%{x}<br>平均心率: %{y:.1f} bpm<extra></extra>',
))

# 添加范围带
fig_hr_trend.add_trace(go.Scatter(
    x=months_hr + months_hr[::-1],
    y=[hr_monthly_stats[m]['max'] for m in months_hr] + 
      [hr_monthly_stats[m]['min'] for m in months_hr][::-1],
    fill='toself',
    fillcolor='rgba(255,59,48,0.08)',
    line=dict(width=0),
    name='心率范围 (最低~最高)',
    showlegend=True,
    hoverinfo='skip',
))

# Watch 分界线
fig_hr_trend.add_shape(type="line", x0="2025-01", x1="2025-01",
    y0=40, y1=180, line=dict(color='gray', width=1, dash='dash'))
fig_hr_trend.add_annotation(x="2025-01", y=175, text="Apple Watch 完整期开始",
    showarrow=False, font=dict(size=10, color='gray'))

fig_hr_trend.update_layout(
    title=dict(text='月平均心率趋势 (2021.08 ~ 至今)', font_size=16, x=0.5),
    xaxis_title='月份', yaxis_title='心率 (次/分)',
    template='plotly_white', height=400,
    legend=dict(orientation='h', y=1.1, x=0.5, xanchor='center'),
    margin=dict(t=80, b=60),
)

# ---- 图表2: 静息心率 + HRV (2025.01 ~ now) ----
fig_rhr_hrv = make_subplots(rows=2, cols=1, shared_xaxes=True,
    vertical_spacing=0.08,
    subplot_titles=('每日静息心率 (RHR)', '心率变异性 (HRV-SDNN)'))

# 静息心率
rhr_d = [r[0] for r in rhr_values]
rhr_v = [r[1] for r in rhr_values]
rhr_ma = moving_avg(rhr_v, 7)

fig_rhr_hrv.add_trace(go.Scatter(
    x=rhr_d, y=rhr_v, mode='markers', name='静息心率',
    marker=dict(color=C_ACCENT, size=4, opacity=0.5),
    hovertemplate='%{x}<br>静息心率: %{y:.0f} 次/分<extra></extra>',
), row=1, col=1)

fig_rhr_hrv.add_trace(go.Scatter(
    x=rhr_d, y=rhr_ma, mode='lines', name='静息心率 7日均线',
    line=dict(color=C_ACCENT, width=2),
), row=1, col=1)

# HRV
hrv_d = [h[0] for h in hrv_daily_avg]
hrv_v = [h[1] for h in hrv_daily_avg]
hrv_ma = moving_avg(hrv_v, 7)

fig_rhr_hrv.add_trace(go.Scatter(
    x=hrv_d, y=hrv_v, mode='markers', name='心率变异性(HRV)',
    marker=dict(color=C_PURPLE, size=4, opacity=0.5),
    hovertemplate='%{x}<br>HRV: %{y:.1f} 毫秒<extra></extra>',
), row=2, col=1)

fig_rhr_hrv.add_trace(go.Scatter(
    x=hrv_d, y=hrv_ma, mode='lines', name='心率变异性 7日均线',
    line=dict(color=C_PURPLE, width=2),
), row=2, col=1)

fig_rhr_hrv.update_yaxes(title_text='bpm', row=1, col=1)
fig_rhr_hrv.update_yaxes(title_text='ms', row=2, col=1)
fig_rhr_hrv.update_layout(
    height=500, template='plotly_white',
    legend=dict(orientation='h', y=1.08, x=0.5, xanchor='center'),
    margin=dict(t=80, b=40),
)

# ---- 图表3: 睡眠时长月趋势（分两段）----
sleep_months = sorted(sleep_monthly_stats.keys())
sm_pre_watch = [m for m in sleep_months if m < '2025-01']
sm_watch = [m for m in sleep_months if m >= '2025-01']

fig_sleep = make_subplots(rows=2, cols=1, shared_xaxes=False,
    vertical_spacing=0.15,
    subplot_titles=(
        '小米手环期间 — 每月平均睡眠时长 (2021.08 ~ 2024)',
        'Apple Watch 期间 — 睡眠分期分析 (2025.01 ~ 至今)'
    ))

# 前段：总时长趋势
fig_sleep.add_trace(go.Bar(
    x=sm_pre_watch,
    y=[sleep_monthly_stats[m]['avg_total'] for m in sm_pre_watch],
    marker_color=C_PRIMARY,
    name='平均睡眠时长',
    text=[f"{sleep_monthly_stats[m]['avg_total']:.1f}h" for m in sm_pre_watch],
    textposition='outside', textfont=dict(size=9),
    hovertemplate='%{x}<br>平均: %{y:.2f} 小时<extra></extra>',
), row=1, col=1)

# 后段：睡眠分期堆叠
fig_sleep.add_trace(go.Bar(
    x=sm_watch,
    y=[sleep_monthly_stats[m]['avg_deep'] for m in sm_watch],
    name='深睡', marker_color='#1B2838',
    hovertemplate='%{x}<br>深睡: %{y:.2f}h<extra></extra>',
), row=2, col=1)

fig_sleep.add_trace(go.Bar(
    x=sm_watch,
    y=[sleep_monthly_stats[m]['avg_core'] for m in sm_watch],
    name='核心睡眠', marker_color=C_PRIMARY,
    hovertemplate='%{x}<br>核心: %{y:.2f}h<extra></extra>',
), row=2, col=1)

fig_sleep.add_trace(go.Bar(
    x=sm_watch,
    y=[sleep_monthly_stats[m]['avg_rem'] for m in sm_watch],
    name='REM', marker_color=C_PURPLE,
    hovertemplate='%{x}<br>REM: %{y:.2f}h<extra></extra>',
), row=2, col=1)

fig_sleep.update_layout(
    barmode='stack',
    height=600, template='plotly_white',
    legend=dict(orientation='h', y=1.06, x=0.5, xanchor='center'),
    margin=dict(t=80, b=40),
)
fig_sleep.update_yaxes(title_text='小时', row=1, col=1)
fig_sleep.update_yaxes(title_text='小时', row=2, col=1)

# ---- 图表4: 每月平均步数趋势 ----
step_months = sorted(step_monthly_stats.keys())

fig_steps = go.Figure()
fig_steps.add_trace(go.Bar(
    x=step_months,
    y=[step_monthly_stats[m]['avg'] for m in step_months],
    marker_color=[C_ACCENT if m >= '2025-01' else (C_SECONDARY if m >= '2021-08' else C_PRIMARY) for m in step_months],
    text=[f"{step_monthly_stats[m]['avg']:.0f}" for m in step_months],
    textposition='outside', textfont=dict(size=8),
    hovertemplate='%{x}<br>日均步数: %{y:.0f}<br>总步数: %{customdata[0]:,.0f}<br>记录天数: %{customdata[1]}<extra></extra>',
    customdata=[(step_monthly_stats[m]['total'], step_monthly_stats[m]['days']) for m in step_months],
))

# 参考线
fig_steps.add_hline(y=8000, line=dict(color='green', dash='dash', width=1),
    annotation_text='推荐目标: 8000步/天', annotation_position='top right')

fig_steps.update_layout(
    title=dict(text='每月日均步数趋势', font_size=16, x=0.5),
    xaxis_title='月份', yaxis_title='日均步数',
    template='plotly_white', height=400,
    margin=dict(t=80, b=60),
)

# ---- 图表5: 运动类型分布（2021.08 ~ now）----
# 按年聚合
workout_yearly = defaultdict(lambda: defaultdict(int))
for w in all_workouts:
    year = w['date'][:4]
    workout_yearly[year][w['type']] += 1

# 取 top 8 类型
top_types = [t for t, _ in workout_type_totals.most_common(8)]
type_labels = {
    'TraditionalStrengthTraining': '力量训练',
    'Walking': '步行',
    'Swimming': '游泳',
    'StairClimbing': '爬楼梯',
    'HighIntensityIntervalTraining': 'HIIT',
    'Elliptical': '椭圆机',
    'MixedCardio': '综合有氧',
    'Running': '跑步',
    'FunctionalStrengthTraining': '功能性训练',
    'CoreTraining': '核心训练',
    'Pilates': '普拉提',
    'Yoga': '瑜伽',
    'Cycling': '骑行',
    'Rowing': '划船机',
    'FitnessGaming': '健身游戏',
    'Cooldown': '冷却',
    'CrossTraining': '交叉训练',
    'Other': '其他',
}

years_workout = sorted(workout_yearly.keys())
fig_workout_dist = go.Figure()

colors_workout = [C_ACCENT, C_PRIMARY, C_TEAL, C_GREEN, C_PURPLE, C_SECONDARY, C_PINK, C_YELLOW]
for i, wtype in enumerate(top_types):
    vals = [workout_yearly[y].get(wtype, 0) for y in years_workout]
    fig_workout_dist.add_trace(go.Bar(
        x=years_workout, y=vals,
        name=type_labels.get(wtype, wtype),
        marker_color=colors_workout[i % len(colors_workout)],
    ))

fig_workout_dist.update_layout(
    barmode='stack',
    title=dict(text='年度运动类型分布', font_size=16, x=0.5),
    xaxis_title='年份', yaxis_title='运动次数',
    template='plotly_white', height=420,
    legend=dict(orientation='h', y=1.12, x=0.5, xanchor='center'),
    margin=dict(t=100, b=60),
)

# ---- 图表6: 活动能量月趋势 ----
energy_months = sorted(energy_monthly_stats.keys())
fig_energy = go.Figure()
fig_energy.add_trace(go.Scatter(
    x=energy_months,
    y=[energy_monthly_stats[m]['avg'] for m in energy_months],
    mode='lines+markers',
    name='日均活动能量',
    line=dict(color=C_SECONDARY, width=2),
    marker=dict(size=5),
    fill='tozeroy', fillcolor='rgba(255,149,0,0.1)',
    hovertemplate='%{x}<br>日均: %{y:.0f} kcal<extra></extra>',
))

fig_energy.update_layout(
    title=dict(text='每月日均活动能量消耗', font_size=16, x=0.5),
    xaxis_title='月份', yaxis_title='kcal',
    template='plotly_white', height=350,
    margin=dict(t=80, b=60),
)

# ---- 图表7: 月经周期长度 ----
fig_menstrual = go.Figure()

if cycle_lengths:
    cycle_dates = [c['start'] for c in cycle_lengths]
    cycle_days = [c['days'] for c in cycle_lengths]
    
    fig_menstrual.add_trace(go.Scatter(
        x=cycle_dates, y=cycle_days,
        mode='lines+markers',
        name='周期长度',
        line=dict(color=C_PINK, width=2),
        marker=dict(size=8, color=C_PINK),
        hovertemplate='经期开始: %{x}<br>周期: %{y} 天<extra></extra>',
    ))
    
    # 正常范围
    fig_menstrual.add_hrect(y0=24, y1=38, fillcolor='rgba(52,199,89,0.1)',
        line=dict(width=0), annotation_text='正常范围 (24-38天)', annotation_position='top right')
    
    avg_cycle = sum(cycle_days) / len(cycle_days)
    fig_menstrual.add_hline(y=avg_cycle, line=dict(color=C_PINK, dash='dash', width=1),
        annotation_text=f'平均: {avg_cycle:.1f}天')

fig_menstrual.update_layout(
    title=dict(text='月经周期长度变化', font_size=16, x=0.5),
    xaxis_title='经期开始日期', yaxis_title='周期长度 (天)',
    template='plotly_white', height=380,
    margin=dict(t=80, b=60),
)

# ---- 图表8: 游泳进步曲线 ----
fig_swim_progress = make_subplots(
    rows=2, cols=2, shared_xaxes=False,
    subplot_titles=('游泳距离 (米)', '配速 (分钟/100米)', '平均心率 (bpm)', '消耗能量 (kcal)'),
    vertical_spacing=0.15, horizontal_spacing=0.1,
)

swim_dates = [s['date'] for s in swim_analysis]
swim_nums = list(range(1, len(swim_analysis) + 1))  # 第N次游泳

# 距离
fig_swim_progress.add_trace(go.Bar(
    x=swim_dates,
    y=[s['distance_m'] for s in swim_analysis],
    marker_color=C_TEAL,
    text=[f"{s['distance_m']:.0f}m" for s in swim_analysis],
    textposition='outside', textfont=dict(size=8),
    name='距离',
    hovertemplate='%{x}<br>距离: %{y:.0f} 米<extra></extra>',
), row=1, col=1)

# 配速
paces = [s['pace_per_100m'] for s in swim_analysis]
valid_paces = [(d, p) for d, p in zip(swim_dates, paces) if 0 < p < 10]
if valid_paces:
    fig_swim_progress.add_trace(go.Scatter(
        x=[v[0] for v in valid_paces],
        y=[v[1] for v in valid_paces],
        mode='lines+markers',
        name='配速',
        line=dict(color=C_PRIMARY, width=2),
        marker=dict(size=6),
        hovertemplate='%{x}<br>配速: %{y:.2f} min/100m<extra></extra>',
    ), row=1, col=2)

# 心率
hrs = [(s['date'], s['hr_avg']) for s in swim_analysis if s['hr_avg'] > 0]
if hrs:
    fig_swim_progress.add_trace(go.Scatter(
        x=[h[0] for h in hrs],
        y=[h[1] for h in hrs],
        mode='lines+markers',
        name='平均心率',
        line=dict(color=C_ACCENT, width=2),
        marker=dict(size=6),
        hovertemplate='%{x}<br>平均心率: %{y:.0f} bpm<extra></extra>',
    ), row=2, col=1)

# 能量
energies = [(s['date'], s['energy_kcal']) for s in swim_analysis if s['energy_kcal'] > 0]
if energies:
    fig_swim_progress.add_trace(go.Scatter(
        x=[e[0] for e in energies],
        y=[e[1] for e in energies],
        mode='lines+markers',
        name='能量',
        line=dict(color=C_GREEN, width=2),
        marker=dict(size=6),
        fill='tozeroy', fillcolor='rgba(52,199,89,0.1)',
        hovertemplate='%{x}<br>消耗: %{y:.0f} kcal<extra></extra>',
    ), row=2, col=2)

fig_swim_progress.update_layout(
    height=600, template='plotly_white', showlegend=False,
    margin=dict(t=60, b=40),
)

# ---- 图表9: 游泳单次详情 (距离 vs 配速 气泡图) ----
fig_swim_bubble = go.Figure()

valid_swims = [s for s in swim_analysis if s['distance_m'] > 0 and 0 < s['pace_per_100m'] < 10]
if valid_swims:
    fig_swim_bubble.add_trace(go.Scatter(
        x=[s['distance_m'] for s in valid_swims],
        y=[s['pace_per_100m'] for s in valid_swims],
        mode='markers+text',
        marker=dict(
            size=[max(10, s['duration_min'] / 2) for s in valid_swims],
            color=[s['hr_avg'] if s['hr_avg'] > 0 else 120 for s in valid_swims],
            colorscale='YlOrRd',
            showscale=True,
            colorbar=dict(title='平均心率'),
            opacity=0.7,
        ),
        text=[s['date'][5:] for s in valid_swims],
        textposition='top center', textfont=dict(size=8),
        hovertemplate='日期: %{text}<br>距离: %{x:.0f}m<br>配速: %{y:.2f} min/100m<br>'
                      '时长: %{customdata[0]:.0f}min<br>心率: %{customdata[1]:.0f}bpm<extra></extra>',
        customdata=[(s['duration_min'], s['hr_avg']) for s in valid_swims],
    ))

fig_swim_bubble.update_layout(
    title=dict(text='游泳：距离 vs 配速（气泡大小=时长，颜色=心率）', font_size=14, x=0.5),
    xaxis_title='距离 (米)', yaxis_title='配速 (分钟/100米)',
    template='plotly_white', height=450,
    margin=dict(t=80, b=60),
)
# 配速轴反转（越低越快）
fig_swim_bubble.update_yaxes(autorange='reversed')

# ---- 图表10: SWOLF 技术一致性趋势 ----
fig_swolf_trend = make_subplots(
    rows=2, cols=1, shared_xaxes=True,
    subplot_titles=('每次游泳 SWOLF 中位数趋势', '每次游泳 SWOLF 变异系数 (CV%)'),
    vertical_spacing=0.15,
    row_heights=[0.6, 0.4],
)

if swim_swolf_trend:
    trend_dates = [s['date'] for s in swim_swolf_trend]
    trend_medians = [s['median'] for s in swim_swolf_trend]
    trend_means = [s['mean'] for s in swim_swolf_trend]
    trend_stds = [s['std'] for s in swim_swolf_trend]
    trend_cvs = [s['cv'] for s in swim_swolf_trend]
    trend_counts = [s['count'] for s in swim_swolf_trend]
    
    # SWOLF 中位数 + 均值
    fig_swolf_trend.add_trace(go.Scatter(
        x=trend_dates, y=trend_medians,
        mode='lines+markers',
        name='SWOLF 中位数',
        line=dict(color=C_PRIMARY, width=2.5),
        marker=dict(size=8),
        hovertemplate='%{x}<br>中位数: %{y:.0f}<br>有效趟数: %{customdata}<extra></extra>',
        customdata=trend_counts,
    ), row=1, col=1)
    
    fig_swolf_trend.add_trace(go.Scatter(
        x=trend_dates, y=trend_means,
        mode='lines',
        name='SWOLF 均值',
        line=dict(color=C_SECONDARY, width=1.5, dash='dash'),
        hovertemplate='%{x}<br>均值: %{y:.1f}<extra></extra>',
    ), row=1, col=1)
    
    # 标准差范围带
    upper = [m + s for m, s in zip(trend_means, trend_stds)]
    lower = [max(m - s, 0) for m, s in zip(trend_means, trend_stds)]
    fig_swolf_trend.add_trace(go.Scatter(
        x=trend_dates + trend_dates[::-1],
        y=upper + lower[::-1],
        fill='toself',
        fillcolor='rgba(0,122,255,0.08)',
        line=dict(width=0),
        name='±1标准差',
        showlegend=True,
        hoverinfo='skip',
    ), row=1, col=1)
    
    # CV% 柱状图
    cv_colors = [C_GREEN if cv < 15 else (C_SECONDARY if cv < 25 else C_ACCENT) for cv in trend_cvs]
    fig_swolf_trend.add_trace(go.Bar(
        x=trend_dates, y=trend_cvs,
        name='变异系数 CV%',
        marker_color=cv_colors,
        hovertemplate='%{x}<br>CV: %{y:.1f}%<extra></extra>',
    ), row=2, col=1)
    
    # CV% 参考线
    fig_swolf_trend.add_hline(y=15, line=dict(color=C_GREEN, width=1, dash='dot'),
                              annotation_text='优秀 (<15%)', row=2, col=1)
    fig_swolf_trend.add_hline(y=25, line=dict(color=C_ACCENT, width=1, dash='dot'),
                              annotation_text='需改进 (>25%)', row=2, col=1)

fig_swolf_trend.update_layout(
    height=550, template='plotly_white',
    margin=dict(t=60, b=40),
    legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
)
fig_swolf_trend.update_yaxes(title_text='SWOLF', row=1, col=1)
fig_swolf_trend.update_yaxes(title_text='CV%', row=2, col=1)

# ---- 图表11: 泳姿效率对比 ----
fig_stroke_efficiency = go.Figure()

STROKE_COLORS = {
    1: '#007AFF',   # 自由泳 - 蓝
    3: '#FF9500',   # 蛙泳 - 橙
    5: '#AF52DE',   # 混合 - 紫
    6: '#8E8E93',   # 打腿板 - 灰
}

if 'all_stroke_data' in dir() and all_stroke_data:
    stroke_names_ordered = []
    stroke_swolf_boxes = []
    for code in [1, 2, 3, 4, 5, 6]:
        if code in all_stroke_data and len(all_stroke_data[code]['swolf']) >= 3:
            name = STROKE_NAMES.get(code, f'泳姿{code}')
            swolf_values = all_stroke_data[code]['swolf']
            fig_stroke_efficiency.add_trace(go.Box(
                y=swolf_values,
                name=name,
                marker_color=STROKE_COLORS.get(code, '#999'),
                boxmean='sd',
                hovertemplate=f'{name}<br>SWOLF: %{{y:.0f}}<extra></extra>',
            ))

fig_stroke_efficiency.update_layout(
    title=dict(text='各泳姿 SWOLF 效率对比（箱线图）', font_size=14, x=0.5),
    yaxis_title='SWOLF',
    template='plotly_white',
    height=400,
    margin=dict(t=60, b=40),
    showlegend=False,
)

# ---- 图表12: 间歇分析 (净游泳 vs 休息) ----
fig_interval = go.Figure()

interval_data = [(sa['date'], sa['net_swim_min'], sa['duration_min'] - sa['net_swim_min'], sa['rest_pct'])
                 for sa in swim_analysis if sa.get('net_swim_min', 0) > 0]

if interval_data:
    int_dates = [d[0] for d in interval_data]
    int_swim = [d[1] for d in interval_data]
    int_rest = [d[2] for d in interval_data]
    int_rest_pct = [d[3] for d in interval_data]
    
    fig_interval.add_trace(go.Bar(
        x=int_dates, y=int_swim,
        name='净游泳时间',
        marker_color=C_PRIMARY,
        hovertemplate='%{x}<br>净游泳: %{y:.0f} min<extra></extra>',
    ))
    fig_interval.add_trace(go.Bar(
        x=int_dates, y=int_rest,
        name='休息时间',
        marker_color='#E5E5EA',
        hovertemplate='%{x}<br>休息: %{y:.0f} min<extra></extra>',
    ))
    
    # 休息占比趋势线 (右Y轴)
    fig_interval.add_trace(go.Scatter(
        x=int_dates, y=int_rest_pct,
        mode='lines+markers',
        name='休息占比 %',
        line=dict(color=C_ACCENT, width=2),
        marker=dict(size=5),
        yaxis='y2',
        hovertemplate='%{x}<br>休息占比: %{y:.0f}%<extra></extra>',
    ))

fig_interval.update_layout(
    title=dict(text='间歇模式分析：净游泳 vs 休息', font_size=14, x=0.5),
    barmode='stack',
    template='plotly_white',
    height=400,
    margin=dict(t=60, b=40),
    yaxis=dict(title='时间 (分钟)'),
    yaxis2=dict(title='休息占比 %', overlaying='y', side='right', range=[0, 100]),
    legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
)

# ---- 图表13: 水温 vs 心率散点图 ----
fig_water_temp = go.Figure()

if temp_hr_data:
    temps_plot = [d[0] for d in temp_hr_data]
    hrs_plot = [d[1] for d in temp_hr_data]
    
    fig_water_temp.add_trace(go.Scatter(
        x=temps_plot, y=hrs_plot,
        mode='markers',
        name='游泳记录',
        marker=dict(
            size=12,
            color=hrs_plot,
            colorscale='RdYlGn_r',
            colorbar=dict(title='心率'),
            line=dict(width=1, color='white'),
        ),
        hovertemplate='水温: %{x:.1f}°C<br>心率: %{y:.0f} bpm<extra></extra>',
    ))
    
    # 添加趋势线
    if len(temps_plot) >= 3:
        import numpy as np
        temps_arr = np.array(temps_plot)
        hrs_arr = np.array(hrs_plot)
        z = np.polyfit(temps_arr, hrs_arr, 1)
        p = np.poly1d(z)
        temp_range = np.linspace(min(temps_plot), max(temps_plot), 50)
        fig_water_temp.add_trace(go.Scatter(
            x=temp_range.tolist(), y=p(temp_range).tolist(),
            mode='lines',
            name=f'趋势线 (斜率: {z[0]:.1f} bpm/°C)',
            line=dict(color=C_ACCENT, width=2, dash='dash'),
        ))

fig_water_temp.update_layout(
    title=dict(text='水温与游泳心率的关系', font_size=14, x=0.5),
    xaxis_title='水温 (°C)', yaxis_title='平均心率 (bpm)',
    template='plotly_white',
    height=400,
    margin=dict(t=60, b=40),
)

# ---- 图表14: 泳姿分布饼图 ----
fig_stroke_dist = go.Figure()

if 'all_stroke_data' in dir() and all_stroke_data:
    pie_labels = []
    pie_values = []
    pie_colors = []
    for code in [1, 3, 5, 6]:
        if code in all_stroke_data and all_stroke_data[code]['count'] > 0:
            name = STROKE_NAMES.get(code, f'泳姿{code}')
            pie_labels.append(name)
            pie_values.append(all_stroke_data[code]['count'])
            pie_colors.append(STROKE_COLORS.get(code, '#999'))
    
    if pie_labels:
        fig_stroke_dist.add_trace(go.Pie(
            labels=pie_labels,
            values=pie_values,
            marker=dict(colors=pie_colors),
            textinfo='label+percent',
            hovertemplate='%{label}: %{value} 趟 (%{percent})<extra></extra>',
        ))

fig_stroke_dist.update_layout(
    title=dict(text='泳姿分布（按趟数）', font_size=14, x=0.5),
    template='plotly_white',
    height=380,
    margin=dict(t=60, b=20),
)

# ---- 图表15: VO2Max 趋势 ----
fig_vo2 = go.Figure()
if vo2max_records:
    vo2_d = [v[0] for v in vo2max_records]
    vo2_v = [v[1] for v in vo2max_records]
    fig_vo2.add_trace(go.Scatter(
        x=vo2_d, y=vo2_v,
        mode='lines+markers',
        name='VO2Max',
        line=dict(color=C_GREEN, width=2),
        marker=dict(size=6),
        hovertemplate='%{x}<br>VO2Max: %{y:.1f} mL/kg/min<extra></extra>',
    ))

fig_vo2.update_layout(
    title=dict(text='最大摄氧量 (VO2Max) 趋势', font_size=16, x=0.5),
    xaxis_title='日期', yaxis_title='mL/(kg·min)',
    template='plotly_white', height=350,
    margin=dict(t=80, b=60),
)

# ============================================================
# 生成 HTML 报告
# ============================================================
print("正在生成 HTML 报告...")

# 计算统计卡片数据
total_steps_all = sum(step_count_daily.values())
total_workouts = len(all_workouts)
total_swim = len(swim_analysis)
avg_rhr = sum(rhr_v) / len(rhr_v) if rhr_v else 0
avg_hrv = sum(hrv_v) / len(hrv_v) if hrv_v else 0
avg_sleep = sum(s['total_hours'] for s in sleep_nightly_data) / len(sleep_nightly_data) if sleep_nightly_data else 0
avg_cycle_len = sum(c['days'] for c in cycle_lengths) / len(cycle_lengths) if cycle_lengths else 0
total_swim_dist = sum(s['distance_m'] for s in swim_analysis)

# Watch 期间深睡/REM统计
watch_sleeps = [s for s in sleep_nightly_data if s['is_watch_period']]
avg_deep = sum(s['deep'] for s in watch_sleeps) / len(watch_sleeps) if watch_sleeps else 0
avg_rem = sum(s['rem'] for s in watch_sleeps) / len(watch_sleeps) if watch_sleeps else 0

# 游泳最远/最近配速
if valid_swims:
    max_swim_dist = max(s['distance_m'] for s in valid_swims)
    best_pace = min(s['pace_per_100m'] for s in valid_swims)
    latest_pace = valid_swims[-1]['pace_per_100m']
    first_pace = valid_swims[0]['pace_per_100m']
else:
    max_swim_dist = best_pace = latest_pace = first_pace = 0

# 预计算所有条件变量，避免 f-string 嵌套问题
min_rhr = f"{min(rhr_v):.0f}" if rhr_v else "0"
latest_vo2 = f"{vo2max_records[-1][1]:.1f}" if vo2max_records else "0"

# ========== 深度心率分析 ==========
# 1) 月平均心率趋势变化
hr_months_sorted = sorted(hr_monthly_stats.keys())
hr_trend_insight = ""
if len(hr_months_sorted) >= 6:
    first_half_hr = [hr_monthly_stats[m]['avg'] for m in hr_months_sorted[:len(hr_months_sorted)//2]]
    second_half_hr = [hr_monthly_stats[m]['avg'] for m in hr_months_sorted[len(hr_months_sorted)//2:]]
    avg_first = sum(first_half_hr) / len(first_half_hr)
    avg_second = sum(second_half_hr) / len(second_half_hr)
    diff_hr = avg_second - avg_first
    if abs(diff_hr) > 2:
        direction = "上升" if diff_hr > 0 else "下降"
        hr_trend_insight = f"整体趋势：后半段相比前半段月平均心率{direction}了 {abs(diff_hr):.1f} bpm，"
        if diff_hr < -2:
            hr_trend_insight += "说明心血管效率在逐步提升，这通常与规律运动正相关。"
        else:
            hr_trend_insight += "可能与运动量变化、压力或生活节奏改变有关，建议关注。"
    else:
        hr_trend_insight = "整体趋势稳定，月平均心率波动不大，心血管状态保持良好。"

# 找出心率最高和最低的月份
hr_max_month = max(hr_months_sorted, key=lambda m: hr_monthly_stats[m]['avg'])
hr_min_month = min(hr_months_sorted, key=lambda m: hr_monthly_stats[m]['avg'])
hr_peak_insight = f"心率峰值出现在 {hr_max_month}（月均 {hr_monthly_stats[hr_max_month]['avg']:.0f} bpm），谷值在 {hr_min_month}（月均 {hr_monthly_stats[hr_min_month]['avg']:.0f} bpm），振幅 {hr_monthly_stats[hr_max_month]['avg'] - hr_monthly_stats[hr_min_month]['avg']:.0f} bpm。"

# 2) RHR 深度分析
rhr_insight = ""
if len(rhr_v) >= 14:
    rhr_recent_14 = rhr_v[-14:]
    rhr_recent_avg = sum(rhr_recent_14) / len(rhr_recent_14)
    rhr_overall_avg = sum(rhr_v) / len(rhr_v)
    rhr_min_val = min(rhr_v)
    rhr_max_val = max(rhr_v)
    rhr_range = rhr_max_val - rhr_min_val
    
    rhr_trend_diff = rhr_recent_avg - rhr_overall_avg
    rhr_insight = f"静息心率范围 {rhr_min_val:.0f}~{rhr_max_val:.0f} bpm（波动 {rhr_range:.0f} bpm）。"
    if abs(rhr_trend_diff) > 2:
        rhr_dir = "偏高" if rhr_trend_diff > 0 else "偏低"
        rhr_insight += f" 最近两周均值 {rhr_recent_avg:.0f} bpm，比整体均值{rhr_dir} {abs(rhr_trend_diff):.1f} bpm。"
        if rhr_trend_diff > 3:
            rhr_insight += "近期上升可能反映疲劳累积、睡眠不足或恢复不充分。"
        elif rhr_trend_diff < -3:
            rhr_insight += "近期下降是积极信号，通常意味着身体恢复状态良好或有氧能力提升。"
    else:
        rhr_insight += f" 最近两周均值 {rhr_recent_avg:.0f} bpm，与整体水平持平，状态稳定。"
    
    # RHR 个人基准评估（避免用大众标准评判，与自己的历史对比）
    rhr_percentiles = sorted(rhr_v)
    rhr_p25 = rhr_percentiles[len(rhr_percentiles)//4]
    rhr_p75 = rhr_percentiles[3*len(rhr_percentiles)//4]
    rhr_insight += f" 你的个人 RHR 区间主要集中在 {rhr_p25:.0f}~{rhr_p75:.0f} bpm（25~75分位）。"
    if rhr_recent_avg < rhr_p25:
        rhr_insight += "近期处于你个人低值区，身体状态佳。"
    elif rhr_recent_avg > rhr_p75:
        rhr_insight += "近期偏向你个人高值区，可能反映近期疲劳或恢复不充分。"
    else:
        rhr_insight += "近期在你个人正常范围内。"
else:
    rhr_insight = f"静息心率平均 {avg_rhr:.0f} bpm，{'处于良好水平' if avg_rhr < 80 else '略偏高，建议关注'}。"

# 3) HRV 深度分析
hrv_insight = ""
if len(hrv_v) >= 14:
    hrv_recent_14 = hrv_v[-14:]
    hrv_recent_avg = sum(hrv_recent_14) / len(hrv_recent_14)
    hrv_overall_avg = sum(hrv_v) / len(hrv_v)
    hrv_std = (sum((x - hrv_overall_avg)**2 for x in hrv_v) / len(hrv_v)) ** 0.5
    hrv_min_val = min(hrv_v)
    hrv_max_val = max(hrv_v)
    
    hrv_insight = f"HRV 范围 {hrv_min_val:.0f}~{hrv_max_val:.0f} ms，日间波动标准差 {hrv_std:.0f} ms。"
    hrv_trend_diff = hrv_recent_avg - hrv_overall_avg
    if abs(hrv_trend_diff) > 3:
        hrv_dir = "上升" if hrv_trend_diff > 0 else "下降"
        hrv_insight += f" 最近两周均值 {hrv_recent_avg:.0f} ms，相比整体均值{hrv_dir}了 {abs(hrv_trend_diff):.1f} ms。"
        if hrv_trend_diff > 3:
            hrv_insight += "HRV 上升说明自主神经调节能力增强，身体恢复和压力管理状态优良。"
        else:
            hrv_insight += "HRV 下降可能提示近期压力较大、睡眠质量下降或过度训练，需注意休息和恢复。"
    else:
        hrv_insight += f" 近期表现稳定，与整体水平一致。"
    
    # HRV 个人基准评估（与自己的历史做对比，而非大众标准）
    hrv_percentiles = sorted(hrv_v)
    hrv_p25 = hrv_percentiles[len(hrv_percentiles)//4]
    hrv_p75 = hrv_percentiles[3*len(hrv_percentiles)//4]
    hrv_insight += f" 你的个人 HRV 分布主要在 {hrv_p25:.0f}~{hrv_p75:.0f} ms（25~75分位）。"
    if hrv_recent_avg > hrv_p75:
        hrv_insight += "近期 HRV 处于你个人高值区，自主神经调节状态优良。"
    elif hrv_recent_avg < hrv_p25:
        hrv_insight += "近期 HRV 偏向你个人低值区，建议关注近期压力和恢复状况。"
    else:
        hrv_insight += "近期在你个人正常范围内。"
else:
    hrv_insight = f"HRV 平均 {avg_hrv:.0f} ms，{'反映自主神经调节能力良好' if avg_hrv > 30 else '建议通过有氧运动和冥想提升'}。"

# 4) RHR 与 HRV 相关性洞察
rhr_hrv_correlation = ""
if len(rhr_v) >= 7 and len(hrv_v) >= 7:
    # 检查最近一周 RHR 低的日子 HRV 是否高（通常呈负相关）
    rhr_hrv_correlation = "医学上，静息心率和 HRV 通常呈负相关——RHR 越低，HRV 越高，意味着心脏「少跳但跳得更有力」。观察你的数据趋势线，如果两者同步变化（一升一降），说明你的自主神经系统反馈机制运作良好。"

# ========== 深度睡眠分析 ==========
sleep_insight_detailed = ""

# Watch 期间的详细分析
if watch_sleeps:
    # 基本统计
    total_hours_list = [s['total_hours'] for s in watch_sleeps]
    deep_hours_list = [s['deep'] for s in watch_sleeps if s['deep'] > 0]
    rem_hours_list = [s['rem'] for s in watch_sleeps if s['rem'] > 0]
    core_hours_list = [s['core'] for s in watch_sleeps if s['core'] > 0]
    awake_hours_list = [s['awake'] for s in watch_sleeps if s['awake'] > 0]
    
    avg_total = sum(total_hours_list) / len(total_hours_list) if total_hours_list else 0
    avg_deep_h = sum(deep_hours_list) / len(deep_hours_list) if deep_hours_list else 0
    avg_rem_h = sum(rem_hours_list) / len(rem_hours_list) if rem_hours_list else 0
    avg_core_h = sum(core_hours_list) / len(core_hours_list) if core_hours_list else 0
    avg_awake_h = sum(awake_hours_list) / len(awake_hours_list) if awake_hours_list else 0
    
    # 深睡比例评估
    deep_ratio = avg_deep_h / avg_total * 100 if avg_total > 0 else 0
    rem_ratio = avg_rem_h / avg_total * 100 if avg_total > 0 else 0
    core_ratio = avg_core_h / avg_total * 100 if avg_total > 0 else 0
    
    sleep_insight_detailed = f"Apple Watch 期间（{len(watch_sleeps)} 夜）：平均总睡眠 {avg_total:.1f} 小时，"
    
    # 总时长评估
    if avg_total >= 7:
        sleep_insight_detailed += "达到成人推荐的 7-9 小时标准。"
    elif avg_total >= 6:
        sleep_insight_detailed += "略低于推荐的 7 小时标准，长期不足可能影响免疫力和认知功能。"
    else:
        sleep_insight_detailed += "明显不足（推荐 7-9 小时），需重点关注！睡眠不足会影响激素平衡、情绪和代谢健康。"
    
    # 深睡分析（推荐占比 15-25%，约 1-2 小时）
    sleep_insight_detailed += f"<br><br><strong>深度睡眠：</strong>平均 {avg_deep_h:.1f} 小时（占比 {deep_ratio:.0f}%）。"
    if deep_ratio >= 15 and deep_ratio <= 25:
        sleep_insight_detailed += "占比在 15-25% 的理想范围内，身体修复和生长激素分泌充足。"
    elif deep_ratio < 15:
        sleep_insight_detailed += f"占比低于 15% 的理想下限。深睡是身体物理修复的核心阶段，不足可能导致：肌肉恢复慢、免疫力下降、皮肤修复受影响。建议：睡前避免酒精和咖啡因，保持卧室温度在 18-20°C，规律运动（但避免睡前 2 小时剧烈运动）。"
    else:
        sleep_insight_detailed += "占比超过 25%，属于偏高水平，这通常出现在高强度运动后的恢复期，如果持续偏高也可能反映身体正在对抗某些压力源。"
    
    # REM 分析（推荐占比 20-25%，约 1.5-2 小时）
    sleep_insight_detailed += f"<br><br><strong>REM 睡眠：</strong>平均 {avg_rem_h:.1f} 小时（占比 {rem_ratio:.0f}%）。"
    if rem_ratio >= 20:
        sleep_insight_detailed += "处于健康水平，REM 阶段是情绪调节和记忆巩固的关键期，充足的 REM 有助于学习能力和情绪稳定。"
    elif rem_ratio >= 15:
        sleep_insight_detailed += "略低于理想的 20-25%，但仍在可接受范围。REM 不足可能影响记忆巩固和情绪调节。提升策略：保持规律作息（REM 在后半夜更集中），避免闹钟在 REM 阶段打断睡眠。"
    else:
        sleep_insight_detailed += f"偏低（理想 20-25%），这可能影响记忆力、创造力和情绪健康。常见原因包括：酒精摄入（抑制 REM）、睡眠时间不足（REM 集中在后半夜）、某些药物影响。建议优先保证充足的总睡眠时长。"
    
    # 睡眠效率（入睡后清醒时间）
    if avg_awake_h > 0:
        efficiency = avg_total / (avg_total + avg_awake_h) * 100
        sleep_insight_detailed += f"<br><br><strong>睡眠效率：</strong>{efficiency:.0f}%（夜间平均清醒 {avg_awake_h * 60:.0f} 分钟）。"
        if efficiency >= 85:
            sleep_insight_detailed += "效率良好（>85% 为健康标准），入睡和维持睡眠能力都不错。"
        else:
            sleep_insight_detailed += "效率偏低（<85%），夜间频繁醒来较多。可能原因：环境噪音/光线、压力焦虑、睡前屏幕时间过长。建议尝试睡前放松仪式（冥想、阅读）。"
    
    # 周末 vs 工作日分析
    weekday_sleeps = [s for s in watch_sleeps if datetime.strptime(s['date'], '%Y-%m-%d').weekday() < 5]
    weekend_sleeps = [s for s in watch_sleeps if datetime.strptime(s['date'], '%Y-%m-%d').weekday() >= 5]
    if weekday_sleeps and weekend_sleeps:
        wd_avg = sum(s['total_hours'] for s in weekday_sleeps) / len(weekday_sleeps)
        we_avg = sum(s['total_hours'] for s in weekend_sleeps) / len(weekend_sleeps)
        diff = we_avg - wd_avg
        sleep_insight_detailed += f"<br><br><strong>作息规律性：</strong>工作日平均 {wd_avg:.1f}h，周末平均 {we_avg:.1f}h，"
        if abs(diff) > 1:
            sleep_insight_detailed += f"差异 {abs(diff):.1f} 小时。周末显著{'多' if diff > 0 else '少'}于工作日，存在「社交时差」现象。这种不规律作息会扰乱昼夜节律，建议将周末和工作日的起床时间差控制在 1 小时以内。"
        elif abs(diff) > 0.5:
            sleep_insight_detailed += f"差异 {abs(diff):.1f} 小时，存在轻度作息偏差，整体尚可。"
        else:
            sleep_insight_detailed += "差异很小，作息非常规律，这对昼夜节律的维持非常有利！"
    
    # 最近趋势
    if len(watch_sleeps) >= 14:
        recent_7 = watch_sleeps[-7:]
        earlier_7 = watch_sleeps[-14:-7]
        recent_avg = sum(s['total_hours'] for s in recent_7) / len(recent_7)
        earlier_avg = sum(s['total_hours'] for s in earlier_7) / len(earlier_7)
        trend_diff = recent_avg - earlier_avg
        if abs(trend_diff) > 0.3:
            sleep_insight_detailed += f"<br><br><strong>近期趋势：</strong>最近一周平均 {recent_avg:.1f}h，相比前一周{'增加' if trend_diff > 0 else '减少'}了 {abs(trend_diff):.1f} 小时。"
            if trend_diff < -0.5:
                sleep_insight_detailed += "睡眠时长明显减少，需要注意是否有压力增加或作息变化。"

# 前手环期间的洞察
pre_watch_sleeps = [s for s in sleep_nightly_data if not s['is_watch_period']]
if pre_watch_sleeps:
    pre_avg = sum(s['total_hours'] for s in pre_watch_sleeps) / len(pre_watch_sleeps)
    pre_monthly_avgs = {}
    for s in pre_watch_sleeps:
        m = to_month(s['date'])
        if m not in pre_monthly_avgs:
            pre_monthly_avgs[m] = []
        pre_monthly_avgs[m].append(s['total_hours'])
    
    # 季节性变化
    season_data = {'春(3-5月)': [], '夏(6-8月)': [], '秋(9-11月)': [], '冬(12-2月)': []}
    for s in pre_watch_sleeps:
        month = int(s['date'][5:7])
        if month in (3,4,5): season_data['春(3-5月)'].append(s['total_hours'])
        elif month in (6,7,8): season_data['夏(6-8月)'].append(s['total_hours'])
        elif month in (9,10,11): season_data['秋(9-11月)'].append(s['total_hours'])
        else: season_data['冬(12-2月)'].append(s['total_hours'])
    
    season_avgs = {k: sum(v)/len(v) for k, v in season_data.items() if v}
    if len(season_avgs) >= 2:
        best_season = max(season_avgs, key=season_avgs.get)
        worst_season = min(season_avgs, key=season_avgs.get)
        pre_watch_insight = f"小米手环期间（{len(pre_watch_sleeps)} 夜）：平均睡眠 {pre_avg:.1f} 小时。季节性特征明显——{best_season}睡得最多（平均 {season_avgs[best_season]:.1f}h），{worst_season}最少（平均 {season_avgs[worst_season]:.1f}h）。"
    else:
        pre_watch_insight = f"小米手环期间（{len(pre_watch_sleeps)} 夜）：平均睡眠 {pre_avg:.1f} 小时。"
else:
    pre_watch_insight = ""

step_target_comment = "达标" if total_steps_all/len(step_dates) >= 8000 else "未达 8000 目标"
step_insight_class = " warn" if total_steps_all/len(step_dates) < 8000 else ""
step_insight = "已达到推荐的 8000 步/天目标，保持得很好！" if total_steps_all/len(step_dates) >= 8000 else "略低于推荐的 8000 步/天目标，建议增加日常步行。"
min_cycle = min(c['days'] for c in cycle_lengths) if cycle_lengths else 0
max_cycle = max(c['days'] for c in cycle_lengths) if cycle_lengths else 0
cycle_avg_comment = f"平均周期 {avg_cycle_len:.0f} 天，" if avg_cycle_len > 0 else ""
cycle_range_comment = "处于正常范围（24-38天）。" if 24 <= avg_cycle_len <= 38 else ""
cycle_var_comment = "周期波动较大，可能受压力、运动、旅行等因素影响。" if cycle_lengths and (max_cycle - min_cycle) > 10 else "周期较为规律。"
swim_date_range = f"{swim_analysis[0]['date']} ~ {swim_analysis[-1]['date']}" if swim_analysis else "? ~ ?"
if len(swim_analysis) >= 2:
    swim_span_days = (datetime.strptime(swim_analysis[-1]['date'], '%Y-%m-%d') - datetime.strptime(swim_analysis[0]['date'], '%Y-%m-%d')).days
    swim_freq = f"约{total_swim / swim_span_days * 7:.1f} 次/周" if swim_span_days > 0 else ""
else:
    swim_freq = ""
if first_pace > latest_pace and first_pace > 0:
    pace_improve = f"配速从 {first_pace:.2f} 提升到 {latest_pace:.2f} min/100m，提升了 {((first_pace - latest_pace) / first_pace * 100):.1f}%！"
else:
    pace_improve = ""
if len(valid_swims) >= 3 and valid_swims[-1]['distance_m'] > valid_swims[0]['distance_m']:
    dist_improve = "距离逐步增加，体能在稳步提升。"
else:
    dist_improve = ""
daily_avg_steps = total_steps_all / len(step_dates)

# ============================================================
# 交叉关联分析 & 个人动态基准 & 压力预警
# ============================================================
print("正在进行交叉关联分析...")

# ---- A. 睡眠与次日恢复的关联 (Sleep -> Next-day HRV/RHR) ----
sleep_recovery_insight = ""
if watch_sleeps and len(rhr_v) >= 7 and len(hrv_v) >= 7:
    # 构建日期索引
    rhr_by_date = dict(rhr_values)
    hrv_by_date = {d: v for d, v in hrv_daily_avg}
    
    good_sleep_next_rhr = []
    bad_sleep_next_rhr = []
    good_sleep_next_hrv = []
    bad_sleep_next_hrv = []
    
    deep_vs_next_hrv = []  # (deep_ratio, next_hrv) 用于关联分析
    
    for s in watch_sleeps:
        next_date = (datetime.strptime(s['date'], '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
        next_rhr = rhr_by_date.get(next_date)
        next_hrv = hrv_by_date.get(next_date)
        
        if next_rhr is not None and s['total_hours'] > 0:
            if s['total_hours'] >= 7:
                good_sleep_next_rhr.append(next_rhr)
            elif s['total_hours'] < 6:
                bad_sleep_next_rhr.append(next_rhr)
        
        if next_hrv is not None and s['total_hours'] > 0:
            if s['total_hours'] >= 7:
                good_sleep_next_hrv.append(next_hrv)
            elif s['total_hours'] < 6:
                bad_sleep_next_hrv.append(next_hrv)
        
        if next_hrv is not None and s['deep'] > 0 and s['total_hours'] > 0:
            deep_ratio_val = s['deep'] / s['total_hours']
            deep_vs_next_hrv.append((deep_ratio_val, next_hrv))
    
    sleep_recovery_insight = "<strong>睡眠 → 次日恢复关联：</strong>"
    
    if good_sleep_next_rhr and bad_sleep_next_rhr:
        avg_good_rhr = sum(good_sleep_next_rhr) / len(good_sleep_next_rhr)
        avg_bad_rhr = sum(bad_sleep_next_rhr) / len(bad_sleep_next_rhr)
        rhr_diff = avg_bad_rhr - avg_good_rhr
        sleep_recovery_insight += f"<br>在你的数据中，睡眠≥7h 的夜晚后次日静息心率平均为 {avg_good_rhr:.0f} bpm，而睡眠<6h 的夜晚后次日平均为 {avg_bad_rhr:.0f} bpm"
        if rhr_diff > 1:
            sleep_recovery_insight += f"（高出 {rhr_diff:.1f} bpm）。数据显示你的身体对睡眠不足有明显的心率反应。"
        else:
            sleep_recovery_insight += "。两者差异不大，说明你的心血管系统恢复韧性较好。"
    
    if good_sleep_next_hrv and bad_sleep_next_hrv:
        avg_good_hrv = sum(good_sleep_next_hrv) / len(good_sleep_next_hrv)
        avg_bad_hrv = sum(bad_sleep_next_hrv) / len(bad_sleep_next_hrv)
        hrv_diff = avg_good_hrv - avg_bad_hrv
        sleep_recovery_insight += f"<br>HRV 方面：好睡眠后次日平均 {avg_good_hrv:.0f} ms，差睡眠后 {avg_bad_hrv:.0f} ms"
        if hrv_diff > 3:
            sleep_recovery_insight += f"（差距 {hrv_diff:.1f} ms）。充足睡眠与更高的 HRV（即更好的自主神经调节）之间存在明显关联。"
        else:
            sleep_recovery_insight += "，差异较小。"
    
    # 深睡比例与次日HRV的关联
    if len(deep_vs_next_hrv) >= 10:
        deep_sorted = sorted(deep_vs_next_hrv, key=lambda x: x[0])
        bottom_q = deep_sorted[:len(deep_sorted)//4]
        top_q = deep_sorted[-(len(deep_sorted)//4):]
        avg_hrv_low_deep = sum(h for _, h in bottom_q) / len(bottom_q) if bottom_q else 0
        avg_hrv_high_deep = sum(h for _, h in top_q) / len(top_q) if top_q else 0
        if avg_hrv_high_deep > avg_hrv_low_deep + 2:
            sleep_recovery_insight += f"<br>深睡比例也有影响：深睡占比最高的 25% 夜晚，次日 HRV 平均为 {avg_hrv_high_deep:.0f} ms，而深睡最低的 25% 夜晚仅 {avg_hrv_low_deep:.0f} ms，深度睡眠的「修复力」在你的数据中有所体现。"

# ---- B. 运动负荷与心率恢复 (Strain -> Recovery) ----
exercise_recovery_insight = ""
if all_workouts and len(rhr_v) >= 7:
    rhr_by_date = dict(rhr_values)
    
    # 找出高强度运动日
    workout_dates = set()
    heavy_workout_dates = []
    for w in all_workouts:
        workout_dates.add(w['date'])
        # 高强度：HIIT、游泳、跑步、力量训练（时长>30min）
        if w['type'] in ('HighIntensityIntervalTraining', 'Swimming', 'Running') or \
           (w['type'] == 'TraditionalStrengthTraining' and w['duration_min'] > 30):
            heavy_workout_dates.append(w['date'])
    
    # 运动日 vs 休息日的次日 RHR
    workout_next_rhr = []
    rest_next_rhr = []
    
    for d, rhr_val in rhr_by_date.items():
        prev_date = (datetime.strptime(d, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')
        if prev_date in workout_dates:
            workout_next_rhr.append(rhr_val)
        elif prev_date not in workout_dates and prev_date >= WATCH_DATE:
            rest_next_rhr.append(rhr_val)
    
    if workout_next_rhr and rest_next_rhr:
        avg_w_rhr = sum(workout_next_rhr) / len(workout_next_rhr)
        avg_r_rhr = sum(rest_next_rhr) / len(rest_next_rhr)
        diff_wr = avg_w_rhr - avg_r_rhr
        
        exercise_recovery_insight = f"<strong>运动负荷 → 心率反馈：</strong>"
        exercise_recovery_insight += f"<br>运动日之后的次日 RHR 平均为 {avg_w_rhr:.0f} bpm，非运动日后为 {avg_r_rhr:.0f} bpm"
        
        if diff_wr > 2:
            exercise_recovery_insight += f"（高 {diff_wr:.1f} bpm）。运动后 RHR 轻微升高是正常的生理反应，说明身体正在修复和适应。"
            # 检查是否存在过度训练迹象（连续3天以上运动后RHR持续偏高）
            consecutive_high = 0
            max_consecutive = 0
            heavy_dates_set = set(heavy_workout_dates)
            for d in sorted(rhr_by_date.keys()):
                if d in heavy_dates_set:
                    personal_avg = sum(rhr_by_date[dd] for dd in sorted(rhr_by_date.keys()) if dd <= d)
                    personal_avg /= len([dd for dd in rhr_by_date.keys() if dd <= d])
                    if rhr_by_date[d] > personal_avg + 3:
                        consecutive_high += 1
                        max_consecutive = max(max_consecutive, consecutive_high)
                    else:
                        consecutive_high = 0
            if max_consecutive >= 3:
                exercise_recovery_insight += f" 值得注意的是，数据中出现过连续 {max_consecutive} 天高强度运动后 RHR 持续高于个人均值的情况，这可能是过度训练的信号。建议在高强度运动后安排 1-2 天轻度恢复日。"
        elif diff_wr < -1:
            exercise_recovery_insight += "，运动日后 RHR 反而更低，说明你的运动强度适中，身体恢复和适应能力很好！"
        else:
            exercise_recovery_insight += "，差异很小，说明运动强度在身体的承受范围内，恢复良好。"
    
    # NEAT 分析（非运动性活动消耗 = 步数对总能量的贡献）
    if step_dates and energy_monthly_stats:
        # 对比运动日和非运动日的步数
        workout_day_steps = []
        rest_day_steps = []
        for d in step_dates:
            if d >= WATCH_DATE:
                if d in workout_dates:
                    workout_day_steps.append(step_count_daily[d])
                else:
                    rest_day_steps.append(step_count_daily[d])
        
        if workout_day_steps and rest_day_steps:
            avg_w_steps = sum(workout_day_steps) / len(workout_day_steps)
            avg_r_steps = sum(rest_day_steps) / len(rest_day_steps)
            exercise_recovery_insight += f"<br><br><strong>NEAT（非运动性活动）：</strong>运动日平均步数 {avg_w_steps:.0f}，非运动日 {avg_r_steps:.0f}。"
            if avg_r_steps < avg_w_steps * 0.6:
                exercise_recovery_insight += "非运动日步数明显偏低，存在「运动补偿效应」——运动日之外活动量显著下降。建议即使在休息日也保持基本步行量，NEAT 对总体能量消耗的贡献往往比运动本身更大。"
            else:
                exercise_recovery_insight += "非运动日也保持了不错的活动量，日常 NEAT 水平健康。"

# ---- C. 月经周期与心率/睡眠/运动的交叉分析 ----
menstrual_cross_insight = ""
if cycle_lengths and len(rhr_v) >= 14:
    rhr_by_date = dict(rhr_values)
    hrv_by_date_dict = {d: v for d, v in hrv_daily_avg}
    
    # 对每个周期划分阶段：
    # 滤泡期(卵泡期) = day 1~13, 排卵期 = day 14, 黄体期 = day 15~周期结束
    follicular_rhr = []
    luteal_rhr = []
    follicular_hrv = []
    luteal_hrv = []
    follicular_sleep = []
    luteal_sleep = []
    
    sleep_by_date = {s['date']: s for s in sleep_nightly_data}
    
    for c in cycle_lengths:
        start = datetime.strptime(c['start'], '%Y-%m-%d')
        cycle_len = c['days']
        ovulation_day = min(14, cycle_len // 2)
        
        for day_offset in range(cycle_len):
            current = start + timedelta(days=day_offset)
            d_str = current.strftime('%Y-%m-%d')
            
            is_follicular = day_offset < ovulation_day
            
            if d_str in rhr_by_date:
                if is_follicular:
                    follicular_rhr.append(rhr_by_date[d_str])
                else:
                    luteal_rhr.append(rhr_by_date[d_str])
            
            if d_str in hrv_by_date_dict:
                if is_follicular:
                    follicular_hrv.append(hrv_by_date_dict[d_str])
                else:
                    luteal_hrv.append(hrv_by_date_dict[d_str])
            
            if d_str in sleep_by_date:
                if is_follicular:
                    follicular_sleep.append(sleep_by_date[d_str]['total_hours'])
                else:
                    luteal_sleep.append(sleep_by_date[d_str]['total_hours'])
    
    menstrual_cross_insight = "<strong>月经周期 × 身体指标交叉分析：</strong>"
    
    if follicular_rhr and luteal_rhr:
        avg_f_rhr = sum(follicular_rhr) / len(follicular_rhr)
        avg_l_rhr = sum(luteal_rhr) / len(luteal_rhr)
        diff_rhr = avg_l_rhr - avg_f_rhr
        menstrual_cross_insight += f"<br><br>卵泡期（经期~排卵前）平均 RHR {avg_f_rhr:.1f} bpm，黄体期（排卵后~下次经期）平均 {avg_l_rhr:.1f} bpm"
        if diff_rhr > 0.5:
            menstrual_cross_insight += f"（黄体期高 {diff_rhr:.1f} bpm）。这符合生理规律——黄体期孕酮升高会导致基础体温和心率自然上升，属于正常现象，不必因为经前 RHR 升高而焦虑。"
        else:
            menstrual_cross_insight += "，两个阶段差异不明显。"
    
    if follicular_hrv and luteal_hrv:
        avg_f_hrv = sum(follicular_hrv) / len(follicular_hrv)
        avg_l_hrv = sum(luteal_hrv) / len(luteal_hrv)
        diff_hrv_mc = avg_f_hrv - avg_l_hrv
        menstrual_cross_insight += f"<br><br>HRV 方面：卵泡期平均 {avg_f_hrv:.0f} ms，黄体期 {avg_l_hrv:.0f} ms"
        if diff_hrv_mc > 2:
            menstrual_cross_insight += f"（黄体期低 {diff_hrv_mc:.0f} ms）。黄体期 HRV 降低也是常见的生理性变化，意味着此阶段身体对压力的缓冲能力稍低，适合安排恢复性训练而非突破性训练。"
        else:
            menstrual_cross_insight += "，差异较小。"
    
    if follicular_sleep and luteal_sleep:
        avg_f_sleep = sum(follicular_sleep) / len(follicular_sleep)
        avg_l_sleep = sum(luteal_sleep) / len(luteal_sleep)
        diff_sleep_mc = avg_l_sleep - avg_f_sleep
        menstrual_cross_insight += f"<br><br>睡眠时长：卵泡期平均 {avg_f_sleep:.1f}h，黄体期 {avg_l_sleep:.1f}h"
        if diff_sleep_mc < -0.2:
            menstrual_cross_insight += f"（黄体期少 {abs(diff_sleep_mc):.1f}h）。经前期睡眠质量下降是常见问题，孕酮下降和体温波动都可能影响入睡和维持睡眠。建议经前一周可适当提前就寝时间、使用较凉爽的寝具。"
        elif diff_sleep_mc > 0.2:
            menstrual_cross_insight += f"（黄体期多 {diff_sleep_mc:.1f}h）。你在黄体期反而睡得更多，这可能是身体自然调节的结果。"
        else:
            menstrual_cross_insight += "，差异不大。"
    
    if not (follicular_rhr and luteal_rhr):
        menstrual_cross_insight += "<br>月经周期记录与 Apple Watch 心率数据重合期较短，暂无法进行深度交叉分析。随着数据积累，这部分分析会更准确。"

# ---- D. 压力预警 (7天 vs 30天 Rolling Average) ----
stress_alert_insight = ""
stress_alert_level = ""  # "good", "warn", "alert"

if len(rhr_v) >= 30 and len(hrv_v) >= 30:
    rhr_7d = rhr_v[-7:]
    rhr_30d = rhr_v[-30:]
    hrv_7d = hrv_v[-7:]
    hrv_30d = hrv_v[-30:]
    
    avg_rhr_7 = sum(rhr_7d) / len(rhr_7d)
    avg_rhr_30 = sum(rhr_30d) / len(rhr_30d)
    avg_hrv_7 = sum(hrv_7d) / len(hrv_7d)
    avg_hrv_30 = sum(hrv_30d) / len(hrv_30d)
    
    rhr_pct_change = (avg_rhr_7 - avg_rhr_30) / avg_rhr_30 * 100
    hrv_pct_change = (avg_hrv_7 - avg_hrv_30) / avg_hrv_30 * 100
    
    stress_alert_insight = f"<strong>近 7 天 vs 近 30 天动态基准对比：</strong>"
    stress_alert_insight += f"<br>RHR：7天均值 {avg_rhr_7:.1f} bpm vs 30天均值 {avg_rhr_30:.1f} bpm（{'↑' if rhr_pct_change > 0 else '↓'}{abs(rhr_pct_change):.1f}%）"
    stress_alert_insight += f"<br>HRV：7天均值 {avg_hrv_7:.0f} ms vs 30天均值 {avg_hrv_30:.0f} ms（{'↑' if hrv_pct_change > 0 else '↓'}{abs(hrv_pct_change):.1f}%）"
    
    # 检查是否 HRV 连续3天显著下降且 RHR 上升
    hrv_consecutive_drop = 0
    rhr_consecutive_rise = 0
    for i in range(max(0, len(hrv_v) - 7), len(hrv_v)):
        if hrv_v[i] < avg_hrv_30 * 0.85:
            hrv_consecutive_drop += 1
        else:
            hrv_consecutive_drop = 0
    for i in range(max(0, len(rhr_v) - 7), len(rhr_v)):
        if rhr_v[i] > avg_rhr_30 * 1.05:
            rhr_consecutive_rise += 1
        else:
            rhr_consecutive_rise = 0
    
    if hrv_consecutive_drop >= 3 and rhr_consecutive_rise >= 3:
        stress_alert_level = "alert"
        stress_alert_insight += "<br><br>⚠️ <strong>疲劳预警：</strong>近期 HRV 连续多天低于个人30天均值 15%+ 且 RHR 持续偏高，这一组合模式往往提示疲劳累积或免疫力下降。建议：优先保证睡眠、减少高强度训练、关注是否有感冒等不适症状。"
    elif rhr_pct_change > 5 or hrv_pct_change < -10:
        stress_alert_level = "warn"
        stress_alert_insight += "<br><br>近期指标略有波动。RHR 偏离幅度或 HRV 下降幅度值得关注，但尚未达到预警水平。建议这两天留意休息质量。"
    else:
        stress_alert_level = "good"
        stress_alert_insight += "<br><br>✅ 你的近期指标与个人30天基准保持一致，身体恢复和压力管理状态良好，无需特别担心。"

# ---- E. 宏观30天快照 ----
macro_30d = {}
today_str = sorted(rhr_by_date.keys())[-1] if rhr_values else step_dates[-1] if step_dates else ""
if today_str:
    cutoff_30d = (datetime.strptime(today_str, '%Y-%m-%d') - timedelta(days=30)).strftime('%Y-%m-%d')
    
    # 30天 RHR
    rhr_30d_vals = [v for d, v in rhr_values if d > cutoff_30d]
    macro_30d['rhr'] = sum(rhr_30d_vals) / len(rhr_30d_vals) if rhr_30d_vals else 0
    
    # 30天 HRV
    hrv_30d_vals = [v for d, v in hrv_daily_avg if d > cutoff_30d]
    macro_30d['hrv'] = sum(hrv_30d_vals) / len(hrv_30d_vals) if hrv_30d_vals else 0
    
    # 30天平均睡眠
    sleep_30d_vals = [s['total_hours'] for s in sleep_nightly_data if s['date'] > cutoff_30d]
    macro_30d['sleep'] = sum(sleep_30d_vals) / len(sleep_30d_vals) if sleep_30d_vals else 0
    
    # 30天平均步数
    step_30d_vals = [step_count_daily[d] for d in step_dates if d > cutoff_30d]
    macro_30d['steps'] = sum(step_30d_vals) / len(step_30d_vals) if step_30d_vals else 0
    
    # 30天运动次数
    workout_30d = [w for w in all_workouts if w['date'] > cutoff_30d]
    macro_30d['workouts'] = len(workout_30d)
    
    # 与前30天对比
    cutoff_60d = (datetime.strptime(today_str, '%Y-%m-%d') - timedelta(days=60)).strftime('%Y-%m-%d')
    rhr_prev30 = [v for d, v in rhr_values if cutoff_60d < d <= cutoff_30d]
    hrv_prev30 = [v for d, v in hrv_daily_avg if cutoff_60d < d <= cutoff_30d]
    sleep_prev30 = [s['total_hours'] for s in sleep_nightly_data if cutoff_60d < s['date'] <= cutoff_30d]
    step_prev30 = [step_count_daily[d] for d in step_dates if cutoff_60d < d <= cutoff_30d]
    
    def delta_str(current, prev_vals, unit="", lower_better=False):
        if not prev_vals:
            return ""
        prev_avg = sum(prev_vals) / len(prev_vals)
        diff = current - prev_avg
        if abs(diff) < 0.01:
            return " (持平)"
        arrow = "↑" if diff > 0 else "↓"
        color = ""
        if lower_better:
            color = "#34C759" if diff < 0 else "#FF9500"
        else:
            color = "#34C759" if diff > 0 else "#FF9500"
        return f' <span style="color:{color};font-size:12px">{arrow}{abs(diff):.1f}{unit}</span>'
    
    macro_30d['rhr_delta'] = delta_str(macro_30d['rhr'], rhr_prev30, " bpm", lower_better=True)
    macro_30d['hrv_delta'] = delta_str(macro_30d['hrv'], hrv_prev30, " ms", lower_better=False)
    macro_30d['sleep_delta'] = delta_str(macro_30d['sleep'], sleep_prev30, "h", lower_better=False)
    macro_30d['steps_delta'] = delta_str(macro_30d['steps'], step_prev30, "", lower_better=False)

# ---- F. 2-3个核心行动洞察 ----
action_insights = []

# 洞察1: 睡眠是否是最大瓶颈
if watch_sleeps:
    if avg_total < 7:
        action_insights.append(
            f"<strong>优先提升睡眠时长</strong><br>"
            f"你的近期平均睡眠 {avg_total:.1f} 小时，低于 7 小时推荐标准。"
            f"在你的数据中，睡眠不足与次日 RHR 升高、HRV 下降存在关联。"
            f"<em>建议微习惯：</em>设定固定的「准备就寝」闹钟（比目标入睡时间提前 30 分钟），"
            f"用这段时间做睡前放松（关屏、调暗灯光、轻度拉伸或阅读）。"
        )
    elif deep_ratio < 15:
        action_insights.append(
            f"<strong>关注深度睡眠质量</strong><br>"
            f"总睡眠时长达标（{avg_total:.1f}h），但深睡占比仅 {deep_ratio:.0f}%（理想 15-25%）。"
            f"<em>建议微习惯：</em>睡前 2 小时内避免酒精和咖啡因；"
            f"保持卧室温度 18-20°C（凉爽环境有助于进入深睡）；"
            f"规律运动但避免临睡前高强度训练。"
        )

# 洞察2: 运动恢复平衡
if exercise_recovery_insight and all_workouts:
    recent_workouts = [w for w in all_workouts if w['date'] > cutoff_30d] if today_str else []
    if len(recent_workouts) >= 15:
        action_insights.append(
            f"<strong>优化运动与恢复的节奏</strong><br>"
            f"近30天锻炼 {len(recent_workouts)} 次，频率较高。"
            f"<em>建议微习惯：</em>采用「2+1」模式——连续 2 天训练后安排 1 天主动恢复（轻度步行、瑜伽或泡沫轴放松）。"
            f"在恢复日监测你的 RHR，如果比个人均值高 3+ bpm，说明身体尚未完全恢复。"
        )
    elif len(recent_workouts) <= 4:
        action_insights.append(
            f"<strong>逐步增加运动频率</strong><br>"
            f"近30天锻炼 {len(recent_workouts)} 次，建议增加到每周 3-4 次。"
            f"<em>建议微习惯：</em>从最低门槛开始——每周固定 3 天「运动日」，"
            f"即使只是 15 分钟的快走或拉伸也算数。建立习惯比强度更重要。"
        )

# 洞察3: 基于步数的 NEAT
if daily_avg_steps < 6000:
    action_insights.append(
        f"<strong>提升日常活动量（NEAT）</strong><br>"
        f"日均步数 {daily_avg_steps:.0f} 步，偏低。研究表明日常非运动性活动消耗（NEAT）"
        f"对体重管理和代谢健康的贡献甚至大于专门的运动时段。"
        f"<em>建议微习惯：</em>每隔 1 小时站起来走动 5 分钟；选择步行代替短途出行；"
        f"午餐后散步 15 分钟。"
    )

# 如果洞察不够，补充一个通用的正面洞察
if len(action_insights) < 2:
    if avg_rhr < 70 and avg_hrv > 35:
        action_insights.append(
            f"<strong>心血管健康状态良好</strong><br>"
            f"RHR {avg_rhr:.0f} bpm、HRV {avg_hrv:.0f} ms，你的心血管指标在个人历史数据中保持稳定且处于健康区间。"
            f"<em>建议：</em>维持当前的运动和作息习惯，定期回顾数据变化趋势即可。"
        )

print("交叉关联分析完成。")

html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>健康数据综合分析报告</title>
    <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Helvetica Neue', sans-serif;
            background: #F2F2F7;
            color: #1D1D1F;
            line-height: 1.6;
        }}
        .hero {{
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 40%, #0f3460 100%);
            color: white;
            padding: 56px 40px 48px;
            text-align: center;
        }}
        .hero h1 {{
            font-size: 34px;
            font-weight: 700;
            letter-spacing: -0.5px;
            margin-bottom: 8px;
        }}
        .hero .tagline {{
            font-size: 17px;
            opacity: 0.75;
            margin-bottom: 24px;
        }}
        .hero-stats {{
            display: flex;
            justify-content: center;
            gap: 32px;
            flex-wrap: wrap;
        }}
        .hero-stat {{
            text-align: center;
        }}
        .hero-stat .num {{
            font-size: 28px;
            font-weight: 700;
            color: #5AC8FA;
        }}
        .hero-stat .label {{
            font-size: 12px;
            opacity: 0.6;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        .container {{
            max-width: 1100px;
            margin: 0 auto;
            padding: 20px;
        }}
        .nav-bar {{
            background: rgba(255,255,255,0.95);
            backdrop-filter: blur(20px);
            border-radius: 16px;
            padding: 12px 20px;
            margin: -24px auto 24px;
            max-width: 1100px;
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
            justify-content: center;
            box-shadow: 0 4px 20px rgba(0,0,0,0.08);
            position: sticky;
            top: 8px;
            z-index: 100;
        }}
        .nav-btn {{
            padding: 8px 16px;
            border-radius: 20px;
            border: none;
            background: transparent;
            color: #666;
            font-size: 14px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
        }}
        .nav-btn:hover {{ background: #F2F2F7; color: #1D1D1F; }}
        .nav-btn.active {{ background: #007AFF; color: white; }}
        .section {{
            background: white;
            border-radius: 20px;
            padding: 32px;
            margin: 20px 0;
            box-shadow: 0 1px 8px rgba(0,0,0,0.04);
        }}
        .section h2 {{
            font-size: 22px;
            font-weight: 600;
            margin-bottom: 4px;
        }}
        .section .subtitle {{
            font-size: 14px;
            color: #86868B;
            margin-bottom: 20px;
        }}
        .chart-container {{ width: 100%; margin: 12px 0; }}
        .insight-box {{
            background: linear-gradient(135deg, #F5F5F7, #E8E8ED);
            border-radius: 14px;
            padding: 16px 20px;
            margin: 16px 0;
            font-size: 14px;
            line-height: 1.7;
        }}
        .insight-box strong {{ color: #007AFF; }}
        .insight-box.warn {{ background: linear-gradient(135deg, #FFF3CD, #FFF8E1); }}
        .insight-box.warn strong {{ color: #FF9500; }}
        .insight-box.good {{ background: linear-gradient(135deg, #D4EDDA, #E8F5E9); }}
        .insight-box.good strong {{ color: #34C759; }}
        .insight-box.alert {{ background: linear-gradient(135deg, #FFE0E0, #FFE8E8); }}
        .insight-box.alert strong {{ color: #FF3B30; }}
        .action-card {{
            border-left: 4px solid #007AFF;
        }}
        .action-card em {{
            display: inline-block;
            color: #34C759;
            font-style: normal;
            font-weight: 600;
            margin-top: 4px;
        }}
        .stat-cards {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
            gap: 12px;
            margin: 16px 0;
        }}
        .stat-card {{
            background: #F9F9FB;
            border-radius: 14px;
            padding: 16px;
            text-align: center;
        }}
        .stat-card .value {{
            font-size: 26px;
            font-weight: 700;
            color: #1D1D1F;
        }}
        .stat-card .label {{
            font-size: 12px;
            color: #86868B;
            margin-top: 4px;
        }}
        .stat-card .sub {{ font-size: 11px; color: #AEB0B6; }}
        .module-tag {{
            display: inline-block;
            padding: 3px 10px;
            border-radius: 6px;
            font-size: 11px;
            font-weight: 600;
            margin-right: 6px;
        }}
        .tag-p0 {{ background: #FFE5E5; color: #FF3B30; }}
        .tag-p1 {{ background: #FFF0DD; color: #FF9500; }}
        .tag-swim {{ background: #E3F6FC; color: #007AFF; }}
        .two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
        @media (max-width: 768px) {{
            .two-col {{ grid-template-columns: 1fr; }}
            .hero h1 {{ font-size: 26px; }}
            .hero-stats {{ gap: 16px; }}
            .stat-cards {{ grid-template-columns: repeat(2, 1fr); }}
        }}
        .swim-table {{
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
            font-size: 13px;
            margin: 12px 0;
        }}
        .swim-table th {{
            background: #F5F5F7;
            padding: 10px 12px;
            text-align: center;
            font-weight: 600;
            border-bottom: 2px solid #E5E5EA;
            position: sticky;
            top: 0;
        }}
        .swim-table td {{
            padding: 8px 12px;
            text-align: center;
            border-bottom: 1px solid #F2F2F7;
        }}
        .swim-table tr:hover td {{ background: #F9F9FB; }}
        .swim-table .best {{ color: #34C759; font-weight: 600; }}
        .footer {{
            text-align: center;
            padding: 32px 20px;
            font-size: 13px;
            color: #86868B;
        }}
    </style>
</head>
<body>

<!-- Hero -->
<div class="hero">
    <h1>个人健康数据深度分析</h1>
    <p class="tagline">2021.08 — 2026.03 | 基于 Apple Health 全量数据 · 交叉关联分析</p>
    <div class="hero-stats">
        <div class="hero-stat">
            <div class="num">{total_steps_all/1e6:.1f}M</div>
            <div class="label">总步数</div>
        </div>
        <div class="hero-stat">
            <div class="num">{total_workouts}</div>
            <div class="label">锻炼次数</div>
        </div>
        <div class="hero-stat">
            <div class="num">{len(sleep_nightly_data)}</div>
            <div class="label">睡眠夜数</div>
        </div>
        <div class="hero-stat">
            <div class="num">{avg_rhr:.0f}</div>
            <div class="label">平均静息心率</div>
        </div>
        <div class="hero-stat">
            <div class="num">{total_swim}</div>
            <div class="label">游泳次数</div>
        </div>
        <div class="hero-stat">
            <div class="num">{total_swim_dist/1000:.1f}km</div>
            <div class="label">总游泳距离</div>
        </div>
    </div>
</div>

<!-- 导航 -->
<div class="container">
<div class="nav-bar">
    <button class="nav-btn active" onclick="scrollToSection('macro')">30天快照</button>
    <button class="nav-btn" onclick="scrollToSection('heart')">心率</button>
    <button class="nav-btn" onclick="scrollToSection('sleep')">睡眠</button>
    <button class="nav-btn" onclick="scrollToSection('cross')">交叉分析</button>
    <button class="nav-btn" onclick="scrollToSection('activity')">运动/步数</button>
    <button class="nav-btn" onclick="scrollToSection('menstrual')">月经</button>
    <button class="nav-btn" onclick="scrollToSection('swim')">游泳专题</button>
    <button class="nav-btn" onclick="scrollToSection('actions')">行动建议</button>
</div>

<!-- ============== 30天宏观快照 ============== -->
<div class="section" id="macro">
    <h2>近 30 天快照</h2>
    <p class="subtitle">与前30天对比的个人动态基准 · 所有指标仅与你自己的历史做对比</p>
    
    <div class="stat-cards">
        <div class="stat-card">
            <div class="value">{macro_30d.get('rhr', 0):.0f}</div>
            <div class="label">30天平均 RHR</div>
            <div class="sub">bpm{macro_30d.get('rhr_delta', '')}</div>
        </div>
        <div class="stat-card">
            <div class="value">{macro_30d.get('hrv', 0):.0f}</div>
            <div class="label">30天平均 HRV</div>
            <div class="sub">ms{macro_30d.get('hrv_delta', '')}</div>
        </div>
        <div class="stat-card">
            <div class="value">{macro_30d.get('sleep', 0):.1f}h</div>
            <div class="label">30天平均睡眠</div>
            <div class="sub">{macro_30d.get('sleep_delta', '')}</div>
        </div>
        <div class="stat-card">
            <div class="value">{macro_30d.get('steps', 0):.0f}</div>
            <div class="label">30天日均步数</div>
            <div class="sub">{macro_30d.get('steps_delta', '')}</div>
        </div>
        <div class="stat-card">
            <div class="value">{macro_30d.get('workouts', 0)}</div>
            <div class="label">30天运动次数</div>
            <div class="sub">次</div>
        </div>
    </div>
    
    <div class="insight-box {stress_alert_level}">
        {stress_alert_insight}
    </div>
</div>

<!-- ============== 心率模块 ============== -->
<div class="section" id="heart">
    <span class="module-tag tag-p0">P0</span>
    <h2>心率综合分析</h2>
    <p class="subtitle">静息心率、HRV、步行心率、VO2Max — 你的心血管健康画像</p>
    
    <div class="stat-cards">
        <div class="stat-card">
            <div class="value">{avg_rhr:.0f}</div>
            <div class="label">平均静息心率</div>
            <div class="sub">bpm · Watch期间</div>
        </div>
        <div class="stat-card">
            <div class="value">{min_rhr}</div>
            <div class="label">最低静息心率</div>
            <div class="sub">bpm</div>
        </div>
        <div class="stat-card">
            <div class="value">{avg_hrv:.0f}</div>
            <div class="label">平均 HRV</div>
            <div class="sub">ms · SDNN</div>
        </div>
        <div class="stat-card">
            <div class="value">{latest_vo2}</div>
            <div class="label">最新 VO2Max</div>
            <div class="sub">mL/kg/min</div>
        </div>
    </div>
    
    <div id="chart_hr_trend" class="chart-container"></div>
    
    <div class="insight-box">
        <strong>长期心率趋势洞察：</strong>
        {len(hr_dates)} 天心率数据覆盖（2021.08起）。{hr_trend_insight}
        {hr_peak_insight}
    </div>
    
    <div id="chart_rhr_hrv" class="chart-container"></div>
    
    <div class="insight-box good">
        <strong>RHR 深度解读：</strong>
        {rhr_insight}
    </div>
    
    <div class="insight-box">
        <strong>HRV 深度解读：</strong>
        {hrv_insight}
        <br><br>{rhr_hrv_correlation}
    </div>
    
    <div id="chart_vo2" class="chart-container"></div>
</div>

<!-- ============== 睡眠模块 ============== -->
<div class="section" id="sleep">
    <span class="module-tag tag-p0">P0</span>
    <h2>睡眠分析</h2>
    <p class="subtitle">分两段分析 — 小米手环看总时长趋势，Apple Watch 看睡眠分期</p>
    
    <div class="stat-cards">
        <div class="stat-card">
            <div class="value">{avg_sleep:.1f}h</div>
            <div class="label">平均睡眠时长</div>
            <div class="sub">全时期</div>
        </div>
        <div class="stat-card">
            <div class="value">{avg_deep:.1f}h</div>
            <div class="label">平均深睡</div>
            <div class="sub">Watch 期间</div>
        </div>
        <div class="stat-card">
            <div class="value">{avg_rem:.1f}h</div>
            <div class="label">平均 REM</div>
            <div class="sub">Watch 期间</div>
        </div>
        <div class="stat-card">
            <div class="value">{len(sleep_nightly_data)}</div>
            <div class="label">记录夜数</div>
            <div class="sub">2021.08 ~ 至今</div>
        </div>
    </div>
    
    <div id="chart_sleep" class="chart-container"></div>
    
    <div class="insight-box">
        <strong>睡眠深度解读 — Apple Watch 期间：</strong><br>
        {sleep_insight_detailed}
    </div>
    
    <div class="insight-box">
        <strong>睡眠趋势回顾 — 小米手环期间：</strong><br>
        {pre_watch_insight}
    </div>
</div>

<!-- ============== 交叉关联分析 ============== -->
<div class="section" id="cross">
    <h2>交叉关联分析</h2>
    <p class="subtitle">打破数据孤岛 — 发现睡眠、心率、运动、周期之间的隐藏关联</p>
    
    <div class="insight-box">
        {sleep_recovery_insight}
    </div>
    
    <div class="insight-box">
        {exercise_recovery_insight}
    </div>
    
    {'<div class="insight-box">' + menstrual_cross_insight + '</div>' if menstrual_cross_insight else ''}
</div>

<!-- ============== 运动/步数模块 ============== -->
<div class="section" id="activity">
    <span class="module-tag tag-p0">P0</span>
    <h2>运动与日常活动</h2>
    <p class="subtitle">步数趋势、运动类型分布、活动能量消耗</p>
    
    <div class="stat-cards">
        <div class="stat-card">
            <div class="value">{total_steps_all/1e6:.1f}M</div>
            <div class="label">总步数</div>
            <div class="sub">{len(step_dates)} 天</div>
        </div>
        <div class="stat-card">
            <div class="value">{total_steps_all/len(step_dates):.0f}</div>
            <div class="label">日均步数</div>
            <div class="sub">{step_target_comment}</div>
        </div>
        <div class="stat-card">
            <div class="value">{total_workouts}</div>
            <div class="label">总锻炼次数</div>
            <div class="sub">{len(workout_type_totals)} 种运动</div>
        </div>
        <div class="stat-card">
            <div class="value">{max(step_count_daily.values()):.0f}</div>
            <div class="label">单日最高步数</div>
            <div class="sub">步</div>
        </div>
    </div>
    
    <div id="chart_steps" class="chart-container"></div>
    
    <div class="insight-box{step_insight_class}">
        <strong>步数趋势洞察：</strong>
        日均步数 {daily_avg_steps:.0f} 步，
        {step_insight}
        可以观察月度波动，是否存在季节性变化或特殊时期的活动量变化。
    </div>
    
    <div id="chart_workout" class="chart-container"></div>
    <div id="chart_energy" class="chart-container"></div>
    
    <div class="insight-box good">
        <strong>运动多样性：</strong>
        共记录了 {len(workout_type_totals)} 种不同类型的运动，
        其中力量训练 {workout_type_totals.get('TraditionalStrengthTraining', 0)} 次为主力，
        2025年新增了游泳、爬楼梯、椭圆机等多种有氧运动，
        运动结构更加均衡。
    </div>
</div>

<!-- ============== 月经模块 ============== -->
<div class="section" id="menstrual">
    <span class="module-tag tag-p1">P1</span>
    <h2>月经周期规律性</h2>
    <p class="subtitle">追踪周期长度变化，观察规律性</p>
    
    <div class="stat-cards">
        <div class="stat-card">
            <div class="value">{avg_cycle_len:.0f}</div>
            <div class="label">平均周期</div>
            <div class="sub">天</div>
        </div>
        <div class="stat-card">
            <div class="value">{min_cycle}</div>
            <div class="label">最短周期</div>
            <div class="sub">天</div>
        </div>
        <div class="stat-card">
            <div class="value">{max_cycle}</div>
            <div class="label">最长周期</div>
            <div class="sub">天</div>
        </div>
        <div class="stat-card">
            <div class="value">{len(cycle_lengths)}</div>
            <div class="label">记录周期数</div>
            <div class="sub">个</div>
        </div>
    </div>
    
    <div id="chart_menstrual" class="chart-container"></div>
    
    <div class="insight-box">
        <strong>周期规律性评估：</strong>
        {cycle_avg_comment}
        {cycle_range_comment}
        {cycle_var_comment}
        图表中灰色区域为正常范围参考。
        注意：周期长度波动受多因素影响（压力、运动强度、旅行时差、体重变化等），单次偏长或偏短不必焦虑，关注连续 3 个周期以上的趋势更有意义。
    </div>
</div>

<!-- ============== 游泳专题 ============== -->
<div class="section" id="swim">
    <span class="module-tag tag-swim">游泳专题</span>
    <h2>游泳深度分析</h2>
    <p class="subtitle">{total_swim} 次泳池游泳 · {swim_date_range} · SWOLF / 泳姿 / 间歇 / 水温</p>
    
    <div class="stat-cards">
        <div class="stat-card"><div class="value">{total_swim}</div><div class="label">总游泳次数</div><div class="sub">{swim_freq}</div></div>
        <div class="stat-card"><div class="value">{total_swim_dist/1000:.1f}km</div><div class="label">总游泳距离</div><div class="sub">{total_swim_dist:.0f} 米</div></div>
        <div class="stat-card"><div class="value">{max_swim_dist:.0f}m</div><div class="label">单次最远</div><div class="sub">米</div></div>
        <div class="stat-card"><div class="value">{best_pace:.2f}</div><div class="label">最佳配速</div><div class="sub">min/100m</div></div>
        <div class="stat-card"><div class="value">{f'{sum(all_valid_swolf)/len(all_valid_swolf):.0f}' if all_valid_swolf else '-'}</div><div class="label">平均 SWOLF</div><div class="sub">{len(all_valid_swolf)} 趟有效</div></div>
        <div class="stat-card"><div class="value">{len([c for c in all_stroke_data if c not in (0, 6)]) if all_stroke_data else '-'}</div><div class="label">掌握泳姿</div><div class="sub">种（不含浮板）</div></div>
    </div>
    
    <h3 style="margin-top:28px;font-size:17px;">训练进步曲线</h3>
    <div id="chart_swim_progress" class="chart-container"></div>
    <div class="insight-box good">
        <strong>进步曲线分析：</strong> 从首次游泳到最近一次，{pace_improve} {dist_improve}
        持续游泳是非常好的有氧运动，对心肺功能和全身肌肉都有很好的锻炼效果。
    </div>
    <div id="chart_swim_bubble" class="chart-container"></div>
    <div class="insight-box">
        <strong>气泡图解读：</strong> 横轴=距离，纵轴=配速（越低越快），气泡大小=时长，颜色=心率。
        理想趋势：气泡向右下方移动（更远更快），颜色变浅（心肺适应更好）。
    </div>
    
    <h3 style="margin-top:28px;font-size:17px;">SWOLF 技术一致性</h3>
    <div id="chart_swolf_trend" class="chart-container"></div>
    <div class="insight-box">{swolf_consistency_insight if swolf_consistency_insight else '<strong>SWOLF 数据不足：</strong>需要更多游泳记录来分析一致性。'}</div>
    
    <h3 style="margin-top:28px;font-size:17px;">泳姿效率对比</h3>
    <div style="display:flex;gap:16px;flex-wrap:wrap;">
        <div style="flex:1;min-width:300px;"><div id="chart_stroke_efficiency" class="chart-container"></div></div>
        <div style="flex:0.7;min-width:260px;"><div id="chart_stroke_dist" class="chart-container"></div></div>
    </div>
    <div class="insight-box">{stroke_efficiency_insight if stroke_efficiency_insight else '<strong>泳姿数据不足：</strong>需要至少2种泳姿的 SWOLF 数据。'}</div>
    {'<div class="insight-box">' + stroke_evolution_insight + '</div>' if stroke_evolution_insight else ''}
    
    <h3 style="margin-top:28px;font-size:17px;">间歇模式分析</h3>
    <div id="chart_interval" class="chart-container"></div>
    <div class="insight-box">{interval_insight if interval_insight else '<strong>间歇数据不足：</strong>需要更多游泳记录。'}</div>
    
    {'<h3 style="margin-top:28px;font-size:17px;">水温与心率</h3><div id="chart_water_temp" class="chart-container"></div><div class="insight-box">' + water_temp_insight + '</div>' if water_temp_insight else ''}

    <h3 style="margin-top:28px;font-size:17px;">全部游泳记录</h3>
    <div style="overflow-x:auto; margin-top:12px;">
        <table class="swim-table">
            <thead>
                <tr>
                    <th>#</th>
                    <th>日期</th>
                    <th>总时长</th>
                    <th>净游泳</th>
                    <th>休息%</th>
                    <th>距离</th>
                    <th>配速</th>
                    <th>SWOLF</th>
                    <th>心率</th>
                    <th>水温</th>
                    <th>主要泳姿</th>
                    <th>能量</th>
                </tr>
            </thead>
            <tbody>"""

for i, s in enumerate(swim_analysis):
    is_best_pace = s['pace_per_100m'] == best_pace and s['pace_per_100m'] > 0
    is_max_dist = s['distance_m'] == max_swim_dist and s['distance_m'] > 0
    dist_class = ' class="best"' if is_max_dist else ''
    pace_class = ' class="best"' if is_best_pace else ''
    pace_str = f"{s['pace_per_100m']:.2f}" if s['pace_per_100m'] > 0 else '-'
    hr_avg_str = f"{s['hr_avg']:.0f}" if s['hr_avg'] > 0 else '-'
    energy_str = f"{s['energy_kcal']:.0f}" if s['energy_kcal'] > 0 else '-'
    net_min_str = f"{s.get('net_swim_min', 0):.0f}" if s.get('net_swim_min', 0) > 0 else '-'
    rest_pct_str = f"{s.get('rest_pct', 0):.0f}%" if s.get('rest_pct', 0) > 0 else '-'
    # SWOLF median from trend data
    swolf_med = '-'
    for t in swim_swolf_trend:
        if t['date'] == s['date']:
            swolf_med = f"{t['median']:.0f}"
            break
    water_t_str = f"{s.get('water_temp', 0):.0f}°C" if s.get('water_temp', 0) > 0 else '-'
    # dominant stroke
    if s.get('stroke_dist', {}):
        dom_code = max(s['stroke_dist'], key=s['stroke_dist'].get)
        dom_name = STROKE_NAMES.get(dom_code, '?')
    else:
        dom_name = '-'
    html_content += f"""
                <tr>
                    <td>{i+1}</td>
                    <td>{s['date']}</td>
                    <td>{s['duration_min']:.0f}m</td>
                    <td>{net_min_str}m</td>
                    <td>{rest_pct_str}</td>
                    <td{dist_class}>{s['distance_m']:.0f}m</td>
                    <td{pace_class}>{pace_str}</td>
                    <td>{swolf_med}</td>
                    <td>{hr_avg_str}</td>
                    <td>{water_t_str}</td>
                    <td>{dom_name}</td>
                    <td>{energy_str}</td>
                </tr>"""

html_content += f"""
            </tbody>
        </table>
    </div>
</div>

<!-- ============== 行动洞察 ============== -->
<div class="section" id="actions">
    <h2>核心行动洞察</h2>
    <p class="subtitle">基于你的个人数据提炼的 Top 改善方向和具体微习惯建议</p>
    
    {''.join(f'<div class="insight-box action-card">{insight}</div>' for insight in action_insights) if action_insights else '<div class="insight-box good">各项指标表现均衡，继续保持当前健康习惯！</div>'}
</div>

<!-- 免责声明 -->
<div style="max-width:1100px;margin:0 auto;padding:0 20px;">
    <div style="background:#F9F9FB;border-radius:12px;padding:14px 20px;font-size:12px;color:#999;line-height:1.6;margin-bottom:8px;">
        提示：本分析基于数据统计规律和个人历史对比，不构成临床医学诊断。
        数据中发现的关联关系不等于因果关系。Apple Watch/手环的测量存在一定误差，
        连续趋势比单日数值更有参考价值。如有身体不适，请咨询专业医生。
    </div>
</div>

<!-- Footer -->
<div class="footer">
    <p>报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')} · 数据来源: Apple Health 导出</p>
    <p>分析周期: 2021.08 ~ 2026.03 · 设备: 小米手环 → Apple Watch</p>
</div>

</div>

<script>
    // 渲染图表
    var charts = {{
        'chart_hr_trend': {fig_hr_trend.to_json()},
        'chart_rhr_hrv': {fig_rhr_hrv.to_json()},
        'chart_vo2': {fig_vo2.to_json()},
        'chart_sleep': {fig_sleep.to_json()},
        'chart_steps': {fig_steps.to_json()},
        'chart_workout': {fig_workout_dist.to_json()},
        'chart_energy': {fig_energy.to_json()},
        'chart_menstrual': {fig_menstrual.to_json()},
        'chart_swim_progress': {fig_swim_progress.to_json()},
        'chart_swim_bubble': {fig_swim_bubble.to_json()},
        'chart_swolf_trend': {fig_swolf_trend.to_json()},
        'chart_stroke_efficiency': {fig_stroke_efficiency.to_json()},
        'chart_stroke_dist': {fig_stroke_dist.to_json()},
        'chart_interval': {fig_interval.to_json()},
        'chart_water_temp': {fig_water_temp.to_json()},
    }};
    
    Object.keys(charts).forEach(function(id) {{
        var chartData = charts[id];
        Plotly.newPlot(id, chartData.data, chartData.layout, {{responsive: true}});
    }});
    
    // 导航滚动
    function scrollToSection(id) {{
        document.getElementById(id).scrollIntoView({{ behavior: 'smooth', block: 'start' }});
        // 更新导航按钮状态
        document.querySelectorAll('.nav-btn').forEach(btn => btn.classList.remove('active'));
        event.target.classList.add('active');
    }}
    
    // 滚动时更新导航按钮
    var sections = ['macro', 'heart', 'sleep', 'cross', 'activity', 'menstrual', 'swim', 'actions'];
    window.addEventListener('scroll', function() {{
        var scrollPos = window.scrollY + 100;
        sections.forEach(function(id, idx) {{
            var el = document.getElementById(id);
            if (el && el.offsetTop <= scrollPos && el.offsetTop + el.offsetHeight > scrollPos) {{
                document.querySelectorAll('.nav-btn').forEach(btn => btn.classList.remove('active'));
                document.querySelectorAll('.nav-btn')[idx].classList.add('active');
            }}
        }});
    }});
</script>

</body>
</html>"""

output_path = '/Users/shiyuan/Documents/Personal/apple_health_export/health_report.html'
with open(output_path, 'w', encoding='utf-8') as f:
    f.write(html_content)

print(f"\n{'='*50}")
print(f"报告已生成: {output_path}")
print(f"{'='*50}")
