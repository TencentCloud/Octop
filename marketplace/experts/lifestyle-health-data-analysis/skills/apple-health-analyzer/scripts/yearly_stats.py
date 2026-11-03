#!/usr/bin/env python3
"""
按年份统计 Apple Health 各数据类型的记录数分布
使用流式 XML 解析以节省内存
"""

import xml.etree.ElementTree as ET
from collections import defaultdict
import json
import time

def parse_health_data(xml_path):
    """流式解析 XML，按年份和数据类型统计记录数"""
    # {type: {year: count}}
    stats = defaultdict(lambda: defaultdict(int))
    # 总记录数
    total_by_type = defaultdict(int)
    # 记录每种类型的最早和最晚日期
    date_range = defaultdict(lambda: {"min": "9999", "max": "0000"})
    
    count = 0
    start_time = time.time()
    
    print("开始解析 XML 文件...")
    
    # 使用 iterparse 流式解析
    context = ET.iterparse(xml_path, events=('end',))
    
    for event, elem in context:
        if elem.tag == 'Record':
            record_type = elem.get('type', 'Unknown')
            # 去掉 HKQuantityTypeIdentifier / HKCategoryTypeIdentifier 前缀
            for prefix in ['HKQuantityTypeIdentifier', 'HKCategoryTypeIdentifier', 'HKDataType']:
                if record_type.startswith(prefix):
                    record_type = record_type[len(prefix):]
                    break
            
            start_date = elem.get('startDate', '')
            if start_date:
                year = start_date[:4]
                stats[record_type][year] += 1
                total_by_type[record_type] += 1
                
                # 更新日期范围
                date_str = start_date[:10]
                if date_str < date_range[record_type]["min"]:
                    date_range[record_type]["min"] = date_str
                if date_str > date_range[record_type]["max"]:
                    date_range[record_type]["max"] = date_str
            
            count += 1
            if count % 500000 == 0:
                elapsed = time.time() - start_time
                print(f"  已处理 {count:,} 条记录... ({elapsed:.1f}秒)")
            
            # 清除已处理的元素以节省内存
            elem.clear()
        
        elif elem.tag == 'Workout':
            workout_type = elem.get('workoutActivityType', 'Unknown')
            if workout_type.startswith('HKWorkoutActivityType'):
                workout_type = 'Workout_' + workout_type[len('HKWorkoutActivityType'):]
            
            start_date = elem.get('startDate', '')
            if start_date:
                year = start_date[:4]
                stats[workout_type][year] += 1
                total_by_type[workout_type] += 1
                
                date_str = start_date[:10]
                if date_str < date_range[workout_type]["min"]:
                    date_range[workout_type]["min"] = date_str
                if date_str > date_range[workout_type]["max"]:
                    date_range[workout_type]["max"] = date_str
            
            count += 1
            elem.clear()
    
    elapsed = time.time() - start_time
    print(f"\n解析完成！共处理 {count:,} 条记录，耗时 {elapsed:.1f} 秒")
    
    return stats, total_by_type, date_range

