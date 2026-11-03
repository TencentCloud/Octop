# Oura Schema (provider = 'oura')

This file describes how Oura data is stored in the `health-sync` SQLite cache (`health.sqlite`).

At a glance:

- Table: `records`
- Provider: `provider = 'oura'`
- Resources: `personal_info`, `daily_activity`, `daily_sleep`, `daily_readiness`, `sleep`, `workout`, `heartrate`
- Storage model: one row per Oura document, raw JSON in `payload_json`

Important note about time columns:

- For many Oura resources, `records.start_time` is a **date string** (`YYYY-MM-DD`) even when the payload contains full datetimes.
- For precise timestamps, prefer `json_extract(payload_json, '$.start_datetime')`, `$.end_datetime`, `$.bedtime_start`, etc.

## Resource Map

### `personal_info`

- Upstream endpoint: `GET /v2/usercollection/personal_info`
- `record_id`: always `"me"` (this sync stores one row)
- `start_time` / `end_time`: NULL
- `source_updated_at`: NULL

`payload_json` keys:

- `id` (string)
- `age` (number)
- `weight` (number)
- `height` (number)
- `biological_sex` (string)
- `email` (string)

### `daily_activity`

- Upstream endpoint: `GET /v2/usercollection/daily_activity`
- `record_id`: `$.id` (fallback: `$.day`)
- `start_time`: `$.day` (YYYY-MM-DD)
- `source_updated_at`: `$.updated_at` or `$.modified_at` or `$.timestamp` (implementation-dependent; often `timestamp`)

`payload_json` keys (top-level):

- `id`
- `day`
- `timestamp`
- `score`
- `contributors` (object)
- `steps`
- `class_5_min`
- `active_calories`
- `total_calories`
- `equivalent_walking_distance`
- `meters_to_target`
- `target_meters`
- `target_calories`
- `average_met_minutes`
- `high_activity_met_minutes`, `high_activity_time`
- `medium_activity_met_minutes`, `medium_activity_time`
- `low_activity_met_minutes`, `low_activity_time`
- `sedentary_met_minutes`, `sedentary_time`
- `resting_time`
- `non_wear_time`
- `inactivity_alerts`
- `met`

`contributors` keys:

- `meet_daily_targets`
- `move_every_hour`
- `recovery_time`
- `stay_active`
- `training_frequency`
- `training_volume`

### `daily_sleep`

- Upstream endpoint: `GET /v2/usercollection/daily_sleep`
- `record_id`: `$.id` (fallback: `$.day`)
- `start_time`: `$.day` (YYYY-MM-DD)
- `source_updated_at`: `$.updated_at` or `$.modified_at` or `$.timestamp`

`payload_json` keys:

- `id`
- `day`
- `timestamp`
- `score`
- `contributors` (object)

`contributors` keys:

- `deep_sleep`
- `efficiency`
- `latency`
- `rem_sleep`
- `restfulness`
- `timing`
- `total_sleep`

### `daily_readiness`

- Upstream endpoint: `GET /v2/usercollection/daily_readiness`
- `record_id`: `$.id` (fallback: `$.day`)
- `start_time`: `$.day` (YYYY-MM-DD)
- `source_updated_at`: `$.updated_at` or `$.modified_at` or `$.timestamp`

`payload_json` keys:

- `id`
- `day`
- `timestamp`
- `score`
- `contributors` (object)
- `temperature_deviation`
- `temperature_trend_deviation`

`contributors` keys:

- `activity_balance`
- `body_temperature`
- `hrv_balance`
- `previous_day_activity`
- `previous_night`
- `recovery_index`
- `resting_heart_rate`
- `sleep_balance`
- `sleep_regularity`

### `sleep`

- Upstream endpoint: `GET /v2/usercollection/sleep`
- `record_id`: `$.id` (fallback: `$.day`)
- `start_time`: `$.day` (YYYY-MM-DD) (note: payload includes precise bedtime datetimes)
- `end_time`: NULL (note: payload includes bedtime datetimes)
- `source_updated_at`: `$.updated_at` or `$.modified_at` or `$.timestamp` (when present)

