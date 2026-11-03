#!/usr/bin/env python3
"""
Apple Health XML Parser — Streaming, Memory-Efficient, Token-Friendly

Usage:
  # Profile only (fast scan, outputs JSON summary):
  python3 parse_health_xml.py --profile-only --input export.xml

  # Full parse (extract to CSV):
  python3 parse_health_xml.py --input export.xml --output-dir ./health_data/
  
  # Parse specific modules only:
  python3 parse_health_xml.py --input export.xml --output-dir ./health_data/ \
    --modules activity,heartrate,sleep

  # Parse with date filter:
  python3 parse_health_xml.py --input export.xml --output-dir ./health_data/ \
    --start-date 2021-01-01
"""

import xml.etree.ElementTree as ET
import csv
import json
import os
import sys
import argparse
import unicodedata
import traceback
from collections import defaultdict, Counter
from datetime import datetime, timedelta
import math
import time

__version__ = '2.1.0'


def normalize_str(s):
    """
    Normalize a string for robust matching:
    1. NFKC normalization — collapses Unicode variants (e.g. \xa0 → space,
       fullwidth chars → ASCII, ligatures → components)
    2. Strip leading/trailing whitespace
    3. Collapse internal runs of whitespace to a single space
    
    This handles the common Apple Health export issue where sourceName
    fields contain non-breaking spaces (\xa0), fullwidth characters,
    or other Unicode whitespace variants that break exact string matching.
    """
    if not s:
        return s
    s = unicodedata.normalize('NFKC', s)
    return ' '.join(s.split())


def classify_source(source_name):
    """Classify a data source by keyword pattern matching, never exact strings.
    
    Returns one of: 'apple_watch', 'iphone', 'pokemon_sleep', 'sleep_tracker_app',
    'third_party_wearable', 'other'.
    """
    normalized = normalize_str(source_name).lower() if source_name else ''
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


# Source priority for deduplication: lower number = higher priority
SOURCE_PRIORITY = {
    'apple_watch': 1,
    'third_party_wearable': 2,
    'iphone': 3,
    'sleep_tracker_app': 4,
    'pokemon_sleep': 5,
    'other': 6,
}


# ============================================================
# Constants
# ============================================================

