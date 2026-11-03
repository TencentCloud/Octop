# Apple Health Data Type Reference

Complete mapping of HealthKit type identifiers to human-readable names, units, expected ranges, aggregation strategies, and analysis notes.

## Record Types — Quantity (HKQuantityTypeIdentifier)

### Heart & Cardiovascular

| Type Identifier | Display Name | Unit | Normal Range | Aggregation | Notes |
|---|---|---|---|---|---|
| `HeartRate` | Heart Rate | count/min (bpm) | 60–100 bpm (rest) | Daily: min, max, mean, std, count | Highest volume metric (~1M+ records). MUST aggregate during parsing. |
| `RestingHeartRate` | Resting Heart Rate | count/min | 60–100 bpm | Keep individual (1/day) | Key fitness indicator. Lower = generally better fitness. Requires Watch. |
| `HeartRateVariabilitySDNN` | HRV (SDNN) | ms | 20–200 ms (age-dependent) | Keep individual | Higher = better recovery/lower stress. Highly individual — track trend, not absolute. |
| `HeartRateRecoveryOneMinute` | HR Recovery (1min) | count/min | >12 bpm drop is normal | Keep individual | Measured after workout. Good fitness = faster recovery. |
| `WalkingHeartRateAverage` | Walking Avg HR | count/min | Age-dependent | Keep individual (1/day) | Proxy for cardiovascular efficiency during daily activity. |
| `VO2Max` | VO2 Max | mL/min·kg | Age/sex tables (see below) | Keep individual | Gold standard cardio fitness. Watch estimates from outdoor walks/runs. |
| `OxygenSaturation` | Blood Oxygen (SpO2) | % | 95–100% | Daily: min, mean | <95% may warrant medical attention. Nighttime readings most useful. |
| `BloodGlucose` | Blood Glucose | mg/dL | 70–100 (fasting) | Keep individual | Usually from 3rd-party CGM. Sparse for most users. |

### Respiratory

| Type Identifier | Display Name | Unit | Normal Range | Aggregation | Notes |
|---|---|---|---|---|---|
| `RespiratoryRate` | Respiratory Rate | count/min | 12–20 breaths/min | Daily: min, mean, max | Measured during sleep by Watch. Elevated rate can indicate illness. |
| `AppleSleepingBreathingDisturbances` | Sleep Breathing Disturbances | count/hr | <5 events/hr | Daily: mean | Potential sleep apnea indicator. New in watchOS 11. |

### Activity & Energy

| Type Identifier | Display Name | Unit | Normal Range | Aggregation | Notes |
|---|---|---|---|---|---|
| `StepCount` | Step Count | count | 7,000–10,000/day | Daily sum (deduplicated) | **DEDUP REQUIRED**: iPhone + Watch both record. Use Apple's priority or pick one source. |
| `DistanceWalkingRunning` | Walk + Run Distance | km or mi | — | Daily sum (deduplicated) | Same dedup logic as steps. |
| `FlightsClimbed` | Flights Climbed | count | — | Daily sum | 1 flight ≈ 3 meters altitude gain (~10 feet). |
| `ActiveEnergyBurned` | Active Calories | kcal | 200–800 kcal/day | Daily sum | From Watch + motion data. Part of Move ring. |
| `BasalEnergyBurned` | Resting Calories | kcal | 1,200–2,000 kcal/day | Daily sum | Estimated BMR. Watch-only. |
| `AppleExerciseTime` | Exercise Minutes | min | 30 min/day goal | Daily sum | Part of Exercise ring. Watch-only. |
| `AppleStandTime` | Stand Time | min | — | Daily sum | Watch-only metric. |
| `PhysicalEffort` | Physical Effort | applePhysicalEffortEstimateType | — | Daily summary | watchOS 10+. Aggregate by effort level distribution. |

### Swimming

| Type Identifier | Display Name | Unit | Normal Range | Aggregation | Notes |
|---|---|---|---|---|---|
| `DistanceSwimming` | Swim Distance | m | — | Per-workout sum | Recorded during swim workouts only. |
| `SwimmingStrokeCount` | Stroke Count | count | — | Per-workout sum | Combined with distance for stroke efficiency. |
| `UnderwaterDepth` | Dive Depth | m | — | Per-session max | Apple Watch Ultra only. |
| `WaterTemperature` | Water Temperature | °C | — | Per-session mean | Apple Watch Ultra / depth sensor. |

### Body Measurements

| Type Identifier | Display Name | Unit | Normal Range | Aggregation | Notes |
|---|---|---|---|---|---|
| `BodyMass` | Weight | kg or lb | BMI 18.5–24.9 | Keep individual | Often manual entry or smart scale. Sparse data. |
| `BodyMassIndex` | BMI | count | 18.5–24.9 | Keep individual | Calculated from weight + height. |
| `BodyFatPercentage` | Body Fat % | % | Women: 21–33%, Men: 8–19% | Keep individual | Smart scale data. Accuracy varies. |
| `Height` | Height | cm or in | — | Keep individual | Usually recorded once. |
| `LeanBodyMass` | Lean Body Mass | kg | — | Keep individual | If available from smart scale. |