def print_results(stats, total_by_type, date_range):
    """打印统计结果"""
    
    # 获取所有年份并排序
    all_years = set()
    for type_years in stats.values():
        all_years.update(type_years.keys())
    all_years = sorted(all_years)
    
    print(f"\n{'='*120}")
    print(f"数据时间跨度: {min(all_years)} ~ {max(all_years)}")
    print(f"数据类型总数: {len(stats)}")
    print(f"{'='*120}")
    
    # 按总记录数降序排列
    sorted_types = sorted(total_by_type.items(), key=lambda x: x[1], reverse=True)
    
    # === 1. 总览表 ===
    print(f"\n{'='*120}")
    print("【总览】各数据类型的总记录数和时间范围")
    print(f"{'='*120}")
    print(f"{'数据类型':<45} {'总记录数':>12} {'起始日期':>12} {'结束日期':>12} {'数据来源推断':<20}")
    print(f"{'-'*120}")
    
    # 推断数据来源
    iphone_types = {'StepCount', 'DistanceWalkingRunning', 'FlightsClimbed', 
                    'EnvironmentalAudioExposure', 'HeadphoneAudioExposure',
                    'WalkingSpeed', 'WalkingStepLength', 'WalkingDoubleSupportPercentage',
                    'WalkingAsymmetryPercentage', 'AppleWalkingSteadiness',
                    'SixMinuteWalkTestDistance', 'StairAscentSpeed', 'StairDescentSpeed'}
    
    watch_types = {'HeartRate', 'HeartRateVariabilitySDNN', 'RestingHeartRate',
                   'WalkingHeartRateAverage', 'HeartRateRecoveryOneMinute',
                   'AppleExerciseTime', 'BasalEnergyBurned', 'ActiveEnergyBurned',
                   'AppleStandTime', 'AppleStandHour', 'OxygenSaturation',
                   'RespiratoryRate', 'AppleSleepingWristTemperature',
                   'SleepAnalysis', 'VO2Max', 'RunningPower', 'RunningSpeed',
                   'RunningStrideLength', 'RunningVerticalOscillation',
                   'RunningGroundContactTime', 'PhysicalEffort',
                   'AppleSleepingBreathingDisturbances', 'TimeInDaylight',
                   'UnderwaterDepth', 'WaterTemperature'}
    
    manual_types = {'MenstrualFlow', 'CervicalMucusQuality', 'OvulationTestResult',
                    'SexualActivity', 'BodyMass', 'Height', 'BodyMassIndex',
                    'BodyFatPercentage', 'LeanBodyMass', 'BloodPressureSystolic',
                    'BloodPressureDiastolic', 'BloodGlucose', 'DietaryWater'}
    
    for type_name, total in sorted_types:
        dr = date_range[type_name]
        if type_name in watch_types:
            source = "⌚ Apple Watch"
        elif type_name in iphone_types:
            source = "📱 iPhone"
        elif type_name in manual_types:
            source = "✏️ 手动/第三方"
        elif type_name.startswith('Workout_'):
            source = "⌚ Watch/📱 手动"
        else:
            source = "❓ 待确认"
        
        print(f"{type_name:<45} {total:>12,} {dr['min']:>12} {dr['max']:>12} {source:<20}")
    
    # === 2. 年份分布详细表 ===
    print(f"\n\n{'='*120}")
    print("【年份分布】各数据类型按年份的记录数")
    print(f"{'='*120}")
    
    # 表头
    header = f"{'数据类型':<40}"
    for year in all_years:
        header += f" {year:>8}"
    header += f" {'总计':>10}"
    print(header)
    print(f"{'-'*120}")
    
    for type_name, total in sorted_types:
        row = f"{type_name:<40}"
        for year in all_years:
            count = stats[type_name].get(year, 0)
            if count == 0:
                row += f" {'—':>8}"
            elif count >= 10000:
                row += f" {count/1000:.0f}K".rjust(9)
            else:
                row += f" {count:>8,}"
            
        row += f" {total:>10,}"
        print(row)
    
    # === 3. 按年份汇总 ===
    print(f"\n\n{'='*120}")
    print("【年份汇总】每年的总记录数和活跃数据类型数")
    print(f"{'='*120}")
    
    yearly_totals = defaultdict(int)
    yearly_type_count = defaultdict(int)
    for type_name in stats:
        for year in stats[type_name]:
            yearly_totals[year] += stats[type_name][year]
            yearly_type_count[year] += 1
    
    print(f"{'年份':<10} {'总记录数':>15} {'活跃类型数':>12} {'数据密度评估':<20}")
    print(f"{'-'*60}")
    for year in all_years:
        total = yearly_totals[year]
        type_count = yearly_type_count[year]
        if type_count >= 30:
            density = "🟢 非常丰富（Watch+）"
        elif type_count >= 15:
            density = "🟡 中等（iPhone+）"
        elif type_count >= 5:
            density = "🟠 基础（iPhone）"
        else:
            density = "🔴 稀疏"
        print(f"{year:<10} {total:>15,} {type_count:>12} {density:<20}")
    
    # === 4. Watch 数据起始时间推断 ===
    print(f"\n\n{'='*120}")
    print("【Apple Watch 佩戴时间推断】")
    print(f"{'='*120}")
    
    watch_indicators = ['HeartRate', 'RestingHeartRate', 'HeartRateVariabilitySDNN', 
                        'WalkingHeartRateAverage', 'SleepAnalysis']
    
    for indicator in watch_indicators:
        if indicator in date_range:
            dr = date_range[indicator]
            print(f"  {indicator}: {dr['min']} ~ {dr['max']}")
    
    # 保存为 JSON 供后续可视化使用
    output = {
        "all_years": all_years,
        "stats": {k: dict(v) for k, v in stats.items()},
        "total_by_type": dict(total_by_type),
        "date_range": {k: dict(v) for k, v in date_range.items()},
        "yearly_totals": dict(yearly_totals),
        "yearly_type_count": dict(yearly_type_count)
    }
    
    with open('/Users/shiyuan/Documents/Personal/apple_health_export/yearly_stats.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n统计数据已保存到 yearly_stats.json")

if __name__ == '__main__':
    xml_path = '/Users/shiyuan/Documents/Personal/apple_health_export/导出.xml'
    stats, total_by_type, date_range = parse_health_data(xml_path)
    print_results(stats, total_by_type, date_range)