# Map HK identifiers to short names
QUANTITY_TYPES = {
    # Heart & Cardiovascular
    'HKQuantityTypeIdentifierHeartRate': 'HeartRate',
    'HKQuantityTypeIdentifierRestingHeartRate': 'RestingHeartRate',
    'HKQuantityTypeIdentifierHeartRateVariabilitySDNN': 'HRV',
    'HKQuantityTypeIdentifierHeartRateRecoveryOneMinute': 'HeartRateRecovery',
    'HKQuantityTypeIdentifierWalkingHeartRateAverage': 'WalkingHeartRateAvg',
    'HKQuantityTypeIdentifierVO2Max': 'VO2Max',
    'HKQuantityTypeIdentifierOxygenSaturation': 'OxygenSaturation',
    'HKQuantityTypeIdentifierBloodGlucose': 'BloodGlucose',
    # Respiratory
    'HKQuantityTypeIdentifierRespiratoryRate': 'RespiratoryRate',
    # Activity & Energy
    'HKQuantityTypeIdentifierStepCount': 'StepCount',
    'HKQuantityTypeIdentifierDistanceWalkingRunning': 'DistanceWalkRun',
    'HKQuantityTypeIdentifierFlightsClimbed': 'FlightsClimbed',
    'HKQuantityTypeIdentifierActiveEnergyBurned': 'ActiveEnergy',
    'HKQuantityTypeIdentifierBasalEnergyBurned': 'BasalEnergy',
    'HKQuantityTypeIdentifierAppleExerciseTime': 'ExerciseTime',
    'HKQuantityTypeIdentifierAppleStandTime': 'StandTime',
    'HKQuantityTypeIdentifierPhysicalEffort': 'PhysicalEffort',
    # Swimming
    'HKQuantityTypeIdentifierDistanceSwimming': 'SwimDistance',
    'HKQuantityTypeIdentifierSwimmingStrokeCount': 'SwimStrokes',
    'HKQuantityTypeIdentifierUnderwaterDepth': 'DiveDepth',
    'HKQuantityTypeIdentifierWaterTemperature': 'WaterTemp',
    # Body
    'HKQuantityTypeIdentifierBodyMass': 'BodyMass',
    'HKQuantityTypeIdentifierBodyMassIndex': 'BMI',
    'HKQuantityTypeIdentifierBodyFatPercentage': 'BodyFat',
    'HKQuantityTypeIdentifierHeight': 'Height',
    'HKQuantityTypeIdentifierLeanBodyMass': 'LeanBodyMass',
    # Mobility
    'HKQuantityTypeIdentifierWalkingSpeed': 'WalkingSpeed',
    'HKQuantityTypeIdentifierWalkingStepLength': 'StepLength',
    'HKQuantityTypeIdentifierWalkingDoubleSupportPercentage': 'DoubleSupport',
    'HKQuantityTypeIdentifierWalkingAsymmetryPercentage': 'WalkingAsymmetry',
    'HKQuantityTypeIdentifierStairAscentSpeed': 'StairAscent',
    'HKQuantityTypeIdentifierStairDescentSpeed': 'StairDescent',
    'HKQuantityTypeIdentifierSixMinuteWalkTestDistance': 'SixMinWalk',
    'HKQuantityTypeIdentifierAppleWalkingSteadiness': 'WalkingSteadiness',
    # Audio
    'HKQuantityTypeIdentifierHeadphoneAudioExposure': 'HeadphoneAudio',
    'HKQuantityTypeIdentifierEnvironmentalAudioExposure': 'EnvironmentAudio',
    'HKQuantityTypeIdentifierEnvironmentalSoundReduction': 'SoundReduction',
    # Sleep temperature
    'HKQuantityTypeIdentifierAppleSleepingWristTemperature': 'WristTemp',
    'HKQuantityTypeIdentifierAppleSleepingBreathingDisturbances': 'BreathingDisturbances',
    # Daylight
    'HKQuantityTypeIdentifierTimeInDaylight': 'TimeInDaylight',
}

CATEGORY_TYPES = {
    'HKCategoryTypeIdentifierSleepAnalysis': 'SleepAnalysis',
    'HKCategoryTypeIdentifierMenstrualFlow': 'MenstrualFlow',
    'HKCategoryTypeIdentifierIntermenstrualBleeding': 'IntermenstrualBleeding',
    'HKCategoryTypeIdentifierPregnancy': 'Pregnancy',
    'HKCategoryTypeIdentifierPregnancyTestResult': 'PregnancyTest',
    'HKCategoryTypeIdentifierProgesteroneTestResult': 'ProgesteroneTest',
    'HKCategoryTypeIdentifierLactation': 'Lactation',
    'HKCategoryTypeIdentifierAppleStandHour': 'StandHour',
    'HKCategoryTypeIdentifierMindfulSession': 'MindfulSession',
    'HKCategoryTypeIdentifierAudioExposureEvent': 'AudioExposureEvent',
    'HKCategoryTypeIdentifierSleepDurationGoal': 'SleepGoal',
}

# Module → which types it needs
MODULE_TYPES = {
    'activity': ['StepCount', 'DistanceWalkRun', 'FlightsClimbed', 'ActiveEnergy',
                 'BasalEnergy', 'ExerciseTime', 'StandTime', 'StandHour', 'PhysicalEffort',
                 'TimeInDaylight'],
    'heartrate': ['HeartRate', 'RestingHeartRate', 'HRV', 'HeartRateRecovery',
                  'WalkingHeartRateAvg', 'VO2Max'],
    'sleep': ['SleepAnalysis', 'WristTemp', 'BreathingDisturbances', 'SleepGoal',
              'RespiratoryRate', 'OxygenSaturation'],
    'menstrual': ['MenstrualFlow', 'IntermenstrualBleeding', 'Pregnancy', 'PregnancyTest',
                  'ProgesteroneTest', 'Lactation'],
    'workout': [],  # Handled separately via <Workout> elements
    'body': ['BodyMass', 'BMI', 'BodyFat', 'Height', 'LeanBodyMass'],
    'mobility': ['WalkingSpeed', 'StepLength', 'DoubleSupport', 'WalkingAsymmetry',
                 'StairAscent', 'StairDescent', 'SixMinWalk', 'WalkingSteadiness'],
    'audio': ['HeadphoneAudio', 'EnvironmentAudio', 'SoundReduction', 'AudioExposureEvent'],
    'swimming': ['SwimDistance', 'SwimStrokes', 'DiveDepth', 'WaterTemp'],
}

