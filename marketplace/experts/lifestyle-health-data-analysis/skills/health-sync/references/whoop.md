# WHOOP Schema (provider = 'whoop')

This file describes how WHOOP data is stored in the `health-sync` SQLite cache (`health.sqlite`).

At a glance:

- Table: `records`
- Provider: `provider = 'whoop'`
- Resources: `profile_basic`, `body_measurement`, `cycles`, `recoveries`, `sleep`, `workouts`
- Storage model: one row per WHOOP document, raw JSON in `payload_json`

Important notes about timestamps and watermarks:

- `profile_basic` and `body_measurement` are snapshot-style resources and use sync-time watermarks.
- Collection resources (`cycles`, `recoveries`, `sleep`, `workouts`) use incremental windows:
  - query params include `start`, `end`, `limit`, and pagination via `nextToken`
  - `sync_state.watermark` tracks max observed event time and is stored as UTC ISO
  - next run subtracts configured overlap days from previous watermark to avoid edge misses

## Resource Map

### `profile_basic` (User Profile Snapshot)

- Upstream endpoint: `GET /v2/user/profile/basic`
- `record_id`: `$.user_id` (fallback: `"me"`)
- `start_time`: `$.created_at` when present, else NULL
- `end_time`: NULL
- `source_updated_at`: `$.updated_at` when present, else sync time

Common `payload_json` keys:

- `user_id`
- `email`
- `first_name`
- `last_name`

### `body_measurement` (User Body Snapshot)

- Upstream endpoint: `GET /v2/user/measurement/body`
- `record_id`: `$.user_id` when present, fallback `"me"`
- `start_time`: `$.created_at` when present, else NULL
- `end_time`: NULL
- `source_updated_at`: `$.updated_at` when present, else sync time

Common `payload_json` keys:

- `height_meter`
- `weight_kilogram`
- `max_heart_rate`

### `cycles`

- Upstream endpoint: `GET /v2/cycle`
- Request params used by this project:
  - `limit` (default 25, max 25)
  - `start` (UTC ISO)
  - `end` (UTC ISO)
  - `nextToken` (for pagination)
- `record_id`: `$.id` (fallback: SHA-256 hash of payload)
- `start_time`: `$.start` (fallback: `$.created_at` / `$.updated_at`)
- `end_time`: `$.end`
- `source_updated_at`: `$.updated_at` (fallback: `$.created_at` / `$.start`)

Common `payload_json` keys:

- `id`
- `user_id`
- `created_at`
- `updated_at`
- `start`
- `end`
- `timezone_offset`
- `score_state`
- `score.*` (strain and cycle-level metrics)

### `recoveries`

- Upstream endpoint: `GET /v2/recovery`
- Request params used by this project:
  - `limit` (default 25, max 25)
  - `start` (UTC ISO)
  - `end` (UTC ISO)
  - `nextToken` (for pagination)
- `record_id`: `$.cycle_id` (fallback: SHA-256 hash of payload)
- `start_time`: `$.start` when present, otherwise `$.created_at` or `$.updated_at`
- `end_time`: `$.end` when present, else NULL
- `source_updated_at`: `$.updated_at` (fallback: `$.created_at` / start time)

Common `payload_json` keys:

- `cycle_id`
- `sleep_id`
- `user_id`
- `created_at`
- `updated_at`
- `score_state`
- `score.*` (recovery score, HRV, resting heart rate, etc.)

### `sleep`

- Upstream endpoint: `GET /v2/activity/sleep`
- Request params used by this project:
  - `limit` (default 25, max 25)
  - `start` (UTC ISO)
  - `end` (UTC ISO)
  - `nextToken` (for pagination)
- `record_id`: `$.id` (fallback: SHA-256 hash of payload)
- `start_time`: `$.start`
- `end_time`: `$.end`
- `source_updated_at`: `$.updated_at` (fallback: `$.created_at` / `$.start`)

Common `payload_json` keys:

- `id`
- `cycle_id`
- `user_id`
- `created_at`
- `updated_at`
- `start`
- `end`
- `nap`
- `score_state`
- `score.*` (sleep performance, stage durations, etc.)

### `workouts`

- Upstream endpoint: `GET /v2/activity/workout`
- Request params used by this project:
  - `limit` (default 25, max 25)
  - `start` (UTC ISO)
  - `end` (UTC ISO)
  - `nextToken` (for pagination)
- `record_id`: `$.id` (fallback: SHA-256 hash of payload)
- `start_time`: `$.start`
- `end_time`: `$.end`
- `source_updated_at`: `$.updated_at` (fallback: `$.created_at` / `$.start`)

Common `payload_json` keys:

- `id`
- `user_id`
- `created_at`
- `updated_at`
- `start`
- `end`
- `sport_name`
- `sport_id` (legacy compatibility field)
- `score_state`
- `score.*` (strain, average HR, max HR, zone durations)

## `sync_state` Notes (WHOOP)

WHOOP sync state entries are resource-specific:

- `sync_state.provider = 'whoop'`
- `sync_state.resource` in:
  - `profile_basic`
  - `body_measurement`
  - `cycles`
  - `recoveries`
  - `sleep`
  - `workouts`

Watermark behavior:

- Snapshot resources (`profile_basic`, `body_measurement`) store sync-time watermark.
- Collection resources store max observed event timestamp in the run.
- Collection query start date is computed as:
  - previous watermark minus `[whoop].overlap_days`, or
  - `[whoop].start_date` on first sync.

## Common Analysis Queries

Recent WHOOP sleep sessions:

```sql
select
  start_time as sleep_start,
  end_time as sleep_end,
  json_extract(payload_json, '$.score_state') as score_state,
  json_extract(payload_json, '$.score.sleep_performance_percentage') as sleep_perf_pct,
  json_extract(payload_json, '$.score.stage_summary.total_in_bed_time_milli') / 60000.0 as in_bed_minutes
from records
where provider = 'whoop' and resource = 'sleep'
order by sleep_start desc
limit 30;
```

Recent WHOOP recovery scores:

```sql
select
  source_updated_at as observed_at,
  json_extract(payload_json, '$.cycle_id') as cycle_id,
  json_extract(payload_json, '$.score.recovery_score') as recovery_score,
  json_extract(payload_json, '$.score.hrv_rmssd_milli') as hrv_rmssd,
  json_extract(payload_json, '$.score.resting_heart_rate') as resting_hr
from records
where provider = 'whoop' and resource = 'recoveries'
order by observed_at desc
limit 30;
```

Monthly workout strain totals by sport:

```sql
select
  substr(start_time, 1, 7) as month,
  json_extract(payload_json, '$.sport_name') as sport_name,
  round(sum(coalesce(json_extract(payload_json, '$.score.strain'), 0)), 2) as total_strain,
  count(*) as workouts
from records
where provider = 'whoop' and resource = 'workouts'
group by month, sport_name
order by month desc, workouts desc;
```

Coverage and watermark sanity check:

```sql
select
  (select min(start_time) from records where provider = 'whoop' and resource = 'sleep') as min_sleep_start,
  (select max(start_time) from records where provider = 'whoop' and resource = 'sleep') as max_sleep_start,
  (select watermark from sync_state where provider = 'whoop' and resource = 'sleep') as sleep_sync_watermark,
  (select watermark from sync_state where provider = 'whoop' and resource = 'workouts') as workout_sync_watermark;
```