### Mobility & Gait

| Type Identifier | Display Name | Unit | Normal Range | Aggregation | Notes |
|---|---|---|---|---|---|
| `WalkingSpeed` | Walking Speed | km/hr | 3–6 km/hr | Daily: mean | iPhone motion coprocessor. Available from iOS 14+. |
| `WalkingStepLength` | Step Length | cm | 50–80 cm | Daily: mean | Gait analysis metric. |
| `WalkingDoubleSupportPercentage` | Double Support Time | % | 20–40% | Daily: mean | Lower = better balance. |
| `WalkingAsymmetryPercentage` | Walking Asymmetry | % | <10% ideal | Daily: mean | Left-right imbalance. High values may indicate injury. |
| `StairAscentSpeed` | Stair Climb Speed | m/s | — | Daily: mean | Functional fitness indicator. |
| `StairDescentSpeed` | Stair Descent Speed | m/s | — | Daily: mean | Balance and lower limb control. |
| `SixMinuteWalkTestDistance` | 6-Min Walk Distance | m | >400m typically healthy | Keep individual | Clinical mobility assessment proxy. |
| `AppleWalkingSteadiness` | Walking Steadiness | % | OK / Low / Very Low | Keep individual | Fall risk indicator. |

### Audio Exposure

| Type Identifier | Display Name | Unit | Normal Range | Aggregation | Notes |
|---|---|---|---|---|---|
| `HeadphoneAudioExposure` | Headphone Level | dBASPL | <80 dB safe | Daily: mean, max | Hearing health. >80 dB prolonged = risk. |
| `EnvironmentalAudioExposure` | Environmental Noise | dBASPL | <80 dB safe | Daily: mean, max | Watch microphone measurements. |
| `EnvironmentalSoundReduction` | Sound Reduction | dBASPL | — | Daily summary | Active noise reduction metrics. |

### Sleep & Temperature

| Type Identifier | Display Name | Unit | Normal Range | Aggregation | Notes |
|---|---|---|---|---|---|
| `AppleSleepingWristTemperature` | Wrist Temperature | °C (deviation) | ±1°C from baseline | Keep individual | Relative to personal baseline. Cycle tracking correlation. Watch Series 8+. |

### Time in Daylight

| Type Identifier | Display Name | Unit | Normal Range | Aggregation | Notes |
|---|---|---|---|---|---|
| `TimeInDaylight` | Daylight Exposure | min | 30+ min/day recommended | Daily sum | New in watchOS 10. Circadian rhythm and mood correlation. |

## Record Types — Category (HKCategoryTypeIdentifier)

### Sleep

| Type Identifier | Display Name | Values | Notes |
|---|---|---|---|
| `SleepAnalysis` | Sleep Analysis | `InBed`, `AsleepUnspecified`, `Awake`, `AsleepCore`, `AsleepDeep`, `AsleepREM` | Each record has startDate/endDate defining a time interval. Multiple records per night. Stage-level data requires Watch Series 3+ with watchOS 9+. |
| `SleepDurationGoal` | Sleep Goal | minutes | Usually a single record. |

### Reproductive Health

| Type Identifier | Display Name | Values | Notes |
|---|---|---|---|
| `MenstrualFlow` | Menstrual Flow | `HKCategoryValueMenstrualFlowUnspecified`, `Light`, `Medium`, `Heavy`, `None` | Track period start/end and flow intensity. |
| `IntermenstrualBleeding` | Spotting | `HKCategoryValueNotApplicable` | Bleeding between periods. |
| `Pregnancy` | Pregnancy | (boolean presence) | Date indicates when pregnancy was recorded. |
| `PregnancyTestResult` | Pregnancy Test | `Positive`, `Negative`, `Indeterminate` | Home test results. |
| `ProgesteroneTestResult` | Progesterone Test | `Positive`, `Negative`, `Indeterminate` | Ovulation predictor. |
| `Lactation` | Breastfeeding | (boolean presence) | If recorded. |

### Activity

| Type Identifier | Display Name | Values | Notes |
|---|---|---|---|
| `AppleStandHour` | Stand Hour | `Stood`, `Idle` | Part of Stand ring. Hourly records. |
| `MindfulSession` | Mindfulness | (time interval) | From Breathe app or 3rd-party. |

### Audio

| Type Identifier | Display Name | Values | Notes |
|---|---|---|---|
| `AudioExposureEvent` | Audio Exposure Alert | (notification events) | Triggered when sustained loud exposure detected. |

## Workout Types (HKWorkoutActivityType)