# Types that need daily aggregation (high-frequency)
AGGREGATE_DAILY = {
    'HeartRate', 'StepCount', 'DistanceWalkRun', 'ActiveEnergy', 'BasalEnergy',
    'ExerciseTime', 'StandTime', 'FlightsClimbed', 'HeadphoneAudio',
    'EnvironmentAudio', 'PhysicalEffort', 'TimeInDaylight',
}

# Types to keep individual records
KEEP_INDIVIDUAL = {
    'RestingHeartRate', 'HRV', 'HeartRateRecovery', 'WalkingHeartRateAvg', 'VO2Max',
    'OxygenSaturation', 'RespiratoryRate', 'WristTemp', 'BreathingDisturbances',
    'BodyMass', 'BMI', 'BodyFat', 'Height', 'LeanBodyMass',
    'WalkingSpeed', 'StepLength', 'DoubleSupport', 'WalkingAsymmetry',
    'StairAscent', 'StairDescent', 'SixMinWalk', 'WalkingSteadiness',
    'BloodGlucose', 'SwimDistance', 'SwimStrokes', 'DiveDepth', 'WaterTemp',
    'SoundReduction',
}

# Category types to keep individual
KEEP_CATEGORY = {
    'SleepAnalysis', 'MenstrualFlow', 'IntermenstrualBleeding',
    'Pregnancy', 'PregnancyTest', 'ProgesteroneTest', 'Lactation',
    'MindfulSession', 'SleepGoal', 'AudioExposureEvent',
}


def parse_date(date_str):
    """Parse Apple Health date format: '2025-03-30 08:15:23 +0800'"""
    if not date_str:
        return None
    try:
        # Try standard format
        return datetime.strptime(date_str[:19], '%Y-%m-%d %H:%M:%S')
    except (ValueError, IndexError):
        try:
            return datetime.strptime(date_str[:10], '%Y-%m-%d')
        except (ValueError, IndexError):
            return None


def parse_date_only(date_str):
    """Extract just the date portion"""
    if not date_str:
        return None
    return date_str[:10]


# ============================================================
# Profile Mode — Quick scan
# ============================================================

