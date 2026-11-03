#!/usr/bin/env python3
"""探索数据详情，为分析方案提供决策依据"""

import xml.etree.ElementTree as ET
from collections import defaultdict, Counter
from datetime import datetime
import json

XML_FILE = "导出.xml"

print("=== 正在解析 XML... ===")
tree = ET.parse(XML_FILE)
root = tree.getroot()

# 1. 游泳相关 Workout 数据探索
print("\n" + "="*60)
print("1. 游泳 Workout 数据")
print("="*60)

swim_workouts = []
all_workout_types = Counter()

for elem in root.iter('Workout'):
    wtype = elem.get('workoutActivityType', '')
    all_workout_types[wtype] += 1
    
    if 'Swimming' in wtype or 'swim' in wtype.lower():
        start = elem.get('startDate', '')
        end = elem.get('endDate', '')
        duration = elem.get('duration', '')
        duration_unit = elem.get('durationUnit', '')
        
        # 获取子元素的统计信息
        stats = {}
        for stat in elem.iter('WorkoutStatistics'):
            stat_type = stat.get('type', '').split('/')[-1]
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
        
        swim_workouts.append({
            'type': wtype.split('/')[-1],
            'start': start,
            'end': end,
            'duration_min': float(duration) if duration else 0,
            'stats': stats,
            'metadata': metadata
        })

print(f"游泳记录总数: {len(swim_workouts)}")

if swim_workouts:
    # 按类型分组
    swim_types = Counter(w['type'] for w in swim_workouts)
    print(f"游泳类型分布: {dict(swim_types)}")
    
    # 时间范围
    dates = [w['start'][:10] for w in swim_workouts]
    dates.sort()
    print(f"时间范围: {dates[0]} ~ {dates[-1]}")
    
    # 按年月分布
    ym_dist = Counter(d[:7] for d in dates)
    print(f"\n按月分布:")
    for ym in sorted(ym_dist.keys()):
        print(f"  {ym}: {ym_dist[ym]}次")
    
    # 查看第一条游泳记录的详细信息
    print(f"\n最近一条游泳记录详情:")
    last = swim_workouts[-1]
    print(f"  类型: {last['type']}")
    print(f"  时间: {last['start']} ~ {last['end']}")
    print(f"  时长: {last['duration_min']:.1f} 分钟")
    print(f"  统计指标:")
    for k, v in last['stats'].items():
        print(f"    {k}: sum={v['sum']}, avg={v['avg']}, unit={v['unit']}")
    print(f"  元数据:")
    for k, v in last['metadata'].items():
        print(f"    {k}: {v}")

# 2. 所有运动类型概览
print("\n" + "="*60)
print("2. 所有运动类型 (有记录的)")
print("="*60)
for wtype, count in all_workout_types.most_common():
    short = wtype.split('/')[-1]
    print(f"  {short}: {count}次")

# 3. P0/P1 关键指标的数据时间范围和量级
print("\n" + "="*60)
print("3. 关键指标数据探索 (2021.08起)")
print("="*60)