`payload_json` keys (top-level):

- `id`
- `day`
- `type`
- `period`
- `bedtime_start` (ISO datetime with timezone offset)
- `bedtime_end` (ISO datetime with timezone offset)
- `average_heart_rate` (number)
- `lowest_heart_rate` (number)
- `average_hrv` (integer)
- `average_breath` (number)
- `efficiency` (integer)
- `latency` (integer)
- `awake_time` (integer)
- `restless_periods` (integer)
- `time_in_bed` (integer)
- `total_sleep_duration` (integer)
- `deep_sleep_duration` (integer)
- `light_sleep_duration` (integer)
- `rem_sleep_duration` (integer)
- `movement_30_sec` (string)
- `sleep_phase_5_min` (string)
- `sleep_score_delta` (integer)
- `readiness_score_delta` (integer)
- `sleep_algorithm_version` (string)
- `sleep_analysis_reason` (string)
- `low_battery_alert` (boolean)
- `heart_rate` (object, time-series)
- `hrv` (object, time-series)
- `readiness` (object)

`heart_rate` and `hrv` (time-series) shape:

- `interval` (number): sample interval
- `timestamp` (datetime): series start timestamp
- `items` (array): samples

### `workout`

- Upstream endpoint: `GET /v2/usercollection/workout`
- `record_id`: `$.id` (fallback: `$.day` or hash)
- `start_time`: `$.day` (YYYY-MM-DD) (note: payload includes `start_datetime`)
- `end_time`: `$.end_datetime` (ISO datetime; populated when present in payload)
- `source_updated_at`: `$.updated_at` or `$.modified_at` or `$.timestamp` (often NULL for workout rows)

`payload_json` keys:

- `id`
- `day`
- `activity`
- `start_datetime` (ISO datetime)
- `end_datetime` (ISO datetime)
- `calories`
- `distance`
- `intensity`
- `label`
- `source`

### `heartrate`

- Upstream endpoint: `GET /v2/usercollection/heartrate`
- `record_id`: `$.timestamp` (fallback: hash)
- `start_time`: `$.timestamp` (ISO datetime with `Z`)
- `end_time`: NULL
- `source_updated_at`: same as `start_time` (timestamp)

`payload_json` keys:

- `timestamp` (ISO datetime)
- `bpm` (integer)
- `source` (string, e.g. `awake`, `sleep`, `rest`)

## Common Analysis Queries

Daily readiness score (last 30 days):

```sql
select
  start_time as day,
  json_extract(payload_json, '$.score') as readiness_score
from records
where provider = 'oura' and resource = 'daily_readiness'
order by day desc
limit 30;
```

Sleep duration and efficiency (use payload fields; `records.start_time` is day-only):

```sql
select
  start_time as day,
  json_extract(payload_json, '$.total_sleep_duration') as total_sleep_s,
  json_extract(payload_json, '$.efficiency') as efficiency
from records
where provider = 'oura' and resource = 'sleep'
order by day desc
limit 30;
```

Workouts (use `start_datetime`/`end_datetime` from payload):

```sql
select
  json_extract(payload_json, '$.start_datetime') as start_dt,
  json_extract(payload_json, '$.end_datetime') as end_dt,
  json_extract(payload_json, '$.activity') as activity,
  json_extract(payload_json, '$.calories') as calories
from records
where provider = 'oura' and resource = 'workout'
order by start_dt desc
limit 50;
```

Heart rate daily average (UTC date derived from timestamp):

```sql
select
  substr(start_time, 1, 10) as day_utc,
  round(avg(json_extract(payload_json, '$.bpm')), 1) as avg_bpm,
  count(*) as samples
from records
where provider = 'oura' and resource = 'heartrate'
group by day_utc
order by day_utc desc
limit 30;
```