def profile_xml(input_path):
    """
    Quick scan of the XML file to produce a compact profile.
    Uses iterparse to avoid loading the full tree.
    """
    print(f"Profiling {input_path}...")
    start_time = time.time()
    
    file_size_mb = os.path.getsize(input_path) / (1024 * 1024)
    
    profile = {
        'file_path': input_path,
        'file_size_mb': round(file_size_mb, 1),
        'user_info': {},
        'devices': Counter(),
        'record_types': defaultdict(lambda: {'count': 0, 'min_date': None, 'max_date': None}),
        'workout_types': Counter(),
        'activity_summary_count': 0,
        'activity_summary_range': [None, None],
        'total_records': 0,
        'total_workouts': 0,
    }
    
    context = ET.iterparse(input_path, events=('end',))
    
    for event, elem in context:
        tag = elem.tag
        
        if tag == 'Me':
            # User demographics
            profile['user_info'] = {
                'date_of_birth': elem.get('HKCharacteristicTypeIdentifierDateOfBirth', ''),
                'sex': elem.get('HKCharacteristicTypeIdentifierBiologicalSex', '').replace('HKBiologicalSex', ''),
                'blood_type': elem.get('HKCharacteristicTypeIdentifierBloodType', '').replace('HKBloodType', ''),
                'skin_type': elem.get('HKCharacteristicTypeIdentifierFitzpatrickSkinType', ''),
            }
        
        elif tag == 'Record':
            profile['total_records'] += 1
            rtype = elem.get('type', '')
            short_name = QUANTITY_TYPES.get(rtype) or CATEGORY_TYPES.get(rtype) or rtype.split('Identifier')[-1]
            date = parse_date_only(elem.get('startDate', ''))
            source = elem.get('sourceName', '')
            
            info = profile['record_types'][short_name]
            info['count'] += 1
            if date:
                if info['min_date'] is None or date < info['min_date']:
                    info['min_date'] = date
                if info['max_date'] is None or date > info['max_date']:
                    info['max_date'] = date
            
            if source:
                # Normalize sourceName to handle Unicode whitespace variants
                source = normalize_str(source)
                profile['devices'][source] += 1
        
        elif tag == 'Workout':
            profile['total_workouts'] += 1
            wtype = elem.get('workoutActivityType', '').split('/')[-1]
            profile['workout_types'][wtype] += 1
        
        elif tag == 'ActivitySummary':
            profile['activity_summary_count'] += 1
            date = elem.get('dateComponents', '')
            if date:
                if profile['activity_summary_range'][0] is None or date < profile['activity_summary_range'][0]:
                    profile['activity_summary_range'][0] = date
                if profile['activity_summary_range'][1] is None or date > profile['activity_summary_range'][1]:
                    profile['activity_summary_range'][1] = date
        
        # Free memory
        elem.clear()
    
    elapsed = time.time() - start_time
    
    # Calculate age using the latest date in the data as reference,
    # consistent with Rule 3 (data-relative time, not datetime.now()).
    # Falls back to datetime.now() only if no data dates are available.
    dob = profile['user_info'].get('date_of_birth', '')
    if dob:
        try:
            birth = datetime.strptime(dob, '%Y-%m-%d')
            # Find the latest date across all record types
            all_max_dates = [
                v['max_date'] for v in profile['record_types'].values()
                if v['max_date']
            ]
            if all_max_dates:
                reference_date = datetime.strptime(max(all_max_dates), '%Y-%m-%d')
            else:
                reference_date = datetime.now()
            age = (reference_date - birth).days // 365
            profile['user_info']['estimated_age'] = age
        except ValueError:
            pass
    
    # Detect device tiers
    device_names = set(profile['devices'].keys())
    has_watch = any('Apple Watch' in d or 'Watch' in d for d in device_names)
    has_advanced_watch = any(
        any(kw in d for kw in ['Series 7', 'Series 8', 'Series 9', 'Series 10', 'Ultra'])
        for d in device_names
    )
    
    # Check for advanced metrics as proxy for advanced watch
    advanced_metrics = {'WristTemp', 'BreathingDisturbances', 'HRV', 'OxygenSaturation'}
    has_advanced_data = bool(advanced_metrics & set(profile['record_types'].keys()))
    
    if has_advanced_watch or has_advanced_data:
        tier = 3
        tier_desc = 'iPhone + Advanced Watch (full metrics)'
    elif has_watch:
        tier = 2
        tier_desc = 'iPhone + Watch (basic metrics)'
    else:
        tier = 1
        tier_desc = 'iPhone Only'
    
    profile['device_tier'] = tier
    profile['device_tier_description'] = tier_desc
    
    # Determine available modules
    available_modules = []
    rt_keys = set(profile['record_types'].keys())
    for module, required_types in MODULE_TYPES.items():
        if module == 'workout':
            if profile['total_workouts'] > 0:
                available_modules.append(module)
        elif any(t in rt_keys for t in required_types):
            available_modules.append(module)
    profile['available_modules'] = available_modules
    
    # Convert to serializable format
    output = {
        'file_info': {
            'path': profile['file_path'],
            'size_mb': profile['file_size_mb'],
            'profile_time_seconds': round(elapsed, 1),
        },
        'user_info': profile['user_info'],
        'device_tier': {
            'tier': tier,
            'description': tier_desc,
        },
        'devices': dict(profile['devices'].most_common(20)),
        'total_records': profile['total_records'],
        'total_workouts': profile['total_workouts'],
        'activity_summary_count': profile['activity_summary_count'],
        'activity_summary_range': profile['activity_summary_range'],
        'record_types': {
            k: {'count': v['count'], 'min_date': v['min_date'], 'max_date': v['max_date']}
            for k, v in sorted(profile['record_types'].items(), key=lambda x: -x[1]['count'])
        },
        'workout_types': dict(profile['workout_types'].most_common()),
        'available_modules': available_modules,
        'data_years': sorted(set(
            v['min_date'][:4] for v in profile['record_types'].values() if v['min_date']
        ) | set(
            v['max_date'][:4] for v in profile['record_types'].values() if v['max_date']
        )),
    }
    
    return output