key_types = {
    # P0: 心率综合
    'HKQuantityTypeIdentifierHeartRate': '心率',
    'HKQuantityTypeIdentifierRestingHeartRate': '静息心率',
    'HKQuantityTypeIdentifierHeartRateVariabilitySDNN': 'HRV',
    'HKQuantityTypeIdentifierHeartRateRecoveryOneMinute': '心率恢复',
    'HKQuantityTypeIdentifierVO2Max': 'VO2Max',
    
    # P0: 睡眠
    'HKCategoryTypeIdentifierSleepAnalysis': '睡眠分析',
    'HKQuantityTypeIdentifierRespiratoryRate': '呼吸率',
    'HKQuantityTypeIdentifierAppleSleepingWristTemperature': '腕温',
    'HKQuantityTypeIdentifierOxygenSaturation': '血氧',
    
    # P0: 运动
    'HKQuantityTypeIdentifierActiveEnergyBurned': '活动能量',
    'HKQuantityTypeIdentifierBasalEnergyBurned': '基础能量',
    'HKQuantityTypeIdentifierAppleExerciseTime': '锻炼时间',
    'HKQuantityTypeIdentifierAppleStandTime': '站立时间',
    'HKQuantityTypeIdentifierStepCount': '步数',
    'HKQuantityTypeIdentifierDistanceWalkingRunning': '步行跑步距离',
    'HKQuantityTypeIdentifierDistanceSwimming': '游泳距离',
    'HKQuantityTypeIdentifierSwimmingStrokeCount': '游泳划水次数',
    
    # P1: 长期趋势
    'HKQuantityTypeIdentifierFlightsClimbed': '爬楼',
    'HKQuantityTypeIdentifierBodyMass': '体重',
    'HKQuantityTypeIdentifierBodyMassIndex': 'BMI',
    'HKQuantityTypeIdentifierBodyFatPercentage': '体脂率',
    'HKQuantityTypeIdentifierLeanBodyMass': '去脂体重',
    
    # P1: 月经
    'HKCategoryTypeIdentifierMenstrualFlow': '月经',
    'HKCategoryTypeIdentifierIntermenstrualBleeding': '经间期出血',
    'HKCategoryTypeIdentifierPregnancyTestResult': '验孕结果',
    'HKCategoryTypeIdentifierLactation': '哺乳',
}

# 统计每个关键指标
for type_id, label in key_types.items():
    records = []
    for elem in root.iter('Record'):
        if elem.get('type') == type_id:
            start = elem.get('startDate', '')
            if start >= '2021-08':
                value = elem.get('value', '')
                records.append({'date': start[:10], 'value': value})
    
    if records:
        dates = [r['date'] for r in records]
        dates.sort()
        
        # 按年统计
        year_counts = Counter(d[:4] for d in dates)
        year_str = ", ".join(f"{y}:{c}" for y, c in sorted(year_counts.items()))
        
        # 数值示例
        sample_vals = [r['value'] for r in records[-5:] if r['value']]
        
        print(f"\n  【{label}】({type_id.split('Identifier')[-1]})")
        print(f"    总记录: {len(records)} | 范围: {dates[0]} ~ {dates[-1]}")
        print(f"    按年: {year_str}")
        if sample_vals:
            print(f"    最近5个值: {sample_vals}")
    else:
        print(f"\n  【{label}】- 无数据 (2021.08起)")

# 4. 睡眠数据特殊处理 - 查看value类型
print("\n" + "="*60)
print("4. 睡眠数据值分布")
print("="*60)

sleep_values = Counter()
sleep_sources = Counter()
for elem in root.iter('Record'):
    if elem.get('type') == 'HKCategoryTypeIdentifierSleepAnalysis':
        val = elem.get('value', '')
        sleep_values[val] += 1
        src = elem.get('sourceName', '')
        sleep_sources[src] += 1

print("睡眠值类型:")
for v, c in sleep_values.most_common():
    print(f"  {v}: {c}")
print("数据来源:")
for s, c in sleep_sources.most_common():
    print(f"  {s}: {c}")

# 5. 体重/身体成分数据来源
print("\n" + "="*60)
print("5. 体重/身体成分数据来源")
print("="*60)
for type_id in ['HKQuantityTypeIdentifierBodyMass', 'HKQuantityTypeIdentifierBodyFatPercentage']:
    sources = Counter()
    for elem in root.iter('Record'):
        if elem.get('type') == type_id:
            src = elem.get('sourceName', '')
            sources[src] += 1
    label = type_id.split('Identifier')[-1]
    print(f"  {label}: {dict(sources)}")

# 6. Workout Route (GPX) 文件信息
print("\n" + "="*60)
print("6. GPX 运动路线文件")
print("="*60)
import os
gpx_dir = "workout-routes"
if os.path.isdir(gpx_dir):
    gpx_files = [f for f in os.listdir(gpx_dir) if f.endswith('.gpx')]
    print(f"GPX文件数: {len(gpx_files)}")
    # 尝试从文件名推断日期
    gpx_files.sort()
    if gpx_files:
        print(f"文件名示例: {gpx_files[0]}, ..., {gpx_files[-1]}")

print("\n=== 探索完成 ===")