| Activity Type | Display Name | Key Metrics | Notes |
|---|---|---|---|
| `TraditionalStrengthTraining` | Strength Training | duration, activeEnergy | Most common for gym users. No distance. |
| `FunctionalStrengthTraining` | Functional Training | duration, activeEnergy | Bodyweight / functional movements. |
| `Walking` | Walking | duration, distance, activeEnergy | Often with GPS route. |
| `Running` | Running | duration, distance, activeEnergy | Heart rate zones important. |
| `Swimming` | Swimming | duration, distance, strokeCount | Pool vs. open water (check metadata). |
| `Cycling` | Cycling | duration, distance, activeEnergy | Indoor vs. outdoor. |
| `HighIntensityIntervalTraining` | HIIT | duration, activeEnergy | Short duration, high calorie. |
| `Yoga` | Yoga | duration, activeEnergy | Low-moderate intensity. |
| `Pilates` | Pilates | duration, activeEnergy | Core-focused. |
| `CoreTraining` | Core Training | duration, activeEnergy | Ab-specific work. |
| `Elliptical` | Elliptical | duration, activeEnergy | Gym cardio. |
| `Rowing` | Rowing | duration, distance, activeEnergy | Indoor rower. |
| `StairClimbing` | Stair Climbing | duration, activeEnergy, flightsClimbed | StairMaster or real stairs. |
| `MixedCardio` | Mixed Cardio | duration, activeEnergy | Catch-all cardio. |
| `CrossTraining` | Cross Training | duration, activeEnergy | Multi-modal. |
| `Cooldown` | Cooldown | duration | Post-workout recovery. |
| `FitnessGaming` | Fitness Gaming | duration, activeEnergy | Ring Fit, Beat Saber, etc. |
| `Other` | Other Workout | duration, activeEnergy | Unclassified. |

## Workout Record Fields

Each `<Workout>` element contains:
- `workoutActivityType`: HKWorkoutActivityType string
- `duration`: Duration in `durationUnit` (usually minutes)
- `totalEnergyBurned`: kcal (if tracked)
- `totalDistance`: meters or km (if applicable)
- `startDate`, `endDate`: Timestamps with timezone
- `sourceName`: Device/app that recorded it
- Nested `<WorkoutStatistics>`: Per-metric stats (sum, avg, min, max)
- Nested `<WorkoutEvent>`: Lap markers, pause/resume events
- Nested `<MetadataEntry>`: Additional context (indoor/outdoor, pool length, etc.)

## ActivitySummary Fields

Each `<ActivitySummary>` element:
- `dateComponents`: Date string (YYYY-MM-DD)
- `activeEnergyBurned`: kcal (Move ring)
- `activeEnergyBurnedGoal`: kcal target
- `appleMoveTime`: minutes
- `appleMoveTimeGoal`: minutes target
- `appleExerciseTime`: minutes (Exercise ring)
- `appleExerciseTimeGoal`: minutes target (default 30)
- `appleStandHours`: hours (Stand ring)
- `appleStandHoursGoal`: hours target (default 12)

## VO2Max Reference Ranges (mL/min·kg)

### Women

| Age | Low | Below Avg | Average | Above Avg | High | Elite |
|-----|-----|-----------|---------|-----------|------|-------|
| 20–29 | <24 | 24–28 | 29–32 | 33–36 | 37–41 | >41 |
| 30–39 | <22 | 22–26 | 27–30 | 31–34 | 35–39 | >39 |
| 40–49 | <20 | 20–24 | 25–28 | 29–32 | 33–37 | >37 |
| 50–59 | <18 | 18–21 | 22–25 | 26–29 | 30–34 | >34 |

### Men

| Age | Low | Below Avg | Average | Above Avg | High | Elite |
|-----|-----|-----------|---------|-----------|------|-------|
| 20–29 | <30 | 30–36 | 37–42 | 43–48 | 49–55 | >55 |
| 30–39 | <28 | 28–34 | 35–40 | 41–46 | 47–53 | >53 |
| 40–49 | <26 | 26–31 | 32–37 | 38–43 | 44–50 | >50 |
| 50–59 | <24 | 24–28 | 29–34 | 35–40 | 41–47 | >47 |

## Sleep Duration Recommendations (National Sleep Foundation)

| Age Group | Recommended | May Be Appropriate | Not Recommended |
|-----------|------------|-------------------|-----------------|
| Young Adults (18–25) | 7–9 hrs | 6 or 10–11 hrs | <6 or >11 hrs |
| Adults (26–64) | 7–9 hrs | 6 or 10 hrs | <6 or >10 hrs |
| Older Adults (65+) | 7–8 hrs | 5–6 or 9 hrs | <5 or >9 hrs |

## Resting Heart Rate Reference

| Category | RHR Range | Interpretation |
|----------|----------|----------------|
| Athletic | 40–54 bpm | Excellent cardiovascular fitness |
| Excellent | 55–61 bpm | Very good fitness level |
| Good | 62–65 bpm | Above average |
| Average | 66–73 bpm | Normal range |
| Below Average | 74–81 bpm | Room for improvement |
| Poor | >82 bpm | Consider increasing cardio activity |

*Note: Values are general guidelines. Individual variation is significant. Medications (beta-blockers), caffeine, and illness all affect RHR.*