# ============================================================
# Full Parse Mode — Extract to CSV
# ============================================================

class HealthDataExtractor:
    """Streaming XML parser that extracts health data to CSV files."""
    
    def __init__(self, input_path, output_dir, modules=None, start_date=None):
        self.input_path = input_path
        self.output_dir = output_dir
        self.modules = modules or list(MODULE_TYPES.keys())
        self.start_date = start_date or '2000-01-01'
        
        # Determine which types to extract based on selected modules
        self.target_types = set()
        for mod in self.modules:
            self.target_types.update(MODULE_TYPES.get(mod, []))
        
        # Aggregation buffers for high-frequency data
        # {type_name: {date: {'values': [], 'sources': set(), 'source_values': defaultdict(float), 'source_counts': defaultdict(int)}}}
        self.daily_agg = defaultdict(lambda: defaultdict(lambda: {
            'values': [], 'sources': set(),
            'source_values': defaultdict(float),
            'source_counts': defaultdict(int),
        }))
        
        # Individual records buffer
        # {type_name: [row_dicts]}
        self.individual = defaultdict(list)
        
        # Sleep records (special handling)
        self.sleep_records = []
        
        # Category records
        self.category_records = defaultdict(list)
        
        # Workout records
        self.workouts = []
        
        # Activity summaries
        self.activity_summaries = []
        
        # Stats
        self.processed = 0
        self.skipped = 0
    
    def extract(self):
        """Run the streaming extraction."""
        os.makedirs(self.output_dir, exist_ok=True)
        
        print(f"Parsing {self.input_path}...")
        print(f"Modules: {', '.join(self.modules)}")
        print(f"Start date filter: {self.start_date}")
        start_time = time.time()
        
        context = ET.iterparse(self.input_path, events=('end',))
        
        for event, elem in context:
            tag = elem.tag
            
            if tag == 'Record':
                self._handle_record(elem)
            elif tag == 'Workout' and 'workout' in self.modules:
                self._handle_workout(elem)
            elif tag == 'ActivitySummary' and 'activity' in self.modules:
                self._handle_activity_summary(elem)
            
            elem.clear()
            
            self.processed += 1
            if self.processed % 500000 == 0:
                print(f"  Processed {self.processed:,} elements...")
        
        elapsed = time.time() - start_time
        print(f"Parsing complete: {self.processed:,} elements in {elapsed:.1f}s")
        
        # Write outputs
        self._write_outputs()
    
    def _handle_record(self, elem):
        """Process a single Record element."""
        rtype = elem.get('type', '')
        short_name = QUANTITY_TYPES.get(rtype) or CATEGORY_TYPES.get(rtype)
        
        if not short_name or short_name not in self.target_types:
            self.skipped += 1
            return
        
        start_str = elem.get('startDate', '')
        date = parse_date_only(start_str)
        if not date or date < self.start_date:
            self.skipped += 1
            return
        
        source = normalize_str(elem.get('sourceName', ''))
        value = elem.get('value', '')
        end_str = elem.get('endDate', '')
        unit = elem.get('unit', '')
        
        # Route to appropriate handler
        if short_name == 'SleepAnalysis':
            self.sleep_records.append({
                'startDate': start_str,
                'endDate': end_str,
                'value': value.split('/')[-1] if '/' in value else value,
                'sourceName': source,
            })
        elif short_name in KEEP_CATEGORY:
            self.category_records[short_name].append({
                'date': date,
                'startDate': start_str,
                'endDate': end_str,
                'value': value.split('/')[-1] if '/' in value else value,
                'sourceName': source,
            })
        elif short_name in AGGREGATE_DAILY:
            try:
                fval = float(value)
                day_entry = self.daily_agg[short_name][date]
                day_entry['values'].append(fval)
                day_entry['sources'].add(source)
                # Track per-source sums for deduplication of additive metrics
                day_entry['source_values'][source] += fval
                day_entry['source_counts'][source] += 1
            except (ValueError, TypeError):
                pass
        elif short_name in KEEP_INDIVIDUAL:
            try:
                fval = float(value)
                self.individual[short_name].append({
                    'date': date,
                    'startDate': start_str,
                    'value': fval,
                    'unit': unit,
                    'sourceName': source,
                })
            except (ValueError, TypeError):
                pass
    
    def _handle_workout(self, elem):
        """Process a Workout element with nested statistics and metadata."""
        start_str = elem.get('startDate', '')
        date = parse_date_only(start_str)
        if not date or date < self.start_date:
            return
        
        workout = {
            'date': date,
            'startDate': start_str,
            'endDate': elem.get('endDate', ''),
            'type': elem.get('workoutActivityType', '').split('/')[-1],
            'duration_min': None,
            'totalEnergyBurned_kcal': None,
            'totalDistance_m': None,
            'sourceName': normalize_str(elem.get('sourceName', '')),
        }
        
        # Parse duration
        try:
            workout['duration_min'] = round(float(elem.get('duration', '0')), 1)
        except (ValueError, TypeError):
            pass
        
        # Parse nested WorkoutStatistics
        for stat in elem.iter('WorkoutStatistics'):
            stat_type = stat.get('type', '').split('/')[-1]
            if 'EnergyBurned' in stat_type:
                try:
                    workout['totalEnergyBurned_kcal'] = round(float(stat.get('sum', '0')), 1)
                except (ValueError, TypeError):
                    pass
            elif 'Distance' in stat_type:
                try:
                    workout['totalDistance_m'] = round(float(stat.get('sum', '0')), 1)
                except (ValueError, TypeError):
                    pass
        
        # Parse metadata
        metadata = {}
        for meta in elem.iter('MetadataEntry'):
            key = meta.get('key', '').split('/')[-1]
            metadata[key] = meta.get('value', '')
        
        if metadata:
            workout['indoor'] = metadata.get('HKIndoorWorkout', '')
            workout['pool_length'] = metadata.get('HKLapLength', '')
            workout['elevation_ascended'] = metadata.get('HKElevationAscended', '')
        
        self.workouts.append(workout)
    
    def _handle_activity_summary(self, elem):
        """Process an ActivitySummary element."""
        summary = {
            'date': elem.get('dateComponents', ''),
            'activeEnergyBurned': elem.get('activeEnergyBurned', ''),
            'activeEnergyBurnedGoal': elem.get('activeEnergyBurnedGoal', ''),
            'appleMoveTime': elem.get('appleMoveTime', ''),
            'appleMoveTimeGoal': elem.get('appleMoveTimeGoal', ''),
            'appleExerciseTime': elem.get('appleExerciseTime', ''),
            'appleExerciseTimeGoal': elem.get('appleExerciseTimeGoal', ''),
            'appleStandHours': elem.get('appleStandHours', ''),
            'appleStandHoursGoal': elem.get('appleStandHoursGoal', ''),
        }
        self.activity_summaries.append(summary)
    
    def _write_outputs(self):
        """Write all collected data to CSV files."""
        files_written = []
        
        # Types that need source-based deduplication (additive metrics where
        # multiple devices record overlapping data, e.g. both iPhone and Watch
        # counting steps simultaneously → double-counting if summed naively).
        NEEDS_SOURCE_DEDUP = {'StepCount', 'DistanceWalkRun', 'FlightsClimbed', 'ActiveEnergy'}
        
        # 1. Daily aggregated data
        for type_name, daily_data in self.daily_agg.items():
            if not daily_data:
                continue
            
            filename = f"{type_name.lower()}_daily.csv"
            filepath = os.path.join(self.output_dir, filename)
            
            with open(filepath, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['date', 'sum', 'mean', 'min', 'max', 'std', 'count', 'sources'])
                
                for date in sorted(daily_data.keys()):
                    vals = daily_data[date]['values']
                    sources = daily_data[date]['sources']
                    
                    # Source-level deduplication for additive metrics:
                    # When multiple sources record the same metric (e.g. iPhone + Watch
                    # both count steps), pick only the highest-priority source's sum.
                    # For non-additive metrics (like HeartRate), keep the full aggregate.
                    if type_name in NEEDS_SOURCE_DEDUP and len(sources) > 1:
                        source_sums = daily_data[date].get('source_values', {})
                        if source_sums:
                            # Pick best source by priority
                            best_source = min(
                                source_sums.keys(),
                                key=lambda src: SOURCE_PRIORITY.get(classify_source(src), 99)
                            )
                            s = source_sums[best_source]
                            n = daily_data[date].get('source_counts', {}).get(best_source, 1)
                            mean = s / n if n > 0 else 0
                            # min/max/std not recoverable per-source without storing
                            # all individual values per source; set to sum-derived values
                            # to signal they are not meaningful for deduped additive data.
                            mn = mean
                            mx = mean
                            std = 0
                        else:
                            # Fallback: no per-source data (shouldn't happen)
                            n = len(vals)
                            s = sum(vals)
                            mean = s / n
                            mn = min(vals)
                            mx = max(vals)
                            std = math.sqrt(sum((v - mean) ** 2 for v in vals) / (n - 1)) if n > 1 else 0
                    else:
                        n = len(vals)
                        s = sum(vals)
                        mean = s / n
                        mn = min(vals)
                        mx = max(vals)
                        # Sample standard deviation (n-1 denominator, Bessel's correction)
                        std = math.sqrt(sum((v - mean) ** 2 for v in vals) / (n - 1)) if n > 1 else 0
                    
                    writer.writerow([
                        date,
                        round(s, 2),
                        round(mean, 2),
                        round(mn, 2),
                        round(mx, 2),
                        round(std, 2),
                        n,
                        '|'.join(sorted(sources)),
                    ])
            
            files_written.append((filename, len(daily_data)))
        
        # 2. Individual records
        for type_name, records in self.individual.items():
            if not records:
                continue
            
            filename = f"{type_name.lower()}.csv"
            filepath = os.path.join(self.output_dir, filename)
            
            with open(filepath, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=['date', 'startDate', 'value', 'unit', 'sourceName'])
                writer.writeheader()
                for rec in sorted(records, key=lambda r: r['date']):
                    writer.writerow(rec)
            
            files_written.append((filename, len(records)))
        
        # 3. Sleep records
        if self.sleep_records:
            filename = 'sleep_analysis.csv'
            filepath = os.path.join(self.output_dir, filename)
            
            with open(filepath, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=['startDate', 'endDate', 'value', 'sourceName'])
                writer.writeheader()
                for rec in sorted(self.sleep_records, key=lambda r: r['startDate']):
                    writer.writerow(rec)
            
            files_written.append((filename, len(self.sleep_records)))
        
        # 4. Category records
        for type_name, records in self.category_records.items():
            if not records:
                continue
            
            filename = f"{type_name.lower()}.csv"
            filepath = os.path.join(self.output_dir, filename)
            
            with open(filepath, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=['date', 'startDate', 'endDate', 'value', 'sourceName'])
                writer.writeheader()
                for rec in sorted(records, key=lambda r: r['date']):
                    writer.writerow(rec)
            
            files_written.append((filename, len(records)))
        
        # 5. Workouts
        if self.workouts:
            filename = 'workouts.csv'
            filepath = os.path.join(self.output_dir, filename)
            
            fields = ['date', 'startDate', 'endDate', 'type', 'duration_min',
                      'totalEnergyBurned_kcal', 'totalDistance_m', 'sourceName',
                      'indoor', 'pool_length', 'elevation_ascended']
            
            with open(filepath, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
                writer.writeheader()
                for w in sorted(self.workouts, key=lambda r: r['date']):
                    writer.writerow(w)
            
            files_written.append((filename, len(self.workouts)))
        
        # 6. Activity summaries
        if self.activity_summaries:
            filename = 'activity_summary.csv'
            filepath = os.path.join(self.output_dir, filename)
            
            fields = ['date', 'activeEnergyBurned', 'activeEnergyBurnedGoal',
                      'appleMoveTime', 'appleMoveTimeGoal',
                      'appleExerciseTime', 'appleExerciseTimeGoal',
                      'appleStandHours', 'appleStandHoursGoal']
            
            with open(filepath, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fields)
                writer.writeheader()
                for s in sorted(self.activity_summaries, key=lambda r: r['date']):
                    writer.writerow(s)
            
            files_written.append((filename, len(self.activity_summaries)))
        
        # Write extraction summary
        summary = {
            'extraction_time': datetime.now().isoformat(),
            'input_file': self.input_path,
            'modules': self.modules,
            'start_date_filter': self.start_date,
            'total_elements_processed': self.processed,
            'total_elements_skipped': self.skipped,
            'files': [{'name': name, 'rows': rows} for name, rows in files_written],
        }
        
        summary_path = os.path.join(self.output_dir, 'extraction_summary.json')
        with open(summary_path, 'w') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        print(f"\nOutput directory: {self.output_dir}")
        print(f"Files written:")
        for name, rows in sorted(files_written):
            print(f"  {name}: {rows:,} rows")
        print(f"  extraction_summary.json")


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='Apple Health XML Parser')
    parser.add_argument('--input', '-i', required=True, help='Path to export.xml or 导出.xml')
    parser.add_argument('--output-dir', '-o', default='./health_data/', help='Output directory for CSV files')
    parser.add_argument('--profile-only', action='store_true', help='Only profile the data (fast scan)')
    parser.add_argument('--modules', '-m', default=None, 
                       help='Comma-separated modules: activity,heartrate,sleep,menstrual,workout,body,mobility,audio,swimming')
    parser.add_argument('--start-date', '-s', default=None, help='Start date filter (YYYY-MM-DD)')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.input):
        print(f"Error: File not found: {args.input}")
        sys.exit(1)
    
    if args.profile_only:
        profile = profile_xml(args.input)
        
        # Write profile to output dir
        os.makedirs(args.output_dir, exist_ok=True)
        profile_path = os.path.join(args.output_dir, 'health_profile.json')
        with open(profile_path, 'w') as f:
            json.dump(profile, f, indent=2, ensure_ascii=False)
        
        print(f"\nProfile saved to: {profile_path}")
        print(f"\n{'='*50}")
        print(f"FILE: {profile['file_info']['size_mb']} MB")
        print(f"USER: {profile['user_info']}")
        print(f"TIER: {profile['device_tier']['description']}")
        print(f"RECORDS: {profile['total_records']:,}")
        print(f"WORKOUTS: {profile['total_workouts']:,}")
        print(f"ACTIVITY DAYS: {profile['activity_summary_count']:,}")
        print(f"DATA YEARS: {profile['data_years']}")
        print(f"AVAILABLE MODULES: {profile['available_modules']}")
        print(f"PROFILE TIME: {profile['file_info']['profile_time_seconds']}s")
    else:
        modules = args.modules.split(',') if args.modules else None
        
        extractor = HealthDataExtractor(
            input_path=args.input,
            output_dir=args.output_dir,
            modules=modules,
            start_date=args.start_date,
        )
        extractor.extract()


if __name__ == '__main__':
    main()
